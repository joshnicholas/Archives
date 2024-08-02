# %%
import feedparser
import requests
import json 
from bs4 import BeautifulSoup as bs
import dateparser
import time
import pandas as pd 

# %%
import datetime 
import pytz
today = datetime.datetime.now()
scrape_time = today.astimezone(pytz.timezone("Australia/Brisbane"))
format_scrape_time = datetime.datetime.strftime(scrape_time, "%Y_%m_%d_%H")


# %%

### Get micro feeds


def micro_process(urlo, cat):

    r = requests.get(urlo)

    records = []

    jsony = json.loads(r.text)

    for post in jsony['items']:
        try:
            if cat in post['tags']:

                soup = bs(post['content_html'], 'html.parser')
                urlo = post['url']
                stemmo = urlo.split('/')[-1].replace(".html", '')
                par = soup.find('p').text

                datto = dateparser.parse(post['date_published']).strftime("%Y-%m-%d %H:%M")
                
                record = {
                    "Id": stemmo,
                    "Source": "Micro blog",
                    "Headline": par,
                    "Url": urlo,
                    "Date": datto,
                    "Category": cat

                }

                records.append(record)
        except:
            continue
    return pd.DataFrame.from_records(records)

scribbles = micro_process('https://joshnicholas.blog/feed.json', "Scribbles")

reading = micro_process('https://joshnicholas.blog/feed.json', "linklog")


# %%

### Get Guardian stuff

def graun_grabber(urlo):
    
    feedo = feedparser.parse(urlo)

    records = []

    for entry in feedo['entries']:

        # 'title', 'title_detail', 'links', 'link', 'summary', 
        # 'summary_detail', 'published', 'published_parsed', 'id', 
        # 'guidislink', 'media_content', 'media_credit', 'credit', 
        # 'authors', 'author', 'author_detail', 'updated', 'updated_parsed'

        datto = time.strftime("%Y-%m-%d %H:%M", entry['published_parsed'])

        record = {
            "Id": entry['id'],
            "Source": "The Guardian",
            "Headline": entry['title'],
            "Url": entry['link'],
            "Date": datto,
            "Category": "Article"

        }

        records.append(record)

    return pd.DataFrame.from_records(records)

graun = graun_grabber('https://www.theguardian.com/profile/josh-nicholas/rss')


# %%

out_path = 'Archive/feed'

old = pd.read_json(f'{out_path}/latest.json')


tog = pd.concat([graun, scribbles, reading])

with open(f'{out_path}/daily_dumps/{format_scrape_time}.json', 'w') as f:
    tog.to_json(f, orient='records')

tog = pd.concat([tog, old])

tog['Date'] = pd.to_datetime(tog['Date'], format="%Y-%m-%d %H:%M")

tog.drop_duplicates(subset=['Id'], inplace=True, keep='first')

tog.sort_values(by=['Date'], ascending=False, inplace=True)

tog['Date'] = tog['Date'].dt.strftime("%Y-%m-%d %H:%M")

tog = tog[:10]

with open(f'{out_path}/latest.json', 'w') as f:
    tog.to_json(f, orient='records')



# print(tog)
# %%
