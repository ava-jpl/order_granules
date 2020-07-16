import os
import requests
import json
import socket
import xmltodict
import logging
# from hysds.celery import app
# from hysds_commons.elasticsearch_utils import ElasticsearchUtility


def main():

    # LOG_FILE_NAME = 'order_granules.log'
    # logging.basicConfig(filename=LOG_FILE_NAME,
    #                     filemode='a', level=logging.DEBUG)
    # logger = logging

    # load creds
    creds = load_creds()
    username = creds.get("username", False)
    password = creds.get("password", False)
    client_id = creds.get("client_id", False)
    token = creds.get("user_ip_address", False)
    user_ip_address = creds.get("token", False)
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

    query_granule_ids()


def query_granule_ids():
    # # query for granule ids
    # ctx = load_context()
    # query_obj = ctx['query']
    # try:
    #     query_obj = json.loads(query_obj)
    #     if (query_obj["filtered"]["query"]["bool"]["must"][0]["term"]["dataset.raw"] == "metadata-AST_09T"):
    #         es_index = "grq_v1.0_metadata-ast_09t"
    #     elif (query_obj["filtered"]["query"]["bool"]["must"][0]["term"]["dataset.raw"] == "metadata-AST_L1B"):
    #         es_index = "grq_v1.0_metadata-ast_l1b"
    #     else:
    #         raise Exception(
    #             "Must filter either 'metadata-AST_L1B' or 'metadata-AST_09T' datatsets")
    # except TypeError as e:
    #     logger.warning(e)

    # es_url = app.conf["GRQ_ES_URL"]
    # es = ElasticsearchUtility(es_url, logger=logger)
    # query = {"query": query_obj}

    # results = es.query(es_index, query)  # Querying for products
    # print(results)

    # gather granule metadata from CMR or AVA system
    '''Localizes and ingests product from input metadata blob'''
    # load parameters
    ctx = load_context()
    producer_granule_ids = ctx.get("producer_granule_id", False)
    print(producer_granule_ids)

# generate CMR token


def generate_token(username, password, client_id, user_ip_address):
    ''' Generate a CMR token using credentials. They will last for a month.'''
    try:
        post_token_url = "https://cmr.earthdata.nasa.gov/legacy-services/rest/tokens"
        print("POST TOKEN URL: {}".format(post_token_url))

        # # load creds
        # creds = load_creds()
        # username = creds.get("username", False)
        # password = creds.get("password", False)
        # client_id = creds.get("client_id", False)
        # user_ip_address = creds.get("user_ip_address", False)
        # if (user_ip_address is False):
        #     user_ip_address = socket.gethostbyname(socket.gethostname())

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

        # # load creds
        # creds = load_creds()
        # username = creds.get("username", False)

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


# add granules to order


# submit order


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
        cwd = os.getcwd()
        creds_file = os.path.join(cwd, "conf/creds.json")
        with open(creds_file, 'r') as fin:
            creds = json.load(fin)
        return creds
    except:
        raise Exception('unable to parse conf/creds.json from work directory')


def update_creds(creds):
    '''updates the creds file into a dict'''
    try:
        cwd = os.getcwd()
        creds_file = os.path.join(cwd, "conf/creds.json")
        with open(creds_file, 'w') as fin:
            creds = json.dump(creds, fin)
    except:
        raise Exception('unable to update conf/creds.json from work directory')


if __name__ == '__main__':
    main()
