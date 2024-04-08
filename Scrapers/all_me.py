import feedparser
import requests
import json 

# %%

### Get micro feeds


r = requests.get('https://joshnicholas.blog/feed.json')


# %%

jsony = json.loads(r.text)

for post in jsony['items']:
    print(post)
    print(post['tags'])

print(type(jsony['items']))

# print(jsony.keys())


# %%
