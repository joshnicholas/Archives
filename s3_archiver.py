
# %%

import requests
import os 
import shutil
import pandas as pd 
import boto3
import dateparser 
import re

import pathlib
pathos = pathlib.Path(__file__).parent
os.chdir(pathos)

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

# response = s3_client.list_objects_v2(Bucket='chaluchasu', Prefix='wiki/dumps/2019-11')

# for obj in response['Contents']:
#     print(obj['Key'])

# %%

pathos = '/Users/josh/Downloads/Archives-main/Archive/'

dirt = os.listdir(pathos)
# dirt = [pathos + x for x in dirt if os.path.isdir(f"{pathos}{x}")]
# dirt = [x for x in dirt if x == 'wiki']

# counter = 0

already_done = ['cse', 'abs', 'graun_top', 'wiki', 'smh_top', 'headlines', 'google', 'sbs_top', 'tech_meme_top', 'link-log', 
                 '.DS_Store', 'aus_visa_wait', 'journalism', 'abc_top', 'writing']


already_done.extend(['foi', 'celtics',])
# dirt = [x for x in dirt if x not in already_done]

# %%

dirt = [x for x in dirt if x == 'foi']

for fold in dirt:
    print(fold)
    counter = 0
    if os.path.isdir(f"{pathos}{fold}"):

        iterrer = pathlib.Path(f"{pathos}{fold}")
        fillos = list(iterrer.rglob("*.json"))

        for fillo in fillos:
            counter += 1
            if counter % 50 == 0:
                print("Counter: ", counter)
            folder_stem = fold
            stemmo = str(fillo).split("/")[-1]

            if "latest" in str(fillo):
                new_path = f"{folder_stem}/{stemmo}"

            elif fold == 'celtics':
                if "__" not in str(fillo):
                    datto = stemmo[:10]
                    datto = dateparser.parse(datto, date_formats=['%Y_%m_%d_%H', "%Y%m%d", '%Y-%m-%d-%H']).strftime("%Y-%m")

                    new_path = f"{folder_stem}/dumps/{datto}/{stemmo}"

                    continue
            elif fold == 'foi':

                    if "inter" in str(fillo):
                        stemmo = str(fillo).split("/")[-1]
                        new_path = f"{folder_stem}/dumps/{stemmo}"
                        print("new_path: ", new_path)
                        # print(str(fillo))
                    else:
                        dirk = str(fillo).split("/")[-1].replace(".json", '')
                        # dirk = "_".join(dirk)
                        # print("dirk: ", dirk)
                        dirk = re.search(r'[a-zA-Z]+_{0,1}[a-zA-Z]+', dirk).group()
                        # print("dirk: ", dirk)
                        stemmo = stemmo.replace(f"_{dirk}", "")
                        new_path = f"{folder_stem}/dumps/{dirk}/{stemmo}"
                        # print("new_path: ", new_path)
            else:
                inter_stemmo = stemmo.split(".")[0]

                datto = dateparser.parse(inter_stemmo, date_formats=['%Y_%m_%d_%H', "%Y%m%d", '%Y-%m-%d-%H']).strftime("%Y-%m")

                new_path = f"{folder_stem}/dumps/{datto}/{stemmo}"
            
            # print(new_path)

            s3_client.upload_file(str(fillo), 'chaluchasu', new_path)
    already_done.append(fold)
    print("already_done: ", already_done)

    #     # print(folder_stem)
    #     # print(fillos)



# %%
