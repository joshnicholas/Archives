
# %%

import requests
import os 
import shutil
import pandas as pd 

import pathlib
pathos = pathlib.Path(__file__).parent
os.chdir(pathos)

# %%
init = 'Archive'

paths = ['abc_top','abs','foi', 'cse', 'google', 'graun_top', 'smh_top', 'wiki']

# %%

def create_if_not_there(stemmo):
    fillos = os.listdir(f"{init}")

    if stemmo not in fillos:
        os.mkdir(f"{init}/{stemmo}")
        os.mkdir(f"{init}/{stemmo}/daily_dumps")
    print(fillos)

for thing in paths:
    create_if_not_there(thing)


# %%


# %%


def already_done(path, stemmo):
    pathos = f"{path}/{stemmo}/daily_dumps"
    fillos = os.listdir(pathos)
    fillos = [x.strip() for x in fillos]

    # print(fillos)
    return fillos



for thing in paths:
    print(thing)
    donners = already_done(init, thing)

    # print("already done: ", donners)

    r = requests.get(f'https://thambili.herokuapp.com/check_archives?folder={thing}')
    # r = requests.get(f"http://127.0.0.1:5000/check_archives?folder={thing}")

    appy = r.text.split(",")

    # print("In app: ", appy)

    diff = [x for x in appy if (x.strip() not in donners) & (x != ' ')]
    # diff = ['202305.csv']

    print("Diff: ", diff)

    if len(diff) > 0:
        for fillo in diff:
            print(fillo)
            stemmo = fillo.replace(".csv", '')
            stemmo = stemmo.strip()

            response = requests.get(f"https://thambili.herokuapp.com/get_archives?pathos={thing}&file={stemmo}", stream=True)

            with open(f"{init}/{thing}/daily_dumps/{fillo.strip()}", "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
                file.flush()
        
        response = requests.get(f"https://thambili.herokuapp.com/get_archives?pathos={thing}&file=latest", stream=True)

        with open(f"{init}/{thing}/latest.csv", "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
            file.flush()

# %%
