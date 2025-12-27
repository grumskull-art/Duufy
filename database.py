from google.cloud import firestore
from datetime import datetime
import os
import json
from pathlib import Path
from db import safe_read_json, safe_write_json, safe_update_json

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
        "last_updated": datetime.utcnow().isoformat()
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
            "item_count": len(g.get("items", []))
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
