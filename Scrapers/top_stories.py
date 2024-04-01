import pandas as pd 

from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

import datetime 
import pytz

import nltk
nltk.download('wordnet')

today = datetime.datetime.now()
scrape_time = today.astimezone(pytz.timezone("Australia/Brisbane"))
format_scrape_time = datetime.datetime.strftime(scrape_time, "%Y_%m_%d_%H")

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

            stealth_sync(page)

            page.goto(urlo)

            print('Before waiting')
            waiting_around = page.locator(awaito)
            waiting_around.wait_for()
            print("After waiting")

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


# print("Scraping the SMH")

# try:
#     smh = shot_grabber('https://www.smh.com.au/', 'SMH', 'Archive/smh_top',
#         """
#         var contexto = document.querySelector('[data-an-name="Most Popular"]')
#         Array.from(contexto.querySelectorAll('[data-testid="article-headline"]'), el => {
#         let Headline = el.querySelector('a').innerText;
#         let Url = el.querySelector('a')['href']
#         return {Headline, Url};
#         })""",
#         '[data-an-name="Most Popular"]')
# except Exception as e:
#     print(e)


# print("Scraping the ABC")
# try:
#     abc = shot_grabber('https://www.abc.net.au/news', 'ABC', 'Archive/abc_top',
#     """
#         var contexto = document.querySelector('[data-uri="recommendation://collection/abc-news-homepage-sidebar"]')
#         Array.from(contexto.querySelectorAll('a'), el => {
#         let Headline = el.innerText;
#         let Url = el['href']
#         return {Headline, Url};
#         })""",
#         '[data-uri="recommendation://collection/abc-news-homepage-sidebar"]')
# except Exception as e:
#     print(e)

# print("Scraping News")

# try:
#     news = shot_grabber('https://www.news.com.au/', 'News', 'Archive/newscom_top',
#         """
#         var contexto = document.querySelector('.most-popular-content')
#         Array.from(contexto.querySelectorAll('a'), el => {
#         let Headline = el.innerText;
#         let Url = el['href']
#         return {Headline, Url};
#         })""",
#         '.most-popular-content')
    
# except Exception as e:
#     print(e)

# print("Scraping Graun")
# try:
#     graun = shot_grabber('https://www.theguardian.com/au', 'The Guardian', 'Archive/graun_top',
#         """
#         var contexto = document.querySelector('[data-link-name="most-viewed"]')
#         Array.from(contexto.querySelectorAll('a'), el => {
#         let Headline = el.innerText;
#         let Url = el['href']
#         return {Headline, Url};
#         })""",
#         '[data-link-name="most-viewed"]')
# except Exception as e:
#     print(e)


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
except Exception as e:
    print(e)