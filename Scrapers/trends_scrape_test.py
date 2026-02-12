# %%
import feedparser
import requests
import json 
from bs4 import BeautifulSoup as bs
import dateparser
import time
import pandas as pd 

import pytz
import datetime 

import os 
import pathlib
pathos = pathlib.Path(__file__).parent.parent
os.chdir(pathos)


# %%

today = datetime.datetime.now()
scrape_time = today.astimezone(pytz.timezone("Australia/Brisbane"))
format_scrape_time = datetime.datetime.strftime(scrape_time, "%Y_%m_%d_%H")

pub_scrape_time = datetime.datetime.strftime(scrape_time, "%-I:%M%p %d/%m")


# %%


def get_google_trends_rss(urlo, out_path):

    feedo = feedparser.parse(urlo)

    records = []

    for entry in feedo['entries']:
        record = {"Headline": entry['title'], 
        'publication': "Google trends",
        'published': entry['published'],

        'scraped_datetime':format_scrape_time,
        "Traffic":entry['ht_approx_traffic'], 
        'Entry': entry['ht_news_item_title'], 
        "Url": entry['ht_news_item_url']}

        records.append(record)

    frame = pd.DataFrame.from_records(records)

    with open(f'{out_path}/latest.json', 'w') as f:
        frame.to_json(f, orient='records')

    with open(f'{out_path}/daily_dumps/{format_scrape_time}.json', 'w') as f:
        frame.to_json(f, orient='records')

    return frame 

trendos = get_google_trends_rss('https://trends.google.com/trending/rss?geo=AU', 'Archive/google_trends_rss')


# %%

# %%

# %%