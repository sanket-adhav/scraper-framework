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

> Note: both Phase-1 sources are deliberately synthetic so the contracts could
> be proven without any legal ambiguity. The first plugin that targets a real,
> live website MUST add a new SRC entry here with an honest ToS/robots/PII
> assessment before any code or config for it is merged.
