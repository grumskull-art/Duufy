# ==================================================
# HEY LOBS - KOMPLET KODEBASE
# Genereret: 25. december 2025
# Total: 2676 linjer Python kode
# ==================================================

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict

import firebase_admin
from dotenv import load_dotenv
# ========== main.py (313 linjer) ==========
from fastapi import BackgroundTasks, Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from filelock import FileLock
from firebase_admin import messaging
from google.cloud import firestore
from pydantic import BaseModel, Field

from ai_parser import local_parse
from ai_parser import local_parse as old_parse
from ai_parser import smart_parse
from ai_parser import smart_parse as old_smart
from ai_parser_optimized import ParseResult
from ai_parser_optimized import local_parse
from ai_parser_optimized import local_parse as new_parse
from ai_parser_optimized import smart_parse as new_smart
from ai_parser_optimized import smart_parse_async
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
    text_alternatives: Optional[list[str]] = (
        None  # Fra speech recognition med multiple alternatives
    )


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
    if request.text_alternatives and (
        not result["items"] or result["confidence"] == "low"
    ):
        for alt_text in request.text_alternatives[
            1:
        ]:  # Skip første (det er hovedtekst)
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
            return {
                "message": "Fejl: Gruppenavn skal vÃ¦re mindst 2 tegn",
                "status": "error",
            }

        group_id = create_group(group_name, owner_id)
        return {
            "message": f"Gruppe '{group_name}' oprettet!",
            "group_id": group_id,
            "status": "success",
        }
    except Exception as e:
        print(f"Error creating group: {e}")
        return {"message": "Serverfejl ved oprettelse", "status": "error"}


@app.get("/groups")
async def get_groups_route():
    from database import get_active_groups, get_groups

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
async def remove_member_route(
    group_id: str, member_name: str, owner_check: str = "Grums"
):
    from database import get_group_owner, remove_member_from_group

    try:
        group_owner = get_group_owner(group_id)
        # owner_check kommer fra frontend som den bruger der forsÃ¸ger at
        # slette
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
            return {
                "message": f"{len(group_ids)} gruppe(r) aktiveret!",
                "status": "success",
            }
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
    from database import delete_group, get_active_groups, set_active_groups

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
async def update_item_quantity_route(
    group_id: str, item_name: str, quantity: str = Body(..., embed=True)
):
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
    from fastapi import Request

    from invitations import create_invitation

    try:
        # Brug ngrok URL hvis tilgÃ¦ngelig, ellers localhost
        base_url = "https://unsophomoric-nila-collaterally.ngrok-free.dev"

        result = create_invitation(
            group_id=request.group_id,
            group_name=request.group_name,
            inviter_name=request.inviter_name,
            email=request.email,
            base_url=base_url,
        )
        return result
    except Exception as e:
        print(f"Error sending invitation: {e}")
        return {"success": False, "message": "Fejl ved afsendelse af invitation"}


@app.get("/invite/{token}")
async def get_invitation_page(token: str):
    """Viser invitation-siden"""
    from fastapi.responses import HTMLResponse

    from invitations import get_invitation

    invitation = get_invitation(token)

    # Return invitation template with data
    template_path = Path(__file__).parent / "templates" / "invitation.html"
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Simple template substitution
    html = html.replace("{{ inviter_name }}", invitation["inviter_name"])
    html = html.replace("{{ group_name }}", invitation["group_name"])
    html = html.replace("{{ token }}", token)

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


# ========== database.py (230 linjer) ==========


# Firestore eller lokal JSON
db = None
USE_LOCAL_JSON = True  # Sæt til False når Firebase er klar
JSON_FILE = Path(__file__).parent / "data" / "groups.json"


def load_local_data():
    """Indlæs data fra lokal JSON-fil (thread-safe)"""
    return safe_read_json(JSON_FILE, {"groups": {}, "active_groups": []})


def save_local_data(data):
    """Gem data til lokal JSON-fil (thread-safe)"""
    safe_write_json(JSON_FILE, data)


def create_group(group_name: str, owner_id: str = "Grums"):
    """Opret ny gruppe"""
    if not USE_LOCAL_JSON:
        return None

    data = load_local_data()
    group_id = group_name.lower().replace(" ", "_")

    if group_id in data["groups"]:
        return group_id  # Allerede eksisterer

    data["groups"][group_id] = {
        "name": group_name,
        "owner_id": owner_id,
        "members": [owner_id],
        "items": [],
        "created": datetime.utcnow().isoformat(),
        "last_updated": datetime.utcnow().isoformat(),
    }
    save_local_data(data)
    return group_id


def get_groups():
    """Hent alle grupper"""
    if not USE_LOCAL_JSON:
        return []

    data = load_local_data()
    return [
        {
            "id": gid,
            "name": g["name"],
            "member_count": len(g.get("members", [])),
            "item_count": len(g.get("items", [])),
        }
        for gid, g in data["groups"].items()
    ]


def add_member_to_group(group_id: str, member_name: str):
    """Tilføj medlem til gruppe"""
    if not USE_LOCAL_JSON:
        return False

    data = load_local_data()

    if group_id not in data["groups"]:
        return False

    members = data["groups"][group_id].get("members", [])

    if member_name.lower() not in [m.lower() for m in members]:
        members.append(member_name)
        data["groups"][group_id]["members"] = members
        data["groups"][group_id]["last_updated"] = datetime.utcnow().isoformat()
        save_local_data(data)
        return True
    return False


def get_group_members(group_id: str):
    """Hent medlemmer fra gruppe"""
    if not USE_LOCAL_JSON:
        return []

    data = load_local_data()
    if group_id in data["groups"]:
        return data["groups"][group_id].get("members", [])
    return []


def get_group_owner(group_id: str):
    """Hent gruppeejer"""
    if not USE_LOCAL_JSON:
        return None

    data = load_local_data()
    if group_id in data["groups"]:
        return data["groups"][group_id].get("owner_id", None)
    return None


def set_active_groups(group_ids: list):
    """Sæt aktive grupper (max 3)"""
    if not USE_LOCAL_JSON or len(group_ids) > 3:
        return False

    data = load_local_data()
    data["active_groups"] = group_ids
    save_local_data(data)
    return True


def get_active_groups():
    """Hent aktive grupper"""
    if not USE_LOCAL_JSON:
        return []

    data = load_local_data()
    return data.get("active_groups", [])


def add_item_to_groups(item_data: dict, group_ids: list = None):
    """Tilføj vare til grupper (hvis ingen grupper, brug aktive)"""
    if not USE_LOCAL_JSON:
        return False

    data = load_local_data()
    target_groups = group_ids or data.get("active_groups", [])

    if not target_groups:
        return False

    item_data["timestamp"] = datetime.utcnow().isoformat()

    for group_id in target_groups:
        if group_id in data["groups"]:
            data["groups"][group_id]["items"].append(item_data)
            data["groups"][group_id]["last_updated"] = datetime.utcnow().isoformat()

    save_local_data(data)
    return True


def get_group_items(group_id: str):
    """Hent varer fra gruppe"""
    if not USE_LOCAL_JSON:
        return []

    data = load_local_data()
    if group_id in data["groups"]:
        return data["groups"][group_id].get("items", [])
    return []


def delete_item_from_group(group_id: str, item_name: str):
    """Slet vare fra gruppe - kun første match"""
    if not USE_LOCAL_JSON:
        return

    data = load_local_data()

    if group_id not in data["groups"]:
        return

    items = data["groups"][group_id].get("items", [])
    # Slet kun FØRSTE match, ikke alle
    for i, item in enumerate(items):
        if item.get("name", "").lower() == item_name.lower():
            items.pop(i)
            break  # Stop efter første match

    data["groups"][group_id]["items"] = items
    data["groups"][group_id]["last_updated"] = datetime.utcnow().isoformat()
    save_local_data(data)


def remove_member_from_group(group_id: str, member_name: str):
    """Fjern medlem fra gruppe"""
    if not USE_LOCAL_JSON:
        return False

    data = load_local_data()

    if group_id not in data["groups"]:
        return False

    members = data["groups"][group_id].get("members", [])
    data["groups"][group_id]["members"] = [
        m for m in members if m.lower() != member_name.lower()
    ]
    data["groups"][group_id]["last_updated"] = datetime.utcnow().isoformat()
    save_local_data(data)
    return True


def delete_group(group_id: str):
    """Slet en gruppe"""
    if not USE_LOCAL_JSON:
        return False

    data = load_local_data()

    if group_id not in data["groups"]:
        return False

    del data["groups"][group_id]

    # Fjern fra aktive grupper hvis den var der
    if group_id in data.get("active_groups", []):
        data["active_groups"].remove(group_id)

    save_local_data(data)
    return True


def update_item_quantity(group_id: str, item_name: str, new_quantity: str):
    """Opdater mængde på en vare"""
    if not USE_LOCAL_JSON:
        return False

    data = load_local_data()

    if group_id not in data["groups"]:
        return False

    items = data["groups"][group_id].get("items", [])
    updated = False

    for item in items:
        if item["name"].lower() == item_name.lower():
            item["quantity"] = new_quantity
            updated = True
            break

    if updated:
        data["groups"][group_id]["last_updated"] = datetime.utcnow().isoformat()
        save_local_data(data)
        return True

    return False


# ========== invitations.py (240 linjer) ==========
"""
Invitation system for Hey Lobs
Håndterer email-invitationer til grupper
"""


# Prøv at importere resend, men lad det fejle gracefully
try:
    import resend

    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False

# Load environment variables

load_dotenv()

DATA_DIR = Path(__file__).parent / "data"
INVITATIONS_FILE = DATA_DIR / "invitations.json"
USERS_FILE = DATA_DIR / "users.json"

# Resend API key
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")


def load_invitations():
    """Loader alle invitationer fra JSON-fil (thread-safe)"""
    return safe_read_json(INVITATIONS_FILE, {"invitations": {}})


def save_invitations(data):
    """Gemmer invitationer til JSON-fil (thread-safe)"""
    safe_write_json(INVITATIONS_FILE, data)


def load_users():
    """Loader alle brugere fra JSON-fil (thread-safe)"""
    return safe_read_json(USERS_FILE, {"users": {}})


def save_users(data):
    """Gemmer brugere til JSON-fil (thread-safe)"""
    safe_write_json(USERS_FILE, data)


def generate_invite_token():
    """Genererer en unik invitation-token"""
    return secrets.token_urlsafe(16)


def create_invitation(
    group_id: str, group_name: str, inviter_name: str, email: str, base_url: str
):
    """
    Opretter en invitation og sender email
    Returns: dict med status og token
    """
    token = generate_invite_token()

    data = load_invitations()

    # Tjek om email allerede er inviteret til denne gruppe
    for inv_token, inv in data["invitations"].items():
        if inv["email"].lower() == email.lower() and inv["group_id"] == group_id:
            if inv["status"] == "pending":
                return {
                    "success": False,
                    "message": f"{email} er allerede inviteret til denne gruppe",
                    "token": inv_token,
                }

    # Opret invitation
    invitation = {
        "token": token,
        "group_id": group_id,
        "group_name": group_name,
        "inviter_name": inviter_name,
        "email": email.lower(),
        "created": datetime.utcnow().isoformat(),
        "expires": (datetime.utcnow() + timedelta(days=7)).isoformat(),
        "status": "pending",  # pending, accepted, expired
    }

    data["invitations"][token] = invitation
    save_invitations(data)

    # Send email
    invite_url = f"{base_url}/invite/{token}"
    email_sent = send_invitation_email(email, inviter_name, group_name, invite_url)

    return {
        "success": True,
        "message": (
            f"Invitation sendt til {email}!"
            if email_sent
            else f"Invitation oprettet (email kunne ikke sendes)"
        ),
        "token": token,
        "invite_url": invite_url,
        "email_sent": email_sent,
    }


def send_invitation_email(
    to_email: str, inviter_name: str, group_name: str, invite_url: str
):
    """Sender invitation-email via Resend"""

    if not RESEND_AVAILABLE or not RESEND_API_KEY:
        print(f"Email ville være sendt til {to_email}: {invite_url}")
        return False

    try:
        resend.api_key = RESEND_API_KEY

        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #667eea; text-align: center;">🛒 Hey Lobs</h1>
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 15px; color: white; text-align: center;">
                <h2 style="margin: 0 0 10px 0;">Du er inviteret!</h2>
                <p style="margin: 0; font-size: 18px;">
                    <strong>{inviter_name}</strong> vil have dig med i indkøbsgruppen
                </p>
                <p style="font-size: 24px; margin: 15px 0;">
                    <strong>"{group_name}"</strong>
                </p>
            </div>
            <div style="text-align: center; margin-top: 25px;">
                <a href="{invite_url}"
                   style="display: inline-block;
                          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                          color: white;
                          padding: 15px 40px;
                          text-decoration: none;
                          border-radius: 25px;
                          font-size: 18px;
                          font-weight: bold;">
                    Acceptér invitation
                </a>
            </div>
            <p style="text-align: center; color: #666; margin-top: 20px; font-size: 14px;">
                Linket udløber om 7 dage
            </p>
        </div>
        """

        resend.Emails.send(
            {
                "from": "Hey Lobs <noreply@resend.dev>",
                "to": to_email,
                "subject": f"🛒 {inviter_name} inviterer dig til {group_name} - Hey Lobs",
                "html": html_content,
            }
        )

        return True

    except Exception as e:
        print(f"Email fejl: {e}")
        return False


def get_invitation(token: str):
    """Henter en invitation fra token"""
    data = load_invitations()
    invitation = data["invitations"].get(token)

    if not invitation:
        return None

    # Tjek om udløbet
    expires = datetime.fromisoformat(invitation["expires"])
    if datetime.utcnow() > expires:
        invitation["status"] = "expired"
        save_invitations(data)
        return None

    return invitation


def accept_invitation(token: str, user_name: str):
    """
    Accepterer en invitation og tilføjer bruger til gruppen
    """
    from database import add_member_to_group

    data = load_invitations()
    invitation = data["invitations"].get(token)

    if not invitation:
        return {"success": False, "message": "Invitation ikke fundet"}

    if invitation["status"] != "pending":
        return {
            "success": False,
            "message": "Invitation er allerede brugt eller udløbet",
        }

    # Tjek udløb
    expires = datetime.fromisoformat(invitation["expires"])
    if datetime.utcnow() > expires:
        invitation["status"] = "expired"
        save_invitations(data)
        return {"success": False, "message": "Invitation er udløbet"}

    # Tilføj bruger til gruppe
    success = add_member_to_group(invitation["group_id"], user_name)

    if success:
        # Marker invitation som accepteret
        invitation["status"] = "accepted"
        invitation["accepted_by"] = user_name
        invitation["accepted_at"] = datetime.utcnow().isoformat()
        save_invitations(data)

        # Opret/opdater bruger
        users_data = load_users()
        email = invitation["email"]
        if email not in users_data["users"]:
            users_data["users"][email] = {
                "name": user_name,
                "email": email,
                "created": datetime.utcnow().isoformat(),
                "groups": [invitation["group_id"]],
            }
        else:
            if invitation["group_id"] not in users_data["users"][email].get(
                "groups", []
            ):
                users_data["users"][email].setdefault("groups", []).append(
                    invitation["group_id"]
                )
        save_users(users_data)

        return {
            "success": True,
            "message": f"Velkommen til {invitation['group_name']}!",
            "group_id": invitation["group_id"],
            "group_name": invitation["group_name"],
        }
    else:
        return {
            "success": False,
            "message": "Kunne ikke tilføje til gruppen - du er måske allerede medlem",
        }


def get_pending_invitations(group_id: str):
    """Henter alle ventende invitationer for en gruppe"""
    data = load_invitations()
    pending = []

    for token, inv in data["invitations"].items():
        if inv["group_id"] == group_id and inv["status"] == "pending":
            # Tjek udløb
            expires = datetime.fromisoformat(inv["expires"])
            if datetime.utcnow() <= expires:
                pending.append(
                    {"email": inv["email"], "created": inv["created"], "token": token}
                )

    return pending


# ========== models.py (15 linjer) ==========


class Item(BaseModel):
    name: str
    quantity: Optional[str] = "1"
    added_by: str


class ItemResponse(BaseModel):
    message: str
    item: Item


class SyncResponse(BaseModel):
    items: List[dict]
    last_updated: str


# ========== db.py (76 linjer) ==========
"""
Database operations with file locking to prevent race conditions
"""


# Thread-safe locks for each file
_locks = {}
_lock_mutex = threading.Lock()


def get_file_lock(filepath: Path) -> FileLock:
    """Get or create a FileLock for a given file"""
    lock_path = str(filepath) + ".lock"

    with _lock_mutex:
        if lock_path not in _locks:
            _locks[lock_path] = FileLock(lock_path, timeout=10)
        return _locks[lock_path]


def safe_read_json(filepath: Path, default: Any = None) -> Any:
    """Thread-safe JSON file reading with file locking"""
    if not filepath.exists():
        return default if default is not None else {}

    lock = get_file_lock(filepath)
    with lock:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)


def safe_write_json(filepath: Path, data: Any) -> None:
    """Thread-safe JSON file writing with file locking"""
    filepath.parent.mkdir(parents=True, exist_ok=True)

    lock = get_file_lock(filepath)
    with lock:
        # Write to temp file first, then rename (atomic on most systems)
        temp_file = filepath.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_file.replace(filepath)


def safe_update_json(filepath: Path, update_func, default: Any = None) -> Any:
    """
    Thread-safe JSON update with file locking

    Args:
        filepath: Path to JSON file
        update_func: Function that takes current data and returns updated data
        default: Default value if file doesn't exist

    Returns:
        Updated data
    """
    lock = get_file_lock(filepath)
    with lock:
        # Read current data
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = default if default is not None else {}

        # Update data
        updated_data = update_func(data)

        # Write back
        filepath.parent.mkdir(parents=True, exist_ok=True)
        temp_file = filepath.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(updated_data, f, indent=2, ensure_ascii=False)
        temp_file.replace(filepath)

        return updated_data


# ========== notifications.py (15 linjer) ==========


def send_push_notification(tokens, title, body):
    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body), tokens=tokens
        )
        response = messaging.send_multicast(message)
        print(f"📱 Sent {response.success_count} notifications.")
        return True
    except Exception as e:
        print(f"⚠️ Push notification failed (Firebase not set up): {e}")
        return False


# ========== ai_parser.py (512 linjer) ==========
"""
AI-powered parser til indkøbslister
Bruger lokal regex først, falder tilbage til Claude API ved usikkerhed
"""


# Load .env fil
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # dotenv ikke installeret, brug miljøvariabler direkte

# Prøv at importere Anthropic (valgfri)
try:
    from anthropic import Anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("⚠️ Anthropic ikke installeret - kun lokal parsing tilgængelig")

# Kategorier til varer
CATEGORIES = {
    # Mejeri
    "mælk": "mejeri",
    "letmælk": "mejeri",
    "minimælk": "mejeri",
    "sødmælk": "mejeri",
    "smør": "mejeri",
    "ost": "mejeri",
    "fløde": "mejeri",
    "piskefløde": "mejeri",
    "yoghurt": "mejeri",
    "skyr": "mejeri",
    "cremefraiche": "mejeri",
    "kærnemælk": "mejeri",
    "ymer": "mejeri",
    "mozzarella": "mejeri",
    # Kød
    "kylling": "kød",
    "oksekød": "kød",
    "hakket": "kød",
    "hakkekød": "kød",
    "svinekød": "kød",
    "bacon": "kød",
    "pølser": "kød",
    "hamburgerryg": "kød",
    "rullepølse": "kød",
    "leverpostej": "kød",
    "skinke": "kød",
    "medister": "kød",
    "kalvekød": "kød",
    "lammekød": "kød",
    # Fisk
    "laks": "fisk",
    "tun": "fisk",
    "torsk": "fisk",
    "rejer": "fisk",
    # Brød
    "brød": "bager",
    "rugbrød": "bager",
    "franskbrød": "bager",
    "boller": "bager",
    # Grøntsager
    "kartofler": "grønt",
    "kartoffel": "grønt",
    "løg": "grønt",
    "hvidløg": "grønt",
    "gulerødder": "grønt",
    "gulerod": "grønt",
    "tomater": "grønt",
    "tomat": "grønt",
    "agurk": "grønt",
    "salat": "grønt",
    "peberfrugt": "grønt",
    "broccoli": "grønt",
    # Frugt
    "æbler": "frugt",
    "æble": "frugt",
    "bananer": "frugt",
    "banan": "frugt",
    "appelsiner": "frugt",
    "appelsin": "frugt",
    "pærer": "frugt",
    "citroner": "frugt",
    # Drikkevarer
    "juice": "drikkevarer",
    "cola": "drikkevarer",
    "sodavand": "drikkevarer",
    "øl": "drikkevarer",
    "vin": "drikkevarer",
    "vand": "drikkevarer",
    "kaffe": "drikkevarer",
    "te": "drikkevarer",
    # Kolonial
    "pasta": "kolonial",
    "ris": "kolonial",
    "mel": "kolonial",
    "sukker": "kolonial",
    "salt": "kolonial",
    "olie": "kolonial",
    "ketchup": "kolonial",
    "sennep": "kolonial",
    "mayonnaise": "kolonial",
    "remoulade": "kolonial",
    # Husholdning
    "toiletpapir": "husholdning",
    "køkkenrulle": "husholdning",
    "sæbe": "husholdning",
    # Æg
    "æg": "æg",
}

# Standard mængder per kategori/vare
DEFAULT_QUANTITIES = {
    "mejeri": "1 L",
    "kød": "500 g",
    "fisk": "400 g",
    "bager": "1 stk",
    "grønt": "1 stk",
    "frugt": "1 stk",
    "drikkevarer": "1 L",
    "kolonial": "1 stk",
    "husholdning": "1 pk",
    "æg": "10 stk",
    # Specifikke varer
    "smør": "250 g",
    "ost": "400 g",
    "bacon": "1 pk",
    "pølser": "1 pk",
    "kartofler": "1 kg",
    "løg": "1 net",
    "æbler": "1 kg",
    "bananer": "1 bundt",
    "pasta": "500 g",
    "ris": "1 kg",
    "mel": "1 kg",
    "sukker": "1 kg",
}

# Kendt produktliste til fuzzy matching
KNOWN_PRODUCTS = list(CATEGORIES.keys())

# Forkortelser og almindelige stavefejl
PRODUCT_ALIASES = {
    "hambo": "hamburgerryg",
    "remu": "remoulade",
    "karto": "kartofler",
    "toma": "tomater",
    "gule": "gulerødder",
    "sømælk": "sødmælk",
    "smæølk": "sødmælk",
    "piskflø": "piskefløde",
    "rugbrø": "rugbrød",
    "franskbrø": "franskbrød",
    "lever": "leverpostej",
    "rulle": "rullepølse",
}


def fuzzy_correct(word: str) -> str:
    """Prøv at rette stavefejl og forkortelser med fuzzy matching"""
    word_lower = word.lower()

    # Check direkte aliases først
    if word_lower in PRODUCT_ALIASES:
        return PRODUCT_ALIASES[word_lower]

    # Brug fuzzy matching på kendte produkter
    matches = get_close_matches(word_lower, KNOWN_PRODUCTS, n=1, cutoff=0.7)
    if matches:
        return matches[0]

    return word


# Mængde-mønster - mere præcist
AMOUNT_PATTERN = re.compile(
    r"^(\d+(?:[.,]\d+)?)\s*(l|liter|ml|dl|cl|stk|stykker?|pakke|pakker|pk|poser?|g|gram|kg|kilo|fl|flaske|flasker|ds|dåse|dåser|bundt|net)?\s+",
    re.IGNORECASE,
)


def get_category(item_name: str) -> str:
    """Find kategori for en vare"""
    item_lower = item_name.lower()
    for key, category in CATEGORIES.items():
        if key in item_lower:
            return category
    return "andet"


def get_default_quantity(item_name: str) -> str:
    """Gæt standard mængde for en vare"""
    item_lower = item_name.lower()

    # Tjek specifikke varer først
    for key, qty in DEFAULT_QUANTITIES.items():
        if key in item_lower:
            return qty

    # Ellers brug kategori
    category = get_category(item_name)
    return DEFAULT_QUANTITIES.get(category, "1 stk")


def smart_split_by_products(text: str) -> List[str]:
    """Splitter tekst ved kendte produkter for at adskille varer uden separator"""
    words = text.strip().split()
    if len(words) <= 2:
        return [text]

    parts = []
    current_part = []
    last_product_idx = -1

    for i, word in enumerate(words):
        # Check om ordet er et kendt produkt
        is_product = any(
            word == p or word.startswith(p) or p.startswith(word)
            for p in CATEGORIES.keys()
        )

        # Check om næste ord starter en ny mængde
        next_word = words[i + 1] if i < len(words) - 1 else ""
        next_is_quantity = bool(
            re.match(
                r"^(\d+|en|et|to|tre|fire|fem|halvanden)$", next_word, re.IGNORECASE
            )
        )
        next_is_product = any(
            next_word == p or next_word.startswith(p) or p.startswith(next_word)
            for p in CATEGORIES.keys()
        )

        current_part.append(word)

        if is_product:
            last_product_idx = len(current_part) - 1

            # Hvis næste ord er mængde eller nyt produkt, afslut denne del
            if next_is_quantity or (next_is_product and i < len(words) - 1):
                parts.append(" ".join(current_part))
                current_part = []
                last_product_idx = -1

    # Tilføj resterende ord
    if current_part:
        parts.append(" ".join(current_part))

    return parts if parts else [text]


def local_parse(text: str) -> List[Dict]:
    """Parser tekst med regex - hurtig lokal parsing"""
    text = text.lower().strip()

    # Fjern fyldord fra starten - MEGET mere omfattende
    fillers = [
        r"^(øh|ehm|øhm|nå|nåh|altså|ikke|jo|bare)\s+",
        r"^(jeg skal have|vi skal have|skal have|jeg skal|vi skal)\s+",
        r"^(jeg|vi|man|den|det|de|der|den der|det der|de der)\s+",
        r"^(det der|ham der|hende der|den slags|du ved|jeg tænker)\s+",
        r"^(sku ha|sku have|ska ha|ska have)\s+",  # Slang/dialekt versioner
        r"^(skal have|skal bruge|skal købe|mangler|vi mangler)\s+",
        r"^(noget|lidt|lidt af|lidt af det|nogen|nogle)\s+",
        r"^(tilføj|køb|hent|tag|skriv|sæt)\s+",
        r"^(en|et|den|det)\s+(?!liter|kilo|kg|l\s)",  # Men ikke før enheder
    ]

    # Kør fyldords-fjernelse flere gange for at fange alle
    for _ in range(3):  # Max 3 iterationer
        old_text = text
        for filler in fillers:
            text = re.sub(filler, "", text, flags=re.IGNORECASE)
        if text == old_text:  # Ingen ændringer mere
            break

    # Split på eksplicitte separatorer
    parts = re.split(r"\s+og\s+|\s*,\s*|\s+samt\s+|\s+plus\s+", text)

    # For hver del, prøv at splitte på kendte produkter
    all_parts = []
    for part in parts:
        all_parts.extend(smart_split_by_products(part))

    parsed_items = []

    # Ordtal til tal mapping
    word_to_num = {
        "en": "1",
        "et": "1",
        "to": "2",
        "tre": "3",
        "fire": "4",
        "fem": "5",
        "seks": "6",
        "syv": "7",
        "otte": "8",
        "ni": "9",
        "ti": "10",
        "halvanden": "1.5",
        "halvandet": "1.5",
    }

    for part in all_parts:
        part = part.strip()
        if not part or len(part) < 2:
            continue

        item_name = part
        quantity = ""

        # Prøv specielle mønstre først

        # "tre/fire/fem kilo/liter X" (ordtal + enhed)
        ordtal_match = re.match(
            r"^(en|et|to|tre|fire|fem|seks|syv|otte|ni|ti|halvanden|halvandet)\s+(liter|l|kilo|kg|gram|g)\s+(.+)$",
            part,
            re.IGNORECASE,
        )
        if ordtal_match:
            num_word = ordtal_match.group(1).lower()
            unit = ordtal_match.group(2).lower()
            item_name = ordtal_match.group(3).strip()

            # Konverter ordtal til tal
            num = word_to_num.get(num_word, num_word)

            # Normaliser enhed
            if unit in ["l", "liter"]:
                unit = "L"
            elif unit in ["kg", "kilo"]:
                unit = "kg"
            elif unit in ["g", "gram"]:
                unit = "g"

            quantity = f"{num} {unit}"

        # "halvanden liter/kilo X"
        elif re.match(
            r"^(halvanden|halvandet)\s+(liter|l|kilo|kg)\s+", part, re.IGNORECASE
        ):
            halvanden_match = re.match(
                r"^(halvanden|halvandet)\s+(liter|l|kilo|kg)\s+(.+)$",
                part,
                re.IGNORECASE,
            )
            if halvanden_match:
                unit = halvanden_match.group(2)
                item_name = halvanden_match.group(3).strip()
                unit_norm = "L" if unit.lower() in ["l", "liter"] else "kg"
                quantity = f"1.5 {unit_norm}"

        # "en/et/halv/halvt liter/kilo X"
        elif re.match(
            r"^(en|et|halv|halvt)\s+(liter|l|kilo|kg)\s+", part, re.IGNORECASE
        ):
            unit_match = re.match(
                r"^(en|et|halv|halvt)\s+(liter|l|kilo|kg)\s+(.+)$", part, re.IGNORECASE
            )
            if unit_match:
                quantity_word = unit_match.group(1).lower()
                unit_word = unit_match.group(2).lower()
                item_name = unit_match.group(3).strip()

                # Bestem mængde
                if quantity_word in ["halv", "halvt"]:
                    num = "0.5"
                else:
                    num = "1"

                if unit_word in ["liter", "l"]:
                    quantity = f"{num} L"
                elif unit_word in ["kilo", "kg"]:
                    quantity = f"{num} kg"

        # "X l/liter/kg/stk Y"
        elif re.match(r"^\d", part):
            amount_match = AMOUNT_PATTERN.match(part)
            if amount_match:
                num = amount_match.group(1)
                unit = amount_match.group(2) or "stk"
                # Normaliser enhed
                unit_lower = unit.lower()
                if unit_lower in ["l", "liter"]:
                    unit = "L"
                elif unit_lower in ["kg", "kilo"]:
                    unit = "kg"
                elif unit_lower in ["g", "gram"]:
                    unit = "g"
                elif unit_lower in ["ml", "milliliter"]:
                    unit = "ml"
                elif unit_lower in ["dl", "deciliter"]:
                    unit = "dl"
                elif unit_lower in ["stk", "stykker", "stykke"]:
                    unit = "stk"
                elif unit_lower in ["pk", "pakke", "pakker"]:
                    unit = "pk"

                quantity = f"{num} {unit}"
                # Resten er item_name
                item_name = part[amount_match.end() :].strip()

        # Ryd GRUNDIGT op i item_name - fjern alle fyldord
        item_name = re.sub(
            r"^(en|et|den|det|noget|nogen|nogle|lidt|den der|det der)\s+",
            "",
            item_name,
            flags=re.IGNORECASE,
        )
        item_name = re.sub(r"^(den|det|der)\s+", "", item_name, flags=re.IGNORECASE)
        item_name = item_name.strip()

        if not item_name:
            continue

        # Prøv fuzzy correction på produktnavnet
        item_name = fuzzy_correct(item_name)

        # Sæt default mængde hvis ikke fundet
        if not quantity:
            quantity = get_default_quantity(item_name)

        # Find kategori
        category = get_category(item_name)

        parsed_items.append(
            {"item": item_name.capitalize(), "quantity": quantity, "category": category}
        )

    # Fjern duplikater - behold første forekomst
    seen = set()
    unique_items = []
    for item in parsed_items:
        item_key = item["item"].lower()
        if item_key not in seen:
            seen.add(item_key)
            unique_items.append(item)

    return unique_items


def opus_parse(text: str) -> List[Dict]:
    """Parser tekst med Claude API - for komplekse sætninger"""
    if not ANTHROPIC_AVAILABLE:
        return []

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("⚠️ ANTHROPIC_API_KEY ikke sat")
        return []

    try:
        client = Anthropic(api_key=api_key)

        prompt = f"""Du er en intelligent dansk indkøbsassistent. Brugeren taler ofte UTYDELIGT med dårligt/mumlet dansk.
Dit job: Forstå hvad de MENER og udtræk kun de relevante produkter.

🎯 HOVEDOPGAVE:
- Parser utydelig tale, stavefejl, afbrudte ord
- Gæt det mest sandsynlige produkt ved tvivl
- Ignorer ALT der ikke er produkter

❌ FJERN ALTID:
- Fyldord: "jeg skal have", "vi mangler", "skal købe"
- Pejleord: "den der", "det der", "ham der", "du ved"
- Samtale: "øh", "ehm", "altså", "ikke", "jo"
- Gentagelser: "mælk mælk mælk" → kun én "Mælk"
- Mumlen og pauser

✅ RET AUTOMATISK:
- "sømælk", "smæølk" → "Sødmælk"
- "rugbrø" → "Rugbrød"
- "hambo" → "Hamburgerryg"
- "remu" → "Remoulade"
- "piskflø" → "Piskefløde"
- "karto" → "Kartofler"

📝 EKSEMPLER:
"jæ ska den der smæølk" → Sødmælk (1 L)
"altså eh rugbrø rugbrød og mælk" → Rugbrød (1 stk), Mælk (1 L)
"øh jeg tænker lidt af det der hambo" → Hamburgerryg (1 pk)
"halv liter piskflø" → Piskefløde (0.5 L)
"tre kilo karto" → Kartofler (3 kg)
"smø smø smør" → Smør (250 g)  [kun én gang!]
"hambo og den der med remu" → Hamburgerryg (1 pk), Remoulade (1 stk)

📦 KATEGORIER:
mejeri, kød, fisk, bager, grønt, frugt, drikkevarer, kolonial, husholdning, æg, andet

🔧 OUTPUT (KUN JSON):
[
  {"item": "Produktnavn", "quantity": "1 enhed", "category": "kategori"}
]

🎤 BRUGERENS UTYDELIGE TALE:
"{text}"

RETURNÉR KUN JSON!"""

        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",  # Bedre kvalitet, stadig billig
            max_tokens=800,
            temperature=0.3,  # Lav temperatur for konsistens
            messages=[{"role": "user", "content": prompt}],
        )

        result_text = response.content[0].text.strip()

        # Fjern eventuelle markdown code blocks
        if result_text.startswith("```"):
            result_text = re.sub(r"^```(?:json)?\n?", "", result_text)
            result_text = re.sub(r"\n?```$", "", result_text)

        parsed = json.loads(result_text)

        # Valider at det er en liste
        if not isinstance(parsed, list):
            print(f"⚠️ AI returnerede ikke en liste: {type(parsed)}")
            return []

        # Valider hvert item
        valid_items = []
        for item in parsed:
            if (
                isinstance(item, dict)
                and "item" in item
                and "quantity" in item
                and "category" in item
            ):
                valid_items.append(item)
            else:
                print(f"⚠️ Ugyldigt item fra AI: {item}")

        return valid_items

    except json.JSONDecodeError as e:
        print(f"⚠️ JSON parse fejl: {e}")
        print(f"   Raw response: {result_text[:200]}...")
        return []
    except Exception as e:
        print(f"⚠️ Claude API fejl: {e}")
        return []


def smart_parse(text: str, force_ai: bool = False) -> Dict:
    """
    Smart parser - prøver lokal først, bruger AI ved usikkerhed

    Returns:
        Dict med 'items' (liste), 'method' ('local' eller 'ai'), og 'confidence'
    """
    # Prøv lokal parsing først
    local_result = local_parse(text)

    # Heuristik: Er vi sikre på resultatet?
    all_unknown = (
        all(item["category"] == "andet" for item in local_result)
        if local_result
        else True
    )
    short_input = len(text.split()) <= 2
    has_items = len(local_result) > 0
    very_short = len(text.split()) < 4  # Meget korte input er ofte uklare

    confidence = "high"
    if all_unknown and has_items:
        confidence = "low"
    elif not has_items:
        confidence = "none"

    # Brug AI hvis vi er usikre eller force_ai er True
    # Ved meget korte sætninger (<4 ord) eller ingen items - brug AI
    use_ai = force_ai or (confidence in ["low", "none"] and ANTHROPIC_AVAILABLE)
    if not has_items or all_unknown or very_short:
        use_ai = force_ai or ANTHROPIC_AVAILABLE

    if use_ai and not short_input:
        ai_result = opus_parse(text)
        if ai_result:
            return {
                "items": ai_result,
                "method": "ai",
                "confidence": "high",
                "original_text": text,
            }

    # Returner lokal resultat
    return {
        "items": local_result,
        "method": "local",
        "confidence": confidence,
        "original_text": text,
    }


# Test
if __name__ == "__main__":
    test_phrases = [
        # Grundlæggende
        "2 liter mælk",
        "vi mangler mælk og brød",
        "et kilo kartofler hamburgerryg og remoulade",
        # Med fyldord
        "jeg skal have den der sødmælk",
        "vi mangler noget rugbrød",
        "skal have øh tre kilo kartofler",
        # Komplekse
        "halvanden liter mælk og 3 bananer",
        "skal have noget kaffe og toiletpapir",
        "den der remoulade og det der øh bacon",
        # Edge cases
        "det der",  # Meget vagt
        "jeg skal have noget",  # Intet produkt
        "sødmælk",  # Simpelt
    ]

    print("🧪 Testing AI Parser\n" + "=" * 50)
    for phrase in test_phrases:
        result = smart_parse(phrase, force_ai=False)
        print(f"\n📝 '{phrase}'")
        print(
            f"   Metode: {
                result['method']} | Tillid: {
                result['confidence']}"
        )
        if result["items"]:
            for item in result["items"]:
                print(
                    f"   ✓ {
                        item['item']}: {
                        item['quantity']} ({
                        item['category']})"
                )
        else:
            print("   ✗ Ingen varer fundet")


# ========== ai_parser_optimized.py (285 linjer) ==========
"""State-of-the-art AI shopping list parser with fuzzy matching and async support."""


# Optional dependencies
try:
    from anthropic import AsyncAnthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

Category = Literal[
    "mejeri",
    "kød",
    "fisk",
    "bager",
    "grønt",
    "frugt",
    "drikkevarer",
    "kolonial",
    "husholdning",
    "æg",
    "andet",
]
Confidence = Literal["high", "low", "none"]


class ParsedItem(TypedDict):
    item: str
    quantity: str
    category: Category


class ParseResult(TypedDict):
    items: list[ParsedItem]
    method: Literal["local", "ai"]
    confidence: Confidence
    original_text: str
    used_alternative: str | None


# Immutable lookups (compile-time constants)
_CATEGORIES: dict[str, Category] = {
    "mælk": "mejeri",
    "letmælk": "mejeri",
    "minimælk": "mejeri",
    "sødmælk": "mejeri",
    "smør": "mejeri",
    "ost": "mejeri",
    "fløde": "mejeri",
    "piskefløde": "mejeri",
    "yoghurt": "mejeri",
    "skyr": "mejeri",
    "cremefraiche": "mejeri",
    "kærnemælk": "mejeri",
    "ymer": "mejeri",
    "mozzarella": "mejeri",
    "kylling": "kød",
    "oksekød": "kød",
    "hakket": "kød",
    "hakkekød": "kød",
    "svinekød": "kød",
    "bacon": "kød",
    "pølser": "kød",
    "hamburgerryg": "kød",
    "rullepølse": "kød",
    "leverpostej": "kød",
    "skinke": "kød",
    "medister": "kød",
    "kalvekød": "kød",
    "lammekød": "kød",
    "laks": "fisk",
    "tun": "fisk",
    "torsk": "fisk",
    "rejer": "fisk",
    "brød": "bager",
    "rugbrød": "bager",
    "franskbrød": "bager",
    "boller": "bager",
    "kartofler": "grønt",
    "kartoffel": "grønt",
    "løg": "grønt",
    "hvidløg": "grønt",
    "gulerødder": "grønt",
    "gulerod": "grønt",
    "tomater": "grønt",
    "tomat": "grønt",
    "agurk": "grønt",
    "salat": "grønt",
    "peberfrugt": "grønt",
    "broccoli": "grønt",
    "æbler": "frugt",
    "æble": "frugt",
    "bananer": "frugt",
    "banan": "frugt",
    "appelsiner": "frugt",
    "appelsin": "frugt",
    "pærer": "frugt",
    "citroner": "frugt",
    "juice": "drikkevarer",
    "cola": "drikkevarer",
    "sodavand": "drikkevarer",
    "øl": "drikkevarer",
    "vin": "drikkevarer",
    "vand": "drikkevarer",
    "kaffe": "drikkevarer",
    "te": "drikkevarer",
    "pasta": "kolonial",
    "ris": "kolonial",
    "mel": "kolonial",
    "sukker": "kolonial",
    "salt": "kolonial",
    "olie": "kolonial",
    "ketchup": "kolonial",
    "sennep": "kolonial",
    "mayonnaise": "kolonial",
    "remoulade": "kolonial",
    "toiletpapir": "husholdning",
    "køkkenrulle": "husholdning",
    "sæbe": "husholdning",
    "æg": "æg",
}

_DEFAULT_QTY: dict[str | Category, str] = {
    "mejeri": "1 L",
    "kød": "500 g",
    "fisk": "400 g",
    "bager": "1 stk",
    "grønt": "1 stk",
    "frugt": "1 stk",
    "drikkevarer": "1 L",
    "kolonial": "1 stk",
    "husholdning": "1 pk",
    "æg": "10 stk",
    "smør": "250 g",
    "ost": "400 g",
    "bacon": "1 pk",
    "pølser": "1 pk",
    "kartofler": "1 kg",
    "løg": "1 net",
    "æbler": "1 kg",
    "bananer": "1 bundt",
    "pasta": "500 g",
    "ris": "1 kg",
    "mel": "1 kg",
    "sukker": "1 kg",
}

_ALIASES: dict[str, str] = {
    "hambo": "hamburgerryg",
    "remu": "remoulade",
    "karto": "kartofler",
    "toma": "tomater",
    "gule": "gulerødder",
    "sømælk": "sødmælk",
    "smæølk": "sødmælk",
    "piskflø": "piskefløde",
    "rugbrø": "rugbrød",
    "franskbrø": "franskbrød",
    "lever": "leverpostej",
    "rulle": "rullepølse",
}

_WORD_TO_NUM: dict[str, str] = {
    "en": "1",
    "et": "1",
    "to": "2",
    "tre": "3",
    "fire": "4",
    "fem": "5",
    "seks": "6",
    "syv": "7",
    "otte": "8",
    "ni": "9",
    "ti": "10",
    "halvanden": "1.5",
    "halvandet": "1.5",
}

_KNOWN_PRODUCTS = tuple(_CATEGORIES.keys())

# Compiled regex patterns (initialized once)
_FILLER_PATTERNS = tuple(
    map(
        lambda p: re.compile(p, re.IGNORECASE),
        [
            r"^(øh|ehm|øhm|nå|nåh|altså|ikke|jo|bare)\s+",
            r"^(jeg skal have|vi skal have|skal have|jeg skal|vi skal)\s+",
            r"^(sku ha|sku have|ska ha|ska have)\s+",
            r"^(jeg|vi|man|den|det|de|der|den der|det der|de der)\s+",
            r"^(det der|ham der|hende der|den slags|du ved|jeg tænker)\s+",
            r"^(skal have|skal bruge|skal købe|mangler|vi mangler)\s+",
            r"^(noget|lidt|lidt af|lidt af det|nogen|nogle)\s+",
            r"^(tilføj|køb|hent|tag|skriv|sæt)\s+",
            r"^(en|et|den|det)\s+(?!liter|kilo|kg|l\s)",
        ],
    )
)

_AMOUNT_PATTERN = re.compile(
    r"^(\d+(?:[.,]\d+)?)\s*(l|liter|ml|dl|cl|stk|stykker?|pakke|pakker|pk|poser?|g|gram|kg|kilo|fl|flaske|flasker|ds|dåse|dåser|bundt|net)?\s+",
    re.IGNORECASE,
)

_SPLIT_PATTERN = re.compile(r"\s+og\s+|\s*,\s*|\s+samt\s+|\s+plus\s+")
_ORDTAL_UNIT_PATTERN = re.compile(
    r"^(en|et|to|tre|fire|fem|seks|syv|otte|ni|ti|halvanden|halvandet)\s+(liter|l|kilo|kg|gram|g)\s+(.+)$",
    re.IGNORECASE,
)
_HALF_UNIT_PATTERN = re.compile(
    r"^(en|et|halv|halvt)\s+(liter|l|kilo|kg)\s+(.+)$", re.IGNORECASE
)


@lru_cache(maxsize=512)
def _fuzzy_correct(word: str) -> str:
    """Fast fuzzy correction with caching."""
    lower = word.lower()
    if alias := _ALIASES.get(lower):
        return alias
    if matches := get_close_matches(lower, _KNOWN_PRODUCTS, n=1, cutoff=0.7):
        return matches[0]
    return word


@lru_cache(maxsize=256)
def _get_category(item: str) -> Category:
    """Cached category lookup."""
    lower = item.lower()
    for key, cat in _CATEGORIES.items():
        if key in lower:
            return cat
    return "andet"


@lru_cache(maxsize=256)
def _get_default_qty(item: str) -> str:
    """Cached quantity lookup."""
    lower = item.lower()
    for key, qty in _DEFAULT_QTY.items():
        if key in lower:
            return qty
    return _DEFAULT_QTY.get(_get_category(item), "1 stk")


def _clean_fillers(text: str) -> str:
    """Remove filler words efficiently."""
    text = text.lower().strip()
    for _ in range(3):
        old = text
        for pattern in _FILLER_PATTERNS:
            text = pattern.sub("", text)
        if text == old:
            break
    return text


def _normalize_unit(unit: str) -> str:
    """Fast unit normalization."""
    u = unit.lower()
    return (
        "L"
        if u in ("l", "liter")
        else (
            "kg"
            if u in ("kg", "kilo")
            else (
                "g"
                if u in ("g", "gram")
                else (
                    "ml"
                    if u in ("ml", "milliliter")
                    else (
                        "dl"
                        if u in ("dl", "deciliter")
                        else (
                            "stk"
                            if u in ("stk", "stykker", "stykke")
                            else "pk" if u in ("pk", "pakke", "pakker") else unit
                        )
                    )
                )
            )
        )
    )


def local_parse(text: str) -> list[ParsedItem]:
    """Fast local regex parser with minimal allocations."""
    text = _clean_fillers(text)
    # Split by delimiters and product names
    parts = []
    for p in _SPLIT_PATTERN.split(text):
        p = p.strip()
        if len(p) >= 2:
            # Further split by spaces if multiple words with same base
            words = p.split()
            if len(words) > 1 and len(set(w[:3] for w in words)) == 1:
                # Repetition like "smø smø smør" - take last
                parts.append(words[-1])
            else:
                parts.append(p)

    items: list[ParsedItem] = []
    seen: set[str] = set()

    for part in parts:
        quantity = ""
        item_name = part

        # Try patterns in order of frequency
        if match := _ORDTAL_UNIT_PATTERN.match(part):
            num, unit, item_name = match.groups()
            quantity = f"{
                _WORD_TO_NUM.get(
                    num.lower(),
                    num)} {
                _normalize_unit(unit)}"
        elif match := _HALF_UNIT_PATTERN.match(part):
            qty_word, unit, item_name = match.groups()
            num = "0.5" if qty_word.lower() in ("halv", "halvt") else "1"
            quantity = f"{num} {_normalize_unit(unit)}"
        elif part[0].isdigit() and (match := _AMOUNT_PATTERN.match(part)):
            num, unit = match.groups()
            quantity = f"{num} {_normalize_unit(unit or 'stk')}"
            item_name = part[match.end() :]

        item_name = _fuzzy_correct(item_name.strip())
        if not item_name:
            continue

        # Dedup check
        key = item_name.lower()
        if key in seen:
            continue
        seen.add(key)

        items.append(
            {
                "item": item_name.capitalize(),
                "quantity": quantity or _get_default_qty(item_name),
                "category": _get_category(item_name),
            }
        )

    return items


async def ai_parse(text: str) -> list[ParsedItem]:
    """Async AI parsing with Claude."""
    if not ANTHROPIC_AVAILABLE or not (key := os.getenv("ANTHROPIC_API_KEY")):
        return []

    client = AsyncAnthropic(api_key=key)

    prompt = f"""Du parser utydelig dansk tale til JSON produkter.

FJERN: fyldord, gentagelser, mumlen
RET: stavefejl automatisk (sømælk→Sødmælk, hambo→Hamburgerryg)

Input: "{text}"
Output JSON array: [{{"item":"Produkt","quantity":"1 L","category":"mejeri"}}]"""

    try:
        response = await client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=600,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        parsed = json.loads(raw)
        return [
            item
            for item in parsed
            if all(k in item for k in ("item", "quantity", "category"))
        ]
    except Exception:
        return []


def smart_parse(text: str, force_ai: bool = False) -> ParseResult:
    """Synchronous entry point."""
    return asyncio.run(smart_parse_async(text, force_ai))


async def smart_parse_async(text: str, force_ai: bool = False) -> ParseResult:
    """Async smart parser with AI fallback."""
    local = local_parse(text)

    all_unknown = all(item["category"] == "andet" for item in local)
    confidence: Confidence = "none" if not local else "low" if all_unknown else "high"

    use_ai = (
        force_ai
        or (not local or all_unknown or len(text.split()) < 4)
        and ANTHROPIC_AVAILABLE
    )

    if use_ai:
        if ai_items := await ai_parse(text):
            return {
                "items": ai_items,
                "method": "ai",
                "confidence": "high",
                "original_text": text,
                "used_alternative": None,
            }

    return {
        "items": local,
        "method": "local",
        "confidence": confidence,
        "original_text": text,
        "used_alternative": None,
    }


# Sync wrapper for compatibility
def parse_sync(text: str, force_ai: bool = False) -> ParseResult:
    """Legacy sync interface."""
    return smart_parse(text, force_ai)


# ========== endpoint_optimized.py (24 linjer) ==========
"""Optimized FastAPI endpoint with async support."""


class ParseRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    force_ai: bool = False
    text_alternatives: list[str] | None = Field(None, max_length=5)


@app.post("/ai/parse", response_model=ParseResult)
async def parse_voice_input(request: ParseRequest) -> ParseResult:
    """Async voice parsing with alternative handling."""
    result = await smart_parse_async(request.text, request.force_ai)

    # Try alternatives if main result is weak
    if request.text_alternatives and (
        not result["items"] or result["confidence"] == "low"
    ):
        for alt in request.text_alternatives[1:]:
            alt_result = await smart_parse_async(alt, request.force_ai)
            if alt_result["items"] and alt_result["confidence"] == "high":
                alt_result["used_alternative"] = alt
                return alt_result

    return result


# ========== test_fuzzy.py (52 linjer) ==========
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test fuzzy matching og utydelig tale"""


test_cases = [
    # Forkortelser
    ("hambo og remu", ["Hamburgerryg", "Remoulade"]),
    ("tre kilo karto", ["Kartofler"]),
    # Stavefejl
    ("sømælk", ["Sødmælk"]),
    ("smæølk", ["Sødmælk"]),
    ("piskflø", ["Piskefløde"]),
    ("rugbrø", ["Rugbrød"]),
    # Gentagelser
    ("smø smø smør", ["Smør"]),
    ("mælk mælk mælk", ["Mælk"]),
    # Komplekse
    ("halv liter piskflø", ["Piskefløde"]),
    ("øh jeg sku ha den der sømælk", ["Sødmælk"]),
]

print("🧪 Testing Fuzzy Matching & Utydelig Tale")
print("=" * 70)

passed = 0
failed = 0

for text, expected in test_cases:
    result = local_parse(text)  # Test lokal først
    items = [item["item"] for item in result]

    success = all(exp in items for exp in expected)
    status = "✓" if success else "✗"

    print(f'\n{status} "{text}"')
    print(f"   Forventet: {expected}")
    print(f"   Fik:       {items}")

    if success:
        passed += 1
    else:
        failed += 1

print(f"\n{'=' * 70}")
print(f"Resultat: {passed}/{len(test_cases)} tests passed")
if failed > 0:
    print(f"⚠️ {failed} tests failed - AI vil måske håndtere dem bedre")


# ========== test_optimized.py (24 linjer) ==========
#!/usr/bin/env python
"""Verify optimized version passes all tests."""

test_cases = [
    ("hambo og remu", ["Hamburgerryg", "Remoulade"]),
    ("tre kilo karto", ["Kartofler"]),
    ("sømælk", ["Sødmælk"]),
    ("smæølk", ["Sødmælk"]),
    ("piskflø", ["Piskefløde"]),
    ("rugbrø", ["Rugbrød"]),
    ("smø smø smør", ["Smør"]),
    ("mælk mælk mælk", ["Mælk"]),
    ("halv liter piskflø", ["Piskefløde"]),
    ("øh jeg sku ha den der sømælk", ["Sødmælk"]),
]

passed = sum(
    all(exp in [i["item"] for i in local_parse(text)] for exp in expected)
    for text, expected in test_cases
)

print(f"✅ {passed}/{len(test_cases)} tests passed")
assert passed == len(test_cases), "Some tests failed!"


# ========== benchmark.py (29 linjer) ==========
#!/usr/bin/env python
"""Performance benchmark comparing old vs optimized parser."""


TEST_CASES = [
    "jeg skal have den der sødmælk",
    "tre kilo kartofler og to liter mælk",
    "hambo og remu",
    "øh jeg sku ha den der sømælk og rugbrø",
    "halvanden liter piskflø",
    "mælk mælk mælk",
] * 100  # 600 total parses


def benchmark(name: str, func, *args):
    start = time.perf_counter()
    for text in TEST_CASES:
        func(text, *args)
    elapsed = time.perf_counter() - start
    ops_per_sec = len(TEST_CASES) / elapsed
    print(f"{name:20} {elapsed:.3f}s  ({ops_per_sec:.0f} ops/s)")
    return elapsed


print("🚀 Performance Benchmark\n" + "=" * 50)
old_time = benchmark("Old local_parse", old_parse)
new_time = benchmark("New local_parse", new_parse)
speedup = old_time / new_time
print(f"\n💨 Speedup: {speedup:.2f}x faster")


# ========== requirements.txt ==========
# fastapi
# uvicorn
# google-cloud-firestore
# firebase-admin
# pydantic
# requests
# python-dotenv
# SpeechRecognition
# filelock

# ========== .env.example ==========
# FIREBASE_CRED_PATH=serviceAccount.json
#
# # SÅDAN SÆTTER DU FIREBASE OP:
# # 1. Gå til https://console.firebase.google.com
# # 2. Vælg dit projekt
# # 3. Gå til Project Settings (tandhjul øverst)
# # 4. Fanen "Service Accounts"
# # 5. Klik "Generate new private key"
# # 6. Gem JSON-filen som "serviceAccount.json" i denne mappe
# # 7. Genstart serveren
