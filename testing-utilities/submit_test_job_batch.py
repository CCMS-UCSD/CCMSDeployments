#!/usr/bin/python

#This executable loads the job submissions in JSON and submits them one by one

import sys
import getopt
import os
import json
import time
import uuid
import requests
import pandas as pd
from import_params import filter_params
from import_params import reformat_params
from import_params import import_params_to_dict
from regression_tests import test_view_counts

def invoke_workflow(credentials, parameters):
    s = requests.Session()

    login = {
        'user' : credentials['username'],
        'password' : credentials['password'],
        'login' : 'Sign in'
    }

    r_login = s.post('https://{}/ProteoSAFe/user/login.jsp'.format(credentials['server_url']), data=login)
    r_login.status_code
    r_login.raise_for_status()

    r_invoke = s.post('https://{}/ProteoSAFe/InvokeTools'.format(credentials['server_url']), data=parameters)
    r_invoke.raise_for_status()

    task_id = r_invoke.text

    print(task_id)

    if len(task_id) > 4 and len(task_id) < 60:
        print("Launched Task: {}".format(task_id))
        return task_id
    else:
        print(task_id)
        return None

def delete_task(task_id, credentials):
    s = requests.Session()

    login = {
        'user' : credentials['username'],
        'password' : credentials['password'],
        'login' : 'Sign in'
    }

    r_login = s.post('https://{}/ProteoSAFe/user/login.jsp'.format(credentials['server_url']), data=login)
    r_login.status_code
    r_login.raise_for_status()

    r_invoke = s.get('https://{}/ProteoSAFe/Delete?task={}'.format(credentials['server_url'], task_id))
    r_invoke.raise_for_status()

def wait_for_workflow_finish(task_id, max_time, credentials):
    start_time = int(round(time.time()))

    try:
        url = 'https://' + credentials['server_url'] + '/ProteoSAFe/status_json.jsp?task=' + task_id
        r = requests.get(url, verify=False)
        json_obj = r.json()
    except:
        print(r.text)
        raise


    while (json_obj["status"] != "FAILED" and json_obj["status"] != "DONE" and json_obj["status"] != "SUSPENDED"):
        print("Waiting for task: " + task_id)
        time.sleep(60)
        current_time = int(round(time.time()))

        if (current_time - start_time) > max_time:
            print("TOOK TOO LONG for WORKFLOW TO FINISH")
            exit(1)

        try:
            json_obj = json.loads(requests.get(url, verify=False).text)
        except KeyboardInterrupt:
            raise
        except:
            print("Exception In Wait")
            time.sleep(1)

    return json_obj["status"]

import argparse

def main():
    parser = argparse.ArgumentParser(description='Run tests in batch mode')
    parser.add_argument('--credentials_file', default=None, help="Credentials JSON to log on")
    parser.add_argument('--credential_username', default=None, help="Credentials Username")
    parser.add_argument('--credential_password', default=None, help="Credentials Password")
    parser.add_argument('--credential_server', default="proteomics3.ucsd.edu", help="Credentials Password")
    parser.add_argument('--wait_time', default=3600, type=int, help="Seconds to wait for completion")
    parser.add_argument('--workflow_json', nargs="+", help="Set of json files to test")
    parser.add_argument('--workflow_task', nargs="+", help="Set of workflow tasks to test")
    parser.add_argument('--workflow_task_file', default=None, help="Set of workflow tasks to test")
    args = parser.parse_args()

    wait_time = args.wait_time

    if args.credentials_file is not None:
        credentials_file = args.credentials_file
        credentials = json.loads(open(credentials_file).read())
    else:
        credentials = {}
        credentials["server_url"] = args.credential_server
        credentials["username"] = args.credential_username
        credentials["password"] = args.credential_password

        if credentials["username"] is None:
            print("Please Enter Username")
            return 1

    regression_test_candidates = []
    task_list = []

    # Processing JSON Tests
    if args.workflow_json != None:
        for path_to_json_file in args.workflow_json:
            param_object = json.loads(open(path_to_json_file).read())
            param_object = filter_params(param_object)

            param_object["desc"][0] = param_object["desc"][0] + " - " + " Clone of JSON {}".format(os.path.basename(path_to_json_file))
            param_object["email"][0] = "ccms.web@gmail.com"

            task_id = invoke_workflow(credentials, param_object)
            if task_id == None:
                exit(1)
            
            time.sleep(15)

            task_list.append(task_id)

    # Processing Task Tests
    if args.workflow_task != None:
        for task_id in args.workflow_task:
            param_object = import_params_to_dict(credentials['server_url'], task_id)
            param_object = reformat_params(param_object)
            param_object = filter_params(param_object)

            param_object["desc"][0] = param_object["desc"][0] + " - " + " Clone of {}".format(task_id)
            param_object["email"][0] = "ccms.web@gmail.com"

            new_task_id = invoke_workflow(credentials, param_object)
            if new_task_id == None:
                exit(1)
            
            time.sleep(15)

            task_list.append(new_task_id)

            regression_test_candidates.append((task_id, new_task_id, param_object["workflow"][0], credentials['server_url']))

    # Processing Tasks in a File
    if args.workflow_task_file != None:
        row_records = pd.read_csv(args.workflow_task_file, sep=",").to_dict(orient="records")
        for row in row_records:
            print(row)
            task_id = row["task_id"]
            param_object = import_params_to_dict(credentials['server_url'], task_id)
            param_object = reformat_params(param_object)
            param_object = filter_params(param_object)

            param_object["desc"][0] = param_object["desc"][0] + " - " + " Clone of {}".format(task_id)
            param_object["email"][0] = "ccms.web@gmail.com"

            new_task_id = invoke_workflow(credentials, param_object)
            if new_task_id == None:
                exit(1)
            
            time.sleep(15)

            task_list.append(new_task_id)

            # These are the views we will test for consistency in the count of rows
            regression_views = []
            try:
                regression_views = row["regressioncountviews"].split(";")
            except:
                regression_views = []
            for regression_count_view in regression_views:
                # Creating Regression candidate
                regression_candidate = {}
                regression_candidate["old_task"] = task_id
                regression_candidate["new_task"] = new_task_id
                regression_candidate["view_name"] = regression_count_view

                regression_test_candidates.append(regression_candidate)

    time.sleep(60)

    # Barrier
    for task_id in task_list:
        status = wait_for_workflow_finish(task_id, wait_time, credentials)

    output_failures_dict = {}

    # Regression Tests
    for regression_candidate in regression_test_candidates:
        server_url = credentials['server_url']
        if not test_view_counts(regression_candidate["old_task"], \
            regression_candidate["new_task"], 
            server_url, regression_candidate["view_name"]):
            print("Regression test failed", regression_candidate["old_task"], regression_candidate["new_task"], server_url)
            output_failures_dict[regression_candidate["new_task"]] = "Regression Failure"

    # Removing Tasks
    for task_id in task_list:
        if task_id in output_failures_dict:
            continue

        status = wait_for_workflow_finish(task_id, wait_time, credentials)
        if status == "DONE":
            delete_task(task_id, credentials)
        else:
            print("Task {} ended with status [{}]".format(task_id, status))
            output_failures_dict[task_id] = "Workflow Failure"

    if len(output_failures_dict) > 0:
        for task in output_failures_dict:
            print(task, output_failures_dict[task])
        exit(1)
    else:
        exit(0)

if __name__ == "__main__":
    main()
