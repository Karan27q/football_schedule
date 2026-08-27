from datetime import date, datetime, time, timedelta
import calendar
from dateutil import parser as date_parser
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session, Response
from flask_sqlalchemy import SQLAlchemy
import os
import requests
import time as time_module
from dotenv import load_dotenv
load_dotenv()


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-football-calendar-2026')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///football_calendar.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# football-data.org API token: https://www.football-data.org/
HARDCODED_FOOTBALL_API_TOKEN = ''
FOOTBALL_API_TOKEN = (HARDCODED_FOOTBALL_API_TOKEN or os.environ.get('FOOTBALL_DATA_API_TOKEN', '')).strip()
FOOTBALL_API_BASE = 'https://api.football-data.org/v4'

db = SQLAlchemy(app)

# Ensure tables exist when the app module loads
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print(f"DEBUG: Failed to create tables on startup: {e}")


class TTLCache:
    """Simple in-memory TTL Cache to prevent API rate limiting."""
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl = ttl_seconds
        self._cache = {}

    def get(self, key: str):
        if key in self._cache:
            val, timestamp = self._cache[key]
            if time_module.time() - timestamp < self.ttl:
                return val
            else:
                del self._cache[key]
        return None

    def set(self, key: str, value):
        self._cache[key] = (value, time_module.time())

    def clear(self):
        self._cache.clear()


# Cache instances
api_cache = TTLCache(ttl_seconds=3600)     # 1 hour match data cache
teams_cache = TTLCache(ttl_seconds=86400)   # 24 hour team list cache


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_date = db.Column(db.Date, nullable=False)
    kickoff_time = db.Column(db.Time, nullable=True)
    home_team = db.Column(db.String(120), nullable=False)
    away_team = db.Column(db.String(120), nullable=False)
    competition = db.Column(db.String(120), nullable=True)
    watched = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<Match {self.home_team} vs {self.away_team} on {self.match_date}>"


class WatchedMatch(db.Model):
    """Stores watched flags for external API matches by their external id."""
    external_id = db.Column(db.String(64), primary_key=True)
    watched = db.Column(db.Boolean, default=False, nullable=False)


# Curated Popular Mock Teams for seamless offline/tokenless execution
MOCK_TEAMS = [
    {'id': 57, 'name': 'Arsenal FC', 'shortName': 'Arsenal', 'crest': 'https://crests.football-data.org/57.png', 'league': 'Premier League'},
    {'id': 86, 'name': 'Real Madrid CF', 'shortName': 'Real Madrid', 'crest': 'https://crests.football-data.org/86.png', 'league': 'La Liga'},
    {'id': 81, 'name': 'FC Barcelona', 'shortName': 'Barcelona', 'crest': 'https://crests.football-data.org/81.png', 'league': 'La Liga'},
    {'id': 65, 'name': 'Manchester City FC', 'shortName': 'Man City', 'crest': 'https://crests.football-data.org/65.png', 'league': 'Premier League'},
    {'id': 64, 'name': 'Liverpool FC', 'shortName': 'Liverpool', 'crest': 'https://crests.football-data.org/64.png', 'league': 'Premier League'},
    {'id': 5, 'name': 'FC Bayern München', 'shortName': 'Bayern', 'crest': 'https://crests.football-data.org/5.png', 'league': 'Bundesliga'},
    {'id': 524, 'name': 'Paris Saint-Germain FC', 'shortName': 'PSG', 'crest': 'https://crests.football-data.org/524.png', 'league': 'Ligue 1'},
    {'id': 61, 'name': 'Chelsea FC', 'shortName': 'Chelsea', 'crest': 'https://crests.football-data.org/61.png', 'league': 'Premier League'},
    {'id': 66, 'name': 'Manchester United FC', 'shortName': 'Man United', 'crest': 'https://crests.football-data.org/66.png', 'league': 'Premier League'},
    {'id': 109, 'name': 'Juventus FC', 'shortName': 'Juventus', 'crest': 'https://crests.football-data.org/109.png', 'league': 'Serie A'},
    {'id': 108, 'name': 'FC Internazionale Milano', 'shortName': 'Inter', 'crest': 'https://crests.football-data.org/108.png', 'league': 'Serie A'},
    {'id': 4, 'name': 'Borussia Dortmund', 'shortName': 'Dortmund', 'crest': 'https://crests.football-data.org/4.png', 'league': 'Bundesliga'},
]


def generate_mock_matches(team_id: int, start_date: date, end_date: date) -> list[dict]:
    """Generates realistic sample fixtures for a team when offline or without API token."""
    team = next((t for t in MOCK_TEAMS if t['id'] == team_id), None)
    team_name = team['name'] if team else f"Team {team_id}"
    league = team['league'] if team else 'Premier League'

    opponents = [t['name'] for t in MOCK_TEAMS if t['id'] != team_id]
    if not opponents:
        opponents = ['Opponent A', 'Opponent B', 'Opponent C']

    matches = []
    try:
        watched_map = {wm.external_id: wm.watched for wm in WatchedMatch.query}
    except Exception:
        watched_map = {}

    curr_date = start_date + timedelta(days=(team_id % 4) + 1)
    match_idx = 1

    while curr_date <= end_date:
        opp = opponents[match_idx % len(opponents)]
        is_home = (match_idx % 2 == 1)
        home_team = team_name if is_home else opp
        away_team = opp if is_home else team_name
        comp = league if match_idx % 3 != 0 else 'UEFA Champions League'
        external_id = f"mock_{team_id}_{curr_date.strftime('%Y%m%d')}_{match_idx}"
        
        kick_hour = 20 if comp == 'UEFA Champions League' else (15 if match_idx % 2 == 0 else 17)
        kick_time = time(kick_hour, 30 if match_idx % 2 == 1 else 0)

        matches.append({
            'external_id': external_id,
            'match_date': curr_date,
            'kickoff_time': kick_time,
            'home_team': home_team,
            'away_team': away_team,
            'competition': comp,
            'watched': watched_map.get(external_id, False),
            'is_mock': True,
        })

        curr_date += timedelta(days=6)
        match_idx += 1

    return matches


def _get_month_year(query_date: date | None) -> tuple[int, int]:
    if query_date is None:
        today = date.today()
        return today.year, today.month
    return query_date.year, query_date.month


def _month_range(year: int, month: int) -> tuple[date, date]:
    first_day = date(year, month, 1)
    _, last_day_num = calendar.monthrange(year, month)
    last_day = date(year, month, last_day_num)
    return first_day, last_day


def _group_matches_by_day(matches: list[dict]) -> dict[date, list[dict]]:
    grouped: dict[date, list[dict]] = {}
    for m in matches:
        grouped.setdefault(m['match_date'], []).append(m)
    for day in grouped:
        grouped[day].sort(key=lambda m: ((m['kickoff_time'] or datetime.min.time()), m['home_team'], m['away_team']))
    return grouped


def api_headers() -> dict:
    if not FOOTBALL_API_TOKEN:
        raise RuntimeError('No API token set.')
    return {'X-Auth-Token': FOOTBALL_API_TOKEN}


def api_get(path: str, params: dict | None = None) -> dict:
    cache_key = f"{path}?{params}"
    cached = api_cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"{FOOTBALL_API_BASE}{path}"
    r = requests.get(url, headers=api_headers(), params=params or {}, timeout=15)
    if r.status_code == 429:
        raise RuntimeError('API rate limit reached. Using cached or fallback fixtures.')
    if r.status_code >= 400:
        raise RuntimeError(f"API error {r.status_code}: {r.text}")
    data = r.json()
    api_cache.set(cache_key, data)
    return data


def search_teams(query: str) -> list[dict]:
    q = (query or '').strip().lower()
    if not q:
        return []

    matched_mock = [t for t in MOCK_TEAMS if q in t['name'].lower() or q in t['shortName'].lower()]
    
    if FOOTBALL_API_TOKEN:
        try:
            data = api_get('/teams', params={'name': query})
            teams = data.get('teams', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            if teams:
                matched_api = []
                for t in teams:
                    if isinstance(t, dict) and (q in (t.get('name') or '').lower() or q in (t.get('shortName') or '').lower()):
                        matched_api.append({
                            'id': t['id'],
                            'name': t['name'],
                            'shortName': t.get('shortName', t['name']),
                            'crest': t.get('crest') or t.get('crestUrl')
                        })
                if matched_api:
                    return matched_api[:20]
        except Exception as e:
            print(f"DEBUG: API team search failed, using mock matches: {e}")

    return matched_mock[:20]


def fetch_team_matches(team_id: int, start_date: date, end_date: date) -> list[dict]:
    cache_key = f"team_matches_{team_id}_{start_date}_{end_date}"
    cached = api_cache.get(cache_key)
    if cached is not None:
        return cached

    matches = []
    if FOOTBALL_API_TOKEN:
        try:
            params = {'dateFrom': start_date.isoformat(), 'dateTo': end_date.isoformat()}
            data = api_get(f'/teams/{team_id}/matches', params=params)
            watched_map = {wm.external_id: wm.watched for wm in WatchedMatch.query}
            for m in data.get('matches', []):
                try:
                    utc_date = date_parser.parse(m['utcDate'])
                    external_id = str(m['id'])
                    matches.append({
                        'external_id': external_id,
                        'match_date': utc_date.date(),
                        'kickoff_time': utc_date.time(),
                        'home_team': m['homeTeam']['name'],
                        'away_team': m['awayTeam']['name'],
                        'competition': m['competition']['name'] if m.get('competition') else None,
                        'watched': watched_map.get(external_id, False),
                        'is_mock': False,
                    })
                except Exception as ex:
                    print(f"DEBUG: Parse error: {ex}")
            api_cache.set(cache_key, matches)
            return matches
        except Exception as e:
            print(f"DEBUG: API fetch error for team {team_id}: {e}. Falling back to mock fixtures.")

    matches = generate_mock_matches(team_id, start_date, end_date)
    api_cache.set(cache_key, matches)
    return matches


@app.route('/')
@app.route('/calendar')
def calendar_view():
    year_param = request.args.get('year')
    month_param = request.args.get('month')
    if year_param and month_param:
        try:
            year = int(year_param)
            month = int(month_param)
        except ValueError:
            year, month = _get_month_year(None)
    else:
        year, month = _get_month_year(None)

    start_date, end_date = _month_range(year, month)

    selected_team_id = session.get('selected_team_id')
    selected_team_name = session.get('selected_team_name')
    matches = []
    matches_by_day = {}
    api_error = None

    if selected_team_id:
        try:
            matches = fetch_team_matches(int(selected_team_id), start_date, end_date)
            if not matches:
                api_error = f'No scheduled matches found for {selected_team_name} in {year}-{month:02d}.'
        except Exception as e:
            api_error = f"Notice: {str(e)}"
            matches = generate_mock_matches(int(selected_team_id), start_date, end_date)

    local_matches = Match.query.filter(Match.match_date >= start_date, Match.match_date <= end_date).all()
    for lm in local_matches:
        matches.append({
            'external_id': f"local_{lm.id}",
            'local_id': lm.id,
            'match_date': lm.match_date,
            'kickoff_time': lm.kickoff_time,
            'home_team': lm.home_team,
            'away_team': lm.away_team,
            'competition': lm.competition or 'Custom Match',
            'watched': lm.watched,
            'is_local': True,
        })

    matches_by_day = _group_matches_by_day(matches)
    competitions = sorted(list({m.get('competition') for m in matches if m.get('competition')}))

    total_count = len(matches)
    watched_count = sum(1 for m in matches if m.get('watched'))
    completion_pct = round((watched_count / total_count * 100), 1) if total_count > 0 else 0.0

    cal = calendar.Calendar(firstweekday=0)
    weeks = list(cal.itermonthdates(year, month))
    rows = [weeks[i:i+7] for i in range(0, len(weeks), 7)]

    prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
    next_year, next_month = (year, month + 1) if month < 12 else (year + 1, 1)

    return render_template(
        'index.html',
        year=year,
        month=month,
        rows=rows,
        matches=matches,
        matches_by_day=matches_by_day,
        competitions=competitions,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        selected_team_id=selected_team_id,
        selected_team_name=selected_team_name,
        api_error=api_error,
        is_demo_mode=(not FOOTBALL_API_TOKEN),
        total_count=total_count,
        watched_count=watched_count,
        completion_pct=completion_pct,
    )



@app.route('/teams/search')
def teams_search():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'teams': []})
    try:
        teams = search_teams(q)
        return jsonify({'teams': teams})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/clear-team')
@app.route('/home')
def clear_team():
    """Clears selected club and returns to the home page with all popular clubs."""
    session.pop('selected_team_id', None)
    session.pop('selected_team_name', None)
    return redirect(url_for('calendar_view'))


@app.route('/clubs/popular')
def clubs_popular():
    out = []
    seen_ids = set()
    seen_names = set()

    if FOOTBALL_API_TOKEN:
        try:
            cached = teams_cache.get('popular_clubs')
            if cached:
                return jsonify({'teams': cached})
            data = api_get('/teams')
            teams_data = data.get('teams', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for t in teams_data[:30]:
                tid = t.get('id')
                name = t.get('name')
                if tid and name:
                    seen_ids.add(tid)
                    seen_names.add(name.lower())
                    out.append({
                        'id': tid,
                        'name': name,
                        'shortName': t.get('shortName', name),
                        'crest': t.get('crest') or t.get('crestUrl') or t.get('logo'),
                        'league': 'Official API'
                    })
        except Exception as e:
            print(f"DEBUG: API popular clubs failed, using fallback mock: {e}")

    # Append fallback mock clubs that aren't already in out
    for mt in MOCK_TEAMS:
        if mt['id'] not in seen_ids and mt['name'].lower() not in seen_names:
            out.append(mt)

    if FOOTBALL_API_TOKEN and out:
        teams_cache.set('popular_clubs', out)

    return jsonify({'teams': out})



@app.route('/teams/select', methods=['POST'])
def team_select():
    team_id = request.form.get('team_id')
    team_name = request.form.get('team_name')
    q = request.form.get('q', '').strip()

    if not team_id or not team_name:
        if q and len(q) >= 2:
            candidates = search_teams(q)
            exact = next((t for t in candidates if t.get('name', '').lower() == q.lower()), None)
            chosen = exact or (candidates[0] if len(candidates) >= 1 else None)
            if chosen:
                team_id = str(chosen['id'])
                team_name = chosen['name']
            else:
                flash('Please select a team from suggestions.', 'danger')
                return redirect(url_for('calendar_view'))
        else:
            flash('Invalid team selection.', 'danger')
            return redirect(url_for('calendar_view'))

    session['selected_team_id'] = team_id
    session['selected_team_name'] = team_name
    flash(f'Selected team: {team_name}', 'success')
    return redirect(url_for('calendar_view'))


@app.route('/api/demo-team', methods=['POST'])
def demo_team():
    team_id = request.json.get('team_id') if request.is_json else request.form.get('team_id')
    team = next((t for t in MOCK_TEAMS if str(t['id']) == str(team_id)), MOCK_TEAMS[0])
    session['selected_team_id'] = str(team['id'])
    session['selected_team_name'] = team['name']
    return jsonify({'ok': True, 'team': team})


@app.route('/matches/<external_id>/toggle', methods=['POST'])
def toggle_watched_external(external_id: str):
    if external_id.startswith('local_'):
        local_id = int(external_id.replace('local_', ''))
        m = db.session.get(Match, local_id)
        if not m:
            return jsonify({'error': 'Match not found'}), 404
        m.watched = not m.watched
        db.session.commit()
        return jsonify({'ok': True, 'watched': m.watched})

    wm = db.session.get(WatchedMatch, external_id)
    if wm is None:
        wm = WatchedMatch(external_id=external_id, watched=True)
        db.session.add(wm)
    else:
        wm.watched = not wm.watched
    db.session.commit()
    return jsonify({'ok': True, 'watched': wm.watched})


@app.route('/api/stats')
def api_stats():
    selected_team_id = session.get('selected_team_id')
    year = request.args.get('year', type=int, default=date.today().year)
    month = request.args.get('month', type=int, default=date.today().month)
    start_date, end_date = _month_range(year, month)

    matches = []
    if selected_team_id:
        try:
            matches = fetch_team_matches(int(selected_team_id), start_date, end_date)
        except Exception:
            matches = generate_mock_matches(int(selected_team_id), start_date, end_date)

    local_matches = Match.query.filter(Match.match_date >= start_date, Match.match_date <= end_date).all()
    for lm in local_matches:
        matches.append({
            'competition': lm.competition or 'Custom Match',
            'watched': lm.watched,
        })

    total = len(matches)
    watched = sum(1 for m in matches if m.get('watched'))
    unwatched = total - watched
    pct = round((watched / total * 100), 1) if total > 0 else 0.0

    competitions = {}
    for m in matches:
        comp = m.get('competition') or 'Other'
        if comp not in competitions:
            competitions[comp] = {'total': 0, 'watched': 0}
        competitions[comp]['total'] += 1
        if m.get('watched'):
            competitions[comp]['watched'] += 1

    return jsonify({
        'total': total,
        'watched': watched,
        'unwatched': unwatched,
        'completion_pct': pct,
        'competitions': competitions
    })


@app.route('/calendar/export.ics')
def export_ics():
    selected_team_id = session.get('selected_team_id')
    year = request.args.get('year', type=int, default=date.today().year)
    month = request.args.get('month', type=int, default=date.today().month)
    start_date, end_date = _month_range(year, month)

    matches = []
    if selected_team_id:
        try:
            matches = fetch_team_matches(int(selected_team_id), start_date, end_date)
        except Exception:
            matches = generate_mock_matches(int(selected_team_id), start_date, end_date)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Football Match Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH"
    ]

    for m in matches:
        mdate = m['match_date']
        ktime = m.get('kickoff_time') or time(15, 0)
        dtstart = datetime.combine(mdate, ktime).strftime("%Y%m%dT%H%M%SZ")
        dtend = (datetime.combine(mdate, ktime) + timedelta(hours=2)).strftime("%Y%m%dT%H%M%SZ")
        summary = f"{m['home_team']} vs {m['away_team']}"
        desc = f"Competition: {m.get('competition', 'N/A')}"
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{m.get('external_id', 'local')}@footballcalendar",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            "STATUS:CONFIRMED",
            "END:VEVENT"
        ])

    lines.append("END:VCALENDAR")
    ics_data = "\r\n".join(lines)
    filename = f"matches_{session.get('selected_team_name', 'football')}_{year}_{month:02d}.ics"

    return Response(
        ics_data,
        mimetype="text/calendar",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route('/matches/new', methods=['GET', 'POST'])
def create_match():
    if request.method == 'POST':
        try:
            match_date_str = request.form.get('match_date', '').strip()
            kickoff_str = request.form.get('kickoff_time', '').strip()
            home_team = request.form.get('home_team', '').strip()
            away_team = request.form.get('away_team', '').strip()
            competition = request.form.get('competition', '').strip() or None

            if not match_date_str or not home_team or not away_team:
                raise ValueError('Date, home, and away teams are required')

            match_date = date_parser.parse(match_date_str).date()
            kickoff_time = date_parser.parse(kickoff_str).time() if kickoff_str else None

            m = Match(
                match_date=match_date,
                kickoff_time=kickoff_time,
                home_team=home_team,
                away_team=away_team,
                competition=competition,
            )
            db.session.add(m)
            db.session.commit()
            flash('Match added successfully', 'success')
            return redirect(url_for('calendar_view', year=match_date.year, month=match_date.month))
        except Exception as e:
            flash(f'Error: {e}', 'danger')
    return render_template('form.html', mode='create')


@app.route('/matches/<int:match_id>/edit', methods=['GET', 'POST'])
def edit_match(match_id: int):
    m = db.session.get(Match, match_id)
    if not m:
        flash('Match not found', 'danger')
        return redirect(url_for('calendar_view'))
    if request.method == 'POST':
        try:
            match_date_str = request.form.get('match_date', '').strip()
            kickoff_str = request.form.get('kickoff_time', '').strip()
            home_team = request.form.get('home_team', '').strip()
            away_team = request.form.get('away_team', '').strip()
            competition = request.form.get('competition', '').strip() or None

            if not match_date_str or not home_team or not away_team:
                raise ValueError('Date, home, and away teams are required')

            m.match_date = date_parser.parse(match_date_str).date()
            m.kickoff_time = date_parser.parse(kickoff_str).time() if kickoff_str else None
            m.home_team = home_team
            m.away_team = away_team
            m.competition = competition
            db.session.commit()
            flash('Match updated successfully', 'success')
            return redirect(url_for('calendar_view', year=m.match_date.year, month=m.match_date.month))
        except Exception as e:
            flash(f'Error: {e}', 'danger')
    return render_template('form.html', mode='edit', match=m)


@app.route('/matches/<int:match_id>/delete', methods=['POST'])
def delete_match(match_id: int):
    m = db.session.get(Match, match_id)
    if not m:
        flash('Match not found', 'danger')
        return redirect(url_for('calendar_view'))
    year, month = m.match_date.year, m.match_date.month
    db.session.delete(m)
    db.session.commit()
    flash('Match deleted', 'info')
    return redirect(url_for('calendar_view', year=year, month=month))


@app.cli.command('init-db')
def init_db_command():
    """Initialize the database tables."""
    db.create_all()
    print('Initialized the database.')


@app.cli.command('seed-db')
def seed_db_command():
    """Seed the database with a few sample matches."""
    base = date.today().replace(day=1)
    examples = [
        ('Team A', 'Team B', 'League', base, time(17, 30)),
        ('Team C', 'Team D', 'Cup', base.replace(day=5), time(20, 0)),
    ]
    for h, a, comp, d, t in examples:
        m = Match(home_team=h, away_team=a, competition=comp, match_date=d, kickoff_time=t)
        db.session.add(m)
    db.session.commit()
    print('Seeded example matches.')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
