"""Autosearch sync — mirror Avito-side saved searches into local SearchProfiles.

ADR-011. Pulls the user's autosearches from Avito via xapi, upserts SearchProfile
rows by ``avito_autosearch_id``, soft-archives the ones removed on Avito side,
and wipes ``pending`` / ``viewed`` ProfileListings on update so the next polling
tick produces fresh "Новые" by the new criteria. ``accepted`` and ``rejected``
links are left untouched — those represent user decisions and survive re-sync.

Sync rate: each autosearch costs 1 deeplink-fetch on Avito's side. We sleep
``_PER_ITEM_SLEEP_SEC`` between items so a 7-autosearch user never dumps 14+
requests on Avito within a few seconds — that pattern reliably triggers the
mobile API anti-fraud filter (HTTP 403 for the next 5–15 min on the device).

V2 (account pool): ``sync_all_autosearches(pool)`` iterates over all active
accounts in the pool and calls ``_sync_for_account(acc, session)`` for each.
Accounts in cooldown/dead/refresh states are skipped with a log entry and
retried next run. Each ``_sync_for_account`` call opens its own DB session so
one failed account cannot poison another account's transaction.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_sessionmaker
from app.db.models import ProfileListing, SearchProfile
from app.db.models.enums import UserAction
from app.services.account_pool import AccountPool, AccountNotAvailableError
from avito_mcp.integrations.xapi_client import XapiClient, XapiError

log = logging.getLogger(__name__)


_SEARCH_WIDEN_PCT = 0.25  # ADR-008 default: alert ±25 % → search range
_PER_ITEM_SLEEP_SEC = 2.0  # space deeplink fetches to dodge anti-fraud


@dataclass(slots=True)
class AutosearchSyncResult:
    created: int
    updated: int
    archived: int
    fetched: int
    failed: list[str]


async def sync_all_autosearches(pool: AccountPool) -> None:
    """Pull autosearches for ALL active accounts in the pool.

    For each active account: claim_for_sync → fetch via xapi (account-aware) → upsert.
    Skip accounts in cooldown/dead/refresh — they'll be retried next sync run.
    Each per-account call opens its own DB session so failures are isolated.
    """
    accounts = await pool.list_active_accounts()
    log.info("sync_all_autosearches: %d active accounts", len(accounts))
    for acc in accounts:
        try:
            acc_session = await pool.claim_for_sync(acc["id"])
        except AccountNotAvailableError as e:
            log.info(
                "skip sync acc=%s state=%s",
                acc.get("nickname", acc["id"]),
                e.state,
            )
            continue
        try:
            await _sync_for_account(acc, acc_session)
        except Exception:
            log.exception("sync_for_account failed for %s", acc.get("nickname"))


async def _sync_for_account(
    acc: dict,
    session: dict,  # pool session dict returned by AccountPool.claim_for_sync
    *,
    xapi: XapiClient | None = None,
) -> AutosearchSyncResult:
    """Sync autosearches for a single account.

    Calls xapi subscription endpoints using ``account_id`` query param so the
    xapi server loads the correct Avito session for this pool account.
    Opens its own DB session via ``get_sessionmaker()`` so it can be used both
    from ``sync_all_autosearches`` and standalone (e.g. in tests or CLI).

    ``session`` is the pool session dict from ``AccountPool.claim_for_sync`` —
    reserved for future per-account bearer header injection.
    """
    account_id: str = acc["id"]

    own_xapi = xapi is None
    if xapi is None:
        xapi = XapiClient()

    fetched: list[dict[str, Any]] = []
    failed_ids: list[str] = []
    items = await xapi.list_subscriptions(account_id=account_id)
    for idx, it in enumerate(items):
        fid = it.get("id")
        if fid is None:
            continue
        if idx > 0:
            await asyncio.sleep(_PER_ITEM_SLEEP_SEC)
        try:
            sp = await xapi.get_subscription_search_params(
                int(fid), account_id=account_id
            )
        except XapiError as exc:
            log.warning(
                "autosearch.fetch_params_failed filter_id=%s account=%s err=%s",
                fid,
                account_id,
                exc,
            )
            failed_ids.append(str(fid))
            continue
        fetched.append({**it, "_search_params": sp.get("search_params") or {}})

    owner_account_id = uuid.UUID(account_id) if _is_uuid(account_id) else None

    async with get_sessionmaker()() as db:
        result = await _upsert_for_account(
            fetched=fetched,
            failed_ids=failed_ids,
            account_id=account_id,
            owner_account_id=owner_account_id,
            session=db,
        )

    log.info(
        "sync_for_account account=%s created=%d updated=%d archived=%d failed=%d",
        account_id,
        result.created,
        result.updated,
        result.archived,
        len(result.failed),
    )
    return result


async def _upsert_for_account(
    *,
    fetched: list[dict[str, Any]],
    failed_ids: list[str],
    account_id: str,
    owner_account_id: uuid.UUID | None,
    session: AsyncSession,
) -> AutosearchSyncResult:
    """Reconcile fetched autosearches with local SearchProfiles for one account.

    Extracted so it can be tested independently with a mock DB session.
    """
    # Scope reconciliation to this account's autosearch-synced profiles.
    where_clauses = [SearchProfile.import_source == "autosearch_sync"]
    if owner_account_id is not None:
        where_clauses.append(SearchProfile.owner_account_id == owner_account_id)

    existing_q = await session.execute(
        select(SearchProfile).where(*where_clauses)
    )
    existing_by_aid: dict[str, SearchProfile] = {
        p.avito_autosearch_id: p for p in existing_q.scalars() if p.avito_autosearch_id
    }
    fetched_ids = {str(it["id"]) for it in fetched}

    now = datetime.now(timezone.utc)
    created = updated = archived = 0

    for it in fetched:
        aid = str(it["id"])
        sp: dict[str, Any] = it["_search_params"]
        title = (it.get("title") or "").strip() or f"Autosearch #{aid}"

        try:
            price_min = int(sp["priceMin"]) if sp.get("priceMin") else None
        except (TypeError, ValueError):
            price_min = None
        try:
            price_max = int(sp["priceMax"]) if sp.get("priceMax") else None
        except (TypeError, ValueError):
            price_max = None
        only_with_delivery = sp.get("withDeliveryOnly") in ("1", 1, True)

        # Search-вилка = alert-вилка ±25 % per ADR-008.
        s_min = round(price_min * (1 - _SEARCH_WIDEN_PCT)) if price_min else None
        s_max = round(price_max * (1 + _SEARCH_WIDEN_PCT)) if price_max else None

        ep = existing_by_aid.get(aid)
        if ep is not None:
            ep.name = title
            ep.search_params = sp
            ep.alert_min_price = price_min
            ep.alert_max_price = price_max
            ep.search_min_price = s_min
            ep.search_max_price = s_max
            ep.only_with_delivery = only_with_delivery
            ep.last_synced_at = now
            ep.is_active = True
            ep.archived_at = None
            ep.owner_account_id = owner_account_id
            await session.execute(
                delete(ProfileListing).where(
                    ProfileListing.profile_id == ep.id,
                    ProfileListing.user_action.in_(
                        [UserAction.PENDING.value, UserAction.VIEWED.value]
                    ),
                )
            )
            updated += 1
        else:
            new_p = SearchProfile(
                id=uuid.uuid4(),
                name=title,
                # synthetic placeholder — autosearch profiles never go through
                # the URL parser; polling routes them through search_params.
                avito_search_url=f"avito://subscription/{aid}",
                avito_autosearch_id=aid,
                import_source="autosearch_sync",
                search_params=sp,
                alert_min_price=price_min,
                alert_max_price=price_max,
                search_min_price=s_min,
                search_max_price=s_max,
                only_with_delivery=only_with_delivery,
                last_synced_at=now,
                is_active=True,
                owner_account_id=owner_account_id,
            )
            session.add(new_p)
            created += 1

    # Archive autosearch-synced profiles that are no longer on Avito.
    for aid, p in existing_by_aid.items():
        if aid not in fetched_ids:
            p.archived_at = now
            p.is_active = False
            archived += 1

    await session.commit()

    return AutosearchSyncResult(
        created=created,
        updated=updated,
        archived=archived,
        fetched=len(fetched),
        failed=failed_ids,
    )


async def sync_autosearches_for_user(
    user_id: uuid.UUID,
    *,
    session: AsyncSession,
    xapi: XapiClient | None = None,
) -> AutosearchSyncResult:
    """Pull autosearches from Avito and reconcile with local SearchProfiles.

    .. deprecated::
        Use ``sync_all_autosearches(pool)`` for pool-aware syncing.
        This function is kept as a compatibility shim for callers that have not
        yet been migrated to the account pool. It uses the legacy (any-active)
        session path in xapi — no ``account_id`` query param.

    Wipe of pending/viewed for an updated profile and soft-delete of missing
    profiles happen in the same transaction as the upsert. ``rejected`` and
    ``accepted`` profile_listings are NOT touched — see ADR-011.
    """
    own_xapi = xapi is None
    if xapi is None:
        xapi = XapiClient()

    fetched: list[dict[str, Any]] = []
    failed_ids: list[str] = []
    items = await xapi.list_subscriptions()
    for idx, it in enumerate(items):
        fid = it.get("id")
        if fid is None:
            continue
        if idx > 0:
            await asyncio.sleep(_PER_ITEM_SLEEP_SEC)
        try:
            sp = await xapi.get_subscription_search_params(int(fid))
        except XapiError as exc:
            log.warning("autosearch.fetch_params_failed filter_id=%s err=%s", fid, exc)
            failed_ids.append(str(fid))
            continue
        fetched.append({**it, "_search_params": sp.get("search_params") or {}})

    existing_q = await session.execute(
        select(SearchProfile).where(
            SearchProfile.user_id == user_id,
            SearchProfile.import_source == "autosearch_sync",
        )
    )
    existing_by_aid: dict[str, SearchProfile] = {
        p.avito_autosearch_id: p for p in existing_q.scalars() if p.avito_autosearch_id
    }
    fetched_ids = {str(it["id"]) for it in fetched}

    now = datetime.now(timezone.utc)
    created = updated = archived = 0

    for it in fetched:
        aid = str(it["id"])
        sp: dict[str, Any] = it["_search_params"]
        title = (it.get("title") or "").strip() or f"Autosearch #{aid}"

        try:
            price_min = int(sp["priceMin"]) if sp.get("priceMin") else None
        except (TypeError, ValueError):
            price_min = None
        try:
            price_max = int(sp["priceMax"]) if sp.get("priceMax") else None
        except (TypeError, ValueError):
            price_max = None
        only_with_delivery = (sp.get("withDeliveryOnly") in ("1", 1, True))

        # Search-вилка = alert-вилка ±25 % per ADR-008.
        s_min = round(price_min * (1 - _SEARCH_WIDEN_PCT)) if price_min else None
        s_max = round(price_max * (1 + _SEARCH_WIDEN_PCT)) if price_max else None

        ep = existing_by_aid.get(aid)
        if ep is not None:
            ep.name = title
            ep.search_params = sp
            ep.alert_min_price = price_min
            ep.alert_max_price = price_max
            ep.search_min_price = s_min
            ep.search_max_price = s_max
            ep.only_with_delivery = only_with_delivery
            ep.last_synced_at = now
            ep.is_active = True
            ep.archived_at = None
            await session.execute(
                delete(ProfileListing).where(
                    ProfileListing.profile_id == ep.id,
                    ProfileListing.user_action.in_(
                        [UserAction.PENDING.value, UserAction.VIEWED.value]
                    ),
                )
            )
            updated += 1
        else:
            new_p = SearchProfile(
                id=uuid.uuid4(),
                user_id=user_id,
                name=title,
                # synthetic placeholder — autosearch profiles never go through
                # the URL parser; polling routes them through search_params.
                avito_search_url=f"avito://subscription/{aid}",
                avito_autosearch_id=aid,
                import_source="autosearch_sync",
                search_params=sp,
                alert_min_price=price_min,
                alert_max_price=price_max,
                search_min_price=s_min,
                search_max_price=s_max,
                only_with_delivery=only_with_delivery,
                last_synced_at=now,
                is_active=True,
            )
            session.add(new_p)
            created += 1

    # Archive autosearch-synced profiles that are no longer on Avito.
    for aid, p in existing_by_aid.items():
        if aid not in fetched_ids:
            p.archived_at = now
            p.is_active = False
            archived += 1

    await session.commit()

    if own_xapi:
        # XapiClient creates per-call AsyncClient; nothing persistent to close.
        pass

    return AutosearchSyncResult(
        created=created,
        updated=updated,
        archived=archived,
        fetched=len(fetched),
        failed=failed_ids,
    )


def _is_uuid(value: str) -> bool:
    """Return True if value is a valid UUID string."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False
