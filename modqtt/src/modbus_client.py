from __future__ import annotations

import logging
import struct
import time
from collections.abc import Sequence
from dataclasses import dataclass

from pymodbus.client import ModbusTcpClient

from src.models import ReadingDefinition, WriteParameterDefinition

LOGGER = logging.getLogger(__name__)


@dataclass
class _Batch:
    register_type: str
    start: int
    count: int
    readings: list[ReadingDefinition]


class ModbusReader:
    def __init__(self, host: str, port: int, unit_id: int, timeout_seconds: float) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout_seconds = timeout_seconds
        self._client = ModbusTcpClient(host=self.host, port=self.port, timeout=self.timeout_seconds)

    def connect_with_backoff(self, max_delay_seconds: float = 30.0) -> None:
        delay = 1.0
        while not self._client.connected:
            if self._client.connect():
                LOGGER.info("modbus_connected host=%s port=%s", self.host, self.port)
                return
            LOGGER.warning(
                "modbus_connect_retry host=%s port=%s next_delay=%.1f",
                self.host,
                self.port,
                delay,
            )
            time.sleep(delay)
            delay = min(delay * 2, max_delay_seconds)

    def close(self) -> None:
        self._client.close()

    def _ensure_connected(self) -> None:
        if not self._client.connected:
            self.connect_with_backoff()

    def _read_registers(self, register_type: str, address: int, count: int) -> list[int]:
        self._ensure_connected()
        if register_type == "input":
            response = self._client.read_input_registers(
                address=address,
                count=count,
                device_id=self.unit_id,
            )
        else:
            response = self._client.read_holding_registers(
                address=address,
                count=count,
                device_id=self.unit_id,
            )

        if response.isError():
            raise RuntimeError(
                "Modbus read failed "
                f"type={register_type} address={address} count={count} response={response}"
            )
        return [int(word) & 0xFFFF for word in response.registers]

    def _build_batches(self, readings: Sequence[ReadingDefinition]) -> list[_Batch]:
        if not readings:
            return []

        ordered = sorted(readings, key=lambda item: (item.register_type, item.address))
        batches: list[_Batch] = []

        current = _Batch(
            register_type=ordered[0].register_type,
            start=ordered[0].address,
            count=ordered[0].length_words,
            readings=[ordered[0]],
        )

        for reading in ordered[1:]:
            next_address = current.start + current.count
            is_same_type = reading.register_type == current.register_type
            is_contiguous = reading.address == next_address
            next_total_words = (reading.address + reading.length_words) - current.start
            # Modbus function codes limit reads to 125 registers per request.
            fits_limit = next_total_words <= 125

            if is_same_type and is_contiguous and fits_limit:
                current.readings.append(reading)
                current.count = next_total_words
            else:
                batches.append(current)
                current = _Batch(
                    register_type=reading.register_type,
                    start=reading.address,
                    count=reading.length_words,
                    readings=[reading],
                )

        batches.append(current)
        return batches

    def read_words(self, reading: ReadingDefinition) -> Sequence[int]:
        words = self._read_registers(
            register_type=reading.register_type,
            address=reading.address,
            count=reading.length_words,
        )
        return words

    def read_many(self, readings: Sequence[ReadingDefinition]) -> dict[str, list[int]]:
        values_by_name: dict[str, list[int]] = {}
        for batch in self._build_batches(readings):
            raw = self._read_registers(
                register_type=batch.register_type,
                address=batch.start,
                count=batch.count,
            )
            for reading in batch.readings:
                offset = reading.address - batch.start
                values_by_name[reading.name] = raw[offset : offset + reading.length_words]
        return values_by_name

    def _pack_value(self, definition: WriteParameterDefinition, value: float) -> list[int]:
        if definition.scale == 0:
            raise ValueError("scale must not be zero for write parameters")

        if definition.min_value is not None and value < definition.min_value:
            raise ValueError(
                f"Value {value} is below min_value={definition.min_value} for {definition.name}"
            )
        if definition.max_value is not None and value > definition.max_value:
            raise ValueError(
                f"Value {value} is above max_value={definition.max_value} for {definition.name}"
            )

        raw_value = int(round((value - definition.offset) / definition.scale))

        if definition.data_type == "u16":
            packed = struct.pack(">H", raw_value)
        elif definition.data_type == "s16":
            packed = struct.pack(">h", raw_value)
        elif definition.data_type == "u32":
            packed = struct.pack(">I", raw_value)
        elif definition.data_type == "s32":
            packed = struct.pack(">i", raw_value)
        else:
            raise ValueError(f"Unsupported write data type: {definition.data_type}")

        words: list[int] = []
        for idx in range(0, len(packed), 2):
            chunk = packed[idx : idx + 2]
            if definition.byte_order == "little":
                chunk = bytes((chunk[1], chunk[0]))
            words.append((chunk[0] << 8) | chunk[1])

        if definition.word_order == "little" and len(words) == 2:
            words = [words[1], words[0]]
        return words

    def write_parameter(self, definition: WriteParameterDefinition, value: float) -> None:
        self._ensure_connected()
        words = self._pack_value(definition, value)

        if len(words) == 1:
            response = self._client.write_register(
                address=definition.address,
                value=words[0],
                device_id=self.unit_id,
            )
        else:
            response = self._client.write_registers(
                address=definition.address,
                values=words,
                device_id=self.unit_id,
            )

        if response.isError():
            raise RuntimeError(
                "Modbus write failed "
                "name="
                f"{definition.name} address={definition.address} value={value} "
                f"response={response}"
            )

        LOGGER.info(
            "modbus_write_ok name=%s address=%s value=%s raw_words=%s",
            definition.name,
            definition.address,
            value,
            words,
        )
