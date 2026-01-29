from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from db import safe_read_json, safe_update_json, safe_write_json
from models import Item

app = FastAPI(title="Hey Lobs API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def read_root():
    """Returner HTML-siden"""
    return FileResponse(Path(__file__).parent / "index.html")

@app.get("/health")
async def health_check():
    return {"status": "OK", "time": datetime.utcnow().isoformat()}

# AI Parser endpoint
class ParseRequest(BaseModel):
    text: str
    force_ai: Optional[bool] = False

@app.post("/ai/parse")
async def parse_voice_input(request: ParseRequest):
    """
    Parser stemme-input til strukturerede varer.
    Bruger lokal regex først, Claude AI ved usikkerhed.
    
    result = smart_parse(request.text, request.force_ai)
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
    from database import add_item_to_groups
    try:
        if not item.name or not item.name.strip():
            return {"message": "Varenavn mangler", "item": item.dict()}
        
        # TilfÃ¸j til aktive grupper
        success = add_item_to_groups(item.dict())
        if success:
            return {"message": "Vare tilfÃ¸jet!", "item": item.dict()}
        else:
            return {"message": "VÃ¦lg mindst Ã©n aktiv gruppe", "item": item.dict()}
    except Exception as e:
        print(f"Error adding item: {e}")
        return {"message": "Serverfejl ved tilfÃ¸jelse", "item": item.dict()}

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
def send_invitation_route(request: InviteRequest):
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

    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Invitation til {invitation['group_name']} - Hey Lobs</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{ font-family: Arial, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; margin: 0; padding: 20px; }}
            .card {{ background: white; padding: 40px; border-radius: 20px; text-align: center; max-width: 400px; width: 100%; box-shadow: 0 10px 40px rgba(0,0,0,0.2); }}
            h1 {{ color: #667eea; margin-bottom: 5px; }}
            .subtitle {{ color: #666; margin-bottom: 20px; }}
            .group-name {{ font-size: 28px; color: #764ba2; margin: 20px 0; font-weight: bold; }}
            .inviter {{ color: #888; margin-bottom: 30px; }}
            input {{ width: 100%; padding: 15px; border: 2px solid #ddd; border-radius: 10px; font-size: 16px; margin-bottom: 15px; }}
            input:focus {{ border-color: #667eea; outline: none; }}
            button {{ width: 100%; padding: 15px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 10px; font-size: 18px; font-weight: bold; cursor: pointer; }}
            button:hover {{ opacity: 0.9; }}
            .error {{ color: #e74c3c; margin-top: 10px; }}
            .success {{ color: #27ae60; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>ðŸ›’ Hey Lobs</h1>
            <p class="subtitle">Du er inviteret til en indkÃ¸bsgruppe!</p>
            
            <p class="group-name">"{invitation['group_name']}"</p>
            <p class="inviter">Inviteret af {invitation['inviter_name']}</p>
            
            <form id="acceptForm">
                <input type="text" id="userName" placeholder="Dit navn" required minlength="2">
                <button type="submit">AcceptÃ©r invitation</button>
            </form>
            <p id="message"></p>
        </div>
        
        <script>
            document.getElementById('acceptForm').addEventListener('submit', async (e) => {{
                e.preventDefault();
                const name = document.getElementById('userName').value.trim();
                const msg = document.getElementById('message');
                
                if (name.length < 2) {{
                    msg.className = 'error';
                    msg.textContent = 'Navn skal vÃ¦re mindst 2 tegn';
                    return;
                }}
                
                try {{
                    const resp = await fetch('/invite/{token}/accept', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ name: name }})
                    }});
                    const data = await resp.json();
                    
                    if (data.success) {{
                        msg.className = 'success';
                        msg.textContent = data.message;
                        // Gem bruger og redirect
                        localStorage.setItem('currentUser', name);
                        localStorage.setItem('lastActiveGroup', data.group_id);
                        setTimeout(() => window.location.href = '/', 1500);
                    }} else {{
                        msg.className = 'error';
                        msg.textContent = data.message;
                    }}
                }} catch (err) {{
                    msg.className = 'error';
                    msg.textContent = 'Fejl ved accept af invitation';
                }}
            }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

class AcceptInviteRequest(BaseModel):
    name: str

@app.post("/invite/{token}/accept")
def accept_invitation_route(token: str, request: AcceptInviteRequest):
    """Accepterer en invitation"""
    from invitations import accept_invitation
    try:
        result = accept_invitation(token, request.name)
        return result
    except Exception as e:
        print(f"Error accepting invitation: {e}")
        return {"success": False, "message": "Fejl ved accept af invitation"}

@app.get("/group/{group_id}/invitations")
def get_group_invitations_route(group_id: str):
    """Henter ventende invitationer for en gruppe"""
    from invitations import get_pending_invitations
    try:
        pending = get_pending_invitations(group_id)
        return {"invitations": pending, "count": len(pending)}
    except Exception as e:
        print(f"Error getting invitations: {e}")
        return {"invitations": [], "count": 0}


