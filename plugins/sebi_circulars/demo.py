"""Full-run demo for the sebi_circulars plugin — dynamic params without the terminal.

In the real application these params come from a caller (a function/job). This
script is only for local testing and demoing: edit PARAMS below and run the file,
no CLI flags needed.

It performs a REAL scrape (hits sebi.gov.in over the network) and writes output
under the repo's output/ folder, exactly as `scraper run-plugin sebi_circulars`
would. Point your editor's interpreter at .venv so the deps are available.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)

from cli.main import _build_engine, _job_from_config, _resolve_plugin  # noqa: E402

PLUGIN = "sebi_circulars"

PARAMS: dict[str, object] = {
    "title": "SEBI (Issuing Observations On Draft Offer Documents Pending Regulatory Actions) Order, 2020",
    # "from_date": "2026-07-01",
    # "to_date": "2026-07-28",
    "max_results": 5,
}

def main() -> None:
    """Resolves the plugin with PARAMS and runs the full scrape pipeline."""
    resolved, config, registry = _resolve_plugin(
        PLUGIN, PARAMS, REPO_ROOT / "plugins", REPO_ROOT / "config"
    )
    print(f"▶ running {PLUGIN} with params: {dict(resolved.params) or '{} (everything)'}")
    print(f"  seed url: {config.data['urls'][0]}")

    engine = _build_engine(config, registry, list(config.data["pipeline"]))
    result = asyncio.run(engine.run(_job_from_config(config)))

    print(
        f"✔ done: {result.completed} completed, {result.aborted} aborted, "
        f"{result.quarantined} quarantined"
        + (f", {result.discarded} filtered" if result.discarded else "")
    )
    print("  output: output/circulars.json  (PDFs under output/pdfs/sebi/)")


if __name__ == "__main__":
    main()
