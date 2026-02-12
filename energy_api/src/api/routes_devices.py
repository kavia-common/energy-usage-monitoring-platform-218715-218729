from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.api import db
from src.api.deps import get_current_user
from src.api.schemas import DeviceCreate, DeviceOut, DeviceUpdate

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get(
    "",
    response_model=list[DeviceOut],
    summary="List devices",
    description="List all devices owned by the current user.",
    operation_id="devices_list",
)
def list_devices(user: dict = Depends(get_current_user)) -> list[DeviceOut]:
    """List devices for the authenticated user."""
    rows = db.fetch_all(
        """
        SELECT *
        FROM devices
        WHERE user_id = %s
        ORDER BY created_at DESC
        """,
        [str(user["id"])],
    )
    return [DeviceOut(**r) for r in rows]


@router.post(
    "",
    response_model=DeviceOut,
    summary="Create device",
    description="Create a new device for the current user.",
    operation_id="devices_create",
)
def create_device(payload: DeviceCreate, user: dict = Depends(get_current_user)) -> DeviceOut:
    """Create a device."""
    created = db.execute_returning(
        """
        INSERT INTO devices (user_id, name, location, type, manufacturer, model, serial_number)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        [
            str(user["id"]),
            payload.name,
            payload.location,
            payload.type,
            payload.manufacturer,
            payload.model,
            payload.serial_number,
        ],
    )
    if not created:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Create failed")
    return DeviceOut(**created)


@router.put(
    "/{device_id}",
    response_model=DeviceOut,
    summary="Update device",
    description="Update an existing device owned by the current user.",
    operation_id="devices_update",
)
def update_device(device_id: UUID, patch: DeviceUpdate, user: dict = Depends(get_current_user)) -> DeviceOut:
    """Update a device."""
    existing = db.fetch_one(
        "SELECT * FROM devices WHERE id = %s AND user_id = %s",
        [str(device_id), str(user["id"])],
    )
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    fields = patch.model_dump(exclude_unset=True)
    if not fields:
        return DeviceOut(**existing)

    set_parts = []
    params = []
    for k, v in fields.items():
        set_parts.append(f"{k} = %s")
        params.append(v)

    params.extend([str(device_id), str(user["id"])])
    updated = db.execute_returning(
        f"""
        UPDATE devices
        SET {", ".join(set_parts)}, updated_at = now()
        WHERE id = %s AND user_id = %s
        RETURNING *
        """,
        params,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Update failed")
    return DeviceOut(**updated)


@router.delete(
    "/{device_id}",
    summary="Delete device",
    description="Delete a device owned by the current user.",
    operation_id="devices_delete",
)
def delete_device(device_id: UUID, user: dict = Depends(get_current_user)) -> dict:
    """Delete a device."""
    deleted = db.execute(
        "DELETE FROM devices WHERE id = %s AND user_id = %s",
        [str(device_id), str(user["id"])],
    )
    if deleted <= 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return {"ok": True}
