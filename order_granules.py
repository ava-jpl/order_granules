#!/usr/bin/env python
import os
import sys
import requests
import json
import socket
import xmltodict
import logging
import traceback
import base64
import pandas as pd
from hysds.celery import app


# CMR enviorments
CMR_URL_PROD = "https://urs.earthdata.nasa.gov"
CMR_URL_UAT = "https://cmr.uat.earthdata.nasa.gov"

# ECS Options
AST_09T_ECS_OPTIONS = "conf/AST_09T_2023_12_27.json"
AST_L1B_ECS_OPTIONS = "conf/AST_L1B_2023_12_27.json"

# Order Size Limit
ORDER_LIMIT = 50

# create order_granule.log
LOG_FILE_NAME = 'order_granules.log'
logging.basicConfig(filename=LOG_FILE_NAME,
                    filemode='a', level=logging.INFO)
logger = logging


def main():
    # load context
    ctx = load_context()
    cmr_env = ctx.get("cmr_enviorment", False)
    if cmr_env == "PROD":
        cmr_url = CMR_URL_PROD
    elif cmr_env == "UAT":
        cmr_url = CMR_URL_UAT
    collection_concept_ids = ctx.get("collection_concept_id", False)
    provider_ids = ctx.get("provider_id", False)
    granule_concept_ids = ctx.get("granule_concept_id", False) 
    granule_urs = ctx.get("granule_ur", False)
    producer_granule_ids = ctx.get("producer_granule_id", False)
    short_names = ctx.get("short_name", False)

    # check inputs
    if (type(producer_granule_ids) is list and type(collection_concept_ids) is list and type(granule_concept_ids) is list and type(granule_urs) is list and type(short_names) is list and type(provider_ids) is list):
        if (len(collection_concept_ids) != len(granule_concept_ids) != len(granule_urs) != len(producer_granule_ids) != len(short_names) != len(provider_ids)):
            raise Exception("List of collection_concept_ids, granule_concept_ids, granule_urs, producer_granule_ids, provider_ids are of uneven length")
    elif (type(producer_granule_ids) is str and type(collection_concept_ids) is str and type(granule_concept_ids) is str and type(granule_urs) is str and type(short_names) is str and type(provider_ids) is str):
        producer_granule_ids = [producer_granule_ids]
        collection_concept_ids = [collection_concept_ids]
        granule_concept_ids = [granule_concept_ids]
        granule_urs = [granule_urs]
        short_names = [short_names]
        provider_ids = [provider_ids]
    elif (collection_concept_ids is False or granule_concept_ids is False or granule_urs is False or producer_granule_ids is False or short_names is False or provider_ids is False):
        raise Exception("Either of collection_concept_ids, granule_concept_ids, granule_urs, producer_granule_ids, provider_ids are empty")

    # load creds
    creds = load_creds()
    username = creds.get("username", False)
    password = creds.get("password", False)
    client_id = creds.get("client_id", False)
    user_ip_address = creds.get("user_ip_address", False)
    token = creds.get("token", False)
    order_id = creds.get("order_id", False)

    if (user_ip_address is False):
        user_ip_address = socket.gethostbyname(socket.gethostname())
        creds['user_ip_address'] = user_ip_address
        # update_creds(creds)

    if (token is False):
        # get valid token
        token = get_token(cmr_url, username, password, client_id, user_ip_address)
        # generate new token
        if not token:
            token = generate_token(cmr_url, username, password, client_id, user_ip_address)
        creds['token'] = token
        update_creds(creds)

    # remove granules that exist in AVA
    for i in range(len(producer_granule_ids)):
        # check if granule is already in the system
        if exists(producer_granule_ids[i], short_names[i], granule_urs[i]):
            logger.warning("{} already exists in AVA".format(granule_urs[i]))
            producer_granule_ids.pop(i)
            collection_concept_ids.pop(i)
            granule_concept_ids.pop(i)
            granule_urs.pop(i)
            short_names.pop(i)
            provider_ids.pop(i)

    # create order items dataframe
    order_items_df = pd.DataFrame({
                "granuleConceptId": granule_concept_ids,
                "granuleUr": granule_urs,
                "producerGranuleId": producer_granule_ids
            })
    order_items = order_items_df.to_dict('records')

    # get collectionConceptId, short_name, and provider_id
    collection_concept_id = set(collection_concept_ids).pop()
    provider_id = set(provider_ids).pop()
    short_name = set(short_names).pop()

    # get ecs options
    ecs_options = {}
    if short_name == "AST_L1B":
        # if cmr_url == CMR_URL_UAT:
        #     body = load_ast_l1b_uat_ecs_options()
        # else:
        ecs_options = load_ast_l1b_ecs_options()
    elif short_name == "AST_09T":
        # if cmr_url == CMR_URL_UAT:
        #     body = load_ast_09t_uat_ecs_options()
        # else:
        ecs_options = load_ast_09t_ecs_options()

    # submit orders 
    while len(order_items) > 0:
        order_batch = order_items[0:ORDER_LIMIT]
        submit_order(cmr_url, token, ecs_options, collection_concept_id, provider_id, order_batch)
        del order_items[0:ORDER_LIMIT]


def generate_token(cmr_url, username, password, client_id, user_ip_address):
    ''' Generate a CMR token using credentials. They will last for a month.'''
    try:
        post_token_url = "{}/api/users/token".format(cmr_url)
        print("POST TOKEN URL: {}".format(post_token_url))

        # make post call
        usrPass = "{}:{}".format(username, password).encode()
        b64Val = base64.b64encode(usrPass)
        headers = {"Authorization": "Basic {}".format(b64Val.decode())}
        r = requests.post(url=post_token_url, headers=headers)
        print("POST TOKEN RESPONSE: {}".format(r.text))

        if (r.raise_for_status() is None):
            rdata = json.loads(r.text)
            token = rdata["access_token"]
            print("Generated CMR token: {}".format(token))
            logger.info("Generated CMR token: {}".format(token))
            return token

    except Exception as e:
        raise Exception("Unable to get valid CMR token using credentials\nError: {}".format(e))


def get_token(cmr_url, username, password, client_id, user_ip_address):
    ''' Generate a CMR token using credentials. They will last for a month.'''
    try:
        get_token_url = "{}/api/users/tokens".format(cmr_url)
        print("GET TOKEN URL: {}".format(get_token_url))

        # make post call
        usrPass = "{}:{}".format(username, password).encode()
        b64Val = base64.b64encode(usrPass)
        headers = {"Authorization": "Basic {}".format(str(b64Val.decode()))}
        r = requests.get(url=get_token_url, headers=headers)
        print("GET TOKEN RESPONSE: {}".format(r.text))

        if (r.raise_for_status() is None):
            rdata = json.loads(r.text)
            if len(rdata) > 0:
                token = rdata[0].get("access_token", None)
                print("Valid CMR token: {}".format(token))
                logger.info("Valid CMR token: {}".format(token))
                return token

    except Exception as e:
        raise Exception("Unable generate a CMR token using credentials\nError: {}".format(e))


def submit_order(cmr_url, token, ecs_options, collection_concept_id, provider_id, order_batch):
    '''
    Submit order to LPDAAC
    Example:
        {
            "query":"mutation CreateOrder ($optionSelection: OptionSelectionInput!$orderItems: [OrderItemInput!]!$collectionConceptId: String!$providerId: String!) {createOrder (optionSelection: $optionSelection orderItems: $orderItems collectionConceptId: $collectionConceptId providerId: $providerId) {id state}}",
            "variables": {
                "collectionConceptId": "C1299783609-LPDAAC_ECS",
                "optionSelection": {
                    "conceptId": "OO2700492578-LPDAAC_ECS",
                    "name": "AST_09T_2023_12_27",
                    "content": "<ecs:options xmlns:ecs=\"http://ecs.nasa.gov/options\" xmlns:lpdaac=\"http://lpdaac.usgs.gov/orderoptions.v1\" xmlns:lpdaacSchemaLocation=\"/v1/AST_09_OMI.xsd\"><!--Default distribution method is FTP Pull --><ecs:distribution><ecs:mediatype><ecs:value>FtpPull</ecs:value></ecs:mediatype><ecs:mediaformat><ecs:ftppull-format><ecs:value>FILEFORMAT</ecs:value></ecs:ftppull-format></ecs:mediaformat></ecs:distribution><ecs:processing><ecs:endpoint>http://elpdx159.cr.usgs.gov:8180/tcoc/PXG_v1/ProcessingXMLGateway</ecs:endpoint><ecs:consider-processing-options-in-request-bundling>false</ecs:consider-processing-options-in-request-bundling><ecs:max-order-item-size>50</ecs:max-order-item-size></ecs:processing><lpdaac:subsetSpecification><lpdaac:productName criteriaName=\"Product Name\" criteriaType=\"FIXED\">AST_09T</lpdaac:productName><lpdaac:longName criteriaName=\"Long Name\" criteriaType=\"FIXED\">ASTER On-Demand L2 Surface Radiance TIR</lpdaac:longName><lpdaac:granuleSize criteriaName=\"Granule_size\" criteriaType=\"FIXED\">0</lpdaac:granuleSize><lpdaac:fileFormat criteriaName=\"File Format\" criteriaType=\"FIXED\"><lpdaac:fileFormatValue>HDF</lpdaac:fileFormatValue></lpdaac:fileFormat><lpdaac:aerosols criteriaName=\"Aerosols\" criteriaType=\"STRING\"><lpdaac:aerosolsValue>Climatology</lpdaac:aerosolsValue></lpdaac:aerosols><lpdaac:columnOzone criteriaName=\"Column Ozone\" criteriaType=\"STRING\"><lpdaac:columnOzoneValue>OZ2DAILY - NCEP TOVS Daily Ozone</lpdaac:columnOzoneValue></lpdaac:columnOzone><lpdaac:moistureTemperaturePressure criteriaName=\"Moisture, Temperature, Pressure\" criteriaType=\"STRING\"><lpdaac:moistureTemperaturePressureValue>GDAS0ZFH - NOAA/NCEP GDAS model, 6h, 1 deg</lpdaac:moistureTemperaturePressureValue></lpdaac:moistureTemperaturePressure></lpdaac:subsetSpecification></ecs:options>"
                },
                "providerId": "LPDAAC_ECS",
                "orderItems": [
                    {
                        "granuleConceptId": "G2946767529-LPDAAC_ECS",
                        "granuleUr": "SC:AST_09T.003:2699270593",
                        "producerGranuleId": "AST_L1A#00304222024232153_04232024080015.hdf"
                    }
                ]
            }
        }
    '''
    try:
        post_submit_order_url = "{}/ordering/api".format(cmr_url)
        print("POST SUBMIT ORDER URL: {}".format(post_submit_order_url))

        # make post call
        headers = {"Authorization": "Bearer {}".format(token)}

        # body
        body = {
                "query":"mutation CreateOrder ($optionSelection: OptionSelectionInput!$orderItems: [OrderItemInput!]!$collectionConceptId: String!$providerId: String!) {createOrder (optionSelection: $optionSelection orderItems: $orderItems collectionConceptId: $collectionConceptId providerId: $providerId) {id state}}",
                "variables": {
                    "collectionConceptId": collection_concept_id,
                    "optionSelection": ecs_options,
                    "providerId": provider_id,
                    "orderItems": order_batch
                }
            }

        r = requests.post(url=post_submit_order_url, headers=headers, body=json.dumps(body))
        print("POST SUBMIT ORDER RESPONSE: {}".format(r.text))
        r.raise_for_status()

        if (r.status_code == 200):
            order_id = r.json()["data"]["createOrder"]["id"]
            print("Successfully submitted order for order ID: {}".format(order_id))
            logger.info("Successfully submitted order for order ID: {}".format(order_id))
            return True
        else:
            print("Unable to submit order:\n{}".format(json.dumps(body, indent=2)))
            logger.warning("Unable to submit order:\n{}".format(json.dumps(body, indent=2)))
            return False

    except Exception as e:
        raise Exception('Unable to submit order:\n{}\nError: {}'.format(json.dumps(body, indent=2), e))


def load_context():
    '''loads the context file into a dict'''
    try:
        context_file = '_context.json'
        with open(context_file, 'r') as fin:
            context = json.load(fin)
        return context
    except:
        raise Exception('unable to parse _context.json from work directory')


def load_creds():
    '''loads the creds file into a dict'''
    try:
        dirname = os.path.dirname(__file__)
        creds_file = os.path.join(dirname, "conf/creds.json")
        with open(creds_file, 'r') as fin:
            creds = json.load(fin)
        return creds
    except:
        raise Exception('unable to parse conf/creds.json from work directory')


def update_creds(creds):
    '''updates the creds file into a dict'''
    try:
        dirname = os.path.dirname(__file__)
        creds_file = os.path.join(dirname, "conf/creds.json")
        with open(creds_file, 'w') as fin:
            creds = json.dump(creds, fin)
    except:
        raise Exception('unable to update conf/creds.json from work directory')


def load_ast_09t_ecs_options():
    '''loads the creds file into a dict'''
    try:
        creds = {}
        dirname = os.path.dirname(__file__)
        creds_file = os.path.join(dirname, AST_09T_ECS_OPTIONS)
        with open(creds_file, 'r') as fin:
            creds = json.load(fin)
        return creds
    except Exception as e:
        raise Exception(
            'Unable to parse {} from work directory\nError: {}'.format(AST_09T_ECS_OPTIONS, e))


def load_ast_l1b_ecs_options():
    '''loads the creds file into a dict'''
    try:
        creds = {}
        dirname = os.path.dirname(__file__)
        creds_file = os.path.join(dirname, AST_L1B_ECS_OPTIONS)
        with open(creds_file, 'r') as fin:
            creds = json.load(fin)
        return creds
    except Exception as e:
        raise Exception(
            'Unable to parse {} from work directory\nError: {}'.format(AST_L1B_ECS_OPTIONS, e))


def load_ast_09t_uat_ecs_options():
    '''loads the creds file into a dict'''
    try:
        dirname = os.path.dirname(__file__)
        creds_file = os.path.join(dirname, "conf/AST_09T_UAT_ecs_options.xml")
        with open(creds_file) as fin:
            tree = xmltodict.parse(fin.read(), process_namespaces=True)
        return tree
    except:
        raise Exception(
            'unable to parse conf/AST_09T_ecs_options.xml from work directory')


def load_ast_l1b_uat_ecs_options():
    '''loads the creds file into a dict'''
    try:
        dirname = os.path.dirname(__file__)
        creds_file = os.path.join(dirname, "conf/AST_L1B_UAT_ecs_options.xml")
        with open(creds_file) as fin:
            tree = xmltodict.parse(fin.read(), process_namespaces=True)
        return tree
    except:
        raise Exception(
            'unable to parse conf/AST_L1B_ecs_options.xml from work directory')


def exists(producer_granule_id, shortname, id):
    '''queries grq to see if the input id exists. Returns True if it does, False if not'''
    VERSION = "v1.0"
    if shortname == "AST_L1B":
        PROD_TYPE = "grq_v1.0_ast_l1b"
    elif shortname == "AST_09T":
        PROD_TYPE = "grq_v1.0_ast_09t"
    split_id = id.split(":")
    id = "*" + split_id[-1]
    grq_ip = app.conf['GRQ_ES_URL']#.replace(':9200', '').replace('http://', 'https://')
    grq_url = '{0}/{1}/_search'.format(grq_ip, PROD_TYPE.format(VERSION, shortname))
    # es_query = {"query":{"bool":{"must":[{"query_string":{"default_field":"metadata.short_name.raw","query":shortname}},{"query_string":{"default_field":"metadata.id.raw","query":id}},{"query_string":{"default_field":"metadata.producer_granule_id.raw","query":producer_granule_id}}],"must_not":[],"should":[]}},"from":0,"size":1,"sort":[],"aggs":{}}
    es_query = {"query":{"bool":{"must":[{"term":{"metadata.short_name.raw":shortname}},{"term":{"metadata.producer_granule_id.raw":producer_granule_id}},{"wildcard":{"metadata.title.raw":id}}],"must_not":[],"should":[]}},"from":0,"size":10,"sort":[],"aggs":{}}
    return query_es(grq_url, es_query)


def query_es(grq_url, es_query):
    '''simple single elasticsearch query, used for existence. returns count of result.'''
    print('querying: {} with {}'.format(grq_url, es_query))
    response = requests.post(grq_url, data=json.dumps(es_query), verify=False)
    try:
        response.raise_for_status()
    except:
        # if there is an error (or 404,just publish
        return 0
    text = response.text.encode('ascii')
    results = json.loads(text)
    results_list = results.get('hits', {}).get('hits', [])
    total_count = results.get('hits', {}).get('total', 0)
    return int(total_count)


if __name__ == '__main__':
    try: status = main()
    except Exception as e:
        with open('_alt_error.txt', 'w') as f:
            f.write("%s\n" % str(e))
        with open('_alt_traceback.txt', 'w') as f:
            f.write("%s\n" % traceback.format_exc())
        raise
    sys.exit(status)
    