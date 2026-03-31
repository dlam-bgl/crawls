"""
ScrapingBee Crawler
Reads URLs from urls.txt and crawls each page using the ScrapingBee API.
Results are saved as JSON in the output/ directory.
"""

import os
import json
import time
import hashlib
from pathlib import Path
from scrapingbee import ScrapingBeeClient


def load_urls(filepath="urls.txt"):
    """Load URLs from a text file (one URL per line)."""
    with open(filepath, "r") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return urls


def get_api_key():
    """Get API key from environment variable or .env file."""
    key = os.environ.get("SCRAPINGBEE_API_KEY")
    if key:
        return key

    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("SCRAPINGBEE_API_KEY="):
                    return line.split("=", 1)[1].strip()

    raise ValueError(
        "SCRAPINGBEE_API_KEY not found. "
        "Set it as an environment variable or in a .env file."
    )


def slug_from_url(url):
    """Create a filesystem-safe filename from a URL."""
    return hashlib.md5(url.encode()).hexdigest()[:12]


def crawl(urls, api_key, render_js=False, delay_between=1):
    """
    Crawl a list of URLs using ScrapingBee.

    Args:
        urls: List of URLs to crawl.
        api_key: ScrapingBee API key.
        render_js: Whether to render JavaScript (costs more credits).
        delay_between: Seconds to wait between requests.
    """
    client = ScrapingBeeClient(api_key=api_key)
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    results = []

    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] Crawling: {url}")

        try:
            response = client.get(
                url,
                params={
                    "render_js": str(render_js).lower(),
                    "premium_proxy": "false",
                },
            )

            result = {
                "url": url,
                "status_code": response.status_code,
                "content_length": len(response.text),
                "success": response.ok,
            }

            if response.ok:
                # Save HTML to individual file
                filename = f"{slug_from_url(url)}.html"
                filepath = output_dir / filename
                filepath.write_text(response.text, encoding="utf-8")
                result["output_file"] = str(filepath)
                print(f"  ✓ Saved ({len(response.text)} chars) -> {filename}")
            else:
                result["error"] = response.text[:500]
                print(f"  ✗ Failed with status {response.status_code}")

        except Exception as e:
            result = {"url": url, "success": False, "error": str(e)}
            print(f"  ✗ Error: {e}")

        results.append(result)

        if i < len(urls):
            time.sleep(delay_between)

    # Save summary
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    succeeded = sum(1 for r in results if r.get("success"))
    print(f"\nDone: {succeeded}/{len(results)} succeeded. Summary -> {summary_path}")
    return results


if __name__ == "__main__":
    api_key = get_api_key()
    urls = load_urls()
    print(f"Loaded {len(urls)} URL(s)\n")
    crawl(urls, api_key)
