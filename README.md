# ScrapingBee Crawler

Crawls a list of URLs using the [ScrapingBee](https://www.scrapingbee.com/) API and saves the HTML output.

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Create a `.env` file with your API key:
   ```
   SCRAPINGBEE_API_KEY=your_key_here
   ```

3. Add target URLs to `urls.txt` (one per line; lines starting with `#` are ignored).

## Usage

```
python scrape.py
```

Results are saved to the `output/` directory:
- Individual HTML files per URL
- `summary.json` with status for all crawled pages
