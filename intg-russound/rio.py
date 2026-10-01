"""
Russound RIO Protocol Client.

Minimal asyncio client for the Russound RIO (Russound I/O) text protocol, which the
MCA-88, MCA-88X, MCA-C3/C5, MCA-66 and other Russound controllers expose on TCP port 9621.

Protocol summary:

- Commands are ASCII lines terminated with a carriage return, e.g. ``GET C[1].Z[1].volume``.
- Every command is answered with exactly one ``S`` (success) or ``E`` (error) line, in order.
- ``WATCH <branch> ON`` subscribes to a branch. The controller then sends ``N`` (notification)
  lines such as ``N C[1].Z[1].volume="20"`` whenever a value changes, starting with a dump
  of the current values.

The client allows one command in flight at a time, so each ``S``/``E`` line is matched to
the command that caused it. ``N`` lines are passed to the notification callback. A
periodic ``VERSION`` request serves as keep-alive; a timed-out command closes the
connection so the caller can reconnect with clean state.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import logging
import re
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass

_LOG = logging.getLogger(__name__)

DEFAULT_PORT = 9621
CONNECT_TIMEOUT = 5.0
REQUEST_TIMEOUT = 5.0
KEEPALIVE_INTERVAL = 30.0

_KEY_VALUE_RE = re.compile(r'^(?P<key>[^=\s]+)="(?P<value>.*)"$')

NotificationCallback = Callable[[str, str | None], None]


class RioError(Exception):
    """Base error for RIO communication."""


class RioConnectionError(RioError, ConnectionError):
    """The connection to the controller failed or was lost."""


class RioCommandError(RioError):
    """The controller answered a command with an ``E`` (error) response."""


@dataclass(frozen=True)
class RioMessage:
    """A single line received from the controller."""

    type: str
    """Message type: ``S`` (success), ``E`` (error) or ``N`` (notification)."""

    key: str | None = None
    """Full variable key, e.g. ``C[1].Z[1].volume``, if the line carries one."""

    value: str | None = None
    """Variable value, or the error text for ``E`` lines."""


def parse_line(line: str) -> RioMessage | None:
    """
    Parse one line received from the controller.

    :param line: Raw line without the line terminator
    :return: Parsed message, or None for empty or unrecognized lines
    """
    line = line.strip()
    if not line or line[0] not in "SNE":
        return None
    tag = line[0]
    payload = line[1:].strip()
    if tag == "E":
        return RioMessage("E", None, payload or None)
    if not payload:
        return RioMessage(tag)
    match = _KEY_VALUE_RE.match(payload)
    if not match:
        return RioMessage(tag, None, payload)
    return RioMessage(tag, match["key"], match["value"])


def split_key(key: str) -> tuple[str, str]:
    """
    Split a variable key into branch and leaf.

    ``C[1].Z[2].volume`` -> (``C[1].Z[2]``, ``volume``); ``VERSION`` -> (``""``, ``VERSION``).
    """
    if "." not in key:
        return "", key
    branch, leaf = key.rsplit(".", 1)
    return branch, leaf


def _decode(raw: bytes) -> str:
    """Decode a received line; newer firmware sends UTF-8, older firmware Latin-1."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


class RioClient:
    """Asynchronous RIO client for a single controller connection."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        on_notification: NotificationCallback | None = None,
        *,
        keepalive_interval: float | None = KEEPALIVE_INTERVAL,
        request_timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        """
        Create a client. Call :meth:`connect` to open the connection.

        :param host: IP address or hostname of the controller
        :param port: RIO TCP port
        :param on_notification: Called with (key, value) for each ``N`` line
        :param keepalive_interval: Seconds between keep-alive requests, None to disable
        :param request_timeout: Seconds to wait for a command response
        """
        self._host = host
        self._port = port
        self._on_notification = on_notification
        self._keepalive_interval = keepalive_interval
        self._request_timeout = request_timeout
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._pending: asyncio.Future | None = None
        self._lock = asyncio.Lock()
        self._closed = asyncio.Event()
        self._closed.set()

    @property
    def host(self) -> str:
        """Return the controller host."""
        return self._host

    @property
    def port(self) -> int:
        """Return the controller port."""
        return self._port

    @property
    def connected(self) -> bool:
        """Return True while the connection is open."""
        return self._writer is not None and not self._closed.is_set()

    async def connect(self) -> None:
        """
        Open the TCP connection and start the reader and keep-alive tasks.

        :raises RioConnectionError: If the controller cannot be reached
        """
        if self.connected:
            return
        _LOG.debug("Connecting to %s:%s", self._host, self._port)
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                reader, writer = await asyncio.open_connection(self._host, self._port)
        except (OSError, TimeoutError) as err:
            raise RioConnectionError(f"Cannot connect to {self._host}:{self._port}: {err or 'timeout'}") from err

        self._writer = writer
        self._closed.clear()
        self._reader_task = asyncio.create_task(self._read_loop(reader))
        if self._keepalive_interval:
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        _LOG.debug("Connected to %s:%s", self._host, self._port)

    async def close(self) -> None:
        """Close the connection and stop background tasks."""
        current = asyncio.current_task()
        for task in (self._keepalive_task, self._reader_task):
            if task and task is not current and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        self._keepalive_task = None
        self._reader_task = None
        self._shutdown("Connection closed")
        if self._writer is not None:
            with suppress(Exception):
                await self._writer.wait_closed()
            self._writer = None

    async def wait_closed(self) -> None:
        """Wait until the connection is closed or lost."""
        await self._closed.wait()

    async def request(self, command: str) -> str | None:
        """
        Send a command and wait for its response.

        :param command: RIO command without line terminator
        :return: The value of an ``S key="value"`` response, None for a bare ``S``
        :raises RioCommandError: If the controller answered with ``E``
        :raises RioConnectionError: If not connected, or no response arrived in time
        """
        async with self._lock:
            writer = self._writer
            if writer is None or not self.connected:
                raise RioConnectionError("Not connected")
            future: asyncio.Future[RioMessage] = asyncio.get_running_loop().create_future()
            self._pending = future
            try:
                _LOG.debug("send: %s", command)
                writer.write(f"{command}\r".encode())
                await writer.drain()
                async with asyncio.timeout(self._request_timeout):
                    message = await future
            except TimeoutError as err:
                # A late answer would be matched to the next command, so drop the connection.
                self._shutdown(f"Timeout waiting for response to '{command}'")
                raise RioConnectionError(f"Timeout waiting for response to '{command}'") from err
            except OSError as err:
                self._shutdown(f"Write failed: {err}")
                raise RioConnectionError(f"Write failed: {err}") from err
            finally:
                self._pending = None

        if message.type == "E":
            raise RioCommandError(f"'{command}' failed: {message.value or 'unknown error'}")
        return message.value

    async def get(self, key: str) -> str | None:
        """Read a variable, e.g. ``C[1].Z[1].name``."""
        return await self.request(f"GET {key}")

    async def set(self, key: str, value: str | int) -> None:
        """Write a variable, e.g. ``C[1].Z[1].bass`` = 2."""
        await self.request(f'SET {key}="{value}"')

    async def event(self, target: str, event: str, *args: str | int) -> None:
        """Send an event, e.g. ``EVENT C[1].Z[1]!KeyPress Volume 20``."""
        command = f"EVENT {target}!{event}"
        if args:
            command += " " + " ".join(str(arg) for arg in args)
        await self.request(command)

    async def watch(self, branch: str, enable: bool = True) -> None:
        """Subscribe to (or unsubscribe from) change notifications for a branch."""
        await self.request(f"WATCH {branch} {'ON' if enable else 'OFF'}")

    async def version(self) -> str | None:
        """Return the RIO protocol version, e.g. ``1.10.00``."""
        return await self.request("VERSION")

    def _shutdown(self, reason: str) -> None:
        """Mark the connection closed, close the transport and fail the pending request."""
        if self._closed.is_set():
            return
        _LOG.debug("Closing connection to %s: %s", self._host, reason)
        self._closed.set()
        if self._writer is not None:
            self._writer.close()
        if self._pending is not None and not self._pending.done():
            self._pending.set_exception(RioConnectionError(reason))

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        """Read lines from the controller until the connection closes."""
        reason = "Connection closed by controller"
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                message = parse_line(_decode(raw))
                if message is None:
                    continue
                _LOG.debug("recv: %s", message)
                if message.type == "N":
                    if message.key and self._on_notification:
                        try:
                            self._on_notification(message.key, message.value)
                        except Exception:  # pylint: disable=broad-exception-caught
                            _LOG.exception("Error handling notification %s", message)
                    continue
                pending = self._pending
                if pending is not None and not pending.done():
                    pending.set_result(message)
                else:
                    _LOG.debug("Ignoring unsolicited response: %s", message)
        except (OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError) as err:
            reason = f"Read failed: {err}"
        finally:
            self._shutdown(reason)

    async def _keepalive_loop(self) -> None:
        """Periodically send a cheap request so a dead connection is detected."""
        while self.connected:
            await asyncio.sleep(self._keepalive_interval)
            try:
                await self.version()
            except RioConnectionError as err:
                _LOG.warning("Keep-alive to %s failed: %s", self._host, err)
                return
            except RioCommandError:
                pass
