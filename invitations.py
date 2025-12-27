"""
Invitation system for Duufy
Do you often forget? Duufy don't
Håndterer email-invitationer til grupper
"""

import json
import secrets
import os
from datetime import datetime, timedelta
from pathlib import Path
from db import safe_read_json, safe_write_json, safe_update_json

# Prøv at importere resend, men lad det fejle gracefully
try:
    import resend
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False

# Load environment variables
from dotenv import load_dotenv
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

def create_invitation(group_id: str, group_name: str, inviter_name: str, email: str, base_url: str):
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
                    "token": inv_token
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
        "status": "pending"  # pending, accepted, expired
    }
    
    data["invitations"][token] = invitation
    save_invitations(data)
    
    # Send email
    invite_url = f"{base_url}/invite/{token}"
    email_sent = send_invitation_email(email, inviter_name, group_name, invite_url)
    
    return {
        "success": True,
        "message": f"Invitation sendt til {email}!" if email_sent else f"Invitation oprettet (email kunne ikke sendes)",
        "token": token,
        "invite_url": invite_url,
        "email_sent": email_sent
    }

def send_invitation_email(to_email: str, inviter_name: str, group_name: str, invite_url: str):
    """Sender invitation-email via Resend"""
    
    if not RESEND_AVAILABLE or not RESEND_API_KEY:
        print(f"Email ville være sendt til {to_email}: {invite_url}")
        return False
    
    try:
        resend.api_key = RESEND_API_KEY
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #667eea; text-align: center;">🧠 Duufy</h1>
            <p style="text-align: center; color: #718096; font-style: italic;">Do you often forget? Duufy don't</p>
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
        
        resend.Emails.send({
            "from": "Duufy <noreply@resend.dev>",
            "to": to_email,
            "subject": f"🧠 {inviter_name} inviterer dig til {group_name} - Duufy",
            "html": html_content
        })
        
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
        return {"success": False, "message": "Invitation er allerede brugt eller udløbet"}
    
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
                "groups": [invitation["group_id"]]
            }
        else:
            if invitation["group_id"] not in users_data["users"][email].get("groups", []):
                users_data["users"][email].setdefault("groups", []).append(invitation["group_id"])
        save_users(users_data)
        
        return {
            "success": True, 
            "message": f"Velkommen til {invitation['group_name']}!",
            "group_id": invitation["group_id"],
            "group_name": invitation["group_name"]
        }
    else:
        return {"success": False, "message": "Kunne ikke tilføje til gruppen - du er måske allerede medlem"}

def get_pending_invitations(group_id: str):
    """Henter alle ventende invitationer for en gruppe"""
    data = load_invitations()
    pending = []
    
    for token, inv in data["invitations"].items():
        if inv["group_id"] == group_id and inv["status"] == "pending":
            # Tjek udløb
            expires = datetime.fromisoformat(inv["expires"])
            if datetime.utcnow() <= expires:
                pending.append({
                    "email": inv["email"],
                    "created": inv["created"],
                    "token": token
                })
    
    return pending
