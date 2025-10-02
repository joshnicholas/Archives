import pandas as pd 

from playwright.sync_api import sync_playwright
# from playwright_stealth import stealth_sync

import datetime 
import pytz
import requests
from pytrends.request import TrendReq
from gnews import GNews
import json 


import os 
import pathlib
pathos = pathlib.Path(__file__).parent.parent
os.chdir(pathos)

print(os.getcwd())

import nltk
nltk.download('wordnet')

today = datetime.datetime.now()
scrape_time = today.astimezone(pytz.timezone("Australia/Brisbane"))
format_scrape_time = datetime.datetime.strftime(scrape_time, "%Y_%m_%d_%H")

pub_scrape_time = datetime.datetime.strftime(scrape_time, "%-I:%M%p %d/%m")


def create_search(what, frame):

    from nltk.stem import WordNetLemmatizer
    import re 

    def do_it(texto):

        wnl = WordNetLemmatizer() 

        senno = ''

        inside_texto = re.sub(r'[^A-Za-z0-9 ]+', '', texto)
        for word in inside_texto.split(" "):
            senno += f"{word.lower()} "

            stemmed = wnl.lemmatize(word)

            if stemmed.lower() not in senno:
                senno += f"{stemmed} "

        return senno

    copier = frame.copy()
    copier.fillna('', inplace=True)
    copier['Search_var'] = copier[what].map(lambda x: do_it(x))
    

    return copier


def get_trending_topics(out_path):

    url = "https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics"

    response = requests.get(url)
    response.raise_for_status()

    data = response.json()

    topics = []
    for topic in data.get('topics', []):
        topics.append({
            'Topic': topic.get('topic', ''),
            'Url': topic.get('link', '')
        })

    df = pd.DataFrame(topics)
    df.insert(0, 'Rank', range(1, len(df) + 1))
    df['publication'] = 'Bsky'
    df['scraped_datetime'] = format_scrape_time 

    df = create_search("Topic", df)

    df = df[['publication', 'scraped_datetime', 'Topic', 'Url', 'Rank', 'Search_var']]

    with open(f'{out_path}/latest.json', 'w') as f:
        df.to_json(f, orient='records')

    with open(f'{out_path}/daily_dumps/{format_scrape_time}.json', 'w') as f:
        df.to_json(f, orient='records')

    # print("Lenno: ", len(df))

    # return df



get_trending_topics('Archive/bsky')
