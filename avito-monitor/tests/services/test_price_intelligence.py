"""Unit tests for Price Intelligence (Block 7).

The DB layer is faked via a tiny ``FakeSession`` because the service
only calls ``add`` / ``flush`` on it — no need for a real engine.

The interesting bits are:

* :func:`_percentile` — linear-interpolation, mirroring NumPy default
* :func:`_build_report` — range, top-5, recommended, conclusion
* :func:`_collect_competitors` — pagination + max cap
* :func:`run_analysis` — happy path through 4 steps, plus failure modes
* :func:`export_report_markdown` — TG-friendly Markdown
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.db.models import PriceAnalysis
from app.schemas.price_analysis import (
    CompetitorRow,
    PriceReport,
    ReferenceSummary,
)
from app.services.price_intelligence import (
    _build_report,
    _collect_competitors,
    _extract_avito_id,
    _percentile,
    _round_to_hundred,
    export_report_markdown,
    run_analysis,
)
from shared.models.avito import ListingDetail, ListingShort, SearchPage
from shared.models.llm import ComparisonResult


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

class TestPercentile:
    def test_empty(self):
        assert _percentile([], 0.5) is None

    def test_single(self):
        assert _percentile([100], 0.5) == 100
        assert _percentile([100], 0.25) == 100

    def test_median_odd(self):
        assert _percentile([10, 20, 30, 40, 50], 0.5) == 30

    def test_median_even(self):
        # Linear interpolation between 20 and 30 at rank=1.5 → 25
        assert _percentile([10, 20, 30, 40], 0.5) == 25

    def test_p25_p75(self):
        prices = [10, 20, 30, 40, 50]
        # ranks: p25 → 1.0 → 20, p75 → 3.0 → 40
        assert _percentile(prices, 0.25) == 20
        assert _percentile(prices, 0.75) == 40


class TestRoundToHundred:
    def test_round_down(self):
        assert _round_to_hundred(22_499) == 22_500

    def test_round_up(self):
        assert _round_to_hundred(22_551) == 22_600

    def test_exact(self):
        assert _round_to_hundred(22_500) == 22_500


class TestExtractAvitoId:
    def test_url(self):
        url = "https://www.avito.ru/moskva/telefony/iphone_13_128gb_4823999"
        assert _extract_avito_id(url) == 4823999

    def test_url_with_query(self):
        url = "https://www.avito.ru/.../iphone_13_4823999?context=abc"
        assert _extract_avito_id(url) == 4823999

    def test_none(self):
        assert _extract_avito_id(None) is None
        assert _extract_avito_id("") is None
        assert _extract_avito_id("not a url") is None


# ---------------------------------------------------------------------------
# _build_report
# ---------------------------------------------------------------------------

def _row(price: int, score: int = 80, *, advantages=None, disadvantages=None) -> CompetitorRow:
    return CompetitorRow(
        avito_id=10_000 + price,
        title=f"iPhone @ {price}",
        price=price,
        url=f"https://avito.ru/lot_{10_000 + price}",
        score=score,
        advantages=advantages or [],
        disadvantages=disadvantages or [],
    )


class TestBuildReport:
    def test_range_and_recommendation(self):
        ref = ReferenceSummary(price=23_500, title="my iPhone")
        rows = [_row(p) for p in [19_500, 20_800, 21_200, 22_300, 23_000, 24_000, 25_000]]
        report = _build_report(ref, competitors_seen=10, rows=rows)
        assert report.range.min == 19_500
        assert report.range.max == 25_000
        assert report.range.median == 22_300  # middle of 7
        assert report.comparable_count == 7
        assert report.competitors_found == 10
        # Recommended = median * 0.95 rounded to 100s
        assert report.recommended_price == 21_200

    def test_top5_split_around_reference(self):
        ref = ReferenceSummary(price=23_500)
        rows = [
            _row(19_500, score=78, disadvantages=["акк 79%"]),
            _row(20_800, score=85),
            _row(22_300, score=95),
            _row(24_000, score=98, advantages=["комплект, чек"]),
            _row(25_000, score=94),
        ]
        report = _build_report(ref, competitors_seen=5, rows=rows)
        cheaper_prices = [r.price for r in report.cheaper_top5]
        pricier_prices = [r.price for r in report.pricier_top5]
        assert all(p < 23_500 for p in cheaper_prices)
        assert all(p > 23_500 for p in pricier_prices)
        # Cheaper sorted by score desc → 22 300 (95), 20 800 (85), 19 500 (78)
        assert cheaper_prices[0] == 22_300
        # Pricier sorted by score desc → 24 000 (98), 25 000 (94)
        assert pricier_prices[0] == 24_000

    def test_empty_rows(self):
        ref = ReferenceSummary(price=10_000)
        report = _build_report(ref, competitors_seen=0, rows=[])
        assert report.range.median is None
        assert report.recommended_price is None
        assert report.cheaper_top5 == []
        assert report.pricier_top5 == []

    def test_conclusion_recommends_drop(self):
        ref = ReferenceSummary(price=23_500)
        rows = [_row(p) for p in [19_500, 20_800, 21_200, 22_300, 23_000, 24_000, 25_000]]
        report = _build_report(ref, competitors_seen=7, rows=rows)
        # 23_500 is above p75 (~24_000? actually rows median=22_300, p75=23_500)
        # Conclusion should reference market position + recommendation if delta exists
        assert "₽" in report.conclusion or report.conclusion == ""
        assert "медиана" in report.conclusion.lower()


# ---------------------------------------------------------------------------
# _collect_competitors
# ---------------------------------------------------------------------------

class FakeMcp:
    """Minimal stand-in for AvitoMcpClient."""

    def __init__(
        self,
        pages: list[SearchPage] | None = None,
        details: dict[int, ListingDetail] | None = None,
        reference: ListingDetail | None = None,
    ) -> None:
        self._pages = list(pages or [])
        self._details = dict(details or {})
        self._reference = reference
        self.fetch_calls: list[tuple[str, int]] = []
        self.detail_calls: list[int | str] = []

    async def fetch_search_page(self, url: str, page: int = 1) -> SearchPage:
        self.fetch_calls.append((url, page))
        if not self._pages:
            return SearchPage(items=[], has_more=False)
        return self._pages.pop(0)

    async def get_listing(self, item_id_or_url: int | str) -> ListingDetail:
        self.detail_calls.append(item_id_or_url)
        if isinstance(item_id_or_url, str):
            if self._reference is None:
                raise RuntimeError("no reference configured")
            return self._reference
        if item_id_or_url not in self._details:
            raise RuntimeError(f"unknown listing {item_id_or_url}")
        return self._details[item_id_or_url]


class FakeAnalyzer:
    def __init__(self, by_id: dict[int, ComparisonResult]) -> None:
        self._by_id = by_id
        self.calls: list[int] = []

    async def compare_to_reference(
        self, competitor, reference, *, model: str | None = None
    ) -> ComparisonResult:
        self.calls.append(competitor.id)
        return self._by_id[competitor.id]


def _short(item_id: int, price: int) -> ListingShort:
    return ListingShort(id=item_id, title=f"lot {item_id}", price=price)


def _detail(item_id: int, price: int, **kw: Any) -> ListingDetail:
    return ListingDetail(
        id=item_id,
        title=kw.get("title", f"lot {item_id}"),
        price=price,
        currency="RUB",
        url=f"https://avito.ru/lot_{item_id}",
        description=kw.get("description", "Хорошее состояние, без сколов."),
        parameters=kw.get("parameters", {"Память": "128 ГБ"}),
    )


@pytest.mark.asyncio
async def test_collect_competitors_paginates_until_cap():
    pages = [
        SearchPage(items=[_short(1, 100), _short(2, 200)], has_more=True),
        SearchPage(items=[_short(3, 300), _short(4, 400)], has_more=True),
        SearchPage(items=[_short(5, 500)], has_more=False),
    ]
    mcp = FakeMcp(pages=pages)
    items = await _collect_competitors(mcp, "http://avito/search", max_competitors=4)
    assert [i.id for i in items] == [1, 2, 3, 4]
    # Stopped after page 2 (cap), didn't fetch page 3
    assert len(mcp.fetch_calls) == 2


@pytest.mark.asyncio
async def test_collect_competitors_respects_has_more_false():
    pages = [SearchPage(items=[_short(1, 100), _short(2, 200)], has_more=False)]
    mcp = FakeMcp(pages=pages)
    items = await _collect_competitors(mcp, "http://avito", max_competitors=10)
    assert [i.id for i in items] == [1, 2]


@pytest.mark.asyncio
async def test_collect_competitors_dedupes_ids():
    pages = [
        SearchPage(items=[_short(1, 100), _short(2, 200)], has_more=True),
        SearchPage(items=[_short(2, 200), _short(3, 300)], has_more=False),
    ]
    mcp = FakeMcp(pages=pages)
    items = await _collect_competitors(mcp, "http://avito", max_competitors=10)
    assert [i.id for i in items] == [1, 2, 3]


# ---------------------------------------------------------------------------
# run_analysis end-to-end
# ---------------------------------------------------------------------------

class FakeSession:
    """Just enough of AsyncSession for the service to add+flush rows."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.flushed = 0

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed += 1


def _make_analysis(
    *,
    reference_url: str | None = None,
    reference_data: dict[str, Any] | None = None,
    search_url: str = "https://avito.ru/moskva/telefony?q=iphone+13",
    max_competitors: int = 30,
) -> PriceAnalysis:
    return PriceAnalysis(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="iPhone 13 Москва",
        reference_listing_url=reference_url,
        reference_data=reference_data or {},
        search_region="moskva",
        competitor_filters={"search_url": search_url},
        max_competitors=max_competitors,
    )


@pytest.mark.asyncio
async def test_run_analysis_happy_path():
    """30 competitors, 5 comparable, builds full report."""
    competitor_prices = [19_500, 20_800, 22_300, 24_000, 25_000]
    pages = [
        SearchPage(
            items=[_short(100 + i, p) for i, p in enumerate(competitor_prices)],
            has_more=False,
        )
    ]
    details = {100 + i: _detail(100 + i, p) for i, p in enumerate(competitor_prices)}
    mcp = FakeMcp(pages=pages, details=details)
    by_id = {
        100 + i: ComparisonResult(
            comparable=True,
            score=70 + i * 5,
            key_advantages=[f"adv{i}"],
            key_disadvantages=[f"dis{i}"],
        )
        for i in range(5)
    }
    analyzer = FakeAnalyzer(by_id)
    analysis = _make_analysis(
        reference_data={"price": 23_500, "title": "my iPhone 13"}
    )
    session = FakeSession()

    run = await run_analysis(session, analysis, mcp=mcp, analyzer=analyzer)

    assert run.status == "success"
    assert run.competitors_found == 5
    assert run.comparable_count == 5
    report = PriceReport.model_validate(run.report)
    assert report.range.min == 19_500
    assert report.range.max == 25_000
    assert report.recommended_price is not None
    # all 5 competitors got compared
    assert len(analyzer.calls) == 5


@pytest.mark.asyncio
async def test_run_analysis_filters_to_comparable():
    competitor_prices = [19_500, 20_800, 22_300]
    pages = [
        SearchPage(
            items=[_short(100 + i, p) for i, p in enumerate(competitor_prices)],
            has_more=False,
        )
    ]
    details = {100 + i: _detail(100 + i, p) for i, p in enumerate(competitor_prices)}
    mcp = FakeMcp(pages=pages, details=details)
    # Only the middle one is comparable
    by_id = {
        100: ComparisonResult(comparable=False, score=10),
        101: ComparisonResult(comparable=True, score=85),
        102: ComparisonResult(comparable=False, score=20),
    }
    analyzer = FakeAnalyzer(by_id)
    analysis = _make_analysis(reference_data={"price": 23_000})
    session = FakeSession()

    run = await run_analysis(session, analysis, mcp=mcp, analyzer=analyzer)

    assert run.status == "success"
    assert run.competitors_found == 3
    assert run.comparable_count == 1


@pytest.mark.asyncio
async def test_run_analysis_no_competitors_failed():
    mcp = FakeMcp(pages=[SearchPage(items=[], has_more=False)])
    analyzer = FakeAnalyzer({})
    analysis = _make_analysis(reference_data={"price": 23_500})
    session = FakeSession()

    run = await run_analysis(session, analysis, mcp=mcp, analyzer=analyzer)
    assert run.status == "failed"
    assert "0 объявлений" in (run.error_message or "")


@pytest.mark.asyncio
async def test_run_analysis_missing_reference_price_failed():
    mcp = FakeMcp(pages=[SearchPage(items=[_short(1, 100)], has_more=False)])
    analyzer = FakeAnalyzer({})
    analysis = _make_analysis(reference_data={})  # no price
    session = FakeSession()

    run = await run_analysis(session, analysis, mcp=mcp, analyzer=analyzer)
    assert run.status == "failed"
    assert "цена эталона" in (run.error_message or "")


@pytest.mark.asyncio
async def test_run_analysis_missing_search_url_failed():
    mcp = FakeMcp(pages=[])
    analyzer = FakeAnalyzer({})
    analysis = PriceAnalysis(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="x",
        reference_data={"price": 100},
        competitor_filters={},  # no search_url
        max_competitors=10,
    )
    session = FakeSession()

    run = await run_analysis(session, analysis, mcp=mcp, analyzer=analyzer)
    assert run.status == "failed"
    assert "search_url" in (run.error_message or "")


@pytest.mark.asyncio
async def test_run_analysis_skips_failed_detail():
    """A failing get_listing for one competitor must not abort the whole run."""
    pages = [SearchPage(items=[_short(1, 100), _short(2, 200)], has_more=False)]
    details = {2: _detail(2, 200)}  # id=1 missing → mcp raises
    mcp = FakeMcp(pages=pages, details=details)
    analyzer = FakeAnalyzer(
        {2: ComparisonResult(comparable=True, score=80)}
    )
    analysis = _make_analysis(reference_data={"price": 150})
    session = FakeSession()

    run = await run_analysis(session, analysis, mcp=mcp, analyzer=analyzer)
    assert run.status == "success"
    assert run.competitors_found == 2  # both seen by search
    assert run.comparable_count == 1   # only id=2 succeeded through


# ---------------------------------------------------------------------------
# export_report_markdown
# ---------------------------------------------------------------------------

def test_export_markdown_includes_key_blocks():
    analysis = _make_analysis(reference_data={"price": 23_500, "title": "my iPhone"})
    rows = [_row(p, score=80) for p in [19_500, 22_300, 25_000]]
    rep = _build_report(
        ReferenceSummary(title="my iPhone", price=23_500),
        competitors_seen=3,
        rows=rows,
    )
    rep_dump = rep.model_dump(mode="json")

    class FakeRun:
        status = "success"
        report = rep_dump
        error_message = None

    md = export_report_markdown(analysis, FakeRun())
    assert "Ценовая разведка" in md
    assert "Медиана" in md
    assert "Рекомендую" in md
    assert "₽" in md


def test_export_markdown_failed_run_short():
    analysis = _make_analysis(reference_data={"price": 100})

    class FailedRun:
        status = "failed"
        report: dict = {}
        error_message = "что-то сломалось"

    md = export_report_markdown(analysis, FailedRun())
    assert "failed" in md
    assert "что-то сломалось" in md
