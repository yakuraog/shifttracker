"""gspread client factory for Google Sheets integration."""
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def build_client(credentials_file: str) -> gspread.Client:
    """Build a synchronous gspread client from a service account JSON file.

    Args:
        credentials_file: Path to the service account JSON key file.

    Returns:
        An authenticated gspread.Client instance.
    """
    creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
    return gspread.authorize(creds)
