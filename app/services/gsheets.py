"""Shared Google Sheets access.

Credentials come from either:
  GOOGLE_CREDENTIALS_JSON  — the raw service-account JSON (recommended on Railway)
  GOOGLE_CREDENTIALS_PATH  — path to the JSON file (local dev)
"""
import json
import os
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly',
]


def get_client():
    raw = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    if raw:
        info = json.loads(raw)
    else:
        path = os.environ.get('GOOGLE_CREDENTIALS_PATH')
        if not path:
            raise RuntimeError(
                'Google credentials are not configured: set GOOGLE_CREDENTIALS_JSON '
                'or GOOGLE_CREDENTIALS_PATH')
        with open(path) as f:
            info = json.load(f)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)
