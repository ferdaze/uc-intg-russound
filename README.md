# Russound RIO integration for Unfolded Circle Remote

Control a Russound MCA-88 (or any other RIO-capable Russound controller) directly
from an Unfolded Circle Remote 2 or Remote 3. Every zone shows up as its own
media player, so you can drop individual rooms into activities, macros and
button mappings.

The driver runs **natively on the Remote**. There is no Docker container, no
Raspberry Pi, and no always-on computer in the middle.

---

## What you get

- **One media player per zone.** Zone names come straight from the controller, so
  "Kitchen" stays "Kitchen".
- **Power, volume, mute, source selection** per zone. Volume is mapped from
  Russound's 0–50 scale onto the Remote's 0–100 scale, one Remote step per
  Russound step.
- **Transport controls** (play/pause, stop, next, previous) for sources that
  support them.
- **Now-playing metadata** — title, artist, album, cover art and track position,
  pulled from whichever source the zone is listening to.
- **Extra zone commands** exposed as buttons: party mode, do not disturb,
  loudness, bass, treble, balance, tuner presets and all-zones-off.
- **Automatic discovery.** Setup scans your local subnet for anything answering
  on the RIO port, so you usually don't need to type an IP address.
- **Survives network blips.** Reconnects on its own and re-establishes RIO
  subscriptions, which are otherwise lost across a TCP reconnect.

## Supported hardware

Anything that speaks the Russound RIO protocol over TCP, including:

| Controller | Zones |
|---|---|
| MCA-88 / MCA-88X | 8 |
| MCA-C5 | 8 |
| MCA-66 / MCA-C3 | 6 |
| SMZ8 | 8 |
| SMZ16 / SMZ16-PRE | 16 |

Daisy-chained RNET controllers behind the primary unit are picked up
automatically — you only configure the first one.

**Connection:** the MCA-88 has an Ethernet port and speaks RIO on TCP **9621**
out of the box. If your controller is serial-only, an RS-232-to-IP bridge works
too; just enter the bridge's address and port during setup.

## Installation

1. Download `uc-intg-russound-<version>-aarch64.tar.gz` from the
   [latest release](https://github.com/ferdaze/uc-intg-russound/releases).
   Do not unpack it.
2. Open the Remote's web configurator in a browser (`http://<remote-ip>`).
3. Go to **Integrations → Add new → Install custom**.
4. Upload the `.tar.gz`, then click the new integration and choose **Start setup**.
5. Let it scan, or enter your controller's IP address manually.
6. Enable the zone entities you actually want on the Remote.

Full walkthrough: **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**

## Building it yourself

Releases are built automatically by GitHub Actions when a `v*` tag is pushed.
To build locally you need Docker and QEMU, because PyInstaller cannot
cross-compile and the Remote needs an aarch64 binary:

```bash
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
docker run --rm --name builder \
  --platform=aarch64 \
  --user=$(id -u):$(id -g) \
  -v "$PWD":/workspace \
  docker.io/unfoldedcircle/r2-pyinstaller:3.11.13-0.7.0 \
  bash -c "cd /workspace && \
    python -m pip install -r requirements.txt && \
    pyinstaller --clean --onedir --name intg-russound \
      --collect-all zeroconf --collect-all ucapi \
      --collect-all ucapi_framework intg-russound/driver.py"

mkdir -p artifacts/bin
mv dist/intg-russound/* artifacts/bin
mv artifacts/bin/intg-russound artifacts/bin/driver
cp driver.json artifacts/
tar czf uc-intg-russound-aarch64.tar.gz -C artifacts .
```

The archive layout the Remote expects is `driver.json` in the root and the
executable at `bin/driver`.

## Running the tests

The test suite runs against a mock RIO server, so no hardware is needed:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r test-requirements.txt
pytest
```

## How it fits together

```
Unfolded Circle Remote 3
  └── intg-russound (this driver, native aarch64 binary)
        │  ucapi + ucapi-framework  → WebSocket integration API
        │  aiorussound              → RIO client
        ▼
      TCP 9621
        ▼
  Russound MCA-88
        ├── Zone 1 … Zone 8   → one media_player entity each
        └── Source 1 … 8      → source list per zone
```

| File | Role |
|---|---|
| `intg-russound/driver.py` | Entry point; wires everything together |
| `intg-russound/device.py` | RIO connection, state cache, zone commands |
| `intg-russound/media_player.py` | Per-zone entity and command routing |
| `intg-russound/setup.py` | Setup flow and connection validation |
| `intg-russound/discover.py` | Subnet scan for controllers on port 9621 |
| `intg-russound/const.py` | Config dataclass, volume scaling, command list |

## Troubleshooting

**Setup can't find the controller.** Confirm the controller answers on 9621 from
a machine on the same network: `nc -zv <controller-ip> 9621`. Also check that
the Remote is on the same subnet — the scan only covers the Remote's own /24.

**Zones appear but commands do nothing.** Some RIO features need a recent
controller firmware. The driver requires RIO API v1.05.00 or newer; the version
is printed in the logs on connect.

**Entities go unavailable after a while.** The driver reconnects automatically
with backoff. If it keeps dropping, another RIO client may be competing for the
connection — the Russound app, a home automation controller, or an old copy of
this integration still installed.

**Reading the logs.** Web configurator → **Settings → Development → Logs**, or
enable the live log viewer:

```bash
curl --request PUT 'http://<remote-ip>/api/system/logs/web' \
  --header 'Content-Type: application/json' \
  --user web-configurator:<pin> \
  --data '{"enabled": true}'
```

Then open `http://<remote-ip>/log/`.

Set `UC_LOG_LEVEL=DEBUG` for verbose output, and `UC_RIO_LOG_LEVEL=DEBUG` to
also see the raw RIO conversation.

## Credits

- Built from [JackJPowell/uc-intg-template](https://github.com/JackJPowell/uc-intg-template)
  and [ucapi-framework](https://github.com/jackjpowell/ucapi-framework).
- RIO protocol handling by [aiorussound](https://github.com/noahhusby/aiorussound).
- Integration API by [Unfolded Circle](https://github.com/unfoldedcircle/integration-python-library).

Not affiliated with or endorsed by Russound or Unfolded Circle.

## License

[Mozilla Public License 2.0](LICENSE)
