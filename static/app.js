document.addEventListener('DOMContentLoaded', () => {
	// Club grid: fetch and render popular clubs when present on the page
	const clubGrid = document.getElementById('club-grid');
	if (clubGrid) {
		const renderClub = (team) => {
			const card = document.createElement('div');
			card.className = 'club-card';
			const img = document.createElement('img');
			img.className = 'club-crest';
			img.src = team.crest || '';
			img.alt = team.name || 'crest';
			img.onerror = () => { img.style.display = 'none'; };
			const title = document.createElement('div');
			title.className = 'club-name';
			title.textContent = team.name || 'Unnamed';
			const content = document.createElement('div');
			content.className = 'club-content';
			const loader = document.createElement('div');
			loader.className = 'muted';
			loader.textContent = 'Click to load calendar';
			content.appendChild(loader);

			card.appendChild(img);
			card.appendChild(title);
			card.appendChild(content);

			// clicking a club selects it (POST /teams/select) and navigates to the calendar view
			card.addEventListener('click', async (e) => {
				if (e.target.tagName === 'A' || e.target.tagName === 'BUTTON' || e.target.tagName === 'INPUT') return;
				content.innerHTML = '';
				const loading = document.createElement('div');
				loading.className = 'muted';
				loading.textContent = 'Loading calendar...';
				content.appendChild(loading);
				try {
					const params = new URLSearchParams();
					params.append('team_id', team.id);
					params.append('team_name', team.name || '');
					params.append('q', team.name || '');
					const res = await fetch('/teams/select', {
						method: 'POST',
						headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
						body: params.toString(),
					});
					if (!res.ok) {
						const txt = await res.text();
						throw new Error(txt || `Server returned ${res.status}`);
					}
					// Redirect to calendar view which will render the selected team's calendar
					window.location.href = '/calendar';
				} catch (err) {
					content.innerHTML = '';
					const errdiv = document.createElement('div');
					errdiv.className = 'muted';
					errdiv.textContent = err.message || 'Failed to select club.';
					content.appendChild(errdiv);
					console.error('Club select failed', err);
				}
			});

			return card;
		};

		(async () => {
			try {
				const res = await fetch('/clubs/popular');
				const data = await res.json();
				if (!res.ok) {
					clubGrid.innerHTML = '<div class="muted">Could not load clubs.</div>';
					return;
				}
				clubGrid.innerHTML = '';
				const teams = Array.isArray(data.teams) ? data.teams : [];
				if (teams.length === 0) {
					clubGrid.innerHTML = '<div class="muted">No clubs available.</div>';
				}
				teams.forEach(t => {
					const card = renderClub(t);
					clubGrid.appendChild(card);
				});
			} catch (err) {
				clubGrid.innerHTML = '<div class="muted">Failed to load clubs.</div>';
				console.error('Failed to load clubs', err);
			}
		})();
	}
	// watched toggle by external id
	const watchedBoxes = document.querySelectorAll('input[type="checkbox"][data-external-id]');
	watchedBoxes.forEach(cb => {
		cb.addEventListener('change', async (e) => {
			const externalId = e.target.getAttribute('data-external-id');
			try {
				const res = await fetch(`/matches/${externalId}/toggle`, { method: 'POST' });
				if (!res.ok) throw new Error('Failed');
				const data = await res.json();
				const container = e.target.closest('.match');
				if (data.watched) {
					container.classList.add('watched');
				} else {
					container.classList.remove('watched');
				}
			} catch (err) {
				alert('Could not toggle watched.');
				e.target.checked = !e.target.checked;
			}
		});
	});

	// team search autocomplete + guarded submit
	const form = document.getElementById('team-select-form');
	const searchInput = document.getElementById('team-search');
	const teamIdInput = document.getElementById('team_id');
	const teamNameInput = document.getElementById('team_name');
	if (searchInput) {
		let dropdown;
		const closeDropdown = () => {
			if (dropdown) { dropdown.remove(); dropdown = null; }
		};
		const renderDropdown = (items) => {
			closeDropdown();
			dropdown = document.createElement('div');
			dropdown.className = 'dropdown';
			if (!items || items.length === 0) {
				const empty = document.createElement('div');
				empty.className = 'dropdown-item';
				empty.textContent = 'No results';
				empty.style.color = '#888';
				empty.style.cursor = 'default';
				dropdown.appendChild(empty);
			} else {
				items.forEach(item => {
					const opt = document.createElement('div');
					opt.className = 'dropdown-item';
					opt.textContent = item.name;
					opt.addEventListener('click', () => {
						searchInput.value = item.name;
						if (teamIdInput) teamIdInput.value = item.id;
						if (teamNameInput) teamNameInput.value = item.name;
						closeDropdown();
					});
					dropdown.appendChild(opt);
				});
			}
			searchInput.parentElement.appendChild(dropdown);
		};
		let debounceTimer;
		searchInput.addEventListener('input', () => {
			if (teamIdInput) teamIdInput.value = '';
			if (teamNameInput) teamNameInput.value = '';
			const q = searchInput.value.trim();
			if (!q || q.length < 2) { closeDropdown(); return; }
			clearTimeout(debounceTimer);
			debounceTimer = setTimeout(async () => {
				try {
					const res = await fetch(`/teams/search?q=${encodeURIComponent(q)}`);
					const data = await res.json();
					if (!res.ok) {
						const errorMsg = data.error || 'Search failed';
						console.error('Team search error:', errorMsg);
						renderDropdown([]);
						return;
					}
					renderDropdown(data.teams || []);
				} catch(e) {
					console.error('Team search exception:', e);
					renderDropdown([]);
				}
			}, 250);
		});
		if (form) {
			form.addEventListener('submit', async (e) => {
				if (!teamIdInput || !teamNameInput) return; // nothing to do
				if (teamIdInput.value && teamNameInput.value) return; // already selected
				// try to auto-resolve if there is at least one match
				e.preventDefault();
				const q = (searchInput.value || '').trim();
				if (!q || q.length < 2) {
					alert('Please type at least 2 characters and choose a team.');
					return;
				}
				try {
					const res = await fetch(`/teams/search?q=${encodeURIComponent(q)}`);
					const data = await res.json();
					const teams = Array.isArray(data.teams) ? data.teams : [];
					if (teams.length >= 1) {
						teamIdInput.value = teams[0].id;
						teamNameInput.value = teams[0].name;
						form.submit();
						return;
					}
					alert('No matching teams found. Please try a different name.');
				} catch(err) {
					console.error('Team auto-resolve failed:', err);
					alert('Team search failed. Please try again.');
				}
			});
		}
	}
});
