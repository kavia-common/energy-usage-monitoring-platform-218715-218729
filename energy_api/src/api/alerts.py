from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from src.api import db


def _op_compare(op: str, value: Decimal, threshold: Decimal) -> bool:
    if op == "gt":
        return value > threshold
    if op == "gte":
        return value >= threshold
    if op == "lt":
        return value < threshold
    if op == "lte":
        return value <= threshold
    if op == "eq":
        return value == threshold
    return False


def _metric_from_row(rule_metric: str, row: dict) -> Optional[Decimal]:
    mv = row.get(rule_metric)
    return mv if mv is not None else None


# PUBLIC_INTERFACE
def evaluate_rules_for_device(
    *,
    user_id: UUID,
    device_id: UUID,
    reading_ts: datetime,
) -> list[Dict[str, Any]]:
    """
    Evaluate enabled rules for a user's device, create alert_events rows when triggered,
    and write a notification_history entry (in_app) for each.

    Returns a list of triggered events (dict rows from alert_events).
    """
    rules = db.fetch_all(
        """
        SELECT *
        FROM alert_rules
        WHERE user_id = %s
          AND is_enabled = true
          AND (device_id IS NULL OR device_id = %s)
        """,
        [str(user_id), str(device_id)],
    )

    triggered: list[Dict[str, Any]] = []
    for rule in rules:
        # Cooldown check: don't trigger if last event within cooldown.
        last_evt = db.fetch_one(
            """
            SELECT triggered_at
            FROM alert_events
            WHERE rule_id = %s
            ORDER BY triggered_at DESC
            LIMIT 1
            """,
            [str(rule["id"])],
        )
        if last_evt and rule.get("cooldown_seconds", 0) > 0:
            cutoff = last_evt["triggered_at"] + timedelta(seconds=int(rule["cooldown_seconds"]))
            if reading_ts <= cutoff:
                continue

        metric = rule["metric"]

        if int(rule.get("window_seconds") or 0) > 0:
            # Window evaluation: average metric across window.
            start_ts = reading_ts - timedelta(seconds=int(rule["window_seconds"]))
            agg = db.fetch_one(
                f"""
                SELECT
                    AVG({metric})::numeric(14,4) AS metric_value
                FROM readings
                WHERE device_id = %s
                  AND ts >= %s
                  AND ts <= %s
                """,
                [str(device_id), start_ts, reading_ts],
            )
            metric_value = agg["metric_value"] if agg else None
        else:
            # Latest reading
            row = db.fetch_one(
                f"""
                SELECT {metric} AS metric_value
                FROM readings
                WHERE device_id = %s AND ts = %s
                """,
                [str(device_id), reading_ts],
            )
            metric_value = row["metric_value"] if row else None

        if metric_value is None:
            continue

        metric_value_dec = Decimal(str(metric_value))
        threshold = Decimal(str(rule["threshold"]))
        if not _op_compare(rule["operator"], metric_value_dec, threshold):
            continue

        msg = f"Rule '{rule['name']}' triggered: {metric} {rule['operator']} {threshold} (value={metric_value_dec})"
        evt = db.execute_returning(
            """
            INSERT INTO alert_events (rule_id, device_id, triggered_at, metric_value, message)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            [str(rule["id"]), str(device_id), reading_ts, metric_value_dec, msg],
        )
        if not evt:
            continue

        db.execute_returning(
            """
            INSERT INTO notification_history (event_id, user_id, channel, destination, status, sent_at, error)
            VALUES (%s, %s, 'in_app', NULL, 'sent', now(), NULL)
            RETURNING id
            """,
            [evt["id"], str(user_id)],
        )
        triggered.append(evt)

    return triggered
