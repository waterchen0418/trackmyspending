import os
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient, Configuration, MessagingApi, ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from parsers import parse_bank_notification, parse_manual_input
from sheets import append_transaction, get_monthly_summary

app = Flask(__name__)

configuration = Configuration(access_token=os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])

HELP_TEXT = """\
📖 使用說明

【手動記帳】
  商家 金額          → 全聯 350
  商家 金額 備註     → 星巴克 180 拿鐵
  金額 商家          → 350 全聯

【轉傳銀行通知】
  直接將台新／國泰／玉山的 LINE 消費通知轉傳給我即可

【查詢本月報表】
  輸入「報表」查看本月支出統計"""


def build_reply(transaction: dict) -> str:
    source_emoji = {'台新': '🟠', '國泰': '🔵', '玉山': '🟡', '手動': '✏️'}.get(transaction['source'], '💳')
    lines = [
        f"✅ 記帳成功！",
        f"📅 {transaction['date']} {transaction['time']}",
        f"💰 ${transaction['amount']:,}",
        f"🏪 {transaction['merchant']}",
        f"{source_emoji} {transaction['source']}",
    ]
    if transaction.get('note'):
        lines.append(f"📝 {transaction['note']}")
    return '\n'.join(lines)


def build_summary_reply(year: str, month: str) -> str:
    data = get_monthly_summary(year, month)
    total = data['total']
    by_source = data['by_source']

    lines = [f"📊 {year}年{month}月支出報表", f"{'─' * 18}", f"💰 總計：${total:,}"]
    if by_source:
        lines.append('')
        lines.append('各銀行：')
        for source, amount in sorted(by_source.items()):
            lines.append(f"  • {source}：${amount:,}")
    return '\n'.join(lines)


def reply_text(reply_token: str, text: str):
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=text)]
                )
            )
    except Exception as e:
        print(f'[reply error] {e}')


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

    if text in ('報表', '本月報表', '統計'):
        now = datetime.now()
        reply = build_summary_reply(str(now.year), str(now.month))
        reply_text(event.reply_token, reply)
        return

    if text in ('說明', '幫助', 'help', '?', '？'):
        reply_text(event.reply_token, HELP_TEXT)
        return

    transaction = parse_bank_notification(text)
    if not transaction:
        transaction = parse_manual_input(text)

    if transaction:
        success = append_transaction(transaction)
        msg = build_reply(transaction) if success else '❌ 記帳失敗，請稍後再試'
    else:
        msg = '❓ 無法辨識格式\n\n輸入「說明」查看使用方式'

    reply_text(event.reply_token, msg)


if __name__ == '__main__':
    app.run(port=8080, debug=True)
