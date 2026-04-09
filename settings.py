import streamlit as st
from google.oauth2 import service_account
from google.cloud import bigquery
from google.cloud import secretmanager
import pandas as pd
import datetime as dt
import json
import logging


default_daterange = [dt.datetime(2021, 1, 1).date(), dt.date.today()]


@st.cache_resource(ttl="1d")
def get_logger(name="dashboard_logger"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
    return logger


@st.cache_resource(ttl="1d")
def get_gcp_credentials():
    client = secretmanager.SecretManagerServiceClient()
    name = "projects/405806232197/secrets/service_account_json/versions/latest"
    response = client.access_secret_version(name=name)
    key = response.payload.data.decode("UTF-8")

    service_account_info = json.loads(key)
    gcp_credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=[
            "https://www.googleapis.com/auth/cloud-platform",
            "https://www.googleapis.com/auth/devstorage.read_only",
            "https://www.googleapis.com/auth/bigquery",
            "https://www.googleapis.com/auth/drive",
        ],
    )

    bq_client = bigquery.Client(
        credentials=gcp_credentials, project="dataexploration-193817"
    )

    return gcp_credentials, bq_client


def initialize():
    pd.options.mode.copy_on_write = True
    pd.set_option("display.max_columns", 20)
