/*
 * Games, Stats, Trends and team pages for every sport except NHL (NHL's
 * pages run their own code in template.html). Reads {slug}/data.json,
 * written by scripts/sport_build.py, and renders into #sportApp:
 *   <div id="sportApp" data-section="games|stats|trends|odds|team" data-team="slug">
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
  // A ?seg= in the URL (a game card's trend link) picks it for this load.
  var SEG_CUR = new URLSearchParams(location.search).get('seg');

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
  // Moneyline (SU) Win % and Tie % count ties as games played: 5-0-12 is
  // 29% wins, 71% ties, not 100%. Same rule as winPct in template.html (NHL).
  function winPct(w, l, t) { var n = w + l + (t || 0); return n ? w / n : null; }
  function tiePct(w, l, t) { var n = w + l + (t || 0); return n ? (t || 0) / n : null; }
  function pct1(x) { return x == null ? null : Math.round(1000 * x) / 10; }
  function suPctTxt(r) { var p = pct1(winPct(r[0], r[1], r[2])); return p == null ? '&mdash;' : p.toFixed(1) + '%'; }
  function suTieTxt(r) { var p = pct1(tiePct(r[0], r[1], r[2])); return p == null ? '' : ' <small class="tie-pct">Tie ' + p.toFixed(1) + '%</small>'; }
  function rec(r) { return r ? r[0] + '-' + r[1] + '-' + r[2] : '0-0-0'; }
  function team(slug) {
    return D.teams[slug] || { name: (D.otherTeams || {})[slug] || slug, short: (D.otherTeams || {})[slug] || slug, code: '', color: null };
  }
  function teamUrl(slug) { return D.teams[slug] ? ROOT + SPORT_SLUG + '/teams/' + (D.sport === 'nhl' ? slug.toLowerCase() : slug) + '/' : null; }
  // The team's logo (assets/logos/{sport}/, light + dark versions switched
  // by CSS with the theme), or a team-color circle when there isn't one.
  function badge(slug, size) {
    var t = team(slug);
    size = size || 26;
    if (t.svg) {   // NHL's logos: assets/logos/{CODE}_light.svg / _dark.svg
      var sv = ROOT + 'assets/logos/' + slug + '_', sst = ' style="width:' + size + 'px;height:' + size + 'px"';
      return '<span class="tlogo"' + sst + '><img class="tl-light" src="' + sv + 'light.svg" alt="" loading="lazy"><img class="tl-dark" src="' + sv + 'dark.svg" alt="" loading="lazy"></span>';
    }
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
  // Segments without 'ML' in their markets (NCAAB 1st half) show no moneyline / SU anywhere.
  function hasMl(k) { var s = seg(k); return !s || !s.markets || s.markets.indexOf('ML') !== -1; }
  function getSeg() { return seg(SEG_CUR) ? SEG_CUR : D.segments[0].key; }
  function setSeg(k) {
    SEG_CUR = k;
    var u = new URL(location.href);
    if (u.searchParams.has('seg')) { u.searchParams.set('seg', k); history.replaceState(null, '', u); }
  }
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
    var ml_ = hasMl(k);
    return '<div class="odds-grid' + (ml_ ? '' : ' two') + '">' +
      '<div class="pill"><span class="pill-label">ATS</span><span class="pill-body">' + atsBody + '</span></div>' +
      (ml_ ? '<div class="pill"><span class="pill-label">SU</span><span class="pill-body">' + suBody + '</span></div>' : '') +
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
      '<div class="card-body">' + cardBody(g, k) + '</div>' +
    '</div>';
  }
  function cardBody(g, k) { return segScoreLine(g, k) + marketPills(g, k) + cardTrends(g, k); }

  // The league trends (not weak) with a pick on this game in the segment
  // the card shows: '2 trends agree · Over 57.5 1Q', linking to Trends.
  function cardTrends(g, k) {
    findGame(g.id);   // fills GAME_DAY
    var slate = D.schedule === 'week' ? g.wk : GAME_DAY[g.id];
    var e = (D.trends || {})[slate];
    if (!e) return '';
    var chips = [], n = 0;
    e.trends.forEach(function(t) {
      if (!t.kind || t.strength === 'weak' || t.seg !== k) return;
      t.games.forEach(function(p) {
        if (p.key !== g.id) return;
        n++;
        var c = p.chip || p.label;
        if (chips.indexOf(c) === -1) chips.push(c);
      });
    });
    if (!n) return '';
    var what = n > 1 && chips.length === 1 ? n + ' trends agree' : n + ' trend' + (n === 1 ? '' : 's');
    var href = ROOT + SPORT_SLUG + '/trends/?' + (D.schedule === 'week' ? 'week=' + slate : 'date=' + slate) + '&seg=' + k;
    return '<a class="gm-trends-line" href="' + href + '"><span>' + what + ' &middot; ' + esc(chips.join(' and ')) + '</span><span class="gm-why">See why &rarr;</span></a>';
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
      card.querySelector('.card-body').innerHTML = cardBody(g, k);
    });
  }

  var GAME_INDEX = null, GAME_DAY = {};
  function findGame(id) {
    if (!GAME_INDEX) {
      GAME_INDEX = {};
      Object.keys(D.games).forEach(function(d) { D.games[d].forEach(function(g) { GAME_INDEX[g.id] = g; GAME_DAY[g.id] = d; }); });
    }
    return GAME_INDEX[id];
  }

  // ------------------------------------------------------------ date bar
  // cal: add the calendar button (openCalendar, wired by the page)
  function dateBar(cur, dates, cal) {
    return '<div class="date-bar">' +
      '<button class="date-nav" id="datePrev" aria-label="Previous day"' + (cur <= dates[0] ? ' disabled' : '') + '>&lsaquo;</button>' +
      '<div class="date-label-wrap"><span class="date-label">' + esc(dateLabel(cur)) + '</span>' +
      (cur !== todayET() ? '<button class="date-today-btn" id="dateTodayBtn" type="button">Today</button>' : '') + (cal ? CAL_BTN : '') + '</div>' +
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
      if (hasMl(k)) row('Home teams SU', rec(home), pct1(winPct(home[0], home[1], home[2])), home[3], home[4], '');
      if (hasMl(k) && fav[0] + fav[1] + fav[2]) row('Favorites SU', rec(fav), pct1(winPct(fav[0], fav[1], fav[2])), fav[3], fav[4], oddsNote(fav[0] + fav[1] + fav[2]));
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
    if (market === 'ml3') {
      // 3-way moneyline: the same score as su, but a tie is a loss (and a win for the tie bet)
      if (!r.su || r.su === 'NA') return null;
      var s3 = home ? flipRes(r.su) : r.su;
      return { res: s3 === 'W' ? 'W' : 'L', tie: s3 === 'T', u: u.ml3 ? u.ml3[i] : null };
    }
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
  function newAgg() { return { w: 0, l: 0, t: 0, d: 0, gp: 0, units: 0, priced: 0 }; }
  function addAgg(a, b) {
    if (!b) return;
    a.gp++;
    if (b.tie) a.d++;   // 3-way: the segment was tied (a loss, counted for Tie %)
    if (b.res === 'W') a.w++; else if (b.res === 'L') a.l++; else a.t++;
    if (b.u != null) { a.units += b.u; a.priced++; }
  }
  // side: 'all' | 'home' | 'away'
  function teamAgg(slug, k, market, side, games) {
    var a = newAgg(), seq = [];
    games.forEach(function(g) {
      if (g.away !== slug && g.home !== slug) return;
      if (side === 'home' && g.home !== slug) return;
      if (side === 'away' && g.away !== slug) return;
      var b = betResult(g, k, market, slug);
      addAgg(a, b);
      if (b) seq.push(b.res);
    });
    a.streak = streakOf(seq);
    // SU: ties count as games played. ATS / totals: pushes are left out of the %.
    a.pct = market === 'su' || market === 'ml3' ? winPct(a.w, a.l, a.t) : (a.w + a.l) ? a.w / (a.w + a.l) : null;
    a.tiePct = market === 'su' ? tiePct(a.w, a.l, a.t) : market === 'ml3' ? (a.gp ? a.d / a.gp : null) : null;
    return a;
  }
  // The current run of one result, from results oldest first:
  // {r: 'W' | 'L' | 'T', n}, and n as a signed number for sorting.
  function streakOf(seq) {
    var n = 0, last = seq[seq.length - 1];
    for (var i = seq.length - 1; i >= 0 && seq[i] === last; i--) n++;
    return n ? { r: last, n: n, v: last === 'W' ? n : last === 'L' ? -n : 0 } : null;
  }
  // 'W4' / 'L3' (O / U for totals, Y / N for YRFI): green for the side the
  // table's % counts, red for the other.
  var STREAK_LETTER = { tot: { W: 'O', L: 'U', T: 'P' }, rfi: { W: 'Y', L: 'N', T: 'P' }, ats: { W: 'W', L: 'L', T: 'P' } };
  function streakHtml(st, market) {
    if (!st) return '&mdash;';
    var letter = (STREAK_LETTER[market] || { W: 'W', L: 'L', T: 'T' })[st.r];
    return '<span class="tl-streak ' + (st.r === 'W' ? 'good' : st.r === 'L' ? 'bad' : 'flat') + '">' + letter + st.n + '</span>';
  }
  function marketsFor(k) {
    if (isRfi(k)) return [['rfi', 'YRFI']];
    return (hasMl(k) ? [['su', 'Moneyline'], ['ml3', '3-way']] : []).concat([['ats', 'ATS'], ['tot', 'Over']]);
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
    var hasTie = false;   // moneyline and 3-way views get a Tie % column
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
        a.wins = a.w; a.u = a.priced ? a.units : null; a.streakV = a.streak ? a.streak.v : null;
        return a;
      });
    }
    function sortRows(list) {
      var key = { units: 'u', streak: 'streakV' }[tlState.sortKey] || tlState.sortKey, dir = tlState.sortDir;
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
      return '<tr class="tl-row" data-href="' + teamUrl(r.slug) + '">' +
        '<td class="team-cell">' + badge(r.slug, 24) + '<a class="tl-name" href="' + teamUrl(r.slug) + '"><span class="tl-full">' + esc(r.name) + '</span><span class="tl-short">' + esc(shortName(r.slug)) + '</span></a></td>' +
        '<td class="num rec-cell mono col-rec"><b>' + (r.gp ? r.w + '-' + r.l + (tlState.market === 'ml3' ? '' : '-' + r.t) : '&mdash;') + '</b></td>' +
        '<td class="num col-pct"><div class="pct-cell"><div class="pct-bar"><span style="width:' + (p || 0) + '%"></span></div><span class="pct-num mono">' + (p == null ? '&mdash;' : p + '%') + '</span></div></td>' +
        (hasTie ? '<td class="num col-tie mono">' + (r.tiePct == null ? '&mdash;' : Math.round(r.tiePct * 100) + '%') + '</td>' : '') +
        '<td class="num col-streak mono">' + streakHtml(r.streak, tlState.market) + '</td>' +
        '<td class="num col-units">' + unitsPill(r.units, r.priced) + '</td><td class="col-go" aria-hidden="true">&rsaquo;</td></tr>';
    }
    function draw() {
      var k = getSeg(), mk = marketsFor(k);
      if (!mk.some(function(m) { return m[0] === tlState.market; })) tlState.market = mk[0][0];
      hasTie = tlState.market === 'su' || tlState.market === 'ml3';
      var list = sortRows(rows(k)), body, ncol = hasTie ? 7 : 6;
      if (!list.length) body = '<tr><td colspan="' + ncol + '"><div class="empty-state">No teams match &ldquo;' + esc(tlState.q) + '&rdquo;.</div></td></tr>';
      else if (college) {
        var groups = {};
        list.forEach(function(r) { (groups[r.conf] = groups[r.conf] || []).push(r); });
        body = Object.keys(groups).sort(confOrder).map(function(c) {
          return '<tr class="tl-group"><td colspan="' + ncol + '">' + esc(c) + ' <span class="tc-count">' + groups[c].length + '</span></td></tr>' + groups[c].map(rowHtml).join('');
        }).join('');
      } else body = list.map(rowHtml).join('');
      var recLabel = { su: 'W-L-T', ml3: 'W-L', ats: 'ATS W-L-P', tot: 'O-U-P', rfi: 'Y-N' }[tlState.market];
      var pctLabel = { su: 'Win %', ml3: 'Win %', ats: 'Cover %', tot: 'Over %', rfi: 'YRFI %' }[tlState.market];
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
        th('name', 'Team') + th('wins', recLabel, 'num col-rec') + th('pct', pctLabel, 'num col-pct') + (hasTie ? th('tiePct', 'Tie %', 'num col-tie') : '') + th('streak', 'Streak', 'num col-streak') + th('units', 'Units', 'num col-units') + '<th class="col-go" aria-hidden="true"></th>' +
        '</tr></thead><tbody id="leagueBody">' + body + '</tbody></table></div></div>' +
        '<p class="tl-note">' + esc(seg(k).label) + ' &middot; ' + esc(D.seasonLabel) + ' season &middot; ' + ({ su: 'Win % and Tie % are out of every game played', ml3: '3-way: a tie loses both teams; Tie % is how often the tie bet won; units only where 3-way prices were saved' }[tlState.market] || 'pushes count in the record but not the %') +
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
  function favSide(o) {
    var ml = (o || {}).ml || {}, a = ml.away, h = ml.home;
    function imp(p) { return p < 0 ? -p / (-p + 100) : 100 / (p + 100); }
    if (typeof a === 'number' && typeof h === 'number' && imp(a) !== imp(h)) return imp(a) > imp(h) ? 'away' : 'home';
    var line = (((o || {}).ats || {}).away || {}).line;
    if (typeof line === 'number' && line !== 0) return line < 0 ? 'away' : 'home';
    return null;
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

  // ---- Football scoring (NFL / NCAAF Stats page) ----
  // Two cards on one game sample (the time filter's graded games with a
  // score for the period): Most Common Scores (exact score, higher first)
  // and Scoring Distribution (combined points in fixed buckets, sortable by
  // count or range). One 1Q / 1H toggle drives both; period and sort live in
  // the URL (?period=1q|1h, ?sort=common|range) so a view can be linked.
  var FB_BUCKETS = {
    '1q': [[0, 0], [1, 3], [4, 7], [8, 10], [11, 14], [15, 17], [18, 21], [22, null]],
    '1h': [[0, 0], [1, 3], [4, 7], [8, 10], [11, 14], [15, 17], [18, 21], [22, 24], [25, 28], [29, 31], [32, 35], [36, null]],
  };
  var fbState = null;
  function isFootball() { return D.sport === 'nfl' || D.sport === 'ncaaf'; }
  function fbInit() {
    if (fbState) return;
    var q = {};
    try { new URLSearchParams(window.location.search).forEach(function(v, key) { q[key] = v; }); } catch (e) {}
    fbState = { k: seg(q.period) ? q.period : D.segments[0].key, sort: q.sort === 'range' ? 'range' : 'common', open: false };
  }
  function fbSaveUrl() {
    try {
      var u = new URL(window.location.href);
      u.searchParams.set('period', fbState.k);
      u.searchParams.set('sort', fbState.sort);
      history.replaceState(null, '', u.toString());
    } catch (e) {}
  }
  function fbPct(n, of) {
    if (!of) return '0%';
    var p = 100 * n / of;
    return (p > 0 && p < 1 ? p.toFixed(1) : String(Math.round(p))) + '%';
  }
  // one bar row: label, bar (width vs the largest row), "count · %" inside
  // the bar when it fits, else just past its end; no bar for 0 games
  function fbRow(label, n, of, max, key) {
    var w = n && max ? Math.min(100, Math.max(1, Math.round(100 * n / max))) : 0;
    var val = '<b>' + n + '</b> <span class="hd-sub">&middot; ' + fbPct(n, of) + '</span>';
    var inside = w >= 38;
    return '<div class="hd-row"' + (key != null ? ' data-fb-key="' + esc(key) + '"' : '') + '><span class="hd-lbl mono">' + esc(label) + '</span>' +
      '<div class="hd-track">' + (w ? '<div class="hd-bar" style="width:' + w + '%">' + (inside ? '<span class="hd-val in">' + val + '</span>' : '') + '</div>' : '') +
      (inside ? '' : '<span class="hd-val out">' + val + '</span>') + '</div></div>';
  }
  function fbScoringHtml(games) {
    var k = fbState.k, sample = [], missing = 0;
    games.forEach(function(g) {
      var r = (g.res || {})[k];
      if (r && r.sc && !r.na) sample.push(r.sc);
      else if (g.state === 'final') missing++;
    });
    var n = sample.length;
    // card 1: exact scores, order-agnostic
    var scores = {};
    sample.forEach(function(sc) {
      var hi = Math.max(sc[0], sc[1]), lo = Math.min(sc[0], sc[1]), key = hi + '-' + lo;
      (scores[key] = scores[key] || { label: key, n: 0, tot: hi + lo, hi: hi }).n++;
    });
    var ranked = Object.keys(scores).map(function(x) { return scores[x]; }).sort(function(a, b) {
      return b.n - a.n || a.tot - b.tot || a.hi - b.hi;
    });
    var top = fbState.open ? ranked : ranked.slice(0, 5), rest = ranked.slice(5);
    var other = rest.reduce(function(t, x) { return t + x.n; }, 0);
    // bars scale to the most common score; "Other" (many scores pooled) caps at full width
    var max1 = Math.max.apply(null, top.map(function(x) { return x.n; }).concat([0]));
    var card1 = top.map(function(x) { return fbRow(x.label, x.n, n, max1); }).join('') +
      (!fbState.open && rest.length ? fbRow('Other', other, n, max1) : '') +
      (rest.length ? '<button type="button" class="fb-more" id="fbMore">' + (fbState.open ? 'Show less &#9652;' : 'Show all (' + rest.length + ' more) &#9662;') + '</button>' : '');
    // card 2: combined points in buckets
    var buckets = FB_BUCKETS[k] || FB_BUCKETS['1q'];
    var rows = buckets.map(function(b, i) {
      var c = sample.filter(function(sc) { var t = sc[0] + sc[1]; return t >= b[0] && (b[1] == null || t <= b[1]); }).length;
      return { i: i, label: b[1] == null ? b[0] + '+' : b[0] === b[1] ? String(b[0]) : b[0] + '–' + b[1], n: c };
    });
    if (fbState.sort === 'common') rows.sort(function(a, b) { return b.n - a.n || a.i - b.i; });
    var max2 = Math.max.apply(null, rows.map(function(r) { return r.n; }).concat([0]));
    var card2 = rows.map(function(r) { return fbRow(r.label, r.n, n, max2, r.label); }).join('');
    var sub = n + ' game' + (n === 1 ? '' : 's') + (missing ? '<span class="fb-missing"> &middot; ' + missing + ' game' + (missing === 1 ? '' : 's') + ' missing period data</span>' : '');
    function sortLink(v, label) {
      return '<button type="button" class="fb-sort' + (fbState.sort === v ? ' on' : '') + '" data-fb-sort="' + v + '" aria-pressed="' + (fbState.sort === v) + '">' + label + '</button>';
    }
    return '<div class="fb-scoring"><div class="season-card-head fb-head"><h3>Scoring</h3><div class="seg-toggle" role="group" aria-label="Period">' +
      D.segments.map(function(sg) { return '<button class="seg-btn" data-fb-seg="' + sg.key + '" aria-pressed="' + (sg.key === k) + '">' + esc(sg.label) + '</button>'; }).join('') +
      '</div></div><div class="fb-cards">' +
      '<div class="season-card fb-card"><div class="fb-card-head"><div><h3>Most Common Scores</h3><div class="fb-sub">' + sub + '</div></div></div>' +
        '<div class="hdist">' + (n ? card1 : emptyNote('No games with ' + esc(seg(k).label) + ' scores in this range.')) + '</div></div>' +
      '<div class="season-card fb-card"><div class="fb-card-head"><div><h3>Scoring Distribution</h3><div class="fb-sub">' + sub + '</div></div>' +
        '<div class="fb-sorts">Sort: ' + sortLink('common', 'Common') + ' <span aria-hidden="true">|</span> ' + sortLink('range', 'Range') + '</div></div>' +
        '<div class="hdist" id="fbDist">' + (n ? card2 : emptyNote('No games with ' + esc(seg(k).label) + ' scores in this range.')) + '</div></div>' +
      '</div></div>';
  }
  function renderFbScoring(games) {
    var box = document.getElementById('statsScoring');
    if (!box) return;
    fbInit();
    // FLIP: remember where each bucket row was, re-render, then slide rows
    // from their old spots to the new ones (~200ms), unless reduced motion
    var before = {};
    box.querySelectorAll('#fbDist [data-fb-key]').forEach(function(el) { before[el.getAttribute('data-fb-key')] = el.getBoundingClientRect().top; });
    box.innerHTML = fbScoringHtml(games);
    var still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!still) {
      box.querySelectorAll('#fbDist [data-fb-key]').forEach(function(el) {
        var was = before[el.getAttribute('data-fb-key')];
        if (was == null) return;
        var dy = was - el.getBoundingClientRect().top;
        if (!dy) return;
        el.style.transform = 'translateY(' + dy + 'px)';
        el.style.transition = 'none';
        requestAnimationFrame(function() {
          el.style.transition = 'transform 200ms ease';
          el.style.transform = '';
        });
      });
    }
    box.querySelectorAll('[data-fb-seg]').forEach(function(b) {
      b.onclick = function() { fbState.k = b.getAttribute('data-fb-seg'); fbState.open = false; fbSaveUrl(); renderFbScoring(games); };
    });
    box.querySelectorAll('[data-fb-sort]').forEach(function(b) {
      b.onclick = function() { fbState.sort = b.getAttribute('data-fb-sort'); fbSaveUrl(); renderFbScoring(games); };
    });
    var more = document.getElementById('fbMore');
    if (more) more.onclick = function() { fbState.open = !fbState.open; renderFbScoring(games); };
  }

  // ------------------------------------------------------------ Stats page
  // One layout for every sport (Chris's Stats spec, the sport-families rule
  // in CLAUDE.md): Season Results cards, the scoring section (NHL Goal
  // Stats, football scoring), Money Board, Edges, Situational Results.
  // Everything is counted here from the graded games: res[k] (from the away
  // side) and u[market] units on each game, the same as the Teams pages.
  //
  // PREMIUM: one flag per section. Off = everyone sees it all. On = free
  // visitors (IS_PREMIUM false, or ?free=1) see each card's first 2 rows
  // and the rest blurred behind "Unlock with Premium".
  var PREMIUM = { board: false, edge1q: false, edge1h: false, edge1p: false };
  function periodFamily() { return D.sport === 'nhl' || D.sport === 'mlb'; }
  function spreadWord() { return D.sportType === 'baseball' ? 'Run Line' : D.sport === 'nhl' ? 'Puck Line' : 'Spread'; }
  function totalWord(k) { return D.sport === 'nhl' && k === '1p' ? 'Total 1.5' : 'Total'; }
  function scoreUnit() { return D.sport === 'nhl' ? 'goals' : D.sportType === 'baseball' ? 'runs' : 'points'; }
  function pctOf(n, of) { return of ? Math.round(100 * n / of) : null; }
  function pctCell(n, of) { var p = pctOf(n, of); return p == null ? '&mdash;' : p + '%'; }
  function mlFavSide(ml) {
    ml = ml || {};
    if (typeof ml.away !== 'number' || typeof ml.home !== 'number') return null;
    function imp(p) { return p < 0 ? -p / (-p + 100) : 100 / (p + 100); }
    return imp(ml.away) === imp(ml.home) ? null : imp(ml.away) > imp(ml.home) ? 'away' : 'home';
  }
  // the segment's favorite: its own moneyline, else its spread line, else the full game
  function segFavSide(g, k) { return favSide((g.odds || {})[k]) || mlFavSide(g.fml) || (g.fs ? (g.fs < 0 ? 'home' : 'away') : null); }
  // the full-game favorite: closing moneyline, else the spread
  function gameFav(g) { return mlFavSide(g.fml) || (g.fs ? (g.fs < 0 ? 'home' : 'away') : null); }
  function graded(games, k) {
    return games.filter(function(g) { var r = (g.res || {})[k]; return r && r.sc && !r.na; });
  }
  function premiumLocked(flag) { return !!PREMIUM[flag] && !IS_PREMIUM; }
  function lockRows(rows, flag) {
    if (!premiumLocked(flag) || rows.length <= 2) return rows.join('');
    return rows.slice(0, 2).join('') + '<div class="pm-blur" aria-hidden="true">' + rows.slice(2).join('') + '</div>' +
      '<a class="pm-unlock" href="' + ROOT + '#premium">Unlock with Premium</a>';
  }
  function infoTip(html, left) {
    return '<button type="button" class="info-tip' + (left ? ' tip-left' : '') + '" aria-label="About this section">i<span class="tip-bubble" role="tooltip">' + html + '</span></button>';
  }

  // ---- Season Results: one row of cards, following the segment toggle ----
  // card = {title, sub, gp, lines [[label, n]], units [[label, sum, priced]], note}
  function newCard(title, sub) { return { title: title, sub: sub, gp: 0, n: {}, u: {}, pr: {}, order: [], uorder: [] }; }
  function cHit(c, label) { if (c.order.indexOf(label) === -1) c.order.push(label); c.n[label] = (c.n[label] || 0) + 1; }
  function cUnit(c, label, u) {
    if (c.uorder.indexOf(label) === -1) c.uorder.push(label);
    if (u == null) return;
    c.u[label] = (c.u[label] || 0) + u; c.pr[label] = (c.pr[label] || 0) + 1;
  }
  function seasonCards(games, k) {
    var list = graded(games, k), cards = [];
    if (isRfi(k)) {
      var rf = newCard('NRFI / YRFI', 'A run in the 1st inning');
      rf.order = ['YRFI', 'NRFI'];
      list.forEach(function(g) {
        var r = g.res[k], u = (r.u || {}).rfi;
        if (r.rfi !== 'Y' && r.rfi !== 'N') return;
        rf.gp++; cHit(rf, r.rfi === 'Y' ? 'YRFI' : 'NRFI');
        cUnit(rf, 'YRFI', u ? u[0] : null); cUnit(rf, 'NRFI', u ? u[1] : null);
      });
      cards.push(rf);
    } else {
      var ha = newCard('Moneyline', 'Home / Away / Tie'), fd = newCard('Moneyline', 'Favorite / Underdog / Tie');
      var sha = newCard(spreadWord(), 'Home / Away / Push'), sfd = newCard(spreadWord(), 'Favorite / Underdog / Push');
      var tot = newCard(totalWord(k), 'Over / Under' + (D.sport === 'nhl' ? '' : ' / Push')), bt = newCard('BTTS', 'Both teams score: Yes / No');
      var m3 = newCard('3-way ML', 'Home / Tie / Away at 3-way prices');
      ha.order = ['Home', 'Away', 'Tie']; fd.order = ['Favorite', 'Underdog', 'Tie']; sha.order = ['Home', 'Away', 'Push'];
      sfd.order = ['Favorite', 'Underdog', 'Push']; tot.order = D.sport === 'nhl' ? ['Over', 'Under'] : ['Over', 'Under', 'Push'];
      bt.order = ['Yes', 'No']; m3.order = ['Home', 'Tie', 'Away'];
      list.forEach(function(g) {
        var r = g.res[k], u = r.u || {}, o = (g.odds || {})[k] || {};
        if (hasMl(k) && r.su && r.su !== 'NA') {
          var hw = { W: 'Away', L: 'Home' }[r.su] || 'Tie';
          ha.gp++; cHit(ha, hw); cUnit(ha, 'Home', u.su ? u.su[1] : null); cUnit(ha, 'Away', u.su ? u.su[0] : null);
          var f = segFavSide(g, k);
          if (f) {
            var fi = f === 'away' ? 0 : 1, won = hw === 'Tie' ? 'Tie' : (hw.toLowerCase() === f ? 'Favorite' : 'Underdog');
            fd.gp++; cHit(fd, won); cUnit(fd, 'Fav', u.su ? u.su[fi] : null); cUnit(fd, 'Dog', u.su ? u.su[1 - fi] : null);
          }
          if (u.ml3) {
            m3.gp++; cHit(m3, hw); cUnit(m3, 'Home', u.ml3[1]); cUnit(m3, 'Tie', u.ml3[2]); cUnit(m3, 'Away', u.ml3[0]);
          }
        }
        if (r.ats && r.ats !== 'NA') {
          var hc = { W: 'Away', L: 'Home' }[r.ats] || 'Push';
          sha.gp++; cHit(sha, hc); cUnit(sha, 'Home', u.ats ? u.ats[1] : null); cUnit(sha, 'Away', u.ats ? u.ats[0] : null);
          var line = ((o.ats || {}).away || {}).line;
          if (typeof line === 'number' && line !== 0) {
            var sf = line < 0 ? 'away' : 'home', si = sf === 'away' ? 0 : 1;
            sfd.gp++; cHit(sfd, hc === 'Push' ? 'Push' : (hc.toLowerCase() === sf ? 'Favorite' : 'Underdog'));
            cUnit(sfd, 'Fav', u.ats ? u.ats[si] : null); cUnit(sfd, 'Dog', u.ats ? u.ats[1 - si] : null);
          }
        }
        if (r.tot && r.tot !== 'NA') {
          tot.gp++; cHit(tot, { O: 'Over', U: 'Under' }[r.tot] || 'Push');
          cUnit(tot, 'Over', u.tot ? u.tot[0] : null); cUnit(tot, 'Under', u.tot ? u.tot[1] : null);
        }
        if (r.btts === 'Y' || r.btts === 'N') {
          bt.gp++; cHit(bt, r.btts === 'Y' ? 'Yes' : 'No');
          cUnit(bt, 'Yes', u.btts ? u.btts[0] : null); cUnit(bt, 'No', u.btts ? u.btts[1] : null);
        }
      });
      cards = [ha, fd, sha, sfd, tot, bt, m3].filter(function(c) { return c.gp; });
    }
    cards.push(scoringCard(list, k));
    return cards;
  }
  // Scoring: the period family's 0-0 and tied rates; the spread family's
  // average closing total and how often games beat it
  function scoringCard(list, k) {
    var s = seg(k), n = list.length, pts = 0, zero = 0, tied = 0, lines = [], ln = 0;
    list.forEach(function(g) {
      var sc = g.res[k].sc, t = sc[0] + sc[1];
      pts += t; if (!t) zero++; if (sc[0] === sc[1]) tied++;
      var tl = (((g.odds || {})[k] || {}).total || {}).line;
      if (typeof tl === 'number') { lines.push({ t: t, l: tl }); ln += tl; }
    });
    var avg = n ? (pts / n).toFixed(periodFamily() ? 2 : 1) : '&mdash;';
    var c = { title: 'Scoring', sub: s.label + ' ' + scoreUnit(), gp: n, stat: [] };
    c.stat.push(['Avg ' + s.tag + ' ' + scoreUnit(), avg]);
    if (periodFamily()) {
      c.stat.push(['0&ndash;0', n ? zero + ' <small>(' + pctCell(zero, n) + ')</small>' : '&mdash;']);
      c.stat.push(['Tied after ' + (D.sport === 'nhl' ? 'one' : s.tag), n ? tied + ' <small>(' + pctCell(tied, n) + ')</small>' : '&mdash;']);
    } else {
      var avgLine = lines.length ? ln / lines.length : null;
      var over = avgLine == null ? 0 : lines.filter(function(x) { return x.t > avgLine; }).length;
      c.stat.push(['Avg closing total', avgLine == null ? '&mdash;' : avgLine.toFixed(1)]);
      c.stat.push(['Over the avg line', lines.length ? over + ' <small>(' + pctCell(over, lines.length) + ')</small>' : '&mdash;']);
    }
    return c;
  }
  function cardHtml(c) {
    var body;
    if (c.stat) body = c.stat.map(function(x) { return '<div class="sc-line"><span>' + x[0] + '</span><span class="sc-val">' + x[1] + '</span></div>'; }).join('');
    else {
      body = c.order.map(function(l) {
        var n = c.n[l] || 0;
        return '<div class="sc-line"><span>' + l + '</span><span class="sc-val">' + n + ' <small>(' + pctCell(n, c.gp) + ')</small></span></div>';
      }).join('');
      var us = c.uorder.filter(function(l) { return c.pr[l]; });
      if (us.length) body += '<div class="sc-units">' + us.map(function(l) { return '<span class="sc-u">' + l + ' ' + unitsPill(c.u[l], true) + '</span>'; }).join('') + '</div>';
    }
    return '<div class="sc-block"><h4>' + c.title + '</h4><div class="sc-sub">' + c.sub + ' &middot; ' + c.gp + ' GP</div>' + body + '</div>';
  }

  // ---- NHL Goal Stats: 1st-period goals (from the old NHL page) ----
  function goalStats(games) {
    var list = graded(games, '1p').filter(function(g) { return g.state === 'final'; }), n = list.length;
    function tp(g) { return g.res['1p'].sc[0] + g.res['1p'].sc[1]; }
    function cnt(arr, fn) { return arr.filter(fn).length; }
    function bars(rows, of) {
      return rows.map(function(r) {
        return '<div class="sc-line"><span>' + r[0] + '</span><span class="sc-val">' + r[1] + ' <small>(' + pctCell(r[1], of) + ')</small></span></div>' +
          '<div class="adv-bar"><span style="width:' + (pctOf(r[1], of) || 0) + '%"></span></div>';
      }).join('');
    }
    // the game after a team was shut out (full game)
    var byTeam = {}, offShut = [], shutGames = {};
    allDates().forEach(function(d) { D.games[d].forEach(function(g) { ['away', 'home'].forEach(function(s) { (byTeam[g[s]] = byTeam[g[s]] || []).push({ g: g, s: s }); }); }); });
    Object.keys(byTeam).forEach(function(t) {
      var arr = byTeam[t];
      for (var i = 1; i < arr.length; i++) {
        var p = arr[i - 1], e = arr[i];
        if (p.g.state !== 'final' || (p.s === 'away' ? p.g.as : p.g.hs) !== 0) continue;
        var r = (e.g.res || {})['1p'];
        if (!r || !r.sc || e.g.state !== 'final') continue;
        offShut.push(e.s === 'away' ? r.sc[0] : r.sc[1]);
        shutGames[e.g.id] = e.g;
      }
    });
    var sg = Object.keys(shutGames).map(function(id) { return shutGames[id]; }), m = offShut.length;
    var cards = [
      ['Overs Ladder', 'Games over each 1st-period total', n, bars([['Over 0.5', cnt(list, function(g) { return tp(g) > 0; })], ['Over 1.5', cnt(list, function(g) { return tp(g) > 1; })], ['Over 2.5', cnt(list, function(g) { return tp(g) > 2; })]], n)],
      ['1P Goal Split', 'Total goals in the 1st period', n, bars([['0 goals', cnt(list, function(g) { return tp(g) === 0; })], ['1 goal', cnt(list, function(g) { return tp(g) === 1; })], ['2 goals', cnt(list, function(g) { return tp(g) === 2; })], ['3+ goals', cnt(list, function(g) { return tp(g) >= 3; })]], n)],
      ['Off a Shutout &middot; Goals Scored', 'Team&rsquo;s own 1P goals the game after being shut out', m, bars([['0 goals', offShut.filter(function(x) { return x === 0; }).length], ['1 goal', offShut.filter(function(x) { return x === 1; }).length], ['2+ goals', offShut.filter(function(x) { return x >= 2; }).length]], m)],
      ['Off a Shutout &middot; 1P Total', 'Both teams, the game after a shutout loss', sg.length, bars([['Over 0.5', cnt(sg, function(g) { return tp(g) > 0; })], ['Over 1.5', cnt(sg, function(g) { return tp(g) > 1; })], ['Over 2.5', cnt(sg, function(g) { return tp(g) > 2; })]], sg.length)]
    ];
    return '<div class="season-card"><div class="season-card-head"><h3>Goal Stats</h3><div class="sc-right"><span class="sc-gp">1st-period totals &middot; ' + n + ' GP</span></div></div>' +
      '<div class="sc-grid">' + cards.map(function(c) {
        return '<div class="sc-block"><h4>' + c[0] + '</h4><div class="sc-sub">' + c[1] + ' &middot; ' + c[2] + ' GP</div>' + c[3] + '</div>';
      }).join('') + '</div></div>';
  }

  // ---- Money Board: the segment's moneyline by side and price; spread
  // sports add a Moneyline / Spread switch (cover rates by line size) ----
  var boardState = { view: 'pct', market: 'ml' };
  function newRec() { return { w: 0, l: 0, t: 0, u: 0, pr: 0 }; }
  function addRec(a, res, u) {
    if (res === 'W') a.w++; else if (res === 'L') a.l++; else a.t++;
    if (u != null) { a.u += u; a.pr++; }
  }
  function boardRow(label, a) {
    var d = a.w + a.l, val = boardState.view === 'pct'
      ? '<span class="u-pill u-zero">' + (d ? Math.round(100 * a.w / d) + '%' : '&mdash;') + '</span>'
      : unitsPill(a.u, a.pr);
    return '<div class="mb-row"><div><div class="mb-label">' + label + '</div><div class="mb-rec mono">' + a.w + '-' + a.l + '-' + a.t + '</div></div>' + val + '</div>';
  }
  function boardCard(title, sub, rows, note) {
    return '<div class="sc-block adv-card"><h4>' + title + '</h4><div class="adv-card-sub">' + sub + '</div>' +
      lockRows(rows, 'board') + (note ? '<div class="adv-note">' + note + '</div>' : '') + '</div>';
  }
  function moneyBoard(games, k) {
    var list = graded(games, k), s = seg(k);
    var canMl = hasMl(k) && !isRfi(k), canAts = !periodFamily() || D.sportType === 'baseball';
    canAts = canAts && list.some(function(g) { var r = g.res[k]; return r.ats && r.ats !== 'NA'; });
    if (!canMl && !canAts) return '';
    var mk = boardState.market === 'ats' && canAts ? 'ats' : canMl ? 'ml' : 'ats';
    var cards = [];
    if (mk === 'ml') {
      var groups = { 'Home Fav': newRec(), 'Home Dog': newRec(), 'Road Fav': newRec(), 'Road Dog': newRec() };
      var tiers = [['-150 or shorter', function(p) { return p <= -150; }], ['-149 to -101', function(p) { return p > -150 && p <= -101; }],
                   ['+100 to +149', function(p) { return (p >= 100 && p <= 149) || p === -100; }], ['+150 or longer', function(p) { return p >= 150; }]];
      var tr = tiers.map(newRec), priced = 0;
      list.forEach(function(g) {
        var r = g.res[k], u = (r.u || {}).su, ml = ((g.odds || {})[k] || {}).ml || {};
        if (!r.su || r.su === 'NA' || !u) return;
        var f = mlFavSide(ml);
        if (!f) return;
        priced++;
        var aRes = r.su === 'P' ? 'T' : r.su, hRes = flipRes(aRes);
        addRec(groups[f === 'home' ? 'Home Fav' : 'Home Dog'], hRes, u[1]);
        addRec(groups[f === 'away' ? 'Road Fav' : 'Road Dog'], aRes, u[0]);
        [['away', aRes, u[0]], ['home', hRes, u[1]]].forEach(function(x) {
          for (var i = 0; i < tiers.length; i++) if (tiers[i][1](ml[x[0]])) { addRec(tr[i], x[1], x[2]); break; }
        });
      });
      cards.push(boardCard('Home / Road Fav &amp; Dog', s.tag + ' moneyline by side', Object.keys(groups).map(function(g) { return boardRow(g, groups[g]); }), priced + ' games with a closing ' + s.tag + ' moneyline'));
      cards.push(boardCard('Odds Tiers', s.tag + ' moneyline by closing price', tiers.map(function(t, i) { return boardRow(t[0], tr[i]); }), 'W-L-T &middot; ties are pushes (0u), left out of win %'));
    } else {
      var B = [['0.5&ndash;2.5', 0.5, 2.5], ['3&ndash;4.5', 3, 4.5], ['5+', 5, 999]];
      var fav = B.map(newRec), dog = B.map(newRec);
      list.forEach(function(g) {
        var r = g.res[k], u = (r.u || {}).ats, ats = ((g.odds || {})[k] || {}).ats || {};
        var line = (ats.away || {}).line;
        if (!r.ats || r.ats === 'NA' || typeof line !== 'number' || line === 0) return;
        var f = line < 0 ? 'away' : 'home', size = Math.abs(line);
        var aRes = r.ats === 'P' ? 'T' : r.ats, fr = f === 'away' ? aRes : flipRes(aRes), fi = f === 'away' ? 0 : 1;
        for (var i = 0; i < B.length; i++) if (size >= B[i][1] && size <= B[i][2]) {
          addRec(fav[i], fr, u ? u[fi] : fbu(fr));
          addRec(dog[i], flipRes(fr), u ? u[1 - fi] : fbu(flipRes(fr)));
          break;
        }
      });
      cards.push(boardCard('Favorites by line', s.tag + ' ' + spreadWord().toLowerCase() + ' cover rate', B.map(function(b, i) { return boardRow('Favored by ' + b[0], fav[i]); }), 'W-L-P &middot; pushes left out of cover %'));
      cards.push(boardCard('Underdogs by line', s.tag + ' ' + spreadWord().toLowerCase() + ' cover rate', B.map(function(b, i) { return boardRow('Getting ' + b[0], dog[i]); }), 'Units at the closing price (-110 when only the line was saved)'));
    }
    var pills = '<div class="adv-pills">' +
      (canMl && canAts ? '<div class="seg-toggle" role="group" aria-label="Market"><button class="seg-btn" data-board-mk="ml" aria-pressed="' + (mk === 'ml') + '">Moneyline</button>' +
        '<button class="seg-btn" data-board-mk="ats" aria-pressed="' + (mk === 'ats') + '">' + spreadWord() + '</button></div>' : '') +
      '<div class="seg-toggle" role="group" aria-label="Show"><button class="seg-btn" data-board-view="pct" aria-pressed="' + (boardState.view === 'pct') + '">Win %</button>' +
      '<button class="seg-btn" data-board-view="units" aria-pressed="' + (boardState.view === 'units') + '">Profit</button></div></div>';
    return '<div class="season-card adv-section"><div class="adv-head"><div class="adv-head-left"><h3>Money Board</h3><span class="adv-sub">' +
      esc(s.label) + ' &middot; ' + (mk === 'ml' ? 'moneyline' : spreadWord().toLowerCase()) + ' at closing prices</span></div>' + pills + '</div>' +
      '<div class="sc-grid adv-grid">' + cards.join('') + '</div></div>';
  }

  // ---- Edges: what happens after the opening segment ----
  // Lead sizes per sport and break: [small max, medium max]; bigger = big.
  var LEAD_CUTS = {
    nhl: { '1p': [1, 2] },
    nba: { '1q': [4, 9], '1h': [6, 12] }, wnba: { '1q': [4, 9], '1h': [6, 12] }, ncaab: { '1h': [5, 10] },
    nfl: { '1q': [3, 7], '1h': [7, 14] }, ncaaf: { '1q': [3, 7], '1h': [7, 14] }
  };
  var EDGE_NAME = { '1p': ['Intermission Edge', 'After the 1st period'], '1q': ['Quarter Edge', 'After the 1st quarter'], '1h': ['Halftime Edge', 'After the 1st half'] };
  function fbu(res) { return res === 'W' ? 0.9091 : res === 'L' ? -1 : 0; }   // spreads and totals at -110
  function mlu(won, price) { return typeof price !== 'number' ? null : won ? (price < 0 ? 100 / -price : price / 100) : -1; }
  function edgeRows(games, k) {
    var cuts = (LEAD_CUTS[D.sport] || {})[k];
    var basketball = ['nba', 'wnba', 'ncaab'].indexOf(D.sport) !== -1, football = isFootball(), hockey = D.sport === 'nhl';
    var unit = hockey ? 'goal' : 'point';
    function lbl(a, b) { return b === 999 ? a + '+' : a === b ? String(a) : a + '&ndash;' + b; }
    var sizes = [[1, cuts[0]], [cuts[0] + 1, cuts[1]], [cuts[1] + 1, 999]];
    var R = {};
    function row(id, label) { return (R[id] = R[id] || { label: label, n: 0, hit: 0, u: 0, pr: 0 }); }
    function add(id, label, hit, u) { var x = row(id, label); x.n++; if (hit) x.hit++; if (u != null) { x.u += u; x.pr++; } }
    sizes.forEach(function(sz, i) { row('lead' + i, 'Leader wins the game &middot; up ' + lbl(sz[0], sz[1]) + ' ' + unit + (sz[1] === 1 ? '' : 's')); });
    var list = graded(games, k).filter(function(g) { return g.state === 'final' && g.as != null && g.hs != null; });
    var later = {};   // team -> rest-of-game record, for the leaderboard
    list.forEach(function(g) {
      var r = g.res[k], a = r.sc[0], h = r.sc[1], fa = g.as, fh = g.hs, lead = Math.abs(a - h);
      var leader = a > h ? 'away' : a < h ? 'home' : null, trail = leader === 'away' ? 'home' : 'away';
      var winner = fa > fh ? 'away' : fa < fh ? 'home' : null, fav = gameFav(g), ml = g.fml || {};
      var margin = function(side) { return side === 'away' ? fa - fh : fh - fa; };
      var spread = function(side) { return g.fs == null ? null : side === 'home' ? g.fs : -g.fs; };
      if (leader) {
        for (var i = 0; i < sizes.length; i++) if (lead >= sizes[i][0] && lead <= sizes[i][1]) add('lead' + i, null, winner === leader, mlu(winner === leader, ml[leader]));
        var sp = spread(leader);
        if (sp != null && margin(leader) + sp !== 0) add('cover', 'Leader covers the full-game ' + spreadWord().toLowerCase(), margin(leader) + sp > 0, fbu(margin(leader) + sp > 0 ? 'W' : 'L'));
        if (lead > cuts[1]) add('blown', 'Blown lead: up ' + (cuts[1] + 1) + '+ at the break, lost the game', winner === trail, mlu(winner === trail, ml[trail]));
        if (fav && leader !== fav) {
          add('favback', 'Favorite trailing at the break wins the game', winner === fav, mlu(winner === fav, ml[fav]));
          var fsp = spread(fav);
          if (fsp != null && margin(fav) + fsp !== 0) add('favcover', 'Favorite trailing at the break still covers', margin(fav) + fsp > 0, fbu(margin(fav) + fsp > 0 ? 'W' : 'L'));
          add('dogwin', 'Underdog leading at the break wins outright', winner === leader, mlu(winner === leader, ml[leader]));
        }
      } else {
        add('tiehome', 'Tied at the break: home team wins', winner === 'home', mlu(winner === 'home', ml.home));
        if (fav) add('tiefav', 'Tied at the break: favorite wins', winner === fav, mlu(winner === fav, ml[fav]));
      }
      // big favorite in a close game at the break
      var bigLine = basketball ? 10 : football ? 7 : null, close = basketball ? 5 : 8;
      if (bigLine && g.fs != null && Math.abs(g.fs) >= bigLine && lead <= close) {
        var bf = g.fs < 0 ? 'home' : 'away', bm = margin(bf) + spread(bf);
        if (bm !== 0) add('bigfav', 'Big favorite (' + bigLine + '+) ' + (football ? 'in a one-score game' : 'within ' + close) + ' at the break covers', bm > 0, fbu(bm > 0 ? 'W' : 'L'));
      }
      // segment total -> game total
      if (g.ft != null && r.tot && r.tot !== 'NA' && r.tot !== 'P' && fa + fh !== g.ft) {
        var gOver = fa + fh > g.ft;
        if (r.tot === 'O') add('oo', 'Segment Over, game Over', gOver, fbu(gOver ? 'W' : 'L'));
        else add('uu', 'Segment Under, game Under', !gOver, fbu(!gOver ? 'W' : 'L'));
      }
      // after the half: a high- or low-scoring 1st half, then the 2nd half
      var tl = (((g.odds || {})[k] || {}).total || {}).line;
      if (k === '1h' && g.ft != null && typeof tl === 'number') {
        var hot = basketball ? (D.sport === 'ncaab' ? 6 : 8) : 7, h1 = a + h, h2 = fa + fh - h1, h2line = g.ft - tl;
        if (h1 >= tl + hot && h2 !== h2line) add('hi', 'High-scoring 1st half (' + hot + '+ over its line), 2nd half Under', h2 < h2line, null);
        if (h1 <= tl - hot && h2 !== h2line) add('lo', 'Low-scoring 1st half (' + hot + '+ under its line), 2nd half Over', h2 > h2line, null);
      }
      if (hockey && g.als && g.hls) {
        var p2 = g.als[1] + g.hls[1];
        if (a + h >= 3) add('hi', 'High-scoring 1st period (3+ goals), 2nd period Under 1.5', p2 < 2, null);
        if (a + h === 0) add('lo', '0&ndash;0 1st period, 2nd period Over 1.5', p2 > 1, null);
        if (leader) add('bounce', 'Bounce-back: the 1st-period loser wins the 2nd period', (trail === 'away' ? g.als[1] > g.hls[1] : g.hls[1] > g.als[1]), null);
      }
      // bounce-backs
      if (k === '1q' && leader && g.als && g.hls && g.als.length > 1) {
        add('bounce', '2nd-quarter bounce-back: the 1st-quarter loser wins the 2nd', trail === 'away' ? g.als[1] > g.hls[1] : g.hls[1] > g.als[1], null);
      }
      if (k === '1h' && leader) {
        var a2 = fa - a, h2s = fh - h;
        add('bounce', '2nd-half bounce-back: the 1st-half loser wins the 2nd half', trail === 'away' ? a2 > h2s : h2s > a2, null);
      }
      // football
      if (football && k === '1q' && a === 0 && h === 0 && g.ft != null && fa + fh !== g.ft) add('fbq', 'Scoreless 1st quarter, game Under', fa + fh < g.ft, fbu(fa + fh < g.ft ? 'W' : 'L'));
      if (football && k === '1h' && lead <= 7) {
        add('fb7h', 'Within 7 at the half: home team wins', winner === 'home', mlu(winner === 'home', ml.home));
        if (fav) add('fb7f', 'Within 7 at the half: favorite wins', winner === fav, mlu(winner === fav, ml[fav]));
      }
      // rest of the game, for the closers leaderboard
      [['away', fa - a, fh - h], ['home', fh - h, fa - a]].forEach(function(x) {
        var t = later[g[x[0]]] = later[g[x[0]]] || { w: 0, l: 0, t: 0 };
        if (x[1] > x[2]) t.w++; else if (x[1] < x[2]) t.l++; else t.t++;
      });
    });
    var order = ['lead0', 'lead1', 'lead2', 'cover', 'blown', 'tiehome', 'tiefav', 'favback', 'favcover', 'dogwin', 'bigfav', 'oo', 'uu', 'hi', 'lo', 'bounce', 'fbq', 'fb7h', 'fb7f'];
    return { rows: order.filter(function(id) { return R[id] && R[id].n; }).map(function(id) { return R[id]; }), n: list.length, later: later };
  }
  function edgeSection(games, k) {
    if (!(LEAD_CUTS[D.sport] || {})[k]) return '';
    var E = edgeRows(games, k), name = EDGE_NAME[k], flag = 'edge' + k;
    if (!E.n) return '';
    var rows = E.rows.map(function(x) {
      var p = pctOf(x.hit, x.n);
      return '<div class="edge-row"><span class="edge-label">' + x.label + '</span><span class="edge-n mono">' + x.n + '</span>' +
        '<span class="edge-rate mono">' + (p == null ? '&mdash;' : p + '%') + '</span><span class="edge-u">' + (x.pr ? unitsPill(x.u, true) : '<span class="edge-none">&mdash;</span>') + '</span></div>';
    });
    var rest = k === '1p' ? 'periods 2&ndash;3 (and OT)' : k === '1q' ? 'quarters 2&ndash;4' : 'the 2nd half';
    var teams = Object.keys(E.later).filter(function(t) { return D.teams[t]; }).map(function(t) {
      var x = E.later[t], d = x.w + x.l + x.t; return { t: t, x: x, p: d ? x.w / d : 0, q: d ? x.l / d : 0, d: d };
    }).filter(function(e) { return e.d >= 3; });
    function lb(arr, key) {
      return arr.slice().sort(function(a, b) { return b[key] - a[key] || b.d - a.d; }).slice(0, 5).map(function(e) {
        return '<div class="edge-row edge-team"><span class="edge-label">' + teamLink(e.t, badge(e.t, 18) + ' ' + esc(shortName(e.t))) + '</span>' +
          '<span class="edge-n mono">' + e.x.w + '-' + e.x.l + '-' + e.x.t + '</span><span class="edge-rate mono">' + Math.round(100 * e[key]) + '%</span><span class="edge-u"></span></div>';
      });
    }
    var tip = 'Games: finished games with the ' + esc(seg(k).label) + ' graded. Rate: how often the row came true. ' +
      'Units: 1 unit on that side at the closing pregame price (spreads and totals at -110); live prices after the break will differ. ' +
      'Lead sizes: ' + (LEAD_CUTS[D.sport][k][0] === 1 ? '1' : '1&ndash;' + LEAD_CUTS[D.sport][k][0]) + ' small, ' + (LEAD_CUTS[D.sport][k][0] + 1) + '&ndash;' + LEAD_CUTS[D.sport][k][1] + ' medium, ' + (LEAD_CUTS[D.sport][k][1] + 1) + '+ big.';
    var head = '<div class="edge-row edge-headrow"><span class="edge-label"></span><span class="edge-n">Games</span><span class="edge-rate">Rate</span><span class="edge-u">Units</span></div>';
    return '<div class="season-card adv-section"><div class="adv-head"><div class="adv-head-left"><h3>' + name[0] + ' ' + infoTip(tip, true) + '</h3>' +
      '<span class="adv-sub">' + name[1] + ' &middot; ' + E.n + ' games</span></div></div>' +
      '<div class="edge-list">' + head + lockRows(rows, flag) + '</div>' +
      (teams.length ? '<div class="edge-boards"><div class="edge-list"><h4>Best closers</h4><div class="adv-card-sub">Win ' + rest + ' most</div>' + lockRows(lb(teams, 'p'), flag) + '</div>' +
        '<div class="edge-list"><h4>Biggest faders</h4><div class="adv-card-sub">Lose ' + rest + ' most</div>' + lockRows(lb(teams, 'q'), flag) + '</div></div>' : '') +
      '</div>';
  }

  function throughDate() {
    var last = null;
    allDates().forEach(function(d) { if (D.games[d].some(function(g) { return g.state === 'final'; })) last = d; });
    return last ? new Date(last + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }) : null;
  }

  function renderStats() {
    if (!D.season || !allDates().length) { app.innerHTML = emptyNote('No ' + esc(D.label) + ' games loaded yet &mdash; stats appear once games are played.'); return; }
    var through = throughDate();
    function draw(anchor) {
      var keep = anchor ? { id: anchor.id, top: anchor.getBoundingClientRect().top } : null;
      var k = getSeg(), range = tfRange();
      var cards = seasonCards(range.games, k);
      var controls = segToggle('statsSeg', k) + tfControls();
      var edges = D.segments.filter(function(s) { return (LEAD_CUTS[D.sport] || {})[s.key]; }).map(function(s) { return edgeSection(finalGames(), s.key); }).join('');
      app.innerHTML = (through ? '<p class="stats-through">Through ' + esc(through) + '</p>' : '') +
        '<section id="statsSeason"><div class="season-card"><div class="season-card-head"><h3>Season Results</h3><div class="sc-right">' + controls + '</div></div>' + range.line +
          (cards.some(function(c) { return c.gp; }) ? '<div class="sc-grid">' + cards.map(cardHtml).join('') + '</div>' : emptyNote('No graded games in this range yet.')) + '</div></section>' +
        '<section id="statsScoring">' + (D.sport === 'nhl' ? goalStats(finalGames()) : '') + '</section>' +
        '<section id="statsBoard">' + moneyBoard(finalGames(), k) + '</section>' +
        '<section id="statsEdges">' + edges + '</section>' +
        (splitReg() ? '<section id="statsSit"></section>' : '');
      var segEl = document.getElementById('statsSeg');
      if (segEl) segEl.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { setSeg(b.getAttribute('data-seg')); draw(segEl.closest('section')); } };
      wireTf(function() { draw(document.getElementById('statsSeason')); });
      app.querySelectorAll('[data-board-view]').forEach(function(b) { b.onclick = function() { boardState.view = b.getAttribute('data-board-view'); draw(document.getElementById('statsBoard')); }; });
      app.querySelectorAll('[data-board-mk]').forEach(function(b) { b.onclick = function() { boardState.market = b.getAttribute('data-board-mk'); draw(document.getElementById('statsBoard')); }; });
      if (isFootball()) renderFbScoring(range.games);
      var eng = sitEngine();
      if (eng) { eng.state.k = k; renderSit('statsSit', { mode: 'league' }); }
      if (keep) { var el = document.getElementById(keep.id); if (el) window.scrollBy(0, el.getBoundingClientRect().top - keep.top); }
    }
    SIT_ON_SEG = function(k, anchor) { setSeg(k); draw(anchor); };
    draw();
  }

  // --------------------------------------------------------- Trends page
  // League Trends (cards from {slug}/trends.json, scripts/trends.py: frozen
  // per slate once its first game starts), then Matchup Trends and Streak
  // Trends, worked out here from each team's games before the slate. Copy
  // and tooltips come from content/trend_tooltips.json (TR.tips).
  var TR = null, TR_MKT = 'all';
  function tcode(slug) { var t = team(slug); return t.code || String(t.short || slug).slice(0, 4).toUpperCase(); }
  function segWord(k) { return seg(k).label.toLowerCase(); }
  function segWords(k) { var w = segWord(k); return /innings$/.test(w) ? w : /half$/.test(w) ? w.replace(/half$/, 'halves') : w + 's'; }
  function flipR(x) { return x === 'W' ? 'L' : x === 'L' ? 'W' : x; }
  // One side's result in a segment: W / L / P (a tie or push), or null.
  // ml3: a tied segment loses a team bet.
  function sideRes(g, k, m, side) {
    var r = (g.res || {})[k];
    if (!r || !r.sc || r.na) return null;
    var x = r[m === 'ats' ? 'ats' : 'su'];
    if (!x || x === 'NA') return null;
    if (side === 'home') x = flipR(x);
    if (m === 'ml3') return x === 'W' ? 'W' : 'L';
    return x === 'T' ? 'P' : x;
  }
  // A game bet's result: over / under, yes / no (BTTS, a 1st-inning run), tie.
  function gameRes(g, k, m, bet) {
    var r = (g.res || {})[k];
    if (!r || !r.sc || r.na) return null;
    if (m === 'ml3') return r.su === 'T' ? 'W' : r.su ? 'L' : null;
    var x = r[{ total: 'tot', btts: 'btts', rfi: 'rfi' }[m]];
    if (!x || x === 'NA') return null;
    if (m === 'total') return x === 'P' ? 'P' : (x === 'O') === (bet === 'over') ? 'W' : 'L';
    return (x === 'Y') === (bet === 'yes') ? 'W' : 'L';
  }
  function started(g) { return g.state === 'in' || g.state === 'final' || (g.start && Date.now() >= Date.parse(g.start)); }
  function betRes(g, c, x) { return x.side ? sideRes(g, c.seg, c.mk, x.side) : gameRes(g, c.seg, c.mk, x.bet); }
  var ST_ICON = { W: ['✓', 'tr-w', 'hit'], L: ['✗', 'tr-l', 'miss'], P: ['–', 'tr-p', 'push'] };
  function statusHtml(g, r) {
    var tip = TR.tips.status_icons || {};
    if (g.state === 'final' && r) { var s = ST_ICON[r]; return '<span class="tr-st ' + s[1] + '" title="' + esc(tip[s[2]] || '') + '">' + s[0] + '</span>'; }
    if (g.state === 'final') return '<span class="tr-st tr-p">–</span>';
    if (started(g)) return '<span class="tr-st tr-live" title="' + esc(tip.live || '') + '"><i></i>LIVE</span>';
    return '<span class="tr-st tr-up" title="' + esc(tip.upcoming || '') + '"></span>';
  }
  function pct0(x) { return Math.round(x * 100) + '%'; }
  // Start time; football rows say the day ("Sun 1:00 PM")
  function trTime(iso) {
    if (!iso || D.schedule !== 'week') return timeET(iso);
    return new Date(iso).toLocaleString('en-US', { weekday: 'short', hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }).replace(',', '');
  }

  // One league card
  function trendCard(c, hidden) {
    var T = TR.tips;
    var tip = '<b>' + esc(c.meaning) + '</b><br>' + esc(c.counted) +
      (c.dir ? '<br>' + esc((T.direction || {})[c.dir] || '') : '') +
      '<br>' + esc((T.market_notes || {})[c.note] || '') + '<br><i>' + esc(c.example) + '</i><br><small>' + esc(T.footer || '') + '</small>';
    var rows = c.games.map(function(x) {
      var g = findGame(x.id);
      if (!g) return '';
      var bet = x.side ? 'Bet ' + badge(g[x.side], 16) + ' ' + esc(tcode(g[x.side])) : esc(x.label);
      return '<button type="button" class="tr-row"><span class="tr-time">' + esc(trTime(g.start)) + '</span>' +
        '<span class="tr-match">' + esc(tcode(g.away)) + ' @ ' + esc(tcode(g.home)) + '</span>' +
        '<span class="tr-bet">' + bet + '</span>' + statusHtml(g, betRes(g, c, x)) +
        '<span class="tr-fact">' + esc(x.fact) + '</span></button>';
    }).join('');
    var r = c.rate * 100, b = c.base * 100;
    return '<div class="tr-card"' + (hidden ? ' hidden' : '') + '><div class="tr-top"><span class="lt-tag">' + esc(c.tag) + '</span>' + infoTip(tip, true) + '</div>' +
      '<h3 class="tr-title">' + esc(c.title) + '</h3>' +
      '<div class="tr-rec" title="' + esc((T.record_line || {}).tooltip || '') + '"><b class="mono">' + c.w + '–' + c.l + '</b> · ' + pct0(c.rate) +
      ' · league ' + pct0(c.base) + ' · <span class="' + (c.units > 0 ? 'pos' : 'neg') + '">' + fmtUnits(c.units) + '</span></div>' +
      '<div class="tr-bar" aria-hidden="true"><span style="width:' + r.toFixed(1) + '%"></span><i style="left:' + b.toFixed(1) + '%"></i></div>' +
      '<div class="tr-rows">' + rows + '</div></div>';
  }

  // Each bet once, ties and pushes not counted
  function dayRecord(cards) {
    var seen = {}, w = 0, l = 0;
    cards.forEach(function(c) {
      c.games.forEach(function(x) {
        var id = x.id + '|' + c.seg + '|' + c.mk + '|' + (x.side || x.bet);
        if (seen[id]) return;
        seen[id] = 1;
        var g = findGame(x.id);
        if (!g || g.state !== 'final') return;
        var r = betRes(g, c, x);
        if (r === 'W') w++; else if (r === 'L') l++;
      });
    });
    return [w, l];
  }

  // ---- each team's season in one segment, for Matchup and Streak Trends
  // seq per market: [{r, g}] oldest first. ml: W / L / T; ats: W / L / P;
  // total: O / U / P; btts, rfi: Y / N.
  var TEAM_SEQ = {};
  function teamSeqs(before, k) {
    var key = before + '|' + k;
    if (TEAM_SEQ[key]) return TEAM_SEQ[key];
    var out = {};
    allDates().forEach(function(d) {
      if (d >= before) return;
      D.games[d].forEach(function(g) {
        var r = (g.res || {})[k];
        if (g.state !== 'final' || !r || !r.sc || r.na) return;
        ['away', 'home'].forEach(function(side) {
          var s = g[side], o = out[s] || (out[s] = { ml: [], ats: [], total: [], btts: [], rfi: [] });
          if (r.su && r.su !== 'NA') o.ml.push(side === 'away' ? r.su : flipR(r.su));
          if (r.ats && r.ats !== 'NA') o.ats.push(side === 'away' ? r.ats : flipR(r.ats));
          if (r.tot && r.tot !== 'NA') o.total.push(r.tot);
          if (r.btts === 'Y' || r.btts === 'N') o.btts.push(r.btts);
          if (r.rfi === 'Y' || r.rfi === 'N') o.rfi.push(r.rfi);
        });
      });
    });
    return (TEAM_SEQ[key] = out);
  }
  function streakOf(seq) {
    var n = 0, last = seq[seq.length - 1];
    if (!last || last === 'T' || last === 'P') return null;
    for (var i = seq.length - 1; i >= 0 && seq[i] === last; i--) n++;
    return { kind: last, n: n };
  }
  var HIT = { ml: 'W', ats: 'W', total: 'O', btts: 'Y', rfi: 'Y' }, MISS = { ml: 'L', ats: 'L', total: 'U', btts: 'N', rfi: 'N' };
  // The team's lean in one market: {kind, x, y, rate} or null. ml counts
  // ties as games played; ats / total leave pushes out.
  function leanOf(m, seq) {
    var a = 0, b = 0, t = 0;
    seq.forEach(function(x) { if (x === HIT[m]) a++; else if (x === MISS[m]) b++; else t++; });
    var y = m === 'ml' ? a + b + t : a + b;
    if (y < 10) return null;
    var kind = a >= b ? HIT[m] : MISS[m], x = Math.max(a, b);
    return x / y >= 0.6 ? { kind: kind, x: x, y: y, rate: x / y } : null;
  }
  function countOf(m, seq, kind) {
    var x = 0, y = 0;
    seq.forEach(function(v) { if (v === kind) x++; if (m === 'ml' || v === HIT[m] || v === MISS[m]) y++; });
    return { x: x, y: y };
  }
  function lineWords(m, kind, k) {
    var s = segWord(k);
    if (m === 'ml') return 'has ' + (kind === 'W' ? 'won' : 'lost') + ' the ' + s;
    if (m === 'ats') return kind === 'W' ? 'has covered the ' + s + ' spread' : 'has failed to cover the ' + s + ' spread';
    if (m === 'total') return 'has gone ' + (kind === 'O' ? 'Over' : 'Under') + (D.sport === 'nhl' ? ' 1.5' : ' the ' + s + ' total');
    if (m === 'btts') return 'has gone BTTS ' + (kind === 'Y' ? 'Yes' : 'No');
    return 'has gone ' + (kind === 'Y' ? 'YRFI' : 'NRFI');
  }
  function streakWords(slug, m, s, k) {
    var nm = shortName(slug), sw = segWords(k), n = s.n + ' straight';
    if (m === 'ml') return nm + ' have ' + (s.kind === 'W' ? 'won' : 'lost') + ' the ' + segWord(k) + ' ' + n;
    if (m === 'ats') return nm + ' have ' + (s.kind === 'W' ? 'covered' : 'failed to cover') + ' the ' + segWord(k) + ' spread ' + n;
    var w = m === 'total' ? (s.kind === 'O' ? 'Over' : 'Under') + (D.sport === 'nhl' ? ' 1.5' : '') : m === 'btts' ? 'BTTS ' + (s.kind === 'Y' ? 'Yes' : 'No') : (s.kind === 'Y' ? 'YRFI' : 'NRFI');
    return nm + ' ' + sw + ' have gone ' + w + ' ' + n;
  }
  // The markets a pill covers (ml3 reads the moneyline's results)
  function teamMarkets(k) {
    var ms = TR.markets.filter(function(x) { return x[0] === k; }).map(function(x) { return x[1] === 'ml3' ? 'ml' : x[1]; });
    if (TR_MKT !== 'all') ms = [TR_MKT === 'ml3' ? 'ml' : TR_MKT];
    return ms.filter(function(m, i) { return ms.indexOf(m) === i && HIT[m]; });
  }
  function dots(seq, kind) {
    return '<span class="tr-dots" aria-hidden="true">' + seq.slice(-8).map(function(v) {
      return '<i class="' + (v === kind ? 'on' : v === 'T' || v === 'P' ? 'mid' : '') + '"></i>';
    }).join('') + '</span>';
  }
  function matchupBlock(g, k, before) {
    var seqs = teamSeqs(before, k), lines = [], leans = {};
    teamMarkets(k).forEach(function(m) {
      ['away', 'home'].forEach(function(side) {
        var slug = g[side], seq = ((seqs[slug] || {})[m]) || [];
        var ln = leanOf(m, seq), st = streakOf(seq);
        if (ln) (leans[m] = leans[m] || {})[side] = ln.kind;
        var kind = ln ? ln.kind : st && st.n >= 3 ? st.kind : null;
        if (!kind) return;
        var c = countOf(m, seq, kind);
        var stTxt = st && st.n >= 3 && st.kind === kind ? ' · ' + st.n + ' straight' : '';
        lines.push('<div class="mt-line">' + badge(slug, 18) + '<span><b>' + esc(tcode(slug)) + '</b> ' + esc(lineWords(m, kind, k)) + ' in ' + c.x + ' of ' + c.y +
          ' · ' + pct0(c.y ? c.x / c.y : 0) + stTxt + '</span>' + dots(seq, kind) + '</div>');
      });
    });
    var L = TR.tips.matchup_labels || {}, labels = [];
    function lab(id, m) { var x = L[id]; if (x) labels.push(infoTipLabel(x.label + (TR_MKT === 'all' ? ' · ' + mktTag(m) : ''), x.tooltip + ' ' + (L.lean_rule || ''))); }
    ['total', 'btts'].forEach(function(m) {
      var x = leans[m];
      if (!x || !x.away || !x.home) return;
      var up = HIT[m];
      if (x.away !== x.home) lab('tug_of_war', m); else lab(x.away === up ? 'fireworks' : 'lockdown', m);
    });
    var x = leans.ml;
    if (x && x.away && x.home) { if (x.away !== x.home) lab('mismatch', 'ml'); else if (x.away === 'W') lab('heavyweights', 'ml'); }
    return '<div class="mt-game"><div class="mt-head"><span class="tr-time">' + esc(trTime(g.start)) + '</span>' +
      badge(g.away, 22) + '<span class="nm-full">' + esc(shortName(g.away)) + '</span><span class="nm-abbr">' + esc(tcode(g.away)) + '</span> @ ' +
      badge(g.home, 22) + '<span class="nm-full">' + esc(shortName(g.home)) + '</span><span class="nm-abbr">' + esc(tcode(g.home)) + '</span>' +
      (labels.length ? '<span class="mt-labels">' + labels.join('') + '</span>' : '') + '</div>' +
      (lines.length ? lines.join('') : '<p class="mt-none">No matchup trends for this game.</p>') + '</div>';
  }
  function mktTag(m) { return { ml: 'ML', ats: 'Spread', total: 'O/U', btts: 'BTTS', rfi: 'NRFI' }[m] || m; }
  function infoTipLabel(text, tip) {
    return '<button type="button" class="info-tip mt-label tip-left" aria-label="' + esc(text) + '">' + esc(text) + '<span class="tip-bubble" role="tooltip">' + esc(tip) + '</span></button>';
  }

  function streakSection(games, k, before, onWord) {
    var seqs = teamSeqs(before, k), playing = {}, list = [];
    games.forEach(function(g) { playing[g.away] = g; playing[g.home] = g; });
    var ms = teamMarkets(k);
    Object.keys(D.teams).forEach(function(slug) {
      ms.forEach(function(m) {
        var s = streakOf(((seqs[slug] || {})[m]) || []);
        if (s && s.n >= 3) list.push({ slug: slug, m: m, s: s, g: playing[slug] });
      });
    });
    list.sort(function(a, b) { return (!!b.g - !!a.g) || (b.s.n - a.s.n); });
    var on = list.filter(function(x) { return x.g; }), rest = list.filter(function(x) { return !x.g; }).slice(0, 30);
    function row(x) {
      var yn = x.m === 'total' || x.m === 'btts' || x.m === 'rfi';
      var cls = (yn ? 'sk-n' : x.s.kind === 'W' ? 'sk-w' : 'sk-l') + (x.s.n >= 7 ? '3' : x.s.n >= 5 ? '2' : '1');
      var opp = x.g ? (x.g.home === x.slug ? x.g.away : x.g.home) : null;
      return '<div class="sk-row"><span class="sk-len ' + cls + '">' + x.s.n + '</span>' + teamLink(x.slug, badge(x.slug, 22)) +
        '<span class="sk-text">' + esc(streakWords(x.slug, x.m, x.s, k)) +
        (opp ? '<small>Plays ' + esc(tcode(opp)) + ' ' + esc(onWord(x.g)) + '</small>' : '') + '</span></div>';
    }
    return '<section class="trends-page-section"><div class="tp-head"><div><h2>Streak Trends</h2>' +
      '<p class="tp-sub">' + esc((TR.tips.streaks || {}).section || '') + ' ' + esc((TR.tips.streaks || {}).colors || '') + '</p></div></div>' +
      (list.length ? '<div class="sk-list">' + on.concat(rest).map(row).join('') + '</div>' : '<div class="no-games-note">No team is on a run of 3 or more.</div>') + '</section>';
  }

  // One slate: a date, or (football) a week
  function trendsSlate(o) {
    var k = getSeg(), slate = (TR.slates || {})[o.key] || { cards: [] };
    var ms = TR.markets.filter(function(x) { return x[0] === k; });
    if (TR_MKT !== 'all' && !ms.some(function(x) { return x[1] === TR_MKT; })) TR_MKT = 'all';
    var cards = slate.cards.filter(function(c) { return c.seg === k && (TR_MKT === 'all' || c.mk === TR_MKT); });
    var html = '<p class="tr-date">' + esc(o.title) + '</p>' + o.bar;
    html += '<div class="sport-seg-row tr-controls">' + segToggle('pageSeg', k) +
      '<div class="seg-toggle" id="trMkt"><button class="seg-btn" data-mkt="all" aria-pressed="' + (TR_MKT === 'all') + '">All</button>' + ms.map(function(x) {
        return '<button class="seg-btn" data-mkt="' + x[1] + '" aria-pressed="' + (x[1] === TR_MKT) + '">' + esc(x[2]) + '</button>';
      }).join('') + '</div></div>';
    html += '<section class="trends-page-section"><div class="tp-head"><div><h2>League Trends</h2></div>';
    if (cards.length) {
      var r = dayRecord(cards);
      html += '<p class="tr-day" title="' + esc(TR.tips.todays_record || '') + '">' + esc(o.recLabel) + ' Trends: <b>' + r[0] + '–' + r[1] + '</b></p>';
    }
    html += '</div>';
    if (!o.games.length) html += '<div class="no-games-note">No ' + esc(D.label) + ' games ' + esc(o.none) + '.</div>';
    else if (!cards.length) html += '<div class="no-games-note">No trends meet our bar ' + esc(o.none) + '.' + (o.today ? ' Check back tomorrow.' : '') + '</div>';
    else {
      html += '<div class="tr-cards">' + cards.map(function(c, i) { return trendCard(c, i >= TR.shown); }).join('') + '</div>';
      if (cards.length > TR.shown) html += '<button type="button" class="tr-more" id="trMore">Show more trends (' + (cards.length - TR.shown) + ')</button>';
    }
    html += '</section>';
    var games = o.games.slice().sort(function(a, b) { return (a.start || '') < (b.start || '') ? -1 : 1; });
    html += '<section class="trends-page-section"><div class="tp-head"><div><h2>Matchup Trends</h2>' +
      '<p class="tp-sub">' + esc((TR.tips.matchup_labels || {}).lean_rule || '') + ' Lines also show a run of 3 or more.</p></div></div>' +
      (games.length ? games.map(function(g) { return matchupBlock(g, k, o.before); }).join('') : '<div class="no-games-note">No games ' + esc(o.none) + '.</div>') + '</section>';
    html += streakSection(o.games, k, o.before, o.onWord);
    html += '<p class="odds-note">' + esc(TR.tips.footer || '') + '</p>';
    return html;
  }
  function wireSlate(draw) {
    var ps = document.getElementById('pageSeg');
    if (ps) ps.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { setSeg(b.getAttribute('data-seg')); draw(); } };
    document.getElementById('trMkt').onclick = function(e) { var b = e.target.closest('[data-mkt]'); if (b) { TR_MKT = b.getAttribute('data-mkt'); draw(); } };
    var more = document.getElementById('trMore');
    if (more) more.onclick = function() { app.querySelectorAll('.tr-card[hidden]').forEach(function(c) { c.hidden = false; }); more.remove(); };
    app.querySelectorAll('.tr-row').forEach(function(r) { r.onclick = function() { r.classList.toggle('open'); }; });
  }
  function dayCounts() { var o = {}; allDates().forEach(function(d) { o[d] = D.games[d].length; }); return o; }
  function longDay(d) { return new Date(d + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric', timeZone: 'UTC' }); }

  function renderTrends() {
    fetch(ROOT + SPORT_SLUG + '/trends.json').then(function(r) { return r.json(); }).then(function(tr) {
      TR = tr;
      if (D.schedule === 'week') renderTrendsByWeek(); else renderTrendsByDay();
    }).catch(function(e) {
      app.innerHTML = emptyNote('Couldn&rsquo;t load the trends. Try reloading.');
      if (window.console) console.error(e);
    });
  }
  function renderTrendsByDay() {
    var dates = allDates();
    if (!dates.length) { app.innerHTML = emptyNote('No ' + esc(D.label) + ' games loaded yet &mdash; trends appear once games are played.'); return; }
    var cur = urlDate() || defaultDate(dates);
    function go(d) { cur = d; setUrlDate(d); draw(); }
    function draw() {
      var t = todayET(), today = cur === t;
      app.innerHTML = trendsSlate({
        key: cur, games: D.games[cur] || [], before: cur, today: today, title: longDay(cur), bar: dateBar(cur, dates, true),
        recLabel: today ? 'Today’s' : shortDay(cur), none: today ? 'today' : 'on ' + shortDay(cur),
        onWord: function() { return today ? 'tonight' : 'on ' + shortDay(cur); }
      });
      wireDateBar(dates, cur, go);
      document.getElementById('dateCal').onclick = function() { openCalendar({ days: dayCounts(), cur: cur, weeks: null, onPick: go }); };
      wireSlate(draw);
    }
    draw();
  }
  // Football: one slate per week, like its Games page
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
      var i = keys.indexOf(cur), w = weeks[i], now = cur === thisWeek;
      app.innerHTML = trendsSlate({
        key: cur, games: weekGames(cur), before: w.start, today: now, title: w.label + ' · ' + weekRange(w), bar: weekBar(weeks, cur, thisWeek),
        recLabel: now ? 'This Week’s' : w.label, none: now ? 'this week' : 'in ' + w.label,
        onWord: function(g) { return g.start ? new Date(g.start).toLocaleDateString('en-US', { weekday: 'short', timeZone: 'America/New_York' }) : ''; }
      });
      var p = document.getElementById('weekPrev'), n = document.getElementById('weekNext'), t = document.getElementById('weekNowBtn');
      if (p) p.onclick = function() { if (i > 0) go(keys[i - 1]); };
      if (n) n.onclick = function() { if (i < keys.length - 1) go(keys[i + 1]); };
      if (t) t.onclick = function() { go(thisWeek); };
      document.getElementById('dateCal').onclick = function() { openCalendar({ days: dayCounts(), cur: cur, weeks: weeks, onPick: go }); };
      wireSlate(draw);
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
  // team lines have no prices, so strength alone (trend_rules.label)
  function trLabel(z) { var R = TRR(), a = Math.abs(z); return a >= R.strong ? 'strong' : a >= R.moderate ? 'moderate' : 'weak'; }
  function teamTrendLines(slug) {
    var R = TRR(), code = team(slug).code || shortName(slug), out = [];
    var streaks = (D.streaks || {})[slug] || [];
    D.segments.forEach(function(s) {
      var st = ((D.stats.teams || {})[slug] || {})[s.key], lg = (D.stats.league || {})[s.key];
      if (!st || !lg) return;
      var markets = isRfi(s.key) ? [['rfi', st.yrfi, lg.yrfi, 'YRFI', 'NRFI', 'YRFI', 'NRFI']]
        : (hasMl(s.key) ? [['su', st.su, null, 'W', 'L', 'Bet ' + code + ' ' + s.tag + ' ML', 'Bet against ' + code + ' ' + s.tag + ' ML']] : []).concat([
           ['ats', st.ats, null, 'W', 'L', code + ' ' + s.tag + ' ATS', 'Against ' + code + ' ' + s.tag + ' ATS'],
           ['tot', st.over, lg.over, 'Over', 'Under', 'Over ' + s.tag, 'Under ' + s.tag]]);
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
          var m3 = hasMl(s.key) ? teamAgg(slug, s.key, 'ml3', 'all', finalGames()) : null;
          rows = (hasMl(s.key) ? [['SU <small>W–L–T</small>' + suTieTxt(r.su), rec(r.su), suPctTxt(r.su), unitsPill(r.su[3], r.su[4])],
                  ['3-way <small>W–L</small>' + (m3.gp ? ' <small class="tie-pct">Tie ' + (Math.round(1000 * m3.tiePct) / 10).toFixed(1) + '%</small>' : ''),
                   m3.gp ? m3.w + '-' + m3.l : '&mdash;', m3.pct == null ? '&mdash;' : (Math.round(1000 * m3.pct) / 10).toFixed(1) + '%', unitsPill(m3.units, m3.priced)]] : []).concat([
                  ['ATS <small>W–L–P</small>' + (atsN ? ' ' + oddsNote(atsN) : ''), atsN ? rec(r.ats) : '&mdash;', atsN ? pctTxt(r.ats[0], r.ats[1]) : '&mdash;', unitsPill(r.ats[3], r.ats[4])],
                  ['O/U <small>O–U–P</small>' + (ouN ? ' ' + oddsNote(ouN) : ''), ouN ? rec(r.over) : '&mdash;', ouN ? pctTxt(r.over[0], r.over[1]) + ' O' : '&mdash;', unitsPill(r.over[3], r.over[4])]]);
        }
        return '<div class="daily-summary season-markets"><h3>' + esc(s.label) + ' &middot; ' + r.gp + ' GP</h3>' +
          '<div class="ds-row ds-head"><span></span><span class="ds-right"><span class="ds-col-rec">Record</span><span class="ds-col-pct">Rate</span><span class="ds-col-units">Units</span></span></div>' +
          rows.map(function(x) {
            return '<div class="ds-row"><span class="ds-label">' + x[0] + '</span><span class="ds-right"><span class="ds-record ds-col-rec">' + x[1] +
              '</span><span class="ds-col-pct">' + x[2] + '</span><span class="ds-col-units">' + (x[3] || '') + '</span></span></div>';
          }).join('') + '</div>';
      }).join('');
      var marketsHtml = section('Season Markets', cards || emptyNote('Records appear once games are graded.'));
      var tl = teamTrendLines(slug);
      var trendsHtml = !tl.length ? '' : section('Current Trends', '<div class="tr-game">' + tl.map(function(l) {
        return '<div class="tr-row' + (l.label === 'weak' ? ' weak' : '') + '"><span class="tr-chip ' + (l.label === 'weak' ? 'muted' : 'good') + '">' + esc(l.chip) + '</span>' +
          '<span class="tr-mk">' + esc(l.tag) + '</span><span class="tr-text">' + esc(l.text) + '</span>' +
          '<span class="tr-meta"><span class="tr-str ' + l.label + '" title="' + esc(TRR().tip || '') + '">' + l.label + '</span> n = ' + l.n + '</span></div>';
      }).join('') + '</div>');
      // the season's game log, every period, newest first: the last 5,
      // then Show all (NFL / NCAAF use the Situational Results log)
      var log = splitReg() ? [] : finals.slice().reverse();
      var shownLog = sitState.logAll ? log : log.slice(0, 5);
      var moreBtn = log.length > 5 ? '<button class="seg-btn sit-more" id="teamLogMore" type="button">' + (sitState.logAll ? 'Show last 5 games' : 'Show all ' + log.length + ' games') + '</button>' : '';
      var logHtml = splitReg() ? '<div id="teamSitLog"></div>' : section('Season Game Log &mdash; ' + esc(seg(k).label) + ' results', log.length ? '<div class="gamelog-scroll"><table class="gamelog"><thead><tr><th>Date</th><th>Opp</th>' +
        D.segments.map(function(s) { return '<th>' + (isRfi(s.key) ? '1st Inn' : esc(s.tag)) + '</th>'; }).join('') +
        (isRfi(k) ? '<th>NRFI/YRFI</th>' : (hasMl(k) ? '<th>SU</th>' : '') + '<th>ATS</th><th>O/U</th>') + '<th>Final</th></tr></thead><tbody>' + shownLog.map(function(g) {
          var home = g.home === slug, opp = home ? g.away : g.home;
          var scores = D.segments.map(function(s) {
            var rr = (g.res || {})[s.key] || {};
            return '<td class="num">' + (rr.sc ? (home ? rr.sc[1] + '–' + rr.sc[0] : rr.sc[0] + '–' + rr.sc[1]) : (rr.na ? 'NA' : '&mdash;')) + '</td>';
          }).join('');
          var r = (g.res || {})[k] || {};
          var fin = home ? g.hs + '–' + g.as : g.as + '–' + g.hs;
          var cells = isRfi(k)
            ? '<td class="num">' + (r.rfi ? chip(r.rfi === 'Y' ? 'Y' : r.rfi === 'N' ? 'N' : 'NA') : '') + '</td>'
            : (hasMl(k) ? '<td class="num">' + (r.su ? chip(home ? flipRes(r.su) : r.su) : '') + '</td>' : '') + '<td class="num">' + (r.ats ? chip(home ? flipRes(r.ats) : r.ats) : '&mdash;') + '</td><td class="num">' + (r.tot ? chip(r.tot) : '&mdash;') + '</td>';
          return '<tr><td>' + esc(new Date(g.start).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'America/New_York' })) + '</td><td>' + (home ? 'vs ' : '@ ') +
            (teamUrl(opp) ? '<a href="' + teamUrl(opp) + '">' + esc(shortName(opp)) + '</a>' : esc(shortName(opp))) + '</td>' + scores + cells + '<td class="num">' + fin + '</td></tr>';
        }).join('') + '</tbody></table></div>' + moreBtn : emptyNote('No games played yet.'), segToggle('teamSeg2', k));
      // Next, Last, Current Trends (if any), Season Markets, Season Game Log,
      // Situational Results (NFL / NCAAF)
      html += trendsHtml + marketsHtml + logHtml + (splitReg() ? '<div id="teamSit" class="team-sit"></div>' : '');
      app.innerHTML = html;
      var lm = document.getElementById('teamLogMore');
      if (lm) lm.onclick = function() { sitState.logAll = !sitState.logAll; draw(); };
      renderSit('teamSit', { mode: 'team', slug: slug });
      renderSitLog('teamSitLog', slug);
      ['teamSeg2'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { k = b.getAttribute('data-seg'); setSeg(k); draw(); } };
      });
    }
    wireCardToggles(app);
    draw();
  }

  // ------------------------------------------------ Situational Results
  // The shared split table (assets/situational.js) with this sport's
  // registry (assets/splits/{sport}.js). "Since last season" loads
  // {slug}/history.json only when picked. Premium: the same lock as NHL's
  // premium sections (everyone is Premium for now; ?free=1 previews it).
  var IS_PREMIUM = !/[?&]free=1\b/.test(window.location.search);
  var LOCK_HTML = '<div class="adv-lock"><div class="adv-lock-card">' +
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2"></rect><path d="M8 11V7a4 4 0 0 1 8 0v4"></path></svg>' +
    '<div class="adv-lock-title">Unlock Situational Results</div><div class="adv-lock-desc">Home / road, favorite / underdog, rest, schedule and previous-game splits for every market.</div>' +
    '<a class="adv-lock-btn" href="' + ROOT + '#premium">Go Premium</a></div></div>';
  var SIT = null;
  function splitReg() { return (window.RTYB_SPLITS || {})[D.sport] || null; }
  // Stats page: this season only (no season picker); rows that are real
  // edges and fit a game today link to the Trends page; a segment change in
  // any of its bars redraws the whole page (SIT_ON_SEG, set by renderStats).
  var SIT_ON_SEG = null;
  function sitEngine() {
    if (SIT || !splitReg() || !window.RTYBSit) return SIT;
    var seasons = [{ key: 'current', label: D.seasonLabel, games: D.games }];
    SIT = window.RTYBSit.create({ sport: D.sport, segments: D.segments, teams: D.teams, seasons: seasons, conf: D.conf, rivals: D.rivals,
      totalCuts: D.totalCuts, tz: D.tz || null, url: SECTION === 'stats', today: todayET(), trendsUrl: ROOT + SPORT_SLUG + '/trends/',
      onSeg: function(k, anchor) { if (SIT_ON_SEG) SIT_ON_SEG(k, anchor); else return false; },
      locked: function() { return !IS_PREMIUM; }, lockHtml: function() { return LOCK_HTML; } });
    return SIT;
  }
  // view = {mode: 'league'} or {mode: 'team', slug}
  function renderSit(boxId, view) {
    var e = sitEngine();
    if (e) e.render(document.getElementById(boxId), view);
  }
  var sitState = { logK: null, logAll: false };

  // Team page game log with the registry's split tags per game.
  function renderSitLog(boxId, slug) {
    var box = document.getElementById(boxId);
    if (!box || !splitReg()) return;
    var k = sitState.logK && seg(sitState.logK) ? sitState.logK : D.segments[0].key;
    var ctx = {}, eng = sitEngine();
    eng.contexts(k).forEach(function(e) { if (e.c.team === slug) ctx[e.c.g.id] = e; });
    var games = teamGames(slug).filter(function(g) { return g.state === 'final'; }).reverse();
    var shown = sitState.logAll ? games : games.slice(0, 5);
    function badge(x) { return x ? chip(x) : '<span class="result-pill T">&ndash;</span>'; }
    var rowsHtml = shown.map(function(g) {
      var home = g.home === slug, opp = home ? g.away : g.home, e = ctx[g.id], r = e ? e.r : {};
      var date = esc(new Date(g.start).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'America/New_York' }));
      var oppHtml = (home ? 'vs ' : '@ ') + (teamUrl(opp) ? '<a href="' + teamUrl(opp) + '">' + esc(shortName(opp)) + '</a>' : esc(shortName(opp)));
      var tags = e ? eng.tags(e.c).map(function(t) { return '<span class="sit-tag">' + esc(t) + '</span>'; }).join('') : '';
      var per = D.segments.map(function(s) {
        var rr = (g.res || {})[s.key] || {};
        return '<td class="num mono' + (s.key === k ? ' sit-hl' : '') + '">' + (rr.sc ? (home ? rr.sc[1] + '–' + rr.sc[0] : rr.sc[0] + '–' + rr.sc[1]) : '&mdash;') + '</td>';
      }).join('');
      var fin = home ? g.hs + '–' + g.as : g.as + '–' + g.hs;
      var b3 = (hasMl(k) ? '<td class="num">' + badge(r.su) + '</td>' : '') + '<td class="num">' + badge(r.ats) + '</td><td class="num">' + badge(r.tot) + '</td>';
      return { desk: '<tr><td>' + date + '</td><td>' + oppHtml + '</td><td class="sit-tags">' + tags + '</td>' + per + b3 + '<td class="num mono">' + fin + '</td></tr>',
        mob: '<div class="sit-gcard"><div class="sit-gl1"><span>' + date + '</span><span>' + oppHtml + '</span><span class="mono">' + fin + '</span></div>' +
          '<div class="sit-gl2"><span class="sit-tags">' + tags + '</span><span class="sit-gb">' + (hasMl(k) ? badge(r.su) : '') + badge(r.ats) + badge(r.tot) + '</span></div></div>' };
    });
    var more = games.length > 5 ? '<button class="seg-btn sit-more" id="sitMore" type="button">' + (sitState.logAll ? 'Show last 5 games' : 'Show all ' + games.length + ' games') + '</button>' : '';
    box.innerHTML = '<h3 class="team-section-title">Season Game Log</h3><div class="seg-toggle" id="sitLogSeg">' +
      D.segments.map(function(s) { return '<button class="seg-btn" data-sit-logseg="' + s.key + '" aria-pressed="' + (s.key === k) + '">' + esc(s.label) + '</button>'; }).join('') + '</div>' +
      (games.length ? '<div class="sit-desk"><div class="gamelog-scroll"><table class="gamelog sit-log"><thead><tr><th>Date</th><th>Opp</th><th>Splits</th>' +
        D.segments.map(function(s) { return '<th class="num' + (s.key === k ? ' sit-hl' : '') + '">' + esc(s.tag) + '</th>'; }).join('') +
        (hasMl(k) ? '<th class="num">SU</th>' : '') + '<th class="num">ATS</th><th class="num">O/U</th><th class="num">Final</th></tr></thead><tbody>' +
        rowsHtml.map(function(x) { return x.desk; }).join('') + '</tbody></table></div></div>' +
        '<div class="sit-mob">' + rowsHtml.map(function(x) { return x.mob; }).join('') + '</div>' + more
        : emptyNote('No games played yet.'));
    box.querySelectorAll('[data-sit-logseg]').forEach(function(b) { b.onclick = function() { sitState.logK = b.getAttribute('data-sit-logseg'); renderSitLog(boxId, slug); }; });
    var m = document.getElementById('sitMore');
    if (m) m.onclick = function() { sitState.logAll = !sitState.logAll; renderSitLog(boxId, slug); };
  }

  // ------------------------------------------------------- calendar modal
  // A month calendar in a modal (a full-width sheet from the bottom on
  // phones), shared by the Odds and Trends pages. Days with games get a dot.
  // opts: {days: {date: n games}, cur: date, weeks: [{key, label, start, end}]
  // or null (weekly sports pick a week: a day picks the week it falls in, or
  // the next one), onPick(date or week key)}.
  function weekFor(weeks, d) {
    for (var i = 0; i < weeks.length; i++) if (d <= weeks[i].end) return weeks[i];
    return null;
  }
  function openCalendar(opts) {
    var weeks = opts.weeks || null, days = opts.days || {};
    var curWeek = weeks ? weeks.filter(function(w) { return w.key === opts.cur; })[0] : null;
    var focus = (curWeek ? curWeek.start : opts.cur || todayET()).slice(0, 7);
    var keys = Object.keys(days).sort();
    var first = (keys[0] || focus).slice(0, 7), last = (keys[keys.length - 1] || focus).slice(0, 7);
    var wrap = document.createElement('div');
    wrap.className = 'cal-modal';
    wrap.setAttribute('role', 'dialog');
    wrap.setAttribute('aria-modal', 'true');
    wrap.setAttribute('aria-label', weeks ? 'Pick a week' : 'Pick a date');
    var opener = document.activeElement;
    function close() { document.removeEventListener('keydown', onKey); wrap.remove(); if (opener && opener.focus) opener.focus(); }
    function onKey(e) { if (e.key === 'Escape') close(); }
    function monthAdd(ym, n) { var y = +ym.slice(0, 4), m = +ym.slice(5, 7) - 1 + n; y += Math.floor(m / 12); m = ((m % 12) + 12) % 12; return y + '-' + (m < 9 ? '0' : '') + (m + 1); }
    function draw() {
      var y = +focus.slice(0, 4), mo = +focus.slice(5, 7);
      var lead = new Date(Date.UTC(y, mo - 1, 1)).getUTCDay(), n = new Date(Date.UTC(y, mo, 0)).getUTCDate();
      var title = new Date(Date.UTC(y, mo - 1, 15)).toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' });
      var cells = '';
      for (var i = 0; i < lead; i++) cells += '<span class="cal-pad"></span>';
      for (var dd = 1; dd <= n; dd++) {
        var d = focus + '-' + (dd < 10 ? '0' : '') + dd, w = weeks ? weekFor(weeks, d) : null;
        var on = weeks ? (curWeek && w && w.key === curWeek.key && d >= w.start && d <= w.end) : d === opts.cur;
        var cls = 'cal-day' + (days[d] ? ' has' : '') + (on ? ' on' : '') + (d === todayET() ? ' today' : '');
        cells += '<button type="button" class="' + cls + '" data-d="' + d + '"' + (w ? ' data-w="' + esc(w.key) + '"' : '') +
          (weeks && !w ? ' disabled' : '') + ' aria-label="' + esc(dateLabel(d)) + (days[d] ? ', ' + days[d] + ' game' + (days[d] === 1 ? '' : 's') : '') + '">' + dd + '</button>';
      }
      wrap.innerHTML = '<div class="cal-back" data-close></div><div class="cal-sheet">' +
        '<div class="cal-head"><button type="button" class="date-nav" data-mon="-1" aria-label="Previous month"' + (focus <= first ? ' disabled' : '') + '>&lsaquo;</button>' +
        '<b>' + esc(title) + '</b><button type="button" class="date-nav" data-mon="1" aria-label="Next month"' + (focus >= last ? ' disabled' : '') + '>&rsaquo;</button>' +
        '<button type="button" class="cal-x" data-close aria-label="Close">&times;</button></div>' +
        '<div class="cal-grid">' + ['S', 'M', 'T', 'W', 'T', 'F', 'S'].map(function(x) { return '<span class="cal-dow">' + x + '</span>'; }).join('') + cells + '</div>' +
        '<p class="cal-key"><i></i>' + (weeks ? 'Game days. Pick any day to jump to its week.' : 'Days with games') + '</p></div>';
      var on = wrap.querySelector('.cal-day.on') || wrap.querySelector('.cal-day.has') || wrap.querySelector('.cal-day');
      if (on) on.focus();
    }
    wrap.addEventListener('click', function(e) {
      if (e.target.closest('[data-close]')) { close(); return; }
      var m = e.target.closest('[data-mon]');
      if (m && !m.disabled) { focus = monthAdd(focus, +m.getAttribute('data-mon')); draw(); return; }
      var b = e.target.closest('.cal-day');
      if (b && !b.disabled) { close(); opts.onPick(weeks ? b.getAttribute('data-w') : b.getAttribute('data-d')); }
    });
    document.addEventListener('keydown', onKey);
    document.body.appendChild(wrap);
    draw();
  }
  var CAL_BTN = '<button type="button" class="date-cal" id="dateCal" aria-label="Open calendar">' +
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg></button>';
  // The week bar (NFL / NCAAF): ‹ Week 11 › with the dates under it
  function weekBar(weeks, cur, thisWeek) {
    var i = weeks.map(function(w) { return w.key; }).indexOf(cur), w = weeks[i];
    return '<div class="date-bar">' +
      '<button class="date-nav" id="weekPrev" aria-label="Previous week"' + (i <= 0 ? ' disabled' : '') + '>&lsaquo;</button>' +
      '<div class="date-label-wrap"><span class="date-label">' + esc(w.label) + ' <span class="week-range">' + esc(weekRange(w)) + '</span></span>' +
      (cur !== thisWeek ? '<button class="date-today-btn" id="weekNowBtn" type="button">This week</button>' : '') + CAL_BTN + '</div>' +
      '<button class="date-nav" id="weekNext" aria-label="Next week"' + (i >= weeks.length - 1 ? ' disabled' : '') + '>&rsaquo;</button></div>';
  }

  // ------------------------------------------------------------ Odds page
  // Every source's price for every game on the selected date (or week), from
  // {slug}/odds.json (the index) and {slug}/odds/{date}.json (one file per
  // date; sport_build.write_odds_page). One table: Team and Open pinned on
  // the left, then a column per source (major sportsbooks, other sportsbooks,
  // then exchanges and prediction markets). Games that haven't started link
  // each price to its source (Gambly links with the partner code); started
  // and finished games show each source's closing line, with its opening line
  // under it when it moved. The best price per side gets a green outline.
  var MKT_CUR = null;
  var MKT_WORD = { ml: 'moneyline', ml3: '3-way moneyline', ats: 'spread', total: 'total', btts: 'BTTS', rfi: 'NRFI / YRFI' };
  var YN_SIDES = { total: ['over', 'under'], btts: ['yes', 'no'], rfi: ['yrfi', 'nrfi'] };
  function renderOdds() {
    fetch(ROOT + SPORT_SLUG + '/odds.json').then(function(r) { return r.ok ? r.json() : null; }).then(function(O) {
      // NHL's data.json has its own shape: its odds.json carries what this page needs
      if (O && O.segments && !(D && D.segments)) D = { sport: O.sport, label: O.label, sportType: O.sportType, segments: O.segments, teams: O.teams || {}, otherTeams: {} };
      if (!D) return;
      var dates = O ? Object.keys(O.days || {}).sort() : [];
      if (!dates.length) { app.innerHTML = emptyNote('No ' + esc(D.label) + ' games on the schedule yet.'); return; }
      var weeks = O.calendar === 'weekly' && (O.weeks || []).length ? O.weeks : null;
      var sources = O.sources || {}, order = O.order || [];
      var cache = {};
      function load(ds) {
        return Promise.all(ds.map(function(d) {
          if (cache[d]) return cache[d];
          cache[d] = fetch(ROOT + SPORT_SLUG + '/odds/' + d + '.json').then(function(r) { return r.ok ? r.json() : { games: [] }; });
          return cache[d];
        }));
      }
      // the selected date, or week
      var cur, thisWeek = null;
      if (weeks) {
        var t = todayET(), keys = weeks.map(function(w) { return w.key; });
        thisWeek = (weekFor(weeks, t) || weeks[weeks.length - 1]).key;
        var wantW = new URLSearchParams(location.search).get('week');
        cur = keys.indexOf(wantW) !== -1 ? wantW : thisWeek;
      } else {
        var want = urlDate();
        cur = want || defaultDate(dates);
      }
      function slate() {
        if (!weeks) return O.days[cur] ? [cur] : [];
        var w = weeks.filter(function(x) { return x.key === cur; })[0];
        return dates.filter(function(d) { return d >= w.start && d <= w.end; });
      }
      function go(x) {
        cur = x;
        if (weeks) { var u = new URL(location.href); u.searchParams.set('week', x); u.searchParams.delete('date'); history.replaceState(null, '', u); }
        else setUrlDate(x);
        show();
      }
      function markets(k) { return (O.markets || []).filter(function(x) { return x[0] === k; }); }
      function code(x) { return team(x).code || shortName(x); }
      // the rows for one market: [side key, label (null = the team on that row)]
      function sides(m, kind) {
        if (kind === 'ml3') return [['away', null], ['draw', 'Tie'], ['home', null]];
        if (kind === 'yn') return [[(YN_SIDES[m] || ['over', 'under'])[0], null, 'away'], [(YN_SIDES[m] || ['over', 'under'])[1], null, 'home']];
        return [['away', null], ['home', null]];
      }
      // {line, price, link} for one source and side
      function val(row, m, s) {
        if (!row || !row[s]) return null;
        if (m === 'total') return { line: row.line, price: row[s].price, link: row[s].link };
        return { line: row[s].line != null ? signed(row[s].line) : null, price: row[s].price, link: row[s].link };
      }
      // the best (or Open) price for a side, from g.best / g.open
      function top(src, m, s) {
        if (!src) return null;
        if (m === 'total') return src[s] != null ? { line: src.line, price: src[s] } : null;
        if (m === 'ats') return src[s] ? { line: signed(src[s].line), price: src[s].price } : null;
        return src[s] != null ? { line: null, price: src[s] } : null;
      }
      function same(a, b) { return !!a && !!b && a.price === b.price && String(a.line) === String(b.line); }
      function counts(b, m) { return m === 'ml3' || m === 'btts' || !(sources[b] || {}).x; }
      function cellTxt(v) { return (v.line != null ? '<span class="ob-ln">' + esc(v.line) + '</span>' : '') + '<span class="ob-pr">' + esc(signed(v.price)) + '</span>'; }
      function name(b) { return (sources[b] || {}).name || 'Source ' + b; }
      function head(b) {
        var s = sources[b] || {};
        return s.logo ? '<img class="ob-logo" src="' + ROOT + s.logo + '" alt="' + esc(name(b)) + '" title="' + esc(name(b)) + '" loading="lazy">' : '<span class="ob-bname">' + esc(name(b)) + '</span>';
      }
      function teamCell(g, sd) {
        if (sd[1]) return '<span class="ob-team"><span class="ob-tie">' + esc(sd[1]) + '</span></span>';
        var slug = g[sd[2] || sd[0]];
        return '<span class="ob-team">' + badge(slug, 20) + '<span class="tn-full">' + esc(shortName(slug)) + '</span><span class="tn-short mono">' + esc(code(slug)) + '</span></span>';
      }
      function table(games, k, m, kind) {
        var ids = {};
        games.forEach(function(g) { Object.keys((((g.books || {})[k] || {})[m]) || {}).forEach(function(b) { ids[b] = 1; }); });
        var cols = order.filter(function(b) { return ids[b]; });
        var span = 2 + cols.length;
        var body = games.map(function(g) {
          var books = ((g.books || {})[k] || {})[m] || {}, opens = ((g.opens || {})[k] || {})[m] || {};
          var best = ((g.best || {})[k] || {})[m], open = ((g.open || {})[k] || {})[m];
          var past = g.state !== 'pre';
          var rows = sides(m, kind).map(function(sd) {
            var s = sd[0], b = top(best, m, s), o = top(open, m, s);
            return '<tr><th scope="row" class="ob-c-team">' + teamCell(g, sd) + '</th>' +
              '<td class="ob-c-open mono">' + (o ? cellTxt(o) : '<span class="ob-na">&ndash;</span>') + '</td>' +
              cols.map(function(id) {
                var v = val(books[id], m, s);
                if (!v) return '<td class="ob-na">&ndash;</td>';
                var was = past ? val(opens[id], m, s) : null;
                var inner = cellTxt(v) + (was && !same(was, v) ? '<span class="ob-was">op ' + esc((was.line != null ? was.line + ' ' : '') + signed(was.price)) + '</span>' : '');
                var cls = 'ob-cell' + (counts(id, m) && same(v, b) ? ' ob-best' : '');
                return '<td class="' + cls + '">' + (v.link && !past ? '<a href="' + esc(v.link) + '" target="_blank" rel="sponsored noopener" title="' + esc(name(id)) + '">' + inner + '</a>' : inner) + '</td>';
              }).join('') + '</tr>';
          }).join('');
          return '<tbody class="ob-game"><tr class="ob-ghead"><td colspan="' + span + '"><span class="ob-time">' +
            (weeks && g.start ? esc(new Date(g.start).toLocaleDateString('en-US', { weekday: 'short', timeZone: 'America/New_York' })) + ' ' : '') +
            (g.start ? esc(timeET(g.start)) : 'TBD') + '</span></td></tr>' + rows + '</tbody>';
        }).join('');
        return '<div class="ob-scroll"><table class="ob-grid"><thead><tr><th class="ob-c-team" scope="col">Team</th><th class="ob-c-open" scope="col">Open</th>' +
          cols.map(function(b) { return '<th scope="col" class="ob-src">' + head(b) + '</th>'; }).join('') + '</tr></thead>' + body + '</table></div>';
      }
      function ago(iso) {
        var min = Math.round((Date.now() - Date.parse(iso)) / 60000);
        if (!(min >= 0)) return '';
        return min < 1 ? 'updated just now' : min < 60 ? 'updated ' + min + ' min ago' : min < 1440 ? 'updated ' + Math.floor(min / 60) + ' hr ago' : 'updated ' + timeET(iso);
      }
      function draw(docs) {
        var k = getSeg(), ms = markets(k);
        var games = [];
        docs.forEach(function(doc) { (doc.games || []).forEach(function(g) { games.push(g); }); });
        if (!ms.some(function(x) { return x[1] === MKT_CUR; })) {
          // start on the first market with lines on this slate
          var withLines = ms.filter(function(x) { return games.some(function(g) { var b = ((g.books || {})[k] || {})[x[1]]; return b && Object.keys(b).length; }); });
          MKT_CUR = ((withLines[0] || ms[0]) || [])[1] || null;
        }
        var mk = ms.filter(function(x) { return x[1] === MKT_CUR; })[0];
        var html = weeks ? weekBar(weeks, cur, thisWeek) : dateBar(cur, dates, true);
        html += '<p class="ob-sub">' + esc(seg(k).label) + ' odds from every source we track' + (O.updated ? ' &middot; ' + esc(ago(O.updated)) : '') + '.</p>';
        html += '<div class="sport-seg-row odds-controls">' + (D.segments.length > 1 ? segToggle('pageSeg', k) : '') +
          '<div class="seg-toggle" id="oddsMkt">' + ms.map(function(x) {
            return '<button class="seg-btn" data-mkt="' + x[1] + '" aria-pressed="' + (x[1] === MKT_CUR) + '">' + esc(x[2]) + '</button>';
          }).join('') + '</div></div>' +
          '<p class="ob-rows">Top row: Over / Yes. Bottom row: Under / No.</p>';
        var lined = mk && games.some(function(g) { var b = ((g.books || {})[k] || {})[mk[1]]; return b && Object.keys(b).length; });
        var first = slate()[0];
        if (!games.length) html += '<div class="no-games-note">No ' + esc(D.label) + ' games ' + (weeks ? 'this week' : 'on ' + esc(dateLabel(cur))) + '.</div>';
        else {
          if (!lined) html += '<div class="no-games-note">' + (first && first < todayET() ? 'Lines not available.' : 'No ' + esc(seg(k).label) + ' ' + (mk ? MKT_WORD[mk[1]] || esc(mk[2]) : 'lines') + ' posted yet.') + '</div>';
          html += table(games, k, mk ? mk[1] : null, mk ? mk[3] : 'side');
        }
        if (mk && mk[1] === 'btts') html += '<p class="odds-note">Both teams to score in the 1st period. BTTS isn&rsquo;t on our odds feed, so this is a consensus price across the books, entered by our team.</p>';
        html += '<p class="odds-note">Green outline: the best price for each side at the sportsbooks (for spreads and totals, at the line most books post). ' +
          'Open: the best price when lines first appeared. Finished games show each source&rsquo;s closing line, with its opening line (&ldquo;op&rdquo;) when it moved. ' +
          'Odds via Unabated, refreshed every 10 minutes; prices can move before you open a link. 21+. Gambling problem? Call 1-800-GAMBLER.</p>';
        app.innerHTML = html;
        if (weeks) {
          var keys = weeks.map(function(w) { return w.key; }), i = keys.indexOf(cur);
          var p = document.getElementById('weekPrev'), n = document.getElementById('weekNext'), now = document.getElementById('weekNowBtn');
          if (p) p.onclick = function() { if (i > 0) go(keys[i - 1]); };
          if (n) n.onclick = function() { if (i < keys.length - 1) go(keys[i + 1]); };
          if (now) now.onclick = function() { go(thisWeek); };
        } else wireDateBar(dates, cur, go);
        document.getElementById('dateCal').onclick = function() { openCalendar({ days: O.days, cur: cur, weeks: weeks, onPick: go }); };
        var ps = document.getElementById('pageSeg');
        if (ps) ps.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { setSeg(b.getAttribute('data-seg')); show(); } };
        document.getElementById('oddsMkt').onclick = function(e) { var b = e.target.closest('[data-mkt]'); if (b) { MKT_CUR = b.getAttribute('data-mkt'); show(); } };
      }
      function show() { load(slate()).then(draw); }
      show();
    }).catch(function(e) {
      app.innerHTML = emptyNote('Couldn&rsquo;t load the odds. Try reloading.');
      if (window.console) console.error(e);
    });
  }

  // ---------------------------------------------------------------- boot
  // "i" tooltips open on tap (phones) as well as hover
  document.addEventListener('click', function(e) {
    var tip = e.target.closest ? e.target.closest('.info-tip') : null;
    document.querySelectorAll('.info-tip.open').forEach(function(t) { if (t !== tip) t.classList.remove('open'); });
    if (tip) tip.classList.toggle('open');
  });
  // NHL's data.json is its own shape; its Stats and Trends pages read the shared shape (nhl/sport.json)
  var DATA_FILE = SPORT_SLUG === 'nhl' && (SECTION === 'stats' || SECTION === 'trends') ? 'sport.json' : 'data.json';
  fetch(ROOT + SPORT_SLUG + '/' + DATA_FILE).then(function(r) { return r.json(); }).then(function(data) {
    D = data;
    if (SECTION === 'odds') { renderOdds(); return; }   // works from odds.json alone for NHL
    if (!D.segments || !D.segments.length) return;
    if (SECTION === 'games') renderGames();
    else if (SECTION === 'stats') renderStats();
    else if (SECTION === 'trends') renderTrends();
    else if (SECTION === 'team') renderTeam();
    else if (SECTION === 'teams') renderTeamsIndex();
    else if (SECTION === 'odds') renderOdds();
  }).catch(function(e) {
    if (SECTION !== 'team' && SECTION !== 'teams') app.innerHTML = emptyNote('Couldn&rsquo;t load ' + esc(SPORT_SLUG) + ' data. Try reloading.');
    if (window.console) console.error(e);
  });
})();
