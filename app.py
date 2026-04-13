from flask import Flask, request, jsonify, render_template, session
import re
import json
import zipfile
import io
import os
from datetime import datetime
from collections import defaultdict
import uuid

app = Flask(__name__)
app.secret_key = os.urandom(24)

SESSIONS = {}

WHATSAPP_PATTERNS = [
    r'(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[aApP][mM])?)\s*-\s*([^:]+?):\s*(.*)',
    r'(\d{1,2}-\d{1,2}-\d{2,4}),\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[aApP][mM])?)\s*-\s*([^:]+?):\s*(.*)',
    r'\[(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[aApP][mM])?)\]\s*([^:]+?):\s*(.*)',
]

def parse_datetime(date_str, time_str):
    date_str = date_str.strip()
    time_str = time_str.strip()
    formats = [
        ('%d/%m/%Y', '%I:%M %p'), ('%d/%m/%Y', '%I:%M:%S %p'),
        ('%d/%m/%Y', '%H:%M'), ('%d/%m/%Y', '%H:%M:%S'),
        ('%m/%d/%Y', '%I:%M %p'), ('%m/%d/%Y', '%H:%M'),
        ('%d/%m/%y', '%I:%M %p'), ('%d/%m/%y', '%H:%M'),
        ('%m/%d/%y', '%I:%M %p'), ('%m/%d/%y', '%H:%M'),
        ('%d-%m-%Y', '%H:%M'), ('%d-%m-%y', '%H:%M'),
    ]
    time_str_clean = re.sub(r'\s+', ' ', time_str).upper().strip()
    for dfmt, tfmt in formats:
        try:
            dt = datetime.strptime(f"{date_str} {time_str_clean}", f"{dfmt} {tfmt}")
            return dt
        except:
            pass
    return None

def parse_whatsapp(text):
    messages = []
    lines = text.splitlines()
    current = None
    pattern = None
    for p in WHATSAPP_PATTERNS:
        for line in lines[:20]:
            if re.match(p, line):
                pattern = re.compile(p)
                break
        if pattern:
            break
    if not pattern:
        pattern = re.compile(WHATSAPP_PATTERNS[0])

    for line in lines:
        m = pattern.match(line)
        if m:
            if current:
                messages.append(current)
            date_s, time_s, sender, body = m.group(1), m.group(2), m.group(3).strip(), m.group(4).strip()
            dt = parse_datetime(date_s, time_s)
            is_media = body in ('<Media omitted>', '<image omitted>', '<video omitted>', '<audio omitted>', '<document omitted>', '<sticker omitted>') or body.endswith('.jpg') or body.endswith('.mp4')
            current = {
                'id': len(messages),
                'timestamp': dt.isoformat() if dt else None,
                'date': dt.strftime('%Y-%m-%d') if dt else None,
                'hour': dt.hour if dt else None,
                'weekday': dt.strftime('%A') if dt else None,
                'month': dt.strftime('%Y-%m') if dt else None,
                'sender': sender,
                'body': body,
                'is_media': is_media,
                'is_system': False,
            }
        else:
            if line.strip() and current:
                current['body'] += '\n' + line.strip()
            elif line.strip() and not current:
                current = {
                    'id': len(messages),
                    'timestamp': None, 'date': None, 'hour': None,
                    'weekday': None, 'month': None,
                    'sender': 'System', 'body': line.strip(),
                    'is_media': False, 'is_system': True,
                }
    if current:
        messages.append(current)
    return [m for m in messages if not m['is_system']]

def parse_telegram(data):
    messages = []
    for msg in data.get('messages', []):
        if msg.get('type') != 'message':
            continue
        text = msg.get('text', '')
        if isinstance(text, list):
            text = ''.join(p if isinstance(p, str) else p.get('text', '') for p in text)
        dt_str = msg.get('date', '')
        try:
            dt = datetime.fromisoformat(dt_str)
        except:
            dt = None
        is_media = bool(msg.get('photo') or msg.get('file') or msg.get('media_type'))
        messages.append({
            'id': msg.get('id', len(messages)),
            'timestamp': dt.isoformat() if dt else None,
            'date': dt.strftime('%Y-%m-%d') if dt else None,
            'hour': dt.hour if dt else None,
            'weekday': dt.strftime('%A') if dt else None,
            'month': dt.strftime('%Y-%m') if dt else None,
            'sender': msg.get('from', 'Unknown'),
            'body': text,
            'is_media': is_media,
            'is_system': False,
        })
    return messages

def compute_stats(messages):
    senders = defaultdict(int)
    by_date = defaultdict(int)
    by_hour = defaultdict(int)
    by_weekday = defaultdict(int)
    by_month = defaultdict(int)
    media_count = 0

    for m in messages:
        senders[m['sender']] += 1
        if m['date']:
            by_date[m['date']] += 1
        if m['hour'] is not None:
            by_hour[str(m['hour'])] += 1
        if m['weekday']:
            by_weekday[m['weekday']] += 1
        if m['month']:
            by_month[m['month']] += 1
        if m['is_media']:
            media_count += 1

    weekday_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    return {
        'total': len(messages),
        'media_count': media_count,
        'senders': dict(sorted(senders.items(), key=lambda x: -x[1])),
        'by_date': dict(sorted(by_date.items())),
        'by_hour': {str(h): by_hour.get(str(h), 0) for h in range(24)},
        'by_weekday': {d: by_weekday.get(d, 0) for d in weekday_order},
        'by_month': dict(sorted(by_month.items())),
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    f = request.files['file']
    filename = f.filename.lower()
    messages = []

    try:
        if filename.endswith('.zip'):
            zf = zipfile.ZipFile(io.BytesIO(f.read()))
            for name in zf.namelist():
                if name.endswith('.txt'):
                    text = zf.read(name).decode('utf-8', errors='ignore')
                    messages = parse_whatsapp(text)
                    break
                elif name.endswith('.json'):
                    data = json.loads(zf.read(name).decode('utf-8', errors='ignore'))
                    messages = parse_telegram(data)
                    break
        elif filename.endswith('.txt'):
            text = f.read().decode('utf-8', errors='ignore')
            messages = parse_whatsapp(text)
        elif filename.endswith('.json'):
            data = json.load(f)
            messages = parse_telegram(data)
        else:
            return jsonify({'error': 'Unsupported file type'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    if not messages:
        return jsonify({'error': 'No messages found. Make sure the file is a valid WhatsApp or Telegram export.'}), 400

    sid = str(uuid.uuid4())
    SESSIONS[sid] = messages
    stats = compute_stats(messages)
    senders = list(stats['senders'].keys())
    return jsonify({'session_id': sid, 'stats': stats, 'senders': senders, 'total': len(messages)})

@app.route('/api/messages', methods=['GET'])
def get_messages():
    sid = request.args.get('session_id')
    if not sid or sid not in SESSIONS:
        return jsonify({'error': 'Session not found'}), 404
    messages = SESSIONS[sid]
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    search = request.args.get('search', '').lower()
    sender = request.args.get('sender', '')
    filtered = messages
    if search:
        filtered = [m for m in filtered if search in m['body'].lower()]
    if sender:
        filtered = [m for m in filtered if m['sender'] == sender]
    total = len(filtered)
    start = (page - 1) * per_page
    end = start + per_page
    return jsonify({
        'messages': filtered[start:end],
        'total': total,
        'page': page,
        'pages': (total + per_page - 1) // per_page,
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    sid = request.args.get('session_id')
    if not sid or sid not in SESSIONS:
        return jsonify({'error': 'Session not found'}), 404
    return jsonify(compute_stats(SESSIONS[sid]))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
