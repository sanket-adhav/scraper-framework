"""One-off script that generates sample_report.pdf — kept so the fixture is reproducible.

Run from the repo root: uv run python tests/fixtures/_generate_pdf.py
"""

from pathlib import Path

import pymupdf


def main() -> None:
    """Creates a small two-page order-report PDF next to this script."""
    doc = pymupdf.open()

    page1 = doc.new_page()
    page1.insert_text(
        (72, 96),
        "ShopVerse Order Report\n"
        "Order ID: SV-2026-018342\n"
        "Date: 17 July 2026\n\n"
        "Item: Aurora X2 Wireless Headphones\n"
        "Quantity: 1\n"
        "Unit Price: INR 4999.00\n",
        fontsize=12,
    )

    page2 = doc.new_page()
    page2.insert_text(
        (72, 96),
        "Summary\n\nSubtotal: INR 4999.00\nGST (18%): INR 899.82\nTotal: INR 5898.82\n",
        fontsize=12,
    )

    out = Path(__file__).parent / "sample_report.pdf"
    doc.save(out)
    doc.close()
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
