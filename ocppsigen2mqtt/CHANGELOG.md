# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.2.0] - 2026-05-27

### Added
- **Home Assistant MQTT Discovery:** Bridge automatically publishes discovery payloads
  on startup, making sensors appear in Home Assistant without manual setup. Exposed
  entities: Power (W), Current (A), Voltage (V), Total Energy (Wh), and Availability
  (binary sensor). All sensors grouped under a device with proper device classes and
  units.
- Runtime authorization gate for `Authorize` handling with MQTT toggle command
  `command/toggle_authorize` and state publish on `authorize/state`.
- `set_power_watts` MQTT command to convert requested watts to per-phase current
  using fixed nominal 230V, clamped to 6-16A, and apply through OCPP smart
  charging (`SetChargingProfile`).
- `usable_phases` configuration option (1|2|3, default 2) for future car upgrades,
  wired through add-on options, runtime YAML generation, and bridge config.
- `set_power_watts` support for optional per-command overrides:
  `phases` and charging profile `purpose`.

### Changed
- `set_power_watts` now prefers `TxProfile` while a transaction is active and
  otherwise falls back to `ChargePointMaxProfile`.
- `ChargePointMaxProfile` requests now use connector `0`, and `TxProfile`
  requests include the active `transactionId` when available.
- Active transaction IDs are now recovered from incoming `MeterValues`
  payloads, so Smart Charging requests can keep using `TxProfile` after
  bridge restarts.
- `set_power_watts` timeout errors now include explicit diagnostics and the
  exact attempted OCPP request payload in MQTT command results.
- Documentation updated with WS/WSS connection variants, CPID guidance, and
  smart charging notes from the SIGEN technical PDF.

- `Authorize` response is now configurable at runtime (`Accepted`/`Blocked`) while
  keeping OCPP connection online.
- Bridge command subscriptions include `command/set_power_watts`.

### Tests
- Added coverage for authorization gate enabled/disabled behavior and runtime
  toggling.
- Added coverage for watts-to-current conversion at 230V, clamp boundaries, and
  phase override behavior.

## [0.1.0] - 2025-07-15

### Added
- OCPP 1.6 JSON/WebSocket central system server.
- Charge point connection tracking and per-CP state (active transaction ID).
- Inbound OCPP handlers: `BootNotification`, `Heartbeat`, `Authorize`,
  `StatusNotification`, `StartTransaction`, `StopTransaction`, `MeterValues`,
  `DataTransfer`.
- Meter value publishing for `Power.Active.Import` (→ W), `Current.Import`,
  `Energy.Active.Import.Register` (→ Wh), `Voltage` — unit-aware scaling.
- MQTT `command/start` and `command/stop` topics with CALL/CALL_RESULT
  correlation and result publish-back.
- MQTT `command/reset`, `command/get_config`, `command/set_config` topics.
- Auto-resolve stop `transactionId` from tracked active transaction when not
  provided in the command payload.
- Bridge and per-CP availability topics (`online`/`offline`).
- YAML config loaded via `--config` (HA add-on) or environment variables (dev).
- `run.sh` converts `/data/options.json` to runtime YAML for Home Assistant.
- Docker build using `ghcr.io/home-assistant/base:3.23` (Alpine-based).
