"""
ScrapingBee Link Checker
Reads a CSV of pages and target links, crawls each page via ScrapingBee,
and checks whether the specified internal link exists on the page.
Also auto-discovers alternate language versions via hreflang and checks those too.
Results are saved as CSV and JSON in the output/ directory.
"""

import csv
import os
import json
import time
import hashlib
from pathlib import Path
from urllib.parse import urljoin, urlparse
from scrapingbee import ScrapingBeeClient
from bs4 import BeautifulSoup


def load_csv(filepath="lobby-internal-links.csv"):
    """Load page/link pairs from CSV. Returns list of (page_url, target_link)."""
    pairs = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            if len(row) >= 2 and row[0].strip():
                pairs.append((row[0].strip(), row[1].strip()))
    return pairs


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


def check_link_on_page(html, target_link, page_url):
    """
    Check if a target link path appears in any <a> tag on the page.
    Handles language-prefixed paths (e.g. /en/casino, /sv/casino for target /casino).
    Returns (found: bool, matching_hrefs: list, anchor_texts: list).
    """
    soup = BeautifulSoup(html, "html.parser")
    matches = []
    target_clean = target_link.rstrip("/")

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        resolved = urljoin(page_url, href)
        path = urlparse(resolved).path.rstrip("/")

        matched = False
        if path == target_clean or path.endswith(target_clean):
            matched = True
        elif len(path) > 3:
            parts = path.split("/")
            if len(parts) >= 3 and len(parts[1]) in (2, 5):
                stripped = "/" + "/".join(parts[2:])
                if stripped.rstrip("/") == target_clean:
                    matched = True

        if matched:
            anchor = a_tag.get_text(strip=True)
            matches.append((href, anchor))

    # Deduplicate by href while preserving order
    seen = set()
    unique_hrefs = []
    anchor_texts = []
    for href, anchor in matches:
        if href not in seen:
            seen.add(href)
            unique_hrefs.append(href)
            anchor_texts.append(anchor)
    return len(unique_hrefs) > 0, unique_hrefs, anchor_texts


def extract_hreflang_urls(html, base_url):
    """Extract alternate language URLs from hreflang link tags."""
    soup = BeautifulSoup(html, "html.parser")
    alt_urls = {}
    for link in soup.find_all("link", rel="alternate", hreflang=True):
        href = link.get("href")
        lang = link.get("hreflang")
        if href and lang and lang != "x-default":
            alt_urls[lang] = urljoin(base_url, href)
    return alt_urls


def adapt_target_for_lang(target_link, lang):
    """Adjust the target link path for a different language (e.g. /casino -> /casino)."""
    # Target links like /casino, /sports, /esports are language-independent paths
    return target_link


def run(pairs, api_key, render_js=False, delay_between=1):
    """
    For each (page_url, target_link) pair:
    1. Crawl the English page
    2. Check if the target link exists
    3. Discover hreflang alternate language pages
    4. Crawl and check those too
    """
    client = ScrapingBeeClient(api_key=api_key)
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    results = []
    counter = 0

    for page_url, target_link in pairs:
        counter += 1
        print(f"\n[{counter}/{len(pairs)}] {page_url}")
        print(f"  Target link: {target_link}")

        try:
            response = client.get(page_url, params={
                "render_js": str(render_js).lower(),
                "premium_proxy": "false",
            })

            if not response.ok:
                print(f"  ✗ HTTP {response.status_code}")
                results.append({
                    "page": page_url, "target_link": target_link,
                    "language": "en", "status_code": response.status_code,
                    "link_found": None, "error": "page fetch failed",
                })
                time.sleep(delay_between)
                continue

            html = response.text
            # Save HTML
            filepath = output_dir / f"{slug_from_url(page_url)}.html"
            filepath.write_text(html, encoding="utf-8")

            found, matches, anchors = check_link_on_page(html, target_link, page_url)
            status = "✓ FOUND" if found else "✗ NOT FOUND"
            anchor_info = f' anchor="{anchors[0]}"' if anchors else ""
            print(f"  [en] {status}" + (f" ({len(matches)} match(es)){anchor_info}" if found else ""))

            results.append({
                "page": page_url, "target_link": target_link,
                "language": "en", "status_code": response.status_code,
                "link_found": found, "matches": matches, "anchor_texts": anchors,
            })

            # Check alternate language versions
            alt_urls = extract_hreflang_urls(html, page_url)
            for lang, alt_url in alt_urls.items():
                time.sleep(delay_between)
                lang_target = adapt_target_for_lang(target_link, lang)

                try:
                    alt_resp = client.get(alt_url, params={
                        "render_js": str(render_js).lower(),
                        "premium_proxy": "false",
                    })
                    if alt_resp.ok:
                        alt_html = alt_resp.text
                        alt_filepath = output_dir / f"{slug_from_url(alt_url)}.html"
                        alt_filepath.write_text(alt_html, encoding="utf-8")

                        alt_found, alt_matches, alt_anchors = check_link_on_page(alt_html, lang_target, alt_url)
                        alt_status = "✓ FOUND" if alt_found else "✗ NOT FOUND"
                        alt_anchor_info = f' anchor="{alt_anchors[0]}"' if alt_anchors else ""
                        print(f"  [{lang}] {alt_status}" + (f" ({len(alt_matches)} match(es)){alt_anchor_info}" if alt_found else ""))

                        results.append({
                            "page": alt_url, "target_link": lang_target,
                            "language": lang, "status_code": alt_resp.status_code,
                            "link_found": alt_found, "matches": alt_matches,
                            "anchor_texts": alt_anchors, "source_page": page_url,
                        })
                    else:
                        print(f"  [{lang}] ✗ HTTP {alt_resp.status_code}")
                        results.append({
                            "page": alt_url, "target_link": lang_target,
                            "language": lang, "status_code": alt_resp.status_code,
                            "link_found": None, "error": "page fetch failed",
                            "source_page": page_url,
                        })
                except Exception as e:
                    print(f"  [{lang}] ✗ Error: {e}")
                    results.append({
                        "page": alt_url, "target_link": lang_target,
                        "language": lang, "link_found": None, "error": str(e),
                        "source_page": page_url,
                    })

        except Exception as e:
            print(f"  ✗ Error: {e}")
            results.append({
                "page": page_url, "target_link": target_link,
                "language": "en", "link_found": None, "error": str(e),
            })

        time.sleep(delay_between)

    # Save JSON summary
    summary_json = output_dir / "summary.json"
    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Save CSV report
    report_csv = output_dir / "report.csv"
    with open(report_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Page", "Target Link", "Language", "Link Found", "Anchor Text", "Status Code", "Matches", "Error"])
        for r in results:
            writer.writerow([
                r.get("page", ""),
                r.get("target_link", ""),
                r.get("language", ""),
                r.get("link_found", ""),
                "; ".join(r.get("anchor_texts", [])),
                r.get("status_code", ""),
                "; ".join(r.get("matches", [])),
                r.get("error", ""),
            ])

    found_count = sum(1 for r in results if r.get("link_found") is True)
    not_found = sum(1 for r in results if r.get("link_found") is False)
    errors = sum(1 for r in results if r.get("link_found") is None)
    print(f"\n{'='*60}")
    print(f"Results: {found_count} found, {not_found} not found, {errors} errors")
    print(f"Report -> {report_csv}")
    print(f"Details -> {summary_json}")
    return results


if __name__ == "__main__":
    api_key = get_api_key()
    pairs = load_csv()
    print(f"Loaded {len(pairs)} page/link pair(s)")
    run(pairs, api_key)
