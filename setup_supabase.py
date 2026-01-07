"""
Duufy Supabase connection test (async)
"""

import os
from dotenv import load_dotenv

# Absolut sti til .env (robust for Codex)
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv(env_path)

# Bekræft miljøet (kan slettes efter test)
if not os.getenv("SUPABASE_URL"):
    print("⚠️ .env ikke fundet af Codex! Kører fallback...")
else:
    print("✅ Miljøvariabler indlæst korrekt.")


import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from dotenv import load_dotenv

try:
    from supabase import create_async_client, create_client
    _SUPABASE_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:
    create_async_client = None
    create_client = None
    _SUPABASE_IMPORT_ERROR = exc


LOG_NAME = "duufy.supabase"


def _setup_logging() -> logging.Logger:
    logger = logging.getLogger(LOG_NAME)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    logs_dir = Path(__file__).parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "connection_test.log"

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def _load_env(logger: logging.Logger) -> None:
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(".env indlæst fra %s", env_path)
    else:
        load_dotenv()
        logger.warning("Ingen .env-fil fundet i projektmappen. Bruger miljøvariabler hvis de findes.")


def _get_env(logger: logging.Logger) -> tuple[str, str, list[str]]:
    """
    Læser miljøvariabler for Supabase og returnerer (url, key, missing).
    Understøtter både SUPABASE_SERVICE_KEY og SUPABASE_KEY som fallback.
    """
    import os

    url = os.getenv("SUPABASE_URL", "").strip()
    # Fallback: accepter både SUPABASE_SERVICE_KEY og SUPABASE_KEY
    key = (os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY") or "").strip()

    missing: list[str] = []
    if not url:
        missing.append("SUPABASE_URL")
    if not key:
        missing.append("SUPABASE_SERVICE_KEY / SUPABASE_KEY")

    if missing:
        logger.error("Manglende miljøvariabler: %s", ", ".join(missing))

    return url, key, missing




async def _create_client(url: str, key: str, logger: logging.Logger) -> tuple[Any, bool]:
    if _SUPABASE_IMPORT_ERROR is not None:
        logger.error("Supabase-py er ikke installeret: %s", _SUPABASE_IMPORT_ERROR)
        raise RuntimeError("SUPABASE_PY_MISSING")

    if create_async_client is not None:
        try:
            client = await create_async_client(url, key)
            logger.info("Async Supabase-klient oprettet")
            return client, True
        except Exception as exc:
            logger.warning("Kunne ikke oprette async client, falder tilbage til sync: %s", exc)

    if create_client is None:
        raise RuntimeError("SUPABASE_CLIENT_UNAVAILABLE")

    client = create_client(url, key)
    logger.info("Sync Supabase-klient oprettet")
    return client, False


def _get_result_error(result: Any) -> Optional[Any]:
    if hasattr(result, "error"):
        return result.error
    if isinstance(result, dict):
        return result.get("error")
    return None


def _get_result_data(result: Any) -> Any:
    if hasattr(result, "data"):
        return result.data
    if isinstance(result, dict):
        return result.get("data")
    return None


def _first_row(data: Any) -> Optional[dict]:
    if isinstance(data, list) and data:
        if isinstance(data[0], dict):
            return data[0]
    return None


async def _execute(query: Any, use_thread: bool) -> Any:
    if use_thread:
        return await asyncio.to_thread(query.execute)
    result = query.execute()
    if asyncio.iscoroutine(result):
        return await result
    return result


async def test_connection(logger: logging.Logger) -> bool:
    _load_env(logger)
    url, key, missing = _get_env(logger)
    if missing:
        return False

    client, is_async = await _create_client(url, key, logger)

    event_id = uuid4().hex
    event_name = f"connection_test_{event_id}"
    payload = {
        "event_name": event_name,
        "event_data": {"test_id": event_id, "source": "setup_supabase.py"},
    }

    logger.info("Starter round-trip test (insert → select → delete)")

    try:
        insert_result = await _execute(
            client.table("analytics_events").insert(payload),
            use_thread=not is_async,
        )
        error = _get_result_error(insert_result)
        if error:
            raise RuntimeError(f"Insert fejl: {error}")

        inserted = _first_row(_get_result_data(insert_result))
        row_id = inserted.get("id") if inserted else None
        logger.info("Insert OK (id=%s)", row_id or "ukendt")

        select_query = client.table("analytics_events").select("*").eq("event_name", event_name).limit(1)
        select_result = await _execute(select_query, use_thread=not is_async)
        error = _get_result_error(select_result)
        if error:
            raise RuntimeError(f"Select fejl: {error}")

        selected = _first_row(_get_result_data(select_result))
        if not selected:
            raise RuntimeError("Select fejl: kunne ikke finde test-row")

        row_id = selected.get("id") or row_id
        logger.info("Select OK (id=%s)", row_id or "ukendt")

        delete_query = client.table("analytics_events").delete().eq("event_name", event_name)
        delete_result = await _execute(delete_query, use_thread=not is_async)
        error = _get_result_error(delete_result)
        if error:
            raise RuntimeError(f"Delete fejl: {error}")

        logger.info("Delete OK")
        return True

    except Exception as exc:
        logger.exception("Round-trip test fejlede: %s", exc)
        return False


async def main() -> None:
    logger = _setup_logging()
    logger.info("Starter Supabase connection test")

    try:
        ok = await test_connection(logger)
    except Exception as exc:
        logger.exception("Uventet fejl under test: %s", exc)
        ok = False

    if ok:
        logger.info("Supabase-forbindelse testet og bekræftet")
        print("✅ Supabase-forbindelse testet og bekræftet.")
    else:
        logger.error("Supabase-test fejlede. Se logs/connection_test.log for detaljer.")


if __name__ == "__main__":
    asyncio.run(main())
