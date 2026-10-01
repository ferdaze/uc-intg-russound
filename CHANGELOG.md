# Russound Integration Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

_Changes in the next release_

---

## v0.1.0 - 2026-09-30
### Added
- Initial release for the Russound MCA-88 (RIO protocol, TCP port 9621).
- One media player entity per selected zone: power, volume, mute, source selection,
  now-playing metadata and transport keys.
- Simple commands for bass, treble, balance, loudness, all zones on/off and direct source selection.
- Live state updates via RIO notifications, keep-alive and automatic reconnect.
- Setup flow with controller discovery (zones, sources, daisy-chained controllers) and zone selection.
- GitHub Actions workflow that lints, tests and builds the aarch64 package for the Remote and publishes releases.
