from typing import List, Dict
import hashlib
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from services.knowledge import knowledge_system, stats
from services.db import save_to_db, manage_cache

SEARXNG_URLS = ["http://localhost:8888"]
SCRAPE_TIMEOUT = 15


async def advanced_web_search(query: str, max_results: int = 5, language: str = "tr") -> List[Dict]:
    """Gelişmiş web araması (SearXNG + kalite filtresi)"""
    cache_key = f"search_{query}_{max_results}_{language}"

    cached = manage_cache(cache_key)
    if cached:
        print(f"[SEARXNG] ✅ Cache HIT")
        return cached

    all_results: List[Dict] = []

    for searxng_url in SEARXNG_URLS:
        try:
            print(f"[SEARXNG] 🔄 Gelişmiş arama: {searxng_url}")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
            }

            search_variations = [
                query,
                f"{query} 2024",
                f"{query} detaylı",
            ]

            for search_query in search_variations:
                async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                    response = await client.get(
                        f"{searxng_url}/search",
                        params={
                            "q": search_query,
                            "format": "json",
                            "language": language,
                            "safesearch": "0"
                        }
                    )

                    if response.status_code == 200:
                        data = response.json()

                        for item in data.get("results", []):
                            url = item.get("url", "")

                            skip_domains = [
                                'facebook.com', 'twitter.com', 'instagram.com',
                                'youtube.com', 'tiktok.com', 'pinterest.com'
                            ]
                            if any(d in url for d in skip_domains):
                                continue

                            content = item.get("content", "") or ""
                            title = item.get("title", "") or ""

                            quality_check = knowledge_system.assess_content_quality_advanced(
                                content, title, url
                            )

                            if quality_check["quality_score"] < 0.3:
                                stats["quality_rejected"] += 1
                                continue

                            result = {
                                "title": title[:150],
                                "url": url,
                                "content": content[:400],
                                "quality_score": quality_check["quality_score"],
                                "domain_trust": quality_check["domain_trust"]
                            }

                            if quality_check["domain_trust"] > 0.8:
                                all_results.insert(0, result)
                            else:
                                all_results.append(result)

                            if len(all_results) >= max_results * 2:
                                break

                if len(all_results) >= max_results * 2:
                    break

        except Exception as e:
            print(f"[SEARXNG] ❌ {searxng_url} - {e}")
            continue

    all_results.sort(
        key=lambda x: x.get("quality_score", 0) * x.get("domain_trust", 0.5),
        reverse=True
    )
    final_results = all_results[:max_results]

    manage_cache(cache_key, final_results)
    print(f"[SEARXNG] ✅ {len(final_results)} kaliteli sonuç ({len(all_results)} aday)")
    return final_results


async def scrape_url(url: str) -> str:
    """URL'den metin çekme (scraping)"""
    try:
        async with httpx.AsyncClient(
            timeout=SCRAPE_TIMEOUT,
            follow_redirects=True,
        ) as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = await client.get(url, headers=headers)

            if response.status_code != 200:
                return ""

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')

            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe', 'noscript']):
                tag.decompose()

            main = (
                soup.find('main') or
                soup.find('article') or
                soup.find('div', class_='content') or
                soup.find('body')
            )

            if main:
                text = main.get_text(separator=' ', strip=True)
            else:
                text = soup.get_text(separator=' ', strip=True)

            lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 20]
            text = ' '.join(lines)

            return text[:8000]

    except Exception as e:
        print(f"[SCRAPE] ❌ {url[:30]}: {str(e)[:30]}")
        return ""
