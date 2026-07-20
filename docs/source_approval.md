# Source approval — the legal gate (plan2.md §13)

**No plugin may target a source that has not passed this checklist.** The
approval is recorded here (one section per source) and referenced from the
plugin's `plugin.yaml` (`source_approval:`). A plugin whose manifest lacks a
source-approval reference fails to load. This gate applies before plugin code
is written, permanently.

## The checklist

For each proposed source, record:

1. **Terms of Service review** — do the site's ToS permit programmatic access?
   Quote or link the relevant clause. If access is forbidden, the answer is no.
2. **robots.txt posture** — what do the site's robots rules say about the paths
   we would fetch? We respect disallow rules unless legal counsel explicitly
   clears an exception.
3. **Personal-data assessment** — does the source contain personal data (names,
   contacts, user-generated content)? If yes: lawful basis, retention limits,
   and whether a compliance stage (PII redaction) is mandatory.
4. **Anti-bot countermeasures permission** — are countermeasures (UA rotation,
   proxies, CAPTCHA solving) permitted against this source? yes / no /
   constraints. "The framework can" never implies "we may".
5. **Decision** — allowed / allowed-with-constraints / rejected.
6. **Approver + date.**

---

## Recorded approvals

### SRC-0001 — ShopVerse product pages (synthetic fixtures) — Plugin: ecommerce_example

- **What it is:** hand-written sample HTML pages for the fictional "ShopVerse"
  shop, stored in this repo (`plugins/ecommerce_example/fixtures/`). No live
  website exists; nothing is fetched over the network.
- **ToS review:** not applicable — the content is our own synthetic fixture data.
- **robots.txt:** not applicable — no live target.
- **Personal data:** none; fixture content is invented product data.
- **Anti-bot countermeasures:** not applicable (no live target). If this plugin
  is ever pointed at a real site, this approval is void and a new entry is required.
- **Decision:** **allowed** (fixture-only source).
- **Approver:** Sanket Adhav · **Date:** 2026-07-18

### SRC-0002 — ShopVerse products API (synthetic fixtures) — Plugin: api_example

- **What it is:** hand-written sample JSON API responses (with cursor
  pagination) for the fictional ShopVerse API, stored in
  `plugins/api_example/fixtures/`. No live endpoint exists.
- **ToS review / robots.txt:** not applicable — synthetic fixture data.
- **Personal data:** none.
- **Anti-bot countermeasures:** not applicable. Same revocation rule as SRC-0001.
- **Decision:** **allowed** (fixture-only source).
- **Approver:** Sanket Adhav · **Date:** 2026-07-18

### SRC-0003 — ShopVerse deals feed (synthetic RSS/XML fixtures) — Plugin: news_feed

- **What it is:** hand-written sample RSS/XML feed pages (with next-page links)
  for the fictional ShopVerse deals feed, stored in `plugins/news_feed/fixtures/`.
  No live feed exists.
- **ToS review / robots.txt:** not applicable — synthetic fixture data.
- **Personal data:** none.
- **Anti-bot countermeasures:** not applicable. Same revocation rule as SRC-0001.
- **Decision:** **allowed** (fixture-only source).
- **Approver:** Sanket Adhav · **Date:** 2026-07-19

> Note: SRC-0001..0003 are deliberately synthetic so the contracts could be
> proven without any legal ambiguity. SRC-0004 below is the first real live
> target — chosen precisely because it is unambiguously permitted.

### SRC-0004 — books.toscrape.com (LIVE) — Plugin: books_toscrape

- **What it is:** `http://books.toscrape.com` — a public web-scraping **sandbox**
  operated by Zyte (the Scrapy maintainers) that exists specifically for people
  to practise scraping against. This is the framework's first real live target.
- **ToS review:** the site is published as a sandbox whose stated purpose is to
  be scraped; there is no prohibition on programmatic access. Content is
  fictional book catalogue data generated for the sandbox.
- **robots.txt:** permissive; the catalogue pages we fetch are not disallowed.
  We fetch individual product pages politely (default rate limit), not a crawl.
- **Personal data:** none — invented book listings, no user data.
- **Anti-bot countermeasures:** none needed and none used (tier `open`).
- **Decision:** **allowed** (public scraping sandbox, explicitly intended for this).
- **Approver:** Sanket Adhav · **Date:** 2026-07-20

> Draft-only note: `plugins/amfi_circulars`, `plugins/sebi_circulars`, and
> `plugins/sebi_gazette` are **work-in-progress config drafts** targeting Indian
> regulator sites (AMFI, SEBI). They use a `manifest.yaml` (not `plugin.yaml`),
> so the plugin loader does NOT load them yet, and they have **no approval
> entry**. Before any of them becomes a live plugin, it needs (a) a real
> ToS/robots.txt/public-data review recorded here, and (b) rename to
> `plugin.yaml` with a valid `source_approval` reference.
