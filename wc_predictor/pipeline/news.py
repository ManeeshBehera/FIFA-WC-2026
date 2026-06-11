"""News gatherer: football media -> normalized article stream.

Sources (all single-request feeds; no article-page crawling):
  - goal.com Google News sitemap (titles + keywords + timestamps)
  - OneFootball daily news sitemap (English edition)
  - ESPN World Cup news API (JSON, with descriptions)
  - RSS: BBC, Guardian, Sky Sports, talkSPORT, CBS Sports, Marca (EN),
    90min, FourFourTwo, The Sun, Mirror
  - plus any extras in data/news_sources.json: [{"source": .., "url": ..}]

Articles are deduped by normalized title and cached in data/news_articles.json.
A dead source never kills the sweep; it just logs and moves on.
"""

import json
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

from . import DATA_DIR

UA = {"User-Agent": "Mozilla/5.0 (wc-predictor research; contact: local script)"}
CACHE_PATH = DATA_DIR / "news_articles.json"

GOAL_SITEMAP = "https://www.goal.com/en/sitemap/google-news.xml"
ONEFOOTBALL_NEWS = "https://onefootball.com/sitemaps/daily_news/en_1.xml"
ESPN_NEWS = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/news?limit=50"
RSS_FEEDS = [
    ("bbc", "https://feeds.bbci.co.uk/sport/football/rss.xml"),
    ("guardian", "https://www.theguardian.com/football/rss"),
    ("sky sports", "https://www.skysports.com/rss/12040"),
    ("talksport", "https://talksport.com/football/feed/"),
    ("cbs sports", "https://www.cbssports.com/rss/headlines/soccer/"),
    ("marca", "https://e00-marca.uecdn.es/rss/en/football.xml"),
    ("90min", "https://www.90min.com/posts.rss"),
    ("fourfourtwo", "https://www.fourfourtwo.com/feeds.xml"),
    ("the sun", "https://www.thesun.co.uk/sport/football/feed/"),
    ("mirror", "https://www.mirror.co.uk/sport/football/?service=rss"),
]


def _extra_sources():
    """User-extensible feeds: data/news_sources.json."""
    path = DATA_DIR / "news_sources.json"
    if not path.exists():
        return []
    try:
        extras = json.loads(path.read_text())
        return [(e["source"], e["url"]) for e in extras
                if isinstance(e, dict) and e.get("source") and e.get("url")]
    except Exception as e:
        print(f"  [news] ignoring malformed news_sources.json: {e}")
        return []


def _get(url):
    import requests
    return requests.get(url, headers=UA, timeout=30)


def _norm_title(t):
    t = unicodedata.normalize("NFKD", t)
    return re.sub(r"\W+", " ", t).lower().strip()


def _news_sitemap_articles(url, source):
    """Parse a Google-News-style sitemap into articles."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(_get(url).content, "xml")
    out = []
    for u in soup.find_all("url"):
        loc, title = u.find("loc"), u.find("news:title") or u.find("title")
        pub = u.find("news:publication_date") or u.find("lastmod")
        if not (loc and title):
            continue
        kw = u.find("news:keywords")
        out.append({
            "source": source,
            "title": title.get_text(strip=True),
            "url": loc.get_text(strip=True),
            "published": pub.get_text(strip=True) if pub else "",
            "summary": kw.get_text(strip=True) if kw else "",
        })
    return out


def _espn_articles():
    data = _get(ESPN_NEWS).json()
    return [{
        "source": "espn",
        "title": a.get("headline", ""),
        "url": a.get("links", {}).get("web", {}).get("href", ""),
        "published": a.get("published", ""),
        "summary": a.get("description", ""),
    } for a in data.get("articles", [])]


def _rss_articles(source, url):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(_get(url).content, "xml")
    return [{
        "source": source,
        "title": item.title.get_text(strip=True) if item.title else "",
        "url": item.link.get_text(strip=True) if item.link else "",
        "published": item.pubDate.get_text(strip=True) if item.pubDate else "",
        "summary": item.description.get_text(strip=True) if item.description else "",
    } for item in soup.find_all("item")]


def _parse_when(s):
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
                "%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s.replace("Z", "+0000"), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def gather(max_age_hours=96, force=False):
    """Fetch all sources, dedupe, keep recent. Returns list of articles."""
    if CACHE_PATH.exists() and not force and \
            time.time() - CACHE_PATH.stat().st_mtime < 1800:
        return json.loads(CACHE_PATH.read_text())

    fetchers = [
        ("goal.com", lambda: _news_sitemap_articles(GOAL_SITEMAP, "goal.com")),
        ("onefootball", lambda: _news_sitemap_articles(ONEFOOTBALL_NEWS, "onefootball")),
        ("espn", _espn_articles),
    ] + [(src, lambda s=src, u=u: _rss_articles(s, u))
         for src, u in RSS_FEEDS + _extra_sources()]

    articles, seen = [], set()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    for name, fn in fetchers:
        try:
            batch = fn()
        except Exception as e:  # a dead source must not kill the gather
            print(f"  [news] {name} failed: {e}")
            continue
        fresh = 0
        for a in batch:
            key = _norm_title(a["title"])[:80]
            if not key or key in seen:
                continue
            when = _parse_when(a.get("published", ""))
            if when and when < cutoff:
                continue
            seen.add(key)
            articles.append(a)
            fresh += 1
        print(f"  [news] {name}: {fresh} fresh articles")

    CACHE_PATH.write_text(json.dumps(articles, indent=1))
    return articles
