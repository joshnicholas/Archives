import subprocess
import ast 
import pandas as pd 

import datetime 
import pytz

today = datetime.datetime.now()
scrape_time = today.astimezone(pytz.timezone("Australia/Brisbane"))
format_scrape_time = datetime.datetime.strftime(scrape_time, "%Y_%m_%d_%H")

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


def shot_grabber(urlo, publication, javascript_code):

    result = subprocess.check_output(['shot-scraper', 'javascript', urlo, javascript_code, "--user-agent", "Firefox"])

    resulto = ast.literal_eval(result.decode("utf-8"))

    frame = pd.DataFrame.from_records(resulto)

    frame['publication'] = publication

    frame = create_search("Headline", frame)

    frame['Rank'] = frame.index + 1

    frame['scraped_datetime']= format_scrape_time 

    frame = frame[['publication', 'scraped_datetime', 'Headline', 'Url', 'Rank', 'Search_var']]
    print(frame)
    print(frame.columns.tolist())
    return frame 


smh = shot_grabber('https://www.smh.com.au/', 'SMH',
    """
    var contexto = document.querySelector('[data-an-name="Most Popular"]')
    Array.from(contexto.querySelectorAll('[data-testid="article-headline"]'), el => {
    let Headline = el.querySelector('a').innerText;
    let Url = el.querySelector('a')['href']
    return {Headline, Url};
    })""")

with open(f'Archive/smh_top/latest_test_two.json', 'w') as f:
    smh.to_json(f, orient='records')


