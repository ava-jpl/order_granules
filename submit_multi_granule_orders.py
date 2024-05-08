import json
import os
import argparse
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import elasticsearch
from datetime import date
from hysds.celery import app
from hysds_commons.job_utils import submit_mozart_job
from hysds_commons.job_utils import submit_hysds_job
from hysds_commons.job_utils import resolve_hysds_job

TEST = False

if TEST is True:
    es_url = "http://localhost:9203/"
else:
    es_url = app.conf["GRQ_ES_URL"]

ES = elasticsearch.Elasticsearch(es_url)

def get_params(job_name, queue, job_version, priority, tags, shortname, starttime, endtime , env, geojson):
    """
    This function would query for all the granules for AST_09T or AST_L1B
    """
    # query granule metdata
    if shortname == "AST_L1B":
        _type = "metadata-AST_L1B"
        index = "grq_v1.0_metadata-ast_l1b"
    elif shortname == "AST_09T":
        _type = "metadata-AST_09T"
        index = "grq_v1.0_metadata-ast_09t"

    
    if starttime and endtime and geojson:
        geojson = json.loads(geojson)
        query = {"query":{"bool":{"must":[{"range":{"starttime":{"gt": starttime,"lt": endtime}}}],"must_not":[],"should":[]}},"filter":{"geo_shape":{"location":{"shape": geojson}}}}

    elif starttime and endtime:
        query = {"query":{"bool":{"must":[],"must_not":[],"should":[{"range":{"starttime":{"gt": starttime ,"lt": endtime }}}]}},"from":0,"size":10,"sort":[]}
        # query = {"query":{"bool":{"must":[{"range":{"starttime":{"gt":starttime,"lt":endtime}}}],"must_not":[],"should":[]}},"sort":[],"aggs":{}}
    else:
        query = {"query":{"bool":{"must":[{"match_all":{}}],"must_not":[],"should":[]}},"sort":[]}

    # get granule metadata
    granule_list = []
    rest_url = es_url[:-1] if es_url.endswith('/') else es_url
    url = "{}/{}/_search?search_type=scan&scroll=60&size=10000".format(rest_url, index)
    r = requests.post(url, data=json.dumps(query))
    r.raise_for_status()
    scan_result = r.json()
    count = scan_result['hits']['total']
    if count == 0:
        return []
    if '_scroll_id' not in scan_result:
        print("_scroll_id not found in scan_result. Returning empty array for the query :\n%s" % query)
        return []
    scroll_id = scan_result['_scroll_id']
    hits = []
    while True:
        r = requests.post('%s/_search/scroll?scroll=60m' % rest_url, data=scroll_id)
        res = r.json()
        scroll_id = res['_scroll_id']
        if len(res['hits']['hits']) == 0:
            break
        hits.extend(res['hits']['hits'])

    collection_concept_ids = []
    provider_ids = []
    granule_concept_ids = []
    granule_urs = []
    producer_granule_ids = []
    short_names = []

    for item in hits:
        collection_concept_ids.append(item.get("_source").get("metadata").get("collection_concept_id"))
        provider_ids.append(item.get("_source").get("metadata").get("dataset_center"))
        granule_concept_ids.append(item.get("_source").get("metadata").get("id"))
        granule_urs.append(item.get("_source").get("metadata").get("title"))
        producer_granule_ids.append(item.get("_source").get("metadata").get("producer_granule_id"))     
        short_names.append(item.get("_source").get("metadata").get("short_name"))

    # for item in hits:
    #     producer_granule_ids = item.get("_source").get("metadata").get("producer_granule_id")
    #     dataset_ids = item.get("_source").get("metadata").get("dataset_id")
    #     catalog_item_ids = item.get("_source").get("metadata").get("id")
    #     granule_urs = item.get("_source").get("metadata").get("title")
    #     short_names = item.get("_source").get("metadata").get("short_name")

        params = {
            "cmr_enviorment": env,
            "collection_concept_id": collection_concept_ids,
            "provider_id": provider_ids,
            "granule_concept_id": granule_concept_ids,
            "granule_ur": granule_urs,
            "producer_granule_id": producer_granule_ids,
            "short_name": short_names
        }

        job_params = {
            'queue': queue,
            'priority': int(priority),
            'tags': tags,
            'type': '%s:%s' % (job_name, job_version),
            'params': json.dumps(params),
            'enable_dedup': True,
            'payload_hash': None,
            'enable_dedup': True
        }

    return job_params


def submit_job(job_name, job_params):
    # submit mozart job
    try:
        job_json = resolve_hysds_job(job_params["type"], job_params["queue"], job_params["priority"],
                                                                    job_params["tags"], job_params["params"],
                                                                    job_name=job_name,
                                                                    payload_hash=job_params["payload_hash"],
                                                                    enable_dedup=job_params["enable_dedup"])
        ident = submit_hysds_job(job_json)
        print("JOB ID: {}".format(ident))

    except Exception as e:
        raise Exception("Failed to submit HySDS Job:\nERROR: {0}".format(e))


if __name__ == '__main__':
    today = date.today()
    date = today.strftime("%Y%m%d")
    default_tags = [str(date) + '-automated-granule-order'];
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-j', '--job_name', help='Job name',
                        dest='job_name', required=False, default="job-order_multiple_granules")
    parser.add_argument('-sn', '--short_name', help='Granule type (i.e AST_09T or AST_L1B)',
                        dest='short_name', required=True)
    parser.add_argument('-env', '--enviornment', help='cmr enviornment: PROD or UAT', dest='env', required=False, default="PROD")
    parser.add_argument('-v', '--version', help='release version, eg "master" or "release-20180615"',
                        dest='version', required=False, default='master')
    parser.add_argument('-q', '--queue', help='Job queue', dest='queue',
                        required=False, default='factotum-job_worker-small')
    parser.add_argument('-pr', '--priority', help='Job priority',
                        dest='priority', required=False, default='2')
    parser.add_argument('-g', '--tags', help='Job tags. Use a comma separated list for more than one',
                        dest='tags', required=False, default=default_tags)
    parser.add_argument('-st', '--starttime', help='starttime: 2021-09-01T00:00:00.000Z',
                        dest='starttime', required=False)
    parser.add_argument('-et', '--endtime', help='endtime: 2021-12-01T00:00:00.000Z',
                        dest='endtime', required=False)
    parser.add_argument('-geo', '--geojson', help='geojson of desired location',
                        dest='geojson', required=False)
    args = parser.parse_args()
    params = get_params(args.job_name, args.queue, args.version, args.priority, args.tags, args.short_name, args.starttime, args.endtime, args.env, args.geojson)
    print(json.dumps(params, indent=4, sort_keys=True))

    if TEST is False:
        submit_job(args.job_name, params)