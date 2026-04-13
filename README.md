# ChatArchive

Browse your WhatsApp and Telegram chats beautifully — search messages, filter by person, visualize activity over time.

## Setup

```bash
pip install flask
python app.py
```

Then open http://localhost:5000

## Supported formats

- **WhatsApp**: Export any chat → ⋮ → More → Export Chat → Without Media → upload the `.zip` or `.txt`
- **Telegram**: Desktop app → Settings → Export Telegram Data → Machine-readable JSON → upload `result.json`

## Features

- Browse all messages with pagination
- Search across all messages
- Filter by person
- Stats: total messages, media count, active days, average per day
- Charts: messages by hour, by month, by day of week
- Per-person message breakdown with percentage bars
- Activity heatmap (one cell per day)

## Stack

- Flask (backend + parsing)
- Vanilla JS + Chart.js (frontend)
- No database required — parsed data lives in memory per session

