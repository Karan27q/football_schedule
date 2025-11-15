from datetime import date, datetime
import calendar
from dateutil import parser as date_parser
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from flask_sqlalchemy import SQLAlchemy
import os
import requests
from dotenv import load_dotenv
load_dotenv()


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///football_calendar.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# football-data.org API token: https://www.football-data.org/
# Set either the hardcoded token below OR environment variable FOOTBALL_DATA_API_TOKEN
HARDCODED_FOOTBALL_API_TOKEN = ''  # <- place your token here if you prefer in-file config
FOOTBALL_API_TOKEN = (HARDCODED_FOOTBALL_API_TOKEN or os.environ.get('FOOTBALL_DATA_API_TOKEN', '')).strip()
FOOTBALL_API_BASE = 'https://api.football-data.org/v4'

db = SQLAlchemy(app)

# Ensure tables exist when the app module loads (works with `flask run`)
with app.app_context():
	try:
		db.create_all()
	except Exception as e:
		print(f"DEBUG: Failed to create tables on startup: {e}")


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
		raise RuntimeError('No API token set. Set HARDCODED_FOOTBALL_API_TOKEN in app.py or FOOTBALL_DATA_API_TOKEN env var.')
	return {
		'X-Auth-Token': FOOTBALL_API_TOKEN
	}


def api_get(path: str, params: dict | None = None) -> dict:
	url = f"{FOOTBALL_API_BASE}{path}"
	r = requests.get(url, headers=api_headers(), params=params or {}, timeout=20)
	if r.status_code == 429:
		raise RuntimeError('API rate limit reached. Try again later.')
	if r.status_code >= 400:
		raise RuntimeError(f"API error {r.status_code}: {r.text}")
	return r.json()


def search_teams(query: str) -> list[dict]:
	"""
	Search for teams using the /teams endpoint with name parameter.
	Documentation: https://api.football-data.org/v4/teams?name={query}
	"""
	# Try the API filtered by name first (some API setups support ?name=)
	try:
		data = api_get('/teams', params={'name': query})
	except Exception:
		data = None

	teams: list[dict] = []
	if isinstance(data, list):
		teams = data
	elif isinstance(data, dict) and 'teams' in data:
		teams = data.get('teams') or []

	# If the API didn't return a useful list, fall back to fetching all teams
	# and perform a local, case-insensitive substring match. This helps when
	# the upstream API does not support ?name filtering or returns a single
	# canonical result.
	if not teams:
		try:
			all_data = api_get('/teams')
			if isinstance(all_data, list):
				teams = all_data
			elif isinstance(all_data, dict) and 'teams' in all_data:
				teams = all_data.get('teams') or []
		except Exception:
			teams = []

	# Filter locally for substring matches (name or shortName) and limit results
	q = (query or '').strip().lower()
	if not q:
		return []

	matched = []
	for t in teams:
		if not isinstance(t, dict):
			continue
		name = (t.get('name') or '').lower()
		short = (t.get('shortName') or '').lower()
		if q in name or q in short:
			matched.append(t)

	# Return up to 20 matches to avoid overwhelming the UI
	return matched[:20]


def fetch_team_matches(team_id: int, start_date: date, end_date: date) -> list[dict]:
	"""
	Fetch matches for a team using /teams/{id}/matches endpoint.
	Documentation example: https://api.football-data.org/v4/teams/86/matches?status=SCHEDULED
	"""
	params = {
		'dateFrom': start_date.isoformat(),
		'dateTo': end_date.isoformat(),
		# Note: status parameter might need to be omitted or use comma-separated values
		# Some APIs require multiple requests for different statuses
	}
	print(f"DEBUG: API request params: {params}")
	data = api_get(f'/teams/{team_id}/matches', params=params)
	matches = []
	watched_map = {wm.external_id: wm.watched for wm in WatchedMatch.query}
	matches_data = data.get('matches', [])
	print(f"DEBUG: Found {len(matches_data)} matches from API for team {team_id}")
	for m in matches_data:
		try:
			utc_date = date_parser.parse(m['utcDate'])
			match_date = utc_date.date()
			kick_time = utc_date.time()
			external_id = str(m['id'])
			matches.append({
				'external_id': external_id,
				'match_date': match_date,
				'kickoff_time': kick_time,
				'home_team': m['homeTeam']['name'],
				'away_team': m['awayTeam']['name'],
				'competition': m['competition']['name'] if m.get('competition') else None,
				'watched': watched_map.get(external_id, False),
			})
		except Exception as e:
			print(f"DEBUG: Error parsing match {m.get('id')}: {e}")
			continue
	print(f"DEBUG: Processed {len(matches)} matches")
	return matches


@app.route('/')
@app.route('/calendar')
def calendar_view():
	year_param = request.args.get('year')
	month_param = request.args.get('month')
	if year_param and month_param:
		year = int(year_param)
		month = int(month_param)
	else:
		year, month = _get_month_year(None)

	start_date, end_date = _month_range(year, month)

	selected_team_id = session.get('selected_team_id')
	selected_team_name = session.get('selected_team_name')
	matches = []
	matches_by_day = {}
	api_error = None
	if selected_team_id:
		print(f"DEBUG: Selected team: {selected_team_name} (ID: {selected_team_id})")
		print(f"DEBUG: Fetching matches from {start_date} to {end_date}")
		try:
			matches = fetch_team_matches(int(selected_team_id), start_date, end_date)
			matches_by_day = _group_matches_by_day(matches)
			print(f"DEBUG: Grouped into {len(matches_by_day)} days")
			# Debug: log if no matches found
			if not matches:
				api_error = f'No scheduled matches found for {selected_team_name} in {year}-{month:02d}. Try a different month or check if matches exist.'
		except Exception as e:
			api_error = str(e)
			import traceback
			print(f"Error fetching matches: {e}")
			print(traceback.format_exc())
	else:
		print("DEBUG: No team selected")

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
		matches_by_day=matches_by_day,
		prev_year=prev_year,
		prev_month=prev_month,
		next_year=next_year,
		next_month=next_month,
		selected_team_id=selected_team_id,
		selected_team_name=selected_team_name,
		api_error=api_error,
	)


@app.route('/teams/search')
def teams_search():
	q = request.args.get('q', '').strip()
	# Avoid short queries that often cause 400s or noisy results
	if not q or len(q) < 2:
		return jsonify({ 'teams': [] })
	try:
		teams = search_teams(q)
		slim = [
			{ 'id': t['id'], 'name': t['name'], 'shortName': t.get('shortName', t.get('name')) }
			for t in teams if 'id' in t and 'name' in t
		]
		return jsonify({ 'teams': slim })
	except RuntimeError as e:
		# API errors (rate limit, auth, etc.)
		return jsonify({ 'error': str(e) }), 400
	except Exception as e:
		# Unexpected errors
		return jsonify({ 'error': f'Search failed: {str(e)}' }), 400


@app.route('/clubs/popular')
def clubs_popular():
	"""Return a short list of teams suitable for rendering a club grid on the homepage.
	Tries to use the /teams endpoint; if that returns a dict with 'teams' key use it,
	otherwise try to interpret list shapes. Returns at most 30 teams with fields
	{id, name, crestUrl} when available.
	"""
	try:
		data = api_get('/teams')
	except Exception as e:
		return jsonify({'error': str(e)}), 400

	teams = []
	if isinstance(data, list):
		teams = data
	elif isinstance(data, dict) and 'teams' in data:
		teams = data.get('teams') or []

	out = []
	for t in teams:
		if not isinstance(t, dict):
			continue
		out.append({
			'id': t.get('id'),
			'name': t.get('name'),
			# different APIs may name the crest field differently
			'crest': t.get('crest') or t.get('crestUrl') or t.get('logo') or None,
		})
		if len(out) >= 30:
			break

	return jsonify({'teams': out})


@app.route('/teams/<int:team_id>/matches_json')
def team_matches_json(team_id: int):
	"""Return matches for a team as JSON for a given year/month query parameters.
	Used by the client to fetch and render an inline calendar without a full page reload.
	"""
	year_param = request.args.get('year')
	month_param = request.args.get('month')
	if year_param and month_param:
		try:
			year = int(year_param)
			month = int(month_param)
		except Exception:
			return jsonify({'error': 'Invalid year/month parameters'}), 400
	else:
		year, month = _get_month_year(None)

	start_date, end_date = _month_range(year, month)
	try:
		matches = fetch_team_matches(team_id, start_date, end_date)
	except Exception as e:
		return jsonify({'error': str(e)}), 400

	# Convert date/time objects to serializable strings for JSON responses
	serializable = []
	for m in matches:
		serializable.append({
			'external_id': m.get('external_id'),
			'match_date': m.get('match_date').isoformat() if m.get('match_date') is not None else None,
			'kickoff_time': m.get('kickoff_time').strftime('%H:%M') if m.get('kickoff_time') is not None else None,
			'home_team': m.get('home_team'),
			'away_team': m.get('away_team'),
			'competition': m.get('competition'),
			'watched': bool(m.get('watched')),
		})

	return jsonify({'matches': serializable})


@app.route('/teams/select', methods=['POST'])
def team_select():
	team_id = request.form.get('team_id')
	team_name = request.form.get('team_name')
	q = request.form.get('q', '').strip()
	if not team_id or not team_name:
		# Fallback: try to resolve from query
		try:
			if q and len(q) >= 2:
				candidates = search_teams(q)
				# Prefer exact (case-insensitive) name match; otherwise pick the first candidate if any
				exact = next((t for t in candidates if t.get('name','').lower() == q.lower()), None)
				chosen = exact or (candidates[0] if len(candidates) >= 1 else None)
				if chosen:
					team_id = str(chosen['id'])
					team_name = chosen['name']
				else:
					flash('Please pick a team from the dropdown suggestions.', 'danger')
					return redirect(url_for('calendar_view'))
		except Exception as e:
			flash(f'Could not resolve team: {e}', 'danger')
			return redirect(url_for('calendar_view'))
	# Persist selection
	session['selected_team_id'] = team_id
	session['selected_team_name'] = team_name
	flash(f'Selected team: {team_name}', 'success')
	return redirect(url_for('calendar_view'))


@app.route('/matches/<external_id>/toggle', methods=['POST'])
def toggle_watched_external(external_id: str):
	wm = WatchedMatch.query.get(external_id)
	if wm is None:
		wm = WatchedMatch(external_id=external_id, watched=True)
		db.session.add(wm)
	else:
		wm.watched = not wm.watched
	db.session.commit()
	return jsonify({ 'ok': True, 'watched': wm.watched })


@app.route('/matches/new', methods=['GET', 'POST'])
def create_match():
	# Local manual creation remains available (optional)
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
			flash('Match added', 'success')
			return redirect(url_for('calendar_view', year=match_date.year, month=match_date.month))
		except Exception as e:
			flash(f'Error: {e}', 'danger')
	return render_template('form.html', mode='create')


@app.route('/matches/<int:match_id>/edit', methods=['GET', 'POST'])
def edit_match(match_id: int):
	m = Match.query.get_or_404(match_id)
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
			flash('Match updated', 'success')
			return redirect(url_for('calendar_view', year=m.match_date.year, month=m.match_date.month))
		except Exception as e:
			flash(f'Error: {e}', 'danger')
	return render_template('form.html', mode='edit', match=m)


@app.route('/matches/<int:match_id>/delete', methods=['POST'])
def delete_match(match_id: int):
	m = Match.query.get_or_404(match_id)
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
	from datetime import time
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
	app.run(debug=True)
