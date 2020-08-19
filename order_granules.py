#!/usr/bin/env python

import os
import requests
import json
import socket
import xmltodict
import logging
from hysds.celery import app

# CMR enviorments
CMR_URL_PROD = "https://cmr.earthdata.nasa.gov"
CMR_URL_UAT = "https://cmr.uat.earthdata.nasa.gov"

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
    producer_granule_ids = ctx.get("producer_granule_id", False)
    dataset_ids = ctx.get("dataset_id", False)
    catalog_item_ids = ctx.get("catalog_item_id", False)
    granule_urs = ctx.get("granule_ur", False)
    short_names = ctx.get("short_name", False)

    # check if inputs have equal length
    if (len(dataset_ids) != len(catalog_item_ids) != len(granule_urs) != len(producer_granule_ids) != len(short_names)):
        raise Exception(
            "List of dataset_ids, catalog_item_ids, granule_urs, producer_granule_ids are of uneven length")

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
        token = generate_token(cmr_url, username, password, client_id, user_ip_address)
        creds['token'] = token
        # update_creds(creds)

    if (order_id is False):
        order_id = generate_empty_order(cmr_url, username, token)
        creds['order_id'] = order_id
        # update_creds(creds)

    granules_added = 0
    for i in range(len(catalog_item_ids)):

        if granules_added >= 100:
            # add user information
            add_user_information(cmr_url, token, order_id)
            # submit
            submit_order(cmr_url, token, order_id)
            # generate new order_id
            order_id = generate_empty_order(cmr_url, username, token)
            # reset counter
            granules_added = 0

        # check if granule is already in the system
        if exists(producer_granule_ids[i], short_names[i], catalog_item_ids[i]):
            logger.warning("{} already exists in AVA".format(catalog_item_ids[i]))
            continue

        else:
            # add to order
            status = add_to_order(cmr_url, order_id, token, dataset_ids[i], catalog_item_ids[i],
                        granule_urs[i], producer_granule_ids[i], short_names[i])
            if status == 422:
                # generate new token
                token = generate_token(cmr_url, username, password, client_id, user_ip_address)
                # attempt to add to order with new token
                status = add_to_order(cmr_url, order_id, token, dataset_ids[i], catalog_item_ids[i], granule_urs[i], producer_granule_ids[i], short_names[i])
                # increment the counter 
                granules_added = granules_added + 1
            else:
                # increment the counter 
                granules_added = granules_added + 1
            
    # add user information to last order id
    add_user_information(cmr_url, token, order_id)

    # submit last order id
    submit_order(cmr_url, token, order_id)


def generate_token(cmr_url, username, password, client_id, user_ip_address):
    ''' Generate a CMR token using credentials. They will last for a month.'''
    try:
        post_token_url = "{}/legacy-services/rest/tokens".format(cmr_url)
        print("POST TOKEN URL: {}".format(post_token_url))

        # make post call
        body = {"token": {
            "username": username,
            "password": password,
            "client_id": client_id,
            "user_ip_address": user_ip_address
        }
        }
        print("POST TOKEN BODY: {}".format(body))

        r = requests.post(url=post_token_url, json=body)
        print("POST TOKEN RESPONSE: {}".format(r.text))

        if (r.raise_for_status() is None):
            tree = xmltodict.parse(r.text)
            token = tree['token']['id']
            print("Generated CMR token: {}".format(token))
            logger.info("Generated CMR token: {}".format(token))
            return token

    except:
        raise Exception('unable generate a CMR token using credentials')


# generate empty order
def generate_empty_order(cmr_url, username, token):
    ''' Generate an empty order from CMR using credentials.'''
    try:
        post_generate_order_url = "{}/legacy-services/rest/orders".format(cmr_url)
        print("POST ORDER URL: {}".format(post_generate_order_url))

        # make post call
        headers = {"Echo-Token": token}

        body = {"order": {"owner_id": username}}
        print("POST ORDER BODY: {}".format(body))

        r = requests.post(url=post_generate_order_url,
                          json=body, headers=headers)
        print("POST ORDER RESPONSE: {}".format(r.text))

        if (r.raise_for_status() is None):
            tree = xmltodict.parse(r.text)
            order = tree['order']['id']
            print("Generated order ID: {}".format(order))
            logger.info("Generated order ID: {}".format(order))
            return order

    except:
        raise Exception('unable generate an order ID')


def add_user_information(cmr_url, token, order_id):
    ''' Add user information to order '''
    try:
        put_user_info_url = "{}/legacy-services/rest/orders/{}/user_information".format(cmr_url,
            order_id)
        print("PUT ADD USER INFO URL: {}".format(put_user_info_url))

        # get user_info.xml file location
        creds_file = os.path.join(
            os.path.dirname(__file__), "conf/user_info.xml")

        # make post call
        headers = {'Content-Type': 'application/xml', "Echo-Token": token}

        body = open(creds_file).read()
        print("PUT ADD USER INFO BODY: {}".format(body))

        r = requests.put(url=put_user_info_url,
                         data=body, headers=headers)
        print("PUT ADD USER INFO RESPONSE: {}".format(r.text))

    except:
        raise Exception(
            'unable to add user information to order ID: {}'.format(order_id))


def add_to_order(cmr_url, order_id, token, dataset_ids, catalog_item_ids, granule_urs, producer_granule_ids, short_names):
    ''' Add producer_granule_ids to order '''

    try:
        post_order_items_url = "{}/legacy-services/rest/orders/{}/order_items".format(cmr_url,
            order_id)
        print("POST ADD ORDER ITEMS URL: {}".format(post_order_items_url))

        # make post call
        headers = {'Content-Type': 'application/xml', "Echo-Token": token}

        # for i in range(len(producer_granule_ids)):
            # check if granule is already in the system
            # if exists(producer_granule_ids[i], short_names[i], catalog_item_ids[i]):
            #     continue

        # get ecs options
        if short_names == "AST_L1B":
            if cmr_url == CMR_URL_UAT:
                body = load_ast_l1b_uat_ecs_options()
            else:
                body = load_ast_l1b_ecs_options()
        elif short_names == "AST_09T":
            if cmr_url == CMR_URL_UAT:
                body = load_ast_09t_uat_ecs_options()
            else:
                body = load_ast_09t_ecs_options()
        body['order_item']['dataset_id'] = dataset_ids
        body['order_item']['catalog_item_id'] = catalog_item_ids
        body['order_item']['granule_ur'] = granule_urs
        body['order_item']['producer_granule_id'] = producer_granule_ids
        body = xmltodict.unparse(body, pretty=True)

        print("POST ADD ORDER ITEMS BODY: {}".format(body))

        # make post request
        r = requests.post(url=post_order_items_url,
                            data=body, headers=headers)
        print("POST ADD ORDER ITEMS RESPONSE: {}".format(r.text))

        if r.status_code == 422:
            return 422
        elif (r.raise_for_status() is None):
            tree = xmltodict.parse(r.text)
            order = tree['order_item']['order_ref']['id']
            ordered_catalog_item_id = tree['order_item']['catalog_item_id']
            print("Added {} to order ID {}".format(ordered_catalog_item_id,order))
            logger.info("Added {} to order ID {}".format(ordered_catalog_item_id,order))
            return None

    except:
        raise Exception(
            'unable to add producer_granule_ids to order ID: {}'.format(order_id))


def submit_order(cmr_url, token, order_id):
    '''Submit order to LPDAAC'''
    try:
        post_submit_order_url = "{}/legacy-services/rest/orders/{}/submit".format(cmr_url,
            order_id)
        print("POST SUBMIT ORDER URL: {}".format(post_submit_order_url))

        # make post call
        headers = {"Echo-Token": token}

        r = requests.post(url=post_submit_order_url, headers=headers)
        print("POST SUBMIT ORDER RESPONSE: {}".format(r.text))
        r.raise_for_status()

        if (r.status_code == 204):
            print("Successfully submitted order for order ID: {}".format(order_id))
            logger.info("Successfully submitted order for order ID: {}".format(order_id))

    except:
        raise Exception('unable to submit order ID: {}'.format(order_id))


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
        dirname = os.path.dirname(__file__)
        creds_file = os.path.join(dirname, "conf/AST_09T_ecs_options.xml")
        with open(creds_file) as fin:
            tree = xmltodict.parse(fin.read(), process_namespaces=True)
        return tree
    except:
        raise Exception(
            'unable to parse conf/AST_09T_ecs_options.xml from work directory')


def load_ast_l1b_ecs_options():
    '''loads the creds file into a dict'''
    try:
        dirname = os.path.dirname(__file__)
        creds_file = os.path.join(dirname, "conf/AST_L1B_ecs_options.xml")
        with open(creds_file) as fin:
            tree = xmltodict.parse(fin.read(), process_namespaces=True)
        return tree
    except:
        raise Exception(
            'unable to parse conf/AST_L1B_ecs_options.xml from work directory')

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
    grq_ip = app.conf['GRQ_ES_URL']#.replace(':9200', '').replace('http://', 'https://')
    grq_url = '{0}/{1}/_search'.format(grq_ip, PROD_TYPE.format(VERSION, shortname))
    es_query = {"query":{"bool":{"must":[{"query_string":{"default_field":"metadata.short_name.raw","query":shortname}},{"query_string":{"default_field":"metadata.id.raw","query":id}},{"query_string":{"default_field":"metadata.producer_granule_id.raw","query":producer_granule_id}}],"must_not":[],"should":[]}},"from":0,"size":1,"sort":[],"aggs":{}}
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
    results = json.loads(response.text, encoding='ascii')
    results_list = results.get('hits', {}).get('hits', [])
    total_count = results.get('hits', {}).get('total', 0)
    return int(total_count)


if __name__ == '__main__':
    main()
