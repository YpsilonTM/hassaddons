from __future__ import annotations

import logging
import time

from paho.mqtt import client as mqtt

LOGGER = logging.getLogger(__name__)


class MqttPublisher:
    def __init__(
        self,
        host: str,
        port: int,
        client_id: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self._username = username
        self._password = password
        if hasattr(mqtt, "CallbackAPIVersion"):
            self._client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=self.client_id,
            )
        else:
            self._client = mqtt.Client(client_id=self.client_id)
        if self._username:
            self._client.username_pw_set(self._username, self._password)
        self._connected = False
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        del client, userdata, flags, reason_code, properties
        self._connected = True
        LOGGER.info("mqtt_connected host=%s port=%s", self.host, self.port)

    def _on_disconnect(self, client, userdata, reason_code=None, properties=None):
        del client, userdata, properties
        self._connected = False
        LOGGER.warning("mqtt_disconnected reason=%s", reason_code)

    def connect_with_backoff(self, max_delay_seconds: float = 30.0) -> None:
        delay = 1.0
        while not self._connected:
            try:
                self._client.connect(host=self.host, port=self.port)
                self._client.loop_start()
                time.sleep(0.2)
                if self._connected:
                    return
            except Exception as exc:
                LOGGER.warning(
                    "mqtt_connect_error host=%s port=%s error=%s",
                    self.host,
                    self.port,
                    exc,
                )

            LOGGER.warning(
                "mqtt_connect_retry host=%s port=%s next_delay=%.1f",
                self.host,
                self.port,
                delay,
            )
            time.sleep(delay)
            delay = min(delay * 2, max_delay_seconds)

    def disconnect(self) -> None:
        if self._connected:
            self._client.disconnect()
        self._client.loop_stop()

    def _ensure_connected(self) -> None:
        if not self._connected:
            self.connect_with_backoff()

    def publish_state(self, topic: str, payload: str, retain: bool = True) -> None:
        self._ensure_connected()
        result = self._client.publish(topic=topic, payload=payload, qos=0, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"Failed to publish topic={topic} rc={result.rc}")

    def publish_availability(self, topic: str, online: bool) -> None:
        message = "online" if online else "offline"
        self.publish_state(topic=topic, payload=message, retain=True)
