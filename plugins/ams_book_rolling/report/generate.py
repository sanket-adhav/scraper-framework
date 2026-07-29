#!/usr/bin/env python3
"""Renders the Book of Business sale-evaluation report from the scraped AMS data.

    .venv/bin/python plugins/ams_book_rolling/report/generate.py \
        --src output/ams --out output/book_rolling_report.html

Metrics come from `metrics.py`; this module only formats them. Anything the AMS
cannot answer is rendered as an explicit "not available" panel rather than a
filled-in guess.
"""

from __future__ import annotations

import argparse
import html
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from metrics import Book, build  # noqa: E402

# ── formatting helpers ──────────────────────────────────────────────────────


def usd(v: float | None, cents: bool = False) -> str:
    """Formats a dollar amount; None renders as an em dash."""
    if v is None:
        return "—"
    return f"${v:,.2f}" if cents else f"${v:,.0f}"


def usd_k(v: float) -> str:
    """Compact dollars for tight cells: $1.8M / $104K / $940."""
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:,.0f}"


def pct(v: float | None, places: int = 0) -> str:
    """Formats a 0–1 ratio as a percentage; None renders as an em dash."""
    return "—" if v is None else f"{v * 100:.{places}f}%"


def signed_pct(v: float | None) -> str:
    """Formats a growth ratio with an explicit sign."""
    return "—" if v is None else f"{v * 100:+.1f}%"


def e(text: object) -> str:
    """HTML-escapes any value for safe interpolation."""
    return html.escape(str(text))


def band(value: float, good: float, ok: float, invert: bool = False) -> str:
    """Picks a green/yellow/red class from a threshold pair."""
    if invert:
        return "green" if value <= good else "yellow" if value <= ok else "red"
    return "green" if value >= good else "yellow" if value >= ok else "red"


def badge(text: str, tone: str) -> str:
    """Renders a coloured pill."""
    return f'<span class="badge badge-{tone}">{e(text)}</span>'


# ── section renderers ───────────────────────────────────────────────────────


def _cover(b: Book, agency: str, prepared_for: str) -> str:
    val = b.valuation
    range_text = (
        f"{usd_k(val['conservative'])} – {usd_k(val['premium'])}" if val else "not derivable"
    )
    return f"""
<div class="cover">
  <div class="cover-top">
    <div>
      <h1>Insurance Book of Business</h1>
      <h2>Sale &amp; Valuation Evaluation Report</h2>
    </div>
    <div class="cover-badge">
      <div class="label">Report Date</div>
      <div class="value">{b.generated_on:%B %Y}</div>
    </div>
  </div>
  <div class="cover-meta">
    <div><span class="lbl">Agency</span><span class="val">{e(agency)}</span></div>
    <div><span class="lbl">Prepared For</span><span class="val">{e(prepared_for)}</span></div>
    <div><span class="lbl">Clients</span><span class="val">{b.client_count}</span></div>
    <div><span class="lbl">Policies In Force</span><span class="val">{b.policy_count}</span></div>
    <div><span class="lbl">Premium In Force</span><span class="val">{usd_k(b.total_premium)}</span></div>
    <div><span class="lbl">Report Type</span><span class="val">Book Rolling — Buyer Evaluation</span></div>
  </div>
</div>

<div class="score-banner">
  <div class="score-card">
    <div class="sc-label">Total Clients</div>
    <div class="sc-value blue">{b.client_count}</div>
    <div class="sc-sub">active policyholders</div>
  </div>
  <div class="score-card">
    <div class="sc-label">Annual Revenue</div>
    <div class="sc-value green">{usd(b.base_revenue)}</div>
    <div class="sc-sub">commission, FY {b.base_year or "—"}</div>
  </div>
  <div class="score-card">
    <div class="sc-label">Clients 5+ Years</div>
    <div class="sc-value {band(b.long_tenure_pct, 0.6, 0.4)}">{pct(b.long_tenure_pct)}</div>
    <div class="sc-sub">tenure (retention n/a)</div>
  </div>
  <div class="score-card">
    <div class="sc-label">Est. Book Value</div>
    <div class="sc-value blue">{range_text}</div>
    <div class="sc-sub">1.5x – 2.0x revenue</div>
  </div>
  <div class="score-card">
    <div class="sc-label">Overall Score</div>
    <div class="sc-value {band(b.total_score, 75, 60)}">{b.total_score:.0f} / 100</div>
    <div class="sc-sub">{e(b.verdict)}</div>
  </div>
</div>
"""


def _section(num: int, icon: str, tone: str, title: str, subtitle: str, body: str) -> str:
    return f"""
<div class="section">
  <div class="section-header">
    <div class="section-icon icon-{tone}">{icon}</div>
    <div>
      <div class="section-title">{num}. {e(title)}</div>
      <div class="section-subtitle">{e(subtitle)}</div>
    </div>
  </div>
  <div class="section-body">{body}</div>
</div>
"""


def _composition(b: Book) -> str:
    rows = "".join(
        f"""<tr>
          <td>{e(r["line"])}</td>
          <td class="num">{r["clients"]}</td>
          <td class="num">{r["policies"]}</td>
          <td class="num">{usd(r["premium"])}</td>
          <td class="num">{pct(r["share"], 1)}</td>
        </tr>"""
        for r in b.by_line
    )
    status = " · ".join(f"{e(k)}: {v}" for k, v in sorted(b.status_mix.items()))
    return f"""
<div class="stat-grid">
  <div class="stat-box"><div class="sb-label">Total Clients</div>
    <div class="sb-value">{b.client_count}</div><div class="sb-note">active policyholders</div></div>
  <div class="stat-box"><div class="sb-label">Policies In Force</div>
    <div class="sb-value">{b.policy_count}</div>
    <div class="sb-note">{b.policy_count / b.client_count if b.client_count else 0:.2f} per client</div></div>
  <div class="stat-box"><div class="sb-label">Annual Premium</div>
    <div class="sb-value">{usd_k(b.total_premium)}</div><div class="sb-note">written, in force</div></div>
  <div class="stat-box"><div class="sb-label">Avg Premium / Policy</div>
    <div class="sb-value">{usd(b.avg_premium)}</div><div class="sb-note">per active policy</div></div>
</div>

<table style="margin-top:20px;">
  <thead><tr><th>Line of Business</th><th>Clients</th><th>Policies</th>
    <th>Annual Premium</th><th>% of Book</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<div class="note">Policy status mix across all {sum(b.status_mix.values())} records — {status}.
  Only <strong>Active</strong> policies are counted above.</div>
"""


def _financials(b: Book) -> str:
    rows = "".join(
        f"""<tr>
          <td>{r["year"]}{" <span class='muted'>(partial)</span>" if r["partial"] else ""}</td>
          <td class="num">{r["statements"]}</td>
          <td class="num">{usd(r["expected"])}</td>
          <td class="num">{usd(r["received"])}</td>
          <td class="num {"green" if (r["growth"] or 0) > 0 else "red" if r["growth"] else ""}">
            {signed_pct(r["growth"])}</td>
        </tr>"""
        for r in b.by_year
    )

    if b.valuation:
        v = b.valuation
        val_block = f"""
<div class="val-box">
  <div class="vb-label">Estimated Purchase Price Range</div>
  <div class="vb-range">{usd_k(v["conservative"])} – {usd_k(v["premium"])}</div>
  <div class="vb-note">1.5x – 2.0x FY {b.base_year} commission revenue</div>
  <div class="val-grid">
    <div class="val-item"><div class="vi-label">Conservative (1.5x)</div>
      <div class="vi-value">{usd(v["conservative"])}</div></div>
    <div class="val-item"><div class="vi-label">Fair Value (1.75x)</div>
      <div class="vi-value">{usd(v["fair"])}</div></div>
    <div class="val-item"><div class="vi-label">Premium (2.0x)</div>
      <div class="vi-value">{usd(v["premium"])}</div></div>
    <div class="val-item"><div class="vi-label">3-Yr CAGR</div>
      <div class="vi-value">{signed_pct(b.cagr)}</div></div>
  </div>
</div>"""
    else:
        val_block = '<div class="unavailable">No complete revenue year — valuation not derivable.</div>'

    return f"""
<div class="two-col">
  <div>
    <div class="stat-grid" style="grid-template-columns:1fr 1fr; margin-bottom:16px;">
      <div class="stat-box"><div class="sb-label">Commission Revenue</div>
        <div class="sb-value">{usd(b.base_revenue)}</div>
        <div class="sb-note">FY {b.base_year or "—"} actual</div></div>
      <div class="stat-box"><div class="sb-label">YoY Growth</div>
        <div class="sb-value {band(b.latest_growth or 0, 0.05, 0)}">{signed_pct(b.latest_growth)}</div>
        <div class="sb-note">vs. prior year</div></div>
      <div class="stat-box"><div class="sb-label">Receivables Outstanding</div>
        <div class="sb-value">{usd_k(b.receivables_outstanding)}</div>
        <div class="sb-note">{usd_k(b.receivables_past_due)} past due</div></div>
      <div class="stat-box"><div class="sb-label">Effective Commission</div>
        <div class="sb-value">{pct(b.base_revenue / b.total_premium if b.total_premium else None, 1)}</div>
        <div class="sb-note">revenue ÷ premium</div></div>
    </div>
    <table>
      <thead><tr><th>Year</th><th>Statements</th><th>Expected</th>
        <th>Received</th><th>YoY Growth</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  {val_block}
</div>
"""


def _retention(b: Book) -> str:
    bars = "".join(
        f"""<div class="rating-row">
          <span class="rating-label">{e(r["label"])}</span>
          <div class="rating-bar-wrap"><div class="rating-bar bar-green"
            style="width:{min(r["share"] * 100, 100):.0f}%"></div></div>
          <span class="rating-pct">{pct(r["share"])}</span>
        </div>"""
        for r in b.tenure
    )
    rows = "".join(
        f"""<tr><td>{e(r["label"])}</td><td class="num">{r["clients"]}</td>
          <td class="num">{pct(r["share"])}</td><td class="num">{usd(r["premium"])}</td>
          <td>{badge(*_tenure_risk(str(r["label"])))}</td></tr>"""
        for r in b.tenure
    )
    return f"""
<div class="unavailable">
  <strong>Policy retention rate is not available.</strong> A true retention figure needs
  renewal history — which policies renewed versus lapsed at each term — and no AMS screen
  exposes it. Client <em>tenure</em> is shown below as the closest supportable proxy.
  It measures how long relationships have lasted, not how reliably policies renew.
</div>
<div class="two-col" style="margin-top:16px;">
  <div>{bars}</div>
  <div>
    <table>
      <thead><tr><th>Client Tenure</th><th>Clients</th><th>% of Book</th>
        <th>Premium</th><th>Risk</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    <div class="callout callout-good">
      <strong>{pct(b.long_tenure_pct)} of clients have been with the agency 5+ years.</strong>
    </div>
  </div>
</div>
"""


def _tenure_risk(label: str) -> tuple[str, str]:
    if "10+" in label:
        return "Low Risk", "green"
    if "5" in label:
        return "Low Risk", "green"
    if "2" in label:
        return "Medium", "yellow"
    return "Higher Risk", "red"


def _client_quality(b: Book) -> str:
    top10_value = pct(b.top10_concentration) + (
        "" if b.concentration_meaningful else " <span class='muted'>(n/m)</span>"
    )
    metrics = [
        ("Multi-line clients (2+ policies)", f"{b.multiline_count} ({pct(b.multiline_pct)})",
         "~45%", *_cmp(b.multiline_pct, 0.45)),
        ("Top 10 clients % of revenue", top10_value, "&lt;25%",
         *(("Not Meaningful", "blue") if not b.concentration_meaningful
           else _cmp(0.25, b.top10_concentration, higher_better=False))),
        ("Largest single client", pct(b.top_client_share, 1), "&lt;5%",
         *_cmp(0.05, b.top_client_share, higher_better=False)),
    ]
    mrows = "".join(
        f"""<tr><td>{e(n)}</td><td class="num">{v}</td>
          <td class="num">{bm}</td><td>{badge(lbl, tone)}</td></tr>"""
        for n, v, bm, lbl, tone in metrics
    )
    crows = "".join(
        f"""<tr><td class="num">{i}</td><td>{e(c["client"])}</td>
          <td class="num">{usd(c["premium"])}</td><td class="num">{c["policies"]}</td>
          <td class="num">{pct(c["share"], 1)}</td><td class="num">{c["tenure"]:.1f} yr</td></tr>"""
        for i, c in enumerate(b.top_clients, 1)
    )
    return f"""
<div class="two-col">
  <div>
    <table>
      <thead><tr><th>Metric</th><th>Value</th><th>Benchmark</th><th>Rating</th></tr></thead>
      <tbody>{mrows}</tbody>
    </table>
    <div class="note">Benchmarks are common broker-market rules of thumb, not figures
      from this agency's data.
      {"" if b.concentration_meaningful else
       f"<br><strong>Top-10 concentration is not meaningful here:</strong> the book holds "
       f"{b.client_count} clients in total, so the top ten are by definition 100% of revenue. "
       "Largest-single-client share is the usable concentration signal."}</div>
  </div>
  <div>
    <div class="col-title">Top Clients by Premium</div>
    <table>
      <thead><tr><th>#</th><th>Client</th><th>Premium</th><th>Policies</th>
        <th>% of Book</th><th>Tenure</th></tr></thead>
      <tbody>{crows}</tbody>
    </table>
  </div>
</div>
"""


def _cmp(value: float, benchmark: float, higher_better: bool = True) -> tuple[str, str]:
    better = value >= benchmark if higher_better else value <= benchmark
    return ("Above Avg", "green") if better else ("Below Avg", "yellow")


def _calendar(b: Book) -> str:
    peak = max((int(m["count"]) for m in b.calendar), default=0)
    cells = "".join(
        f"""<div class="cal-month{" hot" if int(m["count"]) == peak and peak else ""}">
          <div class="cm-name">{e(str(m["label"])[:3])}</div>
          <div class="cm-count">{m["count"]}</div>
          <div class="cm-prem">{usd_k(float(m["premium"]))}</div>
        </div>"""
        for m in b.calendar
    )
    peak_note = (
        f"<strong>Peak renewal month(s): {e(', '.join(b.peak_months))}</strong> — "
        f"plan cash flow and servicing capacity around these."
        if b.peak_months
        else "<strong>No pronounced renewal peak</strong> — expirations are spread "
             "fairly evenly across the year, which smooths the buyer's servicing load."
    )
    stale = (
        f"""<div class="unavailable" style="margin-top:12px;">
      <strong>{b.lapsed_but_active} policies are flagged Active but already past their
      expiration date.</strong> They count toward premium in force yet cannot appear in a
      forward calendar, which is why only {b.renewing_12mo} of {b.policy_count} policies are
      shown above. Treat this as a data-hygiene item to resolve before closing.</div>"""
        if b.lapsed_but_active
        else ""
    )
    return f"""
<div class="cal-grid">{cells}</div>
<div class="callout {"callout-warn" if b.peak_months else "callout-good"}">{peak_note}</div>
<div class="note">{b.renewing_12mo} of {b.policy_count} in-force policies expire between
  {b.calendar_start:%b %Y} and {b.calendar_end:%b %Y}{
    f"; the remaining {b.beyond_calendar} fall just beyond this window and renew in the "
    f"following month" if b.beyond_calendar else ""}.</div>
{stale}
"""


def _risk(b: Book) -> str:
    rows = "".join(
        f"""<tr>
          <td>{e(r["line"])}</td><td class="num">{r["claims"]}</td>
          <td class="num">{r["open"]}</td><td class="num">{usd(r["paid"])}</td>
          <td class="num">{usd(r["reserve"])}</td><td class="num">{usd(r["premium"])}</td>
          <td class="num">{pct(r["loss_ratio"])}</td>
          <td>{badge(*_loss_band(r["loss_ratio"]))}</td>
        </tr>"""
        for r in b.loss_ratio_rows
    )
    items = []
    items.append(_risk_card(
        "Revenue Concentration",
        b.top10_concentration <= 0.5,
        b.top10_concentration <= 0.7,
        f"Top 10 clients hold {pct(b.top10_concentration)} of premium; "
        f"largest single client {pct(b.top_client_share, 1)}.",
    ))
    items.append(_risk_card(
        "Loss Ratio",
        (b.overall_loss_ratio or 1) <= 0.6,
        (b.overall_loss_ratio or 1) <= 0.75,
        f"Incurred (paid + reserve) against in-force premium is "
        f"{pct(b.overall_loss_ratio)} across lines with claims activity.",
    ))
    items.append(_risk_card(
        "Carrier Transferability",
        b.transferable_pct >= 0.9,
        b.transferable_pct >= 0.7,
        f"{pct(b.transferable_pct)} of premium transfers directly. "
        f"{usd_k(b.reapply_premium)} sits with appointments needing buyer re-application"
        + (f"; {usd_k(b.non_transferable_premium)} is non-transferable."
           if b.non_transferable_premium else "."),
    ))
    items.append(_risk_card(
        "Open Claim Exposure",
        b.open_claim_reserve <= 0.1 * b.total_premium,
        b.open_claim_reserve <= 0.25 * b.total_premium,
        f"{usd_k(b.open_claim_reserve)} reserved on open and in-progress claims, "
        f"{pct(b.open_claim_reserve / b.total_premium if b.total_premium else None)} of premium.",
    ))
    items.append(_risk_card(
        "Receivables",
        b.receivables_past_due == 0,
        b.receivables_past_due <= 0.05 * b.total_premium,
        f"{usd_k(b.receivables_outstanding)} outstanding, of which "
        f"{usd_k(b.receivables_past_due)} is past due.",
    ))
    items.append(
        '<div class="risk-item risk-unknown"><div class="ri-title">E&amp;O / Non-Compete — UNKNOWN</div>'
        '<div class="ri-desc">Not agency-management data. Requires legal review and the '
        "seller's E&amp;O certificate — see section 9.</div></div>"
    )

    return f"""
<div class="risk-grid">{"".join(items)}</div>
<div class="col-title" style="margin-top:20px;">Loss Ratio by Line of Business</div>
<table>
  <thead><tr><th>Line</th><th>Claims</th><th>Open</th><th>Paid</th><th>Reserve</th>
    <th>Premium In Force</th><th>Loss Ratio</th><th>Status</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<div class="note">Loss ratio here is <strong>incurred (paid + reserve) ÷ in-force annual
  premium</strong>. Lines with no claims activity are omitted. Because reserves on open
  claims may develop, these ratios are indicative rather than final.</div>
"""


def _risk_card(title: str, good: bool, ok: bool, desc: str) -> str:
    tone = "low" if good else "medium" if ok else "high"
    label = "LOW" if good else "MEDIUM" if ok else "HIGH"
    return (
        f'<div class="risk-item risk-{tone}"><div class="ri-title">{e(title)} — {label}</div>'
        f'<div class="ri-desc">{desc}</div></div>'
    )


def _loss_band(ratio: float | None) -> tuple[str, str]:
    if ratio is None:
        return "No Premium", "blue"
    if ratio <= 0.5:
        return "Excellent", "green"
    if ratio <= 0.65:
        return "Good", "green"
    if ratio <= 0.8:
        return "Watch", "yellow"
    return "Elevated", "red"


def _data_quality(b: Book) -> str:
    icons = {"Email": "📧", "Phone": "📱", "Address": "🏠"}
    cells = "".join(
        f"""<div class="dq-item">
          <div class="dq-icon">{next((v for k, v in icons.items() if k in str(d["metric"])), "🗄️")}</div>
          <div class="dq-label">{e(d["metric"])}</div>
          <div class="dq-pct {band(float(d["coverage"]), 0.9, 0.75)}">{pct(d["coverage"])}</div>
          <div class="dq-count">{e(d["complete"])} clients</div>
        </div>"""
        for d in b.data_quality
    )
    return f"""
<div class="dq-grid">{cells}
  <div class="dq-item"><div class="dq-icon">💾</div>
    <div class="dq-label">Export Ready</div>
    <div class="dq-pct green">Yes</div>
    <div class="dq-count">scraped to JSON</div></div>
</div>
<div class="note">Completeness is measured across all {b.client_count} client records in the AMS.</div>
"""


def _carriers(b: Book) -> str:
    rows = "".join(
        f"""<tr>
          <td>{e(c["carrier"])}</td><td class="num">{c["policies"]}</td>
          <td class="num">{usd(c["premium"])}</td><td class="num">{pct(c["share"], 1)}</td>
          <td class="num">{pct(c["rate"], 1)}</td>
          <td>{badge(str(c["transferable"]), _transfer_tone(str(c["transferable"])))}</td>
        </tr>"""
        for c in b.carriers
    )
    return f"""
<table>
  <thead><tr><th>Carrier</th><th>Policies</th><th>Annual Premium</th><th>% of Book</th>
    <th>Avg Commission</th><th>Transferable</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<div class="callout {"callout-good" if b.transferable_pct >= 0.9 else "callout-warn"}">
  <strong>{pct(b.transferable_pct)} of in-force premium</strong> sits with appointments that
  transfer directly to a buyer. {usd_k(b.reapply_premium)} requires the buyer to re-apply for
  the appointment — typically a 30–60 day delay{
    f", and {usd_k(b.non_transferable_premium)} cannot transfer at all"
    if b.non_transferable_premium else ""}.
</div>
<div class="note">Wholesalers and brokers holding no in-force premium are excluded. Commission
  rate is the mean of the per-product rates configured for each carrier.</div>
"""


def _transfer_tone(text: str) -> str:
    if "Direct" in text:
        return "green"
    if "Re-apply" in text:
        return "yellow"
    if "Non-transferable" in text:
        return "red"
    return "blue"


def _trust() -> str:
    rows = "".join(
        f"""<tr><td>{e(f)}</td><td class="muted">not in AMS</td>
          <td>{badge("Manual Check", "blue")}</td></tr>"""
        for f in (
            "Licence status and states appointed",
            "Years in continuous operation",
            "E&O coverage — limits and expiry",
            "Regulatory complaints (NAIC / state DOI)",
            "Tax and financial standing (liens, judgments)",
            "Non-compete / non-solicit obligations",
            "Client references",
        )
    )
    return f"""
<div class="unavailable">
  <strong>This section cannot be populated from AMS data.</strong> Every item below comes
  from an external source — state DOI records, the seller's E&amp;O certificate, NAIC
  complaint lookup, or legal review of the seller's agency agreement. They are listed so
  the buyer's checklist stays complete, not because the data was found and omitted.
</div>
<table style="margin-top:16px;">
  <thead><tr><th>Trust Factor</th><th>Source</th><th>Status</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
"""


def _score(b: Book) -> str:
    rows = "".join(
        f"""<tr>
          <td>{e(s["dimension"])}</td>
          <td class="num {band(float(s["score"]), 75, 55)}">{s["score"]:.0f}/100</td>
          <td class="num">{pct(s["weight"])}</td>
          <td class="num">{s["weighted"]:.2f}</td>
          <td class="muted">{e(s["note"])}</td>
        </tr>"""
        for s in b.scores
    )
    gaps = "".join(f"<li>{e(g)}</li>" for g in b.gaps)
    return f"""
<div class="overall-score">
  <div class="os-circle">
    <div class="os-num">{b.total_score:.0f}</div>
    <div class="os-den">/ 100</div>
  </div>
  <div class="os-details">
    <h3>{e(b.verdict)}</h3>
    <p>Scored across the six dimensions the AMS data supports. Seller-trust factors are
      <strong>excluded rather than estimated</strong>, and the remaining weights are rescaled
      to total 100 — so this score reflects the book itself, not the counterparty. Complete
      section 9 before treating it as a final view.</p>
    <div class="os-pills">
      <span class="os-pill">{pct(b.long_tenure_pct)} clients 5+ yrs</span>
      <span class="os-pill">{pct(b.multiline_pct)} multi-line</span>
      <span class="os-pill">{pct(b.transferable_pct)} transferable</span>
      <span class="os-pill">loss ratio {pct(b.overall_loss_ratio)}</span>
      <span class="os-pill">{signed_pct(b.latest_growth)} YoY</span>
    </div>
  </div>
</div>

<table style="margin-top:20px;">
  <thead><tr><th>Evaluation Dimension</th><th>Score</th><th>Weight</th>
    <th>Weighted</th><th>Basis</th></tr></thead>
  <tbody>{rows}
    <tr class="total-row">
      <td><strong>TOTAL</strong></td>
      <td class="num"><strong>{b.total_score:.0f}/100</strong></td>
      <td class="num"><strong>100%</strong></td>
      <td class="num"><strong>{b.total_score:.2f}</strong></td>
      <td><strong>{e(b.verdict)}</strong></td>
    </tr>
  </tbody>
</table>

<div class="gaps">
  <div class="gaps-title">Disclosed limitations</div>
  <ul>{gaps}</ul>
</div>
"""


# ── page assembly ───────────────────────────────────────────────────────────

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI',Arial,sans-serif; background:#f0f4f8; color:#1a2533; font-size:14px; }
.cover { background:linear-gradient(135deg,#0d2b55 0%,#1a4f8a 60%,#1e6bb8 100%); color:#fff; padding:48px 60px 40px; }
.cover-top { display:flex; justify-content:space-between; align-items:flex-start; gap:24px; }
.cover h1 { font-size:28px; font-weight:700; letter-spacing:.5px; }
.cover h2 { font-size:15px; font-weight:400; margin-top:6px; opacity:.85; }
.cover-badge { background:rgba(255,255,255,.15); border:1px solid rgba(255,255,255,.3); border-radius:8px; padding:10px 20px; text-align:center; flex-shrink:0; }
.cover-badge .label { font-size:11px; opacity:.75; text-transform:uppercase; letter-spacing:1px; }
.cover-badge .value { font-size:22px; font-weight:700; margin-top:2px; }
.cover-meta { display:flex; flex-wrap:wrap; gap:40px; margin-top:32px; padding-top:24px; border-top:1px solid rgba(255,255,255,.2); }
.cover-meta div { display:flex; flex-direction:column; gap:4px; }
.cover-meta .lbl { font-size:11px; opacity:.65; text-transform:uppercase; letter-spacing:.8px; }
.cover-meta .val { font-size:14px; font-weight:600; }
.score-banner { display:grid; grid-template-columns:repeat(5,1fr); background:#fff; border-bottom:2px solid #e2e8f0; }
.score-card { padding:18px 20px; text-align:center; border-right:1px solid #e2e8f0; }
.score-card:last-child { border-right:none; }
.score-card .sc-label { font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:.8px; }
.score-card .sc-value { font-size:24px; font-weight:700; margin-top:4px; }
.score-card .sc-sub { font-size:11px; color:#94a3b8; margin-top:2px; }
.green{color:#16a34a}.yellow{color:#d97706}.red{color:#dc2626}.blue{color:#1a4f8a}.muted{color:#94a3b8}
.main { max-width:1100px; margin:0 auto; padding:32px 24px; }
.section { background:#fff; border-radius:10px; box-shadow:0 1px 4px rgba(0,0,0,.07); margin-bottom:28px; overflow:hidden; }
.section-header { display:flex; align-items:center; gap:12px; padding:16px 24px; background:#f8fafc; border-bottom:1px solid #e2e8f0; }
.section-icon { width:34px; height:34px; border-radius:8px; display:flex; align-items:center; justify-content:center; font-size:16px; flex-shrink:0; }
.icon-blue{background:#dbeafe}.icon-green{background:#dcfce7}.icon-yellow{background:#fef3c7}
.icon-purple{background:#ede9fe}.icon-red{background:#fee2e2}.icon-teal{background:#ccfbf1}
.icon-orange{background:#ffedd5}.icon-gray{background:#f1f5f9}
.section-title { font-size:15px; font-weight:700; color:#0f172a; }
.section-subtitle { font-size:12px; color:#64748b; margin-top:1px; }
.section-body { padding:24px; }
.stat-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; }
.stat-box { background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:16px; }
.stat-box .sb-label { font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:.7px; }
.stat-box .sb-value { font-size:20px; font-weight:700; color:#0f172a; margin-top:4px; }
.stat-box .sb-note { font-size:11px; color:#94a3b8; margin-top:2px; }
.table-scroll { overflow-x:auto; }
table { width:100%; border-collapse:collapse; }
thead tr { background:#f1f5f9; }
thead th { text-align:left; padding:10px 14px; font-size:11px; font-weight:700; color:#475569; text-transform:uppercase; letter-spacing:.6px; border-bottom:2px solid #e2e8f0; white-space:nowrap; }
tbody tr { border-bottom:1px solid #f1f5f9; }
tbody tr:last-child { border-bottom:none; }
tbody tr:hover { background:#f8fafc; }
tbody td { padding:11px 14px; font-size:13px; color:#334155; }
td.num { text-align:right; font-weight:600; white-space:nowrap; }
tr.total-row { font-weight:700; background:#f1f5f9; }
.badge { display:inline-block; padding:3px 10px; border-radius:20px; font-size:11px; font-weight:600; white-space:nowrap; }
.badge-green{background:#dcfce7;color:#15803d}.badge-yellow{background:#fef3c7;color:#b45309}
.badge-red{background:#fee2e2;color:#b91c1c}.badge-blue{background:#dbeafe;color:#1d4ed8}
.rating-row { display:flex; align-items:center; gap:12px; margin-bottom:12px; }
.rating-label { width:130px; font-size:13px; color:#334155; flex-shrink:0; }
.rating-bar-wrap { flex:1; background:#e2e8f0; border-radius:20px; height:10px; }
.rating-bar { height:10px; border-radius:20px; }
.bar-green{background:#22c55e}
.rating-pct { width:44px; text-align:right; font-size:12px; font-weight:700; color:#0f172a; }
.two-col { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
.col-title { font-size:13px; font-weight:700; margin-bottom:12px; color:#0f172a; }
.val-box { background:linear-gradient(135deg,#0d2b55,#1a4f8a); color:#fff; border-radius:10px; padding:28px; text-align:center; }
.val-box .vb-label { font-size:12px; opacity:.75; text-transform:uppercase; letter-spacing:1px; }
.val-box .vb-range { font-size:30px; font-weight:800; margin:8px 0; }
.val-box .vb-note { font-size:12px; opacity:.8; }
.val-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:16px; }
.val-item { background:rgba(255,255,255,.12); border-radius:8px; padding:12px; text-align:left; }
.val-item .vi-label { font-size:11px; opacity:.7; }
.val-item .vi-value { font-size:15px; font-weight:700; margin-top:2px; }
.risk-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
.risk-item { border-radius:8px; padding:14px 16px; border-left:4px solid; }
.risk-low{background:#f0fdf4;border-color:#22c55e}.risk-medium{background:#fffbeb;border-color:#f59e0b}
.risk-high{background:#fff1f2;border-color:#ef4444}.risk-unknown{background:#f1f5f9;border-color:#94a3b8}
.risk-item .ri-title { font-size:13px; font-weight:700; margin-bottom:4px; }
.risk-item .ri-desc { font-size:12px; color:#64748b; line-height:1.5; }
.risk-low .ri-title{color:#15803d}.risk-medium .ri-title{color:#b45309}
.risk-high .ri-title{color:#b91c1c}.risk-unknown .ri-title{color:#475569}
.dq-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
.dq-item { background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:14px; text-align:center; }
.dq-item .dq-icon { font-size:22px; margin-bottom:6px; }
.dq-item .dq-label { font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:.6px; }
.dq-item .dq-pct { font-size:20px; font-weight:700; margin-top:4px; }
.dq-item .dq-count { font-size:11px; color:#94a3b8; }
.cal-grid { display:grid; grid-template-columns:repeat(6,1fr); gap:8px; }
.cal-month { background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:12px 8px; text-align:center; }
.cal-month .cm-name { font-size:11px; font-weight:700; color:#475569; text-transform:uppercase; }
.cal-month .cm-count { font-size:20px; font-weight:800; margin:6px 0 2px; color:#1a4f8a; }
.cal-month .cm-prem { font-size:11px; color:#64748b; }
.cal-month.hot { background:#fff7ed; border-color:#fb923c; }
.cal-month.hot .cm-count { color:#ea580c; }
.overall-score { display:flex; align-items:center; gap:32px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:24px 28px; }
.os-circle { width:100px; height:100px; border-radius:50%; background:linear-gradient(135deg,#0d2b55,#1a4f8a); display:flex; flex-direction:column; align-items:center; justify-content:center; color:#fff; flex-shrink:0; }
.os-circle .os-num { font-size:32px; font-weight:800; }
.os-circle .os-den { font-size:12px; opacity:.75; }
.os-details h3 { font-size:16px; font-weight:700; color:#0f172a; margin-bottom:6px; }
.os-details p { font-size:13px; color:#475569; line-height:1.6; }
.os-pills { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
.os-pill { background:#dbeafe; color:#1d4ed8; font-size:11px; font-weight:600; padding:4px 10px; border-radius:20px; }
.callout { margin-top:12px; border-radius:8px; padding:12px 14px; font-size:12px; line-height:1.6; }
.callout-good { background:#f0fdf4; color:#15803d; }
.callout-warn { background:#fff7ed; color:#b45309; }
.unavailable { background:#f1f5f9; border-left:4px solid #94a3b8; border-radius:8px; padding:14px 16px; font-size:12.5px; color:#475569; line-height:1.6; }
.note { margin-top:12px; font-size:11.5px; color:#94a3b8; line-height:1.6; }
.gaps { margin-top:20px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:16px 18px; }
.gaps-title { font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.6px; color:#475569; margin-bottom:8px; }
.gaps ul { margin-left:18px; }
.gaps li { font-size:12px; color:#64748b; line-height:1.7; }
.footer { text-align:center; padding:24px; font-size:11px; color:#94a3b8; border-top:1px solid #e2e8f0; }
.footer strong { color:#64748b; }
@media (max-width:900px) {
  .score-banner { grid-template-columns:repeat(2,1fr); }
  .stat-grid,.dq-grid { grid-template-columns:repeat(2,1fr); }
  .two-col,.risk-grid { grid-template-columns:1fr; }
  .cal-grid { grid-template-columns:repeat(3,1fr); }
  .overall-score { flex-direction:column; align-items:flex-start; gap:16px; }
  .cover { padding:32px 24px; }
}
@media print {
  body { background:#fff; }
  .section { box-shadow:none; border:1px solid #e2e8f0; page-break-inside:avoid; }
}
"""


def render(b: Book, agency: str, prepared_for: str) -> str:
    """Assembles the full standalone HTML report."""
    body = "".join(
        [
            _section(1, "📋", "blue", "Book Size & Composition",
                     "What is actually being sold", _composition(b)),
            _section(2, "💰", "green", "Financial Valuation",
                     "Revenue, growth, and estimated purchase price", _financials(b)),
            _section(3, "🔄", "teal", "Retention & Longevity",
                     "How durable the client relationships are", _retention(b)),
            _section(4, "👥", "purple", "Client Quality & Concentration",
                     "Who the clients are and how concentrated the revenue is",
                     _client_quality(b)),
            _section(5, "📅", "yellow", "Renewal Calendar (Next 12 Months)",
                     "When policies renew — cash-flow timing for the buyer", _calendar(b)),
            _section(6, "⚠️", "red", "Risk Assessment",
                     "Factors that could reduce the book's value post-sale", _risk(b)),
            _section(7, "🗄️", "orange", "Data Quality & Portability",
                     "How clean and exportable the AMS data is", _data_quality(b)),
            _section(8, "🏢", "gray", "Carrier Relationships & Appointments",
                     "Which carriers hold the book and whether they transfer", _carriers(b)),
            _section(9, "🤝", "purple", "Trust & Seller Profile",
                     "Verifying the seller's credibility — external sources", _trust()),
            _section(10, "🏆", "blue", "Overall Book Score & Recommendation",
                     "Summary evaluation across all measurable dimensions", _score(b)),
        ]
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Book of Business — Sale Evaluation Report</title>
<style>{CSS}</style>
</head>
<body>
{_cover(b, agency, prepared_for)}
<div class="main">{body}</div>
<div class="footer">
  <strong>CONFIDENTIAL</strong> — Prepared for buyer due diligence. Every figure is derived
  from data scraped out of the seller's agency management system on
  {b.generated_on:%d %B %Y} and has not been independently audited. Sections marked
  "not available" could not be sourced from the AMS and require external verification.
</div>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=Path("output/ams"))
    parser.add_argument("--out", type=Path, default=Path("output/book_rolling_report.html"))
    parser.add_argument("--agency", default="Demo Insurance Agency")
    parser.add_argument("--prepared-for", default="Prospective Buyer")
    parser.add_argument("--as-of", default=None, help="override report date (YYYY-MM-DD)")
    args = parser.parse_args()

    if not args.src.exists():
        print(f"error: no scraped data at {args.src}", file=sys.stderr)
        return 1

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    book = build(args.src, today=as_of)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(book, args.agency, args.prepared_for), encoding="utf-8")

    print(f"report written to {args.out}")
    print(f"  clients {book.client_count} · policies {book.policy_count} · "
          f"premium {usd(book.total_premium)}")
    print(f"  revenue FY{book.base_year} {usd(book.base_revenue)} · "
          f"score {book.total_score:.0f}/100 ({book.verdict})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
