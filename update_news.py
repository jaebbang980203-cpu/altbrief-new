#!/usr/bin/env python3
"""AltBrief: public Google News RSS collector, no API key required."""
from __future__ import annotations
import hashlib
import html
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs, unquote

import feedparser
import requests

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'news.json'
CONFIG = ROOT / 'sources.json'
KST = timezone(timedelta(hours=9))
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; AltBriefRSS/2.0; public-feed-collector)', 'Accept': 'application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.6'}
MAX_ARTICLES = int(os.getenv('MAX_ARTICLES', '500'))
MAX_AGE_DAYS = int(os.getenv('MAX_AGE_DAYS', '21'))
REQUEST_PAUSE = float(os.getenv('REQUEST_PAUSE', '0.35'))
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('altbrief')


def utcnow():
    return datetime.now(timezone.utc)


def as_iso(value):
    if not value:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        except ValueError:
            try:
                value = parsedate_to_datetime(value)
            except (ValueError, TypeError):
                return None
    if hasattr(value, 'tm_year'):
        value = datetime(*value[:6], tzinfo=timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def clean(value):
    value = re.sub(r'<[^>]*>', ' ', value or '')
    value = html.unescape(value)
    return re.sub(r'\s+', ' ', value).strip()


def stable_id(title, source):
    key = re.sub(r'\W+', '', (title + '|' + source).casefold())
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]


def google_news_url(query, language):
    if language == 'ko':
        settings = {'hl': 'ko', 'gl': 'KR', 'ceid': 'KR:ko'}
    else:
        settings = {'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'}
    return 'https://news.google.com/rss/search?' + urlencode({'q': query, **settings})


def fetch_feed(session, url, attempts=3):
    for attempt in range(attempts):
        try:
            r = session.get(url, headers=HEADERS, timeout=(10, 25))
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            if feed.bozo and not feed.entries:
                raise ValueError(f'Invalid feed: {feed.bozo_exception}')
            return feed.entries
        except (requests.RequestException, ValueError) as exc:
            log.warning('Feed attempt %d/%d failed: %s', attempt + 1, attempts, exc)
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)
    return None


def extract_article(entry, category, region):
    title = clean(entry.get('title', ''))
    source_obj = entry.get('source') or {}
    source = clean(source_obj.get('title') or '')
    if not source and ' - ' in title:
        title, source = title.rsplit(' - ', 1)
        title, source = title.strip(), source.strip()
    link = entry.get('link', '')
    if not title or not link or urlparse(link).scheme not in ('https', 'http'):
        return None
    pub = as_iso(entry.get('published_parsed') or entry.get('published') or entry.get('updated_parsed'))
    if not pub:
        return None
    try:
        published_dt = datetime.fromisoformat(pub.replace('Z', '+00:00'))
    except ValueError:
        return None
    if published_dt > utcnow() + timedelta(days=1) or published_dt < utcnow() - timedelta(days=MAX_AGE_DAYS):
        return None
    summary = clean(entry.get('summary') or entry.get('description') or '')
    # Google News descriptions may repeat the headline and list related headlines.
    if summary.casefold().startswith(title.casefold()):
        summary = summary[len(title):].strip(' -–:')
    summary = summary[:550]
    return {
        'id': stable_id(title, source), 'title': title, 'summary': summary,
        'source': source or 'Google News', 'published_at': pub,
        'url': link, 'category': category, 'region': region,
        'summary_type': 'RSS 공개 설명 (AI 요약 아님)'
    }


def read_existing():
    if not OUTPUT.exists():
        return {'updated_at': None, 'articles': []}
    try:
        obj = json.loads(OUTPUT.read_text(encoding='utf-8'))
        if isinstance(obj, list):
            return {'updated_at': None, 'articles': obj}
        return {'updated_at': obj.get('updated_at'), 'articles': obj.get('articles', [])}
    except (OSError, ValueError) as exc:
        log.warning('Previous news.json unreadable: %s', exc)
        return {'updated_at': None, 'articles': []}


def main():
    sources = json.loads(CONFIG.read_text(encoding='utf-8'))
    existing = read_existing()
    cutoff = utcnow() - timedelta(days=MAX_AGE_DAYS)
    pooled = {}
    for obj in existing['articles']:
        if not isinstance(obj, dict) or not obj.get('title') or not obj.get('url'):
            continue
        try:
            dt = datetime.fromisoformat(obj['published_at'].replace('Z', '+00:00'))
            if dt < cutoff:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        key = obj.get('id') or stable_id(obj['title'], obj.get('source', ''))
        obj['id'] = key
        pooled[key] = obj
    successes, failures, fetched_count = 0, 0, 0
    with requests.Session() as session:
        for source in sources:
            query, category = source['query'], source['category']
            region = source.get('region', 'Global')
            language = source.get('language', 'en')
            url = google_news_url(query, language)
            entries = fetch_feed(session, url)
            if entries is None:
                failures += 1
                log.error('FAILED category=%s query=%s', category, query)
                continue
            successes += 1
            added = 0
            for entry in entries:
                article = extract_article(entry, category, region)
                if not article:
                    continue
                fetched_count += 1
                key = article['id']
                # Prefer nonempty text already present, but refresh stale metadata.
                if key in pooled and len(pooled[key].get('summary') or '') > len(article['summary']):
                    article['summary'] = pooled[key]['summary']
                    article['summary_type'] = pooled[key].get('summary_type', article['summary_type'])
                if key not in pooled:
                    added += 1
                pooled[key] = article
            log.info('OK category=%s entries=%d new=%d', category, len(entries), added)
            time.sleep(REQUEST_PAUSE)
    if successes == 0:
        log.error('All RSS requests failed; retaining previous news.json. Check Google News accessibility and GitHub Action logs.')
        return 1
    articles = sorted(pooled.values(), key=lambda x: x.get('published_at') or '', reverse=True)[:MAX_ARTICLES]
    payload = {
        'updated_at': utcnow().isoformat().replace('+00:00', 'Z'),
        'status': 'ok' if failures == 0 else 'partial',
        'feed_successes': successes, 'feed_failures': failures,
        'article_count': len(articles), 'articles': articles
    }
    temp = OUTPUT.with_suffix('.json.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(OUTPUT)
    log.info('DONE success=%d failed=%d fetched=%d articles=%d file=%s', successes, failures, fetched_count, len(articles), OUTPUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
