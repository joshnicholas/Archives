import pandas as pd
import datetime
import pytz
import requests
import os
import pathlib

pathos = pathlib.Path(__file__).parent.parent
os.chdir(pathos)

today = datetime.datetime.now()
scrape_time = today.astimezone(pytz.timezone("Australia/Brisbane"))
format_scrape_time = datetime.datetime.strftime(scrape_time, "%Y_%m_%d_%H")

def get_wiki_edits(out_path):
    url = "https://weeklypedia.toolforge.org/fetch/en"
    response = requests.get(url)
    response.raise_for_status()

    data = response.json()
    articles = data.get("mainspace", [])

    records = []
    for i, article in enumerate(articles, start=1):
        records.append({
            "Rank": i,
            "Page": article.get("title_s", article.get("title", "")),
            "Edits": article.get("edits", 0),
            "Users": article.get("users", 0),
            "scraped_datetime": format_scrape_time,
        })

    df = pd.DataFrame(records)

    with open(f"{out_path}/latest.json", "w") as f:
        df.to_json(f, orient="records")

    with open(f"{out_path}/daily_dumps/{format_scrape_time}.json", "w") as f:
        df.to_json(f, orient="records")

    return df

print("Scraping Wikipedia most-edited articles")
try:
    wiki_edits = get_wiki_edits("Archive/wiki_edits")
    print(f"Got {len(wiki_edits)} articles")
except Exception as e:
    print(e)
