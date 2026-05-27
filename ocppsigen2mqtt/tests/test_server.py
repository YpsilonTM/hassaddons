"""Tests for OCPP bridge logic."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import Config
from server import CALL, CALL_RESULT, CALL_ERROR, ChargePoint, OcppBridge


def make_bridge() -> OcppBridge:
    cfg = Config()
    bridge = OcppBridge(cfg)
    bridge.loop = asyncio.get_event_loop()
    bridge.mq = MagicMock()
    return bridge


@pytest.mark.asyncio
async def test_boot_notification_returns_accepted():
    bridge = make_bridge()
    ws = MagicMock()
    ws.__aiter__ = MagicMock(return_value=iter([]))
    sent_frames = []
    async def fake_send(data):
        sent_frames.append(json.loads(data))
    ws.send = fake_send

    cp = ChargePoint("TEST01")
    cp.websocket = ws

    boot_frame = json.dumps([CALL, "msg1", "BootNotification", {
        "chargePointModel": "EVAC11",
        "chargePointVendor": "SIGEN",
    }])
    await bridge._handle_frame(cp, boot_frame)

    assert len(sent_frames) == 1
    resp = sent_frames[0]
    assert resp[0] == CALL_RESULT
    assert resp[1] == "msg1"
    assert resp[2]["status"] == "Accepted"


@pytest.mark.asyncio
async def test_meter_values_published():
    bridge = make_bridge()
    ws = MagicMock()
    async def fake_send(data):
        pass
    ws.send = fake_send

    cp = ChargePoint("TEST01")
    cp.websocket = ws
    bridge.charge_points["TEST01"] = cp

    published: dict[str, object] = {}
    def fake_publish(topic, payload, retain=True):
        published[topic] = payload
    bridge.publish = fake_publish

    payload = {
        "connectorId": 1,
        "transactionId": 42,
        "meterValue": [{
            "timestamp": "2025-01-01T00:00:00Z",
            "sampledValue": [
                {"measurand": "Power.Active.Import", "value": "3.5", "unit": "kW"},
                {"measurand": "Current.Import", "value": "15.2", "unit": "A"},
                {"measurand": "Energy.Active.Import.Register", "value": "12.345", "unit": "kWh"},
            ],
        }],
    }
    meter_frame = json.dumps([CALL, "msg2", "MeterValues", payload])
    await bridge._handle_frame(cp, meter_frame)

    assert published["ocpp/power_w"] == {"charger_id": "CHARGER01", "value": 3500.0}
    assert published["ocpp/current_a"] == {"charger_id": "CHARGER01", "value": 15.2}
    assert published["ocpp/total_energy_wh"] == {"charger_id": "CHARGER01", "value": 12345.0}
    assert published["ocpp/lifetime_energy_kwh"] == {"charger_id": "CHARGER01", "value": 12.345}


@pytest.mark.asyncio
async def test_meter_values_current_uses_nonzero_phase_when_total_is_zero():
    bridge = make_bridge()
    ws = MagicMock()

    async def fake_send(data):
        pass

    ws.send = fake_send

    cp = ChargePoint("TEST01")
    cp.websocket = ws
    bridge.charge_points["TEST01"] = cp

    published: dict[str, object] = {}

    def fake_publish(topic, payload, retain=True):
        published[topic] = payload

    bridge.publish = fake_publish

    payload = {
        "connectorId": 1,
        "transactionId": 42,
        "meterValue": [{
            "timestamp": "2025-01-01T00:00:00Z",
            "sampledValue": [
                {"measurand": "Current.Import", "value": "5.92", "unit": "A", "phase": "L1"},
                {"measurand": "Current.Import", "value": "6.03", "unit": "A", "phase": "L2"},
                {"measurand": "Current.Import", "value": "0.0", "unit": "A"},
            ],
        }],
    }

    meter_frame = json.dumps([CALL, "msg2", "MeterValues", payload])
    await bridge._handle_frame(cp, meter_frame)

    assert published["ocpp/current_a"] == {"charger_id": "CHARGER01", "value": 6.03}


@pytest.mark.asyncio
async def test_meter_values_derives_power_voltage_and_energy_from_phase_samples():
    bridge = make_bridge()
    ws = MagicMock()

    async def fake_send(data):
        pass

    ws.send = fake_send

    cp = ChargePoint("TEST01")
    cp.websocket = ws
    bridge.charge_points["TEST01"] = cp

    published: dict[str, object] = {}

    def fake_publish(topic, payload, retain=True):
        published[topic] = payload

    bridge.publish = fake_publish

    first_payload = {
        "connectorId": 1,
        "transactionId": 42,
        "meterValue": [{
            "timestamp": "2026-05-27T13:41:11Z",
            "sampledValue": [
                {"value": "5.98", "measurand": "Current.Import", "unit": "A", "phase": "L1"},
                {"value": "6.03", "measurand": "Current.Import", "unit": "A", "phase": "L2"},
                {"value": "0.00", "measurand": "Current.Import", "unit": "A", "phase": "L3"},
                {"value": "243.72", "measurand": "Voltage", "unit": "V", "phase": "L1"},
                {"value": "238.04", "measurand": "Voltage", "unit": "V", "phase": "L2"},
                {"value": "233.30", "measurand": "Voltage", "unit": "V", "phase": "L3"},
                {"value": "0", "measurand": "Power.Active.Import", "unit": "W"},
                {"value": "0", "measurand": "Energy.Active.Import.Register", "unit": "Wh"},
            ],
        }],
    }

    second_payload = {
        "connectorId": 1,
        "transactionId": 42,
        "meterValue": [{
            "timestamp": "2026-05-27T13:41:41Z",
            "sampledValue": first_payload["meterValue"][0]["sampledValue"],
        }],
    }

    await bridge._handle_frame(cp, json.dumps([CALL, "msg1", "MeterValues", first_payload]))
    await bridge._handle_frame(cp, json.dumps([CALL, "msg2", "MeterValues", second_payload]))

    assert published["ocpp/current_a"] == {"charger_id": "CHARGER01", "value": 6.03}
    assert published["ocpp/voltage_v"] == {"charger_id": "CHARGER01", "value": pytest.approx(238.35333333333332)}
    assert published["ocpp/power_w"] == {"charger_id": "CHARGER01", "value": pytest.approx(2865.0, rel=0.05)}
    assert published["ocpp/total_energy_wh"] == {"charger_id": "CHARGER01", "value": pytest.approx(23.875, rel=0.05)}
    assert published["ocpp/lifetime_energy_kwh"] == {"charger_id": "CHARGER01", "value": pytest.approx(0.023875, rel=0.05)}


@pytest.mark.asyncio
async def test_start_transaction_assigns_transaction_id():
    bridge = make_bridge()
    ws = MagicMock()
    async def fake_send(data):
        pass
    ws.send = fake_send

    cp = ChargePoint("TEST01")
    cp.websocket = ws
    bridge.charge_points["TEST01"] = cp

    published = {}
    def fake_publish(topic, payload, retain=True):
        published[topic] = payload
    bridge.publish = fake_publish

    payload = {
        "connectorId": 1,
        "idTag": "REMOTE",
        "meterStart": 0,
        "timestamp": "2025-01-01T00:00:00Z",
    }
    frame = json.dumps([CALL, "msg3", "StartTransaction", payload])
    await bridge._handle_frame(cp, frame)

    assert cp.transaction_id is not None
    assert "ocpp/transaction/active" in published
    assert published["ocpp/transaction/active"]["charger_id"] == "CHARGER01"


@pytest.mark.asyncio
async def test_stop_transaction_clears_transaction_id():
    bridge = make_bridge()
    ws = MagicMock()
    async def fake_send(data):
        pass
    ws.send = fake_send

    cp = ChargePoint("TEST01")
    cp.websocket = ws
    cp.transaction_id = 999
    bridge.charge_points["TEST01"] = cp

    published = {}
    def fake_publish(topic, payload, retain=True):
        published[topic] = payload
    bridge.publish = fake_publish

    payload = {
        "transactionId": 999,
        "meterStop": 5000,
        "timestamp": "2025-01-01T01:00:00Z",
        "reason": "Remote",
    }
    frame = json.dumps([CALL, "msg4", "StopTransaction", payload])
    await bridge._handle_frame(cp, frame)

    assert cp.transaction_id is None
    assert "ocpp/transaction/last" in published
    assert published["ocpp/transaction/last"]["charger_id"] == "CHARGER01"


@pytest.mark.asyncio
async def test_authorize_accepted_when_enabled():
    """Charger should receive Accepted when authorize is enabled."""
    bridge = make_bridge()
    assert bridge.authorize_enabled is True

    ws = MagicMock()
    sent_frames = []
    async def fake_send(data):
        sent_frames.append(json.loads(data))
    ws.send = fake_send

    cp = ChargePoint("TEST01")
    cp.websocket = ws

    auth_frame = json.dumps([CALL, "auth1", "Authorize", {"idTag": "REMOTE"}])
    await bridge._handle_frame(cp, auth_frame)

    assert len(sent_frames) == 1
    resp = sent_frames[0]
    assert resp[0] == CALL_RESULT
    assert resp[1] == "auth1"
    assert resp[2]["idTagInfo"]["status"] == "Accepted"


@pytest.mark.asyncio
async def test_authorize_blocked_when_disabled():
    """Charger should receive Blocked when authorize is disabled."""
    cfg = Config()
    cfg.authorize_enabled = False
    bridge = OcppBridge(cfg)
    bridge.loop = asyncio.get_event_loop()
    bridge.mq = MagicMock()

    ws = MagicMock()
    sent_frames = []
    async def fake_send(data):
        sent_frames.append(json.loads(data))
    ws.send = fake_send

    cp = ChargePoint("TEST01")
    cp.websocket = ws

    auth_frame = json.dumps([CALL, "auth1", "Authorize", {"idTag": "REMOTE"}])
    await bridge._handle_frame(cp, auth_frame)

    assert len(sent_frames) == 1
    resp = sent_frames[0]
    assert resp[0] == CALL_RESULT
    assert resp[1] == "auth1"
    assert resp[2]["idTagInfo"]["status"] == "Blocked"


@pytest.mark.asyncio
async def test_toggle_authorize_toggles_state():
    """Calling toggle_authorize without enabled field should toggle."""
    bridge = make_bridge()
    initial_state = bridge.authorize_enabled

    published = {}
    def fake_publish(topic, payload, retain=True):
        published[topic] = payload
    bridge.publish = fake_publish

    await bridge._cmd_toggle_authorize("TEST01", {})

    assert bridge.authorize_enabled == (not initial_state)
    assert "ocpp/authorize/state" in published
    assert published["ocpp/authorize/state"]["enabled"] == (not initial_state)


@pytest.mark.asyncio
async def test_toggle_authorize_sets_explicit_state():
    """Calling toggle_authorize with enabled field should set that value."""
    bridge = make_bridge()

    published = {}
    def fake_publish(topic, payload, retain=True):
        published[topic] = payload
    bridge.publish = fake_publish

    await bridge._cmd_toggle_authorize("TEST01", {"enabled": False})

    assert bridge.authorize_enabled is False
    assert "ocpp/authorize/state" in published
    assert published["ocpp/authorize/state"]["enabled"] is False

    await bridge._cmd_toggle_authorize("TEST01", {"enabled": True})

    assert bridge.authorize_enabled is True
    assert published["ocpp/authorize/state"]["enabled"] is True


@pytest.mark.asyncio
async def test_set_power_watts_uses_fixed_230v_and_active_phases():
    bridge = make_bridge()

    async def fake_send_call(cp_id, action, payload, timeout=20):
        assert cp_id == "TEST01"
        assert action == "SetChargingProfile"
        assert payload["connectorId"] == 0
        assert payload["csChargingProfiles"]["chargingProfilePurpose"] == "ChargePointMaxProfile"
        periods = payload["csChargingProfiles"]["chargingSchedule"]["chargingSchedulePeriod"]
        assert periods[0]["limit"] == 6
        return {"status": "Accepted"}

    bridge._send_call = fake_send_call

    published = {}

    def fake_publish(topic, payload, retain=True):
        published[topic] = payload

    bridge.publish = fake_publish

    await bridge._cmd_set_power_watts("TEST01", {"watts": 3000})

    assert "ocpp/command_result/set_power_watts" in published
    result = published["ocpp/command_result/set_power_watts"]
    assert result["status"] == "ok"
    assert result["configured_current_a"] == 6
    assert result["assumed_voltage_v"] == 230.0
    assert result["assumed_phases"] == 2


@pytest.mark.asyncio
async def test_set_power_watts_uses_transaction_id_for_tx_profile():
    bridge = make_bridge()
    cp = ChargePoint("TEST01")
    cp.transaction_id = 12345
    bridge.charge_points["TEST01"] = cp

    async def fake_send_call(cp_id, action, payload, timeout=20):
        assert cp_id == "TEST01"
        assert action == "SetChargingProfile"
        assert payload["connectorId"] == 1
        assert payload["csChargingProfiles"]["chargingProfilePurpose"] == "TxProfile"
        assert payload["csChargingProfiles"]["transactionId"] == 12345
        return {"status": "Accepted"}

    bridge._send_call = fake_send_call
    bridge.publish = MagicMock()

    await bridge._cmd_set_power_watts("TEST01", {"watts": 3000})


@pytest.mark.asyncio
async def test_set_power_watts_clamps_to_min_max():
    bridge = make_bridge()

    sent_values = []

    async def fake_send_call(_cp_id, action, payload, timeout=20):
        assert action == "SetChargingProfile"
        sent_values.append(int(payload["csChargingProfiles"]["chargingSchedule"]["chargingSchedulePeriod"][0]["limit"]))
        return {"status": "Accepted"}

    bridge._send_call = fake_send_call
    bridge.publish = MagicMock()

    # floor(500 / (230 * 2)) = 1 -> clamp to 6
    await bridge._cmd_set_power_watts("TEST01", {"watts": 500})
    # floor(10000 / (230 * 2)) = 21 -> clamp to 16
    await bridge._cmd_set_power_watts("TEST01", {"watts": 10000})

    assert sent_values == [6, 16]


@pytest.mark.asyncio
async def test_set_power_watts_command_can_override_phases():
    bridge = make_bridge()
    bridge.usable_phases = 2

    async def fake_send_call(_cp_id, _action, payload, timeout=20):
        # floor(3000 / (230 * 3)) = 4 -> clamp to 6
        assert payload["csChargingProfiles"]["chargingSchedule"]["chargingSchedulePeriod"][0]["limit"] == 6
        return {"status": "Accepted"}

    bridge._send_call = fake_send_call
    bridge.publish = MagicMock()

    await bridge._cmd_set_power_watts("TEST01", {"watts": 3000, "phases": 3})


@pytest.mark.asyncio
async def test_set_power_watts_can_override_connector_for_idle_profile():
    bridge = make_bridge()

    async def fake_send_call(_cp_id, _action, payload, timeout=20):
        assert payload["connectorId"] == 2
        assert payload["csChargingProfiles"]["chargingProfilePurpose"] == "ChargePointMaxProfile"
        return {"status": "Accepted"}

    bridge._send_call = fake_send_call
    bridge.publish = MagicMock()

    await bridge._cmd_set_power_watts("TEST01", {"watts": 3000, "connector_id": 2})


def test_publish_ha_discovery_adds_buttons_and_voltage_icon():
    bridge = make_bridge()

    published: dict[str, object] = {}

    def fake_publish(topic, payload, retain=True):
        published[topic] = payload

    bridge.publish = fake_publish

    bridge._publish_ha_discovery()

    voltage_topic = "homeassistant/sensor/charger01_voltage_v/config"
    assert voltage_topic in published
    voltage_payload = published[voltage_topic]
    assert isinstance(voltage_payload, dict)
    assert voltage_payload["icon"] == "mdi:sine-wave"

    lifetime_energy_topic = "homeassistant/sensor/charger01_lifetime_energy_kwh/config"
    assert lifetime_energy_topic in published
    lifetime_energy_payload = published[lifetime_energy_topic]
    assert isinstance(lifetime_energy_payload, dict)
    assert lifetime_energy_payload["unit_of_measurement"] == "kWh"
    assert lifetime_energy_payload["state_class"] == "total_increasing"

    start_button_topic = "homeassistant/button/charger01_start_button/config"
    stop_button_topic = "homeassistant/button/charger01_stop_button/config"
    reset_button_topic = "homeassistant/button/charger01_reset_button/config"

    assert start_button_topic in published
    assert stop_button_topic in published
    assert reset_button_topic in published

    start_payload = published[start_button_topic]
    stop_payload = published[stop_button_topic]
    reset_payload = published[reset_button_topic]

    assert isinstance(start_payload, dict)
    assert isinstance(stop_payload, dict)
    assert isinstance(reset_payload, dict)

    assert start_payload["command_topic"] == "ocpp/command/start"
    assert stop_payload["command_topic"] == "ocpp/command/stop"
    assert reset_payload["command_topic"] == "ocpp/command/reset"

    assert start_payload["payload_press"] == '{"connector_id": 1, "id_tag": "REMOTE"}'
    assert stop_payload["payload_press"] == "{}"
    assert reset_payload["payload_press"] == '{"type": "Soft"}'
