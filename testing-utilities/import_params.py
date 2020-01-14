#!/usr/bin/python

import xmltodict
import sys
import json
import requests
from collections import defaultdict

def import_params_to_dict(server_url, task_id):
    params = {}
    full_url = "https://" + server_url + "/ProteoSAFe/ManageParameters"
    print(full_url)
    response = requests.get(full_url, params={"task" : task_id})

    response_text = response.text
    print(response_text, task_id)
    params = xmltodict.parse(response_text)

    print(json.dumps(params,indent = 4))

    return params

def reformat_params(params, blacklist={'task','upload_file_mapping','uuid','user','workflow_version'}):
    parameters = params['parameters']['parameter']

    new_parameters = defaultdict(list)
    for parameter in parameters:
        param_name = parameter["@name"]
        param_value = parameter["#text"]

        if param_name not in blacklist:
            new_parameters[param_name].append(param_value)

    return new_parameters

#Filtering out particular keys from a dict
def filter_params(params, blacklist={'task','upload_file_mapping','uuid','user','workflow_version'}):
    new_dict = {}
    for key in params:
        if key in blacklist:
            continue
        else:
            new_dict[key] = params[key]

    return new_dict


def usage():
    print("<server url e.g. proteomics.ucsd.edu> <task> <output json file>")

def main():
    blacklist = {
        'task',
        'upload_file_mapping',
        'uuid',
        'user'
    }

    server_url = sys.argv[1]
    task_id = sys.argv[2]
    output_json_filename = sys.argv[3]

    params = import_params_to_dict(server_url, task_id)
    params = reformat_params(params, blacklist=blacklist)
    print(json.dumps(params,indent = 4))
    open(output_json_filename, "w").write(json.dumps(params,indent = 4))

if __name__ == '__main__':
    main()
