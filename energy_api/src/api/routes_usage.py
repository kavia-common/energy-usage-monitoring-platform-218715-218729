from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api import db
from src.api.alerts import evaluate_rules_for_device
from src.api.deps import get_current_user
from src.api.realtime import manager
from src.api.schemas import (
    AnalyticsInsightsResponse,
    DashboardOverviewResponse,
    IngestResponse,
    LiveUsageResponse,
    ReadingIn,
    UsageSeriesPoint,
    UsageSeriesResponse,
)

router = APIRouter(tags=["usage"])


def _range_to_window(range_key: str) -> timedelta:
    if range_key == "1h":
        return timedelta(hours=1)
    if range_key == "24h":
        return timedelta(hours=24)
    if range_key == "7d":
        return timedelta(days=7)
    if range_key == "30d":
        return timedelta(days=30)
    return timedelta(hours=24)


@router.post(
    "/ingest/readings",
    response_model=IngestResponse,
    summary="Ingest readings",
    description="Insert one or more energy readings. Conflicts on (device_id, ts) are skipped.",
    operation_id="ingest_readings",
)
async def ingest_readings(payload: list[ReadingIn], user: dict = Depends(get_current_user)) -> IngestResponse:
    """
    Ingest readings.

    For safety, validates the device belongs to the authenticated user.
    Broadcasts realtime messages after insert and evaluates alert rules.
    """
    if not payload:
        return IngestResponse(inserted=0, skipped=0)

    # Verify all devices belong to user.
    device_ids = sorted({str(r.device_id) for r in payload})
    owned = db.fetch_all(
        "SELECT id FROM devices WHERE user_id = %s AND id = ANY(%s::uuid[])",
        [str(user["id"]), device_ids],
    )
    owned_ids = {str(r["id"]) for r in owned}
    for did in device_ids:
        if did not in owned_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Device not owned: {did}")

    rows = []
    for r in payload:
        rows.append(
            [
                str(r.device_id),
                r.ts,
                r.power_w,
                r.voltage_v,
                r.current_a,
                r.energy_wh,
                r.cost,
                r.raw,
            ]
        )

    # Insert with ON CONFLICT DO NOTHING to respect unique(device_id, ts)
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO readings (device_id, ts, power_w, voltage_v, current_a, energy_wh, cost, raw)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (device_id, ts) DO NOTHING
                """,
                rows,
            )
            inserted = cur.rowcount

    skipped = max(0, len(rows) - inserted)

    # Realtime: broadcast latest readings for affected devices (fetch current latest).
    for did in device_ids:
        latest = db.fetch_one(
            """
            SELECT device_id, ts, power_w, voltage_v, current_a, energy_wh, cost
            FROM readings
            WHERE device_id = %s
            ORDER BY ts DESC
            LIMIT 1
            """,
            [did],
        )
        if latest:
            await manager.broadcast_user(
                UUID(str(user["id"])),
                {"type": "reading_latest", "device_id": did, "data": latest},
            )

            # Evaluate alerts based on the latest ts for this device.
            events = evaluate_rules_for_device(
                user_id=UUID(str(user["id"])),
                device_id=UUID(did),
                reading_ts=latest["ts"],
            )
            for evt in events:
                await manager.broadcast_user(UUID(str(user["id"])), {"type": "alert_triggered", "data": evt})

    return IngestResponse(inserted=inserted, skipped=skipped)


@router.get(
    "/usage/live",
    response_model=Optional[LiveUsageResponse],
    summary="Get live usage",
    description="Returns the latest reading for a device (or latest across all devices if device_id omitted).",
    operation_id="usage_live",
)
def usage_live(
    device_id: Optional[UUID] = Query(default=None, description="Device to query"),
    user: dict = Depends(get_current_user),
) -> Optional[LiveUsageResponse]:
    """Return latest reading for device or overall."""
    if device_id:
        # Ensure ownership
        dev = db.fetch_one("SELECT id FROM devices WHERE id = %s AND user_id = %s", [str(device_id), str(user["id"])])
        if not dev:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

        row = db.fetch_one(
            """
            SELECT device_id, ts, power_w, voltage_v, current_a, energy_wh, cost
            FROM readings
            WHERE device_id = %s
            ORDER BY ts DESC
            LIMIT 1
            """,
            [str(device_id)],
        )
    else:
        row = db.fetch_one(
            """
            SELECT r.device_id, r.ts, r.power_w, r.voltage_v, r.current_a, r.energy_wh, r.cost
            FROM readings r
            JOIN devices d ON d.id = r.device_id
            WHERE d.user_id = %s
            ORDER BY r.ts DESC
            LIMIT 1
            """,
            [str(user["id"])],
        )

    if not row:
        return None
    return LiveUsageResponse(**row)


@router.get(
    "/usage/series",
    response_model=UsageSeriesResponse,
    summary="Get usage series",
    description="Time-series for charts for a range (1h, 24h, 7d, 30d).",
    operation_id="usage_series",
)
def usage_series(
    device_id: Optional[UUID] = Query(default=None, description="Optional device id"),
    range: str = Query(default="24h", description="Range: 1h, 24h, 7d, 30d"),
    user: dict = Depends(get_current_user),
) -> UsageSeriesResponse:
    """Return downsampled time series for charts."""
    window = _range_to_window(range)
    end = datetime.now(timezone.utc)
    start = end - window

    params = [str(user["id"]), start, end]
    device_clause = ""
    if device_id:
        device_clause = "AND d.id = %s"
        params.insert(1, str(device_id))

    rows = db.fetch_all(
        f"""
        SELECT r.ts, r.power_w, r.energy_wh, r.cost
        FROM readings r
        JOIN devices d ON d.id = r.device_id
        WHERE d.user_id = %s
          {device_clause}
          AND r.ts >= %s
          AND r.ts <= %s
        ORDER BY r.ts ASC
        """,
        params,
    )

    points = [UsageSeriesPoint(**r) for r in rows]
    return UsageSeriesResponse(device_id=device_id, range=range, points=points)


@router.get(
    "/dashboard/overview",
    response_model=DashboardOverviewResponse,
    summary="Dashboard overview",
    description="High-level metrics for the Overview page.",
    operation_id="dashboard_overview",
)
def dashboard_overview(user: dict = Depends(get_current_user)) -> DashboardOverviewResponse:
    """Compute overview metrics across user's devices for 'today'."""
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    totals = db.fetch_one(
        """
        SELECT
          COALESCE(SUM(r.energy_wh), 0)::numeric(14,3) AS today_energy_wh,
          COALESCE(SUM(r.cost), 0)::numeric(14,4) AS today_cost,
          COALESCE(MAX(r.ts), now()) AS last_updated
        FROM readings r
        JOIN devices d ON d.id = r.device_id
        WHERE d.user_id = %s
          AND r.ts >= %s
          AND r.ts <= %s
        """,
        [str(user["id"]), start, now],
    ) or {"today_energy_wh": 0, "today_cost": 0, "last_updated": now}

    active_devices = db.fetch_one(
        "SELECT COUNT(*)::int AS c FROM devices WHERE user_id = %s AND is_active = true",
        [str(user["id"])],
    ) or {"c": 0}

    alerts_enabled = db.fetch_one(
        "SELECT COUNT(*)::int AS c FROM alert_rules WHERE user_id = %s AND is_enabled = true",
        [str(user["id"])],
    ) or {"c": 0}

    return DashboardOverviewResponse(
        today_energy_wh=Decimal(str(totals["today_energy_wh"])),
        today_cost=Decimal(str(totals["today_cost"])),
        active_devices=int(active_devices["c"]),
        alerts_enabled=int(alerts_enabled["c"]),
        last_updated=totals["last_updated"],
    )


@router.get(
    "/analytics/insights",
    response_model=AnalyticsInsightsResponse,
    summary="Analytics insights",
    description="Aggregated insights for a time range (default 7d).",
    operation_id="analytics_insights",
)
def analytics_insights(
    range: str = Query(default="7d", description="Range: 1h, 24h, 7d, 30d"),
    user: dict = Depends(get_current_user),
) -> AnalyticsInsightsResponse:
    """Compute rollups, peak, and simple anomaly detection for a range."""
    window = _range_to_window(range)
    end = datetime.now(timezone.utc)
    start = end - window

    agg = db.fetch_one(
        """
        SELECT
          COALESCE(SUM(r.energy_wh), 0)::numeric(14,3) AS total_energy_wh,
          COALESCE(SUM(r.cost), 0)::numeric(14,4) AS total_cost,
          COALESCE(AVG(r.power_w), 0)::numeric(14,3) AS avg_power_w,
          COALESCE(MAX(r.power_w), 0)::numeric(14,3) AS peak_power_w
        FROM readings r
        JOIN devices d ON d.id = r.device_id
        WHERE d.user_id = %s
          AND r.ts >= %s
          AND r.ts <= %s
        """,
        [str(user["id"]), start, end],
    ) or {"total_energy_wh": 0, "total_cost": 0, "avg_power_w": 0, "peak_power_w": 0}

    # Simple anomaly heuristic: mark readings > 2.5x avg_power_w as anomaly (cap results)
    avg_power = Decimal(str(agg["avg_power_w"]))
    threshold = avg_power * Decimal("2.5") if avg_power > 0 else Decimal("0")
    anomalies = []
    if threshold > 0:
        rows = db.fetch_all(
            """
            SELECT r.device_id, r.ts, r.power_w
            FROM readings r
            JOIN devices d ON d.id = r.device_id
            WHERE d.user_id = %s
              AND r.ts >= %s
              AND r.ts <= %s
              AND r.power_w > %s
            ORDER BY r.power_w DESC
            LIMIT 20
            """,
            [str(user["id"]), start, end, threshold],
        )
        anomalies = [{"device_id": str(r["device_id"]), "ts": r["ts"], "power_w": r["power_w"]} for r in rows]

    return AnalyticsInsightsResponse(
        range=range,
        total_energy_wh=Decimal(str(agg["total_energy_wh"])),
        total_cost=Decimal(str(agg["total_cost"])),
        avg_power_w=Decimal(str(agg["avg_power_w"])),
        peak_power_w=Decimal(str(agg["peak_power_w"])),
        anomalies=anomalies,
    )
