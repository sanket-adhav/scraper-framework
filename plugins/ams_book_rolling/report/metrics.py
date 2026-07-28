"""Derives book-of-business sale metrics from the scraped AMS collections.

Every number this module returns is computed from `output/ams/*.json`. Where the
AMS cannot answer a question (true policy retention, the seller's licence and
E&O standing), the metric is returned as `None` and the renderer prints "not
available" rather than a plausible-looking guess — an inflated retention figure
is the single most misleading number in a book valuation.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

# Policy line nicknames and free-text claim lines describe the same coverages
# with different words; both are folded onto a single canonical label.
_CANONICAL_LINES = {
    "work comp": "Workers Compensation",
    "workers comp": "Workers Compensation",
    "workers compensation": "Workers Compensation",
    "gen. liability": "General Liability",
    "general liability": "General Liability",
    "com. auto": "Commercial Auto",
    "commercial auto": "Commercial Auto",
    "property": "Property",
    "commercial property": "Property",
    "cyber": "Cyber Liability",
    "cyber liability": "Cyber Liability",
    "prof. liab": "Professional Liability",
    "professional liability": "Professional Liability",
    "bop": "Business Owners",
    "business owners": "Business Owners",
    "doli": "Directors & Officers",
    "directors & officers": "Directors & Officers",
    "umbrella": "Umbrella",
    "inland marine": "Inland Marine",
}


def _bucket_floor(label: str) -> float:
    """Lower bound in years of a tenure bucket label.

    '10+ Years' -> 10, '5-10 Years' -> 5, '2-5 Years' -> 2, 'Under 2 Years' -> 0.
    """
    if label.lower().startswith("under"):
        return 0.0
    found = re.findall(r"\d+(?:\.\d+)?", label)
    return min((float(n) for n in found), default=0.0)


def canon_line(raw: str) -> str:
    """Folds a line label from any source onto one canonical coverage name."""
    return _CANONICAL_LINES.get(raw.strip().lower(), raw.strip() or "—")


def money(text: str | None) -> float:
    """Parses '$1,234.50' / '-$470' / '—' into a float; blanks become 0.0."""
    if not text:
        return 0.0
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if cleaned in ("", "-", ".", "-."):
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def num(text: str | None) -> int:
    """Parses an integer out of a cell, tolerating stray punctuation."""
    if not text:
        return 0
    cleaned = re.sub(r"[^0-9\-]", "", text)
    try:
        return int(cleaned)
    except ValueError:
        return 0


def parse_date(text: str) -> date | None:
    """Parses the MM/DD/YYYY dates the AMS renders."""
    try:
        return datetime.strptime(text.strip(), "%m/%d/%Y").date()
    except (ValueError, AttributeError):
        return None


@dataclass
class Book:
    """Every derived figure the report renders, plus the gaps it must disclose."""

    generated_on: date

    # §1 composition
    client_count: int = 0
    policy_count: int = 0
    total_premium: float = 0.0
    avg_premium: float = 0.0
    by_line: list[dict[str, Any]] = field(default_factory=list)
    status_mix: dict[str, int] = field(default_factory=dict)

    # §2 financials
    by_year: list[dict[str, Any]] = field(default_factory=list)
    base_year: int | None = None
    base_revenue: float = 0.0
    cagr: float | None = None
    latest_growth: float | None = None
    valuation: dict[str, float] = field(default_factory=dict)
    receivables_outstanding: float = 0.0
    receivables_past_due: float = 0.0

    # §3 tenure  (true retention is not derivable — see `retention_available`)
    tenure: list[dict[str, Any]] = field(default_factory=list)
    long_tenure_pct: float = 0.0
    retention_available: bool = False

    # §4 client quality
    multiline_pct: float = 0.0
    multiline_count: int = 0
    top10_concentration: float = 0.0
    top_client_share: float = 0.0
    top_clients: list[dict[str, Any]] = field(default_factory=list)
    # With ten or fewer clients "top 10 = 100%" is arithmetic, not concentration.
    concentration_meaningful: bool = True

    # §5 renewal calendar
    calendar: list[dict[str, Any]] = field(default_factory=list)
    peak_months: list[str] = field(default_factory=list)
    renewing_12mo: int = 0
    lapsed_but_active: int = 0
    calendar_start: date | None = None
    calendar_end: date | None = None
    beyond_calendar: int = 0

    # §6 risk
    loss_ratio_rows: list[dict[str, Any]] = field(default_factory=list)
    overall_loss_ratio: float | None = None
    open_claim_reserve: float = 0.0

    # §7 data quality
    data_quality: list[dict[str, Any]] = field(default_factory=list)

    # §8 carriers
    carriers: list[dict[str, Any]] = field(default_factory=list)
    transferable_pct: float = 0.0
    non_transferable_premium: float = 0.0
    reapply_premium: float = 0.0

    # §10 scoring
    scores: list[dict[str, Any]] = field(default_factory=list)
    total_score: float = 0.0
    verdict: str = ""

    gaps: list[str] = field(default_factory=list)


def load(src: Path, name: str) -> dict[str, list[dict[str, str]]]:
    """Reads one scraped file and returns its collections, or {} when absent."""
    path = src / f"{name}.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    record = payload[0] if isinstance(payload, list) else payload
    collections = record.get("collections", {})
    return collections if isinstance(collections, dict) else {}


def build(src: Path, today: date | None = None) -> Book:
    """Computes every report figure from the scraped collections."""
    today = today or date.today()
    book = Book(generated_on=today)

    policies_all = load(src, "policies").get("policies", [])
    cq = load(src, "client_quality")
    commissions = load(src, "commissions")
    claims = load(src, "claims")
    appointments = load(src, "carrier_appointments").get("by_carrier", [])
    aging = load(src, "billing_aging").get("outstanding", [])

    _composition(book, policies_all, cq)
    _financials(book, commissions, aging)
    _tenure(book, cq)
    _client_quality(book, cq)
    _calendar(book, policies_all, today)
    _risk(book, claims)
    _data_quality(book, cq)
    _carriers(book, appointments)
    _score(book)
    return book


# ── §1 composition ──────────────────────────────────────────────────────────
def _composition(book: Book, policies: list[dict[str, str]], cq: dict[str, Any]) -> None:
    """Book size and line-of-business mix, counted on in-force policies only."""
    book.status_mix = dict(Counter(p.get("status", "—") for p in policies))
    active = [p for p in policies if p.get("status") == "Active"]

    book.policy_count = len(active)
    book.total_premium = sum(money(p["premium"]) for p in active)
    book.client_count = len(cq.get("clients", []))
    book.avg_premium = book.total_premium / book.policy_count if book.policy_count else 0.0

    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"policies": 0, "premium": 0.0, "clients": set()}
    )
    for p in active:
        g = grouped[canon_line(p["line_type"])]
        g["policies"] += 1
        g["premium"] += money(p["premium"])
        g["clients"].add(p["client_name"])

    book.by_line = sorted(
        (
            {
                "line": line,
                "clients": len(g["clients"]),
                "policies": g["policies"],
                "premium": g["premium"],
                "share": g["premium"] / book.total_premium if book.total_premium else 0.0,
            }
            for line, g in grouped.items()
        ),
        key=lambda r: -float(r["premium"]),
    )


# ── §2 financials ───────────────────────────────────────────────────────────
def _financials(book: Book, commissions: dict[str, Any], aging: list[dict[str, str]]) -> None:
    """Revenue trend, valuation range, and receivables drag."""
    years = [
        {
            "year": num(y["year"]),
            "statements": num(y["statements"]),
            "expected": money(y["expected"]),
            "received": money(y["received"]),
        }
        for y in commissions.get("by_year", [])
    ]
    years.sort(key=lambda r: int(r["year"]))

    # The current year is usually mid-flight. Treat a trailing year carrying far
    # fewer statements than its predecessor as partial so it cannot understate
    # the valuation base.
    for i, row in enumerate(years):
        prior = years[i - 1]["statements"] if i else 0
        row["partial"] = bool(i and prior and row["statements"] < 0.6 * prior)
        row["growth"] = (
            (row["received"] - years[i - 1]["received"]) / years[i - 1]["received"]
            if i and years[i - 1]["received"]
            else None
        )
    book.by_year = years

    complete = [y for y in years if not y["partial"]]
    if complete:
        base = complete[-1]
        book.base_year = int(base["year"])
        book.base_revenue = float(base["received"])
        book.latest_growth = base["growth"]

        first = complete[0]
        span = len(complete) - 1
        if span and float(first["received"]) > 0:
            book.cagr = (float(base["received"]) / float(first["received"])) ** (1 / span) - 1

        book.valuation = {
            "conservative": book.base_revenue * 1.5,
            "fair": book.base_revenue * 1.75,
            "premium": book.base_revenue * 2.0,
        }

    book.receivables_outstanding = sum(money(r["outstanding"]) for r in aging)
    book.receivables_past_due = sum(
        money(r["outstanding"]) for r in aging if "past" in r.get("age", "").lower()
    )


# ── §3 tenure ───────────────────────────────────────────────────────────────
def _tenure(book: Book, cq: dict[str, Any]) -> None:
    """Client-tenure mix. True retention needs renewal history the AMS does not expose."""
    buckets = [
        {
            "label": t["tenure"],
            "clients": num(t["clients"]),
            "premium": money(t["premium"]),
            "share": num(t["pct_of_book"]) / 100,
        }
        for t in cq.get("by_tenure", [])
    ]
    book.tenure = buckets

    total = sum(int(b["clients"]) for b in buckets) or 1
    # Match on each bucket's lower bound, not on substrings: "2–5 Years" contains
    # a "5" and would otherwise be counted as long-tenured.
    long_lived = sum(int(b["clients"]) for b in buckets if _bucket_floor(str(b["label"])) >= 5)
    book.long_tenure_pct = long_lived / total

    # A renewed-vs-lapsed ratio needs prior-term outcomes per policy; the grid
    # exposes only current status, so no honest retention rate can be derived.
    book.retention_available = False
    book.gaps.append(
        "Policy retention rate — needs renewal history (renewed vs. lapsed per term), "
        "which no AMS screen exposes. Client tenure is shown instead."
    )


# ── §4 client quality ───────────────────────────────────────────────────────
def _client_quality(book: Book, cq: dict[str, Any]) -> None:
    """Multi-line penetration and revenue concentration."""
    clients = [
        {
            "client": c["client"],
            "opened": c["opened"],
            "tenure": float(re.sub(r"[^0-9.]", "", c["tenure"]) or 0),
            "policies": num(c["policies"]),
            "premium": money(c["premium"]),
            "share": money(c["pct_of_book"]) / 100,
            "email": c["has_email"] == "Yes",
            "phone": c["has_phone"] == "Yes",
            "address": c["address_status"] == "Verified",
        }
        for c in cq.get("clients", [])
    ]
    clients.sort(key=lambda r: -float(r["premium"]))

    book.top_clients = clients[:10]
    book.multiline_count = sum(1 for c in clients if int(c["policies"]) >= 2)
    book.multiline_pct = book.multiline_count / len(clients) if clients else 0.0

    total = sum(float(c["premium"]) for c in clients) or 1.0
    book.top10_concentration = sum(float(c["premium"]) for c in clients[:10]) / total
    book.top_client_share = float(clients[0]["premium"]) / total if clients else 0.0
    book.concentration_meaningful = len(clients) > 10
    if not book.concentration_meaningful:
        book.gaps.append(
            f"Top-10 revenue concentration is {book.top10_concentration:.0%} only because the "
            f"book holds {len(clients)} clients in total — with ten or fewer clients the figure "
            "is arithmetic, not a concentration signal. Largest-single-client share is used for "
            "scoring instead."
        )


# ── §5 renewal calendar ─────────────────────────────────────────────────────
def _calendar(book: Book, policies: list[dict[str, str]], today: date) -> None:
    """Twelve forward months of expiring in-force premium."""
    active = [p for p in policies if p.get("status") == "Active"]
    months: dict[tuple[int, int], dict[str, Any]] = {}
    cursor = date(today.year, today.month, 1)
    for _ in range(12):
        months[(cursor.year, cursor.month)] = {
            "label": cursor.strftime("%b %Y"),
            "count": 0,
            "premium": 0.0,
        }
        cursor = date(cursor.year + 1, 1, 1) if cursor.month == 12 else date(
            cursor.year, cursor.month + 1, 1
        )

    for p in active:
        exp = parse_date(p["expiration_date"])
        # Only forward-dated expirations: a policy expiring earlier this month has
        # already lapsed and belongs in the hygiene count, not the renewal calendar.
        if exp and exp >= today and (exp.year, exp.month) in months:
            bucket = months[(exp.year, exp.month)]
            bucket["count"] += 1
            bucket["premium"] += money(p["premium"])

    book.calendar = list(months.values())
    book.renewing_12mo = sum(int(m["count"]) for m in book.calendar)

    # The grid holds whole calendar months, so its window ends before the last
    # bucket rolls over. State that range rather than implying the policies
    # falling just past it never renew.
    first, last = min(months), max(months)
    book.calendar_start = date(first[0], first[1], 1)
    book.calendar_end = (
        date(last[0] + 1, 1, 1) if last[1] == 12 else date(last[0], last[1] + 1, 1)
    )
    book.beyond_calendar = sum(
        1
        for p in active
        if (d := parse_date(p["expiration_date"])) and d >= book.calendar_end
    )

    # Policies still flagged Active whose expiration has already passed: a real
    # hygiene finding for a buyer, and the reason the calendar can hold fewer
    # policies than the in-force count.
    book.lapsed_but_active = sum(
        1 for p in active if (d := parse_date(p["expiration_date"])) and d < today
    )
    if book.lapsed_but_active:
        book.gaps.append(
            f"{book.lapsed_but_active} of {len(active)} policies are still flagged Active "
            "despite an expiration date in the past. They are counted in premium in force but "
            "cannot appear in the forward renewal calendar — the status field needs a clean-up "
            "pass before these figures are relied on."
        )

    # Only call out a peak when one stands clearly above the average month AND
    # few months tie for it — on a small book half the year routinely ties, which
    # is the opposite of a concentrated renewal season.
    counts = [int(m["count"]) for m in book.calendar]
    busiest = max(counts, default=0)
    average = sum(counts) / len(counts) if counts else 0
    tied = [str(m["label"]) for m in book.calendar if int(m["count"]) == busiest]
    if busiest and busiest >= max(average * 1.5, 2) and len(tied) <= 3:
        book.peak_months = tied


# ── §6 risk ─────────────────────────────────────────────────────────────────
def _risk(book: Book, claims: dict[str, Any]) -> None:
    """Loss ratio per line: incurred (paid + reserve) against in-force premium."""
    premium_by_line = {str(r["line"]): float(r["premium"]) for r in book.by_line}

    rows = []
    for c in claims.get("by_line", []):
        line = canon_line(c["line"])
        paid = money(c["paid"])
        reserve = money(c["reserve"])
        premium = premium_by_line.get(line, 0.0)
        rows.append(
            {
                "line": line,
                "claims": num(c["claims"]),
                "open": num(c["open_claims"]),
                "paid": paid,
                "reserve": reserve,
                "incurred": paid + reserve,
                "premium": premium,
                "loss_ratio": (paid + reserve) / premium if premium else None,
            }
        )
    rows.sort(key=lambda r: -float(r["incurred"]))
    book.loss_ratio_rows = rows

    incurred = sum(float(r["incurred"]) for r in rows)
    covered = sum(float(r["premium"]) for r in rows if r["premium"])
    book.overall_loss_ratio = incurred / covered if covered else None
    book.open_claim_reserve = sum(
        money(s["reserve"])
        for s in claims.get("by_status", [])
        if s["status"] in ("Open", "In Progress", "InProgress")
    )


# ── §7 data quality ─────────────────────────────────────────────────────────
def _data_quality(book: Book, cq: dict[str, Any]) -> None:
    """Contact-data completeness across the roster."""
    book.data_quality = [
        {
            "metric": d["metric"],
            "complete": d["complete"],
            "coverage": money(d["coverage"]) / 100,
        }
        for d in cq.get("data_quality", [])
    ]


# ── §8 carriers ─────────────────────────────────────────────────────────────
def _carriers(book: Book, appointments: list[dict[str, str]]) -> None:
    """Carrier concentration, commission rates, and appointment transferability."""
    rows = [
        {
            "carrier": c["carrier"],
            "policies": num(c["policies"]),
            "premium": money(c["premium"]),
            "share": money(c["pct_of_book"]) / 100,
            "rate": money(c["commission_rate"]) / 100 if c["commission_rate"] != "—" else None,
            "transferable": c["transferable"],
        }
        for c in appointments
        if num(c["policies"]) > 0
    ]
    rows.sort(key=lambda r: -float(r["premium"]))
    book.carriers = rows

    total = sum(float(r["premium"]) for r in rows) or 1.0
    book.transferable_pct = (
        sum(float(r["premium"]) for r in rows if "Direct" in str(r["transferable"])) / total
    )
    book.non_transferable_premium = sum(
        float(r["premium"]) for r in rows if "Non-transferable" in str(r["transferable"])
    )
    book.reapply_premium = sum(
        float(r["premium"]) for r in rows if "Re-apply" in str(r["transferable"])
    )


# ── §10 scoring ─────────────────────────────────────────────────────────────
def _score(book: Book) -> None:
    """Weighted 0–100 score over the dimensions the scraped data can support.

    The seller-trust dimension is excluded rather than guessed, and the
    remaining weights are rescaled to sum to 1 so the total stays out of 100.
    """
    lines = len(book.by_line)
    diversification = min(lines / 6, 1.0)
    largest_line = max((float(r["share"]) for r in book.by_line), default=1.0)

    growth = book.latest_growth if book.latest_growth is not None else 0.0
    loss = book.overall_loss_ratio

    dims = [
        (
            "Book Size & Composition",
            0.15,
            round(100 * (0.5 * diversification + 0.5 * (1 - min(largest_line, 1.0)))),
            f"{book.policy_count} policies across {lines} lines",
        ),
        (
            "Financial Valuation",
            0.25,
            round(100 * max(0.0, min(1.0, 0.5 + growth * 5))),
            f"{growth:+.1%} YoY on {book.base_year} revenue" if book.base_year else "no trend",
        ),
        (
            "Retention & Longevity",
            0.25,
            round(100 * book.long_tenure_pct),
            f"{book.long_tenure_pct:.0%} of clients 5+ years (tenure proxy)",
        ),
        (
            "Client Quality",
            0.15,
            # Largest-single-client share is the concentration signal that holds on
            # any book size; a 5% share or lower scores clean.
            round(100 * (0.6 * book.multiline_pct
                         + 0.4 * max(0.0, 1 - book.top_client_share / 0.25))),
            f"{book.multiline_pct:.0%} multi-line, largest client "
            f"{book.top_client_share:.1%}"
            + ("" if book.concentration_meaningful else " (top-10 n/m on a 10-client book)"),
        ),
        (
            "Risk Assessment",
            0.10,
            round(
                100
                * (
                    0.5 * (1 - min(loss, 1.0) if loss is not None else 0.5)
                    + 0.5 * book.transferable_pct
                )
            ),
            (
                f"loss ratio {loss:.0%}, " if loss is not None else "loss ratio n/a, "
            )
            + f"{book.transferable_pct:.0%} transferable",
        ),
        (
            "Data Quality",
            0.10,
            round(
                100
                * (
                    sum(float(d["coverage"]) for d in book.data_quality) / len(book.data_quality)
                    if book.data_quality
                    else 0.0
                )
            ),
            "contact-data completeness",
        ),
    ]

    weight_sum = sum(w for _, w, _, _ in dims)
    book.scores = [
        {
            "dimension": name,
            "score": score,
            "weight": weight / weight_sum,
            "weighted": score * weight / weight_sum,
            "note": note,
        }
        for name, weight, score, note in dims
    ]
    book.total_score = sum(float(s["weighted"]) for s in book.scores)

    book.verdict = (
        "Strong Buy"
        if book.total_score >= 75
        else "Buy — with conditions"
        if book.total_score >= 60
        else "Proceed with caution"
        if book.total_score >= 45
        else "High risk"
    )

    book.gaps.append(
        "Seller trust profile (licence standing, E&O cover, regulatory complaints, "
        "non-compete terms) is not agency-management data — it comes from state DOI "
        "records and legal review. Excluded from the score rather than estimated."
    )
