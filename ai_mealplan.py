import logging
from typing import Dict, List

from fastapi.responses import JSONResponse

from history_service import get_user_history

logger = logging.getLogger(__name__)

_UGEDAGE = [
    "mandag",
    "tirsdag",
    "onsdag",
    "torsdag",
    "fredag",
    "loerdag",
    "soendag",
]

_LOKALE_FORSLAG = [
    "Kylling i karry",
    "Pasta med laks",
    "Chili con carne",
    "Frikadeller med kartoffelmos",
    "Vegetarlasagne",
    "Fiskefrikadeller med salat",
    "Tacos med boenner",
]


def _build_plan(start_index: int) -> List[Dict[str, str]]:
    forslag = []
    for idx, dag in enumerate(_UGEDAGE):
        ret = _LOKALE_FORSLAG[(start_index + idx) % len(_LOKALE_FORSLAG)]
        forslag.append({"dag": dag, "ret": ret})
    return forslag


async def generate_mealplan(user_id: str) -> dict:
    try:
        if not user_id:
            return {"fejl": "Bruger-id mangler"}

        history = await get_user_history(user_id)
        if isinstance(history, JSONResponse):
            logger.error("Historik kunne ikke hentes for bruger %s", user_id)
            return {"fejl": "Der opstod en intern serverfejl"}

        history_data = []
        if isinstance(history, dict):
            history_data = history.get("data") or []

        offset = 0
        if history_data:
            offset = len(history_data) % len(_LOKALE_FORSLAG)

        forslag = _build_plan(offset)
        logger.info("Madplan genereret for bruger %s", user_id)
        return {"ugedage": list(_UGEDAGE), "forslag": forslag}
    except Exception as exc:
        logger.error("Fejl ved madplan: %s", exc)
        return {"fejl": "Der opstod en intern serverfejl"}
