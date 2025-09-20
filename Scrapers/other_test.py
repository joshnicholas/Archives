# %%
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

def rand_delay(num):
  import random 
  import time 
  rando = random.random() * num
#   print(rando)
  time.sleep(rando)


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




today = datetime.datetime.now()
scrape_time = today.astimezone(pytz.timezone("Australia/Brisbane"))
format_scrape_time = datetime.datetime.strftime(scrape_time, "%Y_%m_%d_%H")

pub_scrape_time = datetime.datetime.strftime(scrape_time, "%-I:%M%p %d/%m")

dicto = {"Pushed": pub_scrape_time}

def get_goog_trends(out_path):

    pytrend = TrendReq(hl='en-US', tz=360)

    df = pytrend.trending_searches(pn='australia')
    df.rename(columns={0: "Search"}, inplace=True)

    df['scraped_datetime'] = format_scrape_time

    zdf = df.copy()
    zdf['Rank'] = zdf.index + 1

    zdf = zdf[['Rank', 'Search', 'scraped_datetime']]

    frame = create_search("Search", zdf)

    with open(f'{out_path}/latest.json', 'w') as f:
        frame.to_json(f, orient='records')

    with open(f'{out_path}/daily_dumps/{format_scrape_time}.json', 'w') as f:
        frame.to_json(f, orient='records')
    return frame
# rand_delay(5)

# print("Get Aus google trends")

# try:
#     goog_trendo = get_goog_trends("Archive/google")
#     # listo.append(goog_trendo)
#     dicto['goog_trends'] = goog_trendo.to_dict(orient='records')
# except Exception as e:
#     print(e)


def shot_grabber(urlo, publication, out_path, javascript_code, awaito):
    tries = 0
    with sync_playwright() as p:
        try:

            browser = p.firefox.launch()
            # browser = p.chromium.launch()

            context = browser.new_context()

            page = context.new_page()

            # stealth_sync(page)

            page.goto(urlo)

            # print('Before waiting')
            waiting_around = page.locator(awaito)
            waiting_around.wait_for()
            # print("After waiting")

            resulto = page.evaluate(javascript_code)

            browser.close()

            frame = pd.DataFrame.from_records(resulto)

            frame['publication'] = publication

            frame = create_search("Headline", frame)

            frame['Rank'] = frame.index + 1

            frame['scraped_datetime']= format_scrape_time 

            frame = frame[['publication', 'scraped_datetime', 'Headline', 'Url', 'Rank', 'Search_var']]

            with open(f'{out_path}/latest.json', 'w') as f:
                frame.to_json(f, orient='records')

            with open(f'{out_path}/daily_dumps/{format_scrape_time}.json', 'w') as f:
                frame.to_json(f, orient='records')

            # print("Lenno: ", len(frame))
            return frame 

        except Exception as e:
            tries += 1
            print("Tries: ", tries)
            browser.close()
            print(e)
            rand_delay(5)
            if e == 'Timeout 30000ms exceeded.' and tries <= 3:
                print("Trying again")
                shot_grabber(urlo, publication, out_path, javascript_code, awaito)



try:
    news = shot_grabber('https://www.news.com.au/', 'News', 'Archive/newscom_top',
        """
        var contexto = document.querySelector('.most-popular-content')
        Array.from(contexto.querySelectorAll('a'), el => {
        let Headline = el.innerText;
        let Url = el['href']
        return {Headline, Url};
        })""",
        '.most-popular-content')
    # listo.append(news)\
    dicto['news'] = news.to_dict(orient='records')
except Exception as e:
    print(e)