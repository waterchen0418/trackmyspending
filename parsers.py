import re
from datetime import datetime


def parse_bank_notification(text):
    for parser in [parse_taishin, parse_cathay, parse_esun]:
        result = parser(text)
        if result:
            return result
    return None


def _roc_to_ad(year_str):
    y = int(year_str)
    return str(y + 1911) if y < 1000 else str(y)


def _extract_date_time(text):
    # 民國年 113/05/09 12:34 or 113-05-09 12:34
    m = re.search(r'(\d{3})[/\-](\d{1,2})[/\-](\d{1,2})\s+(\d{1,2}):(\d{2})', text)
    if m:
        return f"{_roc_to_ad(m.group(1))}/{m.group(2).zfill(2)}/{m.group(3).zfill(2)}", f"{m.group(4)}:{m.group(5)}"

    # 西元年 2024/05/09 12:34
    m = re.search(r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})\s+(\d{1,2}):(\d{2})', text)
    if m:
        return f"{m.group(1)}/{m.group(2).zfill(2)}/{m.group(3).zfill(2)}", f"{m.group(4)}:{m.group(5)}"

    # 113年05月09日 12:34
    m = re.search(r'(\d{2,3})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})', text)
    if m:
        return f"{_roc_to_ad(m.group(1))}/{m.group(2).zfill(2)}/{m.group(3).zfill(2)}", f"{m.group(4)}:{m.group(5)}"

    # MM/DD HH:MM (no year)
    m = re.search(r'(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})', text)
    if m:
        year = datetime.now().strftime('%Y')
        return f"{year}/{m.group(1).zfill(2)}/{m.group(2).zfill(2)}", f"{m.group(3)}:{m.group(4)}"

    now = datetime.now()
    return now.strftime('%Y/%m/%d'), now.strftime('%H:%M')


def parse_taishin(text):
    if '台新' not in text:
        return None

    amount_m = re.search(r'消費金額[：:]\s*(?:TWD|NTD|NT\$?)?\s*([\d,]+)', text)
    if not amount_m:
        return None

    merchant_m = re.search(r'(?:消費商店|消費地點|商店名稱)[：:]\s*(.+?)(?:\n|$)', text)
    date_str, time_str = _extract_date_time(text)

    return {
        'date': date_str,
        'time': time_str,
        'amount': int(amount_m.group(1).replace(',', '')),
        'merchant': merchant_m.group(1).strip() if merchant_m else '未知商家',
        'source': '台新',
        'note': '',
    }


def parse_cathay(text):
    if '國泰' not in text:
        return None

    amount_m = re.search(r'消費\s*\$?([\d,]+)', text)
    if not amount_m:
        amount_m = re.search(r'\$([\d,]+)\s*元', text)
    if not amount_m:
        amount_m = re.search(r'NT\$\s*([\d,]+)', text)
    if not amount_m:
        return None

    merchant_m = re.search(r'(?:地點|商店|特店)[：:\s]*(.+?)(?:\n|$)', text)
    date_str, time_str = _extract_date_time(text)

    return {
        'date': date_str,
        'time': time_str,
        'amount': int(amount_m.group(1).replace(',', '')),
        'merchant': merchant_m.group(1).strip() if merchant_m else '未知商家',
        'source': '國泰',
        'note': '',
    }


def parse_esun(text):
    if '玉山' not in text:
        return None

    amount_m = re.search(r'消費金額[：:]\s*\$?([\d,]+)', text)
    if not amount_m:
        return None

    merchant_m = re.search(r'(?:消費商店|商店名稱)[：:]\s*(.+?)(?:\n|$)', text)
    date_str, time_str = _extract_date_time(text)

    return {
        'date': date_str,
        'time': time_str,
        'amount': int(amount_m.group(1).replace(',', '')),
        'merchant': merchant_m.group(1).strip() if merchant_m else '未知商家',
        'source': '玉山',
        'note': '',
    }


def parse_manual_input(text):
    # 支援格式：
    #   商家 金額            → 全聯 350
    #   商家 金額 備註       → 星巴克 180 拿鐵
    #   金額 商家            → 350 全聯
    text = text.strip()

    # 商家 金額 [備註]
    m = re.match(r'^([^\d\s].+?)\s+([\d,]+)(?:\s+(.+))?$', text)
    if m:
        merchant = m.group(1).strip()
        try:
            return {
                'date': datetime.now().strftime('%Y/%m/%d'),
                'time': datetime.now().strftime('%H:%M'),
                'amount': int(m.group(2).replace(',', '')),
                'merchant': merchant,
                'source': '手動',
                'note': m.group(3).strip() if m.group(3) else '',
            }
        except ValueError:
            pass

    # 金額 商家
    m = re.match(r'^([\d,]+)\s+(.+)$', text)
    if m:
        try:
            return {
                'date': datetime.now().strftime('%Y/%m/%d'),
                'time': datetime.now().strftime('%H:%M'),
                'amount': int(m.group(1).replace(',', '')),
                'merchant': m.group(2).strip(),
                'source': '手動',
                'note': '',
            }
        except ValueError:
            pass

    return None
