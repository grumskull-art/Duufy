from fastapi import Header, HTTPException


async def verify_token(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Missing token"}},
        )

    token = authorization.replace("Bearer ", "")
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid token"}},
        )

    from supabase_client import get_user

    result = get_user(token)
    if not result.get("success"):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid token"}},
        )
    return result.get("user")
