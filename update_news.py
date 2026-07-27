from __future__ import annotations

import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUTPUT_FILE = ROOT / "news.json"

MAX_PER_FEED = 18
MAX_TOTAL = 140
REQUEST_TIMEOUT = 25

FEEDS = [
    {
        "category": "Private Equity",
        "query": '"private equity" (fund OR buyout OR acquisition OR fundraising OR "final close") when:14d',
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    },
    {
        "category": "Private Credit",
        "query": '("private credit" OR "direct lending") (fund OR financing OR fundraising OR loan) when:14d',
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    },
    {
        "category": "Infrastructure",
        "query": '("infrastructure fund" OR "infrastructure investment") (energy OR digital OR transport OR "final close") when:14d',
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    },
    {
        "category": "Real Estate",
        "query": '("real estate fund" OR "real estate debt") (investment OR fundraising OR transaction) when:14d',
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    },
    {
        "category": "Secondaries",
        "query": '("private markets secondaries" OR "continuation fund" OR "GP-led secondary") when:21d',
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    },
    {
        "category": "GP Stakes",
        "query": '("GP stakes" OR "asset manager minority stake") when:30d',
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    },
    {
        "category": "ABF",
        "query": '("asset based finance" OR "asset-backed finance") "private credit" when:30d',
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    },
    {
        "category": "SRT",
        "query": '("significant risk transfer" OR "synthetic risk transfer") bank when:30d',
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    },
    {
        "category": "CLO",
        "query": '("CLO fund" OR "collateralized loan obligation") manager when:14d',
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    },
    {
        "category": "국내 대체투자",
        "query": '(대체투자 OR 사모펀드 OR 사모대출 OR 인프라펀드 OR 부동산펀드) when:14d',
        "hl": "ko",
        "gl": "KR",
        "ceid": "KR:ko",
    },
]


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]", "", value.lower())


def stable_id(url: str, title: str) -> str:
    raw = (url or title).encode("utf-8")
    return "n-" + hashlib.sha1(raw).hexdigest()[:16]


def parse_date(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    formats = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(value.strip(), fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            continue

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def classify_region(text: str) -> str:
    value = text.lower()
    rules = [
        ("Korea", r"korea|korean|한국|국내|서울|국민연금|한국투자공사|공제회"),
        ("North America", r"united states|u\.s\.|america|canada|new york|california|texas"),
        ("Europe", r"europe|european|united kingdom|\buk\b|britain|germany|france|italy|spain|netherlands"),
        ("Asia Pacific", r"asia|japan|china|hong kong|singapore|australia|india|apac"),
        ("Middle East", r"middle east|uae|saudi|qatar|abu dhabi|dubai"),
    ]
    for region, pattern in rules:
        if re.search(pattern, value, flags=re.I):
            return region
    return "Global"


def google_news_url(feed: dict[str, str]) -> str:
    params = urllib.parse.urlencode(
        {
            "q": feed["query"],
            "hl": feed["hl"],
            "gl": feed["gl"],
            "ceid": feed["ceid"],
        }
    )
    return f"https://news.google.com/rss/search?{params}"


def read_child_text(item: ET.Element, tag: str) -> str:
    child = item.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def extract_source(item: ET.Element, raw_title: str) -> str:
    source = item.find("source")
    if source is not None and source.text:
        return clean_text(source.text)

    parts = raw_title.rsplit(" - ", 1)
    if len(parts) == 2:
        return clean_text(parts[1])
    return "Google News"


def clean_title(raw_title: str, source: str) -> str:
    title = clean_text(raw_title)
    suffix = f" - {source}"
    if source and title.lower().endswith(suffix.lower()):
        title = title[: -len(suffix)].strip()
    return title


def make_summary(title: str, description: str, source: str) -> str:
    text = clean_text(description)

    # Google News 설명문에 제목과 출처만 반복되는 경우가 많아 중복을 제거합니다.
    for repeated in (title, source):
        if repeated:
            text = re.sub(re.escape(repeated), " ", text, flags=re.I)

    text = re.sub(r"\s+", " ", text).strip(" -–—:|")

    if not text or len(text) < 25:
        return f"{source}가 보도한 기사입니다. 자세한 내용은 원문에서 확인할 수 있습니다."

    if len(text) > 420:
        text = text[:417].rstrip() + "…"

    return text


def fetch_feed(feed: dict[str, str]) -> list[dict[str, Any]]:
    url = google_news_url(feed)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; AltBrief/3.0; +https://github.com/)",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
    )

    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        xml_bytes = response.read()

    root = ET.fromstring(xml_bytes)
    articles: list[dict[str, Any]] = []

    for item in root.findall(".//item")[:MAX_PER_FEED]:
        raw_title = read_child_text(item, "title")
        link = read_child_text(item, "link")
        description = read_child_text(item, "description")
        pub_date = read_child_text(item, "pubDate")

        source = extract_source(item, raw_title)
        title = clean_title(raw_title, source)

        if not title or not link:
            continue

        combined = f"{title} {description}"
        articles.append(
            {
                "id": stable_id(link, title),
                "title": title,
                "source": source,
                "published_at": parse_date(pub_date),
                "category": feed["category"],
                "region": classify_region(combined),
                "summary": make_summary(title, description, source),
                "url": link,
            }
        )

    return articles


def load_existing_articles() -> list[dict[str, Any]]:
    if not OUTPUT_FILE.exists():
        return []

    try:
        payload = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("articles", "news", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value

    return []


def deduplicate(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []

    sorted_articles = sorted(
        articles,
        key=lambda item: str(item.get("published_at", "")),
        reverse=True,
    )

    for article in sorted_articles:
        key = normalize_key(str(article.get("title", "")))[:180]
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(article)

    return result[:MAX_TOTAL]


def main() -> None:
    collected: list[dict[str, Any]] = []
    errors: list[str] = []

    for index, feed in enumerate(FEEDS, start=1):
        try:
            articles = fetch_feed(feed)
            collected.extend(articles)
            print(f"[{index}/{len(FEEDS)}] {feed['category']}: {len(articles)}건")
        except Exception as exc:  # 각 피드 실패가 전체 수집을 막지 않도록 처리
            message = f"{feed['category']}: {type(exc).__name__}: {exc}"
            errors.append(message)
            print(f"[WARN] {message}")

        time.sleep(0.4)

    # 일시적 RSS 장애 때 기존 news.json이 빈 파일로 덮이지 않도록 합니다.
    existing = load_existing_articles()
    if not collected:
        if existing:
            print("[WARN] 신규 수집 결과가 없어 기존 news.json을 유지합니다.")
            return
        raise RuntimeError("모든 RSS 수집에 실패했고 기존 데이터도 없습니다.")

    merged = deduplicate(collected + existing)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "article_count": len(merged),
        "collection_errors": errors,
        "articles": merged,
    }

    OUTPUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[DONE] {OUTPUT_FILE.name}: {len(merged)}건 저장")
    if errors:
        print(f"[INFO] 일부 피드 실패: {len(errors)}개")


if __name__ == "__main__":
    main()
