from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RegisterType = Literal["input", "holding"]
DataType = Literal["u16", "s16", "u32", "s32", "f32"]
Endian = Literal["big", "little"]
Profile = Literal["dev", "prod"]
EntityCategory = Literal["config", "diagnostic"]


class ReadingDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    label: str | None = None
    icon: str | None = None
    topic_suffix: str
    register_type: RegisterType
    address: int = Field(ge=0)
    length_words: int = Field(ge=1, le=2)
    data_type: DataType
    scale: float = 1.0
    offset: float = 0.0
    decimals: int = Field(default=0, ge=0, le=6)
    byte_order: Endian = "big"
    word_order: Endian = "big"
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    entity_category: EntityCategory | None = Field(default=None, alias="entityCategory")
    writable: bool = False

    @model_validator(mode="after")
    def _validate_word_length(self) -> ReadingDefinition:
        if self.data_type in {"u16", "s16"} and self.length_words != 1:
            msg = "u16/s16 readings must use length_words=1"
            raise ValueError(msg)
        if self.data_type in {"u32", "s32", "f32"} and self.length_words != 2:
            msg = "u32/s32/f32 readings must use length_words=2"
            raise ValueError(msg)
        return self


class ModbusConfig(BaseModel):
    host: str
    port: int = Field(default=502, ge=1, le=65535)
    unit_id: int = Field(default=1, ge=0, le=255)
    timeout_seconds: float = Field(default=3.0, gt=0)
    poll_interval_seconds: float = Field(default=5.0, gt=0)


class MqttConfig(BaseModel):
    host: str
    port: int = Field(default=1883, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    client_id: str = "modqtt-bridge"
    topic_prefix: str = "prod/sungrow"
    availability_topic: str = "bridge/availability"
    retain_state: bool = True
    json_grouped_topics: bool = False
    discovery_enabled: bool = False


class AppConfig(BaseModel):
    profile: Profile = "prod"
    read_only_mode: bool = True
    allow_writes: bool = False
    modbus: ModbusConfig
    mqtt: MqttConfig
    readings: list[ReadingDefinition]
    write_parameters: list[WriteParameterDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_safety(self) -> AppConfig:
        if self.profile == "dev" and self.mqtt.topic_prefix.startswith("prod/"):
            msg = "dev profile must not publish under prod/ prefix"
            raise ValueError(msg)
        if self.read_only_mode and self.allow_writes:
            msg = "read_only_mode=true requires allow_writes=false"
            raise ValueError(msg)
        return self


class WriteParameterDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    label: str | None = None
    icon: str | None = None
    register_type: Literal["holding"] = "holding"
    address: int = Field(ge=0)
    length_words: int = Field(ge=1, le=2)
    data_type: Literal["u16", "s16", "u32", "s32"]
    scale: float = 1.0
    offset: float = 0.0
    decimals: int = Field(default=0, ge=0, le=6)
    byte_order: Endian = "big"
    word_order: Endian = "big"
    entity_category: EntityCategory | None = Field(default="config", alias="entityCategory")
    min_value: float | None = None
    max_value: float | None = None

    @model_validator(mode="after")
    def _validate_word_length(self) -> WriteParameterDefinition:
        if self.data_type in {"u16", "s16"} and self.length_words != 1:
            msg = "u16/s16 write parameters must use length_words=1"
            raise ValueError(msg)
        if self.data_type in {"u32", "s32"} and self.length_words != 2:
            msg = "u32/s32 write parameters must use length_words=2"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_value_range(self) -> WriteParameterDefinition:
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            msg = "min_value must be less than or equal to max_value"
            raise ValueError(msg)
        return self
