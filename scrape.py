"""
ScrapingBee Crawler
Reads URLs from urls.txt and crawls each page using the ScrapingBee API.
Automatically discovers alternate language versions via hreflang tags.
Results are saved as JSON in the output/ directory.
"""

import os
import json
import time
import hashlib
from pathlib import Path
from urllib.parse import urljoin
from scrapingbee import ScrapingBeeClient
from bs4 import BeautifulSoup


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


def extract_hreflang_urls(html, base_url):
    """Extract alternate language URLs from hreflang link tags."""
    soup = BeautifulSoup(html, "html.parser")
    alt_urls = {}
    for link in soup.find_all("link", rel="alternate", hreflang=True):
        href = link.get("href")
        lang = link.get("hreflang")
        if href and lang:
            alt_urls[lang] = urljoin(base_url, href)
    return alt_urls


def crawl_url(client, url, output_dir, render_js=False):
    """Crawl a single URL and save the result. Returns (result_dict, html_text)."""
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
        filename = f"{slug_from_url(url)}.html"
        filepath = output_dir / filename
        filepath.write_text(response.text, encoding="utf-8")
        result["output_file"] = str(filepath)
        return result, response.text
    else:
        result["error"] = response.text[:500]
        return result, None


def crawl(urls, api_key, render_js=False, delay_between=1):
    """
    Crawl a list of URLs using ScrapingBee.
    For each page, automatically discovers and crawls alternate language
    versions found in hreflang tags.

    Args:
        urls: List of URLs to crawl (can be just the English versions).
        api_key: ScrapingBee API key.
        render_js: Whether to render JavaScript (costs more credits).
        delay_between: Seconds to wait between requests.
    """
    client = ScrapingBeeClient(api_key=api_key)
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    results = []
    crawled = set()
    counter = 0

    for url in urls:
        if url in crawled:
            continue

        counter += 1
        print(f"[{counter}] Crawling: {url}")
        crawled.add(url)

        try:
            result, html = crawl_url(client, url, output_dir, render_js)
            if result["success"]:
                print(f"  ✓ Saved ({result['content_length']} chars)")
            else:
                print(f"  ✗ Failed with status {result['status_code']}")
            results.append(result)

            # Discover and crawl alternate language versions
            if html:
                alt_urls = extract_hreflang_urls(html, url)
                if alt_urls:
                    langs = list(alt_urls.keys())
                    print(f"  Found {len(alt_urls)} language version(s): {', '.join(langs)}")
                    for lang, alt_url in alt_urls.items():
                        if alt_url in crawled:
                            continue
                        crawled.add(alt_url)
                        time.sleep(delay_between)

                        counter += 1
                        print(f"  [{counter}] Crawling [{lang}]: {alt_url}")
                        try:
                            alt_result, _ = crawl_url(client, alt_url, output_dir, render_js)
                            alt_result["language"] = lang
                            alt_result["source_url"] = url
                            if alt_result["success"]:
                                print(f"    ✓ Saved ({alt_result['content_length']} chars)")
                            else:
                                print(f"    ✗ Failed with status {alt_result['status_code']}")
                            results.append(alt_result)
                        except Exception as e:
                            results.append({"url": alt_url, "language": lang, "source_url": url, "success": False, "error": str(e)})
                            print(f"    ✗ Error: {e}")

        except Exception as e:
            results.append({"url": url, "success": False, "error": str(e)})
            print(f"  ✗ Error: {e}")

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
