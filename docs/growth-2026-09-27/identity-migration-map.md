# Canonical identity map

Status: review only. `redirects_applied` is false. Do not issue 301s from this document.

## Policy

A tool and an agent are the same product when they share a slug and the agent’s short plus long description is at least 40 characters.

| Surface | Behavior |
| --- | --- |
| `/agents/{slug}` | Preferred URL. Stays indexable when the page is substantive. |
| `/tool/{slug}` | Remains HTTP 200. `rel=canonical` points at `/agents/{slug}`. `noindex, follow`. Removed from the tool sitemap. Visible link to the preferred URL. |
| Different intent | No canonical collapse. A thin or missing agent does not take the tool URL. |
| Unknown URL | Existing 404. Do not redirect it to the homepage. |

Preferred path is computed in `api/identity.py` (`MIN_PREFERRED_AGENT_CHARS = 40`). Regenerate rows from a database copy:

```bash
python manage.py export_identity_map
```

The command prints JSON and sets `redirects_applied` to false. It does not write redirects.

## Confirmed production sample (27 Sep 2026)

Fetched with a browser user agent. Production does not yet return `preferred_path`.

| Slug | Tool URL | Agent URL | Same site | Agent text | Preferred after deploy | Redirect |
| --- | --- | --- | --- | --- | --- | --- |
| `15minutes` | `/tool/15minutes` 200 | `/agents/15minutes` 200 | `https://www.15minutes.ai/` | 214 characters | `/agents/15minutes` | none |
| `wondershare-filmora` | not required for this exposure | `/agents/wondershare-filmora` 200 | `https://filmora.wondershare.com/` | high-exposure agent page | keep `/agents/wondershare-filmora` | none |

Filmora’s production API record is `access: "Open Source"`, `github_url: ""`, `popularity_score: 106`. The frontend hides the open-source chip without a repository URL and does not render 106 as a score out of 100. The backend stops inferring open source from a GitHub URL on future imports. Existing rows are not bulk-edited.

## Sitemap

Tool sitemap entries come from the indexable queryset and then drop slugs that have a preferred agent. A `noindex` tool such as `/tool/11sight` should not be emitted. Author sitemap dates use `content_updated_at` (newest related paper) or `first_seen`. Authors with zero papers stay excluded. Author pages are not mass-noindexed.

## Before any redirect

1. Run `export_identity_map` against a production database copy.
2. Review every row for a shared official host and a real content overlap.
3. Ship canonical, noindex, internal links, and sitemap exclusion first.
4. Only then consider 301s for rows that stayed canonical for a recrawl window.
5. Roll back by reverting the release. No data migration is required for the canonical phase.
