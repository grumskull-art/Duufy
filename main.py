import asyncio
import os
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from html import escape
from typing import Any, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               Response)
from pydantic import BaseModel

from ai_parser import local_parse, smart_parse
from analytics import get_full_analytics, log_error, track_event
from analytics import track_user_activity as analytics_track_user_activity
from analytics import track_user_churn as analytics_track_user_churn
from analytics import track_user_signup as analytics_track_user_signup
from auth import verify_token
import database
from supabase_client import (SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY,
                             SUPABASE_URL, check_connection, delete_user_async,
                             get_user_async, shutdown_client,
                             sign_in_async, sign_up_async,
                             startup_client)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Always prepare local JSON data files for dev/runtime safety.
    await database.ensure_data_files()

    # Supabase is optional in local/dev environments.
    app.state.supabase_enabled = all(
        [SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY]
    )

    # Fail fast if supabase backend selected but env vars missing
    storage_backend = os.getenv("DUUFY_STORAGE", "").strip().lower()
    if storage_backend == "supabase" and not app.state.supabase_enabled:
        raise RuntimeError(
            "DUUFY_STORAGE=supabase requires SUPABASE_URL, SUPABASE_ANON_KEY, "
            "and SUPABASE_SERVICE_ROLE_KEY to be set in environment."
        )

    if app.state.supabase_enabled:
        await startup_client()
    else:
        print("WARN: Supabase env vars mangler, kører i lokal/dev mode.")

    yield
    if app.state.supabase_enabled:
        await shutdown_client()


app = FastAPI(
    title="Duufy API",
    description="Do you often forget? Duufy don't - AI-powered shopping list",
    version="1.0.0",
    default_response_class=JSONResponse,
    lifespan=lifespan,
)


RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
INVITE_FROM_EMAIL = os.getenv(
    "DUUFY_INVITE_FROM_EMAIL", "Duufy <onboarding@resend.dev>"
).strip()
PUBLIC_APP_URL = os.getenv("DUUFY_PUBLIC_APP_URL", "").strip()


async def _ensure_active_group(client_id: str = "default") -> list[str]:
    active_group_ids = await database.get_active_groups(client_id)
    if active_group_ids:
        return active_group_ids

    groups = await database.get_groups()
    if groups:
        first_group_id = groups[0].get("id")
        if first_group_id:
            await database.set_active_groups([first_group_id], client_id)
            return [first_group_id]

    default_group_id = await database.create_group("Min liste", "")
    await database.set_active_groups([default_group_id], client_id)
    return [default_group_id]


def _get_client_id(request: Request) -> str:
    client_id = (request.headers.get("X-Duufy-Client-Id", "") or "").strip()
    if not client_id:
        return "default"
    return client_id[:120]


def _user_identifiers(user: dict) -> list[str]:
    values: list[str] = []
    for key in ("id", "email"):
        value = str(user.get(key, "") or "").strip()
        if value:
            values.append(value)
    return values


def _primary_member_key(user: dict) -> str:
    email = str(user.get("email", "") or "").strip()
    if email:
        return email
    return str(user.get("id", "") or "").strip()


async def _get_accessible_groups_for_user(user: dict) -> list[dict[str, Any]]:
    return await database.get_accessible_groups(_user_identifiers(user))


async def _get_scoped_active_groups(
    request: Request, user: dict, ensure_one: bool = False
) -> tuple[list[str], list[dict[str, Any]]]:
    client_id = _get_client_id(request)
    accessible_groups = await _get_accessible_groups_for_user(user)
    accessible_ids = [str(group.get("id", "") or "").strip() for group in accessible_groups]
    accessible_ids = [group_id for group_id in accessible_ids if group_id]

    active_group_ids = await database.get_active_groups(client_id)
    filtered_group_ids = [group_id for group_id in active_group_ids if group_id in accessible_ids]

    if not filtered_group_ids and ensure_one and accessible_ids:
        filtered_group_ids = [accessible_ids[0]]

    if filtered_group_ids != active_group_ids:
        await database.set_active_groups(filtered_group_ids, client_id)

    return filtered_group_ids, accessible_groups


async def _ensure_accessible_active_group(request: Request, user: dict) -> list[str]:
    group_ids, accessible_groups = await _get_scoped_active_groups(
        request, user, ensure_one=True
    )
    if group_ids:
        return group_ids

    client_id = _get_client_id(request)
    owner_id = str(user.get("id", "") or "").strip()
    group_id = await database.create_group("Min liste", owner_id)
    member_key = _primary_member_key(user)
    if member_key:
        await database.add_member_to_group(group_id, member_key)
    await database.set_active_groups([group_id], client_id)
    return [group_id]


def _build_public_app_url(request: Request, invite_token: str = "") -> str:
    base_url = (PUBLIC_APP_URL or str(request.base_url)).rstrip("/")
    url = f"{base_url}/app"
    if invite_token:
        url += f"?invite={invite_token}"
    return url


async def _send_invitation_email(
    invite_email: str,
    group_name: str,
    inviter_name: str,
    invite_url: str,
) -> dict[str, Any]:
    if not RESEND_API_KEY:
        return {"sent": False, "reason": "missing_api_key"}

    try:
        import resend

        def _send() -> Any:
            resend.api_key = RESEND_API_KEY
            return resend.Emails.send(
                {
                    "from": INVITE_FROM_EMAIL,
                    "to": [invite_email],
                    "subject": f"{inviter_name} har inviteret dig til Duufy",
                    "html": (
                        f"<div style='font-family:Arial,sans-serif;line-height:1.6'>"
                        f"<h2>Invitation til {escape(group_name)}</h2>"
                        f"<p>{escape(inviter_name)} har inviteret dig til at dele "
                        f"indkøbsgruppen <strong>{escape(group_name)}</strong> i Duufy.</p>"
                        f"<p><a href='{escape(invite_url)}' "
                        f"style='display:inline-block;padding:12px 18px;border-radius:12px;"
                        f"background:#ef6f53;color:#fff;text-decoration:none;font-weight:700'>"
                        f"Åbn invitation</a></p>"
                        f"<p>Linket åbner appen, hvor du kan logge ind og acceptere gruppen.</p>"
                        f"</div>"
                    ),
                }
            )

        result = await asyncio.to_thread(_send)
        return {"sent": True, "result": result}
    except Exception as exc:
        return {"sent": False, "error": str(exc)}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Always return JSON for unhandled errors (prod-safe)."""
    # NOTE: Detailed stack traces are logged by middleware/uvicorn; do not
    # leak internals to clients.
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal Server Error"}},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    code = None
    message = None
    if isinstance(detail, dict):
        error = detail.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message")
        else:
            code = detail.get("code")
            message = detail.get("message")
    elif isinstance(detail, str):
        message = detail

    if not code:
        code = {
            400: "BAD_REQUEST",
            404: "NOT_FOUND",
            409: "CONFLICT",
            422: "INVALID_INPUT",
            500: "INTERNAL_ERROR",
        }.get(exc.status_code, "ERROR")
    if not message:
        message = exc.detail if isinstance(
            exc.detail, str) else "Request failed"

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message}},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "INVALID_INPUT",
                "message": "Invalid input",
            }
        },
    )

# ========== AUTOMATIC ERROR TRACKING MIDDLEWARE ==========


@app.middleware("http")
async def block_drive_paths(request: Request, call_next):
    path = request.url.path
    if ":" in path or "\\" in path or path.startswith("/.."):
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Not found"},
        )
    return await call_next(request)


@app.middleware("http")
async def track_errors_and_performance(request: Request, call_next):
    """Automatically log errors and slow requests"""
    start_time = time.time()

    try:
        response = await call_next(request)

        # Track slow requests (>3 seconds)
        duration = time.time() - start_time
        if duration > 3.0:
            asyncio.create_task(
                log_error(
                    error_type="PerformanceWarning",
                    message=(
                        f"Slow request: {request.url.path} took {duration:.2f}s"
                    ),
                    metadata={
                        "path": request.url.path,
                        "method": request.method,
                        "duration": duration,
                    },
                )
            )

        return response

    except HTTPException:
        raise
    except Exception as e:
        # Automatically log all unhandled exceptions
        duration = time.time() - start_time

        asyncio.create_task(log_error(
            error_type=type(e).__name__,
            message=str(e),
            stack_trace=traceback.format_exc(),
            metadata={
                "path": request.url.path,
                "method": request.method,
                "duration": duration
            }
        ))

        # Re-raise the exception so FastAPI handles it
        raise

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip() for origin in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:3000").split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "DELETE",
        "PATCH",
        "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization"],
)


@app.get("/")
async def read_root():
    """Returner HTML-siden"""
    index_path = Path(__file__).parent / "index.html"
    if not index_path.exists():
        index_path = Path(__file__).parent / "app.html"
    if not index_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Frontend file not found"},
        )
    return FileResponse(
        index_path,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/app")
async def get_app():
    """Returner PWA app"""
    return FileResponse(
        Path(__file__).parent / "app.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/manifest.json")
async def get_manifest():
    """PWA Manifest"""
    return FileResponse(
        Path(__file__).parent / "manifest.json",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/icon-192.png")
async def get_icon_192():
    icon_path = Path(__file__).parent / "icon-192.png"
    if not icon_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Icon file not found"},
        )
    return FileResponse(icon_path, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/icon-512.png")
async def get_icon_512():
    icon_path = Path(__file__).parent / "icon-512.png"
    if not icon_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Icon file not found"},
        )
    return FileResponse(icon_path, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/sw.js")
async def get_service_worker():
    """Service Worker"""
    content = (Path(__file__).parent / "sw.js").read_text()
    return Response(content=content, media_type="application/javascript")


@app.get("/health")
async def health_check():
    """Perform a live health check of the service and its dependencies."""
    if not getattr(app.state, "supabase_enabled", False):
        return {
            "status": "degraded",
            "services": {
                "database": {
                    "status": "disabled",
                    "details": "Supabase not configured in environment",
                }
            },
            "time": datetime.utcnow().isoformat(),
        }

    # Check Supabase connection (run sync function in thread to avoid blocking)
    supabase_status = await asyncio.to_thread(check_connection)
    if not supabase_status.get("success"):
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unavailable",
                "service": "database",
                "error": supabase_status.get("error"),
            },
        )

    return {
        "status": "ok",
        "services": {
            "database": {
                "status": "ok",
                "details": supabase_status,
            }
        },
        "time": datetime.utcnow().isoformat(),
    }


@app.get("/version")
async def get_version():
    return {"version": "v1.1", "status": "ok"}


@app.get("/config")
async def get_config():
    """Return public Supabase config for frontend Realtime client."""
    return {
        "supabase_url": SUPABASE_URL or "",
        "supabase_anon_key": SUPABASE_ANON_KEY or "",
    }


@app.get("/groups")
async def list_groups(request: Request, user: dict = Depends(verify_token)):
    active_group_ids, groups = await _get_scoped_active_groups(
        request, user, ensure_one=True
    )
    return {"groups": groups, "active_groups": active_group_ids}


@app.post("/active-groups")
async def set_active_groups(
    request: Request, group_ids: list[str] = Body(...), user: dict = Depends(verify_token)
):
    client_id = _get_client_id(request)
    clean_ids = [group_id.strip() for group_id in group_ids if group_id and group_id.strip()]
    allowed_ids = {
        str(group.get("id", "") or "").strip()
        for group in await _get_accessible_groups_for_user(user)
        if str(group.get("id", "") or "").strip()
    }
    if any(group_id not in allowed_ids for group_id in clean_ids):
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "GROUP_ACCESS_DENIED",
                    "message": "You do not have access to one or more groups",
                }
            },
        )
    ok = await database.set_active_groups(clean_ids, client_id)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_ACTIVE_GROUPS",
                    "message": "Could not update active groups",
                }
            },
        )
    return {"success": True, "active_groups": clean_ids}


# ========== AUTH ENDPOINTS ==========


class SignUpRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


class SignInRequest(BaseModel):
    email: str
    password: str


class CreateGroupRequest(BaseModel):
    name: str
    owner_id: Optional[str] = None


class InviteRequest(BaseModel):
    email: str
    group_id: str


@app.post("/auth/signup")
async def auth_signup(req: SignUpRequest):
    metadata = {"name": req.name} if req.name else None
    result = await sign_up_async(req.email, req.password, metadata)
    if result.get("success"):
        return {"success": True}
    return JSONResponse(
        status_code=400,
        content={"success": False, "error": result.get("error", "Signup failed")},
    )


@app.post("/auth/signin")
async def auth_signin(req: SignInRequest):
    result = await sign_in_async(req.email, req.password)
    if result.get("success"):
        return {
            "success": True,
            "access_token": result["access_token"],
            "user": result.get("user"),
        }
    return JSONResponse(
        status_code=401,
        content={"success": False, "error": result.get("error", "Login failed")},
    )


@app.get("/auth/me")
async def auth_me(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "No token"},
        )
    token = auth_header[7:]
    result = await get_user_async(token)
    if result.get("success"):
        return {"success": True, "user": result["user"]}
    return JSONResponse(
        status_code=401,
        content={"success": False, "error": "Invalid token"},
    )


@app.post("/groups/create")
async def create_group_endpoint(
    request: Request, req: CreateGroupRequest, user: dict = Depends(verify_token)
):
    client_id = _get_client_id(request)
    group_name = req.name.strip()
    if not group_name:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_GROUP_NAME",
                    "message": "Group name is required",
                }
            },
        )
    owner_id = str(user.get("id", "") or "").strip() or req.owner_id or ""
    group_id = await database.create_group(group_name, owner_id)
    member_key = _primary_member_key(user)
    if member_key:
        await database.add_member_to_group(group_id, member_key)
    await database.set_active_groups([group_id], client_id)
    return {"success": True, "group_id": group_id}


@app.delete("/groups/{group_id}")
async def delete_group_endpoint(
    group_id: str, request: Request, user: dict = Depends(verify_token)
):
    client_id = _get_client_id(request)
    group_id = group_id.strip()
    if not group_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_GROUP_ID",
                    "message": "Group id is required",
                }
            },
        )

    groups = await database.get_groups()
    if not any(group.get("id") == group_id for group in groups):
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "GROUP_NOT_FOUND",
                    "message": "Group not found",
                }
            },
        )

    if not await database.user_owns_group(group_id, _user_identifiers(user)):
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "GROUP_DELETE_FORBIDDEN",
                    "message": "Only the group owner can delete this group",
                }
            },
        )

    deleted = await database.delete_group(group_id)
    if not deleted:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "DELETE_GROUP_FAILED",
                    "message": "Could not delete group",
                }
            },
        )

    remaining_groups = await _get_accessible_groups_for_user(user)
    existing_ids = [group.get("id", "") for group in remaining_groups if group.get("id")]
    active_group_ids = await database.get_active_groups(client_id)
    active_group_ids = [gid for gid in active_group_ids if gid and gid != group_id and gid in existing_ids]

    if not active_group_ids and existing_ids:
        active_group_ids = [existing_ids[0]]

    await database.set_active_groups(active_group_ids, client_id)
    return {
        "success": True,
        "deleted_group_id": group_id,
        "active_groups": active_group_ids,
    }


@app.post("/invite/send")
async def send_invitation(
    request: Request, payload: InviteRequest, user: dict = Depends(verify_token)
):
    group_id = payload.group_id.strip()
    invite_email = payload.email.strip().lower()
    if not group_id:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_GROUP_ID", "message": "Group id is required"}},
        )
    if "@" not in invite_email or "." not in invite_email:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_EMAIL", "message": "Email is invalid"}},
        )

    user_email = str(user.get("email", "") or "").strip().lower()
    if user_email and invite_email == user_email:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVITE_SELF_FORBIDDEN",
                    "message": "You are already in this account",
                }
            },
        )

    if not await database.user_has_group_access(group_id, _user_identifiers(user)):
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "GROUP_ACCESS_DENIED",
                    "message": "You do not have access to this group",
                }
            },
        )

    group = next(
        (entry for entry in await database.get_groups() if entry.get("id") == group_id),
        None,
    )
    if not group:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "GROUP_NOT_FOUND", "message": "Group not found"}},
        )

    members = [member.lower() for member in await database.get_group_members(group_id)]
    if invite_email in members:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "ALREADY_MEMBER",
                    "message": "This email is already a member of the group",
                }
            },
        )

    invitation = await database.create_invitation(
        group_id=group_id,
        group_name=str(group.get("name", "") or "Din gruppe").strip(),
        email=invite_email,
        inviter_email=user_email,
        inviter_id=str(user.get("id", "") or "").strip(),
    )
    invite_url = _build_public_app_url(request, invitation["token"])
    email_result = await _send_invitation_email(
        invite_email=invite_email,
        group_name=invitation["group_name"],
        inviter_name=str(user.get("email", "") or "En Duufy-bruger"),
        invite_url=invite_url,
    )
    return {
        "success": True,
        "email_sent": email_result.get("sent", False),
        "invite_url": invite_url,
        "invitation": invitation,
    }


@app.get("/group/{group_id}/invitations")
async def get_group_invitations(group_id: str, user: dict = Depends(verify_token)):
    if not await database.user_has_group_access(group_id, _user_identifiers(user)):
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "GROUP_ACCESS_DENIED",
                    "message": "You do not have access to this group",
                }
            },
        )
    invitations = await database.list_group_invitations(group_id)
    return {"invitations": invitations}


@app.get("/invite/{token}")
async def get_invitation(token: str):
    invitation = await database.get_invitation_by_token(token)
    if not invitation:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "INVITE_NOT_FOUND", "message": "Invitation not found"}},
        )
    return {"success": True, "invitation": invitation}


@app.post("/invite/{token}/accept")
async def accept_invitation(token: str, request: Request, user: dict = Depends(verify_token)):
    invitation = await database.get_invitation_by_token(token)
    if not invitation:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "INVITE_NOT_FOUND", "message": "Invitation not found"}},
        )
    if invitation.get("status") == "expired":
        raise HTTPException(
            status_code=410,
            detail={"error": {"code": "INVITE_EXPIRED", "message": "Invitation has expired"}},
        )

    user_email = str(user.get("email", "") or "").strip().lower()
    if not user_email or user_email != str(invitation.get("email", "") or "").strip().lower():
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "INVITE_EMAIL_MISMATCH",
                    "message": "This invitation belongs to another email address",
                }
            },
        )

    accepted = await database.accept_invitation(token, user_email)
    if not accepted:
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "INVITE_ACCEPT_FAILED", "message": "Could not accept invitation"}},
        )

    await database.set_active_groups([str(accepted.get("group_id", "") or "").strip()], _get_client_id(request))
    return {
        "success": True,
        "group_id": accepted.get("group_id"),
        "group_name": accepted.get("group_name"),
        "invitation": accepted,
    }


# AI Parser endpoint


class ParseRequest(BaseModel):
    text: str
    force_ai: Optional[bool] = False
    # Fra speech recognition med multiple alternatives
    text_alternatives: Optional[list[str]] = None


@app.post("/ai/parse")
async def parse_voice_input(request: ParseRequest, _: dict = Depends(verify_token)):
    """
    Parser stemme-input til strukturerede varer.
    Bruger lokal regex først, Claude AI ved usikkerhed.
    Prøver text_alternatives hvis hovedtekst fejler.
    """
    # Prøv hovedtekst først
    result = smart_parse(request.text, request.force_ai)
    if asyncio.iscoroutine(result):
        result = await result
    result = dict(result)

    # Hvis dårligt resultat og vi har alternativer, prøv dem
    if request.text_alternatives and (
            not result["items"] or result["confidence"] == "low"):
        all_texts = set([request.text] + (request.text_alternatives or []))
        results = []
        for text in all_texts:
            parsed = smart_parse(text, request.force_ai)
            if asyncio.iscoroutine(parsed):
                parsed = await parsed
            results.append(parsed)
        merged = {
            i["item"].strip().lower(): i
            for r in results
            for i in r.get("items", [])
        }
        result["items"] = list(merged.values())

    unique_items = []
    seen = set()
    for item in result.get("items", []):
        name = item["item"].strip().lower()
        if name not in seen:
            unique_items.append(item)
            seen.add(name)
    result["items"] = unique_items

    if not result["items"]:
        fallback_texts = [request.text] + (request.text_alternatives or [])
        fallback_items = []
        fallback_seen = set()

        for text in fallback_texts:
            for item in local_parse(text):
                name = str(item.get("item", "")).strip()
                if not name:
                    continue
                key = name.lower()
                if key in fallback_seen:
                    continue
                fallback_seen.add(key)
                fallback_items.append(
                    {
                        "item": key,
                        "name": key,
                        "quantity": str(item.get("quantity", "1")).strip() or "1",
                        "category": item.get("category", "andet"),
                        "warnings": [],
                    }
                )

        if fallback_items:
            result["items"] = fallback_items
            result["method"] = "local_fallback"
            result["confidence"] = "medium"

    return result


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


@app.patch("/items/{item_id}")
async def patch_item(
    item_id: str,
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(verify_token),
):
    client_id = _get_client_id(request)
    await _get_scoped_active_groups(request, user, ensure_one=False)
    updates = {k: v for k, v in payload.items() if k in {"name", "quantity"}}
    if not updates:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "EMPTY_PATCH",
                    "message": "No updatable fields provided",
                }
            },
        )

    result = await database.patch_item(item_id, updates, client_id)
    if result is not None:
        return {"item": result}

    raise HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": "ITEM_NOT_FOUND",
                "message": "Item not found in active groups",
            }
        },
    )


# ========== ITEM CRUD ENDPOINTS ==========


class AddItemRequest(BaseModel):
    item: str
    quantity: Optional[str] = None
    unit: Optional[str] = None
    category: Optional[str] = None


class ToggleItemRequest(BaseModel):
    name: Optional[str] = None
    item_id: Optional[str] = None


@app.get("/items")
async def list_items(request: Request, user: dict = Depends(verify_token)):
    """Get all items across active groups."""
    group_ids, _ = await _get_scoped_active_groups(request, user, ensure_one=True)
    all_items = []
    for gid in group_ids:
        items = await database.get_group_items(gid)
        all_items.extend(items)
    # Return flat array matching frontend expectations
    return [
        {
            "id": item.get("id", ""),
            "name": item.get("name", ""),
            "quantity": item.get("quantity", ""),
            "unit": item.get("unit", ""),
            "category": item.get("category", ""),
            "checked": item.get("checked", False),
            "image_url": item.get("image_url"),
            "created_at": item.get("created_at"),
        }
        for item in all_items
    ]


@app.post("/items")
async def add_item(
    request: Request, req: AddItemRequest, user: dict = Depends(verify_token)
):
    """Add an item to active groups."""
    client_id = _get_client_id(request)
    await _ensure_accessible_active_group(request, user)
    item_data = {
        "name": req.item.strip(),
        "quantity": req.quantity or "",
        "unit": req.unit,
        "category": req.category,
        "added_by": _primary_member_key(user),
    }
    result = await database.add_item_to_groups(item_data, client_id=client_id)
    if result:
        return {"success": True}
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Failed to add item"},
    )


@app.post("/items/toggle")
async def toggle_item(
    request: Request, req: ToggleItemRequest, user: dict = Depends(verify_token)
):
    """Toggle checked state for an item by id when possible."""
    client_id = _get_client_id(request)
    await _get_scoped_active_groups(request, user, ensure_one=False)
    toggled = await database.toggle_item(req.item_id, req.name, client_id)
    return {"success": toggled}


@app.delete("/items/id/{item_id}")
async def delete_item_by_id(
    item_id: str, request: Request, user: dict = Depends(verify_token)
):
    """Delete an item by id within active groups."""
    client_id = _get_client_id(request)
    await _get_scoped_active_groups(request, user, ensure_one=False)
    deleted = await database.delete_item_by_id(item_id, client_id)
    if deleted:
        return {"success": True}
    raise HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": "ITEM_NOT_FOUND",
                "message": "Item not found in active groups",
            }
        },
    )


@app.delete("/items/{item_name}")
async def delete_item_by_name(
    item_name: str, request: Request, user: dict = Depends(verify_token)
):
    """Delete an item by name from all active groups."""
    group_ids, _ = await _get_scoped_active_groups(request, user, ensure_one=False)
    for gid in group_ids:
        await database.delete_item_from_group(gid, item_name)
    return {"success": True}


@app.delete("/auth/account")
async def delete_account(user: dict = Depends(verify_token)):
    user_id = str(user.get("id", "")).strip()
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_USER",
                    "message": "Could not resolve current user",
                }
            },
        )

    result = await delete_user_async(user_id)
    if result.get("success"):
        return {"success": True}

    raise HTTPException(
        status_code=500,
        detail={
            "error": {
                "code": "DELETE_ACCOUNT_FAILED",
                "message": "Could not delete account",
            }
        },
    )


# ========== SIGNUP / ONBOARDING ENDPOINT ==========


@app.get("/signup")
async def signup_page():
    """Generel signup/onboarding side for nye brugere"""
    html = """
    <!DOCTYPE html>
    <html lang="da">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Duufy - Do you often forget? Duufy don't</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .container {
                background: white;
                border-radius: 20px;
                padding: 50px 40px;
                max-width: 500px;
                width: 100%;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                text-align: center;
            }
            .logo {
                font-size: 64px;
                margin-bottom: 20px;
                animation: float 3s ease-in-out infinite;
            }
            @keyframes float {
                0%, 100% { transform: translateY(0); }
                50% { transform: translateY(-10px); }
            }
            h1 {
                color: #667eea;
                font-size: 42px;
                margin-bottom: 10px;
                font-weight: 700;
            }
            .tagline {
                color: #666;
                font-size: 18px;
                margin-bottom: 30px;
                font-style: italic;
            }
            .description {
                color: #555;
                font-size: 16px;
                line-height: 1.6;
                margin-bottom: 40px;
            }
            .features {
                text-align: left;
                margin-bottom: 40px;
            }
            .feature {
                display: flex;
                align-items: center;
                margin-bottom: 15px;
                color: #444;
            }
            .feature-icon {
                font-size: 24px;
                margin-right: 12px;
                width: 30px;
            }
            .share-section {
                background: #f8f9fa;
                padding: 25px;
                border-radius: 12px;
                margin-top: 30px;
            }
            .share-title {
                font-size: 18px;
                font-weight: 600;
                color: #333;
                margin-bottom: 15px;
            }
            .share-url {
                background: white;
                padding: 12px;
                border-radius: 8px;
                border: 2px solid #e1e4e8;
                font-family: 'Courier New', monospace;
                font-size: 14px;
                color: #667eea;
                word-break: break-all;
                margin-bottom: 15px;
            }
            .copy-btn {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 12px 30px;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s;
            }
            .copy-btn:hover {
                transform: scale(1.05);
            }
            .copy-btn:active {
                transform: scale(0.95);
            }
            .footer {
                margin-top: 40px;
                color: #888;
                font-size: 14px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">🧠</div>
            <h1>Duufy</h1>
            <div class="tagline">Do you often forget? Duufy don't</div>

            <div class="description">
                Din smarte indkøbsliste der husker alt det, du glemmer.
                Brug stemmen til at tilføje varer, del lister med familien,
                og lad AI hjælpe dig med at holde styr på indkøbene.
            </div>

            <div class="features">
                <div class="feature">
                    <span class="feature-icon">🎤</span>
                    <span>Tal naturligt - "jeg skal bruge mælk og brød"</span>
                </div>
                <div class="feature">
                    <span class="feature-icon">🤖</span>
                    <span>AI forstår hvad du mener</span>
                </div>
                <div class="feature">
                    <span class="feature-icon">👨‍👩‍👧‍👦</span>
                    <span>Del lister med familien</span>
                </div>
                <div class="feature">
                    <span class="feature-icon">📸</span>
                    <span>Billeder på alle produkter</span>
                </div>
            </div>

            <div class="share-section">
                <div class="share-title">📤 Del Duufy med venner</div>
                <div class="share-url" id="shareUrl"></div>
                <button class="copy-btn" onclick="copyUrl()">
                    📋 Kopier Link
                </button>
            </div>

            <div class="footer">
                Kom i gang ved at downloade appen 🚀
            </div>
        </div>

        <script>
            // Set share URL
            const shareUrl = window.location.href;
            document.getElementById('shareUrl').textContent = shareUrl;

            function copyUrl() {
                navigator.clipboard.writeText(shareUrl).then(() => {
                    const btn = document.querySelector('.copy-btn');
                    btn.textContent = '✅ Kopieret!';
                    setTimeout(() => {
                        btn.textContent = '📋 Kopier Link';
                    }, 2000);
                });
            }
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html)


# ========== ANALYTICS ENDPOINTS ==========

@app.post("/analytics/track")
async def track_analytics_event(
    user_id: str = Body(...),
    event: str = Body(...),
    data: Optional[dict] = Body(None)
):
    """Track user event for analytics"""
    try:
        asyncio.create_task(track_event(user_id, event, data))
        analytics_track_user_activity(user_id)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/analytics/signup")
async def track_signup(
    user_id: str = Body(...),
    email: Optional[str] = Body(None),
    metadata: Optional[dict] = Body(None)
):
    """Track new user signup"""
    try:
        analytics_track_user_signup(user_id, email, metadata)
        return {"success": True, "message": "Signup tracked"}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/analytics/error")
async def log_app_error(
    error_type: str = Body(...),
    message: str = Body(...),
    user_id: Optional[str] = Body(None),
    stack_trace: Optional[str] = Body(None),
    metadata: Optional[dict] = Body(None)
):
    """Log application error"""
    try:
        asyncio.create_task(
            log_error(
                error_type,
                message,
                user_id,
                stack_trace,
                metadata))
        return {"success": True, "message": "Error logged"}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/analytics/churn")
async def track_user_churn(
    user_id: str = Body(...),
    reason: Optional[str] = Body(None)
):
    """Track user uninstall/churn"""
    try:
        analytics_track_user_churn(user_id, reason)
        return {"success": True, "message": "Churn tracked"}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/admin/analytics", dependencies=[Depends(verify_token)])
async def get_analytics_dashboard():
    """Get complete analytics dashboard (ADMIN ONLY)"""
    try:
        data = get_full_analytics()

        html = f"""
        <!DOCTYPE html>
        <html lang="da">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Duufy Analytics Dashboard</title>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: #f5f7fa;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    border-radius: 12px;
                    margin-bottom: 30px;
                }}
                .header h1 {{ font-size: 36px; margin-bottom: 10px; }}
                .header p {{ opacity: 0.9; font-size: 16px; }}
                .grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                .card {{
                    background: white;
                    padding: 25px;
                    border-radius: 12px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }}
                .card h3 {{
                    color: #667eea;
                    font-size: 14px;
                    text-transform: uppercase;
                    margin-bottom: 10px;
                    font-weight: 600;
                }}
                .card .value {{
                    font-size: 42px;
                    font-weight: 700;
                    color: #333;
                    margin-bottom: 5px;
                }}
                .card .label {{
                    color: #888;
                    font-size: 14px;
                }}
                .section {{
                    background: white;
                    padding: 30px;
                    border-radius: 12px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    margin-bottom: 20px;
                }}
                .section h2 {{
                    color: #333;
                    margin-bottom: 20px;
                    font-size: 24px;
                }}
                .stat-row {{
                    display: flex;
                    justify-content: space-between;
                    padding: 12px 0;
                    border-bottom: 1px solid #eee;
                }}
                .stat-row:last-child {{ border-bottom: none; }}
                .stat-label {{ color: #666; }}
                .stat-value {{ font-weight: 600; color: #333; }}
                .error-item {{
                    background: #fff5f5;
                    border-left: 4px solid #e53e3e;
                    padding: 15px;
                    margin-bottom: 10px;
                    border-radius: 4px;
                }}
                .error-type {{ font-weight: 600; color: #e53e3e; }}
                .error-message {{ color: #666; margin-top: 5px; font-size: 14px; }}
                .error-time {{ color: #999; font-size: 12px; margin-top: 5px; }}
                .refresh-btn {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 8px;
                    font-size: 16px;
                    font-weight: 600;
                    cursor: pointer;
                    margin-top: 20px;
                }}
                .refresh-btn:hover {{ opacity: 0.9; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🧠 Duufy Analytics</h1>
                <p>Real-time metrics, user behavior, and error tracking</p>
                <p style="margin-top: 10px; font-size: 14px; opacity: 0.8;">
                    Generated: {data['generated_at'][:19].replace('T', ' ')}
                </p>
            </div>
            
            <div class="grid">
                <div class="card">
                    <h3>Total Users</h3>
                    <div class="value">{data['overview']['total_users']}</div>
                    <div class="label">All time signups</div>
                </div>
                <div class="card">
                    <h3>Active Users</h3>
                    <div class="value">{data['overview']['active_users']}</div>
                    <div class="label">Currently active</div>
                </div>
                <div class="card">
                    <h3>Churn Rate</h3>
                    <div class="value">{data['overview']['churn_rate']}%</div>
                    <div class="label">{data['overview']['churned_users']} churned</div>
                </div>
                <div class="card">
                    <h3>24h Signups</h3>
                    <div class="value">{data['overview']['signups_24h']}</div>
                    <div class="label">Last 24 hours</div>
                </div>
            </div>
            
            <div class="section">
                <h2>📊 Events (Last 7 Days)</h2>
                <div class="stat-row">
                    <span class="stat-label">Total Events</span>
                    <span class="stat-value">{data['events_7days']['total_events']}</span>
                </div>
                {"".join(f'<div class="stat-row"><span class="stat-label">{escape(str(event))}</span><span class="stat-value">{escape(str(count))}</span></div>'
                         for event, count in data['events_7days']['events_by_type'].items())}
            </div>
            
            <div class="section">
                <h2>❌ Errors (Last 7 Days)</h2>
                <div class="stat-row">
                    <span class="stat-label">Total Errors</span>
                    <span class="stat-value">{data['errors_7days']['total_errors']}</span>
                </div>
                {"".join(f'<div class="stat-row"><span class="stat-label">{escape(str(error_type))}</span><span class="stat-value">{escape(str(count))}</span></div>'
                             for error_type, count in data['errors_7days']['errors_by_type'].items())}
                
                <h3 style="margin-top: 30px; margin-bottom: 15px; color: #666; font-size: 16px;">Recent Errors:</h3>
                {"".join(f'''<div class="error-item">
                    <div class="error-type">{escape(str(error['type']))}</div>
                    <div class="error-message">{escape(str(error['message']))}</div>
                    <div class="error-time">{escape(str(error['timestamp'][:19].replace('T', ' ')))}</div>
                </div>''' for error in data['errors_7days']['recent_errors'])}
            </div>
            
            <div class="section">
                <h2>📉 Churn Analysis</h2>
                <div class="stat-row">
                    <span class="stat-label">Total Churned Users</span>
                    <span class="stat-value">{data['churn_analysis']['total_churned']}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Avg Days to Churn</span>
                    <span class="stat-value">{data['churn_analysis']['avg_days_to_churn']}</span>
                </div>
                
                <h3 style="margin-top: 30px; margin-bottom: 15px; color: #666; font-size: 16px;">Churn Reasons:</h3>
                {"".join(f'<div class="stat-row"><span class="stat-label">{escape(str(reason))}</span><span class="stat-value">{escape(str(count))}</span></div>'
                                 for reason, count in data['churn_analysis']['churn_reasons'].items())}
            </div>

            <button class="refresh-btn" onclick="location.reload()">🔄 Refresh Data</button>
        </body>
        </html>
        """

        return HTMLResponse(content=html)
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.get("/admin/analytics/json", dependencies=[Depends(verify_token)])
async def get_analytics_json():
    """Get analytics data as JSON (ADMIN ONLY)"""
    return get_full_analytics()

# ========== USER PROBLEM REPORTING ==========


class ProblemReport(BaseModel):
    user_id: str
    problem_type: str  # "bug", "crash", "slow", "confusing", "other"
    description: str
    screen: Optional[str] = None  # Which screen/page
    expected_behavior: Optional[str] = None
    actual_behavior: Optional[str] = None
    metadata: Optional[dict] = None


@app.post("/report-problem")
async def report_problem(report: ProblemReport):
    """Let users report bugs and issues"""

    try:
        # Log as error
        asyncio.create_task(log_error(
            error_type=f"UserReport_{report.problem_type}",
            message=f"{report.description}",
            user_id=report.user_id,
            metadata={
                "problem_type": report.problem_type,
                "screen": report.screen,
                "expected": report.expected_behavior,
                "actual": report.actual_behavior,
                **(report.metadata or {})
            }
        ))

        # Also track as event
        asyncio.create_task(track_event(report.user_id, "problem_reported", {
            "type": report.problem_type,
            "screen": report.screen
        }))

        return {
            "success": True,
            "message": "Tak for din feedback! Vi kigger på det.",
            "support_id": f"DUF-{int(time.time())}"
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


# ========== AI PARSE RESULT VALIDATION ==========

@app.post("/validate-parse")
async def validate_parse_result(
    user_id: str = Body(...),
    input_text: str = Body(...),
    parsed_items: list = Body(...),
    was_correct: bool = Body(...)
):
    """Track if AI parsing was correct (user feedback)"""

    try:
        if not was_correct:
            # Log as parsing error
            asyncio.create_task(log_error(
                error_type="ParsingError",
                message=f"User reported incorrect parsing: '{input_text}'",
                user_id=user_id,
                metadata={
                    "input": input_text,
                    "output": parsed_items,
                    "user_feedback": "incorrect"
                }
            ))

        asyncio.create_task(track_event(user_id, "parse_feedback", {
            "was_correct": was_correct,
            "input_length": len(input_text),
            "items_count": len(parsed_items)
        }))

        return {"success": True, "message": "Feedback modtaget"}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
    )
