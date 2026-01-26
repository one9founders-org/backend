# One9Founders AI News Automation - Scrapers

Production-ready Python scrapers for discovering and collecting AI tools and news from multiple sources. Designed for daily automated execution via n8n workflows.

## Overview

This system provides modular, CLI-driven scrapers that collect AI tool and model data from four major sources:

1. **Product Hunt** - AI product launches and trending tools
2. **There's An AI For That (TAAFT)** - Newly added AI tools directory
3. **Futurepedia** - Category-organized AI tools database
4. **Hugging Face** - New AI models from the ML community

All scrapers output data in a standardized JSON format suitable for n8n ingestion and Airtable storage.

## Requirements

- Python 3.11+
- Chrome/Chromium browser (for Selenium-based scrapers)
- ChromeDriver (auto-managed via webdriver-manager)

### Python Dependencies

The scrapers use dependencies already included in the main `requirements.txt`:

```
beautifulsoup4==4.12.3
selenium==4.27.1
webdriver-manager==4.0.2
requests==2.32.3
```

## Project Structure

```
backend/
├── scrapers/
│   ├── __init__.py
│   ├── README.md              # This file
│   ├── producthunt/
│   │   ├── __init__.py
│   │   └── scraper.py         # Product Hunt scraper
│   ├── taaft/
│   │   ├── __init__.py
│   │   └── scraper.py         # TAAFT scraper
│   ├── futurepedia/
│   │   ├── __init__.py
│   │   └── scraper.py         # Futurepedia scraper
│   └── huggingface/
│       ├── __init__.py
│       └── scraper.py         # Hugging Face API scraper
├── utils/
│   ├── __init__.py
│   ├── logger.py              # Structured JSON logging
│   ├── output.py              # Standardized output writer
│   ├── rate_limiter.py        # Request rate limiting
│   ├── retry.py               # Exponential backoff retry
│   └── selenium_driver.py     # WebDriver configuration
├── config/
│   └── scraper_settings.py    # Scraper configuration
├── output/                    # JSON output files
└── logs/                      # JSON log files
```

## Output Schema

All scrapers emit JSON in this normalized format for n8n compatibility:

```json
{
  "source": "ProductHunt|TAAFT|Futurepedia|HuggingFace",
  "scrape_date": "2024-01-15T10:30:00.000000Z",
  "items": [
    {
      "title": "Tool/Model Name",
      "description": "Full description text",
      "url": "https://source-site.com/tool-page",
      "external_url": "https://tool-website.com",
      "category": "primary-category",
      "tags": ["tag1", "tag2"],
      "metrics": {
        "upvotes": 100,
        "downloads": 5000
      },
      "images": ["https://image-url.com/thumb.png"],
      "raw": {}
    }
  ]
}
```

## Running Scrapers

### Product Hunt

Scrapes AI product launches from Product Hunt's AI topics page.

```bash
cd /home/ubuntu/repos/backend
source ~/venvs/backend/bin/activate

# Basic usage
python -m scrapers.producthunt.scraper --limit 20

# With options
python -m scrapers.producthunt.scraper \
  --limit 50 \
  --days-back 7 \
  --output /path/to/output.json \
  --headless
```

**CLI Options:**
- `--limit`: Maximum items to scrape (default: 100)
- `--days-back`: Filter to recent days (default: 7)
- `--output`: Custom output file path
- `--headless`: Run browser headless (default: True)
- `--no-headless`: Show browser window

### There's An AI For That (TAAFT)

Scrapes newly added AI tools with infinite scroll support.

```bash
python -m scrapers.taaft.scraper --limit 50

# With options
python -m scrapers.taaft.scraper \
  --limit 100 \
  --output /path/to/output.json
```

**CLI Options:**
- `--limit`: Maximum items to scrape (default: 100)
- `--output`: Custom output file path
- `--headless`: Run browser headless (default: True)

### Futurepedia

Scrapes AI tools by category with configurable limits per category.

```bash
python -m scrapers.futurepedia.scraper --limit 20

# Specific categories
python -m scrapers.futurepedia.scraper \
  --limit 10 \
  --categories "text,image,video"
```

**CLI Options:**
- `--limit`: Maximum items per category (default: 20)
- `--categories`: Comma-separated category list
- `--output`: Custom output file path
- `--headless`: Run browser headless (default: True)

**Available Categories:** text, image, video, audio, code, business, marketing, productivity, education, lifestyle

### Hugging Face

Scrapes new AI models using the Hugging Face API (no browser required).

```bash
python -m scrapers.huggingface.scraper --limit 50

# With filters
python -m scrapers.huggingface.scraper \
  --limit 100 \
  --days-back 7 \
  --min-downloads 1000
```

**CLI Options:**
- `--limit`: Maximum models to scrape (default: 100)
- `--days-back`: Filter to recent days (default: 7)
- `--min-downloads`: Minimum download count filter (default: 1000)
- `--output`: Custom output file path

## n8n Integration

### Code Node Example

```javascript
const { execSync } = require('child_process');

// Run scraper
const result = execSync(
  'cd /home/ubuntu/repos/backend && ' +
  'source ~/venvs/backend/bin/activate && ' +
  'python -m scrapers.huggingface.scraper --limit 50 --output /tmp/hf_output.json',
  { encoding: 'utf-8' }
);

// Read output
const fs = require('fs');
const data = JSON.parse(fs.readFileSync('/tmp/hf_output.json', 'utf-8'));

return data.items.map(item => ({
  json: item
}));
```

### Workflow Schedule

Recommended daily schedule:
- **06:00 UTC**: Hugging Face (API-based, fastest)
- **07:00 UTC**: Product Hunt (web scraping)
- **08:00 UTC**: TAAFT (web scraping with scroll)
- **09:00 UTC**: Futurepedia (multi-category)

## Configuration

Environment variables for customization (optional):

```bash
# Rate limiting
export SCRAPER_MIN_DELAY=2.0
export SCRAPER_MAX_DELAY=7.0

# Retry settings
export SCRAPER_MAX_RETRIES=3
export SCRAPER_RETRY_BACKOFF_FACTOR=2.0

# Timeouts
export SCRAPER_REQUEST_TIMEOUT=30
export SCRAPER_PAGE_LOAD_TIMEOUT=60

# Output directories
export SCRAPER_OUTPUT_DIR=/path/to/output
export SCRAPER_LOG_DIR=/path/to/logs

# Chrome settings (if needed)
export CHROME_BINARY=/path/to/chrome
export CHROMEDRIVER_PATH=/path/to/chromedriver
```

## Logging

All scrapers produce structured JSON logs in the `logs/` directory:

```json
{
  "timestamp": "2024-01-15T10:30:00.000000Z",
  "level": "INFO",
  "logger": "huggingface",
  "message": "Scraping complete. Total items: 50",
  "module": "scraper",
  "function": "scrape",
  "line": 245
}
```

Log files are named: `{scraper}_{timestamp}.json`

## Error Handling

The scrapers implement several resilience features:

1. **Retry with Exponential Backoff**: Failed requests retry up to 3 times with increasing delays
2. **Rate Limiting**: Randomized delays (2-7 seconds) between requests
3. **Graceful Degradation**: Missing fields don't crash the scraper
4. **Timeout Handling**: Configurable timeouts for page loads and requests

### Common Failure Modes

| Issue | Cause | Resolution |
|-------|-------|------------|
| Empty results | Site structure changed | Update CSS selectors |
| Timeout errors | Slow network/site | Increase timeout settings |
| Rate limiting | Too many requests | Increase delay settings |
| Chrome crash | Memory issues | Reduce batch size |

## Expected Output Volume

Daily scraping with default settings:

| Source | Items/Day | Notes |
|--------|-----------|-------|
| Product Hunt | 20-50 | AI topic launches |
| TAAFT | 50-100 | Newly added tools |
| Futurepedia | 100-200 | 10 categories x 20 each |
| Hugging Face | 50-100 | Models with 1000+ downloads |

**Total**: 220-450 items/day

## Development

### Running Tests

```bash
cd /home/ubuntu/repos/backend
source ~/venvs/backend/bin/activate

# Test individual scraper
python -c "
from scrapers.huggingface.scraper import HuggingFaceScraper
scraper = HuggingFaceScraper(limit=5)
items = scraper.scrape()
print(f'Scraped {len(items)} items')
"
```

### Adding New Scrapers

1. Create directory: `scrapers/newsource/`
2. Add `__init__.py` and `scraper.py`
3. Implement scraper class with:
   - `__init__()` with CLI-compatible parameters
   - `scrape()` returning normalized items
   - `save_output()` for file writing
4. Add `main()` function with argparse CLI
5. Update configuration in `config/scraper_settings.py`

## Security Notes

- No hardcoded credentials or API keys
- Respects robots.txt guidelines
- Rate limiting prevents server overload
- User-Agent identifies as standard browser
