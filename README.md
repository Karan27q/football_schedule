# Football Match Calendar

A small Flask web app for browsing football match schedules. Loads team schedules from [football-data.org](https://www.football-data.org/) and displays them in a month-based calendar view.

## Features

- Browse available football clubs in a responsive 4-column grid.
- Click a club to view its monthly match schedule in a calendar view.
- Mark matches as "watched" with a simple checkbox.
- Add, edit, or delete local matches manually.
- Integrates with football-data.org API for real team schedules.

## Quick Start

### Prerequisites

- Python 3.10+
- pip
- A football-data.org API token (get one at [https://www.football-data.org/client/register](https://www.football-data.org/client/register))

### Installation

1. **Install dependencies:**

```powershell
python -m pip install -r requirements.txt
```

2. **Set up environment variables:**

```powershell
copy .env.example .env
```

Edit `.env` and fill in:
- `FOOTBALL_DATA_API_TOKEN` — your football-data.org API token
- `SECRET_KEY` — a secure random string (or leave as dev-key for local development)

### Running the App

#### Option A: Flask CLI (Recommended)

```powershell
$env:FLASK_APP = 'app.py'
$env:FOOTBALL_DATA_API_TOKEN = 'your_token_here'
flask run
```

#### Option B: Direct Python

```powershell
python app.py
```

The app will be available at `http://127.0.0.1:5000/`

## Database

The app uses a local SQLite database file named `football_calendar.db`.

### Initialize and Seed the Database

```powershell
flask --app app init-db
flask --app app seed-db
```

- `init-db` — Creates database tables.
- `seed-db` — Adds sample matches for testing.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FOOTBALL_DATA_API_TOKEN` | Yes* | API token for football-data.org. Required to fetch external team schedules. |
| `SECRET_KEY` | No | Flask session/CSRF secret. Defaults to `dev-key` if not set. Set this in production. |
| `FLASK_APP` | No | When using Flask CLI, set to `app.py` (Windows) or `app` (Unix). |

*Only required if you want to load real team schedules from the API; local-only features work without it.

## Project Structure

```
.
├── app.py                 # Flask application (routes, models, API integration)
├── requirements.txt       # Python dependencies
├── .env.example          # Example environment variables (copy to .env)
├── .gitignore            # Git ignore patterns
├── templates/
│   ├── base.html         # Base template with header/nav
│   ├── index.html        # Calendar view
│   └── form.html         # Add/edit match form
├── static/
│   ├── app.js            # Client-side logic (autocomplete, watched toggle, club grid)
│   └── styles.css        # Styles (responsive, club grid, calendar)
└── .github/workflows/
    └── ci.yml            # GitHub Actions CI configuration
```

## Security

- **Never commit `.env`** — it contains secrets. `.gitignore` excludes it by default.
- **Never commit the database file** — `.gitignore` excludes `*.db` by default.
- Keep `SECRET_KEY` confidential in production.

## Development Notes

- The app uses Flask session to persist selected team across page navigation.
- Client-side JavaScript handles team search autocomplete (debounced 250ms) and match "watched" toggles.
- The `/clubs/popular` endpoint fetches team listings from the upstream API.
- Date/time parsing uses `python-dateutil` to handle API timestamps flexibly.

## License

MIT (
