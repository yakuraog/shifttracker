"""gspread client factory for Google Sheets integration."""
import json

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def build_client(credentials_file: str = "", credentials_json: str = "") -> gspread.Client:
    """Build a synchronous gspread client from a service account.

    Supports two modes:
    - credentials_file: path to JSON key file (local dev)
    - credentials_json: raw JSON string (Render / cloud deploy)

    Returns:
        An authenticated gspread.Client instance.
    """
    if credentials_json:
        info = json.loads(credentials_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    elif credentials_file:
        creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
    else:
        raise ValueError("No credentials provided")
    return gspread.authorize(creds)
