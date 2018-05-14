import yaml ### install the pyyaml package
import json
from lookerapi import LookerApi
from datetime import datetime
from pprint import pprint
from collections import defaultdict
from itertools import groupby

### ------- HERE ARE PARAMETERS TO CONFIGURE -------

# host name in config.yml
host = 'sandbox'
# model that you wish to analyze
model_name = 'trace_surfing'
# How far you wish to look back
timeframe = '28 days'

### ------- OPEN THE CONFIG FILE and INSTANTIATE API -------
f = open('config.yml')
params = yaml.load(f)
f.close()

my_host = params['hosts'][host]['host']
my_secret = params['hosts'][host]['secret']
my_token = params['hosts'][host]['token']

looker = LookerApi(host=my_host,
                 token=my_token,
                 secret = my_secret)

# print('Getting fields in '+model_name+'...')

def get_explores(model):
    print('Getting model ' + model_name)
    model = looker.get_model(model)
    explore_names = [i['name'] for i in model['explores']]
    explores = [looker.get_explore(model_name, i) for i in explore_names]
    return explores

def get_fields(model):
    fields =[]
    for explore in get_explores(model):
        [fields.append(dimension['name']) for dimension in explore['fields']['dimensions']]
        [fields.append(measure['name']) for measure in explore['fields']['measures']]
    distinct_fields = sorted(set(fields))
    return(fields)

get_fields(model_name)
def schema_builder(model):
    schema = []
    distinct_fields = sorted(set(get_fields(model)))
    view_field_pairs = [field.split('.') for field in distinct_fields]
    for key, group in groupby(view_field_pairs, lambda x:x[0]):
        schema.append({"view": key,
        "fields": [i[1] for i in list(group)]
        })
    pprint(schema)
    # print(len(distinct_fields))
schema_builder(model_name)
# get_fields(model_name)

        # schema.append(data)
