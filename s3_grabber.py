
# %%

import requests
import os 
import shutil
import pandas as pd 
import boto3
import dateparser 

import pathlib
pathos = pathlib.Path(__file__).parent
os.chdir(pathos)

print()

from dotenv import load_dotenv
load_dotenv()

AWS_KEY = os.environ['awsykey']
AWS_SECRET = os.environ['awsysec']

# %%

session = boto3.Session(
        aws_access_key_id=AWS_KEY,
        aws_secret_access_key=AWS_SECRET,
        )

s3 = session.resource('s3')

s3_client = session.client('s3')

# %%

# for bucket in s3.buckets.all():
#     print(bucket.name)

# my_bucket = s3.Bucket('chaluchasu')

# for my_bucket_object in my_bucket.objects.all():
#     print(my_bucket_object.key)

response = s3_client.list_objects_v2(Bucket='chaluchasu', Prefix='wiki/dumps/2019-11')

for obj in response['Contents']:
    print(obj['Key'])

    stemmo = obj['Key'].split(".json")[0] + ".json"
    stemmo = stemmo.split("/")[-1]
    print(stemmo)

    s3_client.download_file('chaluchasu', obj['Key'], f"/Users/josh/Github/Archives/Test/{stemmo}")
# %%
