"""
Case Authorization Service — Role-based and case-based access control.

Provides FastAPI dependencies for:
  - Verifying user access to a specific case
  - Retrieving the list of case IDs a user is authorized to access
  - Admin role bypass for full access

Uses the existing `case_investigators` table to determine per-case access.
The `investigator` column stores usernames (matching users.username).
"""

import logging
from typing import List, Optional
from fastapi import Depends, HTTPException, status

from services.auth_utils import get_current_user
from services.database import get_db

logger = logging.getLogger(__name__)


async def get_user_role(user_id: str) -> str:
    """Fetch the user's role from the database."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT role FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row["role"] if row else "investigator"
    finally:
        await db.close()


async def get_authorized_case_ids(
    current_user: dict = Depends(get_current_user),
) -> List[str]:
    """
    FastAPI Dependency: returns the list of case IDs this user can access.

    - Admins/supervisors see all cases.
    - Investigators see only cases where they are listed in case_investigators.
    - If the investigator has no assigned cases, returns an empty list.
    """
    user_id = current_user["user_id"]
    username = current_user["username"]

    role = await get_user_role(user_id)

    db = await get_db()
    try:
        if role in ("admin", "supervisor"):
            # Full access — return all case IDs
            cursor = await db.execute("SELECT case_id FROM cases")
            rows = await cursor.fetchall()
            return [row["case_id"] for row in rows]
        else:
            # Investigator — only assigned cases
            cursor = await db.execute(
                "SELECT case_id FROM case_investigators WHERE investigator = ?",
                (username,),
            )
            rows = await cursor.fetchall()
            case_ids = [row["case_id"] for row in rows]

            logger.debug(
                f"User {username} authorized for {len(case_ids)} cases"
            )
            return case_ids
    finally:
        await db.close()


async def verify_case_access(user_id: str, username: str, case_id: str) -> bool:
    """
    Check if a user has access to a specific case.

    Returns True if:
      - The user has admin/supervisor role, OR
      - The user is listed as an investigator on the case.
    """
    role = await get_user_role(user_id)

    if role in ("admin", "supervisor"):
        return True

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT 1 FROM case_investigators WHERE case_id = ? AND investigator = ?",
            (case_id, username),
        )
        return await cursor.fetchone() is not None
    finally:
        await db.close()


async def require_case_access(
    case_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    FastAPI Dependency: verifies the user can access the specified case.

    Raises 403 if access is denied, 404 if the case doesn't exist.
    Returns the current_user dict on success for downstream use.
    """
    # Verify case exists
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT case_id FROM cases WHERE case_id = ?", (case_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found",
            )
    finally:
        await db.close()

    # Verify access
    has_access = await verify_case_access(
        user_id=current_user["user_id"],
        username=current_user["username"],
        case_id=case_id,
    )

    if not has_access:
        logger.warning(
            f"Access denied: user={current_user['username']} case={case_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this case",
        )

    return current_user
