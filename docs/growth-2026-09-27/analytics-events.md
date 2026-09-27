# Catalog events

Ranking and founder-facing funnel counts use `CatalogEvent` and, for tool clicks, `ToolClick`. PostHog is not added to those counts. Do not sum the two systems.

Endpoint: `POST /track/event/`

The browser sends the event with `keepalive` and ignores failures, so a tracking error does not block navigation. The same `event_id` is stored once.

## Events

| `event_name` | When | Identifiers |
| --- | --- | --- |
| `search_submitted` | A directory search identity is shown | `query_id`, `surface`, `context.sort`, `context.filter_count` |
| `results_displayed` | A directory response is applied | `query_id`, `context.results_count`, `context.sort`, `context.filter_count` |
| `result_selected` | A card or row opens a listing | `entity_type`, `entity_id`, `entity_slug`, `surface`, `result_position` |
| `detail_view` | Tool or agent detail mounts | `entity_type`, `entity_id`, `entity_slug`, `surface` |
| `official_site_click` | Official site or repo click | same, plus `surface` (`tool_detail`, `directory`, `open_source_row`, `agent_detail`) |
| `compare_added` | A tool is added on the compare page | `entity_id`, `context.results_count` |
| `compare_completed` | The second tool is added | `context.results_count` = 2 |
| `tool_saved` | Save is turned on | `entity_type`, `entity_slug`, local to the browser for the list itself |
| `submission_started` | First edit on the submit form | `surface=submit_form` |
| `submission_validation_failed` | Required fields missing | no email |
| `submission_completed` | The submission row was saved | no email |
| `service_inquiry_started` | First edit on an intake | `context.offer` |
| `service_inquiry_submitted` | Intake returned success | `context.offer` |
| `product_activation` | One9 Worker download click | `entity_slug=worker` |

`campaign` is `utm_campaign` from the page URL when present. `session_id` is a random id in `sessionStorage` (`one9_catalog_session`). Query text is not sent.

## What counts for Trending

`GET` trending uses `ToolClick` rows where `action=visit_tool` and `counts_for_ranking` is true.

`counts_for_ranking` is false when:

- the user agent looks like a bot, or `X-One9-Internal: 1` is set
- the same tool and session already has 5 ranked visit clicks in 24 hours

Staff usage should send `X-One9-Internal: 1` during manual checks.

## Measurement

Local or staging proof is a controlled browser journey that creates one `search_submitted`, one `results_displayed`, one `result_selected`, one `detail_view`, and one `official_site_click` with the same `query_id` on the search steps. Confirm a second POST with the same `event_id` does not insert another row.

Production receipt is unverified until this branch is deployed and a non-bot session is inspected in Django admin (`CatalogEvent`).

## Privacy

Do not put email, name, or the raw query in these events. Newsletter and auth flows may still use their existing analytics. Newsletter forms in this change do not send mail.
