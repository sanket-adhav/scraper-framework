"""SEBI circulars — edit the values below and run this file.

    uv run python examples/sebi_circulars_demo.py

This performs a REAL scrape (it hits sebi.gov.in), downloads the matching PDFs
into output/pdfs/sebi/, and writes the metadata to output/circulars.json —
exactly the same as `scraper run-plugin sebi_circulars`, just without typing
flags on the command line.

Set a value to None to leave that filter off. Every parameter is optional: an
omitted filter matches everything, which is how "scrape all of it" works.
"""

from __future__ import annotations

import os
from pathlib import Path

from cli.api import run_scraper

REPO_ROOT = Path(__file__).resolve().parents[1]
os.chdir(REPO_ROOT)


# ─── 👇 EDIT THIS BLOCK ───────────────────────────────────────────────────────

TITLE = "SEBI (Prohibition on Raising Further Capital From Public and Transfer of Securities of Suspended Companies) Order, 2015."

FROM_DATE = None          # e.g. "2026-07-01"
TO_DATE = None            # e.g. "2026-07-28"

# SEBI's own Legal category number:
#   -1 = All categories (default)     1 = Acts         2 = Rules
#    3 = Regulations                  7 = Circulars
CATEGORY_ID = -1
MAX_RESULTS = 5

# ─── 👆 EDIT THIS BLOCK ───────────────────────────────────────────────────────

PLUGIN = "sebi_circulars"

PARAMS: dict[str, object] = {
    "title": TITLE,
    "from_date": FROM_DATE,
    "to_date": TO_DATE,
    "category_id": CATEGORY_ID,
    "max_results": MAX_RESULTS,
}

def main() -> int:
    """Runs the scrape with the values above and reports where the output went."""
    # None means "filter not set" — drop those so the plugin's own defaults apply.
    params = {name: value for name, value in PARAMS.items() if value is not None}

    print(f"scraping {PLUGIN} with {params}\n")
    result = run_scraper(PLUGIN, params)

    print(f"\n{result}")
    if result.quarantined:
        print(
            f"{result.quarantined} record(s) needed review — see why with:\n"
            f"    uv run scraper quarantine list"
        )
    if result.completed:
        print("PDFs:     output/pdfs/sebi/")
        print("Metadata: output/circulars.json")
    else:
        print("Nothing matched. Try a shorter TITLE, or widen the date range.")

    # ok is False if anything aborted OR was quarantined — not just aborted.
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
