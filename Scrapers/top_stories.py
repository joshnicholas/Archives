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

today = datetime.datetime.now()
scrape_time = today.astimezone(pytz.timezone("Australia/Brisbane"))
format_scrape_time = datetime.datetime.strftime(scrape_time, "%Y_%m_%d_%H")

# %%

def rand_delay(num):
  import random 
  import time 
  rando = random.random() * num
  print(rando)
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


# def shot_grabber(urlo, publication, out_path, javascript_code):

#     result = subprocess.check_output(['shot-scraper', 'javascript', urlo, javascript_code, "--user-agent", "Firefox", '--bypass-csp'])

#     resulto = ast.literal_eval(result.decode("utf-8"))

#     frame = pd.DataFrame.from_records(resulto)

#     frame['publication'] = publication

#     frame = create_search("Headline", frame)

#     frame['Rank'] = frame.index + 1

#     frame['scraped_datetime']= format_scrape_time 

#     frame = frame[['publication', 'scraped_datetime', 'Headline', 'Url', 'Rank', 'Search_var']]
#     # print(frame)
#     # print(frame.columns.tolist())

#     with open(f'{out_path}/latest.json', 'w') as f:
#         frame.to_json(f, orient='records')

#     with open(f'{out_path}/daily_dumps/{format_scrape_time}.json', 'w') as f:
#         frame.to_json(f, orient='records')

#     return frame 

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

# %%

# listo = []
dicto = {}

print("Scraping the SMH")

try:
    smh = shot_grabber('https://www.smh.com.au/', 'SMH', 'Archive/smh_top',
        """
        var contexto = document.querySelector('[data-an-name="Most Popular"]')
        Array.from(contexto.querySelectorAll('[data-testid="article-headline"]'), el => {
        let Headline = el.querySelector('a').innerText;
        let Url = el.querySelector('a')['href']
        return {Headline, Url};
        })""",
        '[data-an-name="Most Popular"]')
    # listo.append(smh)
    dicto['smh'] = smh.to_dict(orient='records')
except Exception as e:
    print(e)


print("Scraping the ABC")
try:
    abc = shot_grabber('https://www.abc.net.au/news', 'ABC', 'Archive/abc_top',
    """
        var contexto = document.querySelector('[data-uri="recommendation://collection/abc-news-homepage-sidebar"]')
        Array.from(contexto.querySelectorAll('a'), el => {
        let Headline = el.innerText;
        let Url = el['href']
        return {Headline, Url};
        })""",
        '[data-uri="recommendation://collection/abc-news-homepage-sidebar"]')
    # listo.append(abc)
    dicto['abc'] = abc.to_dict(orient='records')
except Exception as e:
    print(e)

print("Scraping News")

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



print("Scraping Graun")
# try:
#     graun = shot_grabber('https://www.theguardian.com/au', 'The Guardian', 'Archive/graun_top',
#         """
#          var contexto = document.querySelector('[data-link-name="Most viewed"]')
#         Array.from(contexto.querySelectorAll('a'), el => {
#         let Headline = el.innerText;
#         let Url = el['href']
#         return {Headline, Url};
#         })""",
#         '[data-link-name="Most viewed"]')
#     listo.append(graun)
# except Exception as e:
#     print(e)

try:
    graun = shot_grabber('https://www.theguardian.com/au', 'The Guardian', 'Archive/graun_top',
        """
         var contexto = document.querySelector('[data-link-name="most-viewed"]')
        Array.from(contexto.querySelectorAll('a'), el => {
        let Headline = el.innerText;
        let Url = el['href']
        return {Headline, Url};
        })""",
        '[data-link-name="most-viewed"]')
    # listo.append(graun)
    dicto['graun'] = graun.to_dict(orient='records')
except Exception as e:
    print(e)


print("Scraping The Age")

try:
    age = shot_grabber('https://www.theage.com.au/', "The Age", 'Archive/age'
                      ,
        """
        var contexto = document.querySelector('[data-an-name="Most Popular"]')
        Array.from(contexto.querySelectorAll('[data-testid="article-headline"]'), el => {
        let Headline = el.querySelector('a').innerText;
        let Url = el.querySelector('a')['href']
        return {Headline, Url};
        })""",
        '[data-an-name="Most Popular"]')
    # listo.append(age)
    dicto['age'] = age.to_dict(orient='records')
except Exception as e:
    print(e)


print("Scraping Brisbane times")

try:
    bris = shot_grabber('https://www.brisbanetimes.com.au/', "Brisbane Times", 'Archive/brisbane_times'
                      ,
        """
        var contexto = document.querySelector('[data-an-name="Most Popular"]')
        Array.from(contexto.querySelectorAll('[data-testid="article-headline"]'), el => {
        let Headline = el.querySelector('a').innerText;
        let Url = el.querySelector('a')['href']
        return {Headline, Url};
        })""",
        '[data-an-name="Most Popular"]')
    # listo.append(bris)
    dicto['bris'] = bris.to_dict(orient='records')
except Exception as e:
    print(e)

# %%

def get_google(out_path):

    google_news = GNews(language='en', country='AU', period='2h')
    aus_news = google_news.get_top_news()

    records = []
    for thingo in aus_news:
        record = {"Headline": thingo['title'], "Url": thingo['url'], 'publication': thingo['publisher']['title'],
                "Publish datetime": thingo['published date']}
        records.append(record)

    frame = pd.DataFrame.from_records(records)
    frame['scraped_datetime'] = format_scrape_time
    frame['Rank'] = frame.index + 1

    frame = create_search("Headline", frame)

    frame = frame[['publication', 'scraped_datetime', 'Headline', 'Url', 'Rank', 'Search_var']]

    with open(f'{out_path}/latest.json', 'w') as f:
        frame.to_json(f, orient='records')

    with open(f'{out_path}/daily_dumps/{format_scrape_time}.json', 'w') as f:
        frame.to_json(f, orient='records')

    return frame

rand_delay(5)

try:
    print("Get Google News")
    goog = get_google('Archive/google_top')
    dicto['goog_news'] = goog.to_dict(orient='records')
    # listo.append(goog)
except Exception as e:
    print(e)

# %%

def get_wiki(urlo, out_path):
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36",
    'Accept-Language': "en-GB,en-US;q=0.9,en;q=0.8",
    "Referer": 'https://www.google.com',
    "DNT":'1'}

    wiki_r = requests.get(urlo, headers=headers)

    if wiki_r.status_code != 404:

        # print(wiki_r.url)

        # print(wiki_r.text)

        wiki_trends = json.loads(wiki_r.text)
        wiki_trends = wiki_trends['items'][0]['articles']
        # wiki_trends = wiki_trends[2:52]

        # wiki_trends = [x['article'] for x in wiki_trends]



        df = pd.DataFrame(wiki_trends)
        df = df.rename(columns={"article": "Page", "views": "Views", 'rank': "Rank"})
        # df['Page'] = df['Page'].str.replace("_", " ")

        zdf = df.copy()
        zdf = zdf[['Rank', 'Page', 'Views']]
        zdf['scraped_datetime'] = format_scrape_time

        frame = create_search("Page", zdf)

        with open(f'{out_path}/latest.json', 'w') as f:
            frame.to_json(f, orient='records')

        with open(f'{out_path}/daily_dumps/{format_scrape_time}.json', 'w') as f:
            frame.to_json(f, orient='records')
        return frame 
    
rand_delay(5)

try:
    print("Getting Wiki")
    # utc_now = datetime.datetime.utcnow()
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    utc_then = utc_now - datetime.timedelta(days=1)

    utc_month = datetime.date.strftime(utc_then, '%m')
    utc_year = datetime.date.strftime(utc_then, '%Y')
    utc_day = datetime.date.strftime(utc_then, '%d')

    utc_reverse_date = utc_then.strftime('%Y-%m-%d')
    utc_hour = utc_then.strftime('%H')

    wiki_linko = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia.org/all-access/{utc_year}/{utc_month}/{utc_day}"
    wiki = get_wiki(wiki_linko, 'Archive/wiki')
    # listo.append(wiki)
    dicto['wiki'] = wiki.to_dict(orient='records')
except Exception as e:

    print(e)

# %%

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
rand_delay(5)

print("Get Aus google trends")

try:
    goog_trendo = get_goog_trends("Archive/google")
    # listo.append(goog_trendo)
    dicto['goog_trends'] = goog_trendo.to_dict(orient='records')
except Exception as e:
    print(e)

# cat = pd.concat(listo)

# with open(f'combined/top_stories.json', 'w') as f:
#     cat.to_json(f, orient='records')



with open("Combined/top_stories.json", "w") as f: 
    json.dump(dicto, f)


# %%

from dotenv import load_dotenv
load_dotenv()
from github import Github, UnknownObjectException

# %%


listo = []

keys = list(dicto.keys())
exclude = ['goog_trends', 'wiki']
keys = [x for x in keys if x not in exclude]

for keyo in keys:
    inter = pd.DataFrame.from_records(dicto[keyo])
    listo.append(inter)

out_data = pd.concat(listo)

# %%

# %%

def send_to_git(stemmo, repo, what, frame):

    tokeny = os.environ['gitty']
    latest = f'static/{what}.csv'

    github = Github(tokeny)

    repository = github.get_user().get_repo(repo)

    jsony = frame.to_dict(orient='records')
    content = json.dumps(jsony)

    def try_file(pathos):
        try:
            repository.get_contents(pathos)
            return True
        except UnknownObjectException as e:
            return False

    latters = repository.get_contents(latest)
    repository.update_file(latest, f"updated_scraped_file_{stemmo}", content, latters.sha)

send_to_git(format_scrape_time, 'sk-blog', 'dash', out_data )
# %%
