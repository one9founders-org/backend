# AI News Pipeline Documentation

## Overview

The One9Founders AI News Pipeline is a fully automated system that scrapes AI-related content from multiple sources, scores it for relevance, generates editorial content, and publishes articles to the News page without manual intervention.

## Architecture

### Data Flow

```
Scrapers → raw_scraped_items → AI Scoring → qualified_news_items → Content Generation → drafts → Publishing → published_articles/News
```

### 4-Stage Pipeline

1. **raw_scraped_items**: Raw data from scrapers lands here first
2. **qualified_news_items**: Items that passed deduplication and AI scoring
3. **drafts**: AI-generated article content ready for publishing
4. **published_articles**: Published articles linked to the main News model

### Status Tracking

Each stage updates status fields to track progress:

| Stage | Statuses |
|-------|----------|
| Scraped | `scraped`, `processing`, `qualified`, `rejected`, `duplicate`, `error` |
| Qualified | `scored`, `auto_rejected`, `queued`, `auto_approved`, `manually_approved`, `manually_rejected` |
| Drafts | `generating`, `generated`, `editing`, `ready`, `scheduled`, `published`, `failed` |

## Scheduling

### Scraper Schedules

| Source | Schedule | Trigger |
|--------|----------|---------|
| Product Hunt | Daily at 06:00 UTC | n8n cron |
| TAAFT | Daily at 06:00 UTC | n8n cron |
| Futurepedia | Daily at 06:00 UTC | n8n cron |
| Hugging Face | Every 6 hours | n8n cron |

### Fail-Safe

- Failed scrapers are automatically retried after 30 minutes
- All failures are logged with detailed error messages
- Pipeline runs are tracked in `pipeline_runs` table

## AI Decision Engine

### Scoring Criteria

Items are scored on three dimensions (0-100 each):

1. **Founder Relevance**: How useful for startup founders
2. **Practical Impact**: How actionable/practical
3. **Novelty**: How new/innovative

### Auto-Categorization

| Score Range | Action |
|-------------|--------|
| < 40 | Auto-reject |
| 40-69 | Queue for review |
| >= 70 | Auto-approve |

### Scoring Prompt

The AI uses a structured prompt focused on:
- Founder relevance (directly helps build/launch/grow startups)
- Practical impact (immediately usable to solve real problems)
- Novelty (first of its kind or significant breakthrough)

## Content Generation

### Editorial Style

Generated articles follow these guidelines:
- Written for busy founders who want actionable insights
- Concise but informative (300-500 words)
- Professional but approachable tone
- Focus on practical implications for startups
- No hype or marketing speak

### Article Structure

1. **Hook**: Compelling opening sentence
2. **What It Is**: Brief explanation
3. **Why It Matters**: Why founders should care
4. **Key Features**: 2-3 most important capabilities
5. **Founder Takeaway**: One actionable insight

### SEO

- Auto-generated SEO title (max 60 chars)
- Auto-generated meta description (max 155 chars)
- Category-based routing

## Publishing Rules

### Rate Limits

- Maximum 5 articles per day
- Publish times spread throughout the day (8am, 10am, 12pm, 2pm, 4pm)
- Category-based routing to appropriate sections

### Kill-Switch

Publishing can be disabled via the `publishing_enabled` config:

```bash
curl -X POST http://localhost:8000/api/pipeline/toggle-publishing/ \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

## API Endpoints

### Pipeline Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/pipeline/ingest/` | POST | Ingest scraped data |
| `/api/pipeline/run/` | POST | Trigger pipeline execution |
| `/api/pipeline/stats/` | GET | Get pipeline statistics |
| `/api/pipeline/config/` | GET/POST | View/update configuration |
| `/api/pipeline/toggle-publishing/` | POST | Enable/disable publishing |
| `/api/pipeline/feed/` | GET | Get published news feed |

### Data Access

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/pipeline/scraped/` | GET | List scraped items |
| `/api/pipeline/qualified/` | GET | List qualified items |
| `/api/pipeline/qualified/{id}/approve/` | POST | Manually approve item |
| `/api/pipeline/qualified/{id}/reject/` | POST | Manually reject item |
| `/api/pipeline/drafts/` | GET | List drafts |
| `/api/pipeline/drafts/{id}/publish/` | POST | Manually publish draft |
| `/api/pipeline/drafts/{id}/regenerate/` | POST | Regenerate content |
| `/api/pipeline/published/` | GET | List published articles |
| `/api/pipeline/runs/` | GET | List pipeline runs |

### News Feed

```bash
# Get today's news
curl "http://localhost:8000/api/pipeline/feed/?period=today"

# Get this week's highlights
curl "http://localhost:8000/api/pipeline/feed/?period=week&highlights=true"
```

## n8n Workflows

### Importing Workflows

1. Open n8n dashboard
2. Go to Workflows → Import
3. Import JSON files from `/n8n_workflows/`:
   - `daily_scraper_workflow.json` - Daily scraping (06:00 UTC)
   - `huggingface_scraper_workflow.json` - 6-hourly HF scraping
   - `retry_failed_workflow.json` - Retry failed scrapers

### Environment Variables

Set these in n8n:
- `API_BASE_URL`: Backend API URL (e.g., `https://api.one9founders.com`)

### Workflow Triggers

| Workflow | Trigger | Description |
|----------|---------|-------------|
| Daily Scraper | Cron: `0 6 * * *` | Runs PH, TAAFT, Futurepedia daily |
| HuggingFace | Cron: `0 */6 * * *` | Runs HF every 6 hours |
| Retry Failed | Every 30 minutes | Retries failed scrapers |

## Manual Operations

### Manually Approve an Item

```bash
curl -X POST http://localhost:8000/api/pipeline/qualified/123/approve/
```

### Manually Reject an Item

```bash
curl -X POST http://localhost:8000/api/pipeline/qualified/123/reject/ \
  -H "Content-Type: application/json" \
  -d '{"reason": "Not relevant to founders"}'
```

### Manually Publish a Draft

```bash
curl -X POST http://localhost:8000/api/pipeline/drafts/456/publish/
```

### Regenerate Content

```bash
curl -X POST http://localhost:8000/api/pipeline/drafts/456/regenerate/
```

### Run Pipeline Manually

```bash
# Run full pipeline
curl -X POST http://localhost:8000/api/pipeline/run/ \
  -H "Content-Type: application/json" \
  -d '{"type": "full", "limit": 50}'

# Run only scoring
curl -X POST http://localhost:8000/api/pipeline/run/ \
  -H "Content-Type: application/json" \
  -d '{"type": "score", "source": "producthunt", "limit": 50}'

# Run only content generation
curl -X POST http://localhost:8000/api/pipeline/run/ \
  -H "Content-Type: application/json" \
  -d '{"type": "generate", "limit": 10}'

# Run only publishing
curl -X POST http://localhost:8000/api/pipeline/run/ \
  -H "Content-Type: application/json" \
  -d '{"type": "publish", "limit": 5}'
```

## Configuration

### Default Settings

| Key | Default | Description |
|-----|---------|-------------|
| `publishing_enabled` | `true` | Kill-switch for publishing |
| `max_articles_per_day` | `5` | Maximum articles per day |
| `score_thresholds.auto_reject` | `40` | Score below which items are auto-rejected |
| `score_thresholds.auto_approve` | `70` | Score above which items are auto-approved |

### Update Configuration

```bash
curl -X POST http://localhost:8000/api/pipeline/config/ \
  -H "Content-Type: application/json" \
  -d '{"key": "max_articles_per_day", "value": 10}'
```

## Monitoring

### Pipeline Statistics

```bash
curl http://localhost:8000/api/pipeline/stats/
```

Returns:
- Scraped items count (total, today, pending)
- Qualified items count (by status)
- Drafts count (by status)
- Published articles count (today, this week)
- Items by source
- Recent pipeline runs
- Current configuration

### Pipeline Runs

```bash
# All runs
curl http://localhost:8000/api/pipeline/runs/

# Failed runs only
curl "http://localhost:8000/api/pipeline/runs/?status=failed"

# Scraping runs only
curl "http://localhost:8000/api/pipeline/runs/?type=scrape"
```

## Safety Features

### Idempotency

- Each scraper run has a unique `batch_id`
- Items are deduplicated using content hash (SHA256 of source + title + URL)
- Duplicate items are automatically skipped

### Logging

- All pipeline runs are logged in `pipeline_runs` table
- Each run tracks: items processed, succeeded, failed
- Detailed logs stored as JSON in the `logs` field

### Rate Limiting

- Maximum 5 articles published per day
- Publish times spread throughout the day
- Configurable via `max_articles_per_day` setting

### Kill-Switch

- Publishing can be instantly disabled via API
- All publish operations check the kill-switch before proceeding
- Manual override always available

## Troubleshooting

### Common Issues

1. **Scraper fails**: Check logs in `pipeline_runs`, retry will happen automatically after 30 minutes

2. **No items being scored**: Ensure items have `status=scraped` in `raw_scraped_items`

3. **Content generation fails**: Check OpenAI API key is configured in settings

4. **Publishing disabled**: Check `publishing_enabled` config setting

### Debug Commands

```bash
# Check pipeline status
curl http://localhost:8000/api/pipeline/stats/

# Check recent runs
curl "http://localhost:8000/api/pipeline/runs/?limit=10"

# Check pending items
curl "http://localhost:8000/api/pipeline/scraped/?status=scraped"

# Check approved items without drafts
curl "http://localhost:8000/api/pipeline/qualified/?status=auto_approved"
```

## Database Migrations

After deploying, run migrations to create the pipeline tables:

```bash
python manage.py makemigrations api
python manage.py migrate
```

## Environment Variables

Required environment variables:
- `OPENAI_API_KEY`: For AI scoring and content generation
- `DATABASE_*`: PostgreSQL connection settings

## Frontend Integration

The News page should use the `/api/pipeline/feed/` endpoint:

```javascript
// Get today's news
const today = await fetch('/api/pipeline/feed/?period=today');

// Get yesterday's news
const yesterday = await fetch('/api/pipeline/feed/?period=yesterday');

// Get this week's news
const week = await fetch('/api/pipeline/feed/?period=week');

// Get highlights (score >= 70)
const highlights = await fetch('/api/pipeline/feed/?period=week&highlights=true');
```

The existing `/api/news/` endpoint continues to work for backward compatibility.
