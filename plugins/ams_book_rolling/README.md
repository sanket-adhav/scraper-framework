# ams_book_rolling

Scrapes an insurance Agency Management System (Quickfire/Surefire) for the data
behind a **Book of Business sale-evaluation report**.

## Setup

Add to `scraper_framework/.env`:

```
AMS_BASE_URL=http://localhost:5577
AMS_EMAIL=<login email>
AMS_PASSWORD=<login password>
```

The configs reference these as `secret://env/AMS_EMAIL` / `secret://env/AMS_PASSWORD`,
so no credential is ever stored in YAML or hashed into the config fingerprint.

## Run

```bash
for f in policies carriers clients commissions claims renewal_pipeline billing_aging submissions; do
  .venv/bin/python -m cli.main run plugins/ams_book_rolling/config/$f.yaml
done
```

Output lands in `output/ams/*.json`. Each file holds one record shaped as:

```json
{"collections": {"<name>": [ {row}, ... ]}, "row_counts": {...}, "source_url": "..."}
```

## Verified against the live app (2026-07-27)

10 configs, 133 rows, every total reconciled against the database.

| Config | Collections | Rows | DB truth | ✓ |
|---|---|---|---|---|
| `policies` | policies | 34 | 34 policies | ✓ |
| `carriers` | carriers | 10 | 10 carriers | ✓ |
| `clients` | clients, selected_client | 10, 1 | 10 clients | ✓ |
| `commissions` | by_year, by_status, by_carrier | 4, 4, 9 | 99 statements | ✓ |
| `claims` | by_status, by_line | 4, 5 | 7 claims | ✓ |
| `renewal_pipeline` | pipeline | 14 | expiring ≤180d | ✓ |
| `billing_aging` | outstanding | 4 | 4 Due/Overdue | ✓ |
| `submissions` | by_line | 7 | 7 lines | ✓ |
| `client_quality` | data_quality, by_tenure, clients | 3, 4, 10 | 10 clients, 8 verified | ✓ |
| `carrier_appointments` | by_carrier | 10 | 10 carriers | ✓ |

Cross-checks that must hold:

- client premium sum = carrier premium sum = **$1,822,000** = DB active premium
- commission statements across years = **99** = DB row count
- address-verified = **8 / 10** = `SUM(Clients.AddressVerified)`
- transferability mix = **6 Direct / 2 Re-apply / 2 Non-transferable**

## Notes on the target application

- **Auth**: ASP.NET Identity form POST with a `__RequestVerificationToken`
  antiforgery field. Driving the real form in a browser carries the token and
  the auth cookie automatically, so no manual CSRF handling is needed.
- **Rendering**: Blazor Web App (`blazor.web.js`) with interactive islands —
  content hydrates after load, so a browser fetcher is mandatory. Plain HTTP
  returns an empty shell.
- **Grid IDs are unstable.** The FluentUI grids render a random id per
  render (`#f3fc4d7e9`). Never select on it. Use `contains(@class,"fluent-data-grid")`.
- **Report tables are matched on a header cell** (`//table[.//th[.="Carrier"]]`)
  rather than position, so adding a panel to a report page will not silently
  shift the column mapping.
- **In-page pagination.** `/Policies` pages client-side at 18 rows without
  changing the URL. `paginate_next_selector` walks every page and splices the
  rows into one table before the HTML is read.

## Report coverage

| Report section | Source config | Status |
|---|---|---|
| §1 Book size & composition | `policies`, `clients` | ✅ |
| §2 Financial valuation (3-year trend) | `commissions` → `by_year` | ✅ |
| §3 Retention & longevity (tenure) | `client_quality` → `by_tenure` | ✅ |
| §4 Client quality & concentration | `client_quality` → `clients` | ✅ |
| §5 Renewal calendar | `renewal_pipeline`, `policies` | ✅ |
| §6 Risk / loss ratio | `claims` + `policies` | ✅ |
| §7 Data quality & portability | `client_quality` → `data_quality` | ✅ |
| §8 Carrier relationships | `carrier_appointments` | ✅ |
| §9 Trust & seller profile | — | ⛔ not AMS data |
| §10 Overall score | derived from the above | ✅ |

**§9 is the only remaining gap.** Licence status, E&O coverage, regulatory
complaints and non-compete terms are not agency-management data — they come
from state DOI records, certificates and legal review. Options considered:
an Agency Profile page in Settings, a per-report input wizard, or static
placeholders. Deferred by decision.

### Gaps that were closed (2026-07-27)

The first pass found ~30–40% of the report unreachable. Three UI additions in
Quickfire fixed it — the data already existed in the database but was rendered
nowhere, so no selector could reach it:

- `/Reports/Commissions` — added a **By Year** table (the 3-year revenue trend).
- `/Reports/ClientQuality` — **new page**: tenure buckets, contact-data
  completeness, and a per-client roster with `DateOpened`, policy count and
  premium share.
- `/Reports/CarrierAppointments` — **new page**: premium share, average
  commission rate and appointment transferability per carrier.

## Framework additions this plugin required

Both are generic and reusable, not AMS-specific:

- `components/fetchers/authenticated_playwright_fetcher.py` — form login with
  session reuse, plus in-page pagination merging.
- `components/extractors/table_extractor.py` — turns table/list rows into
  `data.collections`, since `SpecDrivenExtractor` takes only the first match
  per field and the pipeline carries one record per document.
- `cli/composition.py` — passes `extractor_options` through to the extractor.
- `core/config/loader.py` — exempts `*_selector` keys from the plaintext-secret
  guard (a CSS selector named `password_selector` is not a credential).
