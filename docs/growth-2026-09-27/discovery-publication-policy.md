# Discovery, provenance, and publication

The existing discovery pipeline is extended. This branch does not start a crawl, call a paid API, or publish listings.

## Path

Source → candidate → official identity → deduplication → sourced fields → review → canonical listing → refresh.

Discovery and publication stay separate. A candidate that fails the usefulness check is not published.

## Usefulness

`passes_quality_gate` still runs. `usefulness_gaps` then requires an identity, an official URL, and a sourced capability or category. Missing price stays missing. It is not invented. The Hacker News catalogue path does not use this extra gate.

## Source budget

`select_with_source_budget` caps one source at half the slots, then fills unused slots so a single available source can still complete a bounded run.

## Refresh

When description similarity is at least 0.9:

- pricing type, free tier, starting price, and India-plan fields still persist when they changed
- `updated_at` moves when those facts change
- a prose no-op only advances `last_enriched_at` and the noop counter

`last_enriched_at` is a crawl cursor. It is not a public “reviewed on” date.

## Fetch safety

`host_is_blocked` refuses localhost, `.local`, `.internal`, `metadata.google.internal`, and non-global IP literals before HTML fact fetch, and checks the final URL again. A DNS failure does not by itself mark a host private. Fetched text stays untrusted.

## Provenance

Important assertions should keep a source URL, an observation time, and the extractor version already stored by the pipeline. Unknown facts stay empty.

## Submissions

`ToolSubmission.save` no longer runs enrichment inline. The row is committed, then `schedule_submission_enrichment` runs. Failure sets `enrichment_status=failed` and keeps the row. The public status URL reports moderation status, enrichment status, `facts_verified: false`, and missing fields. Moderating a row is not a fact check.

Duplicate website plus email inside 30 days returns the existing row.

## Services

`ServiceInquiry` stores workflow, current tools, team context, desired outcome, and contact fields. Offer values: `workflow_audit`, `implementation`, `maintenance`. A non-empty honeypot field `website` returns 201 and writes nothing. More than 3 inquiries per email per hour return 429. Admin is the internal queue. No mail is sent.

## What this branch will not do

- unbounded crawling
- paid API spend
- bulk publication of new production listings
- bulk noindex of research authors
- email to founders
