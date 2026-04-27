"""Pydantic schemas for Price Intelligence (Block 7).

Three tiers:

* :class:`PriceAnalysisBase` / :class:`PriceAnalysisCreate` /
  :class:`PriceAnalysisRead` — the analysis config (the *what*).
* :class:`PriceAnalysisRunRead` — one execution + its result.
* :class:`PriceReport` and helpers — the typed shape of the JSONB
  ``report`` column. Lives here so both the service and the templates
  share one source of truth.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Analysis config
# ---------------------------------------------------------------------------

class PriceAnalysisBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    reference_listing_url: str | None = None
    reference_data: dict[str, Any] = Field(default_factory=dict)
    search_region: str | None = None
    search_radius_km: int | None = Field(None, ge=0)
    competitor_filters: dict[str, Any] = Field(default_factory=dict)
    max_competitors: int = Field(30, ge=1, le=200)
    llm_model: str | None = None
    schedule: str | None = None


class PriceAnalysisCreate(PriceAnalysisBase):
    pass


class PriceAnalysisUpdate(BaseModel):
    """All fields optional for PATCH."""
    name: str | None = None
    reference_listing_url: str | None = None
    reference_data: dict[str, Any] | None = None
    search_region: str | None = None
    search_radius_km: int | None = None
    competitor_filters: dict[str, Any] | None = None
    max_competitors: int | None = Field(None, ge=1, le=200)
    llm_model: str | None = None
    schedule: str | None = None


class PriceAnalysisRead(PriceAnalysisBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Report payload (lives in price_analysis_runs.report JSONB)
# ---------------------------------------------------------------------------

class ReferenceSummary(BaseModel):
    """Reference (own) listing as it appears in the report header."""
    title: str | None = None
    url: str | None = None
    price: int | None = None
    region: str | None = None
    condition: str | None = None
    avito_id: int | None = None


class PriceRange(BaseModel):
    """Five-number summary across comparable competitors."""
    min: int | None = None
    p25: int | None = None
    median: int | None = None
    p75: int | None = None
    max: int | None = None


class CompetitorRow(BaseModel):
    """Single competitor as displayed in cheaper/pricier tables."""
    avito_id: int
    title: str
    price: int
    url: str | None = None
    score: int = 0
    advantages: list[str] = Field(default_factory=list)
    disadvantages: list[str] = Field(default_factory=list)
    price_delta_estimate: int | None = None


class PriceReport(BaseModel):
    """The typed shape of ``price_analysis_runs.report``.

    Mirrors the YAML sample in UI_DESIGN_SPEC §3.6 and the layout
    in §4.6. Empty defaults so the template can render incomplete /
    failed runs without a crash.
    """
    reference: ReferenceSummary = Field(default_factory=ReferenceSummary)
    competitors_found: int = 0
    comparable_count: int = 0
    range: PriceRange = Field(default_factory=PriceRange)
    cheaper_top5: list[CompetitorRow] = Field(default_factory=list)
    pricier_top5: list[CompetitorRow] = Field(default_factory=list)
    recommended_price: int | None = None
    conclusion: str = ""
    histogram_bins: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Run + run-list views
# ---------------------------------------------------------------------------

class PriceAnalysisRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    report: dict[str, Any] = Field(default_factory=dict)
    competitors_found: int = 0
    comparable_count: int = 0
    cost_usd: float | None = None
    error_message: str | None = None


class RunNowResult(BaseModel):
    """Returned by POST /api/price-analyses/{id}/run."""
    run_id: uuid.UUID
    status: str
    competitors_found: int
    comparable_count: int
    error_message: str | None = None
