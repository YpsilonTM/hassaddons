# Changelog

All notable changes to this Home Assistant add-on will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- Added `README.md` intro for Home Assistant add-on presentation.
- Added one-click "Add add-on repository" Home Assistant badge to `README.md`.

## [0.2.1] - 2026-05-20
### Fixed
- Removed reference to deleted `profile` field in app.py startup log (fixes startup crash after profile removal).

## [0.2.0] - 2026-05-20
### Added
- Initial CHANGELOG.md for the add-on.

### Changed
- Removed all profile (dev/prod) logic and configuration. Topic selection is now explicit only.
- Generalized all config, code, and docs for device-neutral use.
- Bumped add-on and Python package version to 0.2.0.

## [0.1.0] - 2026-05-19
### Added
- Initial public release: Modbus TCP to MQTT bridge for Home Assistant.
- Supports device-neutral configuration, Modbus polling, MQTT publishing, and Home Assistant discovery (optional).
