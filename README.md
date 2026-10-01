# Russound Integration for Unfolded Circle Remote Two/3

Control a **Russound MCA-88** multi-zone controller from an [Unfolded Circle](https://www.unfoldedcircle.com/) Remote Two or Remote 3.
The integration runs **natively on the Remote**: no Docker, no extra server.

It talks to the controller over Russound's **RIO** protocol (TCP port 9621). Other RIO-capable Russound controllers such as the MCA-88X, MCA-C3, MCA-C5, MCA-66 and daisy-chained RNET controllers use the same protocol and should also work.

Built on [ucapi-framework](https://github.com/jackjpowell/ucapi-framework), starting from [JackJPowell's integration template](https://github.com/JackJPowell/uc-intg-template).

## Features

Each zone you select during setup becomes a **media player** entity:

| Capability | Details |
|---|---|
| Power | On / Off / Toggle |
| Volume | Slider (Russound 0–50, shown as 0–100 in 50 steps), volume up / down |
| Mute | Mute, unmute, mute toggle |
| Source | Select from the controller's source names, e.g. "Sonos" or "Tuner" |
| Now playing | Title / artist / album / cover art when the source reports metadata (for example a Russound media streamer or tuner) |
| Transport | Play/Pause, Stop, Next, Previous, passed through to the source |
| Live state | Changes made at a keypad, in the Russound app or by another system show up on the Remote immediately (RIO push notifications) |

Simple commands, available for button mapping and activities:

`BASS_UP`, `BASS_DOWN`, `TREBLE_UP`, `TREBLE_DOWN`, `BALANCE_LEFT`, `BALANCE_RIGHT`, `TONE_RESET`,
`LOUDNESS_ON`, `LOUDNESS_OFF`, `LOUDNESS_TOGGLE`, `ALL_ZONES_ON`, `ALL_ZONES_OFF`, `SOURCE_1` … `SOURCE_8`

## Requirements

- Russound MCA-88 connected to your network, with a **static or DHCP-reserved IP address**
- RIO enabled on the controller (TCP port 9621; it is on by default on current firmware). Updating the controller to the latest firmware is recommended.
- Unfolded Circle Remote Two or Remote 3 on the same network

## Installation

1. Download the latest `uc-intg-russound-<version>-aarch64.tar.gz` from the
   [Releases](https://github.com/ferdaze/uc-intg-russound/releases) page.
2. Open the Remote's web configurator, then go to **Integrations** → **Add new** → **Install custom** and upload the `.tar.gz` file.
3. Start the setup of the new **Russound** integration:
   1. Enter the IP address of the MCA-88. The port defaults to 9621.
   2. The integration connects and reads the controller's zones and sources.
   3. Select the zones you want on the Remote.
4. Add the zone entities to your activities or pages.

To change the zone selection or IP address later, run the integration setup again and choose **Update information for selected device**.

## Package layout

GitHub Actions builds the package with Unfolded Circle's PyInstaller builder image for the Remote's aarch64 CPU:

```
uc-intg-russound-<version>-aarch64.tar.gz
├── driver.json          # integration metadata
└── bin/
    ├── driver           # the integration (Python 3.11 runtime + code, built by PyInstaller)
    └── _internal/       # bundled Python libraries
```

## Development

### Project structure

```
├── driver.json              # Integration metadata
├── intg-russound/
│   ├── driver.py            # Entry point
│   ├── const.py             # Configuration dataclasses, simple commands
│   ├── rio.py               # Russound RIO protocol client (asyncio, no dependencies)
│   ├── russound.py          # Zone/source state models and system discovery
│   ├── device.py            # Persistent connection, state tracking and zone commands
│   ├── media_player.py      # Zone media player entity
│   └── setup.py             # Setup flow (address entry, zone selection)
├── tests/                   # Unit tests incl. a fake MCA-88 RIO server
└── .github/workflows/       # Lint, test, build & release
```

### Run locally

Requires Python 3.11+.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r test-requirements.txt
python -m pytest
UC_CONFIG_HOME=./config python intg-russound/driver.py
```

The driver listens on port 9090 and announces itself via mDNS. Add it as an external integration in the web configurator to test without installing a package.

| Variable | Description | Default |
|----------|-------------|---------|
| `UC_LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `UC_CONFIG_HOME` | Configuration directory path | Remote: integration data dir |
| `UC_INTEGRATION_INTERFACE` | Network interface to bind | `0.0.0.0` |
| `UC_INTEGRATION_HTTP_PORT` | HTTP port for the integration | `9090` |
| `UC_DISABLE_MDNS_PUBLISH` | Disable mDNS advertisement | `false` |

Set `UC_LOG_LEVEL=DEBUG` to log every RIO command and notification.

### Releasing

1. Update `version` in `driver.json` and `pyproject.toml`, set `release_date`, and add a `## vX.Y.Z` section to `CHANGELOG.md`.
2. Commit, then tag and push:
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```
3. The **Build & Release** workflow lints, tests and builds the aarch64 package, smoke-tests the binary, and publishes a GitHub release with the `.tar.gz` and its SHA-256 hash.

Every push to `main` and every pull request also builds the package. Download it from the workflow run's **Artifacts** to test unreleased changes.

`setup.sh` enables the `git-hooks/pre-push` hook, which checks that the tag matches the versions in `driver.json` and `pyproject.toml`.

## Resources

- [UCAPI Framework](https://github.com/jackjpowell/ucapi-framework)
- [UC Integration Python Library](https://github.com/unfoldedcircle/integration-python-library)
- [Unfolded Circle Core API](https://github.com/unfoldedcircle/core-api)
- [aiorussound](https://github.com/noahhusby/aiorussound): the Home Assistant Russound RIO library, used as a protocol reference

## License

Mozilla Public License Version 2.0. See [LICENSE](LICENSE) for details.
