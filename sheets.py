import os
import json
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

SPREADSHEET_ID = os.environ['GOOGLE_SPREADSHEET_ID']
SHEET_NAME = '記帳'
HEADERS = ['日期', '時間', '金額', '商家', '來源', '分類', '備註']


def _get_sheet():
    # 優先從環境變數讀取（Railway），否則讀本地檔案（開發環境）
    google_creds = os.environ.get('GOOGLE_CREDENTIALS')
    if google_creds:
        creds = Credentials.from_service_account_info(json.loads(google_creds), scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    try:
        sheet = spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=5000, cols=10)
        sheet.append_row(HEADERS)
        # 凍結標題列
        sheet.freeze(rows=1)

    return sheet


def append_transaction(transaction: dict) -> bool:
    try:
        sheet = _get_sheet()
        sheet.append_row([
            transaction['date'],
            transaction['time'],
            transaction['amount'],
            transaction['merchant'],
            transaction['source'],
            '',
            transaction.get('note', ''),
        ])
        return True
    except Exception as e:
        print(f'[sheets] append error: {e}')
        return False


def get_monthly_summary(year: str, month: str) -> dict:
    """回傳指定月份的總支出、各類別小計、各來源小計"""
    try:
        sheet = _get_sheet()
        rows = sheet.get_all_records()
        prefix = f"{year}/{month.zfill(2)}"

        total = 0
        by_source = {}
        by_category = {}
        for row in rows:
            if str(row.get('日期', '')).startswith(prefix):
                amount = int(row.get('金額', 0))
                source = row.get('來源', '其他')
                category = row.get('分類') or '📦 其他'
                total += amount
                by_source[source] = by_source.get(source, 0) + amount
                by_category[category] = by_category.get(category, 0) + amount

        return {'total': total, 'by_source': by_source, 'by_category': by_category}
    except Exception as e:
        print(f'[sheets] summary error: {e}')
        return {'total': 0, 'by_source': {}, 'by_category': {}}
