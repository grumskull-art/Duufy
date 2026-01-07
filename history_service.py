import logging
from datetime import datetime
from statistics import median
from typing import Any, Dict, List, Optional

from fastapi.responses import JSONResponse

from supabase_client import db_insert_async, db_select_async

logger = logging.getLogger(__name__)

_HISTORY_TABLE = "history"


def _parse_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _median_days(values: List[int]) -> int:
    if not values:
        return 0
    return int(median(values))


async def add_history_entry(user_id: str, item_id: str, timestamp: str) -> Any:
    payload = {"user_id": user_id, "item_id": item_id, "timestamp": timestamp}
    try:
        result = await db_insert_async(_HISTORY_TABLE, payload, use_service_key=True)
        if result.get("success"):
            logger.info("Historik opdateret for bruger %s", user_id)
            return {"status": "ok", "data": result.get("data")}
        logger.error("Historik kunne ikke gemmes for bruger %s", user_id)
        return JSONResponse(status_code=500, content={"fejl": "Kunne ikke gemme historik"})
    except Exception as exc:
        logger.error("Fejl ved historikindsats: %s", exc)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


async def get_user_history(user_id: str) -> Any:
    try:
        result = await db_select_async(
            _HISTORY_TABLE,
            columns="*",
            filters={"user_id": user_id},
            use_service_key=True,
        )
        if not result.get("success"):
            logger.error("Historik kunne ikke hentes for bruger %s", user_id)
            return JSONResponse(status_code=500, content={"fejl": "Kunne ikke hente historik"})

        data = result.get("data") or []
        if not data:
            logger.warning("Ingen historik fundet for bruger %s", user_id)
        else:
            logger.info("Historik hentet for bruger %s", user_id)
        return {"status": "ok", "data": data}
    except Exception as exc:
        logger.error("Fejl ved historikhaentning: %s", exc)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


async def calculate_median_purchase_pattern(user_id: str) -> Any:
    try:
        result = await db_select_async(
            _HISTORY_TABLE,
            columns="item_id,timestamp",
            filters={"user_id": user_id},
            use_service_key=True,
        )
        if not result.get("success"):
            logger.error("Historik kunne ikke hentes for bruger %s", user_id)
            return JSONResponse(status_code=500, content={"fejl": "Kunne ikke beregne historik"})

        entries = result.get("data") or []
        if not entries:
            logger.warning("Ingen historik fundet for bruger %s", user_id)
            return {"item_id": None, "median_days": None}

        per_item: Dict[str, List[datetime]] = {}
        for entry in entries:
            item_id = entry.get("item_id")
            timestamp = entry.get("timestamp")
            if not item_id or not timestamp:
                continue
            parsed = _parse_timestamp(timestamp)
            if not parsed:
                continue
            per_item.setdefault(item_id, []).append(parsed)

        if not per_item:
            logger.warning("Historikdata mangler tidsstempler for bruger %s", user_id)
            return {"item_id": None, "median_days": None}

        medians: List[Dict[str, Any]] = []
        for item_id, timestamps in per_item.items():
            timestamps.sort()
            deltas = []
            for first, second in zip(timestamps, timestamps[1:]):
                deltas.append((second - first).days)
            medians.append(
                {"item_id": item_id, "median_days": _median_days(deltas)}
            )

        medians.sort(key=lambda entry: entry["median_days"])
        logger.info("Medianm\u00f8nster beregnet for bruger %s", user_id)
        return medians[0]
    except Exception as exc:
        logger.error("Fejl ved medianberegning: %s", exc)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})
