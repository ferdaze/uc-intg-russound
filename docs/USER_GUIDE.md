# User guide

How to install and use the Russound integration on your Unfolded Circle Remote.

---

## Before you start

You need:

- A Russound RIO controller (MCA-88, MCA-88X, MCA-C5, MCA-66, MCA-C3, SMZ8, SMZ16)
  connected to your network by Ethernet, powered on.
- An Unfolded Circle Remote 2 or 3 on the **same subnet** as the controller.
- The Remote's web configurator PIN. It's on the Remote under
  **Settings → General → About**, or you set it during first-time setup.

Two things worth checking first:

- **Zone names.** The integration names each entity after the zone name stored on
  the controller. Set those up in the Russound app first and you'll save yourself
  renaming eight entities later.
- **RIO port reachable.** From a computer on the same network:
  ```bash
  nc -zv <controller-ip> 9621
  ```
  A "succeeded" or "open" response means you're good.

---

## Step 1 — Download the integration

Go to the [releases page](https://github.com/ferdaze/uc-intg-russound/releases)
and download the file named:

```
uc-intg-russound-<version>-aarch64.tar.gz
```

**Do not unpack it.** The Remote wants the archive as-is.

---

## Step 2 — Install it on the Remote

1. Open `http://<remote-ip>` in a browser and log in with your PIN.
2. Go to the **Integrations** tab.
3. Click **Add new**, then **Install custom**.
4. Select the `.tar.gz` file and upload.

If you're replacing an earlier version and your Remote runs firmware 2.9.3 or
newer, tick **Update existing driver** during upload. On older firmware you must
delete the old integration instance first, then the driver, then install fresh.

Command-line alternative:

```bash
curl --location 'http://<remote-ip>/api/intg/install' \
  --user 'web-configurator:<pin>' \
  --form 'file=@"uc-intg-russound-0.1.0-aarch64.tar.gz"'
```

---

## Step 3 — Run setup

1. In the Integrations list, click **Russound RIO**.
2. Click **Start setup**.
3. Read the intro screen and continue.
4. The integration scans your subnet for controllers on port 9621. This takes
   up to 30 seconds.
   - **Found it?** Pick your controller from the list.
   - **Nothing found?** Choose manual entry and type the controller's IP address.
     Leave the port at 9621 unless you're going through an RS-232-to-IP bridge.
5. The integration connects, reads your zone and source names, and finishes.

If setup fails, the error tells you which stage broke:

| Message | What it usually means |
|---|---|
| Connection refused | Wrong IP, or RIO isn't enabled on the controller |
| Timeout | Controller unreachable — check the subnet and any VLAN separation |
| Not found | Connected, but the device didn't identify as a RIO controller |

---

## Step 4 — Enable the zones you want

After setup, the Remote shows one **media player entity per zone**. You probably
don't want all eight cluttering your interface.

1. Go to **Entities** in the web configurator.
2. Find the entities named after your zones.
3. Enable the ones you'll actually use.

Entity IDs look like `media_player.<controller>.c1z3` — `c1` is controller 1,
`z3` is zone 3.

---

## Using it

### Standard controls

Each zone entity gives you:

| Control | Behaviour |
|---|---|
| Power on/off | Turns that zone on or off |
| Volume slider | 0–100, mapped onto Russound's 0–50 internally |
| Volume up/down | One Russound step per press |
| Mute / unmute | Per zone |
| Source | Dropdown of the sources available to that zone |
| Play / pause / next / previous | Passed through to the active source |

Now-playing info (title, artist, album, cover art) appears for sources that
report it — streaming sources generally do, a turntable on a line input won't.

### Extra commands

These show up as buttons and can be used in macros and activities:

| Command | What it does |
|---|---|
| `PARTY_MODE_ON` / `PARTY_MODE_MASTER` / `PARTY_MODE_OFF` | Join, lead, or leave party mode |
| `DO_NOT_DISTURB_ON` / `_OFF` | Blocks paging into the zone |
| `LOUDNESS_ON` / `_OFF` | Loudness compensation |
| `BASS_UP` / `BASS_DOWN` / `BASS_FLAT` | Bass in steps of 2, range −10 to +10 |
| `TREBLE_UP` / `TREBLE_DOWN` / `TREBLE_FLAT` | Treble, same range |
| `BALANCE_LEFT` / `BALANCE_RIGHT` / `BALANCE_CENTER` | Left–right balance |
| `PRESET_1` … `PRESET_6` | Recall a tuner preset (tuner sources only) |
| `ALL_ZONES_OFF` | Shuts down every zone on the controller |

### Activity ideas

**Whole-house music**

```
Zone 1 (Living Room) → On
Zone 2 (Kitchen)     → On
Zone 4 (Patio)       → On
All three            → Select source "Sonos"
All three            → Volume 60
```

**Bedtime**

```
Zone 3 (Bedroom) → On
Zone 3           → Select source "Streaming"
Zone 3           → Volume 20
ALL other zones  → Off
```

**Movie night** — put `ALL_ZONES_OFF` at the start of your home-theatre
activity so the distributed audio doesn't compete with the AV receiver.

---

## Troubleshooting

**Entities show as unavailable.** The driver lost the RIO connection. It retries
automatically with increasing backoff. Check the controller is powered on and
reachable. If it recovers and then drops again repeatedly, something else is
probably holding the RIO connection — the Russound app, a home automation hub,
or an older copy of this integration that's still installed.

**Volume jumps in odd increments.** Russound has 51 volume levels (0–50) and the
Remote shows 0–100, so each Remote step is worth two on the slider. This is
expected.

**Source list is missing sources.** RIO lets you exclude sources per zone. The
integration honours that, so if a source is hidden for a zone on the controller,
it won't appear here either. Change it in the Russound app.

**No metadata for a source.** Line-level inputs (turntable, TV audio) have no
metadata to report. Only smart sources send title and artist.

**A zone is missing entirely.** The integration only creates entities for zones
the controller actually reports. Check the zone is enabled in your Russound
configuration, then re-run setup.

**Getting logs.** Web configurator → **Settings → Development → Logs**, and
download the log for the `russound` service. For live tailing:

```bash
curl --request PUT 'http://<remote-ip>/api/system/logs/web' \
  --header 'Content-Type: application/json' \
  --user web-configurator:<pin> \
  --data '{"enabled": true}'
```

Open `http://<remote-ip>/log/`. Note the log viewer itself uses a chunk of the
integration memory pool, so turn it off when you're done.

---

## Uninstalling

1. Web configurator → **Integrations**.
2. Delete the integration **instance** first.
3. Then delete the **driver**.

Both steps are needed; the driver can't be removed while an instance exists.

---

## Getting help

Open an issue at
[github.com/ferdaze/uc-intg-russound/issues](https://github.com/ferdaze/uc-intg-russound/issues)
and include:

- Controller model and firmware version
- Remote model and firmware version
- Integration version
- The relevant log section with `UC_LOG_LEVEL=DEBUG`
