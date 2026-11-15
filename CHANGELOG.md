# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/).

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
