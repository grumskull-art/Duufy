from typing import List, Optional

from pydantic import BaseModel


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
