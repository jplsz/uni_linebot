import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Googleシート用の共通関数
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    raw_cred = os.environ.get("GOOGLE_CREDENTIALS_JSON")

    if raw_cred is None:
        raise Exception("GOOGLE_CREDENTIALS_JSON is not set")

    creds_dict = json.loads(raw_cred)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# Google Sheets接続設定
def get_sheet(sheet_name="達成記録"):
    # スプレッドシートの名前を指定
    client = get_gspread_client()
    return client.open("UniQuest_DB").worksheet(sheet_name)

def get_emotion_sheet():
    client = get_gspread_client()
    return client.open("UniQuest_DB").worksheet("感情ログ")

def append_row_to_sheet(sheet_name, row_values):
    sheet = get_sheet(sheet_name)
    sheet.append_row(row_values)