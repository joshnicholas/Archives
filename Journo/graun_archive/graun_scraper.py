# %%
"""
Loop through every Guardian article by a given byline, pull the full text
and metadata (tags, section, word count, etc) from the Guardian Content
API, archive each article's URL to the Wayback Machine, and persist
everything to SQLite (source of truth) + CSV (for the Svelte searchable
table).

Requires a Guardian Open Platform API key: https://open-platform.theguardian.com/access/
Set GUARDIAN_API_KEY in a .env file at the repo root (falls back to the
public rate-limited "test" key if unset).
"""

import os
import re
import time
import random
import sqlite3
import pathlib
import datetime

import requests
import pandas as pd
import savepagenow
from savepagenow.exceptions import BlockedByRobots, WaybackRuntimeError
from playwright.sync_api import sync_playwright
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

# %%
### Config

BYLINE = "josh-nicholas"  # matches theguardian.com/profile/josh-nicholas
API_KEY = os.getenv("GUARDIAN_API_KEY", "test")
SEARCH_URL = "https://content.guardianapis.com/search"

# Authenticated Wayback captures are far more reliable than anonymous ones.
# Get a free key pair from https://archive.org/account/s3.php
IA_AUTH = bool(os.getenv("SAVEPAGENOW_ACCESS_KEY") and os.getenv("SAVEPAGENOW_SECRET_KEY"))

# Set SKIP_ARCHIVE=1 to bypass archive.org entirely (e.g. while rate limited)
# - articles are still scraped and saved, just with archive_url left blank.
SKIP_ARCHIVE = os.getenv("SKIP_ARCHIVE", "").strip().lower() in ("1", "true", "yes")

HERE = pathlib.Path(__file__).parent
DB_PATH = HERE / "graun_archive.db"
CSV_PATH = HERE / "graun_articles.csv"
SCREENSHOT_FULL_DIR = HERE / "screenshots" / "full"
SCREENSHOT_WEB_DIR = HERE / "screenshots" / "web"

PAGE_SIZE = 50
SHOW_FIELDS = "headline,trailText,byline,bodyText,wordcount,shortUrl,thumbnail"
SHOW_TAGS = "all"

COLUMNS = [
    "id", "url", "short_url", "headline", "standfirst", "byline",
    "section", "section_id", "pillar", "tags", "word_count",
    "published_date", "text", "thumbnail", "archive_url", "archived_at",
    "screenshot_path", "screenshot_webp_path", "scraped_at",
]


def rand_delay(num):
    rando = random.random() * num
    print(f"  sleeping {rando:.1f}s")
    time.sleep(rando)


# %%
### SQLite setup

def init_db(conn):
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS articles (
            {", ".join(f"{c} TEXT" if c != "word_count" else f"{c} INTEGER" for c in COLUMNS)},
            PRIMARY KEY (id)
        )
    """)
    conn.commit()

    # self-heal: add any columns that were introduced after a db already existed
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
    for c in COLUMNS:
        if c not in existing_cols:
            col_type = "INTEGER" if c == "word_count" else "TEXT"
            conn.execute(f"ALTER TABLE articles ADD COLUMN {c} {col_type}")
    conn.commit()


def existing_ids(conn):
    return {row[0] for row in conn.execute("SELECT id FROM articles")}


# %%
### Guardian Content API

def fetch_guardian_articles(byline):
    """Page through the Content API for every article tagged with this byline."""
    articles = []
    page = 1
    while True:
        params = {
            "tag": f"profile/{byline}",
            "type": "-liveblog",  # exclude live blogs; keeps article/interactive/etc
            "api-key": API_KEY,
            "page-size": PAGE_SIZE,
            "page": page,
            "order-by": "newest",
            "show-fields": SHOW_FIELDS,
            "show-tags": SHOW_TAGS,
        }
        r = requests.get(SEARCH_URL, params=params)
        r.raise_for_status()
        payload = r.json()["response"]

        results = payload.get("results", [])
        articles.extend(results)

        print(f"Fetched page {page}/{payload.get('pages')} ({len(articles)} articles so far)")

        if page >= payload.get("pages", 1):
            break
        page += 1
        rand_delay(1)

    return articles


def fetch_single_article(article_id):
    """Re-fetch one article's fields/tags by its Guardian content id - used
    to backfill a row that's missing metadata/text."""
    r = requests.get(
        f"https://content.guardianapis.com/{article_id}",
        params={"api-key": API_KEY, "show-fields": SHOW_FIELDS, "show-tags": SHOW_TAGS},
    )
    r.raise_for_status()
    return r.json()["response"]["content"]


def parse_article(raw):
    fields = raw.get("fields", {}) or {}
    tags = raw.get("tags", []) or []

    # drop the contributor tag - it's just the byline again
    tag_titles = "; ".join(
        t.get("webTitle", "") for t in tags
        if t.get("webTitle") and t.get("type") != "contributor"
    )

    return {
        "id": raw.get("id"),
        "url": raw.get("webUrl"),
        "short_url": fields.get("shortUrl"),
        "headline": fields.get("headline") or raw.get("webTitle"),
        "standfirst": fields.get("trailText"),
        "byline": fields.get("byline"),
        "section": raw.get("sectionName"),
        "section_id": raw.get("sectionId"),
        "pillar": raw.get("pillarName"),
        "tags": tag_titles,
        "word_count": int(fields["wordcount"]) if fields.get("wordcount") else None,
        "published_date": raw.get("webPublicationDate"),
        "text": fields.get("bodyText"),
        "thumbnail": fields.get("thumbnail"),
    }


# %%
### Internet Archive

# a real snapshot url looks like .../web/20260717120411/https://...  -
# the 14-digit timestamp is what's missing from a bare timegate url
MEMENTO_RE = re.compile(r"/web/(\d{14})/")

AVAILABILITY_URL = "https://archive.org/wayback/available"


def find_existing_snapshot(url, retries=3):
    """
    Ask the Wayback Availability API whether archive.org already has any
    capture of this URL, without asking it to make a new one. Checked
    before attempting a fresh capture - archive.org's legacy save endpoint
    500s fairly often (independent of auth or which url), so there's no
    point hammering it for articles that are already archived.

    The availability API also rate-limits (429) if it's hit too fast, so a
    429 is retried with backoff rather than treated as "no snapshot".
    """
    for attempt in range(1, retries + 2):
        try:
            r = requests.get(AVAILABILITY_URL, params={"url": url}, timeout=30)
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After", 0)) or (1 * attempt)
                print(f"  snapshot lookup rate-limited (attempt {attempt}), waiting {wait:.0f}s")
                if attempt <= retries:
                    time.sleep(wait)
                    continue
                return None
            r.raise_for_status()
            snapshot = r.json().get("archived_snapshots", {}).get("closest")
            if snapshot and snapshot.get("available"):
                return snapshot["url"]
            return None
        except Exception as e:
            print(f"  snapshot lookup failed ({type(e).__name__}: {e}) for {url}")
            return None
    return None


def archived_at_from_url(archived_url, fallback):
    """Pull the real capture timestamp out of a memento url (rather than
    stamping archived_at with scrape time, which is wrong for a snapshot
    that already existed from a previous capture)."""
    match = MEMENTO_RE.search(archived_url or "")
    if not match:
        return fallback
    try:
        dt = datetime.datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
        return dt.replace(tzinfo=datetime.timezone.utc).isoformat()
    except ValueError:
        return fallback


def archive_url(url, retries=2):
    """
    Return an archive.org URL for this article - an existing capture if one
    is already on file, otherwise a freshly made one.

    We check for an existing snapshot first rather than always capturing
    fresh: archive.org's legacy save endpoint 500s fairly often (independent
    of auth or which url is being saved), so there's no point spending
    retries/backoff hammering it for an article that's already archived.

    savepagenow raises WaybackRuntimeError when archive.org's response is
    missing the headers it needs to build an archive URL - in that case the
    exception's payload is the *entire raw HTML/response body*, so it must
    never be printed directly (it'll flood the console). We log a short
    summary instead and retry, since these are usually transient.

    It can also return a *timegate* url (no timestamp, e.g. heavy JS pages
    like ng-interactive that archive.org's crawler fails to render/save in
    time) which savepagenow treats as success even though no snapshot was
    actually created - visiting it later shows "cannot be displayed due to
    an internal error". We check for the timestamp and treat a timegate-only
    result as a failure worth retrying.
    """
    if SKIP_ARCHIVE:
        return None

    existing = find_existing_snapshot(url)
    if existing:
        print(f"  already archived: {existing}")
        return existing

    for attempt in range(1, retries + 2):
        try:
            archived, was_new = savepagenow.capture_or_cache(url, authenticate=IA_AUTH)
            if not MEMENTO_RE.search(archived):
                print(f"  archive attempt {attempt} produced no real snapshot (timegate only) for {url}")
            else:
                print(f"  {'archived' if was_new else 'already archived recently'}: {archived}")
                return archived
        except BlockedByRobots:
            print(f"  archive skipped, blocked by robots.txt: {url}")
            return None
        except WaybackRuntimeError as e:
            detail = e.args[0] if e.args else e
            if isinstance(detail, dict):
                detail = f"status={detail.get('status_code')}"
            print(f"  archive attempt {attempt} failed ({detail}) for {url}")
        except Exception as e:
            print(f"  archive attempt {attempt} failed ({type(e).__name__}: {e}) for {url}")

        if attempt <= retries:
            rand_delay(20)

    return None


# %%
### Full-page screenshot

def _scroll_through_page(page, step=900, pause_ms=250):
    """
    Most news sites lazy-load images/graphics via an IntersectionObserver -
    they never fire unless the element actually scrolls into view. A
    full_page screenshot does NOT scroll through the page itself, so
    anything below the fold is captured blank unless we do this first.
    """
    page.evaluate(
        """({step, pause}) => new Promise((resolve) => {
            let total = 0;
            const timer = setInterval(() => {
                const height = document.body.scrollHeight;
                window.scrollBy(0, step);
                total += step;
                if (total >= height) {
                    clearInterval(timer);
                    window.scrollTo(0, 0);
                    resolve();
                }
            }, pause);
        })""",
        {"step": step, "pause": pause_ms},
    )


# libwebp hard-fails past this many pixels on either side. Guardian
# long-reads/interactives can produce full-page screenshots taller than
# this, so we downscale rather than let the whole article fail to save.
MAX_WEBP_DIM = 16383


def save_webp(png_path, webp_path, quality=80, max_dim=MAX_WEBP_DIM):
    """
    Convert a PNG screenshot to WebP for the web. Returns True on success,
    False if the PNG couldn't be converted (caller decides what to do -
    the PNG archival copy is untouched either way).
    """
    try:
        with Image.open(png_path) as im:
            im = im.convert("RGB")
            if im.width > max_dim or im.height > max_dim:
                scale = max_dim / max(im.width, im.height)
                new_size = (max(1, round(im.width * scale)), max(1, round(im.height * scale)))
                print(f"  downscaling {im.width}x{im.height} -> {new_size[0]}x{new_size[1]} to fit WebP's size limit")
                im = im.resize(new_size, Image.LANCZOS)
            im.save(webp_path, "WEBP", quality=quality, method=6)
        return True
    except Exception as e:
        print(f"  webp conversion failed for {png_path.name}: {type(e).__name__}: {e}")
        return False


def screenshot_page(url, article_id, browser):
    """
    Render the article with JS enabled and save a full-page screenshot:
    a full-resolution PNG (for archival) and a compressed WebP (for the web).
    Returns (png_path, webp_path) relative to this script's folder, or
    (None, None) on failure.
    """
    SCREENSHOT_FULL_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_WEB_DIR.mkdir(parents=True, exist_ok=True)

    stem = article_id.replace("/", "_")
    png_path = SCREENSHOT_FULL_DIR / f"{stem}.png"
    webp_path = SCREENSHOT_WEB_DIR / f"{stem}.webp"

    page = browser.new_page(viewport={"width": 1280, "height": 1024})
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            # Hide, rather than click through, everything that isn't the article:
            #  - #slot-body-end: the Guardian's end-of-article "Epic" reader-revenue
            #    ask (their support/contribution banner)
            #  - .ad-slot-container: every paid ad placement (top banner, inline,
            #    right-column, etc) - a stable, non-hashed class regardless of
            #    which creative is rotating through it
            #  - [id^="sp_message_container_"]: the Sourcepoint consent-management
            #    overlay ("It's your choice" - a real privacy banner, not an ad).
            #    It renders as a fixed-position iframe, so it was covering real
            #    article text in screenshots rather than just sitting at the top.
            #    sp_message_container_ is Sourcepoint's own hardcoded id prefix,
            #    the numeric suffix is a per-campaign message id.
            page.add_style_tag(content="""
                #slot-body-end,
                .ad-slot-container,
                [id^="sp_message_container_"] { display: none !important; }
            """)
        except Exception:
            pass
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        # scroll through the whole page to trigger lazy-loaded images/graphics,
        # then give them time to actually finish downloading and rendering
        _scroll_through_page(page)
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            # ng-interactive/data pages poll continuously and never go fully
            # idle - give it a fixed settle window and screenshot regardless
            page.wait_for_timeout(3000)
        page.wait_for_timeout(1000)

        page.screenshot(path=str(png_path), full_page=True)
    except Exception as e:
        print(f"  screenshot failed for {url}: {type(e).__name__}: {e}")
        return None, None
    finally:
        page.close()

    webp_ok = save_webp(png_path, webp_path)

    return str(png_path.relative_to(HERE)), (str(webp_path.relative_to(HERE)) if webp_ok else None)


# %%
### Main

def main():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    already = existing_ids(conn)
    print(f"{len(already)} articles already in the database")
    if SKIP_ARCHIVE:
        print("SKIP_ARCHIVE is set - archive.org captures will be skipped for this run")

    raw_articles = fetch_guardian_articles(BYLINE)
    new_raw = [a for a in raw_articles if a.get("id") not in already]
    print(f"{len(new_raw)} new articles to process")

    with sync_playwright() as p:
        browser = p.firefox.launch()

        for raw in new_raw:
            try:
                record = parse_article(raw)
                print(f"Processing: {record['headline']}")

                archived = archive_url(record["url"])
                png_path, webp_path = screenshot_page(record["url"], record["id"], browser)
                now = datetime.datetime.now(datetime.timezone.utc).isoformat()

                record["archive_url"] = archived
                record["archived_at"] = archived_at_from_url(archived, now) if archived else None
                record["screenshot_path"] = png_path
                record["screenshot_webp_path"] = webp_path
                record["scraped_at"] = now

                placeholders = ", ".join(f":{c}" for c in COLUMNS)
                conn.execute(
                    f"INSERT OR REPLACE INTO articles ({', '.join(COLUMNS)}) VALUES ({placeholders})",
                    record,
                )
                conn.commit()

                rand_delay(10)
            except Exception as e:
                print(f"  failed on {raw.get('webUrl')}: {e}")
                continue

        browser.close()

    # %%
    ### Export CSV for the Svelte table, always regenerated from SQLite

    df = pd.read_sql("SELECT * FROM articles ORDER BY published_date DESC", conn)
    df.to_csv(CSV_PATH, index=False)
    print(f"Wrote {len(df)} rows to {CSV_PATH}")

    conn.close()


if __name__ == "__main__":
    main()
