"""Fetch RSS feeds and write news.json for the Mujaz app.

Runs in GitHub Actions on a schedule. Uses only the Python standard library.
If a feed fails, the previous items for that source are kept.
"""
import json
import re
import html
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "news.json"
MAX_ITEMS = 15

SOURCES = [
    {"id": "ajar", "name": "الجزيرة نت", "lang": "ar",
     "url": "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9"},
    {"id": "bbcar", "name": "بي بي سي عربي", "lang": "ar",
     "url": "https://feeds.bbci.co.uk/arabic/rss.xml"},
    {"id": "sky", "name": "سكاي نيوز عربية", "lang": "ar",
     "url": "https://www.skynewsarabia.com/web/rss"},
    {"id": "f24ar", "name": "فرانس 24", "lang": "ar",
     "url": "https://www.france24.com/ar/rss"},
    {"id": "dwar", "name": "DW عربية", "lang": "ar",
     "url": "https://rss.dw.com/xml/rss-ar-all"},
    {"id": "ajen", "name": "Al Jazeera", "lang": "en",
     "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"id": "bbcen", "name": "BBC News", "lang": "en",
     "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"id": "guardian", "name": "The Guardian", "lang": "en",
     "url": "https://www.theguardian.com/world/rss"},
]

UA = "Mozilla/5.0 (compatible; MujazNewsBot/1.0; personal RSS reader)"
TAG_RE = re.compile(r"<[^>]+>")


def local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def child_text(el, *names):
    for c in el:
        if local(c.tag) in names:
            if local(c.tag) == "link" and c.get("href"):
                return c.get("href")
            if c.text and c.text.strip():
                return c.text.strip()
    return ""


def clean(text, limit=None):
    text = html.unescape(TAG_RE.sub(" ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def parse_date(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(src):
    req = urllib.request.Request(src["url"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = r.read()
    root = ET.fromstring(data)
    entries = [e for e in root.iter() if local(e.tag) in ("item", "entry")]
    items = []
    for e in entries:
        title = clean(child_text(e, "title"))
        link = child_text(e, "link", "guid").strip()
        if not title or not link.startswith("http"):
            continue
        items.append({
            "t": title,
            "u": link.replace("http://", "https://", 1),
            "d": parse_date(child_text(e, "pubdate", "published", "updated", "date")),
            "s": clean(child_text(e, "description", "summary"), 220),
        })
    items.sort(key=lambda i: i["d"] or "", reverse=True)
    return items[:MAX_ITEMS]


def main():
    previous = {}
    if OUT.exists():
        try:
            for f in json.loads(OUT.read_text("utf-8")).get("feeds", []):
                previous[f["id"]] = f
        except (ValueError, KeyError):
            pass

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    feeds = []
    for i, src in enumerate(SOURCES):
        base = {"id": src["id"], "name": src["name"], "lang": src["lang"], "order": i}
        try:
            items = fetch(src)
            if not items:
                raise ValueError("no items")
            feeds.append({**base, "updatedAt": now, "ok": True, "items": items})
            print(f"ok   {src['id']}: {len(items)} items")
        except Exception as exc:  # keep old items when a feed fails
            old = previous.get(src["id"], {})
            feeds.append({**base, "updatedAt": old.get("updatedAt"), "ok": False,
                          "items": old.get("items", [])})
            print(f"FAIL {src['id']}: {exc}")

    OUT.write_text(json.dumps({"generatedAt": now, "feeds": feeds},
                              ensure_ascii=False, separators=(",", ":")), "utf-8")


if __name__ == "__main__":
    main()
