from datetime import date, time
import pytest
from app import app, db, Match, WatchedMatch, TTLCache, generate_mock_matches


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SECRET_KEY'] = 'test-secret-key'

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()


def test_calendar_view_index(client):
    """Test calendar view renders home page cleanly."""
    res = client.get('/')
    assert res.status_code == 200
    assert b"Football Calendar" in res.data
    assert b"Select a Popular Club" in res.data


def test_calendar_view_with_month_year(client):
    """Test calendar view with year and month query params."""
    res = client.get('/calendar?year=2026&month=9')
    assert res.status_code == 200
    assert b"2026 - 09" in res.data


def test_clear_team(client):
    """Test /clear-team resets selected team and redirects to home calendar."""
    client.post('/api/demo-team', json={'team_id': '57'})
    res = client.get('/clear-team', follow_redirects=True)
    assert res.status_code == 200
    assert b"Select a Popular Club" in res.data


def test_clubs_popular_api(client):

    """Test /clubs/popular returns list of clubs with expected fields."""
    res = client.get('/clubs/popular')
    assert res.status_code == 200
    json_data = res.get_json()
    assert 'teams' in json_data
    assert len(json_data['teams']) > 0
    assert json_data['teams'][0]['name'] is not None


def test_team_search_api(client):
    """Test /teams/search endpoint with query parameters."""
    res = client.get('/teams/search?q=Arsenal')
    assert res.status_code == 200
    json_data = res.get_json()
    assert 'teams' in json_data
    assert any('Arsenal' in t['name'] for t in json_data['teams'])


def test_team_search_short_query(client):
    """Test search with single character query returns empty list."""
    res = client.get('/teams/search?q=a')
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data['teams'] == []


def test_demo_team_select(client):
    """Test selecting a demo team updates session."""
    res = client.post('/api/demo-team', json={'team_id': '57'})
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data['ok'] is True
    assert json_data['team']['name'] == 'Arsenal FC'


def test_team_select_form(client):
    """Test submitting team selection form redirects to calendar."""
    res = client.post('/teams/select', data={'team_id': '86', 'team_name': 'Real Madrid CF'}, follow_redirects=True)
    assert res.status_code == 200
    assert b"Selected team: Real Madrid CF" in res.data


def test_toggle_watched_external(client):
    """Test toggling watched state for an external match ID."""
    res = client.post('/matches/mock_57_20260901_1/toggle')
    assert res.status_code == 200
    data = res.get_json()
    assert data['ok'] is True
    assert data['watched'] is True

    # Toggle off
    res2 = client.post('/matches/mock_57_20260901_1/toggle')
    assert res2.get_json()['watched'] is False


def test_manual_match_crud(client):
    """Test creating, editing, and deleting a manual custom match."""
    # 1. Create match
    post_res = client.post('/matches/new', data={
        'match_date': '2026-09-15',
        'kickoff_time': '19:45',
        'home_team': 'Local FC',
        'away_team': 'Rival United',
        'competition': 'Derby Cup'
    }, follow_redirects=True)
    assert post_res.status_code == 200
    assert b"Match added successfully" in post_res.data

    with app.app_context():
        m = Match.query.filter_by(home_team='Local FC').first()
        assert m is not None
        assert m.away_team == 'Rival United'
        match_id = m.id

    # 2. Edit match
    edit_res = client.post(f'/matches/{match_id}/edit', data={
        'match_date': '2026-09-16',
        'kickoff_time': '20:00',
        'home_team': 'Local FC Updated',
        'away_team': 'Rival United',
        'competition': 'Derby Cup Final'
    }, follow_redirects=True)
    assert edit_res.status_code == 200
    assert b"Match updated successfully" in edit_res.data

    # 3. Toggle local match
    toggle_res = client.post(f'/matches/local_{match_id}/toggle')
    assert toggle_res.status_code == 200
    assert toggle_res.get_json()['watched'] is True

    # 4. Delete match
    del_res = client.post(f'/matches/{match_id}/delete', follow_redirects=True)
    assert del_res.status_code == 200
    assert b"Match deleted" in del_res.data


def test_api_stats(client):
    """Test stats calculation endpoint."""
    client.post('/api/demo-team', json={'team_id': '57'})
    res = client.get('/api/stats?year=2026&month=9')
    assert res.status_code == 200
    data = res.get_json()
    assert 'total' in data
    assert 'watched' in data
    assert 'completion_pct' in data


def test_export_ics(client):
    """Test export iCalendar file endpoint."""
    client.post('/api/demo-team', json={'team_id': '57'})
    res = client.get('/calendar/export.ics?year=2026&month=9')
    assert res.status_code == 200
    assert res.headers['Content-Type'] == 'text/calendar; charset=utf-8'
    assert b"BEGIN:VCALENDAR" in res.data
    assert b"END:VCALENDAR" in res.data


def test_ttl_cache():
    """Test TTLCache set, get, and expiration."""
    cache = TTLCache(ttl_seconds=1)
    cache.set('key1', 'val1')
    assert cache.get('key1') == 'val1'
    
    # Wait for expiration
    import time
    time.sleep(1.1)
    assert cache.get('key1') is None


def test_generate_mock_matches():
    """Test mock fixture generator produces expected schema."""
    matches = generate_mock_matches(57, date(2026, 9, 1), date(2026, 9, 30))
    assert len(matches) > 0
    m = matches[0]
    assert 'external_id' in m
    assert 'home_team' in m
    assert 'away_team' in m
    assert 'competition' in m
