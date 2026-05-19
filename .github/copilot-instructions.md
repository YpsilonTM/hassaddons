# Copilot Instructions: Modbus TCP -> MQTT Bridge (Python-First)

## Project Goal
Build a lightweight, headless, Python-first bridge that:
- Reads Modbus TCP registers from any Modbus TCP device (inverter, meter, sensor, etc).
- Decodes values correctly (including 32-bit and signed values).
- Publishes normalized state to MQTT topics for Home Assistant.
- Stays safe for live-home use during development.

## Scope
In scope:
- Python bridge service.
- YAML config for registers and decoding.
- MQTT publishing and optional Home Assistant discovery payloads.
- Docker packaging for Home Assistant add-on deployment.

Out of scope (for first milestone):
- Web GUI.
- Full Home Assistant custom integration.
- Advanced write/RPC support.

## Tech Preferences
- Language: Python 3.12+
- Modbus library: pymodbus
- MQTT library: paho-mqtt
- Config parser: pydantic + YAML (or strict dataclasses)
- Packaging: Docker
- Lint/format: ruff + black
- Testing: pytest

## Current Repository State
- The repository is implementation-first and actively used with real hardware.
- The Home Assistant add-on lives in `modqtt/`.
- The Python service code lives under `modqtt/src/` with tests in `modqtt/tests/`.
- Local runtime config is `modqtt/modqtt.yaml`.
- Add-on metadata file is `modqtt/config.yaml` (do not use this filename for bridge runtime config).
- A GitHub Actions workflow exists at `.github/workflows/build-and-push-addon.yml` for build and GHCR push.

## Architecture Requirements
Use this structure:
- modqtt/src/
  - app.py (entrypoint)
  - config.py (schema validation)
  - modbus_client.py (polling and read batching)
  - decoder.py (all decode logic only)
  - mqtt_client.py (publish and availability)
  - publisher.py (topic mapping and payload shaping)
  - models.py (typed config and reading models)
- modqtt/tests/
  - test_decoder.py
  - test_config_validation.py
  - fixtures/

Keep decode logic isolated in decoder.py and fully unit tested.

## Data Model Rules
Each reading definition should support at least:
- name
- topic_suffix
- register_type: input | holding
- address
- length_words
- data_type: u16 | s16 | u32 | s32 | f32
- scale
- offset
- decimals
- byte_order: big | little
- word_order: big | little
- unit
- device_class
- state_class
- writable (default false)

Do not hardcode register maps in Python. Use config.

## Decode Correctness Rules (Critical)
- Always decode from raw words with explicit word_order and byte_order.
- Never assume default endianness.
- Support both signed and unsigned 16/32-bit.
- Apply transform order exactly:
  1. raw decode
  2. scale and offset
  3. round to decimals
- For signed 32-bit, use proper two's-complement conversion.
- Add unit tests for every data_type and each byte/word order combination used by supported devices.

## MQTT Rules
- Publish to state topics under a configurable prefix.
- Use retained messages for state.
- Publish bridge availability topic: online/offline.
- Use JSON payload option for grouped topics, but default to one topic per sensor for clarity.

Topic style:
- dev/device/<sensor_name>/state during development
- prod/device/<sensor_name>/state in production

## Home Assistant Safety Rules
Default behavior must be safe for live HA:
- Read-only mode on by default.
- Writes disabled unless explicitly enabled in config.
- Development prefix must be different from production prefix.
- Home Assistant discovery disabled by default in dev profile.

## Local Development and Live HA Testing Workflow
Use this workflow unless user asks otherwise:
1. Run bridge locally on dev machine.
2. Connect to real inverter Modbus TCP in read-only mode.
3. Publish to dev MQTT topic prefix only.
4. Validate values in MQTT Explorer and HA Developer Tools.
5. Compare critical points to known-good raw registers.
6. Switch to prod prefix only after validation checklist passes.

## Validation Gates Before Cutover
Require all checks to pass:
- No absurd outlier values for power/energy.
- Signed values behave correctly around zero.
- 32-bit values match manual recomposition from raw words.
- Poll cycle stable for at least 30 minutes.
- No unexpected writes attempted.

## Performance and Reliability
- Poll interval configurable per source.
- Batch contiguous register reads where possible.
- Handle reconnect with exponential backoff for Modbus and MQTT.
- Avoid crashing on single-sensor decode failure; log and continue.

## Logging Rules
- Structured logs with level, source, address, sensor name.
- Include raw words for debug mode only.
- Never log secrets.

## Secrets Handling
- Do not hardcode credentials.
- For Home Assistant add-on usage, read credentials from add-on options (`/data/options.json`) via `run.sh` generated runtime YAML.
- Keep example config scrubbed.

If environment variables are used for non-add-on local development, keep names under the `MODQTT_` prefix.

## Copilot Behavior for This Project
When generating code for this repository:
- Prioritize correctness of decoding over adding features.
- Add tests with every decoding change.
- Keep functions small and typed.
- Prefer explicit code over clever shortcuts.
- Do not introduce a GUI.
- Do not enable writes by default.
- If uncertain about endianness, add config options and test both paths.

Default implementation order (unless user requests otherwise):
1. models.py + config.py
2. decoder.py + tests/test_decoder.py
3. modbus_client.py
4. mqtt_client.py + publisher.py
5. app.py wiring and graceful shutdown
6. Dockerfile and compose example

Command behavior for agents:
- If pyproject.toml exists, use it as the source of truth for tooling commands.
- Run project commands from `modqtt/`.
- Prefer these commands:
  - python -m pytest
  - python -m ruff check .
  - python -m black --check .
- Run tests after decode or config changes before concluding work.

## Home Assistant Add-on Workflow
- Keep add-on packaging files in `modqtt/` (`config.yaml`, `Dockerfile`, `run.sh`, `DOCS.md`).
- Keep local app testing support in `.devcontainer/devcontainer.json` and `.vscode/tasks.json`.
- Use `Start Home Assistant` task inside devcontainer for local Supervisor testing.
- For remote hardware testing, use a separate development topic prefix before production cutover.

## Suggested Milestones
Milestone 1:
- Read Modbus input and holding registers.
- Decode u16/s16/u32/s32.
- Publish MQTT state topics.
- Unit tests for decoder.

Milestone 2:
- HA discovery payload generation.
- Better batching and retry logic.
- Docker image and compose example.

Milestone 3:
- Optional write/RPC path with explicit allowlist and safety guardrails.

## Definition of Done (MVP)
MVP is done when:
- Bridge runs locally and publishes stable values for key device sensors.
- All decoder tests pass.
- No production topic collisions during development.
- Cutover to production topic prefix requires one config change only.
