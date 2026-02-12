from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api import db
from src.api.deps import get_current_user
from src.api.schemas import (
    AlertRuleCreate,
    AlertRuleOut,
    AlertRuleUpdate,
    NotificationHistoryOut,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get(
    "",
    response_model=list[AlertRuleOut],
    summary="List alert rules",
    description="List alert rules for the current user.",
    operation_id="alerts_list",
)
def list_alerts(user: dict = Depends(get_current_user)) -> list[AlertRuleOut]:
    """List alert rules for current user."""
    rows = db.fetch_all(
        """
        SELECT *
        FROM alert_rules
        WHERE user_id = %s
        ORDER BY created_at DESC
        """,
        [str(user["id"])],
    )
    return [AlertRuleOut(**r) for r in rows]


@router.post(
    "",
    response_model=AlertRuleOut,
    summary="Create alert rule",
    description="Create a new alert rule.",
    operation_id="alerts_create",
)
def create_alert(payload: AlertRuleCreate, user: dict = Depends(get_current_user)) -> AlertRuleOut:
    """Create alert rule."""
    created = db.execute_returning(
        """
        INSERT INTO alert_rules (user_id, device_id, name, metric, operator, threshold, window_seconds, cooldown_seconds, is_enabled)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        [
            str(user["id"]),
            str(payload.device_id) if payload.device_id else None,
            payload.name,
            payload.metric,
            payload.operator,
            payload.threshold,
            payload.window_seconds,
            payload.cooldown_seconds,
            payload.is_enabled,
        ],
    )
    if not created:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Create failed")
    return AlertRuleOut(**created)


@router.put(
    "/{alert_id}",
    response_model=AlertRuleOut,
    summary="Update alert rule",
    description="Update an alert rule.",
    operation_id="alerts_update",
)
def update_alert(alert_id: UUID, patch: AlertRuleUpdate, user: dict = Depends(get_current_user)) -> AlertRuleOut:
    """Update rule."""
    existing = db.fetch_one(
        "SELECT * FROM alert_rules WHERE id = %s AND user_id = %s",
        [str(alert_id), str(user["id"])],
    )
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")

    fields = patch.model_dump(exclude_unset=True)
    if not fields:
        return AlertRuleOut(**existing)

    # Allow explicit null for device_id via patch.device_id = null in JSON.
    set_parts = []
    params = []
    for k, v in fields.items():
        set_parts.append(f"{k} = %s")
        params.append(str(v) if k == "device_id" and v is not None else v)

    params.extend([str(alert_id), str(user["id"])])
    updated = db.execute_returning(
        f"""
        UPDATE alert_rules
        SET {", ".join(set_parts)}, updated_at = now()
        WHERE id = %s AND user_id = %s
        RETURNING *
        """,
        params,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Update failed")
    return AlertRuleOut(**updated)


@router.delete(
    "/{alert_id}",
    summary="Delete alert rule",
    description="Delete an alert rule.",
    operation_id="alerts_delete",
)
def delete_alert(alert_id: UUID, user: dict = Depends(get_current_user)) -> dict:
    """Delete rule."""
    deleted = db.execute("DELETE FROM alert_rules WHERE id = %s AND user_id = %s", [str(alert_id), str(user["id"])])
    if deleted <= 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")
    return {"ok": True}


@router.get(
    "/notifications/history",
    response_model=list[NotificationHistoryOut],
    summary="Notification history",
    description="List notification history entries for the current user.",
    operation_id="alerts_notification_history",
)
def notification_history(
    limit: int = Query(default=50, ge=1, le=200, description="Max items to return"),
    user: dict = Depends(get_current_user),
) -> list[NotificationHistoryOut]:
    """List notification history for user."""
    rows = db.fetch_all(
        """
        SELECT *
        FROM notification_history
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        [str(user["id"]), limit],
    )
    return [NotificationHistoryOut(**r) for r in rows]
