from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.api import db
from src.api.deps import get_current_user
from src.api.schemas import LoginRequest, RegisterRequest, TokenResponse, UserMeResponse
from src.api.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenResponse,
    summary="Register a new user",
    description="Creates a user account and returns a JWT access token.",
    operation_id="auth_register",
)
def register(payload: RegisterRequest) -> TokenResponse:
    """
    Register endpoint.

    Creates a new user record in Postgres and returns an access token.
    """
    existing = db.fetch_one("SELECT id FROM users WHERE email = %s", [payload.email.lower()])
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = db.execute_returning(
        """
        INSERT INTO users (email, password_hash, full_name)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        [payload.email.lower(), hash_password(payload.password), payload.full_name],
    )
    assert user is not None
    token = create_access_token(str(user["id"]))
    return TokenResponse(access_token=token)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login",
    description="Validates credentials and returns a JWT access token.",
    operation_id="auth_login",
)
def login(payload: LoginRequest) -> TokenResponse:
    """
    Login endpoint.

    Returns a JWT if the user's email/password are valid.
    """
    user = db.fetch_one(
        "SELECT id, password_hash, is_active FROM users WHERE email = %s",
        [payload.email.lower()],
    )
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(str(user["id"]))
    return TokenResponse(access_token=token)


@router.post(
    "/logout",
    summary="Logout",
    description="Stateless JWT logout; kept for UI compatibility.",
    operation_id="auth_logout",
)
def logout(_: dict = Depends(get_current_user)) -> dict:
    """
    Logout endpoint.

    JWTs are stateless; clients should delete the token locally.
    """
    return {"ok": True}


user_router = APIRouter(prefix="/user", tags=["user"])


@user_router.get(
    "/me",
    response_model=UserMeResponse,
    summary="Get current user",
    description="Returns the authenticated user's profile.",
    operation_id="user_me",
)
def me(user: dict = Depends(get_current_user)) -> UserMeResponse:
    """Return the current authenticated user."""
    return UserMeResponse(**user)
