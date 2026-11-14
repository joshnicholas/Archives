# %%
"""
Walk every row already in graun_archive.db and fill in whatever's missing
- metadata/text from the Guardian API, a Wayback archive link, or the
full-page screenshots - without touching columns that are already
populated. Safe to re-run; only ever fills gaps.

Typical reasons a row ends up partial: a transient Guardian/Wayback/
Playwright error mid-run, or (before the WebP size cap in
graun_scraper.py) a screenshot taller than WebP's 16383px limit, which
used to crash the whole article before it was ever inserted, or leave
screenshot_webp_path null even though the PNG saved fine.
"""

import datetime
import sqlite3

from playwright.sync_api import sync_playwright

from graun_scraper import (
    DB_PATH, HERE, SCREENSHOT_WEB_DIR,
    init_db, archive_url, archived_at_from_url, screenshot_page, save_webp,
    fetch_single_article, parse_article, rand_delay,
)

REQUIRED_METADATA = ["headline", "text", "word_count", "published_date", "byline", "section"]


def needs_metadata(row):
    return any(row[c] in (None, "") for c in REQUIRED_METADATA)


def needs_archive(row):
    return not row["archive_url"]


def screenshot_present(row):
    return bool(row["screenshot_path"]) and (HERE / row["screenshot_path"]).exists()


def webp_present(row):
    return bool(row["screenshot_webp_path"]) and (HERE / row["screenshot_webp_path"]).exists()


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    rows = conn.execute("SELECT * FROM articles").fetchall()
    print(f"{len(rows)} articles in the database")

    todo = [
        row for row in rows
        if needs_metadata(row) or needs_archive(row)
        or not screenshot_present(row) or not webp_present(row)
    ]
    print(f"{len(todo)} articles have something missing")

    with sync_playwright() as p:
        browser = None

        for row in todo:
            updates = {}
            try:
                if needs_metadata(row):
                    print(f"Fetching metadata: {row['id']}")
                    raw = fetch_single_article(row["id"])
                    parsed = parse_article(raw)
                    for k, v in parsed.items():
                        if k != "id" and not row[k] and v not in (None, ""):
                            updates[k] = v
                    rand_delay(1)

                if needs_archive(row):
                    print(f"Archiving: {row['id']}")
                    archived = archive_url(row["url"])
                    if archived:
                        updates["archive_url"] = archived
                        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        updates["archived_at"] = archived_at_from_url(archived, now)

                if not screenshot_present(row):
                    print(f"Screenshotting: {row['id']}")
                    if browser is None:
                        browser = p.firefox.launch()
                    png_path, webp_path = screenshot_page(row["url"], row["id"], browser)
                    if png_path:
                        updates["screenshot_path"] = png_path
                    if webp_path:
                        updates["screenshot_webp_path"] = webp_path
                    rand_delay(30)
                elif not webp_present(row):
                    # PNG is there but the WebP never got made - e.g. an
                    # oversized full-page shot from before the size cap existed
                    print(f"Repairing WebP: {row['id']}")
                    png_path = HERE / row["screenshot_path"]
                    webp_path = SCREENSHOT_WEB_DIR / f"{png_path.stem}.webp"
                    SCREENSHOT_WEB_DIR.mkdir(parents=True, exist_ok=True)
                    if save_webp(png_path, webp_path):
                        updates["screenshot_webp_path"] = str(webp_path.relative_to(HERE))

                if updates:
                    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
                    updates["id"] = row["id"]
                    conn.execute(f"UPDATE articles SET {set_clause} WHERE id = :id", updates)
                    conn.commit()
                    print(f"  updated: {', '.join(k for k in updates if k != 'id')}")
                else:
                    print(f"  nothing landed for {row['id']}")

            except Exception as e:
                print(f"  failed on {row['id']}: {e}")
                continue

        if browser is not None:
            browser.close()

    conn.close()


if __name__ == "__main__":
    main()
