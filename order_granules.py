#!/usr/bin/env python

import os
import requests
import json
import socket
import xmltodict
import logging


def main():

    # LOG_FILE_NAME = 'order_granules.log'
    # logging.basicConfig(filename=LOG_FILE_NAME,
    #                     filemode='a', level=logging.DEBUG)
    # logger = logging

    # load context
    ctx = load_context()
    producer_granule_ids = ctx.get("producer_granule_id", False)
    dataset_ids = ctx.get("dataset_id", False)
    catalog_item_ids = ctx.get("catalog_item_id", False)
    granule_urs = ctx.get("granule_ur", False)
    short_names = ctx.get("short_name", False)

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
        update_creds(creds)

    if (token is False):
        token = generate_token(username, password, client_id, user_ip_address)
        creds['token'] = token
        update_creds(creds)

    if (order_id is False):
        order_id = generate_empty_order(username, token)
        creds['order_id'] = order_id
        update_creds(creds)

    # generate token
    token = generate_token(username, password, client_id, user_ip_address)

    # create empty order
    order_id = generate_empty_order(username, token)

    # add user information
    add_user_information(token, order_id)

    # add to order
    add_to_order(order_id, token, dataset_ids, catalog_item_ids,
                 granule_urs, producer_granule_ids, short_names)

    # submit
    submit_order(token, order_id)


def generate_token(username, password, client_id, user_ip_address):
    ''' Generate a CMR token using credentials. They will last for a month.'''
    try:
        post_token_url = "https://cmr.earthdata.nasa.gov/legacy-services/rest/tokens"
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
            return token

    except:
        raise Exception('unable generate a CMR token using credentials')


# generate empty order
def generate_empty_order(username, token):
    ''' Generate an empty order from CMR using credentials.'''
    try:
        post_generate_order_url = "https://cmr.earthdata.nasa.gov/legacy-services/rest/orders"
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
            return order

    except:
        raise Exception('unable generate an order ID')


def add_user_information(token, order_id):
    ''' Add user information to order '''
    try:
        post_user_info_url = "https://cmr.earthdata.nasa.gov/legacy-services/rest/orders/{}/user_information".format(
            order_id)
        print("POST ADD USER INFO URL: {}".format(post_user_info_url))

        # get user_info.xml file location
        creds_file = os.path.join(
            os.path.dirname(__file__), "conf/user_info.xml")

        # make post call
        headers = {'Content-Type': 'text/xml', "Echo-Token": token}

        with open(creds_file) as body:
            print("POST ORDER BODY: {}".format(body))
            r = requests.post(url=post_user_info_url,
                              data=body, headers=headers)
            print("POST ORDER RESPONSE: {}".format(r.text))

    except:
        raise Exception(
            'unable to add user information to order ID: {}'.format(order_id))


def add_to_order(order_id, token, dataset_ids, catalog_item_ids, granule_urs, producer_granule_ids, short_names):
    ''' Add producer_granule_ids to order '''

    # check if inputs have equal length
    if (len(dataset_ids) != len(catalog_item_ids) != len(granule_urs) != len(producer_granule_ids) != len(short_names)):
        raise Exception(
            "List of dataset_ids, catalog_item_ids, granule_urs, producer_granule_ids are of uneven length")

    try:
        post_order_items_url = "https://cmr.earthdata.nasa.gov/legacy-services/rest/orders/{}/order_items".format(
            order_id)
        print("POST ADD ORDER ITEMS URL: {}".format(post_order_items_url))

        # make post call
        headers = {'Content-Type': 'application/xml', "Echo-Token": token}

        for i in range(len(producer_granule_ids)):
            if short_names[i] == "AST_L1B":
                body = load_ast_l1b_ecs_options()
            elif short_names[i] == "AST_09T":
                body = load_ast_09t_ecs_options()
            body['order_item']['dataset_id'] = dataset_ids[i]
            body['order_item']['catalog_item_id'] = catalog_item_ids[i]
            body['order_item']['granule_ur'] = granule_urs[i]
            body['order_item']['producer_granule_id'] = producer_granule_ids[i]
            body = xmltodict.unparse(body, pretty=True)

            print("POST ORDER BODY: {}".format(body))

            r = requests.post(url=post_order_items_url,
                              data=body, headers=headers)
            print("POST ORDER RESPONSE: {}".format(r.text))

            if (r.raise_for_status() is None):
                tree = xmltodict.parse(r.text)
                order = tree['order_item']['id']
                print("Order Item ID: {}".format(order))
                # return order

    except:
        raise Exception(
            'unable to add producer_granule_ids to order ID: {}'.format(order_id))


def submit_order(token, order_id):
    '''Submit order to LPDAAC'''
    try:
        post_submit_order_url = "https://cmr.earthdata.nasa.gov/legacy-services/rest/orders/{}/submit".format(
            order_id)
        print("POST SUBMIT ORDER URL: {}".format(post_submit_order_url))

        # make post call
        headers = {"Echo-Token": token}

        r = requests.post(url=post_submit_order_url, headers=headers)
        print("POST SUBMIT ORDER RESPONSE: {}".format(r.text))
        r.raise_for_status()

        if (r.status_code == 204):
            print("successfully placed order for order ID: {}".format(order_id))

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


if __name__ == '__main__':
    main()
