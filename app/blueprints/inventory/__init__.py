import os
import json
import requests
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
import gspread
from google.oauth2.service_account import Credentials

inventory = Blueprint('inventory', __name__, url_prefix='/inventory',
                      template_folder='../../app/templates/inventory')

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def get_gc():
    with open(os.environ["GOOGLE_CREDENTIALS_PATH"]) as f:
        creds_info = json.load(f)
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    return gspread.authorize(creds)

def get_spreadsheet():
    return get_gc().open_by_key(os.environ["SPREADSHEET_ID"])

def get_inventory_rows():
    ws = get_spreadsheet().worksheet(os.environ.get("SHEET_NAME", "Остатки по базам"))
    rows = ws.get_all_records()
    return rows

def get_sheet_rows(sheet_name):
    ws = get_spreadsheet().worksheet(sheet_name)
    rows = ws.get_all_values()
    if not rows:
        return []
    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:]]

@inventory.route('/')
@login_required
def index():
    query = request.args.get('q', '').strip().lower()
    rows = get_inventory_rows()
    if query:
        rows = [r for r in rows if query in str(r).lower()]
    return render_template('inventory/index.html', rows=rows, query=query)

@inventory.route('/chat', methods=['POST'])
@login_required
def chat():
    user_message = request.json.get('message', '').strip()
    if not user_message:
        return jsonify({'error': 'No message'}), 400

    lang = getattr(current_user, 'language', 'ru')

    # Load all relevant sheet data
    stock_rows = get_inventory_rows()
    receipts = get_sheet_rows('Поступления')
    usage = get_sheet_rows('Использование')

    lang_instruction = {
        'ru': 'Отвечай на русском языке.',
        'en': 'Reply in English.',
        'kz': 'Қазақ тілінде жауап бер.',
    }.get(lang, 'Reply in Russian.')

    system_prompt = f"""You are an inventory assistant for CIS Platform, a chemical inventory management system.
{lang_instruction}

You have access to the following data:

CURRENT STOCK (Остатки по базам):
{json.dumps(stock_rows[:100], ensure_ascii=False)}

RESTOCKING HISTORY (Поступления) - last 100 entries:
{json.dumps(receipts[-100:], ensure_ascii=False)}

USAGE HISTORY (Использование) - last 100 entries:
{json.dumps(usage[-100:], ensure_ascii=False)}

Answer questions about stock levels, which materials are running low, usage history, restocking dates, and trends.
Be concise and helpful. Use the actual data to give specific answers."""

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': os.environ.get('ANTHROPIC_API_KEY', ''),
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        },
        json={
            'model': 'claude-sonnet-4-6',
            'max_tokens': 1024,
            'system': system_prompt,
            'messages': [{'role': 'user', 'content': user_message}],
        }
    )

    data = response.json()
    reply = data['content'][0]['text']
    return jsonify({'reply': reply})