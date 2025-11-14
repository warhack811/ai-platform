from typing import List, Dict
import hashlib
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from services.knowledge import knowledge_system, stats
from services.db import save_to_db, manage_cache

SEARXNG_URLS = ["http://localhost:8888"]
SCRAPE_TIMEOUT = 15


async def advanced_web_search(
    query: str,
    max_results: int = 5,
    language: str = "tr",
) -> List[Dict]:
    """Gelişmiş web araması (SearXNG + kalite filtresi + cache)"""

    cache_key = f"search_{query}_{max_results}_{language}"

    # Cache kontrolü (boş listeyi cache'ten okumayalım)
    cached = manage_cache(cache_key)
    if cached:  # sadece truthy ise ([], {}, None = miss)
        print(f"[SEARXNG] ✅ Cache HIT ({len(cached)} sonuç)")
        return cached

    all_results: List[Dict] = []
    raw_candidates = 0

    for searxng_url in SEARXNG_URLS:
        try:
            print(f"[SEARXNG] 🔄 Gelişmiş arama: {searxng_url}")

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36"
                ),
                "Accept": "application/json",
            }

            # Aynı sorguyu farklı varyasyonlarla dene
            search_variations = [
                query,
                f"{query} 2024",
                f"{query} detaylı",
            ]

            # Dil parametresini biraz esnek tutalım: önce 'tr', sonra 'all'
            language_candidates = [language, "all"]

            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                for search_query in search_variations:
                    for lang in language_candidates:
                        params = {
                            "q": search_query,
                            "format": "json",
                            "safesearch": "0",
                        }
                        # SearXNG bazı config'lerde language paramı sorun çıkarabiliyor,
                        # bu yüzden boş / None ise göndermiyoruz.
                        if lang:
                            params["language"] = lang

                        response = await client.get(
                            f"{searxng_url}/search",
                            params=params,
                        )

                        if response.status_code != 200:
                            print(
                                f"[SEARXNG] ❌ HTTP {response.status_code} "
                                f"({search_query}, lang={lang})"
                            )
                            continue

                        data = response.json()
                        results = data.get("results") or []

                        if not results:
                            print(
                                f"[SEARXNG] ⚠️ Boş sonuç seti "
                                f"({search_query}, lang={lang})"
                            )
                            continue

                        for item in results:
                            raw_candidates += 1

                            url = item.get("url", "") or ""
                            title = item.get("title", "") or ""
                            content = item.get("content", "") or ""

                            # Sosyal medya / gereksiz alanları at
                            skip_domains = [
                                "facebook.com",
                                "twitter.com",
                                "instagram.com",
                                "youtube.com",
                                "tiktok.com",
                                "pinterest.com",
                            ]
                            if any(d in url for d in skip_domains):
                                continue

                            # Kalite analizi
                            quality_check = knowledge_system.assess_content_quality_advanced(
                                content,
                                title,
                                url,
                            )

                            q = quality_check["quality_score"]
                            domain_trust = quality_check["domain_trust"]

                            # Eşik: 0.3'ten 0.15'e düşürdük (daha az agresif)
                            if q < 0.15:
                                stats["quality_rejected"] += 1
                                continue

                            result = {
                                "title": title[:150],
                                "url": url,
                                "content": content[:400],
                                "quality_score": q,
                                "domain_trust": domain_trust,
                            }

                            # Güvenilir domainleri başa al
                            if domain_trust > 0.8:
                                all_results.insert(0, result)
                            else:
                                all_results.append(result)

                            # Çok fazla aday birikmesin
                            if len(all_results) >= max_results * 2:
                                break

                        if len(all_results) >= max_results * 2:
                            break

                    if len(all_results) >= max_results * 2:
                        break

        except Exception as e:
            print(f"[SEARXNG] ❌ {searxng_url} - {e}")
            continue

    # Skorla sırala (kalite * domain güveni)
    all_results.sort(
        key=lambda x: x.get("quality_score", 0) * x.get("domain_trust", 0.5),
        reverse=True,
    )

    final_results = all_results[:max_results]

    # Hiç kaliteli sonuç yoksa ama aday varsa → fallback
    if not final_results and all_results:
        print(
            f"[SEARXNG] ⚠️ Filtrelenen sonuç kalmadı, en iyi "
            f"{max_results} adayı fallback olarak kullanıyorum."
        )
        final_results = all_results[:max_results]

    print(
        f"[SEARXNG] ✅ {len(final_results)} kaliteli sonuç "
        f"({len(all_results)} filtrelenmiş, {raw_candidates} ham aday)"
    )

    # Boş listeyi cache'e yazmanın anlamı yok
    if final_results:
        manage_cache(cache_key, final_results)

    return final_results


async def scrape_url(url: str) -> str:
    """URL'den metin çekme (scraping)"""
    try:
        async with httpx.AsyncClient(
            timeout=SCRAPE_TIMEOUT,
            follow_redirects=True,
        ) as client:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36"
                )
            }
            response = await client.get(url, headers=headers)

        if response.status_code != 200:
            print(f"[SCRAPE] ❌ HTTP {response.status_code} - {url[:60]}")
            return ""

        soup = BeautifulSoup(response.text, "html.parser")

        # Gereksiz tagleri temizle
        for tag in soup(
            [
                "script",
                "style",
                "nav",
                "footer",
                "header",
                "aside",
                "iframe",
                "noscript",
            ]
        ):
            tag.decompose()

        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_="content")
            or soup.find("body")
        )

        if main:
            text = main.get_text(separator=" ", strip=True)
        else:
            text = soup.get_text(separator=" ", strip=True)

        # Çok kısa satırları at
        lines = [
            l.strip()
            for l in text.split("\n")
            if l.strip() and len(l.strip()) > 20
        ]
        text = " ".join(lines)

        return text[:8000]

    except Exception as e:
        print(f"[SCRAPE] ❌ {url[:30]}: {str(e)[:80]}")
        return ""