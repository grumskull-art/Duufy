from fastapi import FastAPI, Body, BackgroundTasks, Request
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from models import Item
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel
from typing import Optional
from database import ensure_data_files
from db import safe_read_json, safe_update_json
import time
import traceback

class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="Duufy API",
    description="Do you often forget? Duufy don't - AI-powered shopping list",
    version="1.0.0",
    default_response_class=UTF8JSONResponse,
)


@app.on_event("startup")
async def startup_event():
    ensure_data_files()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Always return JSON for unhandled errors (prod-safe)."""
    # NOTE: Detailed stack traces are logged by middleware/uvicorn; do not leak internals to clients.
    return UTF8JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Internal Server Error"},
    )

# ========== AUTOMATIC ERROR TRACKING MIDDLEWARE ==========

@app.middleware("http")
async def track_errors_and_performance(request: Request, call_next):
    """Automatically log errors and slow requests"""
    from analytics import log_error, track_event
    
    start_time = time.time()
    
    try:
        response = await call_next(request)
        
        # Track slow requests (>3 seconds)
        duration = time.time() - start_time
        if duration > 3.0:
            log_error(
                error_type="PerformanceWarning",
                message=f"Slow request: {request.url.path} took {duration:.2f}s",
                metadata={
                    "path": request.url.path,
                    "method": request.method,
                    "duration": duration
                }
            )
        
        return response
        
    except Exception as e:
        # Automatically log all unhandled exceptions
        duration = time.time() - start_time
        
        log_error(
            error_type=type(e).__name__,
            message=str(e),
            stack_trace=traceback.format_exc(),
            metadata={
                "path": request.url.path,
                "method": request.method,
                "duration": duration
            }
        )
        
        # Re-raise the exception so FastAPI handles it
        raise

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== AUTHENTICATION ENDPOINTS ==========

class SignUpRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None

class SignInRequest(BaseModel):
    email: str
    password: str

@app.post("/auth/signup")
async def auth_signup(request: SignUpRequest):
    """Create new user account"""
    from supabase_client import sign_up
    from analytics import track_user_signup
    
    result = sign_up(request.email, request.password, {"name": request.name})
    
    if result["success"]:
        # Track signup in analytics
        if result.get("user"):
            track_user_signup(str(result["user"].id), request.email, {"name": request.name})
        
        return {
            "success": True,
            "message": "Konto oprettet! Tjek din email for at bekræfte.",
            "user_id": str(result["user"].id) if result.get("user") else None
        }
    else:
        return {"success": False, "error": result.get("error", "Signup fejlede")}

@app.post("/auth/signin")
async def auth_signin(request: SignInRequest):
    """Sign in existing user"""
    from supabase_client import sign_in
    from analytics import track_event
    
    result = sign_in(request.email, request.password)
    
    if result["success"]:
        track_event(str(result["user"].id), "user_signin")
        
        return {
            "success": True,
            "access_token": result["access_token"],
            "user": {
                "id": str(result["user"].id),
                "email": result["user"].email
            }
        }
    else:
        return {"success": False, "error": result.get("error", "Login fejlede")}

@app.post("/auth/signout")
async def auth_signout(authorization: Optional[str] = None):
    """Sign out user"""
    from supabase_client import sign_out
    
    if authorization:
        token = authorization.replace("Bearer ", "")
        result = sign_out(token)
        return result
    return {"success": True}

@app.get("/auth/me")
async def auth_me(authorization: str = None):
    """Get current user info"""
    from supabase_client import get_user
    
    if not authorization:
        return {"success": False, "error": "No token provided"}
    
    token = authorization.replace("Bearer ", "")
    result = get_user(token)
    
    if result["success"]:
        return {
            "success": True,
            "user": {
                "id": str(result["user"].id),
                "email": result["user"].email
            }
        }
    return result

@app.post("/auth/reset-password")
async def auth_reset_password(email: str = Body(..., embed=True)):
    """Send password reset email"""
    from supabase_client import reset_password
    return reset_password(email)


@app.get("/")
async def read_root():
    """Returner HTML-siden"""
    return FileResponse(Path(__file__).parent / "index.html")

@app.get("/app")
async def get_app():
    """Returner PWA app"""
    return FileResponse(Path(__file__).parent / "app.html")

@app.get("/manifest.json")
async def get_manifest():
    """PWA Manifest"""
    return FileResponse(Path(__file__).parent / "manifest.json")

@app.get("/sw.js")
async def get_service_worker():
    """Service Worker"""
    from fastapi.responses import Response
    content = (Path(__file__).parent / "sw.js").read_text()
    return Response(content=content, media_type="application/javascript")

@app.get("/health")
async def health_check():
    return {"status": "OK", "time": datetime.utcnow().isoformat()}

# AI Parser endpoint
class ParseRequest(BaseModel):
    text: str
    force_ai: Optional[bool] = False
    text_alternatives: Optional[list[str]] = None  # Fra speech recognition med multiple alternatives

@app.post("/ai/parse")
async def parse_voice_input(request: ParseRequest):
    """
    Parser stemme-input til strukturerede varer.
    Bruger lokal regex først, Claude AI ved usikkerhed.
    Prøver text_alternatives hvis hovedtekst fejler.
    """
    from ai_parser import smart_parse
    
    # Prøv hovedtekst først
    result = smart_parse(request.text, request.force_ai)
    
    # Hvis dårligt resultat og vi har alternativer, prøv dem
    if request.text_alternatives and (not result["items"] or result["confidence"] == "low"):
        for alt_text in request.text_alternatives[1:]:  # Skip første (det er hovedtekst)
            alt_result = smart_parse(alt_text, request.force_ai)
            if alt_result["items"] and alt_result["confidence"] == "high":
                result = alt_result
                result["used_alternative"] = alt_text
                break
    
    return result

# GRUPPE endpoints
@app.post("/group/{group_name}")
async def create_group_route(group_name: str, owner_id: str):
    from database import create_group
    try:
        if not owner_id or not owner_id.strip():
            return {"message": "Fejl: Ugyldigt ejernavn", "status": "error"}
        
        if not group_name or not group_name.strip():
            return {"message": "Fejl: Gruppenavn mangler", "status": "error"}
        
        if len(group_name.strip()) < 2:
            return {"message": "Fejl: Gruppenavn skal vÃ¦re mindst 2 tegn", "status": "error"}
        
        group_id = create_group(group_name, owner_id)
        return {"message": f"Gruppe '{group_name}' oprettet!", "group_id": group_id, "status": "success"}
    except Exception as e:
        print(f"Error creating group: {e}")
        return {"message": "Serverfejl ved oprettelse", "status": "error"}

@app.get("/groups")
async def get_groups_route():
    from database import get_groups, get_active_groups
    try:
        groups = get_groups()
        active = get_active_groups()
        return {"groups": groups, "active_groups": active}
    except Exception as e:
        print(f"Error getting groups: {e}")
        return {"groups": [], "active_groups": []}

# MEDLEMMER endpoints
@app.post("/group/{group_id}/member/{member_name}")
async def add_member_route(group_id: str, member_name: str):
    from database import add_member_to_group
    try:
        if not member_name or not member_name.strip():
            return {"message": "Medlemsnavn mangler", "status": "error"}
        
        if len(member_name.strip()) < 2:
            return {"message": "Navn skal vÃ¦re mindst 2 tegn", "status": "error"}
        
        success = add_member_to_group(group_id, member_name)
        if success:
            return {"message": f"{member_name} tilfÃ¸jet!", "status": "success"}
        else:
            return {"message": f"{member_name} er allerede medlem", "status": "info"}
    except Exception as e:
        print(f"Error adding member: {e}")
        return {"message": "Serverfejl ved tilfÃ¸jelse", "status": "error"}

@app.get("/group/{group_id}/members")
async def get_members_route(group_id: str):
    from database import get_group_members, get_group_owner
    try:
        members = get_group_members(group_id)
        owner = get_group_owner(group_id)
        return {"members": members, "count": len(members), "owner": owner}
    except Exception as e:
        print(f"Error getting members: {e}")
        return {"members": [], "count": 0, "owner": None}

@app.delete("/group/{group_id}/member/{member_name}")
async def remove_member_route(group_id: str, member_name: str, owner_check: str = "Grums"):
    from database import remove_member_from_group, get_group_owner
    try:
        group_owner = get_group_owner(group_id)
        # owner_check kommer fra frontend som den bruger der forsÃ¸ger at slette
        if group_owner != owner_check:
            return {"message": "Kun gruppeejer kan slette medlemmer", "status": "error"}
        
        success = remove_member_from_group(group_id, member_name)
        if success:
            return {"message": f"{member_name} fjernet!", "status": "success"}
        else:
            return {"message": "Fejl ved fjernelse", "status": "error"}
    except Exception as e:
        print(f"Error removing member: {e}")
        return {"message": "Fejl ved fjernelse", "status": "error"}

# AKTIVE GRUPPER endpoints
@app.post("/active-groups")
async def set_active_groups_route(group_ids: list = Body(...)):
    from database import set_active_groups
    try:
        if len(group_ids) > 3:
            return {"message": "Max 3 aktive grupper tilladt", "status": "error"}
        
        success = set_active_groups(group_ids)
        if success:
            return {"message": f"{len(group_ids)} gruppe(r) aktiveret!", "status": "success"}
        else:
            return {"message": "Fejl ved aktivering", "status": "error"}
    except Exception as e:
        print(f"Error setting active groups: {e}")
        return {"message": "Fejl", "status": "error"}

@app.get("/active-groups")
async def get_active_groups_route():
    from database import get_active_groups
    try:
        active = get_active_groups()
        return {"active_groups": active}
    except Exception as e:
        print(f"Error getting active groups: {e}")
        return {"active_groups": []}

@app.delete("/group/{group_id}")
async def delete_group_route(group_id: str):
    from database import delete_group, set_active_groups, get_active_groups
    try:
        success = delete_group(group_id)
        if success:
            # Fjern fra aktive grupper automatisk
            active = get_active_groups()
            set_active_groups(active)
            return {"message": "Gruppe slettet!", "status": "success"}
        else:
            return {"message": "Gruppe ikke fundet", "status": "error"}
    except Exception as e:
        print(f"Error deleting group: {e}")
        return {"message": "Fejl ved sletning", "status": "error"}

# VARER endpoints
@app.post("/add_item")
async def add_item_route(item: Item):
    from database import get_active_groups, load_items, save_items
    try:
        if not item.name or not item.name.strip():
            return {"message": "Varenavn mangler", "item": item.dict()}

        active = get_active_groups()
        if not active:
            return {"message": "VÇŸ¶Ýlg mindst ÇŸ¶¸n aktiv gruppe", "item": item.dict()}

        items = load_items()
        timestamp = datetime.utcnow().isoformat()
        for gid in active:
            items.append(
                {
                    "name": item.name,
                    "quantity": item.quantity,
                    "added_by": item.added_by,
                    "timestamp": timestamp,
                    "group_id": gid,
                }
            )
        save_items(items)

        return {"message": "Vare tilfÇŸ¶÷jet!", "item": item.dict()}
    except Exception as e:
        print(f"Error adding item: {e}")
        return {"message": "Serverfejl ved tilfÇŸ¶÷jelse", "item": item.dict()}

@app.get("/items")
async def get_items_flat_route():
    from database import get_active_groups, load_items
    try:
        active = get_active_groups()
        if not active:
            return {
                "items": [],
                "groups": [],
                "last_updated": datetime.utcnow().isoformat(),
            }

        items = load_items()
        merged = [item for item in items if item.get("group_id") in active]

        return {
            "items": merged,
            "groups": active,
            "last_updated": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        print(f"Error getting items: {e}")
        return {
            "items": [],
            "groups": [],
            "last_updated": datetime.utcnow().isoformat(),
        }

@app.get("/group/{group_id}/items")
async def get_items_route(group_id: str):
    from database import get_group_items
    try:
        items = get_group_items(group_id)
        return {"items": items, "last_updated": datetime.utcnow().isoformat()}
    except Exception as e:
        print(f"Error getting items: {e}")
        return {"items": [], "last_updated": datetime.utcnow().isoformat()}

@app.delete("/group/{group_id}/item/{item_name}")
async def delete_item_route(group_id: str, item_name: str):
    from database import delete_item_from_group
    try:
        success = delete_item_from_group(group_id, item_name)
        if success:
            return {"message": "Vare slettet!", "status": "success"}
        else:
            return {"message": "Vare ikke fundet", "status": "error"}
    except Exception as e:
        print(f"Error deleting item: {e}")
        return {"message": "Serverfejl ved sletning", "status": "error"}

@app.patch("/group/{group_id}/item/{item_name}/quantity")
async def update_item_quantity_route(group_id: str, item_name: str, quantity: str = Body(..., embed=True)):
    from database import update_item_quantity
    try:
        success = update_item_quantity(group_id, item_name, quantity)
        if success:
            return {"message": "MÃ¦ngde opdateret!", "status": "success"}
        else:
            return {"message": "Vare ikke fundet", "status": "error"}
    except Exception as e:
        print(f"Error updating quantity: {e}")
        return {"message": "Serverfejl ved opdatering", "status": "error"}


# ========== INVITATION ENDPOINTS ==========

class InviteRequest(BaseModel):
    email: str
    group_id: str
    group_name: str
    inviter_name: str

@app.post("/invite/send")
async def send_invitation_route(request: InviteRequest):
    """Sender en email-invitation til en bruger"""
    from invitations import create_invitation
    from fastapi import Request
    try:
        # Brug ngrok URL hvis tilgÃ¦ngelig, ellers localhost
        base_url = "https://unsophomoric-nila-collaterally.ngrok-free.dev"
        
        result = create_invitation(
            group_id=request.group_id,
            group_name=request.group_name,
            inviter_name=request.inviter_name,
            email=request.email,
            base_url=base_url
        )
        return result
    except Exception as e:
        print(f"Error sending invitation: {e}")
        return {"success": False, "message": "Fejl ved afsendelse af invitation"}

@app.get("/invite/{token}")
async def get_invitation_page(token: str):
    """Viser invitation-siden"""
    from invitations import get_invitation
    from fastapi.responses import HTMLResponse
    
    invitation = get_invitation(token)
    
    
    # Return invitation template with data
    template_path = Path(__file__).parent / "templates" / "invitation.html"
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # Simple template substitution
    html = html.replace('{{ inviter_name }}', invitation['inviter_name'])
    html = html.replace('{{ group_name }}', invitation['group_name'])
    html = html.replace('{{ token }}', token)
    
    return HTMLResponse(content=html)

class AcceptInviteRequest(BaseModel):
    name: str

@app.post("/invite/{token}/accept")
async def accept_invitation_route(token: str, request: AcceptInviteRequest):
    """Accepterer en invitation"""
    from invitations import accept_invitation
    try:
        result = accept_invitation(token, request.name)
        return result
    except Exception as e:
        print(f"Error accepting invitation: {e}")
        return {"success": False, "message": "Fejl ved accept af invitation"}

@app.get("/group/{group_id}/invitations")
async def get_group_invitations_route(group_id: str):
    """Henter ventende invitationer for en gruppe"""
    from invitations import get_pending_invitations
    try:
        pending = get_pending_invitations(group_id)
        return {"invitations": pending, "count": len(pending)}
    except Exception as e:
        print(f"Error getting invitations: {e}")
        return {"invitations": [], "count": 0}


# ========== SIGNUP / ONBOARDING ENDPOINT ==========

@app.get("/signup")
async def signup_page():
    """Generel signup/onboarding side for nye brugere"""
    from fastapi.responses import HTMLResponse
    
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
    from analytics import track_event, track_user_activity
    try:
        track_event(user_id, event, data)
        track_user_activity(user_id)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/analytics/signup")
async def track_signup(
    user_id: str = Body(...),
    email: Optional[str] = Body(None),
    metadata: Optional[dict] = Body(None)
):
    """Track new user signup"""
    from analytics import track_user_signup
    try:
        track_user_signup(user_id, email, metadata)
        return {"success": True, "message": "Signup tracked"}
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
    from analytics import log_error
    try:
        log_error(error_type, message, user_id, stack_trace, metadata)
        return {"success": True, "message": "Error logged"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/analytics/churn")
async def track_user_churn(
    user_id: str = Body(...),
    reason: Optional[str] = Body(None)
):
    """Track user uninstall/churn"""
    from analytics import track_user_churn
    try:
        track_user_churn(user_id, reason)
        return {"success": True, "message": "Churn tracked"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/admin/analytics")
async def get_analytics_dashboard():
    """Get complete analytics dashboard (ADMIN ONLY)"""
    from analytics import get_full_analytics
    from fastapi.responses import HTMLResponse
    
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
                {"".join(f'<div class="stat-row"><span class="stat-label">{event}</span><span class="stat-value">{count}</span></div>' 
                         for event, count in data['events_7days']['events_by_type'].items())}
            </div>
            
            <div class="section">
                <h2>❌ Errors (Last 7 Days)</h2>
                <div class="stat-row">
                    <span class="stat-label">Total Errors</span>
                    <span class="stat-value">{data['errors_7days']['total_errors']}</span>
                </div>
                {"".join(f'<div class="stat-row"><span class="stat-label">{error_type}</span><span class="stat-value">{count}</span></div>' 
                         for error_type, count in data['errors_7days']['errors_by_type'].items())}
                
                <h3 style="margin-top: 30px; margin-bottom: 15px; color: #666; font-size: 16px;">Recent Errors:</h3>
                {"".join(f'''<div class="error-item">
                    <div class="error-type">{error['type']}</div>
                    <div class="error-message">{error['message']}</div>
                    <div class="error-time">{error['timestamp'][:19].replace('T', ' ')}</div>
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
                {"".join(f'<div class="stat-row"><span class="stat-label">{reason}</span><span class="stat-value">{count}</span></div>' 
                         for reason, count in data['churn_analysis']['churn_reasons'].items())}
            </div>
            
            <button class="refresh-btn" onclick="location.reload()">🔄 Refresh Data</button>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html)
    except Exception as e:
        return {"error": str(e)}

@app.get("/admin/analytics/json")
async def get_analytics_json():
    """Get analytics data as JSON (ADMIN ONLY)"""
    from analytics import get_full_analytics
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
    from analytics import log_error, track_event
    
    try:
        # Log as error
        log_error(
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
        )
        
        # Also track as event
        track_event(report.user_id, "problem_reported", {
            "type": report.problem_type,
            "screen": report.screen
        })
        
        return {
            "success": True,
            "message": "Tak for din feedback! Vi kigger på det.",
            "support_id": f"DUF-{int(time.time())}"
        }
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
    from analytics import track_event, log_error
    
    try:
        if not was_correct:
            # Log as parsing error
            log_error(
                error_type="ParsingError",
                message=f"User reported incorrect parsing: '{input_text}'",
                user_id=user_id,
                metadata={
                    "input": input_text,
                    "output": parsed_items,
                    "user_feedback": "incorrect"
                }
            )
        
        track_event(user_id, "parse_feedback", {
            "was_correct": was_correct,
            "input_length": len(input_text),
            "items_count": len(parsed_items)
        })
        
        return {"success": True, "message": "Feedback modtaget"}
    except Exception as e:
        return {"success": False, "error": str(e)}
