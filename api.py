import sys
import os
import logging

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from fastapi import Body, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from auth import verify_token
from database import (
    create_group,
    create_history_entry,
    create_item,
    create_user,
    delete_group,
    delete_item,
    delete_user,
    get_groups,
    get_history,
    get_items,
    get_users,
    update_group,
    update_item,
    update_user,
)
from history_service import calculate_median_purchase_pattern

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Duufy API",
    version="1.1-fixes",
    description="Dansk AI-indk\u00f8bsassistent",
)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Duufy API startet")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("Duufy API lukket")


@app.exception_handler(Exception)
async def handle_exceptions(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Fejl: %s", exc)
    return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info("Anmodning modtaget: %s %s", request.method, request.url.path)
    return await call_next(request)


@app.get("/ping")
async def ping() -> dict:
    return {"status": "ok", "besked": "Duufy API k\u00f8rer"}


@app.get("/users")
async def list_users(user=Depends(verify_token)) -> JSONResponse:
    """Returnerer alle brugere"""
    try:
        result = await get_users()
        logger.info("Brugere hentet")
        return JSONResponse(status_code=200, content={"status": "ok", "data": result})
    except Exception as e:
        logger.error("Fejl i endpoint: %s", e)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


@app.post("/users")
async def create_user_endpoint(
    data: dict = Body(...),
    user=Depends(verify_token),
) -> JSONResponse:
    """Opretter bruger"""
    try:
        result = await create_user(data)
        logger.info("Bruger oprettet")
        return JSONResponse(status_code=201, content={"status": "ok", "data": result})
    except Exception as e:
        logger.error("Fejl i endpoint: %s", e)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


@app.put("/users/{user_id}")
async def update_user_endpoint(
    user_id: str,
    data: dict = Body(...),
    user=Depends(verify_token),
) -> JSONResponse:
    """Opdaterer bruger"""
    try:
        result = await update_user(user_id, data)
        logger.info("Bruger opdateret")
        return JSONResponse(status_code=200, content={"status": "ok", "data": result})
    except Exception as e:
        logger.error("Fejl i endpoint: %s", e)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


@app.delete("/users/{user_id}")
async def delete_user_endpoint(user_id: str, user=Depends(verify_token)) -> JSONResponse:
    """Sletter bruger"""
    try:
        result = await delete_user(user_id)
        logger.info("Bruger slettet")
        return JSONResponse(status_code=200, content={"status": "ok", "data": result})
    except Exception as e:
        logger.error("Fejl i endpoint: %s", e)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


@app.get("/groups")
async def list_groups(user=Depends(verify_token)) -> JSONResponse:
    """Returnerer alle grupper"""
    try:
        result = await get_groups()
        logger.info("Grupper hentet")
        return JSONResponse(status_code=200, content={"status": "ok", "data": result})
    except Exception as e:
        logger.error("Fejl i endpoint: %s", e)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


@app.post("/groups")
async def create_group_endpoint(
    data: dict = Body(...),
    user=Depends(verify_token),
) -> JSONResponse:
    """Opretter gruppe"""
    try:
        result = await create_group(data)
        logger.info("Gruppe oprettet")
        return JSONResponse(status_code=201, content={"status": "ok", "data": result})
    except Exception as e:
        logger.error("Fejl i endpoint: %s", e)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


@app.put("/groups/{group_id}")
async def update_group_endpoint(
    group_id: str,
    data: dict = Body(...),
    user=Depends(verify_token),
) -> JSONResponse:
    """Opdaterer gruppe"""
    try:
        result = await update_group(group_id, data)
        logger.info("Gruppe opdateret")
        return JSONResponse(status_code=200, content={"status": "ok", "data": result})
    except Exception as e:
        logger.error("Fejl i endpoint: %s", e)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


@app.delete("/groups/{group_id}")
async def delete_group_endpoint(group_id: str, user=Depends(verify_token)) -> JSONResponse:
    """Sletter gruppe"""
    try:
        result = await delete_group(group_id)
        logger.info("Gruppe slettet")
        return JSONResponse(status_code=200, content={"status": "ok", "data": result})
    except Exception as e:
        logger.error("Fejl i endpoint: %s", e)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


@app.get("/items")
async def list_items(user=Depends(verify_token)) -> JSONResponse:
    """Returnerer alle items"""
    try:
        result = await get_items()
        logger.info("Varer hentet")
        return JSONResponse(status_code=200, content={"status": "ok", "data": result})
    except Exception as e:
        logger.error("Fejl i endpoint: %s", e)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


@app.post("/items")
async def create_item_endpoint(
    data: dict = Body(...),
    user=Depends(verify_token),
) -> JSONResponse:
    """Opretter item"""
    try:
        result = await create_item(data)
        logger.info("Vare oprettet")
        return JSONResponse(status_code=201, content={"status": "ok", "data": result})
    except Exception as e:
        logger.error("Fejl i endpoint: %s", e)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


@app.put("/items/{item_id}")
async def update_item_endpoint(
    item_id: str,
    data: dict = Body(...),
    user=Depends(verify_token),
) -> JSONResponse:
    """Opdaterer item"""
    try:
        result = await update_item(item_id, data)
        logger.info("Vare opdateret")
        return JSONResponse(status_code=200, content={"status": "ok", "data": result})
    except Exception as e:
        logger.error("Fejl i endpoint: %s", e)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


@app.delete("/items/{item_id}")
async def delete_item_endpoint(item_id: str, user=Depends(verify_token)) -> JSONResponse:
    """Sletter item"""
    try:
        result = await delete_item(item_id)
        logger.info("Vare slettet")
        return JSONResponse(status_code=200, content={"status": "ok", "data": result})
    except Exception as e:
        logger.error("Fejl i endpoint: %s", e)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


@app.get("/history")
async def list_history(user=Depends(verify_token)) -> JSONResponse:
    """Returnerer historik"""
    try:
        result = await get_history()
        logger.info("Historik hentet")
        return JSONResponse(status_code=200, content={"status": "ok", "data": result})
    except Exception as e:
        logger.error("Fejl i endpoint: %s", e)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


@app.post("/history")
async def create_history_endpoint(
    data: dict = Body(...),
    user=Depends(verify_token),
) -> JSONResponse:
    """Opretter historik"""
    try:
        result = await create_history_entry(data)
        logger.info("Historik oprettet")
        return JSONResponse(status_code=201, content={"status": "ok", "data": result})
    except Exception as e:
        logger.error("Fejl i endpoint: %s", e)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})


@app.get("/history/patterns")
async def get_history_patterns(user=Depends(verify_token)) -> JSONResponse:
    """Returnerer medianm\u00f8nstre pr. bruger"""
    try:
        user_id = user.get("id") if isinstance(user, dict) else getattr(user, "id", None)
        result = await calculate_median_purchase_pattern(user_id)
        logger.info("Historikm\u00f8nster returneret for bruger %s", user_id)
        return JSONResponse(status_code=200, content={"status": "ok", "pattern": result})
    except Exception as e:
        logger.error("Fejl i endpoint: %s", e)
        return JSONResponse(status_code=500, content={"fejl": "Der opstod en intern serverfejl"})
