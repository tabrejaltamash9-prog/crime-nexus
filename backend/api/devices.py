"""
Devices API Routes.
Handles registering new devices and revoking them.
"""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from models.schemas import DeviceRegister, DeviceResponse
from services.database import get_db
from services.auth_utils import get_current_user

router = APIRouter(prefix="/devices", tags=["Devices"])

@router.post("/register", response_model=DeviceResponse, status_code=201)
async def register_device(payload: DeviceRegister, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        # Fetch user's officer_id
        cursor = await db.execute("SELECT officer_id FROM users WHERE user_id = ?", (current_user["user_id"],))
        user_row = await cursor.fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")
        
        officer_id = user_row["officer_id"]
        now = datetime.now(timezone.utc).isoformat()
        device_id = str(uuid.uuid4())

        await db.execute(
            """INSERT INTO devices (device_id, user_id, device_name, signing_public_key, encryption_public_key, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (device_id, current_user["user_id"], payload.device_name, "", "", 'active', now)
        )
        
        await db.commit()

        return DeviceResponse(
            device_id=device_id,
            device_name=payload.device_name,
            status='active',
            created_at=now
        )
    finally:
        await db.close()

@router.post("/{device_id}/revoke")
async def revoke_device(device_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        # Ensure device belongs to user
        cursor = await db.execute("SELECT user_id, status FROM devices WHERE device_id = ?", (device_id,))
        device = await cursor.fetchone()
        
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        if device["user_id"] != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="Not authorized to revoke this device")
        if device["status"] == 'revoked':
            raise HTTPException(status_code=400, detail="Device is already revoked")

        now = datetime.now(timezone.utc).isoformat()

        # Revoke device
        await db.execute(
            "UPDATE devices SET status = 'revoked', revoked_at = ? WHERE device_id = ?",
            (now, device_id)
        )
        # Revoke associated certificates
        await db.execute(
            "UPDATE certificates SET status = 'revoked' WHERE device_id = ?",
            (device_id,)
        )
        
        await db.commit()
        return {"detail": f"Device {device_id} successfully revoked."}
    finally:
        await db.close()

@router.get("/", response_model=list[DeviceResponse])
async def list_devices(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT device_id, device_name, status, created_at FROM devices WHERE user_id = ?",
            (current_user["user_id"],)
        )
        rows = await cursor.fetchall()
        return [DeviceResponse(**dict(row)) for row in rows]
    finally:
        await db.close()
