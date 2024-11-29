# %%
from atproto import Client

import datetime
import pytz
import time 
import pandas as pd 
import requests
today = datetime.datetime.now().astimezone(pytz.timezone("Australia/Brisbane"))

from sudulunu.helpers import dumper

import os 
import pathlib
pathos = pathlib.Path(__file__).parent.parent
os.chdir(pathos)

print(os.getcwd())

# %%

user = os.environ['bskyuser']
passy = os.environ['bskypass']

client = Client()
client.login(user,passy)

outty = 'Archive/bsky/joshnicholas/pics'

# %%

counter = 0
checked = 0
records = []

init = client.get_author_feed(user, limit=100)
curse = init.cursor


# %%

listo = []
deleted = 0

curse = None
for i in range(0,9):
# for i in range(0, 1):
    print("eye: ", i)
    # print("curse: ", curse)
    next = client.get_author_feed(user, cursor=curse, limit=100)
    curse = next.cursor
    feed = next.feed

    for thingo in feed:
        try:
            handle = thingo.post.author.handle
            uri = thingo.post.uri

            old = pd.read_csv(f"{outty}/Pics.csv")
            # old = old.loc[old['Deleted'] == True] 
            already_done = old['Uri'].unique().tolist()

            if uri not in already_done:
                if handle.lower() == user:
                    if hasattr(thingo.post.record, 'embed'):
                    # if thingo.post.record.embed != None:
                        if hasattr(thingo.post.record.embed, 'images'):
                        # if thingo.post.record.embed.images != None:
                            # uri = thingo.post.uri

                            checked += 1
                            if checked % 50 == 0:
                                print(f"Checked: ", checked)
                            time.sleep(1)

                            created = datetime.datetime.fromisoformat(thingo.post.record.created_at)
                            difference = today - created

                            text = thingo.post.record.text
                            # print(thingo.post.record.embed)

                            # print(thingo.post.record)
                            record = {"Handle": handle, "Posted": created.strftime("%Y-%m-%d"), "Text": text,
                                    "Deleted": False, "Uri": uri}
                            
                            imagery = ''
                            for image in thingo.post.record.embed.images:
                                print(image.image)

                                # if hasattr(image.image, 'ref'):
                                #     stemmo = image.image.ref.link
                                # else:
                                stemmo = image.image.cid
                                imagery += f"{stemmo}.jpg"
                                # stemmo = image.image.ref.link
                                # imagery += f"{stemmo}.jpg"

                                picco = f'https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:3kqj3ksyfct7pip5j5dnmjcu/{stemmo}@jpeg'

                                r = requests.get(picco, stream=True)

                                if r.status_code == 200:
                                    with open(f'{outty}/images/{stemmo}.jpg', 'wb') as f:
                                        for chunk in r:
                                            f.write(chunk)
                                
                            record['Images'] = imagery
                            records.append(record)

                            cat = pd.DataFrame.from_records(records)
                            old = pd.read_csv(f"{outty}/Pics.csv")

                            tog = pd.concat([cat, old])
                            tog.drop_duplicates(subset=['Uri'], inplace=True)
                            dumper(outty, 'Pics', tog)

            created = datetime.datetime.fromisoformat(thingo.post.record.created_at)
            difference = today - created

            if handle.lower() == user:
                uri = thingo.post.uri
                if (difference.days > 30):
                    client.delete_post(uri)
                    # record['Deleted'] = True
                    deleted += 1
                    print("Deleted: ", deleted)
            else:
                uri = thingo.post.viewer.repost
                if (difference.days > 30):
                    client.delete_repost(uri)
                    # record['Deleted'] = True
                    deleted += 1
                    print("Deleted: ", deleted)
        except Exception as e:
            print(e)
            print(thingo.post.record.embed.images)
            continue




# https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:3kqj3ksyfct7pip5j5dnmjcu/bafkreihnhin3ktxu7qmy7cskxtoc7te6pkp3v47sybg75kz7ses46anxqm@jpeg