from __future__ import annotations

import struct
from collections.abc import Sequence

from src.models import DataType, ReadingDefinition


def _ordered_words(words: Sequence[int], word_order: str) -> list[int]:
    normalized = [int(word) & 0xFFFF for word in words]
    if word_order == "little":
        return list(reversed(normalized))
    return normalized


def _word_to_bytes(word: int, byte_order: str) -> bytes:
    high = (word >> 8) & 0xFF
    low = word & 0xFF
    if byte_order == "big":
        return bytes((high, low))
    return bytes((low, high))


def words_to_bytes(words: Sequence[int], *, byte_order: str, word_order: str) -> bytes:
    ordered = _ordered_words(words, word_order)
    raw = bytearray()
    for word in ordered:
        raw.extend(_word_to_bytes(word, byte_order))
    return bytes(raw)


def decode_raw_value(
    words: Sequence[int], *, data_type: DataType, byte_order: str, word_order: str
) -> int | float:
    if data_type in {"u16", "s16"} and len(words) != 1:
        raise ValueError("u16/s16 decoding requires exactly one 16-bit word")
    if data_type in {"u32", "s32", "f32"} and len(words) != 2:
        raise ValueError("u32/s32/f32 decoding requires exactly two 16-bit words")

    raw = words_to_bytes(words, byte_order=byte_order, word_order=word_order)

    if data_type == "u16":
        return struct.unpack(">H", raw)[0]
    if data_type == "s16":
        return struct.unpack(">h", raw)[0]
    if data_type == "u32":
        return struct.unpack(">I", raw)[0]
    if data_type == "s32":
        return struct.unpack(">i", raw)[0]
    if data_type == "f32":
        return struct.unpack(">f", raw)[0]

    raise ValueError(f"Unsupported data type: {data_type}")


def apply_transform(
    value: int | float,
    *,
    scale: float,
    offset: float,
    decimals: int,
) -> int | float:
    transformed = (float(value) * scale) + offset
    rounded = round(transformed, decimals)
    if decimals == 0:
        return int(rounded)
    return rounded


def decode_reading(words: Sequence[int], reading: ReadingDefinition) -> int | float:
    raw_value = decode_raw_value(
        words,
        data_type=reading.data_type,
        byte_order=reading.byte_order,
        word_order=reading.word_order,
    )
    return apply_transform(
        raw_value,
        scale=reading.scale,
        offset=reading.offset,
        decimals=reading.decimals,
    )
