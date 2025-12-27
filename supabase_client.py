"""
Supabase Client - Simple HTTP-based (no build dependencies)
Free tier: 500MB database, 50k monthly users, unlimited API requests

Includes both sync and async variants for FastAPI compatibility.
"""
import os
import httpx
from typing import Any, Optional
from dotenv import load_dotenv

load_dotenv()

# Type alias for API responses
ApiResponse = dict[str, Any]

# Supabase credentials
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _headers(use_service_key: bool = False) -> dict[str, str]:
    """Get headers for Supabase API"""
    key = SUPABASE_SERVICE_KEY if use_service_key else SUPABASE_ANON_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def _log_error(error_type: str, message: str, metadata: dict = None) -> None:
    """Log error to Supabase error_logs table (fire-and-forget)"""
    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/error_logs",
            headers=_headers(use_service_key=True),
            json={
                "error_type": error_type,
                "message": message,
                "metadata": metadata or {}
            },
            timeout=5
        )
    except:
        pass  # Don't fail if logging fails


def check_connection() -> ApiResponse:
    """Test Supabase connection"""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return {"success": False, "error": "Supabase ikke konfigureret i .env"}
    
    try:
        r = httpx.get(f"{SUPABASE_URL}/rest/v1/", headers=_headers(), timeout=10)
        return {"success": True, "status": r.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============ AUTH (via GoTrue API) ============

def sign_up(email: str, password: str, user_metadata: Optional[dict] = None) -> ApiResponse:
    """Create new user"""
    try:
        r = httpx.post(
            f"{SUPABASE_URL}/auth/v1/signup",
            headers=_headers(),
            json={
                "email": email,
                "password": password,
                "data": user_metadata or {}
            },
            timeout=10
        )
        data = r.json()
        if r.status_code == 200:
            return {"success": True, "user": data.get("user"), "session": data}
        return {"success": False, "error": data.get("msg", data)}
    except Exception as e:
        _log_error("auth_signup", str(e), {"email": email})
        return {"success": False, "error": str(e)}


def sign_in(email: str, password: str) -> ApiResponse:
    """Sign in existing user"""
    try:
        r = httpx.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers=_headers(),
            json={"email": email, "password": password},
            timeout=10
        )
        data = r.json()
        if r.status_code == 200:
            return {
                "success": True,
                "user": data.get("user"),
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token")
            }
        return {"success": False, "error": data.get("error_description", data)}
    except Exception as e:
        _log_error("auth_signin", str(e), {"email": email})
        return {"success": False, "error": str(e)}


def get_user(access_token: str) -> ApiResponse:
    """Get user from access token"""
    try:
        headers = _headers()
        headers["Authorization"] = f"Bearer {access_token}"
        r = httpx.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers, timeout=10)
        if r.status_code == 200:
            return {"success": True, "user": r.json()}
        return {"success": False, "error": "Invalid token"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def reset_password(email: str) -> ApiResponse:
    """Send password reset email"""
    try:
        r = httpx.post(
            f"{SUPABASE_URL}/auth/v1/recover",
            headers=_headers(),
            json={"email": email},
            timeout=10
        )
        if r.status_code == 200:
            return {"success": True, "message": "Password reset email sent"}
        return {"success": False, "error": r.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============ DATABASE - SYNC (via PostgREST API) ============

def db_insert(table: str, data: dict, use_service_key: bool = False) -> ApiResponse:
    """Insert row into table"""
    try:
        r = httpx.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_headers(use_service_key),
            json=data,
            timeout=10
        )
        if r.status_code in [200, 201]:
            return {"success": True, "data": r.json()}
        return {"success": False, "error": r.text}
    except Exception as e:
        _log_error("db_insert", str(e), {"table": table})
        return {"success": False, "error": str(e)}


def db_select(table: str, columns: str = "*", filters: Optional[dict] = None, use_service_key: bool = False) -> ApiResponse:
    """Select from table with optional filters"""
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}?select={columns}"
        if filters:
            for key, value in filters.items():
                url += f"&{key}=eq.{value}"
        r = httpx.get(url, headers=_headers(use_service_key), timeout=10)
        if r.status_code == 200:
            return {"success": True, "data": r.json()}
        return {"success": False, "error": r.text}
    except Exception as e:
        _log_error("db_select", str(e), {"table": table})
        return {"success": False, "error": str(e)}


def db_update(table: str, data: dict, match_column: str, match_value: Any, use_service_key: bool = False) -> ApiResponse:
    """Update row(s) in table"""
    try:
        r = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/{table}?{match_column}=eq.{match_value}",
            headers=_headers(use_service_key),
            json=data,
            timeout=10
        )
        if r.status_code == 200:
            return {"success": True, "data": r.json()}
        return {"success": False, "error": r.text}
    except Exception as e:
        _log_error("db_update", str(e), {"table": table})
        return {"success": False, "error": str(e)}


def db_delete(table: str, match_column: str, match_value: Any, use_service_key: bool = False) -> ApiResponse:
    """Delete row(s) from table"""
    try:
        r = httpx.delete(
            f"{SUPABASE_URL}/rest/v1/{table}?{match_column}=eq.{match_value}",
            headers=_headers(use_service_key),
            timeout=10
        )
        if r.status_code in [200, 204]:
            return {"success": True}
        return {"success": False, "error": r.text}
    except Exception as e:
        _log_error("db_delete", str(e), {"table": table})
        return {"success": False, "error": str(e)}


def db_upsert(table: str, data: dict, use_service_key: bool = False) -> ApiResponse:
    """Insert or update row"""
    headers = _headers(use_service_key)
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    try:
        r = httpx.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers,
            json=data,
            timeout=10
        )
        if r.status_code in [200, 201]:
            return {"success": True, "data": r.json()}
        return {"success": False, "error": r.text}
    except Exception as e:
        _log_error("db_upsert", str(e), {"table": table})
        return {"success": False, "error": str(e)}


# ============ DATABASE - ASYNC (for FastAPI) ============

async def db_insert_async(table: str, data: dict, use_service_key: bool = False) -> ApiResponse:
    """Async: Insert row into table"""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{SUPABASE_URL}/rest/v1/{table}",
                headers=_headers(use_service_key),
                json=data,
                timeout=10
            )
            if r.status_code in [200, 201]:
                return {"success": True, "data": r.json()}
            return {"success": False, "error": r.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def db_select_async(table: str, columns: str = "*", filters: Optional[dict] = None, use_service_key: bool = False) -> ApiResponse:
    """Async: Select from table with optional filters"""
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}?select={columns}"
        if filters:
            for key, value in filters.items():
                url += f"&{key}=eq.{value}"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=_headers(use_service_key), timeout=10)
            if r.status_code == 200:
                return {"success": True, "data": r.json()}
            return {"success": False, "error": r.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def db_update_async(table: str, data: dict, match_column: str, match_value: Any, use_service_key: bool = False) -> ApiResponse:
    """Async: Update row(s) in table"""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.patch(
                f"{SUPABASE_URL}/rest/v1/{table}?{match_column}=eq.{match_value}",
                headers=_headers(use_service_key),
                json=data,
                timeout=10
            )
            if r.status_code == 200:
                return {"success": True, "data": r.json()}
            return {"success": False, "error": r.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def db_delete_async(table: str, match_column: str, match_value: Any, use_service_key: bool = False) -> ApiResponse:
    """Async: Delete row(s) from table"""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.delete(
                f"{SUPABASE_URL}/rest/v1/{table}?{match_column}=eq.{match_value}",
                headers=_headers(use_service_key),
                timeout=10
            )
            if r.status_code in [200, 204]:
                return {"success": True}
            return {"success": False, "error": r.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def sign_in_async(email: str, password: str) -> ApiResponse:
    """Async: Sign in existing user"""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
                headers=_headers(),
                json={"email": email, "password": password},
                timeout=10
            )
            data = r.json()
            if r.status_code == 200:
                return {
                    "success": True,
                    "user": data.get("user"),
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token")
                }
            return {"success": False, "error": data.get("error_description", data)}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def sign_up_async(email: str, password: str, user_metadata: Optional[dict] = None) -> ApiResponse:
    """Async: Create new user"""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{SUPABASE_URL}/auth/v1/signup",
                headers=_headers(),
                json={
                    "email": email,
                    "password": password,
                    "data": user_metadata or {}
                },
                timeout=10
            )
            data = r.json()
            if r.status_code == 200:
                return {"success": True, "user": data.get("user"), "session": data}
            return {"success": False, "error": data.get("msg", data)}
    except Exception as e:
        return {"success": False, "error": str(e)}
