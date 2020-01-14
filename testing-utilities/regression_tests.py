import pandas as pd
import argparse
import requests

def test_view_counts(old_task_id, new_task_id, server_url, view_name):
    print(old_task_id, new_task_id, server_url, view_name)

    old_url = "https://{}/ProteoSAFe/result_json.jsp?task={}&view={}".format(server_url, old_task_id, view_name)
    new_url = "https://{}/ProteoSAFe/result_json.jsp?task={}&view={}".format(server_url, new_task_id, view_name)

    old_df = pd.DataFrame(requests.get(old_url).json()["blockData"])
    new_df = pd.DataFrame(requests.get(new_url).json()["blockData"])

    if len(old_df) == len(new_df):
        return True
    else:
        return False