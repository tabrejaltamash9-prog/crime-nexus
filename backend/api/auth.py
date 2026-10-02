"""
Authentication API Routes.
Handles user signup, login, OTP verification, and multi-step registration.
"""

import uuid
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm

from models.schemas import RegisterInit, RegisterFinalize, UserResponse, Token, OTPRequest, OTPVerify, ProfileUpdate
from services.database import get_db
from services.auth_utils import get_password_hash, verify_password, create_access_token, get_current_user
from services.email_service import generate_otp, send_otp_email
from services.storage_service import store_avatar

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/send-otp")
async def send_otp(payload: OTPRequest):
    print(f"DEBUG: Received POST request for send-otp for email: {payload.email}")
    db = await get_db()
    try:
        # Check if email is already registered
        cursor = await db.execute("SELECT user_id FROM users WHERE email = ?", (payload.email,))
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")

        otp = generate_otp()
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()

        await db.execute(
            "INSERT OR REPLACE INTO otp_codes (email, otp, expires_at, attempts) VALUES (?, ?, ?, ?)",
            (payload.email, otp, expires_at, 0)
        )
        await db.commit()

        success = send_otp_email(payload.email, otp)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to send OTP email")
            
        return {"detail": "OTP sent successfully"}
    finally:
        await db.close()

@router.post("/verify-otp")
async def verify_otp(payload: OTPVerify):
    db = await get_db()
    try:
        cursor = await db.execute("SELECT otp, expires_at, attempts FROM otp_codes WHERE email = ?", (payload.email,))
        record = await cursor.fetchone()
        
        if not record:
            raise HTTPException(status_code=400, detail="OTP not requested or expired")
            
        if record["attempts"] >= 5:
            await db.execute("DELETE FROM otp_codes WHERE email = ?", (payload.email,))
            await db.commit()
            raise HTTPException(status_code=400, detail="Too many failed attempts. Request a new OTP.")
            
        if record["otp"] != payload.otp:
            await db.execute("UPDATE otp_codes SET attempts = attempts + 1 WHERE email = ?", (payload.email,))
            await db.commit()
            raise HTTPException(status_code=400, detail="Invalid OTP")
            
        expires_at = datetime.fromisoformat(record["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            await db.execute("DELETE FROM otp_codes WHERE email = ?", (payload.email,))
            await db.commit()
            raise HTTPException(status_code=400, detail="OTP has expired")
            
        return {"detail": "OTP verified successfully. Proceed to finalize registration."}
    finally:
        await db.close()

def generate_officer_id():
    return f"IO-{datetime.now().year}-{secrets.randbelow(999999):06d}"

@router.post("/register", response_model=UserResponse, status_code=201)
async def register(payload: RegisterFinalize):
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    db = await get_db()
    try:
        # Verify OTP again during finalization to prevent bypass
        cursor = await db.execute("SELECT otp, expires_at FROM otp_codes WHERE email = ?", (payload.email,))
        record = await cursor.fetchone()
        if not record or record["otp"] != payload.otp:
            raise HTTPException(status_code=400, detail="Invalid or missing OTP")
            
        expires_at = datetime.fromisoformat(record["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(status_code=400, detail="OTP has expired")

        # Check unique username
        cursor = await db.execute("SELECT user_id FROM users WHERE username = ?", (payload.username,))
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Username already taken")

        # Check unique email (just in case)
        cursor = await db.execute("SELECT user_id FROM users WHERE email = ?", (payload.email,))
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")

        # Create user
        user_id = str(uuid.uuid4())
        officer_id = generate_officer_id()
        hashed_password = get_password_hash(payload.password)
        now = datetime.now(timezone.utc).isoformat()
        role = "investigator"

        await db.execute(
            """INSERT INTO users (user_id, officer_id, username, email, name, phone, password_hash, signing_pin_verifier, role, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, officer_id, payload.username, payload.email, payload.name, payload.phone, hashed_password, "", role, 'active', now)
        )
        
        # Create Device
        device_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO devices (device_id, user_id, device_name, signing_public_key, encryption_public_key, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (device_id, user_id, payload.device_name, "", "", 'active', now)
        )
        
        # Clean up OTP
        await db.execute("DELETE FROM otp_codes WHERE email = ?", (payload.email,))
        
        await db.commit()

        return UserResponse(
            user_id=user_id,
            officer_id=officer_id,
            username=payload.username,
            email=payload.email,
            name=payload.name,
            phone=payload.phone,
            created_at=now,
            status='active',
            role=role
        )
    finally:
        await db.close()

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT user_id, username, password_hash FROM users WHERE username = ?",
            (form_data.username,)
        )
        user = await cursor.fetchone()
        
        if not user or not verify_password(form_data.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token = create_access_token(data={"sub": user["username"]})
        return Token(access_token=access_token, token_type="bearer")
    finally:
        await db.close()

@router.get("/me", response_model=dict)
async def get_me(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT officer_id, created_at, name, phone, profile_picture_url, status, role FROM users WHERE user_id = ?",
            (current_user["user_id"],)
        )
        row = await cursor.fetchone()
        officer_id = row["officer_id"] if row else ""
        created_at = row["created_at"] if row else ""
        name = row["name"] if row else None
        phone = row["phone"] if row else None
        profile_picture_url = row["profile_picture_url"] if row else None
        status_val = row["status"] if row else "active"
        role = row["role"] if row else "investigator"

        cursor = await db.execute(
            "SELECT device_id FROM devices WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (current_user["user_id"],)
        )
        device_row = await cursor.fetchone()
        device_id = device_row["device_id"] if device_row else None
            
    finally:
        await db.close()
        
    return {
        "userId": current_user["user_id"],
        "officerId": officer_id,
        "username": current_user["username"],
        "email": current_user["email"],
        "name": name,
        "phone": phone,
        "profilePictureUrl": profile_picture_url,
        "createdAt": created_at,
        "status": status_val,
        "deviceId": device_id
    }

@router.put("/profile", response_model=UserResponse)
async def update_profile(payload: ProfileUpdate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET name = ?, phone = ? WHERE user_id = ?",
            (payload.name, payload.phone, current_user["user_id"])
        )
        await db.commit()
    finally:
        await db.close()
    
    return await get_me(current_user)

@router.post("/avatar", response_model=UserResponse)
async def update_avatar(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    file_bytes = await file.read()
    avatar_url = await store_avatar(
        user_id=current_user["user_id"],
        file_bytes=file_bytes,
        original_filename=file.filename or "avatar.png",
        mime_type=file.content_type or "image/png"
    )
    
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET profile_picture_url = ? WHERE user_id = ?",
            (avatar_url, current_user["user_id"])
        )
        await db.commit()
    finally:
        await db.close()
        
    return await get_me(current_user)

@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    return {"detail": "Successfully logged out"}
