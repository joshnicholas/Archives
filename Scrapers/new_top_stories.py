# %%
import pandas as pd 

from playwright.sync_api import sync_playwright
# from playwright_stealth import stealth_sync
import feedparser
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

