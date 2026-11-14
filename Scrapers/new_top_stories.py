import asyncio
import datetime
import json
import os
import pathlib
import random
import time

import feedparser
import nltk
import pandas as pd
import pytz
import requests
import spacy
from gnews import GNews
from playwright.async_api import async_playwright
from pytrends.request import TrendReq

from extract_entities import extract_entities, records_from_dicto
from wiki_edits import get_wiki_edits

pathos = pathlib.Path(__file__).parent.parent
os.chdir(pathos)

try:
    nltk.data.find("corpora/wordnet")
except LookupError:
    nltk.download("wordnet")

today = datetime.datetime.now()
scrape_time = today.astimezone(pytz.timezone("Australia/Brisbane"))
format_scrape_time = datetime.datetime.strftime(scrape_time, "%Y_%m_%d_%H")
pub_scrape_time = datetime.datetime.strftime(scrape_time, "%-I:%M%p %d/%m")


def rand_delay(num):
    # a deliberate anti-bot throttle at a couple of call sites below, not a bug — don't
    # optimise this away, it's doing its job
    time.sleep(random.random() * num)


def create_search(what, frame):
    from nltk.stem import WordNetLemmatizer
    import re

    def do_it(texto):
        wnl = WordNetLemmatizer()
        senno = ""
        inside_texto = re.sub(r"[^A-Za-z0-9 ]+", "", texto)
        for word in inside_texto.split(" "):
            senno += f"{word.lower()} "
            stemmed = wnl.lemmatize(word)
            if stemmed.lower() not in senno:
                senno += f"{stemmed} "
        return senno

    copier = frame.copy()
    copier.fillna("", inplace=True)
    copier["Search_var"] = copier[what].map(lambda x: do_it(x))
    return copier


# --- the 7 Playwright sites, as data instead of 7 separate sequential function calls ---
# key: used for both dicto[...] and extract_entities' entity_sources list — keep the existing
# short keys ("news", "bris", ...) since downstream code (records_from_dicto's entity_sources)
# already expects them.
SITES = [
    {"key": "smh", "publication": "SMH", "out_path": "Archive/smh_top",
     "url": "https://www.smh.com.au/", "awaito": '[data-an-name="Most Popular"]',
     "javascript_code": """
        var contexto = document.querySelector('[data-an-name="Most Popular"]')
        Array.from(contexto.querySelectorAll('[data-testid="article-headline"]'), el => {
        let Headline = el.querySelector('a').innerText;
        let Url = el.querySelector('a')['href']
        return {Headline, Url};
        })"""},
    {"key": "abc", "publication": "ABC", "out_path": "Archive/abc_top",
     "url": "https://www.abc.net.au/news/justin",
     "awaito": '[data-uri="coremedia://collection/10719986"]',
     "javascript_code": """
        var contexto = document.querySelectorAll('[data-component="LinkList"]')[1]
        Array.from(contexto.querySelectorAll('a'), el => {
        let Headline = el.innerText;
        let Url = el['href']
        return {Headline, Url};
        })"""},
    {"key": "news", "publication": "News", "out_path": "Archive/newscom_top",
     "url": "https://www.news.com.au/", "awaito": ".most-popular-content",
     "javascript_code": """
        var contexto = document.querySelector('.most-popular-content')
        Array.from(contexto.querySelectorAll('a'), el => {
        let Headline = el.innerText;
        let Url = el['href']
        return {Headline, Url};
        })"""},
    {"key": "graun", "publication": "The Guardian", "out_path": "Archive/graun_top",
     "url": "https://www.theguardian.com/au", "awaito": '[data-link-name="most-viewed"]',
     "javascript_code": """
         var contexto = document.querySelector('[data-link-name="most-viewed"]')
        Array.from(contexto.querySelectorAll('a'), el => {
        let Headline = el.innerText;
        let Url = el['href']
        return {Headline, Url};
        })"""},
    {"key": "age", "publication": "The Age", "out_path": "Archive/age",
     "url": "https://www.theage.com.au/", "awaito": '[data-an-name="Most Popular"]',
     "javascript_code": """
        var contexto = document.querySelector('[data-an-name="Most Popular"]')
        Array.from(contexto.querySelectorAll('[data-testid="article-headline"]'), el => {
        let Headline = el.querySelector('a').innerText;
        let Url = el.querySelector('a')['href']
        return {Headline, Url};
        })"""},
    {"key": "bris", "publication": "Brisbane Times", "out_path": "Archive/brisbane_times",
     "url": "https://www.brisbanetimes.com.au/", "awaito": '[data-an-name="Most Popular"]',
     "javascript_code": """
        var contexto = document.querySelector('[data-an-name="Most Popular"]')
        Array.from(contexto.querySelectorAll('[data-testid="article-headline"]'), el => {
        let Headline = el.querySelector('a').innerText;
        let Url = el.querySelector('a')['href']
        return {Headline, Url};
        })"""},
    {"key": "bbc", "publication": "bbc", "out_path": "Archive/bbc_top",
     "url": "https://www.bbc.com/news", "awaito": '[data-testid="illinois-grid-10"]',
     "javascript_code": """
        var contexto = document.querySelector('[data-testid="illinois-grid-10"]');
        Array.from(
          contexto.querySelectorAll('[data-testid="cambridge-card"] a'),
          el => {
            let Headline = el.querySelector('[data-testid="card-headline"]')?.innerText.trim();
            let Url = el.getAttribute('href');
            return { Headline, Url };
          }
        );""",
     # bbc's own markup only ever has the path, every other site's JS already returns a full URL
     "url_prefix": "https://www.bbc.com"},
]


async def scrape_one(browser, site, max_tries=3):
    # tries counts THIS site's own retry attempts only — a timeout on one slow site never eats
    # into another site's own retry budget the way a shared/global counter would
    for attempt in range(1, max_tries + 1):
        context = await browser.new_context()
        try:
            page = await context.new_page()
            await page.goto(site["url"], wait_until="domcontentloaded", timeout=60_000)
            await page.locator(site["awaito"]).wait_for()
            resulto = await page.evaluate(site["javascript_code"])
            return site["key"], resulto
        except Exception as error:
            print(f"{site['key']} attempt {attempt} failed: {error}")
            if attempt == max_tries:
                return site["key"], None  # every attempt failed — skip this one site
            await asyncio.sleep(random.random() * 5)  # same budget as rand_delay(5)
        finally:
            await context.close()  # always closed, success or failure


async def scrape_all_sites(browser, sites):
    results = await asyncio.gather(*(scrape_one(browser, site) for site in sites))
    return dict(results)


def build_frame(site, resulto):
    frame = pd.DataFrame.from_records(resulto)
    frame["publication"] = site["publication"]
    frame = create_search("Headline", frame)
    frame["Rank"] = frame.index + 1
    frame["scraped_datetime"] = format_scrape_time
    frame = frame[["publication", "scraped_datetime", "Headline", "Url", "Rank", "Search_var"]]
    if site.get("url_prefix"):
        frame["Url"] = site["url_prefix"] + frame["Url"]
    return frame


def write_outputs(out_path, frame):
    with open(f"{out_path}/latest.json", "w") as f:
        frame.to_json(f, orient="records")
    with open(f"{out_path}/daily_dumps/{format_scrape_time}.json", "w") as f:
        frame.to_json(f, orient="records")


# --- non-Playwright sources: unchanged logic, just no longer run strictly after the
# Playwright block finishes — each gets wrapped in asyncio.to_thread and gathered alongside it ---

def get_google(out_path):
    rand_delay(5)
    google_news = GNews(language="en", country="AU", period="2h")
    aus_news = google_news.get_top_news()

    records = []
    for thingo in aus_news:
        records.append({
            "Headline": thingo["title"], "Url": thingo["url"],
            "publication": thingo["publisher"]["title"],
            "Publish datetime": thingo["published date"],
        })

    frame = pd.DataFrame.from_records(records)
    frame["scraped_datetime"] = format_scrape_time
    frame["Rank"] = frame.index + 1
    frame = create_search("Headline", frame)
    frame = frame[["publication", "scraped_datetime", "Headline", "Url", "Rank", "Search_var"]]
    write_outputs(out_path, frame)
    return frame


def get_wiki(out_path):
    rand_delay(5)
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    utc_then = utc_now - datetime.timedelta(days=1)
    utc_year = utc_then.strftime("%Y")
    utc_month = utc_then.strftime("%m")
    utc_day = utc_then.strftime("%d")
    urlo = (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia.org/"
        f"all-access/{utc_year}/{utc_month}/{utc_day}"
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com",
        "DNT": "1",
    }
    wiki_r = requests.get(urlo, headers=headers)
    if wiki_r.status_code == 404:
        return None

    wiki_trends = json.loads(wiki_r.text)["items"][0]["articles"]
    df = pd.DataFrame(wiki_trends)
    df = df.rename(columns={"article": "Page", "views": "Views", "rank": "Rank"})
    zdf = df[["Rank", "Page", "Views"]].copy()
    zdf["scraped_datetime"] = format_scrape_time
    frame = create_search("Page", zdf)
    write_outputs(out_path, frame)
    return frame


def get_trending_topics(out_path):
    url = "https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    topics = [
        {"Topic": topic.get("topic", ""), "Url": topic.get("link", "")}
        for topic in data.get("topics", [])
    ]
    df = pd.DataFrame(topics)
    df.insert(0, "Rank", range(1, len(df) + 1))
    df["publication"] = "Bsky"
    df["scraped_datetime"] = format_scrape_time
    df = create_search("Topic", df)
    df = df[["publication", "scraped_datetime", "Topic", "Url", "Rank", "Search_var"]]
    write_outputs(out_path, df)
    return df


def get_google_trends_rss(urlo, out_path):
    feedo = feedparser.parse(urlo)
    records = [
        {
            "Headline": entry["title"],
            "publication": "Google trends",
            "published": entry["published"],
            "scraped_datetime": format_scrape_time,
            "Traffic": entry["ht_approx_traffic"],
            "Entry": entry["ht_news_item_title"],
            "Url": entry["ht_news_item_url"],
        }
        for entry in feedo["entries"]
    ]
    frame = pd.DataFrame.from_records(records)
    write_outputs(out_path, frame)
    return frame


# --- orchestration: every non-Playwright call wrapped so it can sit in the same gather as
# the Playwright scrapes, each catching its own failure the same way the original script's
# per-site try/except did ---

async def run_sync(key, func, *args):
    try:
        resulto = await asyncio.to_thread(func, *args)
        return key, resulto
    except Exception as error:
        print(f"{key} failed: {error}")
        return key, None


NON_PLAYWRIGHT_SOURCES = [
    ("goog_news", get_google, ("Archive/google_top",)),
    ("wiki", get_wiki, ("Archive/wiki",)),
    ("bsky", get_trending_topics, ("Archive/bsky",)),
    ("google_trends", get_google_trends_rss,
     ("https://trends.google.com/trending/rss?geo=AU", "Archive/google_trends_rss")),
    ("wiki_edits", get_wiki_edits, ("Archive/wiki_edits",)),
]


async def scrape_everything():
    async with async_playwright() as p:
        browser = await p.firefox.launch()  # launched ONCE for all 7 sites
        playwright_results, *non_playwright_results = await asyncio.gather(
            scrape_all_sites(browser, SITES),
            *(run_sync(key, func, *args) for key, func, args in NON_PLAYWRIGHT_SOURCES),
        )
        await browser.close()
    return playwright_results, dict(non_playwright_results)


def combiner(stemmo, data_dir, days=7):
    data_dir = pathlib.Path(data_dir)
    cutoff_datetime = datetime.datetime.now() - datetime.timedelta(days=days)

    all_files = []
    for json_file in data_dir.glob("*.json"):
        try:
            file_datetime = datetime.datetime.strptime(json_file.stem, "%Y_%m_%d_%H")
            if file_datetime >= cutoff_datetime:
                all_files.append(json_file)
        except ValueError:
            continue

    all_data = []
    for json_file in sorted(all_files):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    all_data.extend(data)
                else:
                    all_data.append(data)
        except (json.JSONDecodeError, IOError) as error:
            print(f"Warning: Could not read {json_file}: {error}")
            continue

    df = pd.DataFrame(all_data)
    with open(f"Combined/{stemmo}.json", "w") as f:
        df.to_json(f)


def main():
    print("Scraping all sources concurrently")
    playwright_results, non_playwright_results = asyncio.run(scrape_everything())

    dicto = {"Pushed": pub_scrape_time}

    for site in SITES:
        resulto = playwright_results.get(site["key"])
        if resulto is None:
            continue
        frame = build_frame(site, resulto)
        write_outputs(site["out_path"], frame)
        dicto[site["key"]] = frame.to_dict(orient="records")

    for key, _func, _args in NON_PLAYWRIGHT_SOURCES:
        frame = non_playwright_results.get(key)
        if frame is None:
            continue
        dicto[key] = frame.to_dict(orient="records")

    with open("Combined/top_stories.json", "w") as f:
        json.dump(dicto, f)

    combiner("graun", "Archive/graun_top/daily_dumps", days=1)

    try:
        print("Extracting named entities")
        entity_sources = ["smh", "abc", "news", "graun", "age", "bris", "bbc", "goog_news"]
        nlp = spacy.load("en_core_web_sm")
        records = records_from_dicto(dicto, entity_sources)
        entities = extract_entities(records, nlp)
        entity_output = {
            "scraped_datetime": format_scrape_time,
            "sources": entity_sources,
            "headline_count": len(records),
            "entities": [
                {"name": name, "type": info["type"], "count": info["count"],
                 "mentions": info["mentions"]}
                for name, info in entities.items()
            ],
        }
        with open("Archive/entities/latest.json", "w") as f:
            json.dump(entity_output, f)
        with open(f"Archive/entities/dumps/{format_scrape_time}.json", "w") as f:
            json.dump(entity_output, f)
        with open("Combined/entities.json", "w") as f:
            json.dump(entity_output, f)
    except Exception as error:
        print(error)


if __name__ == "__main__":
    main()
