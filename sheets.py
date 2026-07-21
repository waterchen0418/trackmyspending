import os
import json
import base64
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

SPREADSHEET_ID = os.environ['GOOGLE_SPREADSHEET_ID']
SHEET_NAME = '記帳'
MEMORY_SHEET_NAME = '商家記憶'
CATEGORY_SHEET_NAME = '自訂分類'
HEADERS = ['日期', '時間', '金額', '商家', '來源', '分類', '備註']


def _get_client():
    google_creds = os.environ.get('GOOGLE_CREDENTIALS')
    if google_creds:
        # 支援 base64 編碼或純 JSON
        try:
            decoded = base64.b64decode(google_creds).decode('utf-8')
            info = json.loads(decoded)
        except Exception:
            info = json.loads(google_creds)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
    return gspread.authorize(creds)


def _get_sheet():
    spreadsheet = _get_client().open_by_key(SPREADSHEET_ID)
    try:
        sheet = spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=5000, cols=10)
        sheet.append_row(HEADERS)
        sheet.freeze(rows=1)
    return sheet


def _get_memory_sheet():
    spreadsheet = _get_client().open_by_key(SPREADSHEET_ID)
    try:
        sheet = spreadsheet.worksheet(MEMORY_SHEET_NAME)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=MEMORY_SHEET_NAME, rows=1000, cols=2)
        sheet.append_row(['商家', '分類'])
        sheet.freeze(rows=1)
    return sheet


def _get_category_sheet():
    spreadsheet = _get_client().open_by_key(SPREADSHEET_ID)
    try:
        sheet = spreadsheet.worksheet(CATEGORY_SHEET_NAME)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=CATEGORY_SHEET_NAME, rows=100, cols=1)
        sheet.append_row(['分類'])
        sheet.freeze(rows=1)
    return sheet


def get_custom_categories() -> list[str]:
    """從 Sheets 取得自訂分類清單"""
    try:
        sheet = _get_category_sheet()
        records = sheet.get_all_records()
        return [row['分類'] for row in records if row.get('分類')]
    except Exception as e:
        print(f'[sheets] get_custom_categories error: {e}')
    return []


def add_custom_category(category: str) -> bool:
    """新增自訂分類"""
    try:
        sheet = _get_category_sheet()
        records = sheet.get_all_records()
        if any(row.get('分類') == category for row in records):
            return False  # 已存在
        sheet.append_row([category])
        return True
    except Exception as e:
        print(f'[sheets] add_custom_category error: {e}')
    return False


def delete_custom_category(category: str) -> bool:
    """刪除自訂分類"""
    try:
        sheet = _get_category_sheet()
        records = sheet.get_all_records()
        for i, row in enumerate(records, start=2):
            if row.get('分類') == category:
                sheet.delete_rows(i)
                return True
    except Exception as e:
        print(f'[sheets] delete_custom_category error: {e}')
    return False


def get_merchant_category(merchant: str) -> str | None:
    """查詢商家的記憶分類，找不到回傳 None"""
    try:
        sheet = _get_memory_sheet()
        records = sheet.get_all_records()
        for row in records:
            if row.get('商家') == merchant:
                return row.get('分類')
    except Exception as e:
        print(f'[sheets] get_merchant_category error: {e}')
    return None


def save_merchant_category(merchant: str, category: str) -> None:
    """儲存或更新商家分類記憶"""
    try:
        sheet = _get_memory_sheet()
        records = sheet.get_all_records()
        for i, row in enumerate(records, start=2):
            if row.get('商家') == merchant:
                sheet.update_cell(i, 2, category)
                return
        sheet.append_row([merchant, category])
    except Exception as e:
        print(f'[sheets] save_merchant_category error: {e}')


def append_transaction(transaction: dict) -> bool:
    try:
        sheet = _get_sheet()
        sheet.append_row([
            transaction['date'],
            transaction['time'],
            transaction['amount'],
            transaction['merchant'],
            transaction['source'],
            transaction.get('category', ''),
            transaction.get('note', ''),
        ])
        return True
    except Exception as e:
        print(f'[sheets] append error: {e}')
        return False


def get_last_transaction() -> dict | None:
    """回傳最後一筆記帳資料"""
    try:
        sheet = _get_sheet()
        rows = sheet.get_all_records()
        return rows[-1] if rows else None
    except Exception as e:
        print(f'[sheets] get_last error: {e}')
    return None


def delete_last_transaction() -> bool:
    """刪除最後一筆記帳"""
    try:
        sheet = _get_sheet()
        last_row = len(sheet.get_all_values())
        if last_row <= 1:
            return False
        sheet.delete_rows(last_row)
        return True
    except Exception as e:
        print(f'[sheets] delete_last error: {e}')
    return False


def get_monthly_summary(year: str, month: str) -> dict:
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
