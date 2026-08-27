document.addEventListener('DOMContentLoaded', () => {
  // 1. VIEW TAB SWITCHER (Calendar Grid vs Fixture List vs Stats Overview)
  const tabBtns = document.querySelectorAll('.tab-btn');
  const viewSections = document.querySelectorAll('.view-section');

  const switchView = (viewName) => {
    tabBtns.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.view === viewName);
    });
    viewSections.forEach(section => {
      section.style.display = (section.id === `view-${viewName}`) ? 'block' : 'none';
    });
    localStorage.setItem('selected_view', viewName);
  };

  const savedView = localStorage.getItem('selected_view') || 'calendar';
  switchView(savedView);

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => switchView(btn.dataset.view));
  });

  // 2. DEMO PILLS HANDLER
  const demoBtns = document.querySelectorAll('.demo-pill-btn');
  demoBtns.forEach(btn => {
    btn.addEventListener('click', async () => {
      const teamId = btn.dataset.teamId;
      try {
        const res = await fetch('/api/demo-team', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ team_id: teamId })
        });
        if (res.ok) {
          window.location.href = '/calendar';
        }
      } catch (err) {
        console.error('Demo team selection failed:', err);
      }
    });
  });

  // 3. POPULAR CLUBS GRID
  const clubGrid = document.getElementById('club-grid');
  if (clubGrid) {
    const renderClub = (team) => {
      const card = document.createElement('div');
      card.className = 'club-card';

      const img = document.createElement('img');
      img.className = 'club-crest';
      img.src = team.crest || 'https://crests.football-data.org/57.png';
      img.alt = team.name || 'crest';
      img.onerror = () => { img.src = 'https://crests.football-data.org/57.png'; };

      const name = document.createElement('div');
      name.className = 'club-name';
      name.textContent = team.name || team.shortName || 'Club';

      const badge = document.createElement('div');
      badge.className = 'club-badge';
      badge.textContent = team.league || 'Select Club';

      card.appendChild(img);
      card.appendChild(name);
      card.appendChild(badge);

      card.addEventListener('click', async () => {
        try {
          const params = new URLSearchParams();
          params.append('team_id', team.id);
          params.append('team_name', team.name || '');
          params.append('q', team.name || '');

          const res = await fetch('/teams/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: params.toString()
          });

          if (res.ok) {
            window.location.href = '/calendar';
          }
        } catch (err) {
          console.error('Failed to select club', err);
        }
      });

      return card;
    };

    (async () => {
      try {
        const res = await fetch('/clubs/popular');
        const data = await res.json();
        if (res.ok && data.teams) {
          clubGrid.innerHTML = '';
          data.teams.forEach(t => clubGrid.appendChild(renderClub(t)));
        } else {
          clubGrid.innerHTML = '<div style="color: var(--text-muted);">No clubs available.</div>';
        }
      } catch (err) {
        console.error('Failed loading popular clubs:', err);
      }
    })();
  }

  // 4. CLIENT-SIDE LIVE MATCH FILTERING (Competition & Opponent Search)
  const compFilter = document.getElementById('comp-filter');
  const searchInputFilter = document.getElementById('match-search-input');

  const applyFilters = () => {
    const selectedComp = compFilter ? compFilter.value : 'ALL';
    const query = searchInputFilter ? searchInputFilter.value.trim().toLowerCase() : '';

    const matchItems = document.querySelectorAll('.match, .fixture-card');
    matchItems.forEach(item => {
      const itemComp = item.dataset.comp || '';
      const itemSearch = item.dataset.search || '';

      const compMatch = (selectedComp === 'ALL') || (itemComp === selectedComp);
      const searchMatch = !query || itemSearch.includes(query);

      if (compMatch && searchMatch) {
        item.style.display = '';
      } else {
        item.style.display = 'none';
      }
    });
  };

  if (compFilter) compFilter.addEventListener('change', applyFilters);
  if (searchInputFilter) searchInputFilter.addEventListener('input', applyFilters);

  // 5. WATCHED CHECKBOX TOGGLING WITH LIVE STATS RECALCULATION
  const updateStatsUI = () => {
    const allBoxes = document.querySelectorAll('.watch-checkbox');
    if (allBoxes.length === 0) return;

    const checkedIds = new Set();
    allBoxes.forEach(cb => {
      if (cb.checked) {
        checkedIds.add(cb.dataset.externalId);
      }
    });
    const watched = checkedIds.size;

    const totalEl = document.getElementById('stat-total');
    const watchedEl = document.getElementById('stat-watched');
    const pctEl = document.getElementById('stat-pct');
    const progressEl = document.getElementById('stat-progress');

    const calculatedTotal = totalEl ? (parseInt(totalEl.textContent) || 0) : 0;
    const pct = calculatedTotal > 0 ? ((watched / calculatedTotal) * 100).toFixed(1) : 0;

    if (watchedEl) watchedEl.textContent = watched;
    if (pctEl) pctEl.textContent = `${pct}%`;
    if (progressEl) progressEl.style.width = `${pct}%`;
  };

  const watchBoxes = document.querySelectorAll('.watch-checkbox');
  watchBoxes.forEach(cb => {
    cb.addEventListener('change', async (e) => {
      const externalId = e.target.getAttribute('data-external-id');
      const isChecked = e.target.checked;

      document.querySelectorAll(`.watch-checkbox[data-external-id="${externalId}"]`).forEach(sibling => {
        sibling.checked = isChecked;
        const parentMatch = sibling.closest('.match, .fixture-card');
        if (parentMatch) {
          parentMatch.classList.toggle('watched', isChecked);
        }
      });

      try {
        const res = await fetch(`/matches/${externalId}/toggle`, { method: 'POST' });
        if (!res.ok) throw new Error('Toggle failed');
        updateStatsUI();
      } catch (err) {
        console.error('Could not toggle watched status:', err);
        document.querySelectorAll(`.watch-checkbox[data-external-id="${externalId}"]`).forEach(sibling => {
          sibling.checked = !isChecked;
        });
      }
    });
  });

  // 6. AUTOCOMPLETE TEAM SEARCH WITH CREST BADGES
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
        empty.textContent = 'No matching clubs found';
        empty.style.color = 'var(--text-muted)';
        dropdown.appendChild(empty);
      } else {
        items.forEach(item => {
          const opt = document.createElement('div');
          opt.className = 'dropdown-item';

          if (item.crest) {
            const img = document.createElement('img');
            img.className = 'dropdown-crest';
            img.src = item.crest;
            img.onerror = () => { img.style.display = 'none'; };
            opt.appendChild(img);
          }

          const nameSpan = document.createElement('span');
          nameSpan.textContent = item.name;
          opt.appendChild(nameSpan);

          opt.addEventListener('click', () => {
            searchInput.value = item.name;
            if (teamIdInput) teamIdInput.value = item.id;
            if (teamNameInput) teamNameInput.value = item.name;
            closeDropdown();
            if (form) form.submit();
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
          if (res.ok) {
            renderDropdown(data.teams || []);
          }
        } catch (e) {
          console.error('Search error:', e);
        }
      }, 200);
    });

    document.addEventListener('click', (e) => {
      if (dropdown && !dropdown.contains(e.target) && e.target !== searchInput) {
        closeDropdown();
      }
    });
  }
});
