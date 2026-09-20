import psycopg
from fastapi import APIRouter, HTTPException, Request
from psycopg.errors import UniqueViolation
from pydantic import BaseModel
from werkzeug.security import check_password_hash, generate_password_hash

from ..config import get_settings
from .rate_limit import AuthRateLimiter


router = APIRouter(prefix="/api", tags=["auth"])
auth_rate_limiter = AuthRateLimiter()


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    confirm_password: str


def require_user(request: Request) -> int:
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Please log in again.")
    return int(user_id)


def rate_limit_auth(request: Request, action: str) -> None:
    client_host = request.client.host if request.client else "unknown"
    auth_rate_limiter.check(f"{action}:{client_host}")


def validate_password_policy(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")
    if not any(character.isdigit() for character in password):
        raise HTTPException(status_code=400, detail="Password must include at least one number.")
    if not any(character.isalpha() for character in password):
        raise HTTPException(status_code=400, detail="Password must include at least one letter.")


def require_admin(request: Request) -> int:
    user_id = require_user(request)
    role = get_user_role(user_id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access is required.")
    request.session["role"] = role
    return user_id


def get_user_role(user_id: int) -> str | None:
    with psycopg.connect(get_settings().database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT role FROM users WHERE id = %s;", (user_id,))
            row = cursor.fetchone()
            return row[0] if row else None


def get_user_by_username(username: str):
    with psycopg.connect(get_settings().database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, username, email, password_hash, role
                FROM users
                WHERE username = %s;
                """,
                (username,),
            )
            return cursor.fetchone()


def get_user_by_email(email: str):
    with psycopg.connect(get_settings().database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE email = %s;", (email,))
            return cursor.fetchone()


def create_user(username: str, email: str, password: str):
    password_hash = generate_password_hash(password)
    try:
        with psycopg.connect(get_settings().database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM users;")
                role = "admin" if cursor.fetchone()[0] == 0 else "user"
                cursor.execute(
                    """
                    INSERT INTO users (username, email, password_hash, role)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, username, email, role;
                    """,
                    (username, email, password_hash, role),
                )
                return cursor.fetchone()
    except UniqueViolation as error:
        raise HTTPException(status_code=409, detail="That username or email is already registered.") from error


@router.post("/register")
def register(data: RegisterRequest, request: Request):
    rate_limit_auth(request, "register")
    username = data.username.strip()
    email = data.email.strip().lower()

    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    if not data.password:
        raise HTTPException(status_code=400, detail="Password is required.")
    if data.password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")
    validate_password_policy(data.password)
    if get_user_by_username(username):
        raise HTTPException(status_code=409, detail="Username already exists.")
    if get_user_by_email(email):
        raise HTTPException(status_code=409, detail="Email already exists.")

    user = create_user(username, email, data.password)
    request.session["user_id"] = user[0]
    request.session["username"] = user[1]
    request.session["role"] = user[3]

    return {"message": "Registration successful.", "user": {"id": user[0], "username": user[1], "email": user[2], "role": user[3]}}


@router.post("/login")
def login(data: LoginRequest, request: Request):
    rate_limit_auth(request, "login")
    username = data.username.strip()
    if not username or not data.password:
        raise HTTPException(status_code=400, detail="Username and password are required.")

    user = get_user_by_username(username)
    if not user or not check_password_hash(user[3], data.password):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    request.session["user_id"] = user[0]
    request.session["username"] = user[1]
    request.session["role"] = user[4]

    return {"message": "Login successful.", "user": {"id": user[0], "username": user[1], "email": user[2], "role": user[4]}}


@router.get("/session")
def get_session(request: Request):
    user_id = request.session.get("user_id")
    username = request.session.get("username")
    if user_id is None:
        return {"logged_in": False, "user": None}
    role = get_user_role(int(user_id))
    if role is None:
        request.session.clear()
        return {"logged_in": False, "user": None}
    request.session["role"] = role
    return {"logged_in": True, "user": {"id": user_id, "username": username, "role": role}}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"message": "Logout successful."}
