import os
import re
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient, Configuration, MessagingApi,
    ReplyMessageRequest, TextMessage,
    QuickReply, QuickReplyItem, MessageAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from parsers import parse_bank_notification, parse_manual_input
from sheets import append_transaction, get_monthly_summary, get_merchant_category, save_merchant_category, get_last_transaction, delete_last_transaction

app = Flask(__name__)

configuration = Configuration(access_token=os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])

CATEGORIES = [
    '🍽️ 餐飲',
    '🧋 飲料',
    '🛒 生活用品',
    '👕 購物',
    '🚗 交通',
    '🏋️ 運動',
    '🎉 社交',
    '🎮 娛樂',
    '🏥 醫療',
    '💻 訂閱/軟體',
    '📦 其他',
]

# 暫存等待分類的交易，key = user_id
pending: dict = {}
# 暫存等待確認刪除，key = user_id
confirm_delete: set = set()

HELP_TEXT = """\
📖 使用說明

【手動記帳】
  商家 金額          → 全聯 350
  商家 金額 備註     → 星巴克 180 拿鐵
  金額 商家          → 350 全聯

【轉傳銀行通知】
  直接將台新／國泰／玉山的 LINE 消費通知轉傳給我即可

【查詢本月報表】
  輸入「報表」查看本月支出統計

【刪除最後一筆】
  輸入「刪除」刪除最後一筆記帳"""


def build_success_reply(transaction: dict) -> str:
    source_emoji = {'台新': '🟠', '國泰': '🔵', '玉山': '🟡', '手動': '✏️'}.get(transaction['source'], '💳')
    category = transaction.get('category', '')
    lines = [
        '✅ 記帳成功！',
        f"📅 {transaction['date']} {transaction['time']}",
        f"💰 ${transaction['amount']:,}",
        f"🏪 {transaction['merchant']}",
        f"{source_emoji} {transaction['source']}",
    ]
    if category:
        lines.append(f"🏷️ {category}")
    if transaction.get('note'):
        lines.append(f"📝 {transaction['note']}")
    return '\n'.join(lines)


def build_summary_reply(year: str, month: str) -> str:
    data = get_monthly_summary(year, month)
    total = data['total']
    by_category = data.get('by_category', {})
    by_source = data.get('by_source', {})

    lines = [f"📊 {year}年{month}月支出報表", '─' * 18, f"💰 總計：${total:,}"]

    if by_category:
        lines.append('')
        lines.append('各類別：')
        for cat, amount in sorted(by_category.items(), key=lambda x: -x[1]):
            lines.append(f"  {cat}：${amount:,}")

    if by_source:
        lines.append('')
        lines.append('各銀行：')
        for source, amount in sorted(by_source.items()):
            lines.append(f"  • {source}：${amount:,}")

    return '\n'.join(lines)


def reply_text(reply_token: str, text: str, quick_reply: QuickReply = None):
    try:
        msg = TextMessage(text=text)
        if quick_reply:
            msg.quick_reply = quick_reply
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=reply_token, messages=[msg])
            )
    except Exception as e:
        print(f'[reply error] {e}')


def ask_category(reply_token: str, merchant: str):
    qr = QuickReply(items=[
        QuickReplyItem(action=MessageAction(label=cat, text=cat))
        for cat in CATEGORIES
    ])
    reply_text(reply_token, f'「{merchant}」請選擇分類：', quick_reply=qr)


@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception:
        pass
    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id

    # 確認刪除
    if user_id in confirm_delete:
        confirm_delete.discard(user_id)
        if text == '✅ 確認刪除':
            success = delete_last_transaction()
            reply_text(event.reply_token, '🗑️ 已刪除最後一筆記錄' if success else '❌ 刪除失敗')
        else:
            reply_text(event.reply_token, '取消刪除')
        return

    # 刪除最後一筆
    if text in ('刪除', '刪除最後一筆'):
        last = get_last_transaction()
        if not last:
            reply_text(event.reply_token, '❌ 找不到任何記錄')
            return
        confirm_delete.add(user_id)
        qr = QuickReply(items=[
            QuickReplyItem(action=MessageAction(label='✅ 確認刪除', text='✅ 確認刪除')),
            QuickReplyItem(action=MessageAction(label='❌ 取消', text='❌ 取消')),
        ])
        msg = f"確定要刪除最後一筆？\n📅 {last['日期']} {last['時間']}\n💰 ${int(last['金額']):,}\n🏪 {last['商家']}"
        reply_text(event.reply_token, msg, quick_reply=qr)
        return

    # 使用者點選了分類按鈕
    if text in CATEGORIES and user_id in pending:
        transaction = pending.pop(user_id)
        transaction['category'] = text
        save_merchant_category(transaction['merchant'], text)
        success = append_transaction(transaction)
        msg = build_success_reply(transaction) if success else '❌ 記帳失敗，請稍後再試'
        reply_text(event.reply_token, msg)
        return

    if text in ('報表', '本月報表', '統計', '月結', '總結', '本月總結', '本月消費'):
        now = datetime.now()
        reply = build_summary_reply(str(now.year), str(now.month))
        reply_text(event.reply_token, reply)
        return

    # 上個月
    if text in ('上個月', '上月', '上月報表', '上個月報表'):
        now = datetime.now()
        if now.month == 1:
            year, month = str(now.year - 1), '12'
        else:
            year, month = str(now.year), str(now.month - 1)
        reply = build_summary_reply(year, month)
        reply_text(event.reply_token, reply)
        return

    # 指定月份：4月、4月報表、2026年4月、2026/4
    month_match = re.search(r'(?:(\d{4})[年/])?(\d{1,2})月', text)
    if month_match and any(kw in text for kw in ('月', '報表', '統計', '消費', '總結')):
        now = datetime.now()
        year = month_match.group(1) or str(now.year)
        month = month_match.group(2)
        reply = build_summary_reply(year, month)
        reply_text(event.reply_token, reply)
        return

    if text in ('說明', '幫助', 'help', '?', '？'):
        reply_text(event.reply_token, HELP_TEXT)
        return

    transaction = parse_bank_notification(text)
    if not transaction:
        transaction = parse_manual_input(text)

    if transaction:
        remembered = get_merchant_category(transaction['merchant'])
        if remembered:
            transaction['category'] = remembered
            success = append_transaction(transaction)
            msg = build_success_reply(transaction) if success else '❌ 記帳失敗，請稍後再試'
            reply_text(event.reply_token, msg)
        else:
            pending[user_id] = transaction
            ask_category(event.reply_token, transaction['merchant'])
    else:
        reply_text(event.reply_token, '❓ 無法辨識格式\n\n輸入「說明」查看使用方式')


if __name__ == '__main__':
    app.run(port=8080, debug=True)
