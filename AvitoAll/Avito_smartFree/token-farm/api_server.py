"""
Token Farm API Server
FastAPI REST API for managing Avito accounts and tokens
"""

import asyncio
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import sys
sys.path.insert(0, "..")
from shared.database import (
    get_db, Database, init_db, close_db,
    AccountRepository, SessionRepository, ProxyRepository
)
from shared.models import Account, Session, AccountStatus
from shared.config import settings
from shared.utils import parse_jwt, mask_phone, mask_token


# ============== Pydantic Schemas ==============

class AccountCreate(BaseModel):
    """Create account request"""
    phone: str = Field(..., description="Phone number in any format")
    device_id: Optional[str] = None
    device_model: str = "SM-G998B"
    android_version: str = "12"


class AccountResponse(BaseModel):
    """Account response"""
    id: UUID
    phone: str
    phone_masked: str
    user_id: Optional[int]
    user_hash: Optional[str]
    status: str
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SessionResponse(BaseModel):
    """Session response"""
    id: UUID
    session_token: str
    token_masked: str
    expires_at: datetime
    hours_until_expiry: float
    is_expired: bool
    is_active: bool

    class Config:
        from_attributes = True


class AccountWithSession(AccountResponse):
    """Account with active session"""
    session: Optional[SessionResponse] = None


class RefreshRequest(BaseModel):
    """Token refresh request"""
    force: bool = False


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    database: bool
    containers_active: int
    accounts_total: int
    accounts_active: int
    accounts_expiring: int


class ContainerStatus(BaseModel):
    """Container status"""
    id: str
    name: str
    status: str
    created: str
    account_id: Optional[UUID]


# ============== Dependencies ==============

async def verify_api_key(x_api_key: str = Header(None)) -> bool:
    """Verify API key from header"""
    if settings.farm_api_key and x_api_key != settings.farm_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


async def get_database() -> Database:
    """Get database instance"""
    return await get_db()


# ============== Lifespan ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    print("Starting Token Farm API...")
    await init_db()
    print("Database initialized")

    # Import and start farm manager
    try:
        from farm_manager import FarmManager
        app.state.farm = FarmManager()
        await app.state.farm.start()
        print("Farm manager started")
    except Exception as e:
        print(f"Farm manager not available: {e}")
        app.state.farm = None

    yield

    # Shutdown
    print("Shutting down...")
    if hasattr(app.state, 'farm') and app.state.farm:
        await app.state.farm.stop()
    await close_db()


# ============== FastAPI App ==============

app = FastAPI(
    title="Token Farm API",
    description="API for managing Avito accounts and JWT tokens",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== Health Endpoints ==============

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(db: Database = Depends(get_database)):
    """Check system health"""
    db_healthy = await db.health_check()

    containers_active = 0
    if hasattr(app.state, 'farm') and app.state.farm:
        containers_active = len(app.state.farm.get_active_containers())

    async with db.session() as session:
        repo = AccountRepository(session)
        all_accounts = await repo.get_all()
        active_accounts = await repo.get_all(status=AccountStatus.ACTIVE)
        expiring_accounts = await repo.get_expiring(hours=4)

    return HealthResponse(
        status="healthy" if db_healthy else "degraded",
        database=db_healthy,
        containers_active=containers_active,
        accounts_total=len(all_accounts),
        accounts_active=len(active_accounts),
        accounts_expiring=len(expiring_accounts)
    )


# ============== Account Endpoints ==============

@app.get("/accounts", response_model=List[AccountWithSession], tags=["Accounts"])
async def list_accounts(
    status: Optional[str] = None,
    db: Database = Depends(get_database),
    _: bool = Depends(verify_api_key)
):
    """List all accounts"""
    async with db.session() as session:
        repo = AccountRepository(session)
        session_repo = SessionRepository(session)

        status_enum = AccountStatus(status) if status else None
        accounts = await repo.get_all(status=status_enum)

        result = []
        for account in accounts:
            active_session = await session_repo.get_active(account.id)

            account_data = AccountWithSession(
                id=account.id,
                phone=account.phone,
                phone_masked=mask_phone(account.phone),
                user_id=account.user_id,
                user_hash=account.user_hash,
                status=account.status.value,
                error_message=account.error_message,
                created_at=account.created_at,
                updated_at=account.updated_at,
                session=None
            )

            if active_session:
                account_data.session = SessionResponse(
                    id=active_session.id,
                    session_token=active_session.session_token,
                    token_masked=mask_token(active_session.session_token),
                    expires_at=active_session.expires_at,
                    hours_until_expiry=active_session.hours_until_expiry,
                    is_expired=active_session.is_expired,
                    is_active=active_session.is_active
                )

            result.append(account_data)

        return result


@app.post("/accounts", response_model=AccountResponse, tags=["Accounts"])
async def create_account(
    data: AccountCreate,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_database),
    _: bool = Depends(verify_api_key)
):
    """Create new account and start registration"""
    from shared.utils import normalize_phone, generate_device_id

    phone = normalize_phone(data.phone)

    async with db.session() as session:
        repo = AccountRepository(session)

        # Check if exists
        existing = await repo.get_by_phone(phone)
        if existing:
            raise HTTPException(status_code=400, detail="Account with this phone already exists")

        # Create account
        device_id = data.device_id or generate_device_id()
        account = await repo.create(
            phone=phone,
            device_id=device_id,
            device_model=data.device_model,
            android_version=data.android_version,
            status=AccountStatus.PENDING
        )

        # Schedule registration in background
        if hasattr(app.state, 'farm') and app.state.farm:
            background_tasks.add_task(
                app.state.farm.register_account,
                account.id
            )

        return AccountResponse(
            id=account.id,
            phone=account.phone,
            phone_masked=mask_phone(account.phone),
            user_id=account.user_id,
            user_hash=account.user_hash,
            status=account.status.value,
            error_message=account.error_message,
            created_at=account.created_at,
            updated_at=account.updated_at
        )


@app.get("/accounts/{account_id}", response_model=AccountWithSession, tags=["Accounts"])
async def get_account(
    account_id: UUID,
    db: Database = Depends(get_database),
    _: bool = Depends(verify_api_key)
):
    """Get account by ID"""
    async with db.session() as session:
        repo = AccountRepository(session)
        session_repo = SessionRepository(session)

        account = await repo.get_by_id(account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        active_session = await session_repo.get_active(account.id)

        response = AccountWithSession(
            id=account.id,
            phone=account.phone,
            phone_masked=mask_phone(account.phone),
            user_id=account.user_id,
            user_hash=account.user_hash,
            status=account.status.value,
            error_message=account.error_message,
            created_at=account.created_at,
            updated_at=account.updated_at,
            session=None
        )

        if active_session:
            response.session = SessionResponse(
                id=active_session.id,
                session_token=active_session.session_token,
                token_masked=mask_token(active_session.session_token),
                expires_at=active_session.expires_at,
                hours_until_expiry=active_session.hours_until_expiry,
                is_expired=active_session.is_expired,
                is_active=active_session.is_active
            )

        return response


@app.get("/accounts/{account_id}/session", response_model=SessionResponse, tags=["Accounts"])
async def get_account_session(
    account_id: UUID,
    db: Database = Depends(get_database),
    _: bool = Depends(verify_api_key)
):
    """Get active session for account"""
    async with db.session() as session:
        repo = AccountRepository(session)
        session_repo = SessionRepository(session)

        account = await repo.get_by_id(account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        active_session = await session_repo.get_active(account.id)
        if not active_session:
            raise HTTPException(status_code=404, detail="No active session")

        return SessionResponse(
            id=active_session.id,
            session_token=active_session.session_token,
            token_masked=mask_token(active_session.session_token),
            expires_at=active_session.expires_at,
            hours_until_expiry=active_session.hours_until_expiry,
            is_expired=active_session.is_expired,
            is_active=active_session.is_active
        )


@app.post("/accounts/{account_id}/refresh", response_model=AccountResponse, tags=["Accounts"])
async def refresh_account_token(
    account_id: UUID,
    data: RefreshRequest,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_database),
    _: bool = Depends(verify_api_key)
):
    """Request token refresh for account"""
    async with db.session() as session:
        repo = AccountRepository(session)

        account = await repo.get_by_id(account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        if account.status == AccountStatus.REFRESHING and not data.force:
            raise HTTPException(status_code=400, detail="Refresh already in progress")

        # Update status
        await repo.update_status(account_id, AccountStatus.REFRESHING)

        # Schedule refresh in background
        if hasattr(app.state, 'farm') and app.state.farm:
            background_tasks.add_task(
                app.state.farm.refresh_token,
                account_id
            )

        # Reload account
        account = await repo.get_by_id(account_id)

        return AccountResponse(
            id=account.id,
            phone=account.phone,
            phone_masked=mask_phone(account.phone),
            user_id=account.user_id,
            user_hash=account.user_hash,
            status=account.status.value,
            error_message=account.error_message,
            created_at=account.created_at,
            updated_at=account.updated_at
        )


@app.delete("/accounts/{account_id}", tags=["Accounts"])
async def delete_account(
    account_id: UUID,
    db: Database = Depends(get_database),
    _: bool = Depends(verify_api_key)
):
    """Delete account"""
    async with db.session() as session:
        repo = AccountRepository(session)

        account = await repo.get_by_id(account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        await repo.delete(account_id)

        return {"status": "deleted", "id": str(account_id)}


# ============== Container Endpoints ==============

@app.get("/containers", response_model=List[ContainerStatus], tags=["Containers"])
async def list_containers(_: bool = Depends(verify_api_key)):
    """List Redroid containers"""
    if not hasattr(app.state, 'farm') or not app.state.farm:
        return []

    containers = app.state.farm.get_containers_status()
    return [
        ContainerStatus(
            id=c["id"],
            name=c["name"],
            status=c["status"],
            created=c["created"],
            account_id=c.get("account_id")
        )
        for c in containers
    ]


# ============== Expiring Accounts ==============

@app.get("/accounts/expiring/{hours}", response_model=List[AccountWithSession], tags=["Accounts"])
async def get_expiring_accounts(
    hours: int = 4,
    db: Database = Depends(get_database),
    _: bool = Depends(verify_api_key)
):
    """Get accounts with tokens expiring within N hours"""
    async with db.session() as session:
        repo = AccountRepository(session)
        session_repo = SessionRepository(session)

        accounts = await repo.get_expiring(hours=hours)

        result = []
        for account in accounts:
            active_session = await session_repo.get_active(account.id)

            response = AccountWithSession(
                id=account.id,
                phone=account.phone,
                phone_masked=mask_phone(account.phone),
                user_id=account.user_id,
                user_hash=account.user_hash,
                status=account.status.value,
                error_message=account.error_message,
                created_at=account.created_at,
                updated_at=account.updated_at,
                session=None
            )

            if active_session:
                response.session = SessionResponse(
                    id=active_session.id,
                    session_token=active_session.session_token,
                    token_masked=mask_token(active_session.session_token),
                    expires_at=active_session.expires_at,
                    hours_until_expiry=active_session.hours_until_expiry,
                    is_expired=active_session.is_expired,
                    is_active=active_session.is_active
                )

            result.append(response)

        return result


# ============== Main ==============

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api_server:app",
        host=settings.farm_host,
        port=settings.farm_port,
        reload=True,
        log_level="info"
    )
