# Deployment, rollback, and 30-day measurement

Do not deploy from this note. It is the sequence to use after review.

## Order

1. Backend `cursor/growth-discovery-3b84` first. It adds migration `0030_growth_discovery_events`, directory query params, `preferred_path`, catalog events, service inquiries, and submission status.
2. Confirm migrate, `/tools/?q=video&ordering=relevance`, `/submissions/status/` without a token (400), and `/services/inquiries/` validation.
3. Frontend after that. The directory sends `q`, `job_cluster`, `deployment`, and `integration`. An old API ignores unknown params in Django, but text relevance and job filters will not apply until the backend is live. Search requests omit `ordering` when the sort is relevance, because the new API treats that as relevance and the current production API returns 500 for `ordering=relevance`. Canonical `preferred_path` is null until the backend is live, so tool pages stay self-canonical.
4. No DNS change. No Cloudflare configuration change. No bulk listing update. No email.

## Rollback

- Frontend: redeploy the previous frontend release. It does not require a database rollback.
- Backend: redeploy the previous release. Migration `0030` adds nullable columns and two tables (`CatalogEvent`, `ServiceInquiry`) plus submission enrichment fields. Rolling the app back without reversing the migration is safe: old code ignores the new columns. Reverse the migration only if the new tables must be dropped, and only after confirming no inquiries need to be kept.
- Canonical phase writes nothing to listing rows. Removing the release restores self-canonical tool pages on the next render.
- No redirect map is live, so there is no redirect rollback.

## Risks

- Job and deployment filters match text. They are not a verified taxonomy.
- Open-source chips disappear when `github_url` is empty, including Filmora, even if the stored `access` value still says Open Source. The stored value is not bulk-corrected.
- Service and newsletter copy says no email is sent. That matches the code. Do not add a sender without a separate decision.
- Search Console recrawl is not instantaneous. Do not report indexing improvement until it is measured.

## Blocked

- Google clicks, CTR, queries, and positions. The supplied performance export does not include them.
- Example URL lists behind the historical +43,505 discovered-URL jump.
- Whether the Cloudflare export includes the API hostname as well as the website.
- Production PostHog and production `CatalogEvent` receipt.
- Permission to email founders or to 301 overlapping URLs.

## 30-day measurement

Start the clock the day after both releases are in production. Compare with the 30 days before that date. Do not treat Cloudflare unique visitors as people, and do not treat a byte-cache ratio as a request hit rate.

| Outcome | Read | Notes |
| --- | --- | --- |
| Search clicks | Search Console clicks and queries for `/`, `/agents/wondershare-filmora`, `/agents/*`, `/tool/*`, `/solutions/*`, `/services/*` | Needs query and click export. Impressions alone are not a click result. |
| Useful tool clicks | `CatalogEvent` `official_site_click` where `counts_for_ranking` is true, split by `surface` and `entity_slug` | Do not add PostHog `tool_visited`. |
| Service inquiries | `ServiceInquiry` count by `offer`, excluding honeypot drops (those are not stored) | No reply-time target is set. |
| Product activation | `product_activation` for `worker` | A click is not an install. |
| Returning visitors | Search Console or analytics returning-user report if one is already configured | Do not invent one from Cloudflare uniques. |

Also watch, without treating them as the goal: tool-sitemap URL count versus noindex overlap, submission `enrichment_status=failed` per day, and discovery noop versus `facts_updated` on the next bounded run.
