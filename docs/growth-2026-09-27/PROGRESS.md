# Growth work log — 27 Sep 2026

Prepared changes are on `cursor/growth-discovery-3b84` in the backend and frontend repositories. Nothing in this branch has been deployed, merged, or applied to production data.

## Completed in code

- Robots no longer disallow public `/_next/` assets. Private areas stay disallowed.
- Directory `GET /tools/` applies search text, category, pricing, job cluster, deployment text, integration text, and a whitelist of sort fields before pagination.
- Overlapping tool/agent slugs with a substantive agent description expose `preferred_path`. The tool URL stays 200, is noindex, canonicalizes to `/agents/{slug}`, and leaves the tool sitemap. No redirect is applied.
- Agent popularity is an unbounded source signal. Scores above 100 are not shown as a percentage. Open Source is hidden unless a repository URL is recorded. `map_access` no longer infers open source from any GitHub URL.
- Directory titles no longer claim “Review” unless the tool is editorially assessed, and they are not cut mid-phrase at 60 characters.
- Catalog events are the ranking source. Trending counts ranked `visit_tool` clicks only, with a per-session cap and bot/internal filtering.
- Submissions are saved before enrichment. Enrichment status is visible on a token URL. Approval is not treated as fact-checking. No email is sent.
- Service inquiries persist for workflow audit, implementation, and maintenance, with validation, a honeypot, and an hourly email cap. No email is sent.
- Discovery: usefulness gaps, per-source budget, structured-fact refresh when prose is unchanged, and a block on private-network fetch targets.
- Author sitemap `lastmod` uses the newest paper date, then `first_seen`, not `last_seen`.
- Homepage, services, solutions, products, saved listings, and submission status pages are implemented in the frontend.

## Findings that changed the plan

- Production homepage SearchAction already targets `/?q={search_term_string}#tools-section`. `/search?q=video` is still HTTP 404. The new homepage keeps the working target.
- Production still blocks `/_next/` in robots.txt (confirmed 27 Sep 2026). The fix is in the frontend branch only.
- `/agents/wondershare-filmora` is the high-exposure URL. It stays. Production title is still `Wondershare Filmora - Review, Features & | One9Founders`. Production API still returns `access: Open Source` with an empty `github_url` and `popularity_score: 106`.
- `/tool/15minutes` and `/agents/15minutes` both exist in production for `15minutes.ai`. Production `preferred_path` is null until the backend branch is deployed. Description length on the agent is 214 characters, so the policy selects `/agents/15minutes`.
- `/tool/11sight` already returns `noindex, follow` in production HTML.
- Cloudflare unique counts, the coverage export, and the AI-feature export are historical inputs. They were not re-pulled. They do not prove a Google click decline or a penalty.

## Not done

- No production deploy, DNS or cache change, bulk listing edit, email, or campaign.
- Search Console clicks, queries, and positions were not available.
- Production receipt of the new catalog events is unverified.
- Reticle MCP tools were not available in this session. Browser verification is recorded separately after the dev server run.
