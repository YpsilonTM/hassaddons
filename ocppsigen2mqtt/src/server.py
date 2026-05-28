from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt
try:
    from websockets.asyncio.server import serve as ws_serve
    _WEBSOCKETS_NEW_API = True
except ImportError:
    from websockets.legacy.server import serve as ws_serve  # type: ignore[no-redef]
    _WEBSOCKETS_NEW_API = False

from config import Config

CALL = 2
CALL_RESULT = 3
CALL_ERROR = 4

log = logging.getLogger("ocppsigen2mqtt")

ACTIVE_CHARGING_STATUSES = {"Charging"}
MIN_VALID_PHASE_VOLTAGE_V = 120.0
MAX_VALID_PHASE_VOLTAGE_V = 300.0
NON_CHARGING_CURRENT_CLAMP_MAX_POWER_W = 250.0


class ChargePoint:
    """Tracks per-charge-point state and active transaction."""

    def __init__(self, cp_id: str) -> None:
        self.cp_id = cp_id
        self.websocket: Any = None
        self.transaction_id: int | None = None
        self.connector_status: dict[int, str] = {}
        self.connected_at = datetime.now(timezone.utc).isoformat()


class OcppBridge:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.loop: asyncio.AbstractEventLoop | None = None
        self.charge_points: dict[str, ChargePoint] = {}
        self.pending: dict[str, asyncio.Future[Any]] = {}
        self.authorize_enabled = config.authorize_enabled
        self.last_active_phases: int | None = None
        self.usable_phases = max(1, min(3, int(config.usable_phases)))
        self.nominal_voltage_v = 230.0
        self._derived_energy_wh = 0.0
        self._last_meter_timestamp: datetime | None = None

        try:
            self.mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=config.mqtt.client_id)  # paho-mqtt >= 2.0
        except AttributeError:
            self.mq = mqtt.Client(client_id=config.mqtt.client_id)  # paho-mqtt < 2.0
        if config.mqtt.username:
            self.mq.username_pw_set(config.mqtt.username, config.mqtt.password)
        self.mq.on_connect = self._on_mqtt_connect
        self.mq.on_message = self._on_mqtt_message

    # ------------------------------------------------------------------ MQTT

    def _prefix(self, *parts: str) -> str:
        return "/".join([self.config.mqtt.topic_prefix, *parts])

    def _parse_ocpp_timestamp(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None

    def _on_mqtt_connect(self, client: mqtt.Client, _ud: Any, _flags: Any, rc: Any, *_args: Any) -> None:
        # rc is int (v1 API) or ReasonCode (v2 API); treat non-zero / non-Success as failure
        success = (rc == 0) if isinstance(rc, int) else rc.is_failure is False
        if not success:
            log.error("MQTT connect failed, rc=%s", rc)
            return
        log.info("MQTT connected to %s:%s", self.config.mqtt.host, self.config.mqtt.port)
        prefix = self.config.mqtt.topic_prefix
        client.subscribe(f"{prefix}/command/start")
        client.subscribe(f"{prefix}/command/stop")
        client.subscribe(f"{prefix}/command/reset")
        client.subscribe(f"{prefix}/command/get_config")
        client.subscribe(f"{prefix}/command/set_config")
        client.subscribe(f"{prefix}/command/set_power_watts")
        client.subscribe(f"{prefix}/command/toggle_authorize")
        # Backwards compatible path-based command topics.
        client.subscribe(f"{prefix}/+/command/start")
        client.subscribe(f"{prefix}/+/command/stop")
        client.subscribe(f"{prefix}/+/command/reset")
        client.subscribe(f"{prefix}/+/command/get_config")
        client.subscribe(f"{prefix}/+/command/set_config")
        log.info("Subscribed to command topics under %s/command/", prefix)
        # Publish Home Assistant MQTT discovery payloads
        self._publish_ha_discovery()

    def _on_mqtt_message(self, _client: mqtt.Client, _ud: Any, msg: mqtt.MQTTMessage) -> None:
        if not self.loop:
            return
        topic = msg.topic
        raw = msg.payload.decode("utf-8") if msg.payload else "{}"
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            log.error("Bad JSON on %s: %s", topic, raw)
            return

        prefix = self.config.mqtt.topic_prefix
        if not topic.startswith(f"{prefix}/"):
            return
        suffix = topic[len(prefix) + 1 :]
        parts = suffix.split("/")
        if len(parts) < 2:
            return

        cp_id = self.config.charger_id
        command = parts[-1]
        # Support both:
        # - {prefix}/command/start
        # - {prefix}/{cp_id}/command/start
        if parts[0] != "command" and len(parts) >= 3 and parts[1] == "command":
            cp_id = parts[0]

        dispatch = {
            "start": self._cmd_start,
            "stop": self._cmd_stop,
            "reset": self._cmd_reset,
            "get_config": self._cmd_get_config,
            "set_config": self._cmd_set_config,
            "set_power_watts": self._cmd_set_power_watts,
            "toggle_authorize": self._cmd_toggle_authorize,
        }
        handler = dispatch.get(command)
        if handler:
            asyncio.run_coroutine_threadsafe(handler(cp_id, payload), self.loop)

    def publish(self, topic: str, payload: Any, retain: bool = True) -> None:
        body = json.dumps(payload) if not isinstance(payload, str) else payload
        self.mq.publish(topic, body, retain=retain)

    def publish_event(self, topic_suffix: str, payload: Any, retain: bool = True) -> None:
        topic = self._prefix(topic_suffix)
        if isinstance(payload, dict):
            enriched = {"charger_id": self.config.charger_id, **payload}
            self.publish(topic, enriched, retain=retain)
            return
        self.publish(topic, {"charger_id": self.config.charger_id, "value": payload}, retain=retain)

    def _publish_ha_discovery(self) -> None:
        """Publish Home Assistant MQTT discovery payloads."""
        prefix = self.config.mqtt.topic_prefix
        device = {
            "identifiers": [f"ocpp_{self.config.charger_id}"],
            "name": f"EV Charger {self.config.charger_id}",
            "manufacturer": "OCPP Bridge",
            "model": "SIGEN EVAC 11",
        }

        # Numeric sensors with simple state topics
        sensors = [
            {
                "suffix": "charger_status",
                "name": "Status",
                "device_class": None,
                "unit": None,
                "icon": "mdi:ev-station",
                "value_template": "{{ value_json.value }}",
            },
            {
                "suffix": "power_w",
                "name": "Power",
                "device_class": "power",
                "unit": "W",
                "icon": "mdi:flash",
                "value_template": "{{ value_json.value }}",
            },
            {
                "suffix": "current_a",
                "name": "Current",
                "device_class": "current",
                "unit": "A",
                "icon": "mdi:current-ac",
                "value_template": "{{ value_json.value }}",
            },
            {
                "suffix": "voltage_v",
                "name": "Voltage",
                "device_class": "voltage",
                "unit": "V",
                "icon": "mdi:sine-wave",
                "value_template": "{{ value_json.value }}",
            },
            {
                "suffix": "total_energy_wh",
                "name": "Total Energy",
                "device_class": "energy",
                "unit": "Wh",
                "icon": "mdi:lightning-bolt",
                "state_class": "total_increasing",
                "value_template": "{{ value_json.value }}",
            },
            {
                "suffix": "lifetime_energy_kwh",
                "name": "Lifetime Energy",
                "device_class": "energy",
                "unit": "kWh",
                "icon": "mdi:counter",
                "state_class": "total_increasing",
                "value_template": "{{ value_json.value }}",
            },
        ]

        for sensor in sensors:
            object_id = f"{self.config.charger_id}_{sensor['suffix']}".lower()
            state_topic = self._prefix(sensor["suffix"])
            
            discovery_payload: dict[str, Any] = {
                "name": f"{device['name']} {sensor['name']}",
                "state_topic": state_topic,
                "unique_id": f"ocpp_{object_id}",
                "device": device,
                "availability_topic": self._prefix("availability"),
                "value_template": sensor["value_template"],
            }

            if sensor["device_class"]:
                discovery_payload["device_class"] = sensor["device_class"]
            if sensor["unit"]:
                discovery_payload["unit_of_measurement"] = sensor["unit"]
            if sensor.get("icon"):
                discovery_payload["icon"] = sensor["icon"]
            if sensor.get("state_class"):
                discovery_payload["state_class"] = sensor["state_class"]

            discovery_topic = f"homeassistant/sensor/{object_id}/config"
            self.publish(discovery_topic, discovery_payload, retain=True)
            log.debug("Published Home Assistant discovery for %s", object_id)

        # Command buttons
        buttons = [
            {
                "suffix": "start",
                "name": "Start Charging",
                "icon": "mdi:play-circle",
                "payload_press": json.dumps({"connector_id": 1, "id_tag": "REMOTE"}),
            },
            {
                "suffix": "stop",
                "name": "Stop Charging",
                "icon": "mdi:stop-circle",
                "payload_press": "{}",
            },
            {
                "suffix": "reset",
                "name": "Reset Charger",
                "icon": "mdi:restart",
                "payload_press": json.dumps({"type": "Soft"}),
            },
        ]

        for button in buttons:
            object_id = f"{self.config.charger_id}_{button['suffix']}_button".lower()
            button_payload = {
                "name": f"{device['name']} {button['name']}",
                "unique_id": f"ocpp_{object_id}",
                "device": device,
                "availability_topic": self._prefix("availability"),
                "command_topic": self._prefix(f"command/{button['suffix']}"),
                "payload_press": button["payload_press"],
                "icon": button["icon"],
            }
            self.publish(f"homeassistant/button/{object_id}/config", button_payload, retain=True)
            log.debug("Published Home Assistant discovery for %s", object_id)

        authorize_switch_payload = {
            "name": f"{device['name']} App Access",
            "state_topic": self._prefix("authorize/state"),
            "unique_id": f"ocpp_{self.config.charger_id}_authorize_switch".lower(),
            "device": device,
            "command_topic": self._prefix("command/toggle_authorize"),
            "payload_on": json.dumps({"enabled": True}),
            "payload_off": json.dumps({"enabled": False}),
            "state_on": "true",
            "state_off": "false",
            "value_template": "{{ value_json.enabled | lower }}",
            "icon": "mdi:phone",
        }
        object_id = f"ocpp_{self.config.charger_id}_authorize_switch".lower()
        self.publish(
            f"homeassistant/switch/{object_id}/config",
            authorize_switch_payload,
            retain=True,
        )
        log.debug("Published Home Assistant discovery for authorize switch")

        # Binary sensor for availability
        availability_payload = {
            "name": f"{device['name']} Available",
            "state_topic": self._prefix("availability"),
            "unique_id": f"ocpp_{self.config.charger_id}_availability",
            "device": device,
            "device_class": "connectivity",
            "payload_on": "online",
            "payload_off": "offline",
        }
        self.publish(f"homeassistant/binary_sensor/ocpp_{self.config.charger_id}_availability/config", availability_payload, retain=True)
        log.debug("Published Home Assistant discovery for availability")

        # Binary sensor for bridge availability
        bridge_availability_payload = {
            "name": "OCPP Bridge Available",
            "state_topic": self._prefix("bridge/availability"),
            "unique_id": "ocpp_bridge_availability",
            "device": {
                "identifiers": ["ocpp_bridge"],
                "name": "OCPP Bridge",
                "manufacturer": "OCPP Bridge",
            },
            "device_class": "connectivity",
            "payload_on": "online",
            "payload_off": "offline",
        }
        self.publish("homeassistant/binary_sensor/ocpp_bridge_availability/config", bridge_availability_payload, retain=True)
        log.debug("Published Home Assistant discovery for bridge availability")

    # ---------------------------------------------------------- MQTT commands

    async def _cmd_start(self, cp_id: str, data: dict) -> None:
        request = {
            "connectorId": int(data.get("connector_id", 1)),
            "idTag": data.get("id_tag", "REMOTE"),
        }
        await self._call_and_publish(cp_id, "RemoteStartTransaction", request, "command_result/start")

    async def _cmd_stop(self, cp_id: str, data: dict) -> None:
        cp = self.charge_points.get(cp_id)
        txn_id = data.get("transaction_id") or (cp.transaction_id if cp else None)
        if txn_id is None:
            log.error("Stop command for %s missing transaction_id and no active transaction known", cp_id)
            self.publish_event("command_result/stop", {"status": "error", "message": "no transaction_id"}, retain=False)
            return
        await self._call_and_publish(cp_id, "RemoteStopTransaction", {"transactionId": int(txn_id)}, "command_result/stop")

    async def _cmd_reset(self, cp_id: str, data: dict) -> None:
        reset_type = data.get("type", "Soft")
        await self._call_and_publish(cp_id, "Reset", {"type": reset_type}, "command_result/reset")

    async def _cmd_get_config(self, cp_id: str, data: dict) -> None:
        keys = data.get("keys", [])
        payload: dict[str, Any] = {"key": keys} if keys else {}
        await self._call_and_publish(cp_id, "GetConfiguration", payload, "command_result/get_config")

    async def _cmd_set_config(self, cp_id: str, data: dict) -> None:
        key = data.get("key")
        value = data.get("value")
        if not key or value is None:
            self.publish_event("command_result/set_config", {"status": "error", "message": "key and value required"}, retain=False)
            return
        await self._call_and_publish(cp_id, "ChangeConfiguration", {"key": key, "value": str(value)}, "command_result/set_config")

    async def _cmd_set_power_watts(self, cp_id: str, data: dict) -> None:
        watts_raw = data.get("watts")
        if watts_raw is None:
            self.publish_event(
                "command_result/set_power_watts",
                {"status": "error", "message": "watts required"},
                retain=False,
            )
            return

        try:
            watts = float(watts_raw)
        except (TypeError, ValueError):
            self.publish_event(
                "command_result/set_power_watts",
                {"status": "error", "message": "watts must be numeric"},
                retain=False,
            )
            return

        if watts <= 0:
            self.publish_event(
                "command_result/set_power_watts",
                {"status": "error", "message": "watts must be > 0"},
                retain=False,
            )
            return

        phases = int(data.get("phases") or self.usable_phases)
        phases = max(1, min(3, phases))
        current_per_phase = math.floor(watts / (self.nominal_voltage_v * phases))
        clamped_current = max(6, min(16, current_per_phase))

        cp = self.charge_points.get(cp_id)
        purpose = data.get("purpose")
        if not purpose:
            purpose = "TxProfile" if cp and cp.transaction_id is not None else "ChargePointMaxProfile"
        if purpose == "ChargePointMaxProfile":
            connector_id = int(data.get("connector_id", 0))
        else:
            connector_id = int(data.get("connector_id", 1))

        charging_profile: dict[str, Any] = {
            "chargingProfileId": int(time.time()),
            "stackLevel": 1,
            "chargingProfilePurpose": purpose,
            "chargingProfileKind": "Absolute",
            "chargingSchedule": {
                "chargingRateUnit": "A",
                "startSchedule": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "chargingSchedulePeriod": [
                    {"startPeriod": 0, "limit": clamped_current},
                ],
            },
        }
        if purpose == "TxProfile":
            if cp and cp.transaction_id is not None:
                charging_profile["transactionId"] = cp.transaction_id
            elif data.get("transaction_id") is not None:
                charging_profile["transactionId"] = int(data["transaction_id"])

        request = {
            "connectorId": connector_id,
            "csChargingProfiles": charging_profile,
        }
        try:
            result = await self._send_call(cp_id, "SetChargingProfile", request)
            self.publish_event(
                "command_result/set_power_watts",
                {
                    "status": "ok",
                    "result": result,
                    "requested_watts": watts,
                    "configured_current_a": clamped_current,
                    "assumed_voltage_v": self.nominal_voltage_v,
                    "assumed_phases": phases,
                    "estimated_watts": clamped_current * self.nominal_voltage_v * phases,
                    "connector_id": connector_id,
                    "purpose": request["csChargingProfiles"]["chargingProfilePurpose"],
                },
                retain=False,
            )
        except TimeoutError:
            message = (
                "No CALL_RESULT for SetChargingProfile within timeout; "
                "charger likely ignores this action on current firmware"
            )
            log.error("set_power_watts timeout for %s: %s", cp_id, message)
            self.publish_event(
                "command_result/set_power_watts",
                {
                    "status": "error",
                    "message": message,
                    "request": request,
                },
                retain=False,
            )
        except Exception as exc:
            log.exception("set_power_watts failed for %s: %s", cp_id, exc)
            self.publish_event(
                "command_result/set_power_watts",
                {"status": "error", "message": str(exc), "request": request},
                retain=False,
            )

    async def _cmd_toggle_authorize(self, _cp_id: str, data: dict) -> None:
        """Toggle authorization gate. Does not require charger connection."""
        enabled = data.get("enabled")
        if enabled is None:
            # Toggle behavior
            self.authorize_enabled = not self.authorize_enabled
        else:
            # Set to explicit value
            self.authorize_enabled = bool(enabled)
        log.info("Authorization gate is now %s", "enabled" if self.authorize_enabled else "disabled")
        self.publish_event("authorize/state", {"enabled": self.authorize_enabled}, retain=True)

    async def _call_and_publish(self, cp_id: str, action: str, payload: dict, result_topic: str) -> None:
        try:
            result = await self._send_call(cp_id, action, payload)
            self.publish_event(result_topic, {"status": "ok", "result": result}, retain=False)
        except Exception as exc:
            log.exception("%s failed for %s: %s", action, cp_id, exc)
            self.publish_event(result_topic, {"status": "error", "message": str(exc)}, retain=False)

    # --------------------------------------------------------- OCPP outbound

    async def _send_call(self, cp_id: str, action: str, payload: dict, timeout: int = 20) -> Any:
        cp = self.charge_points.get(cp_id)
        if not cp or not cp.websocket:
            raise RuntimeError(f"Charge point {cp_id!r} is not connected")
        msg_id = uuid.uuid4().hex[:12]
        future: asyncio.Future[Any] = self.loop.create_future()  # type: ignore[union-attr]
        self.pending[msg_id] = future
        frame = json.dumps([CALL, msg_id, action, payload])
        log.info("-> %s %s %s", cp_id, action, payload)
        await cp.websocket.send(frame)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self.pending.pop(msg_id, None)

    # --------------------------------------------------------- OCPP inbound

    async def handle_connection(self, websocket: Any, path: str = "") -> None:
        if not path:
            # websockets >= 14 asyncio API: path is on the request object
            path = getattr(getattr(websocket, "request", None), "path", "") or ""
        requested_cp_id = path.strip("/").split("/")[-1] if path.strip("/") else ""
        cp_id = self.config.charger_id or requested_cp_id or "unknown"
        if requested_cp_id and cp_id != requested_cp_id:
            log.warning(
                "Connection cp_id '%s' overridden by configured charger_id '%s'",
                requested_cp_id,
                cp_id,
            )
        cp = ChargePoint(cp_id)
        cp.websocket = websocket
        self.charge_points[cp_id] = cp
        log.info("Charge point connected: %s", cp_id)
        self.publish(self._prefix("availability"), "online", retain=True)
        self.publish_event("bridge/availability", "online")

        try:
            async for raw in websocket:
                log.debug("<- %s %s", cp_id, raw)
                await self._handle_frame(cp, raw)
        except Exception as exc:
            log.info("Connection closed for %s: %s", cp_id, exc)
        finally:
            self.charge_points.pop(cp_id, None)
            self.publish(self._prefix("availability"), "offline", retain=True)
            log.info("Charge point disconnected: %s", cp_id)

    async def _handle_frame(self, cp: ChargePoint, raw: str) -> None:
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            log.error("Invalid JSON from %s", cp.cp_id)
            return

        if not isinstance(frame, list) or len(frame) < 3:
            log.error("Malformed OCPP frame from %s: %s", cp.cp_id, frame)
            return

        msg_type = frame[0]
        msg_id = frame[1]

        if msg_type == CALL:
            action = frame[2]
            payload = frame[3] if len(frame) > 3 else {}
            await self._handle_call(cp, msg_id, action, payload)

        elif msg_type == CALL_RESULT:
            result = frame[2] if len(frame) > 2 else {}
            future = self.pending.get(msg_id)
            if future and not future.done():
                future.set_result(result)

        elif msg_type == CALL_ERROR:
            error_code = frame[2] if len(frame) > 2 else "UnknownError"
            error_msg = frame[3] if len(frame) > 3 else ""
            future = self.pending.get(msg_id)
            if future and not future.done():
                future.set_exception(RuntimeError(f"{error_code}: {error_msg}"))

    async def _handle_call(self, cp: ChargePoint, msg_id: str, action: str, payload: dict) -> None:
        log.info("<- %s %s %s", cp.cp_id, action, payload)
        response: dict[str, Any] = {}

        if action == "BootNotification":
            response = {
                "status": "Accepted",
                "currentTime": datetime.now(timezone.utc).isoformat(),
                "interval": 30,
            }
            self.publish_event("boot", payload)

        elif action == "Heartbeat":
            response = {"currentTime": datetime.now(timezone.utc).isoformat()}

        elif action == "Authorize":
            if self.authorize_enabled:
                response = {"idTagInfo": {"status": "Accepted"}}
            else:
                log.info("Authorization blocked for %s (authorize_enabled=false)", cp.cp_id)
                response = {"idTagInfo": {"status": "Blocked"}}

        elif action == "StatusNotification":
            status = payload.get("status", "Unknown")
            connector = payload.get("connectorId", 0)
            try:
                connector_id = int(connector)
            except (TypeError, ValueError):
                connector_id = 0
            cp.connector_status[connector_id] = status
            self.publish_event(f"connector/{connector}/status", status)
            self.publish_event("charger_status", {"value": status, "connector_id": connector_id})
            self.publish_event("status", payload)

        elif action == "StartTransaction":
            cp.transaction_id = int(datetime.now(timezone.utc).timestamp())
            response = {
                "transactionId": cp.transaction_id,
                "idTagInfo": {"status": "Accepted"},
            }
            self.publish_event("transaction/active", {
                "transaction_id": cp.transaction_id,
                "id_tag": payload.get("idTag"),
                "connector_id": payload.get("connectorId"),
                "meter_start": payload.get("meterStart"),
                "timestamp": payload.get("timestamp"),
            })

        elif action == "StopTransaction":
            self.publish_event("transaction/last", {
                "transaction_id": payload.get("transactionId"),
                "meter_stop": payload.get("meterStop"),
                "timestamp": payload.get("timestamp"),
                "reason": payload.get("reason"),
            })
            meter_stop = payload.get("meterStop")
            try:
                meter_stop_wh = float(meter_stop)
                self.publish_event("total_energy_wh", {"value": meter_stop_wh})
                self.publish_event("lifetime_energy_kwh", {"value": meter_stop_wh / 1000.0})
            except (TypeError, ValueError):
                pass
            cp.transaction_id = None
            response = {"idTagInfo": {"status": "Accepted"}}

        elif action == "MeterValues":
            self._publish_meter_values(cp, payload)

        elif action == "DataTransfer":
            response = {"status": "Accepted"}

        await cp.websocket.send(json.dumps([CALL_RESULT, msg_id, response]))

    def _publish_meter_values(self, cp: ChargePoint, payload: dict) -> None:
        txn_id = payload.get("transactionId")
        if txn_id is not None:
            try:
                cp.transaction_id = int(txn_id)
            except (TypeError, ValueError):
                pass

        connector_raw = payload.get("connectorId", 0)
        try:
            connector_id = int(connector_raw)
        except (TypeError, ValueError):
            connector_id = 0
        status = cp.connector_status.get(connector_id) or cp.connector_status.get(0) or "Unknown"

        metrics: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "connector_id": connector_id,
            "status": status,
            "transaction_id": payload.get("transactionId"),
        }
        total_current_a: float | None = None
        reported_power_w: float | None = None
        reported_energy_wh: float | None = None
        phase_currents: dict[str, float] = {}
        phase_voltages: dict[str, float] = {}
        meter_timestamp: datetime | None = None

        for meter in payload.get("meterValue", []):
            meter_timestamp = self._parse_ocpp_timestamp(meter.get("timestamp")) or meter_timestamp
            for sv in meter.get("sampledValue", []):
                measurand = sv.get("measurand", "Energy.Active.Import.Register")
                unit = sv.get("unit", "")
                raw_value = sv.get("value")
                if raw_value is None:
                    continue
                try:
                    value = float(raw_value)
                except ValueError:
                    continue

                if measurand == "Power.Active.Import":
                    w = value * 1000 if unit == "kW" else value
                    if w > 0.1:
                        reported_power_w = w

                elif measurand == "Current.Import":
                    phase = sv.get("phase")
                    if phase in {"L1", "L2", "L3"}:
                        phase_currents[phase] = value
                    elif value > 0.1:
                        total_current_a = value

                elif measurand == "Current.Offered":
                    metrics["current_offered_a"] = value

                elif measurand == "Energy.Active.Import.Register":
                    wh = value * 1000 if unit == "kWh" else value
                    if wh > 0.1:
                        reported_energy_wh = wh

                elif measurand == "Voltage":
                    phase = sv.get("phase")
                    is_plausible_phase_voltage = MIN_VALID_PHASE_VOLTAGE_V <= value <= MAX_VALID_PHASE_VOLTAGE_V
                    if phase in {"L1", "L2", "L3"}:
                        if is_plausible_phase_voltage:
                            phase_voltages[phase] = value
                    else:
                        if is_plausible_phase_voltage:
                            metrics["voltage_v"] = value
                            self.publish_event("voltage_v", {"value": value})

        active_phases = sum(1 for val in phase_currents.values() if val > 0.1)
        if active_phases > 0:
            self.last_active_phases = active_phases
            metrics["active_phases"] = active_phases

        if total_current_a is not None:
            current_a = total_current_a
        elif phase_currents:
            current_a = max(phase_currents.values())
        else:
            current_a = None

        derived_voltage_v: float | None = None
        if phase_voltages:
            derived_voltage_v = sum(phase_voltages.values()) / len(phase_voltages)

        if derived_voltage_v is not None:
            metrics["voltage_v"] = derived_voltage_v
            self.publish_event("voltage_v", {"value": derived_voltage_v})

        derived_power_w: float | None = reported_power_w
        if derived_power_w is None and phase_currents and phase_voltages:
            derived_power_w = sum(
                phase_currents[phase] * phase_voltages[phase]
                for phase in phase_currents
                if phase in phase_voltages and phase_currents[phase] > 0.1
            )

        if derived_power_w is not None:
            metrics["power_w"] = derived_power_w
            self.publish_event("power_w", {"value": derived_power_w})

        if current_a is not None:
            # Some chargers keep reporting ~6A while idle/finished; clamp to 0A when not charging.
            if (
                status != "Unknown"
                and status not in ACTIVE_CHARGING_STATUSES
                and (derived_power_w is None or derived_power_w <= NON_CHARGING_CURRENT_CLAMP_MAX_POWER_W)
            ):
                current_a = 0.0
            metrics["current_a"] = current_a
            self.publish_event("current_a", {"value": current_a})

        if reported_energy_wh is not None:
            self._derived_energy_wh = max(self._derived_energy_wh, reported_energy_wh)

        if meter_timestamp is not None and self._last_meter_timestamp is not None and derived_power_w is not None:
            elapsed_seconds = (meter_timestamp - self._last_meter_timestamp).total_seconds()
            if elapsed_seconds > 0:
                self._derived_energy_wh += derived_power_w * (elapsed_seconds / 3600.0)

        if meter_timestamp is not None:
            self._last_meter_timestamp = meter_timestamp

        if self._derived_energy_wh > 0:
            metrics["total_energy_wh"] = self._derived_energy_wh
            self.publish_event("total_energy_wh", {"value": self._derived_energy_wh})
            self.publish_event("lifetime_energy_kwh", {"value": self._derived_energy_wh / 1000.0})

        self.publish_event("metrics", metrics)

    # --------------------------------------------------------------- startup

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.mq.connect(self.config.mqtt.host, self.config.mqtt.port)
        self.mq.loop_start()

        log.info(
            "Starting OCPP server on %s:%s  (topic prefix: %s)",
            self.config.ocpp.host, self.config.ocpp.port, self.config.mqtt.topic_prefix,
        )
        self.publish(self._prefix("bridge/availability"), "online", retain=True)
        self.publish_event("authorize/state", {"enabled": self.authorize_enabled}, retain=True)
        async with ws_serve(
            self.handle_connection,
            self.config.ocpp.host,
            self.config.ocpp.port,
            subprotocols=["ocpp1.6"],
        ):
            await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser(description="OCPP SIGEN to MQTT bridge")
    parser.add_argument("--config", default="", help="Path to runtime YAML config")
    args = parser.parse_args()

    config = Config.load(args.config or None)

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler()],
    )

    try:
        asyncio.run(OcppBridge(config).run())
    except KeyboardInterrupt:
        log.info("Shutdown")


if __name__ == "__main__":
    main()
