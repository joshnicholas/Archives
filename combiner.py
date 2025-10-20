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

# from dotenv import load_dotenv
# load_dotenv()


import os 
import pathlib
pathos = pathlib.Path(__file__).parent
os.chdir(pathos)


def combiner(stemmo, data_dir,days=7):

    # Convert data_dir to Path object if it's a string
    data_dir = pathlib.Path(data_dir)

    # Calculate the cutoff datetime (x days ago)
    cutoff_datetime = datetime.datetime.now() - datetime.timedelta(days=days)

    # Find all JSON files and filter by date
    all_files = []

    for json_file in data_dir.glob("*.json"):
        # Extract datetime from filename (format: YYYY_MM_DD_HH.json)
        filename = json_file.stem  

        try:
            # Parse the datetime from filename
            file_datetime = datetime.datetime.strptime(filename, "%Y_%m_%d_%H")

            # Check if file is within the date range
            if file_datetime >= cutoff_datetime:
                all_files.append(json_file)

        except ValueError:

            continue

    all_data = []

    for json_file in sorted(all_files):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

                if isinstance(data, list):
                    all_data.extend(data)
                else:
                    all_data.append(data)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not read {json_file}: {e}")
            continue

    df = pd.DataFrame(all_data)
    with open(f"Combined/{stemmo}.json", "w") as f: 
        df.to_json(f)



combiner("graun", 'Archive/graun_top/daily_dumps', days=1)

