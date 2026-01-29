"""
Duufy Analytics & Event Tracking
Track user behavior, bugs, and retention
"""

import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

# Storage files
DATA_DIR = Path(__file__).parent / "data"
EVENTS_FILE = DATA_DIR / "analytics_events.json"
USERS_FILE = DATA_DIR / "analytics_users.json"
ERRORS_FILE = DATA_DIR / "error_logs.json"
_MAX_FILE_BYTES = 10 * 1024 * 1024
_MAX_EVENTS = 5000
_MAX_ERRORS = 1000

_EVENTS_LOCK = asyncio.Lock()
_ERRORS_LOCK = asyncio.Lock()
_USERS_LOCK = asyncio.Lock()

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)


def _load_json(file_path: Path) -> dict:
    """Load JSON file or return empty dict"""
    if not file_path.exists():
        file_path.write_text(json.dumps({}))
    try:
        return json.loads(file_path.read_text())
    except BaseException:
        return {}


def _save_json(file_path: Path, data: dict):
    """Save dict to JSON file"""
    file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


async def _load_json_async(file_path: Path) -> dict:
    return await asyncio.to_thread(_load_json, file_path)


async def _save_json_async(file_path: Path, data: dict) -> None:
    await asyncio.to_thread(_save_json, file_path, data)


async def _rotate_if_needed(file_path: Path, data: dict, keep_count: int) -> dict:
    try:
        stat = await asyncio.to_thread(file_path.stat)
    except FileNotFoundError:
        return data

    if stat.st_size <= _MAX_FILE_BYTES:
        return data

    if not isinstance(data, dict) or keep_count <= 0:
        return {}

    items = list(data.items())
    items.sort(key=lambda item: item[1].get("timestamp", ""))
    return dict(items[-keep_count:])


def _schedule_async(coro) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return
    loop.create_task(coro)


def _get_user_hash(user_id: str) -> str:
    """Create anonymous hash of user ID for privacy"""
    return hashlib.sha256(user_id.encode()).hexdigest()[:16]


# ============ USER TRACKING ============


async def _track_user_signup_async(
    user_id: str, email: Optional[str] = None, metadata: Optional[Dict] = None
) -> None:
    """Track new user signup"""
    async with _USERS_LOCK:
        users = await _load_json_async(USERS_FILE)
        user_hash = _get_user_hash(user_id)

        users[user_hash] = {
            "user_id_hash": user_hash,
            "signup_date": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "email_domain": email.split("@")[1] if email else None,
            "status": "active",
            "metadata": metadata or {},
        }

        await _save_json_async(USERS_FILE, users)

    await track_event(user_id, "user_signup", metadata)


def track_user_signup(
    user_id: str, email: Optional[str] = None, metadata: Optional[Dict] = None
):
    _schedule_async(_track_user_signup_async(user_id, email, metadata))


async def _track_user_activity_async(user_id: str) -> None:
    """Update last active timestamp"""
    async with _USERS_LOCK:
        users = await _load_json_async(USERS_FILE)
        user_hash = _get_user_hash(user_id)

        if user_hash in users:
            users[user_hash]["last_active"] = datetime.now().isoformat()
            await _save_json_async(USERS_FILE, users)


def track_user_activity(user_id: str):
    _schedule_async(_track_user_activity_async(user_id))


async def _track_user_churn_async(user_id: str, reason: Optional[str] = None) -> None:
    """Track when user uninstalls/churns"""
    async with _USERS_LOCK:
        users = await _load_json_async(USERS_FILE)
        user_hash = _get_user_hash(user_id)

        if user_hash in users:
            users[user_hash]["status"] = "churned"
            users[user_hash]["churn_date"] = datetime.now().isoformat()
            users[user_hash]["churn_reason"] = reason
            await _save_json_async(USERS_FILE, users)

    await track_event(user_id, "user_churn", {"reason": reason})


def track_user_churn(user_id: str, reason: Optional[str] = None):
    _schedule_async(_track_user_churn_async(user_id, reason))


# ============ EVENT TRACKING ============


async def track_event(
    user_id: str, event_name: str, data: Optional[Dict[str, Any]] = None
):
    """Track any user event"""
    async with _EVENTS_LOCK:
        events = await _load_json_async(EVENTS_FILE)
        events = await _rotate_if_needed(EVENTS_FILE, events, _MAX_EVENTS)

        event_id = f"{datetime.now().timestamp()}-{event_name}"
        events[event_id] = {
            "user_hash": _get_user_hash(user_id),
            "event": event_name,
            "timestamp": datetime.now().isoformat(),
            "data": data or {},
        }

        await _save_json_async(EVENTS_FILE, events)


# ============ ERROR LOGGING ============


async def log_error(
    error_type: str,
    message: str,
    user_id: Optional[str] = None,
    stack_trace: Optional[str] = None,
    metadata: Optional[Dict] = None,
):
    """Log application errors"""
    async with _ERRORS_LOCK:
        errors = await _load_json_async(ERRORS_FILE)
        errors = await _rotate_if_needed(ERRORS_FILE, errors, _MAX_ERRORS)

        error_id = f"err-{datetime.now().timestamp()}"
        errors[error_id] = {
            "error_id": error_id,
            "type": error_type,
            "message": message,
            "user_hash": _get_user_hash(user_id) if user_id else None,
            "timestamp": datetime.now().isoformat(),
            "stack_trace": stack_trace,
            "metadata": metadata or {},
        }

        await _save_json_async(ERRORS_FILE, errors)

    if user_id:
        await track_event(
            user_id,
            "error_occurred",
            {
                "error_type": error_type,
                "error_message": message,
            },
        )


# ============ ANALYTICS QUERIES ============


def get_user_stats() -> Dict:
    """Get user statistics"""
    users = _load_json(USERS_FILE)

    total_users = len(users)
    active_users = sum(1 for u in users.values() if u.get("status") == "active")
    churned_users = sum(1 for u in users.values() if u.get("status") == "churned")

    # Calculate retention (active for 7+ days)
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    retained_users = sum(
        1
        for u in users.values()
        if u.get("status") == "active" and u.get("signup_date", "") < week_ago
    )

    # Recent signups (last 24h)
    day_ago = (datetime.now() - timedelta(days=1)).isoformat()
    recent_signups = sum(
        1 for u in users.values() if u.get("signup_date", "") > day_ago
    )

    return {
        "total_users": total_users,
        "active_users": active_users,
        "churned_users": churned_users,
        "churn_rate": round(
            (churned_users / total_users * 100) if total_users > 0 else 0, 2
        ),
        "retention_7day": retained_users,
        "signups_24h": recent_signups,
    }


def get_event_stats(days: int = 7) -> Dict:
    """Get event statistics for last N days"""
    events = _load_json(EVENTS_FILE)
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    recent_events = [e for e in events.values() if e.get("timestamp", "") > cutoff]

    # Count by event type
    event_counts = {}
    for event in recent_events:
        event_name = event.get("event", "unknown")
        event_counts[event_name] = event_counts.get(event_name, 0) + 1

    return {
        "total_events": len(recent_events),
        "period_days": days,
        "events_by_type": event_counts,
    }


def get_error_stats(days: int = 7) -> Dict:
    """Get error statistics for last N days"""
    errors = _load_json(ERRORS_FILE)
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    recent_errors = [e for e in errors.values() if e.get("timestamp", "") > cutoff]

    # Count by error type
    error_counts = {}
    for error in recent_errors:
        error_type = error.get("type", "unknown")
        error_counts[error_type] = error_counts.get(error_type, 0) + 1

    return {
        "total_errors": len(recent_errors),
        "period_days": days,
        "errors_by_type": error_counts,
        "recent_errors": recent_errors[-10:],  # Last 10 errors
    }


def get_churn_analysis() -> Dict:
    """Analyze why users are churning"""
    users = _load_json(USERS_FILE)
    churned = [u for u in users.values() if u.get("status") == "churned"]

    # Count churn reasons
    reasons = {}
    for user in churned:
        reason = user.get("churn_reason", "unknown")
        reasons[reason] = reasons.get(reason, 0) + 1

    # Calculate average time to churn
    churn_times = []
    for user in churned:
        if user.get("signup_date") and user.get("churn_date"):
            signup = datetime.fromisoformat(user["signup_date"])
            churn = datetime.fromisoformat(user["churn_date"])
            days = (churn - signup).days
            churn_times.append(days)

    avg_days_to_churn = round(sum(churn_times) / len(churn_times)) if churn_times else 0

    return {
        "total_churned": len(churned),
        "churn_reasons": reasons,
        "avg_days_to_churn": avg_days_to_churn,
    }


def get_full_analytics() -> Dict:
    """Get complete analytics dashboard data"""
    return {
        "overview": get_user_stats(),
        "events_7days": get_event_stats(7),
        "errors_7days": get_error_stats(7),
        "churn_analysis": get_churn_analysis(),
        "generated_at": datetime.now().isoformat(),
    }
