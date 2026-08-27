# ⚽ Football Match Calendar & Fixture Tracker

A modern, high-performance web application built with **Flask**, **SQLite**, and **Football-Data API** to discover, track, and manage football match schedules. Features a dark cyber-sports UI theme, intelligent API caching, instant offline demo mode, watched match metrics, and iCalendar (.ics) exports.

---

## ✨ Features

- **🏆 Dark Sports UI**: Built with glassmorphism surface styling, responsive grid layouts, custom badges, and Google Fonts (`Inter` & `Outfit`).
- **⚡ Instant Demo Mode**: Seamless offline fallback with pre-populated realistic fixtures for top European clubs (Arsenal, Real Madrid, Barcelona, Man City, Bayern, PSG) without needing an API token.
- **🚀 API TTL Caching Layer**: In-memory `TTLCache` prevents upstream 429 rate limits and delivers sub-5ms match response times.
- **📅 Multiple View Modes**:
  - **Calendar Grid**: Interactive monthly calendar with day cells and match cards.
  - **Fixture List**: Chronological card list with kickoff times and team badges.
  - **Stats Overview**: Watched match metrics and competition progress tracking.
- **🔍 Live Search & Filter**: Instant client-side filtering by competition and opponent name.
- **📥 iCalendar (.ics) Export**: One-click calendar download to sync fixtures directly with Apple Calendar, Google Calendar, or Outlook.
- **➕ Custom Fixtures**: Add, edit, or delete custom manual matches stored in SQLite.
- **🧪 100% Test Coverage**: Full Pytest unit and integration test suite.
- **🐳 Docker Ready**: Multi-stage `Dockerfile` and `docker-compose.yml` included.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.10+, Flask 3.0, Flask-SQLAlchemy, requests, python-dateutil
- **Database**: SQLite
- **Frontend**: HTML5, Vanilla CSS3 (Custom Properties & Glassmorphism), JavaScript (ES6+)
- **Testing & Tooling**: Pytest, Pytest-Cov, Flake8
- **CI/CD**: GitHub Actions (Python 3.10-3.12 matrix test suite)

---

## 🚀 Quick Start

### 1. Local Setup

```bash
# Clone the repository
cd football_schedule

# Install dependencies
pip install -r requirements.txt

# Run the Flask development server
python app.py
```

Open your browser at `http://127.0.0.1:5000`.

---

### 2. Environment Configuration (Optional)

To enable live football API match fetching, set your API token in a `.env` file or environment variable:

```env
FOOTBALL_DATA_API_TOKEN=your_football_data_org_api_token_here
SECRET_KEY=your_custom_secret_key
```

> **Note:** If `FOOTBALL_DATA_API_TOKEN` is omitted, the application operates in **Instant Demo Mode** with realistic sample fixtures for major clubs.

---

## 🧪 Running Tests

Run the Pytest suite with coverage:

```bash
pytest --cov=. -v
```

Run code syntax and linting checks:

```bash
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
```

---

## 🐳 Running with Docker

Run the application using Docker Compose:

```bash
docker-compose up --build
```

Access the app at `http://localhost:5000`.

---

## 📁 Project Structure

```text
football_schedule/
├── app.py                  # Main Flask application & routes
├── static/
│   ├── app.js             # Client-side JavaScript (Filters, Tabs, Watched sync)
│   └── styles.css         # Modern Dark Sports Design System
├── templates/
│   ├── base.html          # Base HTML template with topbar & search
│   ├── index.html         # Main dashboard (Calendar, List, Stats views)
│   └── form.html          # Custom match creation & edit form
├── tests/
│   ├── __init__.py
│   └── test_app.py        # Pytest unit & integration test suite
├── .github/
│   └── workflows/
│       └── ci.yml         # GitHub Actions CI workflow
├── Dockerfile              # Docker build file
├── docker-compose.yml      # Docker Compose configuration
├── requirements.txt        # Python dependencies
└── README.md               # Project documentation
```
