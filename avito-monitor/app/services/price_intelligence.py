"""Price Intelligence — Block 7.

Implements the 4-step algorithm from TZ §4.2:

1. Fetch competitors via avito-mcp (paginated up to ``max_competitors``).
2. For each competitor — pull the detail page.
3. LLM-compare each competitor to the reference.
4. Build the aggregate report (range, top-5 cheaper / top-5 pricier,
   recommended price, conclusion).

The service is **synchronous-from-the-API-perspective** (no TaskIQ enqueue
in V1 — see V1_BLOCKS_TZ §4 Block 7 / §5.1 column "Файлы которые ТОЧНО не
трогать"). One run takes ≲ 3 min on 30 competitors with a fast model
because :class:`LLMAnalyzer` already caches ``compare`` results in the
``llm_analyses`` table — re-runs within a day are essentially free.
"""
from __future__ import annotations

import logging
import re
import statistics
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PriceAnalysis, PriceAnalysisRun
from app.schemas.price_analysis import (
    CompetitorRow,
    PriceAnalysisCreate,
    PriceAnalysisUpdate,
    PriceRange,
    PriceReport,
    ReferenceSummary,
)
from shared.models.avito import ListingDetail, ListingShort
from shared.models.llm import ComparisonResult

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols (so the service is easy to fake in tests).
# ---------------------------------------------------------------------------

class _MCPProto:
    """The subset of :class:`AvitoMcpClient` we call."""
    async def fetch_search_page(self, url: str, page: int = 1) -> Any: ...
    async def get_listing(self, item_id_or_url: int | str) -> ListingDetail: ...


class _AnalyzerProto:
    """The subset of :class:`LLMAnalyzer` we call."""
    async def compare_to_reference(
        self,
        competitor: ListingDetail,
        reference: ListingDetail | dict[str, Any],
        *,
        model: str | None = None,
    ) -> ComparisonResult: ...


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def list_analyses(
    session: AsyncSession, user_id: uuid.UUID
) -> list[PriceAnalysis]:
    stmt = (
        select(PriceAnalysis)
        .where(PriceAnalysis.user_id == user_id)
        .order_by(PriceAnalysis.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_analysis(
    session: AsyncSession, user_id: uuid.UUID, analysis_id: uuid.UUID
) -> PriceAnalysis | None:
    stmt = select(PriceAnalysis).where(
        PriceAnalysis.id == analysis_id,
        PriceAnalysis.user_id == user_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_analysis(
    session: AsyncSession, user_id: uuid.UUID, data: PriceAnalysisCreate
) -> PriceAnalysis:
    analysis = PriceAnalysis(user_id=user_id, **data.model_dump())
    session.add(analysis)
    await session.flush()
    return analysis


async def update_analysis(
    session: AsyncSession,
    analysis: PriceAnalysis,
    data: PriceAnalysisUpdate,
) -> PriceAnalysis:
    payload = data.model_dump(exclude_unset=True)
    for k, v in payload.items():
        setattr(analysis, k, v)
    await session.flush()
    return analysis


async def delete_analysis(
    session: AsyncSession, analysis: PriceAnalysis
) -> None:
    await session.delete(analysis)
    await session.flush()


async def list_runs(
    session: AsyncSession, analysis_id: uuid.UUID, limit: int = 50
) -> list[PriceAnalysisRun]:
    stmt = (
        select(PriceAnalysisRun)
        .where(PriceAnalysisRun.analysis_id == analysis_id)
        .order_by(PriceAnalysisRun.started_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_run(
    session: AsyncSession, run_id: uuid.UUID
) -> PriceAnalysisRun | None:
    stmt = select(PriceAnalysisRun).where(PriceAnalysisRun.id == run_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_latest_run(
    session: AsyncSession, analysis_id: uuid.UUID
) -> PriceAnalysisRun | None:
    stmt = (
        select(PriceAnalysisRun)
        .where(PriceAnalysisRun.analysis_id == analysis_id)
        .order_by(PriceAnalysisRun.started_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Reference resolution
# ---------------------------------------------------------------------------

_AVITO_ID_RE = re.compile(r"_(\d{6,})/?(?:\?|$)")


def _extract_avito_id(url: str | None) -> int | None:
    if not url:
        return None
    m = _AVITO_ID_RE.search(url)
    if m:
        try:
            return int(m.group(1))
        except ValueError:  # pragma: no cover — defensive
            return None
    return None


def _reference_summary_from_listing(detail: ListingDetail) -> ReferenceSummary:
    return ReferenceSummary(
        title=detail.title,
        url=detail.url,
        price=int(detail.price) if detail.price is not None else None,
        region=detail.region,
        condition=(detail.parameters or {}).get("Состояние") if detail.parameters else None,
        avito_id=detail.id,
    )


def _reference_summary_from_data(data: dict[str, Any]) -> ReferenceSummary:
    """Build the reference header from manually-entered ``reference_data``.

    Accepts the same shape as a ListingDetail (``title``, ``price``,
    ``region``, ``condition``, ``url``) but doesn't require all fields.
    """
    price = data.get("price") or data.get("my_price")
    try:
        price_i = int(price) if price is not None else None
    except (TypeError, ValueError):
        price_i = None
    return ReferenceSummary(
        title=data.get("title"),
        url=data.get("url"),
        price=price_i,
        region=data.get("region"),
        condition=data.get("condition"),
        avito_id=_extract_avito_id(data.get("url")),
    )


def _reference_data_for_llm(
    detail: ListingDetail | None, data: dict[str, Any], summary: ReferenceSummary
) -> ListingDetail | dict[str, Any]:
    """Return the object passed to ``LLMAnalyzer.compare_to_reference``."""
    if detail is not None:
        return detail
    # Manual reference: synthesise a minimal dict with the LLM-friendly
    # keys. The analyzer accepts dict | ListingDetail.
    return {
        "id": summary.avito_id,
        "title": summary.title or data.get("title") or "",
        "price": summary.price,
        "currency": "RUB",
        "region": summary.region,
        "description": data.get("description"),
        "parameters": data.get("parameters") or {},
        "url": summary.url,
    }


# ---------------------------------------------------------------------------
# Search competitors
# ---------------------------------------------------------------------------

async def _collect_competitors(
    mcp: _MCPProto, search_url: str, max_competitors: int
) -> list[ListingShort]:
    """Page through avito-mcp until ``max_competitors`` hit or the page runs out."""
    collected: list[ListingShort] = []
    page = 1
    seen_ids: set[int] = set()
    while len(collected) < max_competitors:
        try:
            search_page = await mcp.fetch_search_page(search_url, page=page)
        except Exception:
            log.exception("price_intel.fetch_search_page_failed page=%s", page)
            break
        items = list(getattr(search_page, "items", []) or [])
        if not items:
            break
        for item in items:
            if item.id in seen_ids:
                continue
            seen_ids.add(item.id)
            collected.append(item)
            if len(collected) >= max_competitors:
                break
        if not getattr(search_page, "has_more", False):
            break
        page += 1
        if page > 50:  # absolute safety net — Avito caps at 100ish anyway
            break
    return collected


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def _percentile(sorted_prices: list[int], p: float) -> int | None:
    """Linear-interpolation percentile, like NumPy's default. ``p`` in [0, 1]."""
    if not sorted_prices:
        return None
    if len(sorted_prices) == 1:
        return sorted_prices[0]
    rank = p * (len(sorted_prices) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_prices) - 1)
    frac = rank - lo
    return int(round(sorted_prices[lo] + (sorted_prices[hi] - sorted_prices[lo]) * frac))


def _round_to_hundred(value: float) -> int:
    return int(round(value / 100.0)) * 100


def _build_histogram_bins(
    prices: list[int], reference_price: int | None, bin_count: int = 10
) -> list[dict[str, Any]]:
    """Compute simple equal-width histogram for the report widget."""
    if not prices:
        return []
    lo, hi = min(prices), max(prices)
    if lo == hi:
        return [{"low": lo, "high": hi, "count": len(prices), "is_ref": True}]
    width = max(1, (hi - lo) // bin_count)
    bins: list[dict[str, Any]] = []
    for i in range(bin_count):
        b_lo = lo + width * i
        b_hi = lo + width * (i + 1) if i < bin_count - 1 else hi
        count = sum(1 for p in prices if b_lo <= p < b_hi or (i == bin_count - 1 and p == b_hi))
        is_ref = (
            reference_price is not None
            and (b_lo <= reference_price < b_hi or (i == bin_count - 1 and reference_price == b_hi))
        )
        bins.append({"low": b_lo, "high": b_hi, "count": count, "is_ref": is_ref})
    return bins


def _conclusion_text(
    reference_price: int | None,
    range_p25: int | None,
    range_median: int | None,
    range_p75: int | None,
    recommended: int | None,
) -> str:
    if reference_price is None or range_median is None:
        return "Недостаточно данных для оценки твоего объявления."

    if reference_price < (range_p25 or range_median):
        loc = "ниже p25"
    elif reference_price < range_median:
        loc = "между p25 и медианой"
    elif reference_price <= (range_p75 or range_median):
        loc = "между медианой и p75"
    else:
        loc = "выше p75"

    pieces = [
        f"Твоя цена {reference_price:,} ₽ — {loc} рынка "
        f"(медиана {range_median:,} ₽).".replace(",", "\xa0"),
    ]
    if recommended is not None and recommended != reference_price:
        delta = recommended - reference_price
        if delta < 0:
            pieces.append(
                f"Рекомендую снизить до {recommended:,} ₽ "
                f"(−{abs(delta):,} ₽) для попадания в активный диапазон p25–медиана."
                .replace(",", "\xa0")
            )
        else:
            pieces.append(
                f"Можно подтянуть к {recommended:,} ₽ "
                f"(+{delta:,} ₽), рынок это поддерживает.".replace(",", "\xa0")
            )
    return " ".join(pieces)


def _row_from(detail: ListingDetail, comparison: ComparisonResult) -> CompetitorRow:
    return CompetitorRow(
        avito_id=detail.id,
        title=detail.title or "",
        price=int(detail.price) if detail.price is not None else 0,
        url=detail.url,
        score=int(comparison.score),
        advantages=list(comparison.key_advantages or []),
        disadvantages=list(comparison.key_disadvantages or []),
        price_delta_estimate=comparison.price_delta_estimate,
    )


def _build_report(
    reference_summary: ReferenceSummary,
    competitors_seen: int,
    rows: list[CompetitorRow],
) -> PriceReport:
    """Assemble the final :class:`PriceReport` from per-competitor rows.

    ``rows`` comes pre-filtered to ``comparable=True`` competitors.
    """
    prices = sorted([r.price for r in rows if r.price > 0])
    range_ = PriceRange(
        min=prices[0] if prices else None,
        p25=_percentile(prices, 0.25),
        median=_percentile(prices, 0.5),
        p75=_percentile(prices, 0.75),
        max=prices[-1] if prices else None,
    )

    ref_price = reference_summary.price
    cheaper = sorted(
        [r for r in rows if ref_price is not None and r.price < ref_price],
        key=lambda r: (-r.score, r.price),
    )[:5]
    pricier = sorted(
        [r for r in rows if ref_price is not None and r.price > ref_price],
        key=lambda r: (-r.score, -r.price),
    )[:5]

    recommended = (
        _round_to_hundred(range_.median * 0.95)
        if range_.median is not None else None
    )

    histogram = _build_histogram_bins(prices, ref_price)

    return PriceReport(
        reference=reference_summary,
        competitors_found=competitors_seen,
        comparable_count=len(rows),
        range=range_,
        cheaper_top5=cheaper,
        pricier_top5=pricier,
        recommended_price=recommended,
        conclusion=_conclusion_text(
            ref_price, range_.p25, range_.median, range_.p75, recommended
        ),
        histogram_bins=histogram,
    )


# ---------------------------------------------------------------------------
# The actual run
# ---------------------------------------------------------------------------

class PriceIntelligenceError(RuntimeError):
    """Raised when a run fails irrecoverably (no competitors / bad URL / etc.)."""


def _resolve_search_url(analysis: PriceAnalysis) -> str:
    """Pick the search URL out of competitor_filters; raise otherwise.

    V1: the form stores the user-pasted Avito search URL under
    ``competitor_filters.search_url``. Future iterations may build the
    URL from structured filters.
    """
    cf = analysis.competitor_filters or {}
    url = cf.get("search_url")
    if url:
        return str(url)
    raise PriceIntelligenceError(
        "competitor_filters.search_url не задан — "
        "нужен URL поиска конкурентов на Avito"
    )


async def run_analysis(
    session: AsyncSession,
    analysis: PriceAnalysis,
    *,
    mcp: _MCPProto,
    analyzer: _AnalyzerProto,
) -> PriceAnalysisRun:
    """Execute one run of ``analysis``. Always persists a Run row."""

    run = PriceAnalysisRun(
        analysis_id=analysis.id,
        started_at=datetime.now(tz=timezone.utc),
        status="running",
    )
    session.add(run)
    await session.flush()

    try:
        # ---- step 1: resolve reference -----------------------------------
        ref_detail: ListingDetail | None = None
        if analysis.reference_listing_url:
            try:
                ref_detail = await mcp.get_listing(analysis.reference_listing_url)
            except Exception as e:
                raise PriceIntelligenceError(
                    f"не удалось получить эталон по URL: {e}"
                ) from e

        if ref_detail is not None:
            ref_summary = _reference_summary_from_listing(ref_detail)
        else:
            ref_summary = _reference_summary_from_data(
                dict(analysis.reference_data or {})
            )
        if ref_summary.price is None:
            raise PriceIntelligenceError(
                "цена эталона не определена — задай reference_data.price "
                "или укажи reference_listing_url с известной ценой"
            )

        ref_for_llm = _reference_data_for_llm(
            ref_detail, dict(analysis.reference_data or {}), ref_summary
        )

        # ---- step 2: collect competitors ---------------------------------
        search_url = _resolve_search_url(analysis)
        competitors = await _collect_competitors(
            mcp, search_url, int(analysis.max_competitors or 30)
        )
        if not competitors:
            raise PriceIntelligenceError(
                "поиск конкурентов вернул 0 объявлений"
            )

        # ---- step 3: detail + LLM compare per-competitor -----------------
        rows: list[CompetitorRow] = []
        per_competitor_data: list[dict[str, Any]] = []
        comparable_rows: list[CompetitorRow] = []

        for short in competitors:
            # Skip the reference itself if it sneaks into the result set.
            if ref_summary.avito_id is not None and short.id == ref_summary.avito_id:
                continue

            try:
                detail = await mcp.get_listing(short.id)
            except Exception:
                log.warning("price_intel.get_listing_failed id=%s", short.id)
                continue

            try:
                comp = await analyzer.compare_to_reference(
                    detail, ref_for_llm, model=analysis.llm_model or None
                )
            except Exception:
                log.exception(
                    "price_intel.compare_failed competitor=%s", short.id
                )
                continue

            row = _row_from(detail, comp)
            rows.append(row)
            per_competitor_data.append(
                {
                    "avito_id": detail.id,
                    "title": detail.title,
                    "price": row.price,
                    "url": detail.url,
                    "comparable": comp.comparable,
                    "score": row.score,
                    "advantages": row.advantages,
                    "disadvantages": row.disadvantages,
                    "price_delta_estimate": row.price_delta_estimate,
                }
            )
            if comp.comparable:
                comparable_rows.append(row)

        # ---- step 4: build report ----------------------------------------
        report = _build_report(
            ref_summary,
            competitors_seen=len(competitors),
            rows=comparable_rows,
        )

        run.status = "success"
        run.report = report.model_dump(mode="json")
        run.competitor_data = per_competitor_data
        run.competitors_found = len(competitors)
        run.comparable_count = len(comparable_rows)
        run.finished_at = datetime.now(tz=timezone.utc)

    except PriceIntelligenceError as e:
        run.status = "failed"
        run.error_message = str(e)
        run.finished_at = datetime.now(tz=timezone.utc)
    except Exception as e:
        log.exception("price_intel.run_unhandled analysis=%s", analysis.id)
        run.status = "failed"
        run.error_message = f"unhandled: {type(e).__name__}: {e}"
        run.finished_at = datetime.now(tz=timezone.utc)

    await session.flush()
    return run


# ---------------------------------------------------------------------------
# Markdown export — used by /send-to-telegram and the "Скачать MD" button
# ---------------------------------------------------------------------------

def _fmt_money(value: int | float | Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{int(value):,}".replace(",", "\xa0") + " ₽"


def export_report_markdown(
    analysis: PriceAnalysis, run: PriceAnalysisRun
) -> str:
    """Render the run's report as Markdown — for TG send + file download."""
    if run.status != "success":
        return (
            f"❗ *{analysis.name}*\n\n"
            f"Прогон завершился со статусом *{run.status}*.\n"
            f"{run.error_message or ''}"
        ).strip()

    report = PriceReport.model_validate(run.report or {})
    lines: list[str] = []
    lines.append(f"📊 *Ценовая разведка: {analysis.name}*")
    if report.reference.title:
        lines.append(f"_{report.reference.title}_")
    if report.reference.price is not None:
        lines.append(f"Моя цена: *{_fmt_money(report.reference.price)}*")
    lines.append("")
    lines.append(
        f"Конкурентов: {report.competitors_found} · "
        f"сопоставимых: {report.comparable_count}"
    )
    lines.append("")
    lines.append("*Вилка по сопоставимым:*")
    lines.append(f"• Минимум: {_fmt_money(report.range.min)}")
    lines.append(f"• P25: {_fmt_money(report.range.p25)}")
    lines.append(f"• Медиана: {_fmt_money(report.range.median)}")
    lines.append(f"• P75: {_fmt_money(report.range.p75)}")
    lines.append(f"• Максимум: {_fmt_money(report.range.max)}")
    if report.recommended_price is not None:
        lines.append("")
        lines.append(
            f"💡 *Рекомендую: {_fmt_money(report.recommended_price)}*"
        )
    if report.cheaper_top5:
        lines.append("")
        lines.append("*Дешевле меня (топ-5):*")
        for r in report.cheaper_top5:
            cons = ", ".join(r.disadvantages[:2]) or "—"
            lines.append(f"• {_fmt_money(r.price)} · score {r.score} · {cons}")
    if report.pricier_top5:
        lines.append("")
        lines.append("*Дороже меня (топ-5):*")
        for r in report.pricier_top5:
            pros = ", ".join(r.advantages[:2]) or "—"
            lines.append(f"• {_fmt_money(r.price)} · score {r.score} · {pros}")
    if report.conclusion:
        lines.append("")
        lines.append(f"_{report.conclusion}_")
    return "\n".join(lines)
