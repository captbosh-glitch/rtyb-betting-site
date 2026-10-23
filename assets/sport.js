/*
 * Games, Stats, Trends and team pages for every sport except NHL (NHL's
 * pages run their own code in template.html). Reads {slug}/data.json,
 * written by scripts/sport_build.py, and renders into #sportApp:
 *   <div id="sportApp" data-section="games|stats|trends|team" data-team="slug">
 *
 * Wording rules: the straight-up market is "SU" (never "ML"); records are
 * ATS W-L-P, SU W-L-T, O-U-P. Anything that needs odds counts only games
 * with odds and says "based on N games with odds".
 */
(function() {
  'use strict';
  var app = document.getElementById('sportApp');
  if (!app) return;
  var ROOT = (document.currentScript && document.currentScript.src || '').replace(/assets\/sport\.js.*$/, '');
  var SPORT_SLUG = document.body.getAttribute('data-sport-slug');
  var SECTION = app.getAttribute('data-section');
  var TEAM = app.getAttribute('data-team');
  var D = null;
  // The selected segment pill (1st Quarter / 1st Half / ...). Every page
  // load starts on the sport's first segment -- its order in
  // scripts/sports.py, 1st Quarter first -- and nothing is remembered
  // between visits, so a new sport gets the right default automatically.
  var SEG_CUR = null;

  // ---------------------------------------------------------------- utils
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function todayET() {
    var p = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
    var o = {}; p.forEach(function(x) { o[x.type] = x.value; });
    return o.year + '-' + o.month + '-' + o.day;
  }
  function dateLabel(d) {
    var t = todayET();
    if (d === t) return 'Today';
    var dt = new Date(d + 'T12:00:00Z');
    var y = new Date(dt.getTime() - 864e5).toISOString().slice(0, 10);
    var n = new Date(new Date(t + 'T12:00:00Z').getTime() - 864e5).toISOString().slice(0, 10);
    if (d === n) return 'Yesterday';
    return dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' });
  }
  function timeET(iso) {
    if (!iso) return '';
    var t = new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }) + ' ET';
    // Week view lists several days, so say which one.
    if (D && D.schedule === 'week') {
      t = new Date(iso).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'America/New_York' }) + ' · ' + t;
    }
    return t;
  }
  function signed(n) { return n == null ? '' : (n > 0 ? '+' : '') + n; }
  function fmtUnits(u) { var r = Math.round(u * 100) / 100; return (r > 0 ? '+' : '') + r.toFixed(2) + 'u'; }
  function unitsPill(u, priced) {
    if (!priced) return '<span class="u-pill u-none">&mdash;</span>';
    var r = Math.round(u * 100) / 100;
    var cls = r >= 3 ? 'u-pos2' : r > 0 ? 'u-pos1' : r === 0 ? 'u-zero' : r > -3 ? 'u-neg1' : 'u-neg2';
    return '<span class="u-pill ' + cls + '">' + fmtUnits(r) + '</span>';
  }
  function pct(w, l) { return (w + l) ? Math.round(1000 * w / (w + l)) / 10 : null; }
  function pctTxt(w, l) { var p = pct(w, l); return p == null ? '&mdash;' : p.toFixed(1) + '%'; }
  function rec(r) { return r ? r[0] + '-' + r[1] + '-' + r[2] : '0-0-0'; }
  function team(slug) {
    return D.teams[slug] || { name: (D.otherTeams || {})[slug] || slug, short: (D.otherTeams || {})[slug] || slug, code: '', color: null };
  }
  function teamUrl(slug) { return D.teams[slug] ? ROOT + SPORT_SLUG + '/teams/' + slug + '/' : null; }
  // The team's logo (assets/logos/{sport}/, light + dark versions switched
  // by CSS with the theme), or a team-color circle when there isn't one.
  function badge(slug, size) {
    var t = team(slug);
    size = size || 26;
    if (t.logo) {
      var base = ROOT + 'assets/logos/' + D.sport + '/' + slug;
      var st = ' style="width:' + size + 'px;height:' + size + 'px"';
      return t.logo === 'd'
        ? '<span class="tlogo"' + st + '><img class="tl-light" src="' + base + '.png" alt="" loading="lazy"><img class="tl-dark" src="' + base + '-dark.png" alt="" loading="lazy"></span>'
        : '<span class="tlogo"' + st + '><img src="' + base + '.png" alt="" loading="lazy"></span>';
    }
    var hex = (t.color || '5B6674').replace('#', '');
    var r = parseInt(hex.slice(0, 2), 16), g = parseInt(hex.slice(2, 4), 16), b = parseInt(hex.slice(4, 6), 16);
    var fg = (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? '#111' : '#FFF';
    var code = t.code || (t.short || '?').slice(0, 3).toUpperCase();
    return '<span class="team-badge" style="width:' + size + 'px;height:' + size + 'px;background:#' + hex + ';color:' + fg +
      ';font-size:' + Math.max(8, Math.round(size * (code.length > 3 ? 0.27 : 0.34))) + 'px">' + esc(code) + '</span>';
  }
  function teamLink(slug, text) {
    var u = teamUrl(slug);
    return u ? '<a class="gm-team" href="' + u + '">' + text + '</a>' : '<span class="gm-team">' + text + '</span>';
  }
  function shortName(slug) { var t = team(slug); return t.short || t.name; }
  function segs() { return D.segments; }
  function seg(k) { return D.segments.filter(function(s) { return s.key === k; })[0]; }
  function isRfi(k) { return D.sportType === 'baseball' && k === '1i'; }
  function getSeg() { return seg(SEG_CUR) ? SEG_CUR : D.segments[0].key; }
  function setSeg(k) { SEG_CUR = k; }
  function segToggle(id, cur, attr) {
    if (D.segments.length < 2) return '';
    return '<div class="seg-toggle" id="' + id + '">' + D.segments.map(function(s) {
      return '<button class="seg-btn" ' + (attr || 'data-seg') + '="' + s.key + '" aria-pressed="' + (s.key === cur) + '">' + esc(s.label) + '</button>';
    }).join('') + '</div>';
  }
  function chip(res) {
    var cls = { W: 'W', L: 'L', T: 'T', P: 'T', O: 'W', U: 'L', Y: 'W', N: 'L', NA: 'T' }[res] || 'T';
    return '<span class="result-pill ' + cls + '">' + esc(res === 'NA' ? '–' : res) + '</span>';
  }
  function emptyNote(html) { return '<div class="section-empty">' + html + '</div>'; }
  function oddsNote(n) {
    return '<span class="odds-n">based on ' + n + ' game' + (n === 1 ? '' : 's') + ' with odds</span>';
  }
  function allDates() { return Object.keys(D.games || {}).sort(); }

  // ----------------------------------------------------------- game card
  function flipRes(r) { return { W: 'L', L: 'W' }[r] || r; }

  function marketPills(g, k) {
    var o = (g.odds || {})[k] || {}, r = (g.res || {})[k] || {};
    var a = shortName(g.away), h = shortName(g.home);
    function pb(txt, res) { return '<span class="pb">' + esc(txt) + (res ? ' ' + chip(res) : '') + '</span>'; }
    if (isRfi(k)) {
      var m = o.nrfi_yrfi || {};
      return '<div class="odds-grid two">' +
        '<div class="pill"><span class="pill-label">YRFI</span><span class="pill-body">' + (m.yrfi != null || r.rfi ? pb(m.yrfi != null ? signed(m.yrfi) : 'Yes', r.rfi ? (r.rfi === 'Y' ? 'W' : r.rfi === 'N' ? 'L' : 'NA') : null) : '') + '</span></div>' +
        '<div class="pill"><span class="pill-label">NRFI</span><span class="pill-body">' + (m.nrfi != null || r.rfi ? pb(m.nrfi != null ? signed(m.nrfi) : 'No', r.rfi ? (r.rfi === 'N' ? 'W' : r.rfi === 'Y' ? 'L' : 'NA') : null) : '') + '</span></div>' +
        '</div>';
    }
    var ats = o.ats, ml = o.ml, tot = o.total;
    var na = r.na ? 'NA' : null;
    var atsBody = ats ? pb(a + ' ' + signed(ats.away.line), na || (r.ats || null)) + pb(h + ' ' + signed(ats.home.line), na || (r.ats ? flipRes(r.ats) : null)) : '';
    var suBody = (ml || r.su) ? pb(a + (ml ? ' ' + signed(ml.away) : ''), na || (r.su || null)) + pb(h + (ml ? ' ' + signed(ml.home) : ''), na || (r.su ? flipRes(r.su) : null)) : '';
    var totBody = tot ? pb('O/U ' + tot.line, na || (r.tot ? (r.tot === 'P' ? 'P' : r.tot) : null)) : '';
    return '<div class="odds-grid">' +
      '<div class="pill"><span class="pill-label">ATS</span><span class="pill-body">' + atsBody + '</span></div>' +
      '<div class="pill"><span class="pill-label">SU</span><span class="pill-body">' + suBody + '</span></div>' +
      '<div class="pill"><span class="pill-label">Total</span><span class="pill-body">' + totBody + '</span></div>' +
      '</div>';
  }

  function segScoreLine(g, k) {
    var r = (g.res || {})[k];
    var s = seg(k);
    if (r && r.na) return '<div class="gm-seg-line">' + esc(s.tag) + ': No Action</div>';
    var sc = r && r.sc;
    if (!sc && (g.state === 'in' || g.state === 'final')) {
      // partial: sum what's played so far
      return '<div class="gm-seg-line">' + esc(s.label) + ': in progress</div>';
    }
    if (!sc) return '';
    return '<div class="gm-seg-line">' + esc(s.label) + ': <b class="mono">' + sc[0] + '–' + sc[1] + '</b></div>';
  }

  function statusText(g) {
    if (g.state === 'final') return 'Final' + (g.detail && g.detail !== 'Final' ? ' · ' + g.detail.replace(/^Final\/?/, '') : '');
    if (g.state === 'in') return 'Live · ' + g.detail;
    if (g.state === 'pre') return timeET(g.start);
    return g.detail || g.state;
  }

  function gameCard(g, k, opts) {
    opts = opts || {};
    var score = (g.state === 'final' || g.state === 'in') && g.as != null
      ? '<div class="game-final-score">' + g.as + '–' + g.hs + '</div>' : '';
    var toggle = (D.segments.length > 1 && !opts.noToggle) ? '<div class="seg-toggle card-seg">' + D.segments.map(function(s) {
      return '<button class="seg-btn" data-card-seg="' + s.key + '" aria-pressed="' + (s.key === k) + '">' + esc(s.tag) + '</button>';
    }).join('') + '</div>' : '';
    return '<div class="game-card" data-game="' + esc(g.id) + '">' +
      '<div class="gm-time">' + esc(statusText(g)) + (g.note ? ' · ' + esc(g.note) : '') + '</div>' +
      '<div class="game-card-head">' +
        '<div class="game-matchup">' +
          teamLink(g.away, badge(g.away) + esc(shortName(g.away))) + '<span class="gm-at">@</span>' +
          teamLink(g.home, badge(g.home) + esc(shortName(g.home))) +
        '</div>' + score +
      '</div>' + toggle +
      '<div class="card-body">' + segScoreLine(g, k) + marketPills(g, k) + '</div>' +
    '</div>';
  }

  function wireCardToggles(root) {
    root.addEventListener('click', function(e) {
      var b = e.target.closest('[data-card-seg]');
      if (!b) return;
      var card = b.closest('.game-card');
      var g = findGame(card.getAttribute('data-game'));
      if (!g) return;
      var k = b.getAttribute('data-card-seg');
      card.querySelectorAll('[data-card-seg]').forEach(function(x) { x.setAttribute('aria-pressed', String(x === b)); });
      card.querySelector('.card-body').innerHTML = segScoreLine(g, k) + marketPills(g, k);
    });
  }

  var GAME_INDEX = null;
  function findGame(id) {
    if (!GAME_INDEX) {
      GAME_INDEX = {};
      Object.keys(D.games).forEach(function(d) { D.games[d].forEach(function(g) { GAME_INDEX[g.id] = g; }); });
    }
    return GAME_INDEX[id];
  }

  // ------------------------------------------------------------ date bar
  function dateBar(cur, dates) {
    return '<div class="date-bar">' +
      '<button class="date-nav" id="datePrev" aria-label="Previous day"' + (cur <= dates[0] ? ' disabled' : '') + '>&lsaquo;</button>' +
      '<div class="date-label-wrap"><span class="date-label">' + esc(dateLabel(cur)) + '</span>' +
      (cur !== todayET() ? '<button class="date-today-btn" id="dateTodayBtn" type="button">Today</button>' : '') + '</div>' +
      '<button class="date-nav" id="dateNext" aria-label="Next day"' + (cur >= dates[dates.length - 1] ? ' disabled' : '') + '>&rsaquo;</button>' +
    '</div>';
  }
  function step(dates, cur, dir) {
    if (dir > 0) { for (var i = 0; i < dates.length; i++) if (dates[i] > cur) return dates[i]; return cur; }
    for (var j = dates.length - 1; j >= 0; j--) if (dates[j] < cur) return dates[j];
    return cur;
  }
  // Today, else the next date with games, else the last one.
  function defaultDate(dates) {
    var t = todayET();
    if (dates.indexOf(t) !== -1) return t;
    var next = dates.filter(function(d) { return d > t; })[0];
    return next || dates[dates.length - 1];
  }
  function wireDateBar(dates, cur, go) {
    var p = document.getElementById('datePrev'), n = document.getElementById('dateNext'), t = document.getElementById('dateTodayBtn');
    if (p) p.onclick = function() { go(step(dates, cur, -1)); };
    if (n) n.onclick = function() { go(step(dates, cur, 1)); };
    if (t) t.onclick = function() { go(defaultDate(dates)); };
  }
  function urlDate() {
    var d = new URLSearchParams(location.search).get('date');
    return /^\d{4}-\d{2}-\d{2}$/.test(d || '') ? d : null;
  }
  function setUrlDate(d) {
    var u = new URL(location.href);
    u.searchParams.set('date', d);
    history.replaceState(null, '', u);
  }

  // ---------------------------------------------------------- daily recap
  function recapHtml(games, k) {
    var done = games.filter(function(g) { return g.res && g.res[k] && !g.res[k].na && g.state === 'final'; });
    if (!done.length) return '';
    var rows = [];
    function row(label, recTxt, pctVal, units, priced, note) {
      rows.push('<div class="ds-row"><span class="ds-label">' + label + (note ? ' ' + note : '') + '</span><span class="ds-right">' +
        '<span class="ds-record ds-col-rec">' + recTxt + '</span><span class="ds-col-pct">' + (pctVal == null ? '&mdash;' : pctVal.toFixed(0) + '%') + '</span>' +
        '<span class="ds-col-units">' + (priced ? unitsPill(units, true) : '<span class="u-pill u-none">&mdash;</span>') + '</span></span></div>');
    }
    if (isRfi(k)) {
      var y = 0, n = 0, uy = 0, un = 0, pr = 0;
      done.forEach(function(g) {
        var r = g.res[k];
        if (r.rfi === 'Y') y++; else if (r.rfi === 'N') n++;
        if (r.u && r.u.rfi) { uy += r.u.rfi[0]; un += r.u.rfi[1]; pr++; }
      });
      row('NRFI', n + '-' + y, pct(n, y), un, pr, pr ? oddsNote(pr) : '');
      row('YRFI', y + '-' + n, pct(y, n), uy, pr, '');
    } else {
      var home = [0, 0, 0, 0, 0], fav = [0, 0, 0, 0, 0], favAts = [0, 0, 0, 0, 0], ou = [0, 0, 0, 0, 0];
      done.forEach(function(g) {
        var r = g.res[k], o = (g.odds || {})[k] || {};
        var hr = flipRes(r.su);
        home[hr === 'W' ? 0 : hr === 'L' ? 1 : 2]++;
        if (r.u && r.u.su) { home[3] += r.u.su[1]; home[4]++; }
        var f = favSide(o);
        if (f) {
          var fr = f === 'away' ? r.su : flipRes(r.su);
          fav[fr === 'W' ? 0 : fr === 'L' ? 1 : 2]++;
          if (r.u && r.u.su) { fav[3] += r.u.su[f === 'away' ? 0 : 1]; fav[4]++; }
          if (r.ats) {
            var fa = f === 'away' ? r.ats : flipRes(r.ats);
            favAts[fa === 'W' ? 0 : fa === 'L' ? 1 : 2]++;
            if (r.u && r.u.ats) { favAts[3] += r.u.ats[f === 'away' ? 0 : 1]; favAts[4]++; }
          }
        }
        if (r.tot) {
          ou[r.tot === 'O' ? 0 : r.tot === 'U' ? 1 : 2]++;
          if (r.u && r.u.tot) { ou[3] += r.u.tot[0]; ou[4]++; }
        }
      });
      row('Home teams SU', rec(home), pct(home[0], home[1]), home[3], home[4], '');
      if (fav[0] + fav[1] + fav[2]) row('Favorites SU', rec(fav), pct(fav[0], fav[1]), fav[3], fav[4], oddsNote(fav[0] + fav[1] + fav[2]));
      if (favAts[0] + favAts[1] + favAts[2]) row('Favorites ATS', rec(favAts), pct(favAts[0], favAts[1]), favAts[3], favAts[4], oddsNote(favAts[0] + favAts[1] + favAts[2]));
      if (ou[0] + ou[1] + ou[2]) row('Overs (O-U-P)', rec(ou), pct(ou[0], ou[1]), ou[3], ou[4], oddsNote(ou[0] + ou[1] + ou[2]));
    }
    return '<h3>Recap &middot; ' + esc(seg(k).label) + ' &middot; ' + done.length + ' game' + (done.length === 1 ? '' : 's') + '</h3>' +
      '<div class="ds-row ds-head"><span></span><span class="ds-right"><span class="ds-col-rec">Record</span><span class="ds-col-pct">Win %</span><span class="ds-col-units">Units</span></span></div>' +
      rows.join('');
  }

  // ------------------------------------------------- Games page, by week
  // NFL / NCAAF: one week at a time (ESPN's weeks). Games still to play
  // come first by kickoff (live ones keep their spot), finals drop to the
  // bottom as they finish, and postponed / canceled games come last.
  function weekGames(key) {
    var out = [];
    allDates().forEach(function(d) { D.games[d].forEach(function(g) { if (g.wk === key) out.push(g); }); });
    var rank = function(g) { return g.state === 'final' ? 1 : (g.state === 'pre' || g.state === 'in') ? 0 : 2; };
    return out.sort(function(a, b) { return (rank(a) - rank(b)) || ((a.start || '') < (b.start || '') ? -1 : (a.start || '') > (b.start || '') ? 1 : 0); });
  }
  function shortDay(d) { return new Date(d + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }); }
  function weekRange(w) { return w.start === w.end ? shortDay(w.start) : shortDay(w.start) + '–' + shortDay(w.end); }
  // This week = the first week that still has a game to play; else the last.
  function currentWeek(weeks) {
    for (var i = 0; i < weeks.length; i++) {
      if (weekGames(weeks[i].key).some(function(g) { return g.state === 'pre' || g.state === 'in'; })) return weeks[i].key;
    }
    return weeks[weeks.length - 1].key;
  }
  function renderGamesByWeek() {
    var weeks = D.weeks || [];
    if (!weeks.length) { app.innerHTML = emptyNote('No ' + esc(D.label) + ' games loaded yet.'); return; }
    var keys = weeks.map(function(w) { return w.key; });
    var want = new URLSearchParams(location.search).get('week');
    var cur = keys.indexOf(want) !== -1 ? want : currentWeek(weeks);
    var thisWeek = currentWeek(weeks);
    function go(k) {
      cur = k;
      var u = new URL(location.href); u.searchParams.set('week', k); u.searchParams.delete('date');
      history.replaceState(null, '', u);
      draw();
    }
    function draw() {
      var i = keys.indexOf(cur), w = weeks[i];
      var games = weekGames(cur);
      var k = getSeg();
      var html = '<div class="date-bar">' +
        '<button class="date-nav" id="weekPrev" aria-label="Previous week"' + (i <= 0 ? ' disabled' : '') + '>&lsaquo;</button>' +
        '<div class="date-label-wrap"><span class="date-label">' + esc(w.label) + ' <span class="week-range">' + esc(weekRange(w)) + '</span></span>' +
        (cur !== thisWeek ? '<button class="date-today-btn" id="weekNowBtn" type="button">This week</button>' : '') + '</div>' +
        '<button class="date-nav" id="weekNext" aria-label="Next week"' + (i >= keys.length - 1 ? ' disabled' : '') + '>&rsaquo;</button></div>';
      if (D.segments.length > 1) html += '<div class="sport-seg-row"><span class="control-label">Show</span>' + segToggle('pageSeg', k) + '</div>';
      var recap = recapHtml(games, k);
      if (recap) html += '<div class="daily-summary">' + recap + '</div>';
      if (!games.length) html += '<div class="no-games-note">No ' + esc(D.label) + ' games this week.</div>';
      html += '<div class="games-list">' + games.map(function(g) { return gameCard(g, k); }).join('') + '</div>';
      app.innerHTML = html;
      var p = document.getElementById('weekPrev'), n = document.getElementById('weekNext'), t = document.getElementById('weekNowBtn');
      if (p) p.onclick = function() { if (i > 0) go(keys[i - 1]); };
      if (n) n.onclick = function() { if (i < keys.length - 1) go(keys[i + 1]); };
      if (t) t.onclick = function() { go(thisWeek); };
      var ps = document.getElementById('pageSeg');
      if (ps) ps.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { setSeg(b.getAttribute('data-seg')); draw(); } };
    }
    wireCardToggles(app);
    draw();
  }

  // ---------------------------------------------------------- Games page
  function renderGames() {
    if (D.schedule === 'week') { renderGamesByWeek(); return; }
    var dates = allDates();
    if (!dates.length) {
      app.innerHTML = emptyNote('No ' + esc(D.label) + ' games loaded yet.');
      return;
    }
    var cur = urlDate() || defaultDate(dates);
    function go(d) { cur = d; setUrlDate(d); draw(); }
    function draw() {
      var games = D.games[cur] || [];
      var k = getSeg();
      var html = dateBar(cur, dates);
      if (D.segments.length > 1) {
        html += '<div class="sport-seg-row"><span class="control-label">Show</span>' + segToggle('pageSeg', k) + '</div>';
      }
      var recap = recapHtml(games, k);
      if (recap) html += '<div class="daily-summary">' + recap + '</div>';
      if (!games.length) html += '<div class="no-games-note">No ' + esc(D.label) + ' games on ' + esc(dateLabel(cur)) + '.</div>';
      html += '<div class="games-list">' + games.map(function(g) { return gameCard(g, k); }).join('') + '</div>';
      app.innerHTML = html;
      wireDateBar(dates, cur, go);
      var ps = document.getElementById('pageSeg');
      if (ps) ps.onclick = function(e) {
        var b = e.target.closest('[data-seg]');
        if (!b) return;
        setSeg(b.getAttribute('data-seg'));
        draw();
      };
    }
    wireCardToggles(app);
    draw();
  }

  // ---------------------------------------------------------- Stats page
  // Built like NHL's Stats page: a Season Results card for the selected
  // period, then one card per team. Records are W-L-T (SU), W-L-P (ATS)
  // and O-U-P (totals) -- ties and pushes always shown, never folded into
  // losses -- with units wherever odds were saved. Each block sits in its
  // own section so premium sections can be added later.
  function cnt(r, i, tot) { return '<span class="sc-val">' + r[i] + ' <small>(' + (tot ? Math.round(100 * r[i] / tot) : 0) + '%)</small></span>'; }
  function scLine(label, r, i, tot) { return '<div class="sc-line"><span>' + label + '</span>' + cnt(r, i, tot) + '</div>'; }
  function scUnits(pairs) {
    var shown = pairs.filter(function(p) { return p[1][4]; });
    return shown.length ? '<div class="sc-units">' + shown.map(function(p) {
      return '<span class="sc-u">' + p[0] + ' ' + unitsPill(p[1][3], true) + '</span>';
    }).join('') + '</div>' : '';
  }
  function scBlock(title, sub, lines, units, note) {
    return '<div class="sc-block"><h4>' + title + '</h4>' + (sub ? '<div class="sc-sub">' + sub + '</div>' : '') + lines + (units || '') +
      (note ? '<div class="sc-note">' + note + '</div>' : '') + '</div>';
  }
  function seasonResultsHtml(lg, k, controls, weekLine) {
    var head = '<div class="season-card-head"><h3>Season Results</h3><div class="sc-right">' + (controls || '') +
      '<span class="sc-gp">' + (lg ? lg.gp : 0) + ' GP</span></div></div>' + (weekLine || '');
    if (!lg || !lg.gp) return '<div class="season-card">' + head + emptyNote('No graded games in this range yet.') + '</div>';
    var blocks;
    if (isRfi(k)) {
      var y = lg.yrfi, n = y[0] + y[1];
      blocks = scBlock('NRFI / YRFI', 'Run scored in the 1st inning', scLine('YRFI', y, 0, n) + scLine('NRFI', y, 1, n),
        scUnits([['YRFI', y], ['NRFI', lg.nrfi || [0, 0, 0, 0, 0]]]), y[4] ? oddsNote(y[4]) : 'Units need saved odds');
    } else {
      var h = lg.home, gp = lg.gp, f = lg.fav_su, fa = lg.fav_ats, o = lg.over;
      var fn = f[0] + f[1] + f[2], an = fa[0] + fa[1] + fa[2], on = o[0] + o[1] + o[2];
      blocks =
        scBlock('SU (H/A)', 'Straight up, ties shown', scLine('Home', h, 0, gp) + scLine('Away', h, 1, gp) + scLine('Tie', h, 2, gp),
          scUnits([['Home', h], ['Away', lg.away || [0, 0, 0, 0, 0]]])) +
        scBlock('SU (F/D)', 'Favorite vs underdog', fn ? scLine('Favorite', f, 0, fn) + scLine('Underdog', f, 1, fn) + scLine('Tie', f, 2, fn) : emptyNote('Needs odds.'),
          scUnits([['Fav', f], ['Dog', lg.dog_su || [0, 0, 0, 0, 0]]]), fn ? oddsNote(fn) : '') +
        scBlock('ATS (F/D)', 'Against the spread, pushes shown', an ? scLine('Favorite', fa, 0, an) + scLine('Underdog', fa, 1, an) + scLine('Push', fa, 2, an) : emptyNote('Needs odds.'),
          scUnits([['Fav', fa], ['Dog', lg.dog_ats || [0, 0, 0, 0, 0]]]), an ? oddsNote(an) : '') +
        scBlock('Total (O/U)', 'Over-Under-Push', on ? scLine('Over', o, 0, on) + scLine('Under', o, 1, on) + scLine('Push', o, 2, on) : emptyNote('Needs odds.'),
          scUnits([['Over', o], ['Under', lg.under || [0, 0, 0, 0, 0]]]), on ? oddsNote(on) : '');
    }
    return '<div class="season-card">' + head + '<div class="sc-grid">' + blocks + '</div></div>';
  }

  // One team's card: records for the period (W-L-T / W-L-P / O-U-P), the
  // rate (ties and pushes left out) and units where odds were saved.
  function recRow(label, r, rateOf, priced) {
    var n = r[0] + r[1] + r[2];
    return '<div class="tc-row"><span class="tc-label">' + label + '</span>' +
      '<span class="tc-rec mono">' + (n ? r[0] + '–' + r[1] + '–' + r[2] : '&mdash;') + '</span>' +
      '<span class="tc-pct">' + (n ? pctTxt(r[0], r[1]) : '') + '</span>' +
      '<span class="tc-u">' + (priced ? unitsPill(r[3], r[4]) : '') + '</span></div>';
  }
  function teamCard(slug, k, compact) {
    var t = team(slug), st = ((STATS.teams || {})[slug] || {})[k];
    var head = '<div class="tc-head">' + teamLink(slug, badge(slug, compact ? 26 : 30) + '<span class="tc-name">' + esc(t.name) + '</span>') +
      '<span class="tc-gp mono">' + (st ? st.gp + ' GP' : '') + '</span></div>';
    if (!st) return '<div class="tc-card">' + head + '<div class="tc-none">No ' + esc(seg(k).label) + ' results yet.</div></div>';
    var rows;
    if (isRfi(k)) {
      rows = recRow('YRFI', st.yrfi, true, true) +
        '<div class="tc-row"><span class="tc-label">Scored 1st</span><span class="tc-rec mono">' + st.scored + '/' + st.gp + '</span><span class="tc-pct">' + pctTxt(st.scored, st.gp - st.scored) + '</span><span class="tc-u"></span></div>' +
        '<div class="tc-row"><span class="tc-label">Allowed 1st</span><span class="tc-rec mono">' + st.allowed + '/' + st.gp + '</span><span class="tc-pct">' + pctTxt(st.allowed, st.gp - st.allowed) + '</span><span class="tc-u"></span></div>';
    } else {
      rows = recRow('SU', st.su, true, true) + recRow('ATS', st.ats, true, true) + recRow('O/U', st.over, true, true) +
        (compact ? '' : recRow('Home SU', st.home, true, false) + recRow('Away SU', st.away, true, false));
    }
    return '<div class="tc-card">' + head + rows + '</div>';
  }

  // Sort keys for the team cards (rates leave ties / pushes out).
  var TC_SORTS = [
    ['su', 'SU win %', function(st) { return st.su ? pct(st.su[0], st.su[1]) : pct(st.yrfi[1], st.yrfi[0]); }],
    ['ats', 'ATS cover %', function(st) { return st.ats ? pct(st.ats[0], st.ats[1]) : null; }],
    ['over', 'Over %', function(st) { return st.over ? pct(st.over[0], st.over[1]) : st.yrfi ? pct(st.yrfi[0], st.yrfi[1]) : null; }],
    ['suu', 'SU units', function(st) { return st.su && st.su[4] ? st.su[3] : null; }],
    ['atsu', 'ATS units', function(st) { return st.ats && st.ats[4] ? st.ats[3] : null; }],
  ];
  var tcState = { sort: 'su', view: 'conf', conf: '', q: '' };

  // Team cards with search, sort and (NCAAF) conference grouping. `opts`:
  // {compact, group: 'conf' | 'division' | 'letter' | null}
  function teamCardsHtml(k, opts) {
    var sortFn = (TC_SORTS.filter(function(s) { return s[0] === tcState.sort; })[0] || TC_SORTS[0])[2];
    var slugs = Object.keys(D.teams).filter(function(s) {
      var t = D.teams[s];
      if (tcState.q && (t.name + ' ' + (t.code || '') + ' ' + (t.short || '')).toLowerCase().indexOf(tcState.q) === -1) return false;
      if (tcState.conf && t.conference !== tcState.conf) return false;
      return true;
    });
    function val(s) { var st = ((STATS.teams || {})[s] || {})[k]; return st ? sortFn(st) : null; }
    slugs.sort(function(a, b) {
      var va = val(a), vb = val(b);
      if (va == null && vb == null) return D.teams[a].name < D.teams[b].name ? -1 : 1;
      if (va == null) return 1; if (vb == null) return -1;
      if (va !== vb) return vb - va;
      // same rate: the bigger sample first (6-0 above 3-0-3)
      var ra = STATS.teams[a][k], rb = STATS.teams[b][k], ma = ra.su || ra.yrfi, mb = rb.su || rb.yrfi;
      return (mb[0] + mb[1]) - (ma[0] + ma[1]) || (D.teams[a].name < D.teams[b].name ? -1 : 1);
    });
    if (!slugs.length) return '<div class="tc-none">No teams match.</div>';
    var group = opts.group;
    if (group === 'conf' && tcState.view === 'all') group = null;
    if (!group) return '<div class="tc-grid">' + slugs.map(function(s) { return teamCard(s, k, opts.compact); }).join('') + '</div>';
    var groups = {};
    slugs.forEach(function(s) {
      var t = D.teams[s];
      var g = group === 'conf' ? (t.conference || 'Other') : group === 'letter' ? t.name.charAt(0).toUpperCase()
        : (t.division || t.conference || 'Teams').replace('American League', 'AL').replace('National League', 'NL');
      (groups[g] = groups[g] || []).push(s);
    });
    // Conference headers A-Z (independents last); divisions in league order.
    var names = Object.keys(groups).sort(function(a, b) {
      if (/Independent/.test(a) !== /Independent/.test(b)) return /Independent/.test(a) ? 1 : -1;
      return a < b ? -1 : a > b ? 1 : 0;
    });
    return names.map(function(g) {
      return '<section class="tc-group"><h3 class="tc-group-title">' + esc(g) + ' <span class="tc-count">' + groups[g].length + '</span></h3>' +
        '<div class="tc-grid">' + groups[g].map(function(s) { return teamCard(s, k, opts.compact); }).join('') + '</div></section>';
    }).join('');
  }
  function teamControlsHtml(k, opts) {
    var confs = {};
    Object.keys(D.teams).forEach(function(s) { if (D.teams[s].conference) confs[D.teams[s].conference] = 1; });
    var college = opts.group === 'conf';
    return '<div class="controls"><div class="control-group">' +
      (college ? '<div class="seg-toggle" id="tcView"><button class="seg-btn" data-view="conf" aria-pressed="' + (tcState.view === 'conf') + '">By conference</button>' +
        '<button class="seg-btn" data-view="all" aria-pressed="' + (tcState.view === 'all') + '">All</button></div>' : '') + '</div>' +
      '<div class="control-group">' +
      (college ? '<select class="conf-select" id="tcConf"><option value="">All conferences</option>' +
        Object.keys(confs).sort().map(function(c) { return '<option' + (c === tcState.conf ? ' selected' : '') + '>' + esc(c) + '</option>'; }).join('') + '</select>' : '') +
      '<select class="conf-select" id="tcSort" aria-label="Sort teams">' + TC_SORTS.map(function(s) {
        return '<option value="' + s[0] + '"' + (s[0] === tcState.sort ? ' selected' : '') + '>Sort: ' + s[1] + '</option>';
      }).join('') + '</select>' +
      '<input class="search-box" id="tcSearch" type="search" placeholder="Search team&hellip;" value="' + esc(tcState.q) + '"></div></div>';
  }
  function wireTeamControls(draw) {
    var segEl = document.getElementById('tcSeg');
    if (segEl) segEl.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { setSeg(b.getAttribute('data-seg')); draw(); } };
    var v = document.getElementById('tcView');
    if (v) v.onclick = function(e) { var b = e.target.closest('[data-view]'); if (b) { tcState.view = b.getAttribute('data-view'); draw(); } };
    var c = document.getElementById('tcConf');
    if (c) c.onchange = function() { tcState.conf = c.value; draw(); };
    var so = document.getElementById('tcSort');
    if (so) so.onchange = function() { tcState.sort = so.value; draw(); };
    var q = document.getElementById('tcSearch');
    if (q) q.oninput = function() {
      tcState.q = q.value.trim().toLowerCase(); var pos = q.selectionStart; draw();
      var q2 = document.getElementById('tcSearch'); q2.focus(); q2.setSelectionRange(pos, pos);
    };
  }

  // ------------------------------------------------- per-game aggregation
  // Records from the graded games themselves (res + per-side units on each
  // game), so any side, market or date range can be counted in the browser.
  // res is from the away side: su / ats W-L-T(P); tot O-U-P; rfi Y / N.
  // u[market] = [away units, home units] ([over, under] for totals).
  // Games with any graded period (a live game counts once its 1st quarter /
  // half / inning is final, the same as the build's season stats).
  function finalGames(from, to) {
    var out = [];
    allDates().forEach(function(d) {
      if ((from && d < from) || (to && d > to)) return;
      D.games[d].forEach(function(g) { if (g.res) out.push(g); });
    });
    return out;
  }
  // One bet's result on a game for `slug` ('W' / 'L' / 'T', or null when
  // the game has no grade in that market) and its units (null = no price).
  function betResult(g, k, market, slug) {
    var r = (g.res || {})[k];
    if (!r) return null;
    var home = g.home === slug, i = home ? 1 : 0, u = r.u || {};
    if (market === 'su' || market === 'ats') {
      var x = r[market];
      if (!x || x === 'NA') return null;
      x = home ? flipRes(x) : x;
      return { res: x === 'P' ? 'T' : x, u: u[market] ? u[market][i] : null };
    }
    if (market === 'tot') {
      if (!r.tot || r.tot === 'NA') return null;
      return { res: { O: 'W', U: 'L', P: 'T' }[r.tot], u: u.tot ? u.tot[0] : null };
    }
    if (market === 'rfi') {
      if (r.rfi !== 'Y' && r.rfi !== 'N') return null;
      return { res: r.rfi === 'Y' ? 'W' : 'L', u: u.rfi ? u.rfi[0] : null };
    }
    return null;
  }
  function newAgg() { return { w: 0, l: 0, t: 0, gp: 0, units: 0, priced: 0 }; }
  function addAgg(a, b) {
    if (!b) return;
    a.gp++;
    if (b.res === 'W') a.w++; else if (b.res === 'L') a.l++; else a.t++;
    if (b.u != null) { a.units += b.u; a.priced++; }
  }
  // side: 'all' | 'home' | 'away'
  function teamAgg(slug, k, market, side, games) {
    var a = newAgg();
    games.forEach(function(g) {
      if (g.away !== slug && g.home !== slug) return;
      if (side === 'home' && g.home !== slug) return;
      if (side === 'away' && g.away !== slug) return;
      addAgg(a, betResult(g, k, market, slug));
    });
    a.pct = (a.w + a.l) ? a.w / (a.w + a.l) : null;   // ties / pushes left out
    return a;
  }
  function marketsFor(k) {
    return isRfi(k) ? [['rfi', 'YRFI']] : [['su', 'Moneyline'], ['ats', 'ATS'], ['tot', 'Over']];
  }

  // ----------------------------------------------------------- Teams page
  // The NHL Teams table (same markup and classes): one row per team with
  // logo, name, record, win % bar and units, for a period, market and side;
  // sortable, with search. College sports group the rows by conference.
  var tlState = { market: 'su', side: 'all', q: '', sortKey: 'units', sortDir: -1 };
  function confOrder(a, b) {
    if (/Independent/.test(a) !== /Independent/.test(b)) return /Independent/.test(a) ? 1 : -1;
    return a < b ? -1 : a > b ? 1 : 0;
  }
  function renderTeamsIndex() {
    if (!D.season) return;   // keep the plain list
    var college = D.sport === 'ncaaf' || D.sport === 'ncaab';
    var games = finalGames();
    function pills(attr, opts, cur) {
      return opts.map(function(o) { return '<button class="seg-btn" ' + attr + '="' + o[0] + '" aria-pressed="' + (o[0] === cur) + '">' + o[1] + '</button>'; }).join('');
    }
    function rows(k) {
      return Object.keys(D.teams).filter(function(s) {
        var t = D.teams[s];
        return !tlState.q || (t.name + ' ' + (t.code || '') + ' ' + (t.short || '')).toLowerCase().indexOf(tlState.q) !== -1;
      }).map(function(s) {
        var a = teamAgg(s, k, tlState.market, tlState.side, games);
        a.slug = s; a.name = D.teams[s].name; a.conf = D.teams[s].conference || 'Other';
        a.wins = a.w; a.u = a.priced ? a.units : null;
        return a;
      });
    }
    function sortRows(list) {
      var key = tlState.sortKey === 'units' ? 'u' : tlState.sortKey, dir = tlState.sortDir;
      return list.sort(function(a, b) {
        if (key === 'name') return a.name.localeCompare(b.name) * dir;
        var va = a[key], vb = b[key];
        if (va === vb || (va == null && vb == null)) return (b.w + b.l) - (a.w + a.l) || a.name.localeCompare(b.name);
        if (va == null) return 1;
        if (vb == null) return -1;
        return (va - vb) * dir;
      });
    }
    function rowHtml(r) {
      var p = r.pct == null ? null : Math.round(r.pct * 100);
      return '<tr data-href="' + teamUrl(r.slug) + '">' +
        '<td class="team-cell">' + badge(r.slug, 24) + '<a class="tl-name" href="' + teamUrl(r.slug) + '">' + esc(r.name) + '</a></td>' +
        '<td class="num rec-cell mono col-rec"><b>' + (r.gp ? r.w + '-' + r.l + '-' + r.t : '&mdash;') + '</b></td>' +
        '<td class="num col-pct"><div class="pct-cell"><div class="pct-bar"><span style="width:' + (p || 0) + '%"></span></div><span class="pct-num mono">' + (p == null ? '&mdash;' : p + '%') + '</span></div></td>' +
        '<td class="num col-units">' + unitsPill(r.units, r.priced) + '</td></tr>';
    }
    function draw() {
      var k = getSeg(), mk = marketsFor(k);
      if (!mk.some(function(m) { return m[0] === tlState.market; })) tlState.market = mk[0][0];
      var list = sortRows(rows(k)), body;
      if (!list.length) body = '<tr><td colspan="4"><div class="empty-state">No teams match &ldquo;' + esc(tlState.q) + '&rdquo;.</div></td></tr>';
      else if (college) {
        var groups = {};
        list.forEach(function(r) { (groups[r.conf] = groups[r.conf] || []).push(r); });
        body = Object.keys(groups).sort(confOrder).map(function(c) {
          return '<tr class="tl-group"><td colspan="4">' + esc(c) + ' <span class="tc-count">' + groups[c].length + '</span></td></tr>' + groups[c].map(rowHtml).join('');
        }).join('');
      } else body = list.map(rowHtml).join('');
      var recLabel = { su: 'Record', ats: 'ATS', tot: 'O-U-P', rfi: 'Y-N' }[tlState.market];
      var pctLabel = { su: 'Win %', ats: 'Cover %', tot: 'Over %', rfi: 'YRFI %' }[tlState.market];
      function th(key, label, cls) {
        var on = tlState.sortKey === key;
        return '<th class="' + (cls || '') + '" data-sort="' + key + '">' + label + '<span class="arrow">' + (on ? (tlState.sortDir < 0 ? '▼' : '▲') : '') + '</span></th>';
      }
      app.innerHTML = '<div id="teamView"><div class="controls">' +
        (D.segments.length > 1 ? '<div class="control-group"><span class="control-label">Period</span>' + pills('data-tl-seg', D.segments.map(function(s) { return [s.key, esc(s.label)]; }), k) + '</div>' : '') +
        (mk.length > 1 ? '<div class="control-group"><span class="control-label">Market</span>' + pills('data-tl-market', mk, tlState.market) + '</div>' : '') +
        '<div class="control-group"><span class="control-label">Side</span>' + pills('data-tl-side', [['all', 'All'], ['home', 'Home'], ['away', 'Away']], tlState.side) + '</div>' +
        '<div class="control-group"><input class="search-box" id="tlSearch" type="search" placeholder="Search team&hellip;" value="' + esc(tlState.q) + '"></div></div>' +
        '<div class="table-wrap"><div class="table-scroll"><table id="leagueTable"><thead><tr>' +
        th('name', 'Team') + th('wins', recLabel, 'num col-rec') + th('pct', pctLabel, 'num col-pct') + th('units', 'Units', 'num col-units') +
        '</tr></thead><tbody id="leagueBody">' + body + '</tbody></table></div></div>' +
        '<p class="tl-note">' + esc(seg(k).label) + ' &middot; ' + esc(D.seasonLabel) + ' season &middot; ties and pushes count in the record but not the %' +
        (tlState.market !== 'su' && tlState.market !== 'rfi' ? ' &middot; ATS and totals need saved odds' : '') + '</p></div>';
      app.querySelectorAll('[data-tl-seg]').forEach(function(b) { b.onclick = function() { setSeg(b.getAttribute('data-tl-seg')); draw(); }; });
      app.querySelectorAll('[data-tl-market]').forEach(function(b) { b.onclick = function() { tlState.market = b.getAttribute('data-tl-market'); draw(); }; });
      app.querySelectorAll('[data-tl-side]').forEach(function(b) { b.onclick = function() { tlState.side = b.getAttribute('data-tl-side'); draw(); }; });
      app.querySelectorAll('th[data-sort]').forEach(function(h) {
        h.onclick = function() {
          var key = h.getAttribute('data-sort');
          if (tlState.sortKey === key) tlState.sortDir *= -1; else { tlState.sortKey = key; tlState.sortDir = key === 'name' ? 1 : -1; }
          draw();
        };
      });
      app.querySelectorAll('tr[data-href]').forEach(function(tr) {
        tr.onclick = function(e) { if (!e.target.closest('a')) window.location.href = tr.getAttribute('data-href'); };
      });
      var q = document.getElementById('tlSearch');
      q.oninput = function() {
        tlState.q = q.value.trim().toLowerCase(); var pos = q.selectionStart; draw();
        var q2 = document.getElementById('tlSearch'); q2.focus(); q2.setSelectionRange(pos, pos);
      };
    }
    draw();
  }

  // Stats for any set of graded games, in the same shape as the build's
  // season stats (sport_build.season_stats): records [W, L, T/P, units,
  // priced games] per team and league-wide, per period.
  var STATS = null;   // what the Stats page shows (the time filter's games)
  function favSide(o) {
    var ml = (o || {}).ml || {}, a = ml.away, h = ml.home;
    function imp(p) { return p < 0 ? -p / (-p + 100) : 100 / (p + 100); }
    if (typeof a === 'number' && typeof h === 'number' && imp(a) !== imp(h)) return imp(a) > imp(h) ? 'away' : 'home';
    var line = (((o || {}).ats || {}).away || {}).line;
    if (typeof line === 'number' && line !== 0) return line < 0 ? 'away' : 'home';
    return null;
  }
  function computeStats(games) {
    function R() { return [0, 0, 0, 0, 0]; }
    function add(r, res, u) {
      if (res == null || res === 'NA') return;
      if (res === 'W') r[0]++; else if (res === 'L') r[1]++; else r[2]++;
      if (u != null) { r[3] += u; r[4]++; }
    }
    function sres(res, m, side) { var x = res[m]; return side === 'away' ? x : flipRes(x); }
    function su(res, m, side) { var u = (res.u || {})[m]; return u == null ? null : u[side === 'away' ? 0 : 1]; }
    var TOT = { O: 'W', U: 'L', P: 'P' }, TOTU = { O: 'L', U: 'W', P: 'P' };
    var out = { teams: {}, league: {} };
    D.segments.forEach(function(sg) {
      var k = sg.key, rfi = isRfi(k), teams = {}, lg;
      lg = rfi ? { gp: 0, yrfi: R(), nrfi: R(), dist: {} }
        : { gp: 0, home: R(), away: R(), fav_su: R(), dog_su: R(), fav_ats: R(), dog_ats: R(), home_ats: R(), away_ats: R(), over: R(), under: R(), pts: 0, dist: {}, na: 0 };
      games.forEach(function(g) {
        var res = (g.res || {})[k];
        if (!res) return;
        if (res.na) { if ('na' in lg) lg.na++; return; }
        var sc = res.sc;
        if (!sc) return;
        lg.gp++;
        var tp = sc[0] + sc[1];
        lg.dist[String(tp)] = (lg.dist[String(tp)] || 0) + 1;
        ['away', 'home'].forEach(function(side) {
          var slug = g[side], t = teams[slug];
          if (!t) t = teams[slug] = rfi ? { gp: 0, yrfi: R(), scored: 0, allowed: 0, home: R(), away: R() }
            : { gp: 0, su: R(), home: R(), away: R(), ats: R(), over: R(), pf: 0, pa: 0 };
          t.gp++;
          var mine = side === 'away' ? sc[0] : sc[1], theirs = side === 'away' ? sc[1] : sc[0];
          if (rfi) {
            var yu = (res.u || {}).rfi;
            add(t.yrfi, res.rfi === 'Y' ? 'W' : 'L', yu == null ? null : yu[0]);
            add(t[side], res.rfi === 'Y' ? 'W' : 'L', null);
            t.scored += mine > 0 ? 1 : 0; t.allowed += theirs > 0 ? 1 : 0;
          } else {
            add(t.su, sres(res, 'su', side), su(res, 'su', side));
            add(t[side], sres(res, 'su', side), su(res, 'su', side));
            if ('ats' in res) add(t.ats, sres(res, 'ats', side), su(res, 'ats', side));
            if ('tot' in res) add(t.over, TOT[res.tot], ((res.u || {}).tot || [null])[0]);
            t.pf += mine; t.pa += theirs;
          }
        });
        if (rfi) {
          var yu = (res.u || {}).rfi;
          add(lg.yrfi, res.rfi === 'Y' ? 'W' : 'L', yu == null ? null : yu[0]);
          add(lg.nrfi, res.rfi === 'N' ? 'W' : 'L', yu == null ? null : yu[1]);
        } else {
          add(lg.home, flipRes(res.su), su(res, 'su', 'home'));
          add(lg.away, res.su, su(res, 'su', 'away'));
          var fav = favSide((g.odds || {})[k]);
          if (fav) {
            var dog = fav === 'away' ? 'home' : 'away';
            add(lg.fav_su, sres(res, 'su', fav), su(res, 'su', fav));
            add(lg.dog_su, sres(res, 'su', dog), su(res, 'su', dog));
            if ('ats' in res) { add(lg.fav_ats, sres(res, 'ats', fav), su(res, 'ats', fav)); add(lg.dog_ats, sres(res, 'ats', dog), su(res, 'ats', dog)); }
          }
          if ('ats' in res) { add(lg.home_ats, flipRes(res.ats), su(res, 'ats', 'home')); add(lg.away_ats, res.ats, su(res, 'ats', 'away')); }
          if ('tot' in res) {
            var tu = (res.u || {}).tot || [null, null];
            add(lg.over, TOT[res.tot], tu[0]); add(lg.under, TOTU[res.tot], tu[1]);
          }
          lg.pts += tp;
        }
      });
      if ('pts' in lg) { lg.avg = lg.gp ? Math.round(100 * lg.pts / lg.gp) / 100 : null; delete lg.pts; }
      out.league[k] = lg;
      Object.keys(teams).forEach(function(slug) { (out.teams[slug] = out.teams[slug] || {})[k] = teams[slug]; });
    });
    return out;
  }

  // ---- Stats page time filter ----
  // Daily sports: All / Current Week / Last Week (weeks run Monday-Sunday,
  // like NHL's). Weekly sports (NFL, NCAAF): Season / Current Week / Last
  // Week by the league's own weeks, plus a Week dropdown for any week so far.
  var tf = { mode: 'all', wk: '' };
  function addDaysStr(d, n) { return new Date(new Date(d + 'T12:00:00Z').getTime() + n * 864e5).toISOString().slice(0, 10); }
  function mondayOf(d) { var day = new Date(d + 'T12:00:00Z').getUTCDay(); return addDaysStr(d, -((day + 6) % 7)); }
  function weeklySport() { return D.schedule === 'week' && (D.weeks || []).length; }
  function startedWeeks() {
    var t = todayET();
    var w = (D.weeks || []).filter(function(x) { return x.start <= t; });
    return w.length ? w : (D.weeks || []).slice(0, 1);
  }
  // {games, line}: the graded games in the selected range, and the range
  function tfRange() {
    if (weeklySport()) {
      var ws = startedWeeks(), w = null;
      if (tf.mode === 'week') w = ws[ws.length - 1];
      else if (tf.mode === 'lastweek') w = ws[ws.length - 2];
      else if (tf.mode === 'wk') w = (D.weeks || []).filter(function(x) { return x.key === tf.wk; })[0];
      if (tf.mode === 'all') return { games: finalGames(), line: '' };
      if (!w) return { games: [], line: '<div class="sc-week">No week to show yet</div>' };
      return { games: finalGames().filter(function(g) { return g.wk === w.key; }),
               line: '<div class="sc-week">' + esc(w.label) + ' (' + shortDay(w.start) + ' &ndash; ' + shortDay(w.end) + ')</div>' };
    }
    if (tf.mode === 'all') return { games: finalGames(), line: '' };
    var mon = addDaysStr(mondayOf(todayET()), tf.mode === 'week' ? 0 : -7), sun = addDaysStr(mon, 6);
    return { games: finalGames(mon, sun), line: '<div class="sc-week">(' + shortDay(mon) + ' &ndash; ' + shortDay(sun) + ')</div>' };
  }
  function tfControls() {
    function btn(mode, full, short) {
      return '<button class="seg-btn" data-tf="' + mode + '" aria-pressed="' + (tf.mode === mode) + '">' +
        (short ? '<span class="lbl-full">' + full + '</span><span class="lbl-short">' + short + '</span>' : full) + '</button>';
    }
    var weekly = weeklySport();
    return '<div class="seg-toggle" role="group" aria-label="Time range">' + btn('all', weekly ? 'Season' : 'All') +
      btn('week', 'Current Week', 'Cur Wk') + btn('lastweek', 'Last Week', 'Last Wk') + '</div>' +
      (weekly ? '<select class="conf-select tf-week" id="tfWeek" aria-label="Pick a week"><option value="">Week&hellip;</option>' +
        startedWeeks().map(function(w) { return '<option value="' + esc(w.key) + '"' + (tf.mode === 'wk' && tf.wk === w.key ? ' selected' : '') + '>' + esc(w.label) + '</option>'; }).join('') +
        '</select>' : '');
  }
  function wireTf(draw) {
    app.querySelectorAll('[data-tf]').forEach(function(b) { b.onclick = function() { tf.mode = b.getAttribute('data-tf'); tf.wk = ''; draw(); }; });
    var sel = document.getElementById('tfWeek');
    if (sel) sel.onchange = function() { if (sel.value) { tf.mode = 'wk'; tf.wk = sel.value; } else tf.mode = 'all'; draw(); };
  }

  function renderStats() {
    if (!D.season) { app.innerHTML = emptyNote('No ' + esc(D.label) + ' games loaded yet &mdash; stats appear once games are played.'); return; }
    var group = D.sport === 'ncaaf' ? 'conf' : null;
    function draw() {
      var k = getSeg(), range = tfRange();
      STATS = computeStats(range.games);
      var lg = STATS.league[k];
      var controls = segToggle('statsSeg', k) + tfControls();
      app.innerHTML =
        '<section id="statsSeason">' + seasonResultsHtml(lg, k, controls, range.line) + '</section>' +
        '<section id="statsScoring">' + distHtml(lg, k) + '</section>' +
        '<section id="statsTeams"><div class="tp-head"><h2>Teams</h2><span class="sc-gp">' + esc(seg(k).label) + ' &middot; ' +
          (tf.mode === 'all' ? esc(D.seasonLabel) + ' season' : 'selected range') + '</span></div>' +
          teamControlsHtml(k, { group: group }) + teamCardsHtml(k, { group: group }) + '</section>' +
        '<section id="statsPremium"></section>';   // premium sections slot in here later
      var segEl = document.getElementById('statsSeg');
      if (segEl) segEl.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { setSeg(b.getAttribute('data-seg')); draw(); } };
      wireTf(draw);
      wireTeamControls(draw);
      wireDist(draw);
    }
    draw();
  }

  // Scoring distribution: one bar per range with its count and share of
  // games ("14 · 23%"); the #/% toggle picks which leads. The label sits
  // inside the bar when it fits, else just past its end.
  var distMode = 'n';
  function distHtml(lg, k) {
    if (!lg || !lg.dist || !lg.gp) return '';
    var keys = Object.keys(lg.dist).map(Number).sort(function(a, b) { return a - b; });
    // Wide ranges (basketball halves) are grouped into buckets.
    var span = keys[keys.length - 1] - keys[0];
    var size = span > 40 ? 5 : span > 20 ? 2 : 1;
    var buckets = {};
    keys.forEach(function(v) { var b = Math.floor(v / size) * size; buckets[b] = (buckets[b] || 0) + lg.dist[v]; });
    var bk = Object.keys(buckets).map(Number).sort(function(a, b) { return a - b; });
    var max = Math.max.apply(null, bk.map(function(b) { return buckets[b]; }));
    var unit = D.sportType === 'baseball' ? 'runs' : 'points';
    return '<div class="season-card"><div class="season-card-head"><h3>Scoring Distribution &middot; ' + esc(seg(k).label) + '</h3>' +
      '<div class="sc-right"><div class="seg-toggle" role="group" aria-label="Lead with count or percent">' +
        '<button class="seg-btn" data-dist="n" aria-pressed="' + (distMode === 'n') + '">#</button>' +
        '<button class="seg-btn" data-dist="p" aria-pressed="' + (distMode === 'p') + '">%</button></div>' +
      '<span class="sc-gp">combined ' + unit + ', ' + lg.gp + ' game' + (lg.gp === 1 ? '' : 's') + '</span></div></div><div class="hdist">' +
      bk.map(function(b) {
        var c = buckets[b], w = Math.max(1, Math.round(100 * c / max)), p = Math.round(100 * c / lg.gp) + '%';
        var lbl = size === 1 ? String(b) : b + '–' + (b + size - 1);
        var val = distMode === 'n' ? '<b>' + c + '</b> <span class="hd-sub">&middot; ' + p + '</span>' : '<b>' + p + '</b> <span class="hd-sub">&middot; ' + c + '</span>';
        var inside = w >= 38;
        return '<div class="hd-row" title="' + lbl + ' ' + unit + ': ' + c + ' games (' + p + ')"><span class="hd-lbl mono">' + lbl + '</span>' +
          '<div class="hd-track"><div class="hd-bar" style="width:' + w + '%">' + (inside ? '<span class="hd-val in">' + val + '</span>' : '') + '</div>' +
          (inside ? '' : '<span class="hd-val out">' + val + '</span>') + '</div></div>';
      }).join('') + '</div></div>';
  }
  function wireDist(draw) {
    app.querySelectorAll('[data-dist]').forEach(function(b) { b.onclick = function() { distMode = b.getAttribute('data-dist'); draw(); }; });
  }

  // --------------------------------------------------------- Trends page
  function streakText(s) {
    var sg = seg(s.seg);
    var where = s.seg === '1i' ? '' : ' (' + sg.tag + ')';
    if (s.market === 'rfi') return (s.kind === 'NRFI' ? 'NRFI' : 'YRFI') + ' in ' + s.n + ' straight';
    if (s.market === 'tot') return 'The ' + s.kind + ' in ' + s.n + ' straight' + where;
    if (s.market === 'ats') return (s.kind === 'W' ? 'Covered' : 'Failed to cover') + ' ' + s.n + ' straight' + where;
    return (s.kind === 'W' ? 'Won' : 'Lost') + ' ' + s.n + ' straight SU' + where;
  }

  // One league trend, from the side to bet (scripts/sport_build.py +
  // trend_rules.py): plain-English title, strength label with n, the
  // bettor-side record, and pick chips that name team, market, period and
  // line. Hit / miss / push shows only once a pick is graded. A trend that
  // covers (nearly) the whole slate collapses to "Applies to all N games".
  var PICK_STATUS = { W: ['Hit', 'lt-w'], L: ['Miss', 'lt-l'], P: ['Push', 'lt-pending'], NA: ['No Action', 'lt-pending'] };
  function trendRow(t) {
    if (!t.kind) return '';   // an entry in the old format
    var chips = t.games.map(function(p) {
      var st = PICK_STATUS[p.status];
      return '<span class="lt-game"><span class="lt-pick">' + esc(p.chip || p.label) + '</span>' +
        (p.why ? ' <span class="lt-why">' + esc(p.matchup) + ' · ' + esc(p.why) + '</span>' : ' <span class="lt-why">' + esc(p.matchup || '') + '</span>') +
        (st ? ' <span class="lt-chip ' + st[1] + '">' + st[0] + '</span>' : '') + '</span>';
    }).join('');
    var n = t.games.length, all = t.slate_n && n >= Math.max(6, Math.ceil(t.slate_n * 0.8));
    var picks = all
      ? '<details class="lt-all"><summary>' + (n === t.slate_n ? 'Applies to all ' + n + ' games' : 'Applies to ' + n + ' of ' + t.slate_n + ' games') + '</summary><div class="lt-games">' + chips + '</div></details>'
      : '<div class="lt-games"><span class="lt-when">Picks</span>' + chips + '</div>';
    var rec = t.kind === 'side'
      ? esc(t.group) + ' are <b class="mono">' + esc(t.record) + '</b>'
      : '<b class="mono">' + Math.round(t.rate * 100) + '%</b> hit (' + esc(t.record) + ', league ' + Math.round(t.base * 100) + '%)';
    return '<div class="lt-row' + (t.strength === 'weak' ? ' weak' : '') + '"><div class="lt-top"><span class="lt-tag">' + esc(t.market) + '</span>' +
      '<span class="lt-sentence">' + esc(t.title) + '</span>' +
      '<span class="lt-str ' + t.strength + '">' + t.strength + '</span><span class="lt-n">n = ' + t.n + '</span></div>' +
      '<div class="lt-rec">' + rec + (t.units != null ? ' &middot; ' + fmtUnits(t.units) : '') + '</div>' + picks + '</div>';
  }

  // League Trends + Team Streaks for one slate: a date, or (football) a week.
  // `games` = the slate's games; `when` = "today's" / "Week 7's"; `on` = how
  // to say when a team plays ("Today", "Week 7").
  function trendsSections(e, games, when, on, noun) {
    var playing = {};
    games.forEach(function(g) { playing[g.away] = g; playing[g.home] = g; });
    var html = '<section class="trends-page-section"><div class="tp-head"><div><h2>League Trends</h2>' +
      '<p class="tp-sub">League-wide angles for ' + when + ' games, strongest first. Records are from the side to bet; ties and pushes don\'t count. Weak trends are muted. Locked in when the first game starts.</p></div></div>';
    if (e && e.trends.length) {
      var r = e.record || { w: 0, l: 0 };
      if (r.w + r.l) html += '<p class="lt-summary">League Trends went <b>' + r.w + '-' + r.l + '</b> ' + noun + '.</p>';
      html += '<div class="lt-list">' + e.trends.map(trendRow).join('') + '</div>';
    } else {
      html += '<div class="no-games-note" style="margin-top:12px">' + (games.length ? 'No league trends clear the bar for these games (8+ points off the league rate, or &plusmn;2 units, over 10+ games).' : 'No ' + esc(D.label) + ' games ' + noun + '.') + '</div>';
    }
    html += '</section>';
    // Team streaks: teams playing in this slate first.
    var list = [];
    Object.keys(D.streaks || {}).forEach(function(slug) {
      if (!D.teams[slug]) return;
      D.streaks[slug].forEach(function(s) { list.push({ slug: slug, s: s, on: !!playing[slug] }); });
    });
    list.sort(function(a, b) { return (b.on - a.on) || (b.s.n - a.s.n); });
    html += '<section class="trends-page-section"><div class="tp-head"><div><h2>Team Streaks</h2>' +
      '<p class="tp-sub">Current runs of 4 or more, through the latest final. Teams playing ' + esc(on) + ' first.</p></div></div>';
    html += list.length ? '<div class="lt-list">' + list.slice(0, 30).map(function(x) {
      var g = playing[x.slug];
      var opp = g ? (g.home === x.slug ? 'vs ' + shortName(g.away) : '@ ' + shortName(g.home)) : '';
      var day = g && D.schedule === 'week' && g.start
        ? new Date(g.start).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'America/New_York' }) + ' '
        : '';
      return '<div class="lt-row"><div class="lt-top">' + teamLink(x.slug, badge(x.slug, 22)) + '<span class="lt-sentence">' +
        esc(team(x.slug).short || team(x.slug).name) + ': ' + esc(streakText(x.s)) + '</span></div>' +
        (g ? '<div class="lt-rec">Plays ' + esc(day || on + ' ') + esc(opp) + '</div>' : '') + '</div>';
    }).join('') + '</div>' : '<div class="no-games-note" style="margin-top:12px">No team has a run of 4+ right now.</div>';
    return html + '</section>';
  }

  // Football: one list per week, like its Games page.
  function renderTrendsByWeek() {
    var weeks = D.weeks || [];
    if (!weeks.length) { app.innerHTML = emptyNote('No ' + esc(D.label) + ' games loaded yet &mdash; trends appear once games are played.'); return; }
    var keys = weeks.map(function(w) { return w.key; });
    var want = new URLSearchParams(location.search).get('week');
    var thisWeek = currentWeek(weeks);
    var cur = keys.indexOf(want) !== -1 ? want : thisWeek;
    function go(k) {
      cur = k;
      var u = new URL(location.href); u.searchParams.set('week', k); u.searchParams.delete('date');
      history.replaceState(null, '', u);
      draw();
    }
    function draw() {
      var i = keys.indexOf(cur), w = weeks[i];
      var html = '<div class="date-bar">' +
        '<button class="date-nav" id="weekPrev" aria-label="Previous week"' + (i <= 0 ? ' disabled' : '') + '>&lsaquo;</button>' +
        '<div class="date-label-wrap"><span class="date-label">' + esc(w.label) + ' <span class="week-range">' + esc(weekRange(w)) + '</span></span>' +
        (cur !== thisWeek ? '<button class="date-today-btn" id="weekNowBtn" type="button">This week</button>' : '') + '</div>' +
        '<button class="date-nav" id="weekNext" aria-label="Next week"' + (i >= keys.length - 1 ? ' disabled' : '') + '>&rsaquo;</button></div>';
      html += trendsSections(D.trends[cur], weekGames(cur), esc(w.label) + '&rsquo;s', w.label, 'in ' + esc(w.label));
      app.innerHTML = html;
      var p = document.getElementById('weekPrev'), n = document.getElementById('weekNext'), t = document.getElementById('weekNowBtn');
      if (p) p.onclick = function() { if (i > 0) go(keys[i - 1]); };
      if (n) n.onclick = function() { if (i < keys.length - 1) go(keys[i + 1]); };
      if (t) t.onclick = function() { go(thisWeek); };
    }
    draw();
  }

  function renderTrends() {
    if (D.schedule === 'week') { renderTrendsByWeek(); return; }
    var dates = Object.keys(D.trends || {}).sort();
    var gameDates = allDates();
    if (!gameDates.length) { app.innerHTML = emptyNote('No ' + esc(D.label) + ' games loaded yet &mdash; trends appear once games are played.'); return; }
    if (!dates.length) dates = gameDates;
    var cur = urlDate() || defaultDate(dates);
    function go(d) { cur = d; setUrlDate(d); draw(); }
    function draw() {
      var when = dateLabel(cur).toLowerCase() === 'today' ? 'today&rsquo;s' : esc(dateLabel(cur)) + '&rsquo;s';
      app.innerHTML = dateBar(cur, dates) + trendsSections(D.trends[cur], D.games[cur] || [], when, dateLabel(cur), 'on this date');
      wireDateBar(dates, cur, go);
    }
    draw();
  }

  // ----------------------------------------------------------- team page
  function teamGames(slug) {
    var out = [];
    allDates().forEach(function(d) { D.games[d].forEach(function(g) { if (g.away === slug || g.home === slug) out.push(g); }); });
    return out;
  }

  // A team's active trends, with the same rules and strength labels as
  // league trends (trend_rules.py via D.trendRules): per period and market,
  // the current streak and the season rate, merged into one line when they
  // point the same way. Rates leave ties and pushes out; base is 50% for
  // SU / ATS and the league rate for totals and YRFI.
  function TRR() { return D.trendRules || { team_rate_min: 15, streak_min: 4, moderate: 1, strong: 2 }; }
  function trZ(rate, base, n) { return (rate == null || !n || base <= 0 || base >= 1) ? 0 : (rate - base) / Math.sqrt(base * (1 - base) / n); }
  function trLabel(z) { var R = TRR(), a = Math.abs(z); return a >= R.strong ? 'strong' : a >= R.moderate ? 'moderate' : 'weak'; }
  function teamTrendLines(slug) {
    var R = TRR(), code = team(slug).code || shortName(slug), out = [];
    var streaks = (D.streaks || {})[slug] || [];
    D.segments.forEach(function(s) {
      var st = ((D.stats.teams || {})[slug] || {})[s.key], lg = (D.stats.league || {})[s.key];
      if (!st || !lg) return;
      var markets = isRfi(s.key) ? [['rfi', st.yrfi, lg.yrfi, 'YRFI', 'NRFI', 'YRFI', 'NRFI']]
        : [['su', st.su, null, 'W', 'L', 'Bet ' + code + ' ' + s.tag + ' ML', 'Bet against ' + code + ' ' + s.tag + ' ML'],
           ['ats', st.ats, null, 'W', 'L', code + ' ' + s.tag + ' ATS', 'Against ' + code + ' ' + s.tag + ' ATS'],
           ['tot', st.over, lg.over, 'Over', 'Under', 'Over ' + s.tag, 'Under ' + s.tag]];
      markets.forEach(function(m) {
        var r = m[1], dec = r[0] + r[1];
        var base = m[2] ? (m[2][0] + m[2][1] ? m[2][0] / (m[2][0] + m[2][1]) : 0.5) : 0.5;
        var rate = dec ? r[0] / dec : null, z = trZ(rate, base, dec);
        var seasonDir = rate == null ? null : rate >= base ? m[3] : m[4];
        var seasonOk = dec >= R.team_rate_min && Math.abs(z) >= R.moderate;
        var sk = streaks.filter(function(x) { return x.seg === s.key && x.market === m[0]; })[0];
        var word = { su: ['won', 'lost'], ats: ['covered', 'failed to cover'], tot: ['went over', 'went under'], rfi: ['had a YRFI', 'had a NRFI'] }[m[0]];
        var recTxt = r[0] + '–' + r[1] + '–' + r[2] + ' this season' + (m[0] === 'tot' ? ' (O–U–P)' : m[0] === 'ats' ? ' (W–L–P)' : m[0] === 'su' ? ' (W–L–T)' : '');
        function add(dir, text) {
          var zz = dir === m[3] ? z : -z;
          out.push({ chip: dir === m[3] ? m[5] : m[6], tag: s.tag + ' ' + { su: 'SU', ats: 'ATS', tot: 'O/U', rfi: '1st inn' }[m[0]],
            text: text, z: Math.max(0, zz), label: trLabel(Math.max(0, zz)), n: dec });
        }
        var sDir = sk ? sk.kind : null;
        if (sk && seasonOk && sDir === seasonDir) add(sDir, code + ' ' + word[sDir === m[3] ? 0 : 1] + ' ' + sk.n + ' straight · ' + recTxt);
        else {
          if (sk) add(sDir, code + ' ' + word[sDir === m[3] ? 0 : 1] + ' ' + sk.n + ' straight · ' + recTxt);
          if (seasonOk) add(seasonDir, code + ' ' + word[seasonDir === m[3] ? 0 : 1] + ' ' + Math.round((seasonDir === m[3] ? rate : 1 - rate) * 100) + '% of decisions · ' + recTxt);
        }
      });
    });
    return out.sort(function(a, b) { return b.z - a.z; });
  }

  function renderTeam() {
    var slug = TEAM;
    var games = teamGames(slug);
    if (!games.length) return; // keep the server-rendered empty sections
    var k = getSeg();
    var finals = games.filter(function(g) { return g.state === 'final'; });
    var next = games.filter(function(g) { return g.state === 'pre' || g.state === 'in'; })[0];
    var last = finals[finals.length - 1];
    function section(title, body, extra) {
      return '<h3 class="team-section-title">' + title + '</h3>' + (extra || '') + body;
    }
    function draw() {
      var st = ((D.stats.teams || {})[slug] || {})[k];
      var html = '';
      html += section('Next Game', next ? '<div class="games-list">' + gameCard(next, k, { noToggle: true }) + '</div>' : emptyNote('No upcoming game scheduled.'));
      html += section('Last Game', last ? '<div class="games-list">' + gameCard(last, k, { noToggle: true }) + '</div>' : emptyNote('No games played yet.'));
      // season markets for every segment
      var cards = D.segments.map(function(s) {
        var r = ((D.stats.teams || {})[slug] || {})[s.key];
        if (!r) return '';
        var rows;
        if (isRfi(s.key)) {
          rows = [['YRFI', r.yrfi[0] + ' of ' + r.gp, pctTxt(r.yrfi[0], r.yrfi[1]), null],
                  ['NRFI', r.yrfi[1] + ' of ' + r.gp, pctTxt(r.yrfi[1], r.yrfi[0]), null],
                  ['Scored in the 1st', r.scored + ' of ' + r.gp, pctTxt(r.scored, r.gp - r.scored), null]];
        } else {
          var atsN = r.ats[0] + r.ats[1] + r.ats[2], ouN = r.over[0] + r.over[1] + r.over[2];
          rows = [['SU <small>W–L–T</small>', rec(r.su), pctTxt(r.su[0], r.su[1]), unitsPill(r.su[3], r.su[4])],
                  ['ATS <small>W–L–P</small>' + (atsN ? ' ' + oddsNote(atsN) : ''), atsN ? rec(r.ats) : '&mdash;', atsN ? pctTxt(r.ats[0], r.ats[1]) : '&mdash;', unitsPill(r.ats[3], r.ats[4])],
                  ['O/U <small>O–U–P</small>' + (ouN ? ' ' + oddsNote(ouN) : ''), ouN ? rec(r.over) : '&mdash;', ouN ? pctTxt(r.over[0], r.over[1]) + ' O' : '&mdash;', unitsPill(r.over[3], r.over[4])]];
        }
        return '<div class="daily-summary season-markets"><h3>' + esc(s.label) + ' &middot; ' + r.gp + ' GP</h3>' +
          '<div class="ds-row ds-head"><span></span><span class="ds-right"><span class="ds-col-rec">Record</span><span class="ds-col-pct">Rate</span><span class="ds-col-units">Units</span></span></div>' +
          rows.map(function(x) {
            return '<div class="ds-row"><span class="ds-label">' + x[0] + '</span><span class="ds-right"><span class="ds-record ds-col-rec">' + x[1] +
              '</span><span class="ds-col-pct">' + x[2] + '</span><span class="ds-col-units">' + (x[3] || '') + '</span></span></div>';
          }).join('') + '</div>';
      }).join('');
      html += section('Season Markets', cards || emptyNote('Records appear once games are graded.'));
      // splits
      if (st) {
        var splits = isRfi(k)
          ? [['Home', st.home[0] + ' YRFI of ' + (st.home[0] + st.home[1]), pctTxt(st.home[0], st.home[1])], ['Away', st.away[0] + ' YRFI of ' + (st.away[0] + st.away[1]), pctTxt(st.away[0], st.away[1])]]
          : [['Home SU', rec(st.home), pctTxt(st.home[0], st.home[1])], ['Away SU', rec(st.away), pctTxt(st.away[0], st.away[1])]];
        html += section('Home / Away Splits', '<div class="daily-summary">' + splits.map(function(x) {
          return '<div class="ds-row"><span class="ds-label">' + x[0] + '</span><span class="ds-right"><span class="ds-record">' + x[1] + '</span><span class="ds-col-pct">' + x[2] + '</span></span></div>';
        }).join('') + '</div>', segToggle('teamSeg', k));
      }
      var tl = teamTrendLines(slug);
      html += section('Current Trends', tl.length ? '<div class="tr-game">' + tl.map(function(l) {
        return '<div class="tr-row' + (l.label === 'weak' ? ' weak' : '') + '"><span class="tr-chip ' + (l.label === 'weak' ? 'muted' : 'good') + '">' + esc(l.chip) + '</span>' +
          '<span class="tr-mk">' + esc(l.tag) + '</span><span class="tr-text">' + esc(l.text) + '</span>' +
          '<span class="tr-meta"><span class="tr-str ' + l.label + '">' + l.label + '</span> n = ' + l.n + '</span></div>';
      }).join('') + '</div>' : emptyNote('No active trends: no streak of ' + TRR().streak_min + '+ and no season rate that clears the bar yet.'));
      // the season's game log, every period, newest first
      var log = finals.slice().reverse();
      html += section('Season Game Log &mdash; ' + esc(seg(k).label) + ' results', log.length ? '<div class="gamelog-scroll"><table class="gamelog"><thead><tr><th>Date</th><th>Opp</th>' +
        D.segments.map(function(s) { return '<th>' + (isRfi(s.key) ? '1st Inn' : esc(s.tag)) + '</th>'; }).join('') +
        (isRfi(k) ? '<th>NRFI/YRFI</th>' : '<th>SU</th><th>ATS</th><th>O/U</th>') + '<th>Final</th></tr></thead><tbody>' + log.map(function(g) {
          var home = g.home === slug, opp = home ? g.away : g.home;
          var scores = D.segments.map(function(s) {
            var rr = (g.res || {})[s.key] || {};
            return '<td class="num">' + (rr.sc ? (home ? rr.sc[1] + '–' + rr.sc[0] : rr.sc[0] + '–' + rr.sc[1]) : (rr.na ? 'NA' : '&mdash;')) + '</td>';
          }).join('');
          var r = (g.res || {})[k] || {};
          var fin = home ? g.hs + '–' + g.as : g.as + '–' + g.hs;
          var cells = isRfi(k)
            ? '<td class="num">' + (r.rfi ? chip(r.rfi === 'Y' ? 'Y' : r.rfi === 'N' ? 'N' : 'NA') : '') + '</td>'
            : '<td class="num">' + (r.su ? chip(home ? flipRes(r.su) : r.su) : '') + '</td><td class="num">' + (r.ats ? chip(home ? flipRes(r.ats) : r.ats) : '&mdash;') + '</td><td class="num">' + (r.tot ? chip(r.tot) : '&mdash;') + '</td>';
          return '<tr><td>' + esc(new Date(g.start).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'America/New_York' })) + '</td><td>' + (home ? 'vs ' : '@ ') +
            (teamUrl(opp) ? '<a href="' + teamUrl(opp) + '">' + esc(shortName(opp)) + '</a>' : esc(shortName(opp))) + '</td>' + scores + cells + '<td class="num">' + fin + '</td></tr>';
        }).join('') + '</tbody></table></div>' : emptyNote('No games played yet.'), segToggle('teamSeg2', k));
      app.innerHTML = html;
      ['teamSeg', 'teamSeg2'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { k = b.getAttribute('data-seg'); setSeg(k); draw(); } };
      });
    }
    wireCardToggles(app);
    draw();
  }

  // ---------------------------------------------------------------- boot
  fetch(ROOT + SPORT_SLUG + '/data.json').then(function(r) { return r.json(); }).then(function(data) {
    D = data;
    if (!D.segments || !D.segments.length) return;
    if (SECTION === 'games') renderGames();
    else if (SECTION === 'stats') renderStats();
    else if (SECTION === 'trends') renderTrends();
    else if (SECTION === 'team') renderTeam();
    else if (SECTION === 'teams') renderTeamsIndex();
  }).catch(function(e) {
    if (SECTION !== 'team' && SECTION !== 'teams') app.innerHTML = emptyNote('Couldn&rsquo;t load ' + esc(SPORT_SLUG) + ' data. Try reloading.');
    if (window.console) console.error(e);
  });
})();
