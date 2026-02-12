from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field("bearer", description="Token type for Authorization header")


class RegisterRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="User password (min 6 chars)")
    full_name: Optional[str] = Field(None, description="Optional display name")


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class UserMeResponse(BaseModel):
    id: UUID = Field(..., description="User id")
    email: str = Field(..., description="User email")
    full_name: Optional[str] = Field(None, description="Full name")
    is_active: bool = Field(..., description="Whether the user is active")
    created_at: datetime = Field(..., description="Created timestamp")


class DeviceCreate(BaseModel):
    name: str = Field(..., description="Device name (unique per user)")
    location: Optional[str] = Field(None, description="Optional location label")
    type: str = Field("smart_plug", description="Device type")
    manufacturer: Optional[str] = Field(None, description="Manufacturer")
    model: Optional[str] = Field(None, description="Model")
    serial_number: Optional[str] = Field(None, description="Serial number")


class DeviceUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Device name")
    location: Optional[str] = Field(None, description="Location label")
    type: Optional[str] = Field(None, description="Device type")
    manufacturer: Optional[str] = Field(None, description="Manufacturer")
    model: Optional[str] = Field(None, description="Model")
    serial_number: Optional[str] = Field(None, description="Serial number")
    is_active: Optional[bool] = Field(None, description="Active flag")


class DeviceOut(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    location: Optional[str] = None
    type: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ReadingIn(BaseModel):
    device_id: UUID = Field(..., description="Device id to attach this reading to")
    ts: datetime = Field(..., description="Timestamp of the reading (ISO8601)")
    power_w: Decimal = Field(..., ge=0, description="Instantaneous power in Watts")
    voltage_v: Optional[Decimal] = Field(None, ge=0, description="Voltage in Volts")
    current_a: Optional[Decimal] = Field(None, ge=0, description="Current in Amps")
    energy_wh: Optional[Decimal] = Field(None, ge=0, description="Energy in Wh (cumulative or interval)")
    cost: Optional[Decimal] = Field(None, ge=0, description="Cost for this interval")
    raw: Optional[Dict[str, Any]] = Field(None, description="Optional raw JSON payload")


class IngestResponse(BaseModel):
    inserted: int = Field(..., description="Count of readings inserted")
    skipped: int = Field(..., description="Count of readings skipped due to conflicts")


class LiveUsageResponse(BaseModel):
    device_id: UUID = Field(..., description="Device id")
    ts: datetime = Field(..., description="Timestamp for latest reading")
    power_w: Decimal = Field(..., description="Power in W")
    voltage_v: Optional[Decimal] = None
    current_a: Optional[Decimal] = None
    energy_wh: Optional[Decimal] = None
    cost: Optional[Decimal] = None


class UsageSeriesPoint(BaseModel):
    ts: datetime
    power_w: Decimal
    energy_wh: Optional[Decimal] = None
    cost: Optional[Decimal] = None


class UsageSeriesResponse(BaseModel):
    device_id: Optional[UUID] = Field(None, description="Filtered device id, if applied")
    range: str = Field(..., description="Range identifier: 1h, 24h, 7d, 30d")
    points: List[UsageSeriesPoint]


class DashboardOverviewResponse(BaseModel):
    today_energy_wh: Decimal = Field(..., description="Total energy today (Wh) across user's devices")
    today_cost: Decimal = Field(..., description="Total cost today across user's devices")
    active_devices: int = Field(..., description="Number of active devices")
    alerts_enabled: int = Field(..., description="Count of enabled alert rules")
    last_updated: datetime = Field(..., description="Timestamp of last reading across user's devices")


class AnalyticsInsightsResponse(BaseModel):
    range: str = Field(..., description="Requested range")
    total_energy_wh: Decimal = Field(..., description="Total energy in range (Wh)")
    total_cost: Decimal = Field(..., description="Total cost in range")
    avg_power_w: Decimal = Field(..., description="Average power in range")
    peak_power_w: Decimal = Field(..., description="Peak power in range")
    anomalies: List[Dict[str, Any]] = Field(..., description="Detected anomalies (simple heuristics)")


MetricLiteral = Literal["power_w", "energy_wh", "cost"]
OperatorLiteral = Literal["gt", "gte", "lt", "lte", "eq"]


class AlertRuleCreate(BaseModel):
    name: str = Field(..., description="Rule name")
    device_id: Optional[UUID] = Field(None, description="Optional device scope; null means all devices")
    metric: MetricLiteral = Field(..., description="Metric to evaluate")
    operator: OperatorLiteral = Field(..., description="Comparison operator")
    threshold: Decimal = Field(..., description="Threshold value for metric")
    window_seconds: int = Field(0, ge=0, description="Evaluation window in seconds (0 = latest reading)")
    cooldown_seconds: int = Field(300, ge=0, description="Cooldown between triggers")
    is_enabled: bool = Field(True, description="Enabled flag")


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    device_id: Optional[UUID] = None
    metric: Optional[MetricLiteral] = None
    operator: Optional[OperatorLiteral] = None
    threshold: Optional[Decimal] = None
    window_seconds: Optional[int] = Field(None, ge=0)
    cooldown_seconds: Optional[int] = Field(None, ge=0)
    is_enabled: Optional[bool] = None


class AlertRuleOut(BaseModel):
    id: UUID
    user_id: UUID
    device_id: Optional[UUID] = None
    name: str
    metric: str
    operator: str
    threshold: Decimal
    window_seconds: int
    cooldown_seconds: int
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class NotificationHistoryOut(BaseModel):
    id: int
    event_id: Optional[int] = None
    user_id: UUID
    channel: str
    destination: Optional[str] = None
    status: str
    sent_at: Optional[datetime] = None
    error: Optional[str] = None
    created_at: datetime
