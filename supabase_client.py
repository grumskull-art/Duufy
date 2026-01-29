"""
Supabase Client - Simple HTTP-based (no build dependencies)
Free tier: 500MB database, 50k monthly users, unlimited API requests

Includes both sync and async variants for FastAPI compatibility.
Refactored to use a singleton httpx.AsyncClient for performance.
"""

import os
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

# --- Globals ---
ApiResponse = dict[str, Any]
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Singleton async client, initialized on app startup
_async_client: Optional[httpx.AsyncClient] = None


# --- Lifecycle Management for FastAPI ---

async def startup_client():
    """Initialize the async client."""
    global _async_client
    if _async_client is None:
        # Set a default timeout that is reasonable for external API calls, including AI
        timeout = httpx.Timeout(15.0, connect=5.0)
        _async_client = httpx.AsyncClient(timeout=timeout)


async def shutdown_client():
    """Gracefully close the async client."""
    global _async_client
    if _async_client:
        await _async_client.aclose()
        _async_client = None


def get_async_client() -> httpx.AsyncClient:
    """Get the singleton async client, raises error if not initialized."""
    if _async_client is None:
        raise RuntimeError("Async client not initialized. Call startup_client() first.")
    return _async_client


# --- Internal Helpers ---

def _headers(use_service_key: bool = False) -> dict[str, str]:
    """Get headers for Supabase API"""
    key = SUPABASE_SERVICE_KEY if use_service_key else SUPABASE_ANON_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _log_error(error_type: str, message: str, metadata: dict = None) -> None:
    """Log error to Supabase error_logs table (fire-and-forget)"""
    try:
        # Use a sync client for this fire-and-forget task to not block startup/shutdown
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/error_logs",
            headers=_headers(use_service_key=True),
            json={
                "error_type": error_type,
                "message": message,
                "metadata": metadata or {},
            },
            timeout=5,
        )
    except BaseException:
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

async def get_user_async(access_token: str) -> ApiResponse:
    """Async: Get user from access token"""
    try:
        client = get_async_client()
        headers = _headers()
        headers["Authorization"] = f"Bearer {access_token}"
        r = await client.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers)
        if r.status_code == 200:
            return {"success": True, "user": r.json()}
        return {"success": False, "error": "Invalid token"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def sign_in_async(email: str, password: str) -> ApiResponse:
    """Async: Sign in existing user"""
    try:
        client = get_async_client()
        r = await client.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers=_headers(),
            json={"email": email, "password": password},
        )
        data = r.json()
        if r.status_code == 200:
            return {
                "success": True,
                "user": data.get("user"),
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
            }
        return {"success": False, "error": data.get("error_description", data)}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def sign_up_async(
    email: str, password: str, user_metadata: Optional[dict] = None
) -> ApiResponse:
    """Async: Create new user"""
    try:
        client = get_async_client()
        r = await client.post(
            f"{SUPABASE_URL}/auth/v1/signup",
            headers=_headers(),
            json={
                "email": email,
                "password": password,
                "data": user_metadata or {},
            },
        )
        data = r.json()
        if r.status_code == 200:
            return {"success": True, "user": data.get("user"), "session": data}
        return {"success": False, "error": data.get("msg", data)}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Note: Sync auth functions are kept for now if they are used by any sync scripts.
# They will continue to create their own clients.

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


# ============ DATABASE - ASYNC (for FastAPI) ============

async def db_insert_async(
    table: str, data: dict, use_service_key: bool = False
) -> ApiResponse:
    """Async: Insert row into table"""
    try:
        client = get_async_client()
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_headers(use_service_key),
            json=data,
        )
        if r.status_code in [200, 201]:
            return {"success": True, "data": r.json()}
        return {"success": False, "error": r.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def db_select_async(
    table: str,
    columns: str = "*",
    filters: Optional[dict] = None,
    use_service_key: bool = False,
) -> ApiResponse:
    """Async: Select from table with optional filters"""
    try:
        client = get_async_client()
        url = f"{SUPABASE_URL}/rest/v1/{table}?select={columns}"
        if filters:
            for key, value in filters.items():
                url += f"&{key}=eq.{value}"
        
        r = await client.get(url, headers=_headers(use_service_key))
        if r.status_code == 200:
            return {"success": True, "data": r.json()}
        return {"success": False, "error": r.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def db_update_async(
    table: str,
    data: dict,
    match_column: str,
    match_value: Any,
    use_service_key: bool = False,
) -> ApiResponse:
    """Async: Update row(s) in table"""
    try:
        client = get_async_client()
        r = await client.patch(
            f"{SUPABASE_URL}/rest/v1/{table}?{match_column}=eq.{match_value}",
            headers=_headers(use_service_key),
            json=data,
        )
        if r.status_code == 200:
            return {"success": True, "data": r.json()}
        return {"success": False, "error": r.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def db_delete_async(
    table: str, match_column: str, match_value: Any, use_service_key: bool = False
) -> ApiResponse:
    """Async: Delete row(s) from table"""
    try:
        client = get_async_client()
        r = await client.delete(
            f"{SUPABASE_URL}/rest/v1/{table}?{match_column}=eq.{match_value}",
            headers=_headers(use_service_key),
        )
        if r.status_code in [200, 204]:
            return {"success": True}
        return {"success": False, "error": r.text}
    except Exception as e:
        return {"success": False, "error": str(e)}