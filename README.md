# ShotTrack LineBot

LINE Bot backend for vaccine schedule reminders.

## Setup

1. Create a virtual environment and install dependencies:

```bash
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill in your API keys.

3. Run Flask locally:

```bash
venv/bin/flask --app app run --host 127.0.0.1 --port 5001
```

4. Start ngrok:

```bash
ngrok http 5001
```

5. Set the LINE Developers webhook URL to:

```text
https://your-ngrok-url/callback
```
