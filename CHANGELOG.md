# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## v0.1.1

Fixes zones staying unavailable after a connection problem.

- After the link to the controller dropped, the socket was re-opened but zone updates were never re-subscribed and the zones were never marked available again. The integration now rebuilds the whole session itself and retries with backoff (1 s up to 30 s) until the controller answers.
- If the controller cannot be reached when the Remote starts or wakes, the integration now keeps retrying in the background instead of giving up.
- Zone entities are registered at startup from the names saved during setup, so they no longer depend on the controller being reachable at that moment.
- A command the controller does not acknowledge within 5 seconds now fails with a timeout and restarts the connection instead of waiting indefinitely.
- The connection to the controller is now closed explicitly on disconnect and before every reconnect.

---

## v0.1.0

First release.

- Native aarch64 integration driver for the Unfolded Circle Remote 2 / 3 — no Docker, no external host required.
- Connects to Russound MCA-88 and other RIO controllers over TCP port 9621.
- Creates one media-player entity per zone, named from the zone names configured on the controller.
- Power, volume, mute, source selection and transport controls per zone.
- Live metadata: title, artist, album, cover art, track position.
- Extra per-zone commands: party mode, do not disturb, loudness, bass, treble, balance, presets and all-zones-off.
- Network scan during setup finds controllers on the local subnet automatically.
- Automatic reconnect with RIO subscription recovery after a network drop.
