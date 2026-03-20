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

from ai_parser import smart_parse
from analytics import get_full_analytics, log_error, track_event
from analytics import track_user_activity as analytics_track_user_activity
from analytics import track_user_churn as analytics_track_user_churn
from analytics import track_user_signup as analytics_track_user_signup
from auth import verify_token
import database
from supabase_client import (SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY,
                             SUPABASE_URL, check_connection,
                             shutdown_client, startup_client)


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
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/app")
async def get_app():
    """Returner PWA app"""
    return FileResponse(Path(__file__).parent / "app.html")


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

    return result


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


@app.patch("/items/{item_id}")
async def patch_item(item_id: str, payload: dict = Body(...)):
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

    result = await database.patch_item(item_id, updates)
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
