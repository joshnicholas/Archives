import savepagenow
import pandas as pd 
import random 
import time 

def rand_delay(num):
  
  rando = random.random() * num
  print(rando)
  time.sleep(rando)

# %%


frame = pd.read_csv('https://docs.google.com/spreadsheets/d/e/2PACX-1vTjkG6JLNK0HSEBTwV17gq_Cvf2VNybZNlHHJQtILtNYuQkxKtzwLSvR4mmXlqxJ3XW1QD6DC35ZqM7/pub?gid=0&single=true&output=csv')

links = frame['Links'].unique().tolist()


# %%


for linko in links:
    try:
        archiver = savepagenow.capture(linko)
        print(archiver)

        rand_delay(30)
    except Exception as e:
       print(e)
       continue

    