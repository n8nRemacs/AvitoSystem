"""Account pool router — list, claim, report, refresh-cycle, state."""
from fastapi import APIRouter

from src.storage.supabase import get_supabase

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


@router.get("")
async def list_accounts():
    sb = get_supabase()
    res = sb.table("avito_accounts").select("*").execute()
    return res.data or []
