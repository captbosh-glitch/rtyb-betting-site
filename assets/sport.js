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

  function favSide(o) {
    var ml = o.ml;
    if (ml && ml.away != null && ml.home != null) {
      var ia = ml.away < 0 ? -ml.away / (-ml.away + 100) : 100 / (ml.away + 100);
      var ih = ml.home < 0 ? -ml.home / (-ml.home + 100) : 100 / (ml.home + 100);
      if (ia !== ih) return ia > ih ? 'away' : 'home';
    }
    var line = o.ats && o.ats.away && o.ats.away.line;
    if (line) return line < 0 ? 'away' : 'home';
    return null;
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
  var SORT = { key: 'pct', dir: -1 };

  function statColumns(k) {
    if (isRfi(k)) {
      return [
        { key: 'gp', label: 'GP', v: function(r) { return r.gp; } },
        { key: 'yrfi', label: 'YRFI', v: function(r) { return pct(r.yrfi[0], r.yrfi[1]); }, h: function(r) { return pctTxt(r.yrfi[0], r.yrfi[1]); } },
        { key: 'nrfi', label: 'NRFI', v: function(r) { return pct(r.yrfi[1], r.yrfi[0]); }, h: function(r) { return pctTxt(r.yrfi[1], r.yrfi[0]); } },
        { key: 'scored', label: 'Scored 1st', v: function(r) { return pct(r.scored, r.gp - r.scored); }, h: function(r) { return pctTxt(r.scored, r.gp - r.scored); } },
        { key: 'allowed', label: 'Allowed 1st', v: function(r) { return pct(r.allowed, r.gp - r.allowed); }, h: function(r) { return pctTxt(r.allowed, r.gp - r.allowed); } },
        { key: 'homey', label: 'Home YRFI', v: function(r) { return pct(r.home[0], r.home[1]); }, h: function(r) { return pctTxt(r.home[0], r.home[1]); } },
        { key: 'awayy', label: 'Away YRFI', v: function(r) { return pct(r.away[0], r.away[1]); }, h: function(r) { return pctTxt(r.away[0], r.away[1]); } },
        { key: 'nrfiu', label: 'NRFI u', v: function(r) { return r.yrfi[4] ? r._nrfiU : null; }, h: function(r) { return unitsPill(r._nrfiU || 0, r.yrfi[4]); } },
      ];
    }
    return [
      { key: 'gp', label: 'GP', v: function(r) { return r.gp; } },
      { key: 'su', label: 'SU', v: function(r) { return r.su[0] - r.su[1]; }, h: function(r) { return rec(r.su); } },
      { key: 'pct', label: 'SU %', v: function(r) { return pct(r.su[0], r.su[1]); }, h: function(r) { return pctTxt(r.su[0], r.su[1]); } },
      { key: 'suu', label: 'SU u', v: function(r) { return r.su[4] ? r.su[3] : null; }, h: function(r) { return unitsPill(r.su[3], r.su[4]); } },
      { key: 'home', label: 'Home', v: function(r) { return pct(r.home[0], r.home[1]); }, h: function(r) { return rec(r.home); } },
      { key: 'away', label: 'Away', v: function(r) { return pct(r.away[0], r.away[1]); }, h: function(r) { return rec(r.away); } },
      { key: 'ats', label: 'ATS', v: function(r) { return r.ats[0] + r.ats[1] + r.ats[2] ? pct(r.ats[0], r.ats[1]) : null; }, h: function(r) { return r.ats[0] + r.ats[1] + r.ats[2] ? rec(r.ats) : '&mdash;'; } },
      { key: 'atsu', label: 'ATS u', v: function(r) { return r.ats[4] ? r.ats[3] : null; }, h: function(r) { return unitsPill(r.ats[3], r.ats[4]); } },
      { key: 'ou', label: 'O-U-P', v: function(r) { return r.over[0] + r.over[1] + r.over[2] ? pct(r.over[0], r.over[1]) : null; }, h: function(r) { return r.over[0] + r.over[1] + r.over[2] ? rec(r.over) : '&mdash;'; } },
      { key: 'pf', label: 'Pts For', v: function(r) { return r.gp ? r.pf / r.gp : null; }, h: function(r) { return r.gp ? (r.pf / r.gp).toFixed(1) : '&mdash;'; } },
      { key: 'pa', label: 'Pts Agst', v: function(r) { return r.gp ? r.pa / r.gp : null; }, h: function(r) { return r.gp ? (r.pa / r.gp).toFixed(1) : '&mdash;'; } },
    ];
  }

  function leagueTiles(lg, k) {
    function tile(lbl, val, sub) { return '<div class="stat-tile"><div class="lbl">' + lbl + '</div><div class="val">' + val + '</div>' + (sub ? '<div class="tile-sub">' + sub + '</div>' : '') + '</div>'; }
    if (!lg || !lg.gp) return '';
    var t = [tile('Games', lg.gp)];
    if (isRfi(k)) {
      var y = lg.yrfi;
      t.push(tile('YRFI', pctTxt(y[0], y[1]), y[0] + ' of ' + (y[0] + y[1])));
      t.push(tile('NRFI', pctTxt(y[1], y[0]), y[1] + ' of ' + (y[0] + y[1])));
      var runs = 0, n = 0;
      Object.keys(lg.dist).forEach(function(v) { runs += Number(v) * lg.dist[v]; n += lg.dist[v]; });
      t.push(tile('Avg 1st-inning runs', n ? (runs / n).toFixed(2) : '&mdash;'));
    } else {
      t.push(tile('Home SU', pctTxt(lg.home[0], lg.home[1]), rec(lg.home)));
      var f = lg.fav_su, fa = lg.fav_ats, o = lg.over;
      t.push(tile('Favorites SU', f[0] + f[1] + f[2] ? pctTxt(f[0], f[1]) : '&mdash;', f[0] + f[1] + f[2] ? rec(f) + ' &middot; ' + oddsNote(f[0] + f[1] + f[2]) : 'needs odds'));
      t.push(tile('Favorites ATS', fa[0] + fa[1] + fa[2] ? pctTxt(fa[0], fa[1]) : '&mdash;', fa[0] + fa[1] + fa[2] ? rec(fa) + ' &middot; ' + oddsNote(fa[0] + fa[1] + fa[2]) : 'needs odds'));
      t.push(tile('Overs (O-U-P)', o[0] + o[1] + o[2] ? pctTxt(o[0], o[1]) : '&mdash;', o[0] + o[1] + o[2] ? rec(o) + ' &middot; ' + oddsNote(o[0] + o[1] + o[2]) : 'needs odds'));
      t.push(tile('Avg combined points', lg.avg != null ? lg.avg.toFixed(1) : '&mdash;'));
      if (lg.na) t.push(tile('No Action', lg.na, 'fewer than 5 innings'));
    }
    return '<div class="stat-row sport-tiles">' + t.join('') + '</div>';
  }

  function distHtml(lg, k) {
    if (!lg || !lg.dist || !lg.gp) return '';
    var keys = Object.keys(lg.dist).map(Number).sort(function(a, b) { return a - b; });
    var max = Math.max.apply(null, keys.map(function(v) { return lg.dist[v]; }));
    // Wide ranges (basketball halves) are grouped into buckets.
    var span = keys[keys.length - 1] - keys[0];
    var size = span > 40 ? 5 : span > 20 ? 2 : 1;
    var buckets = {};
    keys.forEach(function(v) { var b = Math.floor(v / size) * size; buckets[b] = (buckets[b] || 0) + lg.dist[v]; });
    var bk = Object.keys(buckets).map(Number).sort(function(a, b) { return a - b; });
    max = Math.max.apply(null, bk.map(function(b) { return buckets[b]; }));
    var unit = D.sportType === 'baseball' ? 'runs' : 'points';
    return '<div class="season-card"><div class="season-card-head"><h3>Scoring distribution &middot; ' + esc(seg(k).label) + '</h3>' +
      '<span class="sc-gp">combined ' + unit + ', ' + lg.gp + ' games</span></div><div class="dist">' +
      bk.map(function(b) {
        var c = buckets[b], h = Math.max(2, Math.round(100 * c / max));
        var lbl = size === 1 ? String(b) : b + '–' + (b + size - 1);
        return '<div class="dist-col" title="' + lbl + ' ' + unit + ': ' + c + ' games (' + Math.round(100 * c / lg.gp) + '%)">' +
          '<div class="dist-bar" style="height:' + h + '%"></div><div class="dist-lbl">' + lbl + '</div></div>';
      }).join('') + '</div></div>';
  }

  function renderStats() {
    if (!D.season) { app.innerHTML = emptyNote('No ' + esc(D.label) + ' games loaded yet &mdash; stats appear once games are played.'); return; }
    var k = getSeg();
    var season = D.season;
    var stats = D.stats;
    var query = '';
    function draw() {
      var lg = (stats.league || {})[k];
      var cols = statColumns(k);
      var rows = Object.keys(stats.teams).filter(function(s) { return D.teams[s] && stats.teams[s][k]; }).map(function(s) {
        var r = stats.teams[s][k];
        r._slug = s;
        return r;
      });
      if (isRfi(k)) computeNrfiUnits(rows, k, season);
      var col = cols.filter(function(c) { return c.key === SORT.key; })[0] || cols[0];
      rows.sort(function(a, b) {
        var va = col.v(a), vb = col.v(b);
        if (va == null && vb == null) return 0;
        if (va == null) return 1;
        if (vb == null) return -1;
        return (va - vb) * SORT.dir;
      });
      if (query) rows = rows.filter(function(r) { var t = team(r._slug); return (t.name + ' ' + t.code + ' ' + (t.conference || '')).toLowerCase().indexOf(query) !== -1; });
      // Current season only.
      var seasonSel = '<span class="sc-gp">' + esc(D.seasonLabel) + ' season</span>';
      var atsN = 0, ouN = 0;
      if (!isRfi(k) && lg) { atsN = lg.home_ats[0] + lg.home_ats[1] + lg.home_ats[2]; ouN = lg.over[0] + lg.over[1] + lg.over[2]; }
      var html = '<div class="controls"><div class="control-group">' + segToggle('statSeg', k) + '</div>' +
        '<div class="control-group">' + seasonSel + '<input class="search-box" id="statSearch" type="search" placeholder="Search team&hellip;" value="' + esc(query) + '"></div></div>' +
        leagueTiles(lg, k) +
        '<div class="table-wrap"><div class="table-scroll"><table class="sport-stats"><thead><tr><th>Team</th>' +
        cols.map(function(c) { return '<th data-sort="' + c.key + '" class="sortable' + (c.key === SORT.key ? ' sorted' : '') + '">' + c.label + (c.key === SORT.key ? (SORT.dir < 0 ? ' &darr;' : ' &uarr;') : '') + '</th>'; }).join('') +
        '</tr></thead><tbody>' +
        (rows.length ? rows.map(function(r) {
          return '<tr><td class="team-cell">' + teamLink(r._slug, badge(r._slug, 22) + esc(team(r._slug).short || team(r._slug).name)) + '</td>' +
            cols.map(function(c) { return '<td class="num">' + (c.h ? c.h(r) : (c.v(r) == null ? '&mdash;' : c.v(r))) + '</td>'; }).join('') + '</tr>';
        }).join('') : '<tr><td colspan="' + (cols.length + 1) + '" class="teams-empty">No teams match.</td></tr>') +
        '</tbody></table></div></div>' +
        (isRfi(k) ? '' : '<p class="stats-note">SU is straight up (W-L-T, ties are 0u). ATS is W-L-P and O-U-P counts Over-Under-Push; ' +
          (atsN || ouN ? 'ATS ' + oddsNote(atsN) + ', totals ' + oddsNote(ouN) + '.' : 'ATS and totals need odds &mdash; none saved yet this season.') +
          ' Units: 1u = $100 at the saved price (spreads and totals default to &ndash;110).</p>') +
        distHtml(lg, k);
      app.innerHTML = html;
      var ss = document.getElementById('statSeg');
      if (ss) ss.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { k = b.getAttribute('data-seg'); setSeg(k); draw(); } };
      var q = document.getElementById('statSearch');
      q.oninput = function() { query = q.value.trim().toLowerCase(); var pos = q.selectionStart; draw(); var q2 = document.getElementById('statSearch'); q2.focus(); q2.setSelectionRange(pos, pos); };
      app.querySelectorAll('th[data-sort]').forEach(function(th) {
        th.onclick = function() {
          var key = th.getAttribute('data-sort');
          SORT = { key: key, dir: SORT.key === key ? -SORT.dir : -1 };
          draw();
        };
      });
    }
    draw();
  }

  // A team's NRFI units aren't in the stats file (only YRFI's); add them up
  // from the current season's games.
  function computeNrfiUnits(rows, k, season) {
    if (season !== D.season) return;
    var u = {};
    Object.keys(D.games).forEach(function(d) {
      D.games[d].forEach(function(g) {
        var r = g.res && g.res[k];
        if (!r || !r.u || !r.u.rfi) return;
        [g.away, g.home].forEach(function(s) { u[s] = (u[s] || 0) + r.u.rfi[1]; });
      });
    });
    rows.forEach(function(r) { r._nrfiU = u[r._slug] || 0; });
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
          rows = [['SU', rec(r.su), pctTxt(r.su[0], r.su[1]), unitsPill(r.su[3], r.su[4])],
                  ['ATS' + (atsN ? ' ' + oddsNote(atsN) : ''), atsN ? rec(r.ats) : '&mdash;', atsN ? pctTxt(r.ats[0], r.ats[1]) : '&mdash;', unitsPill(r.ats[3], r.ats[4])],
                  ['O-U-P' + (ouN ? ' ' + oddsNote(ouN) : ''), ouN ? rec(r.over) : '&mdash;', ouN ? pctTxt(r.over[0], r.over[1]) + ' O' : '&mdash;', null]];
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
      var streaks = (D.streaks || {})[slug] || [];
      html += section('Current Trends', streaks.length ? '<div class="lt-list">' + streaks.map(function(s) {
        return '<div class="lt-row"><div class="lt-top"><span class="lt-tag">' + esc(s.market === 'rfi' ? 'NRFI/YRFI' : seg(s.seg).tag + ' ' + { su: 'SU', ats: 'ATS', tot: 'O/U' }[s.market]) + '</span><span class="lt-sentence">' + esc(streakText(s)) + '</span></div></div>';
      }).join('') + '</div>' : emptyNote('No active streaks of 4 or more.'));
      // last 10
      var l10 = finals.slice(-10).reverse();
      html += section('Last 10 Games &mdash; ' + esc(seg(k).label), l10.length ? '<div class="gamelog-scroll"><table class="gamelog"><thead><tr><th>Date</th><th>Opp</th><th>' + (isRfi(k) ? '1st Inn' : esc(seg(k).tag)) + '</th>' +
        (isRfi(k) ? '<th>NRFI/YRFI</th>' : '<th>SU</th><th>ATS</th><th>O/U</th>') + '<th>Final</th></tr></thead><tbody>' + l10.map(function(g) {
          var home = g.home === slug, opp = home ? g.away : g.home;
          var r = (g.res || {})[k] || {};
          var sc = r.sc ? (home ? r.sc[1] + '–' + r.sc[0] : r.sc[0] + '–' + r.sc[1]) : (r.na ? 'NA' : '&mdash;');
          var fin = home ? g.hs + '–' + g.as : g.as + '–' + g.hs;
          var cells = isRfi(k)
            ? '<td class="num">' + (r.rfi ? chip(r.rfi === 'Y' ? 'Y' : r.rfi === 'N' ? 'N' : 'NA') : '') + '</td>'
            : '<td class="num">' + (r.su ? chip(home ? flipRes(r.su) : r.su) : '') + '</td><td class="num">' + (r.ats ? chip(home ? flipRes(r.ats) : r.ats) : '&mdash;') + '</td><td class="num">' + (r.tot ? chip(r.tot) : '&mdash;') + '</td>';
          return '<tr><td>' + esc(new Date(g.start).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'America/New_York' })) + '</td><td>' + (home ? 'vs ' : '@ ') +
            (teamUrl(opp) ? '<a href="' + teamUrl(opp) + '">' + esc(shortName(opp)) + '</a>' : esc(shortName(opp))) + '</td><td class="num">' + sc + '</td>' + cells + '<td class="num">' + fin + '</td></tr>';
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
  }).catch(function(e) {
    if (SECTION !== 'team') app.innerHTML = emptyNote('Couldn&rsquo;t load ' + esc(SPORT_SLUG) + ' data. Try reloading.');
    if (window.console) console.error(e);
  });
})();
