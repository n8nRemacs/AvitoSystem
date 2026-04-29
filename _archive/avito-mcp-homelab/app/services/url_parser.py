"""Parse Avito search URL into structured params (ADR-001 + ADR-002)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def _regions_by_slug() -> dict[str, dict]:
    raw = json.loads((DATA_DIR / "avito_regions.json").read_text(encoding="utf-8"))
    return {r["slug"]: r for r in raw}


@lru_cache(maxsize=1)
def _categories() -> dict[str, str]:
    return json.loads((DATA_DIR / "avito_categories.json").read_text(encoding="utf-8"))


# Common brand slugs → human names
_BRAND_MAP = {
    "apple": "Apple",
    "samsung": "Samsung",
    "xiaomi": "Xiaomi",
    "honor": "Honor",
    "huawei": "Huawei",
    "sony": "Sony",
    "lg": "LG",
    "google": "Google",
    "oneplus": "OnePlus",
    "asus": "Asus",
    "lenovo": "Lenovo",
    "hp": "HP",
    "dell": "Dell",
    "acer": "Acer",
    "msi": "MSI",
    "nokia": "Nokia",
    "realme": "Realme",
    "oppo": "Oppo",
    "vivo": "Vivo",
    "tecno": "Tecno",
    "infinix": "Infinix",
    "bmw": "BMW",
    "mercedes-benz": "Mercedes-Benz",
    "audi": "Audi",
    "volkswagen": "Volkswagen",
    "toyota": "Toyota",
    "lada": "Lada",
    "kia": "Kia",
    "hyundai": "Hyundai",
}


@dataclass
class ParsedAvitoUrl:
    region_slug: str | None
    region_name: str | None
    region_location_id: int | None
    category_path: str | None  # e.g. "telefony/mobilnye_telefony"
    category_human: str | None  # e.g. "Телефоны / Мобильные телефоны"
    brand: str | None
    model: str | None
    query: str | None  # ?q= keyword
    pmin: int | None
    pmax: int | None
    sort: int | None
    only_with_delivery: bool | None
    radius: int | None
    raw_url: str

    def display_name(self) -> str:
        """Suggest a human-readable profile name based on parsed fields."""
        parts: list[str] = []
        if self.brand and self.model:
            parts.append(f"{self.brand} {self.model}")
        elif self.brand:
            parts.append(self.brand)
        elif self.query:
            parts.append(self.query)
        elif self.category_human:
            parts.append(self.category_human.split(" / ")[-1])
        if self.pmax:
            parts.append(f"до {_short_price(self.pmax)}")
        return " ".join(parts) if parts else "Без названия"


def _short_price(p: int) -> str:
    if p >= 1_000_000:
        return f"{p / 1_000_000:.1f}M".rstrip("0").rstrip(".")
    if p >= 1000:
        return f"{p // 1000}K"
    return str(p)


# Token in slug that looks like the binary `f=` blob
_FILTER_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{12,}$")


def _is_filter_token(s: str) -> bool:
    return bool(_FILTER_TOKEN_RE.match(s)) and any(c.isdigit() for c in s)


def _extract_brand_model_from_slug(slug: str) -> tuple[str | None, str | None]:
    """Avito uses slugs like `apple-ASgBAgICAUSwwQ2OWg` or
    `apple_iphone_12_pro_max-ASgBAg...`.
    Strip trailing filter token, derive brand and optional model."""
    if not slug:
        return None, None
    parts = slug.split("-")
    # Strip trailing tokens that look like base64 filters
    while parts and _is_filter_token(parts[-1]):
        parts.pop()
    if not parts:
        return None, None
    # Now parts may look like ['apple_iphone_12_pro_max'] or ['apple']
    head = "-".join(parts)
    head_parts = head.split("_")

    brand_slug = head_parts[0]
    brand = _BRAND_MAP.get(brand_slug.lower(), brand_slug.replace("_", " ").title())
    model_words = head_parts[1:]
    if not model_words:
        return brand, None
    # Title-case model parts but keep numbers as-is, preserve "pro"/"max" style
    model_parts: list[str] = []
    for w in model_words:
        if w.isdigit():
            model_parts.append(w)
        elif len(w) <= 3:
            model_parts.append(w.title())
        else:
            model_parts.append(w.title())
    return brand, " ".join(model_parts)


def parse_avito_url(url: str) -> ParsedAvitoUrl:
    """Parse Avito search URL into structured fields. Best-effort, never raises."""
    raw = url.strip()
    if not raw:
        raise ValueError("URL пуст")
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if "avito.ru" not in host:
        raise ValueError("Не похоже на URL Avito (домен не avito.ru)")

    # Path
    path = parsed.path.strip("/")
    segments = [s for s in path.split("/") if s]

    region_slug: str | None = None
    region_name: str | None = None
    region_location_id: int | None = None
    if segments:
        candidate = segments[0]
        regions = _regions_by_slug()
        if candidate in regions:
            r = regions[candidate]
            region_slug = candidate
            region_name = r["name"]
            region_location_id = r["location_id"]
            segments = segments[1:]

    # Category path (segments before potential brand-filter segment)
    cats = _categories()
    category_segments: list[str] = []
    brand: str | None = None
    model: str | None = None
    for i, seg in enumerate(segments):
        # If segment matches a known category — keep as category
        if seg in cats:
            category_segments.append(seg)
            continue
        # If segment contains '-' it's likely a brand-filter slug
        if "-" in seg:
            brand, model = _extract_brand_model_from_slug(seg)
            # rest of segments after this — also probably filters, ignore
            break
        # Unknown plain segment — could be a brand without filter token
        if i == len(segments) - 1:
            brand, model = _extract_brand_model_from_slug(seg)
            break
        category_segments.append(seg)

    category_path = "/".join(category_segments) if category_segments else None
    category_human = (
        " / ".join(cats.get(s, s.replace("_", " ").title()) for s in category_segments)
        if category_segments else None
    )

    # Query params
    query = parse_qs(parsed.query)
    def _q(key: str) -> str | None:
        v = query.get(key)
        return v[0] if v else None

    def _qint(key: str) -> int | None:
        v = _q(key)
        if v is None:
            return None
        try:
            return int(v)
        except ValueError:
            return None

    pmin = _qint("pmin")
    pmax = _qint("pmax")
    sort = _qint("s")
    radius = _qint("radius")
    delivery_raw = _q("d")
    only_with_delivery: bool | None
    if delivery_raw == "1":
        only_with_delivery = True
    elif delivery_raw == "0":
        only_with_delivery = False
    else:
        only_with_delivery = None

    keyword = _q("q")

    return ParsedAvitoUrl(
        region_slug=region_slug,
        region_name=region_name,
        region_location_id=region_location_id,
        category_path=category_path,
        category_human=category_human,
        brand=brand,
        model=model,
        query=keyword,
        pmin=pmin,
        pmax=pmax,
        sort=sort,
        only_with_delivery=only_with_delivery,
        radius=radius,
        raw_url=raw,
    )


def apply_overlay(url: str, *, region_slug: str | None,
                  search_min_price: int | None, search_max_price: int | None,
                  only_with_delivery: bool | None, sort: int | None) -> str:
    """Apply overlay parameters from a profile to its base URL. ADR-002.

    - Replaces first path segment if region_slug given
    - Rewrites pmin / pmax / s / d in query string from overlay fields
    """
    from urllib.parse import urlencode, urlunparse

    parsed = urlparse(url)
    path = parsed.path.strip("/")
    segments = [s for s in path.split("/") if s]
    regions = _regions_by_slug()

    if region_slug:
        if segments and segments[0] in regions:
            segments[0] = region_slug
        else:
            segments.insert(0, region_slug)

    new_path = "/" + "/".join(segments) if segments else "/"
    if parsed.path.endswith("/") and not new_path.endswith("/"):
        new_path += "/"

    # Query
    params = parse_qs(parsed.query, keep_blank_values=True)
    if search_min_price is not None:
        params["pmin"] = [str(search_min_price)]
    if search_max_price is not None:
        params["pmax"] = [str(search_max_price)]
    if only_with_delivery is not None:
        params["d"] = ["1" if only_with_delivery else "0"]
    if sort is not None:
        params["s"] = [str(sort)]

    new_query = urlencode([(k, v) for k, vs in params.items() for v in vs])
    return urlunparse((
        parsed.scheme, parsed.netloc, new_path, parsed.params, new_query, parsed.fragment,
    ))


def compute_search_range(alert_min: int | None, alert_max: int | None,
                         widen_pct: float = 0.25) -> tuple[int | None, int | None]:
    """Compute search-вилка from alert-вилка. Default ±25% (ADR-008)."""
    s_min = round(alert_min * (1 - widen_pct)) if alert_min is not None else None
    s_max = round(alert_max * (1 + widen_pct)) if alert_max is not None else None
    return s_min, s_max
