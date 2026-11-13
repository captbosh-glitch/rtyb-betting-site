/*
 * Matchups, Stats, Trends and team pages for every sport except NHL (NHL's
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
    var cls = r >= 3 ? 'u-pos2' : r > 0.5 ? 'u-pos1' : r < -3 ? 'u-neg2' : r < -0.5 ? 'u-neg1' : 'u-mid';
    return '<span class="u-pill ' + cls + '">' + fmtUnits(r) + '</span>';
  }
  // green above +0.5u, red below -0.5u, yellow between (CLAUDE.md color rule)
  function unitCls(u) { var r = Math.round(u * 100) / 100; return r > 0.5 ? 'pos' : r < -0.5 ? 'neg' : 'mid'; }
  function pct(w, l) { return (w + l) ? Math.round(1000 * w / (w + l)) / 10 : null; }
  function pctTxt(w, l) { var p = pct(w, l); return p == null ? '&mdash;' : p.toFixed(1) + '%'; }
  // Win % leaves ties and pushes out (Favorites 2-0-4 is 100%); Tie % is out
  // of every game played. Same rule as winPct in template.html (NHL).
  function winPct(w, l, t) { var n = w + l; return n ? w / n : null; }
  function tiePct(w, l, t) { var n = w + l + (t || 0); return n ? (t || 0) / n : null; }
  function pct1(x) { return x == null ? null : Math.round(1000 * x) / 10; }
  function suPctTxt(r) { var p = pct1(winPct(r[0], r[1], r[2])); return p == null ? '&mdash;' : p.toFixed(1) + '%'; }
  function suTieTxt(r) { var p = pct1(tiePct(r[0], r[1], r[2])); return p == null ? '' : ' <small class="tie-pct">Tie ' + p.toFixed(1) + '%</small>'; }
  function rec(r) { return r ? r[0] + '-' + r[1] + '-' + r[2] : '0-0-0'; }
  // Teams outside the league (non-Division I opponents) have a name and
  // maybe a logo; college ones go by the school name (the nickname dropped)
  function team(slug) {
    if (D.teams[slug]) return D.teams[slug];
    var full = (D.otherTeams || {})[slug] || slug, college = D.sport === 'ncaab' || D.sport === 'ncaaf';
    return { name: full, short: college ? full.replace(/\s+\S+$/, '') || full : full, code: '', color: null, logo: (D.otherLogos || {})[slug] || null };
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
  function emptyNote(html) { return '<div class="section-empty">' + html + '</div>'; }
  function allDates() { return Object.keys(D.games || {}).sort(); }

  // -------------------------------------------------------- matchup card
  // Chris's Matchups spec: one compact table per game for every sport, teams
  // on the rows (name per the naming rule: desktop name, phone abbreviation)
  // and the sport's markets across the top. Top-left: the start time, "LIVE
  // · clock · period" or "FINAL · segment". Each team gets its segment score
  // once the game starts; the full game sits under a divider. A finished
  // game shows its results by highlight only (resultCls): the side that won
  // a soft green fill, the side that lost dimmed, a tie or push soft yellow.
  function flipRes(r) { return { W: 'L', L: 'W' }[r] || r; }
  function nameHtml(slug) { return '<span class="tn-full">' + esc(shortName(slug)) + '</span><span class="tn-short">' + esc(tcode(slug)) + '</span>'; }
  // periods in a segment, for the score so far
  function segPeriods(k) { return { '1q': 1, '1p': 1, '1i': 1, f5: 5 }[k] || (k === '1h' ? (D.sport === 'ncaab' ? 1 : 2) : 1); }
  // [away, home] in a segment so far, or null before it starts
  function segScore(g, k) {
    var r = (g.res || {})[k];
    if (r && r.sc) return r.sc;
    if (g.state === 'pre' || !g.als || !g.hls) return null;
    var n = segPeriods(k), a = g.als.slice(0, n).filter(function(x) { return typeof x === 'number'; }), h = g.hls.slice(0, n).filter(function(x) { return typeof x === 'number'; });
    if (!a.length || !h.length) return null;
    return [a.reduce(function(s, x) { return s + x; }, 0), h.reduce(function(s, x) { return s + x; }, 0)];
  }
  // the segment whose score shows next to the names (MLB: First 5)
  function cardSeg(k) { return D.sportType === 'baseball' ? 'f5' : k; }
  // "OT", "2OT", "SO" after a final score
  function otTag(g) { return g.ot || ((g.detail || '').split('/')[1] || '').trim(); }
  // the live clock as [clock, period]: "4:58 - 3rd" -> ['4:58', '3RD']
  function liveClock(g) {
    var p = String(g.detail || '').split(' - ');
    return p.length > 1 ? [p[0].trim(), p[p.length - 1].trim().toUpperCase()] : ['', livePeriod(g)];
  }
  function cardStatus(g, k) {
    if (g.state === 'final') return 'FINAL &middot; ' + esc(seg(cardSeg(k)).tag);
    if (g.state === 'in') {
      var c = liveClock(g);
      return '<span class="st-live">LIVE' + (c[0] ? ' &middot; ' + esc(c[0]) : '') + (c[1] ? ' &middot; ' + esc(c[1]) : '') + '</span>';
    }
    return g.start ? esc(timeET(g.start)) : 'TBD';
  }
  // W (won) / L (lost) / P (tie or push) -> the cell's highlight
  function resultCls(r) { return r === 'W' ? ' mc-w' : r === 'L' ? ' mc-l' : r === 'P' ? ' mc-p' : ''; }
  // the markets across the top: [market, header]
  function cardCols(k) {
    if (D.sport === 'nhl') return [['ml', 'ML'], ['total', 'O/U'], ['btts', 'BTTS'], ['ml3', '3-WAY']];
    if (D.sportType === 'baseball') return [['rfi', 'NRFI/YRFI'], ['ml', 'F5 ML'], ['ats', 'F5 RUN LINE'], ['total', 'F5 O/U']];
    return [['ats', 'SPREAD'], ['total', 'O/U']].concat(hasMl(k) ? [['ml', 'ML']] : []);
  }
  // one cell: row 0 = away (Over / Yes / YRFI), 1 = home (Under / No / NRFI),
  // 2 = the tie (NHL 3-way only)
  function cardCell(g, k, m, row) {
    var sk = m === 'rfi' ? '1i' : cardSeg(k), o = ((g.odds || {})[sk] || {}), fin = g.state === 'final';
    var r = (g.res || {})[sk], done = fin && r && r.sc ? r : null, home = row === 1, res = null, line = null, price = null, tip = '';
    function side(x) { if (!done) return null; if (done.na || !x || x === 'NA') return 'P'; x = home ? flipRes(x) : x; return x === 'W' || x === 'L' ? x : 'P'; }
    function yn(x, want) { if (!done) return null; if (done.na || !x || x === 'NA' || x === 'P') return 'P'; return x === want ? 'W' : 'L'; }
    if (m === 'ml') {
      if (row === 2) return '<td class="mc-cell mc-none"></td>';
      price = o.ml ? o.ml[home ? 'home' : 'away'] : null; res = side(done && done.su);
    } else if (m === 'ats') {
      if (row === 2) return '<td class="mc-cell mc-none"></td>';
      var a = o.ats && o.ats[home ? 'home' : 'away'];
      if (a) { line = signed(a.line); price = a.price; }
      res = side(done && done.ats);
    } else if (m === 'total') {
      if (row === 2) return '<td class="mc-cell mc-none"></td>';
      var ln = o.total ? o.total.line : D.sport === 'nhl' ? 1.5 : null;
      if (o.total) { line = ln; price = o.total[home ? 'under' : 'over']; }
      if (ln != null) tip = (home ? 'Under ' : 'Over ') + ln;
      res = yn(done && done.tot, home ? 'U' : 'O');
    } else if (m === 'btts') {
      if (row === 2) return '<td class="mc-cell mc-none"></td>';
      price = o.btts ? o.btts[home ? 'no' : 'yes'] : null; tip = home ? 'BTTS No' : 'BTTS Yes';
      res = yn(done && done.btts, home ? 'N' : 'Y');
    } else if (m === 'rfi') {
      if (row === 2) return '<td class="mc-cell mc-none"></td>';
      price = o.nrfi_yrfi ? o.nrfi_yrfi[home ? 'nrfi' : 'yrfi'] : null; tip = home ? 'NRFI' : 'YRFI';
      res = yn(done && done.rfi, home ? 'N' : 'Y');
    } else if (m === 'ml3') {
      var want = ['W', 'L', 'T'][row];
      price = o.ml3 ? o.ml3[['away', 'home', 'draw'][row]] : null;
      // only the outcome that hit is green; a tied period is the TIE cell
      if (done) res = done.na || !done.su || done.su === 'NA' ? 'P' : done.su === want ? 'W' : 'L';
    }
    var none = line == null && price == null, body = none ? '<span class="mc-dash">&ndash;</span>' : oddsCell(line, price);
    // no price, nothing to highlight
    return '<td class="mc-cell' + (none ? '' : resultCls(res)) + '"' + (tip ? ' data-tip="' + esc(tip) + '" data-tap title="' + esc(tip) + '"' : '') + '>' + body + '</td>';
  }
  // "FULL GAME  WSH 101 · IND 114 OT", away first, the winner bold
  function fullGameRow(g) {
    if (g.as == null || g.hs == null || (g.state !== 'final' && g.state !== 'in')) return '';
    var fin = g.state === 'final', lbl = 'FULL GAME';
    if (!fin) { var c = liveClock(g); lbl += ' &middot; <span class="st-live">LIVE' + (c[1] || c[0] ? ' &middot; ' + esc((c[1] + ' ' + c[0]).trim()) : '') + '</span>'; }
    function sc(slug, n, other) { return '<span class="mc-fs' + (fin ? (n > other ? ' mc-fs-win' : n < other ? ' mc-fs-lose' : '') : '') + '">' + esc(tcode(slug)) + ' ' + esc(n) + '</span>'; }
    var ot = fin ? otTag(g) : '';
    return '<div class="mc-full"><span class="mc-full-lbl">' + lbl + '</span><span class="mc-full-sc">' + sc(g.away, g.as, g.hs) + ' &middot; ' + sc(g.home, g.hs, g.as) +
      (ot ? ' <span class="mc-ot">' + esc(ot) + '</span>' : '') + '</span></div>';
  }
  function gameCard(g, k) {
    var cols = cardCols(k), sc = g.state !== 'pre' ? segScore(g, cardSeg(k)) : null;
    function teamRow(slug, i) {
      return '<tr><th scope="row" class="mc-team"><div class="mc-tw"><span class="mc-tn">' + teamLink(slug, badge(slug, 22) + nameHtml(slug)) + '</span>' +
        (sc ? '<b class="mc-sc">' + esc(sc[i]) + '</b>' : '') + '</div></th>' +
        cols.map(function(c) { return cardCell(g, k, c[0], i); }).join('') + '</tr>';
    }
    // NHL: a TIE row under the teams, only the 3-way column filled
    var tie = D.sport === 'nhl' ? '<tr class="mc-tie"><th scope="row" class="mc-team"><span class="mc-tie-lbl">TIE &middot; 3-WAY</span></th>' +
      cols.map(function(c) { return c[0] === 'ml3' ? cardCell(g, k, 'ml3', 2) : '<td class="mc-cell mc-none"></td>'; }).join('') + '</tr>' : '';
    return '<div class="game-card mc" data-game="' + esc(g.id) + '" style="--mc-n:' + cols.length + '">' +
      '<table class="mc-grid"><thead><tr><th scope="col" class="mc-st">' + cardStatus(g, k) + '</th>' +
      cols.map(function(c) { return '<th scope="col">' + esc(c[1]) + '</th>'; }).join('') + '</tr></thead>' +
      '<tbody>' + teamRow(g.away, 0) + teamRow(g.home, 1) + tie + '</tbody></table>' + fullGameRow(g) + '</div>';
  }

  var GAME_INDEX = null, GAME_DAY = {};
  function findGame(id) {
    if (!GAME_INDEX) {
      GAME_INDEX = {};
      Object.keys(D.games).forEach(function(d) { D.games[d].forEach(function(g) { GAME_INDEX[g.id] = g; GAME_DAY[g.id] = d; }); });
    }
    return GAME_INDEX[id];
  }

  // pin an element (position: sticky) just under the site header, which is
  // sticky too; its height changes with the viewport
  function stickBelowNav(el) {
    if (!el) return;
    function place() { var hn = document.querySelector('.hn'); el.style.top = (hn ? hn.getBoundingClientRect().height : 0) + 'px'; }
    place();
    if (!stickBelowNav.wired) { stickBelowNav.wired = true; window.addEventListener('resize', function() { document.querySelectorAll('[data-stick]').forEach(function(x) { x.__place && x.__place(); }); }); }
    el.setAttribute('data-stick', '');
    el.__place = place;
  }

  // ------------------------------------------------------------ date bar
  // cal: add the calendar button (openCalendar, wired by the page)
  // words: "Today · Thu, Nov 12" (Matchups)
  function dateBar(cur, dates, cal, words) {
    var lbl = dateLabel(cur);
    if (words && (lbl === 'Today' || lbl === 'Yesterday')) lbl += ' · ' + new Date(cur + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' });
    return '<div class="date-bar">' +
      '<button class="date-nav" id="datePrev" aria-label="Previous day"' + (cur <= dates[0] ? ' disabled' : '') + '>&lsaquo;</button>' +
      '<div class="date-label-wrap"><span class="date-label">' + esc(lbl) + '</span>' +
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

  // ------------------------------------------------------- Results box
  // "[Weekday] [M/D] Results" (football: "Week N Results"): the finished
  // games' record, win % and units for the sport's markets in plain words,
  // in the sport's market order. Ties and pushes stay out of the win %
  // (Favorites 2-0-4 is 100%).
  function resultRows(games, k) {
    var rows = [];
    function acc(label, opts) { var x = { label: label, w: 0, l: 0, t: 0, u: 0, n: 0, ties: !!opts.ties, noTie: !!opts.noTie, always: !!opts.always }; rows.push(x); return x; }
    function add(x, r, u) {
      if (!r) return;
      if (r === 'W') x.w++; else if (r === 'L') x.l++; else x.t++;
      if (u != null) { x.u += u; x.n++; }
    }
    function done(g, key) { var r = (g.res || {})[key]; return g.state === 'final' && r && r.sc && !r.na ? r : null; }
    function suSide(r, home) { var x = r.su; if (!x || x === 'NA') return null; x = home ? flipRes(x) : x; return x === 'W' || x === 'L' ? x : 'T'; }
    if (D.sport === 'nhl') {
      var hm = acc('Home teams', { ties: true }), fv = acc('Favorites', { ties: true }), ov = acc('O/U: Over 1.5', { noTie: true }),
          bt = acc('BTTS Yes', { noTie: true }), m3 = acc('3-way ML (home team)', { noTie: true, always: true });
      games.forEach(function(g) {
        var r = done(g, '1p'); if (!r) return;
        var u = r.u || {};
        add(hm, suSide(r, true), u.su ? u.su[1] : null);
        var f = segFavSide(g, '1p');
        if (f) add(fv, suSide(r, f === 'home'), u.su ? u.su[f === 'away' ? 0 : 1] : null);
        if (r.tot === 'O' || r.tot === 'U') add(ov, r.tot === 'O' ? 'W' : 'L', u.tot ? u.tot[0] : null);
        if (r.btts === 'Y' || r.btts === 'N') add(bt, r.btts === 'Y' ? 'W' : 'L', u.btts ? u.btts[0] : null);
        if (r.su && r.su !== 'NA') add(m3, r.su === 'L' ? 'W' : 'L', u.ml3 ? u.ml3[1] : null);
      });
    } else if (D.sportType === 'baseball') {
      var bh = acc('Home teams (F5 moneyline)', { ties: true }), bf = acc('Favorites (F5)', { ties: true }), yr = acc('YRFI', { noTie: true }), fo = acc('F5 O/U: Over', {});
      games.forEach(function(g) {
        var r = done(g, 'f5'), ri = done(g, '1i');
        if (ri && (ri.rfi === 'Y' || ri.rfi === 'N')) add(yr, ri.rfi === 'Y' ? 'W' : 'L', ri.u && ri.u.rfi ? ri.u.rfi[0] : null);
        if (!r) return;
        var u = r.u || {};
        add(bh, suSide(r, true), u.su ? u.su[1] : null);
        var f = segFavSide(g, 'f5');
        if (f) add(bf, suSide(r, f === 'home'), u.su ? u.su[f === 'away' ? 0 : 1] : null);
        if (r.tot && r.tot !== 'NA') add(fo, { O: 'W', U: 'L' }[r.tot] || 'T', u.tot ? u.tot[0] : null);
      });
    } else {
      var ml = hasMl(k);
      var sh = ml ? acc('Home teams (moneyline)', {}) : null, sf = ml ? acc('Favorites (moneyline)', {}) : null,
          sa = acc('Favorites (spread)', {}), so = acc('O/U: Over', {});
      games.forEach(function(g) {
        var r = done(g, k); if (!r) return;
        var u = r.u || {}, o = (g.odds || {})[k] || {};
        if (ml) {
          add(sh, suSide(r, true), u.su ? u.su[1] : null);
          var f = segFavSide(g, k);
          if (f) add(sf, suSide(r, f === 'home'), u.su ? u.su[f === 'away' ? 0 : 1] : null);
        }
        var line = ((o.ats || {}).away || {}).line;
        if (r.ats && r.ats !== 'NA' && typeof line === 'number' && line !== 0) {
          var fs = line < 0 ? 'away' : 'home', x = fs === 'home' ? flipRes(r.ats) : r.ats;
          add(sa, x === 'W' || x === 'L' ? x : 'T', u.ats ? u.ats[fs === 'away' ? 0 : 1] : null);
        }
        if (r.tot && r.tot !== 'NA') add(so, { O: 'W', U: 'L' }[r.tot] || 'T', u.tot ? u.tot[0] : null);
      });
    }
    rows.forEach(function(x) { var d = x.w + x.l; x.pct = d ? x.w / d : null; x.gp = x.w + x.l + x.t; });
    return rows.filter(function(x) { return x.gp || (x.always && games.some(function(g) { return g.state === 'final'; })); });
  }
  function resultsTitle(d) {
    var dt = new Date(d + 'T12:00:00Z');
    return dt.toLocaleDateString('en-US', { weekday: 'long', timeZone: 'UTC' }) + ' ' + (dt.getUTCMonth() + 1) + '/' + dt.getUTCDate() + ' Results';
  }
  function resultsBox(games, k, title) {
    if (!games.some(function(g) { return g.state === 'final'; })) return '';
    var rows = resultRows(games, k);
    if (!rows.length) return '';
    return '<div class="daily-summary gm-results"><h3>' + esc(title) + '</h3>' +
      '<div class="ds-row ds-head"><span></span><span class="ds-right"><span class="ds-col-rec">Record</span><span class="ds-col-pct">Win %</span><span class="ds-col-units">Units</span></span></div>' +
      rows.map(function(x) {
        return '<div class="ds-row"><span class="ds-label">' + esc(x.label) + '</span><span class="ds-right">' +
          '<span class="ds-record ds-col-rec mono">' + x.w + '-' + x.l + (x.noTie ? '' : '-' + x.t) + '</span>' +
          '<span class="ds-col-pct mono">' + (x.pct == null ? '&mdash;' : Math.round(x.pct * 100) + '%') + '</span>' +
          '<span class="ds-col-units">' + (x.n ? unitsPill(x.u, true) : '<span class="u-pill u-none">&mdash;</span>') + '</span></span></div>';
      }).join('') + '</div>';
  }

  // ------------------------------------------------------- Matchups page
  // One template for every sport: the date bar (football: the week bar),
  // a pinned segment toggle (spread sports with two segments), the Results
  // box, then the cards, two to a row on desktop. Football weeks list
  // finished games last.
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
  function gmSegBar(k) {
    return !periodFamily() && D.segments.length > 1 ? '<div class="gm-stick" id="gmStick"><div class="sport-seg-row">' + segToggle('pageSeg', k) + '</div></div>' : '';
  }
  function renderGames() {
    var weeks = D.schedule === 'week' ? D.weeks || [] : null;
    var dates = allDates();
    if (weeks ? !weeks.length : !dates.length) { app.innerHTML = emptyNote('No ' + esc(D.label) + ' matchups loaded yet.'); return; }
    var keys = weeks ? weeks.map(function(w) { return w.key; }) : null;
    var thisWeek = weeks ? currentWeek(weeks) : null, cur;
    if (weeks) { var want = new URLSearchParams(location.search).get('week'); cur = keys.indexOf(want) !== -1 ? want : thisWeek; }
    else cur = urlDate() || defaultDate(dates);
    function go(x) {
      if (weeks) { if (keys.indexOf(x) === -1) { var w = weekFor(weeks, x); if (!w) return; x = w.key; } cur = x; var u = new URL(location.href); u.searchParams.set('week', x); u.searchParams.delete('date'); history.replaceState(null, '', u); }
      else { cur = x; setUrlDate(x); }
      draw();
    }
    function draw() {
      var k = getSeg(), games, title, none;
      if (weeks) {
        var w = weeks[keys.indexOf(cur)];
        games = weekGames(cur); title = w.label + ' Results'; none = 'this week';
      } else {
        games = (D.games[cur] || []).slice().sort(function(a, b) { return (a.start || '') < (b.start || '') ? -1 : (a.start || '') > (b.start || '') ? 1 : 0; });
        title = resultsTitle(cur); none = 'on ' + dateLabel(cur);
      }
      var html = (weeks ? weekBar(weeks, cur, thisWeek) : dateBar(cur, dates, true, true)) + gmSegBar(k) + resultsBox(games, k, title);
      if (!games.length) html += '<div class="no-games-note">No ' + esc(D.label) + ' matchups ' + esc(none) + '.</div>';
      html += '<div class="games-list mc-list">' + games.map(function(g) { return gameCard(g, k); }).join('') + '</div>';
      app.innerHTML = html;
      wireTips(app);
      stickBelowNav(document.getElementById('gmStick'));
      if (weeks) {
        var i = keys.indexOf(cur), p = document.getElementById('weekPrev'), n = document.getElementById('weekNext'), t = document.getElementById('weekNowBtn');
        if (p) p.onclick = function() { if (i > 0) go(keys[i - 1]); };
        if (n) n.onclick = function() { if (i < keys.length - 1) go(keys[i + 1]); };
        if (t) t.onclick = function() { go(thisWeek); };
      } else wireDateBar(dates, cur, go);
      var cal = document.getElementById('dateCal');
      if (cal) cal.onclick = function() { openCalendar({ days: dayCounts(), cur: cur, weeks: weeks, onPick: go }); };
      var ps = document.getElementById('pageSeg');
      if (ps) ps.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { setSeg(b.getAttribute('data-seg')); draw(); } };
    }
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
  // ------------------------------------------- Teams list + team pages
  // One layout for every sport (Chris's Teams spec). The market pills come
  // from the sport's family config (D.markets: [segment, market, label,
  // kind], scripts/sports.py). A team's result in a market, from res (away
  // side): ml W/L/T, ats W/L/P, total O/U/P, btts Y/N, rfi Y/N, with units
  // u[market] = [away, home] ([over, under] / [yes, no]). NHL and MLB count
  // a tied segment as a tie; the spread family calls it a push.
  function tieSport() { return periodFamily(); }
  function tmMarkets(k) {
    return (D.markets || []).filter(function(m) { return !k || m[0] === k; }).map(function(m) {
      return { k: m[0], m: m[1], label: m[1] === 'total' && D.sport === 'nhl' ? 'Over 1.5' : m[2] };
    });
  }
  // the hit / miss / tie letters for runs, records and the game log
  var TM_INFO = {
    ml: { pct: 'Win %', hit: 'W', miss: 'L' }, ml3: { pct: 'Win %', hit: 'W', miss: 'L', tie: 'T' },
    ats: { pct: 'Cover %', hit: 'W', miss: 'L', tie: 'P' }, total: { pct: 'Over %', hit: 'O', miss: 'U', tie: 'P' },
    btts: { pct: 'Yes %', hit: 'Y', miss: 'N' }, rfi: { pct: 'NRFI %', hit: 'N', miss: 'Y' }
  };
  function tmTieLetter(m) { return m === 'ml' ? (tieSport() ? 'T' : 'P') : (TM_INFO[m].tie || 'P'); }
  function tmLetter(r, m) { return r === 'W' ? TM_INFO[m].hit : r === 'L' ? TM_INFO[m].miss : tmTieLetter(m); }
  function tmNoPush(m) { return m === 'btts' || m === 'rfi' || (m === 'total' && D.sport === 'nhl'); }
  function tmRecHead(m) {
    if (m === 'ml') return tieSport() ? 'W-L-T' : 'W-L-P';
    return { ml3: 'W-L-T', ats: 'W-L-P', total: tmNoPush('total') ? 'O-U' : 'O-U-P', btts: 'Y-N', rfi: 'N-Y' }[m];
  }
  function fbUnits(r) { return r === 'W' ? 0.9091 : r === 'L' ? -1 : 0; }   // -110 when only the line was saved
  // One team's result in one market: {r: 'W' (the hit side) | 'L' | 'T' (tie / push), u: units or null}
  function tmBet(g, k, m, slug) {
    var r = (g.res || {})[k];
    if (!r || !r.sc || r.na) return null;
    var home = g.home === slug, i = home ? 1 : 0, u = r.u || {}, o = (g.odds || {})[k] || {};
    function side(x) { if (!x || x === 'NA') return null; x = home ? flipRes(x) : x; return x === 'P' ? 'T' : x; }
    if (m === 'ml' || m === 'ml3') {
      var x = side(r.su);
      if (!x) return null;
      return { r: x, u: m === 'ml3' ? (u.ml3 ? u.ml3[i] : null) : (u.su ? u.su[i] : null) };   // 3-way: a tie loses the bet
    }
    if (m === 'ats') { var a = side(r.ats); return a ? { r: a, u: u.ats ? u.ats[i] : o.ats ? fbUnits(a) : null } : null; }
    if (m === 'total') {
      if (!r.tot || r.tot === 'NA') return null;
      var t = { O: 'W', U: 'L', P: 'T' }[r.tot];
      return { r: t, u: u.tot ? u.tot[0] : o.total ? fbUnits(t) : null };
    }
    if (m === 'btts') return r.btts === 'Y' || r.btts === 'N' ? { r: r.btts === 'Y' ? 'W' : 'L', u: u.btts ? u.btts[0] : null } : null;
    if (m === 'rfi') return r.rfi === 'Y' || r.rfi === 'N' ? { r: r.rfi === 'N' ? 'W' : 'L', u: u.rfi ? u.rfi[1] : null } : null;
    return null;
  }
  // games: one team's games, oldest first; side: all / home / away
  function tmAgg(slug, k, m, side, games) {
    var a = { w: 0, l: 0, t: 0, gp: 0, units: 0, priced: 0, seq: [] };
    games.forEach(function(g) {
      if ((side === 'home' && g.home !== slug) || (side === 'away' && g.away !== slug)) return;
      var b = tmBet(g, k, m, slug);
      if (!b) return;
      a.gp++; a.seq.push(b.r);
      if (b.r === 'W') a.w++; else if (b.r === 'L') a.l++; else a.t++;
      if (b.u != null) { a.units += b.u; a.priced++; }
    });
    // ties and pushes stay out of the win % (a 3-way bet loses on a tie)
    var d = m === 'ml3' ? a.w + a.l + a.t : a.w + a.l;
    a.pct = d ? a.w / d : null;
    a.tiePct = m === 'ml3' && a.gp ? a.t / a.gp : null;
    var n = 0, last = a.seq[a.seq.length - 1];
    for (var j = a.seq.length - 1; j >= 0 && a.seq[j] === last; j--) n++;
    a.run = n ? { r: last, n: n } : null;
    return a;
  }
  function tmRecTxt(a, m) { return !a.gp ? '&mdash;' : a.w + '-' + a.l + (tmNoPush(m) ? '' : '-' + a.t); }
  function tmPct(x) { return x == null ? '&mdash;' : Math.round(x * 100) + '%'; }
  function tmRunHtml(run, m) {
    if (!run) return '&mdash;';
    return '<span class="tl-streak ' + (run.r === 'W' ? 'good' : run.r === 'L' ? 'bad' : 'flat') + '">' + tmLetter(run.r, m) + run.n + '</span>';
  }
  // the last 10 as a record: "6-3-1" (a market that can't push: "6-4")
  function tmL10(seq, m) {
    var x = seq.slice(-10), w = 0, l = 0, t = 0;
    if (!x.length) return '&mdash;';
    x.forEach(function(r) { if (r === 'W') w++; else if (r === 'L') l++; else t++; });
    return w + '-' + l + (tmNoPush(m) ? '' : '-' + t);
  }
  // only the number is colored: --good above +0.5u, red below -0.5u, yellow between
  function tmUnits(a) {
    if (!a.priced) return '<span class="tm-u">&mdash;</span>';
    var r = Math.round(a.units * 100) / 100;
    return '<span class="tm-u ' + unitCls(r) + '">' + fmtUnits(r) + '</span>';
  }
  function teamGames(slug) {
    var out = [];
    allDates().forEach(function(d) { D.games[d].forEach(function(g) { if (g.away === slug || g.home === slug) out.push(g); }); });
    return out.sort(function(a, b) { return (a.start || '') < (b.start || '') ? -1 : (a.start || '') > (b.start || '') ? 1 : 0; });
  }
  function gameDay(g) { findGame(g.id); return GAME_DAY[g.id]; }
  // "Playing today" (weekly sports: this week)
  function tmSlate() {
    if (D.schedule === 'week') return D.weeks && D.weeks.length ? weekGames(currentWeek(D.weeks)) : [];
    return D.games[todayET()] || [];
  }
  function tmShortTime(g) {
    if (g.state === 'in') return 'LIVE';
    if (g.state === 'final' || g.state === 'post') return 'Final';
    if (!g.start) return '';
    var o = { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' };
    if (D.schedule === 'week') o.weekday = 'short';
    return new Date(g.start).toLocaleString('en-US', o).replace(',', '').replace(/ (AM|PM)$/, '');
  }
  // pills: the spread family picks a segment first; NHL / MLB list every market
  function tmPills(k) { return !periodFamily() && D.segments.length > 1 ? tmMarkets(k) : tmMarkets(); }
  function tmPick(st, pills) {
    var p = pills.filter(function(x) { return x.k === st.k && x.m === st.m; })[0] || pills.filter(function(x) { return x.k === st.k; })[0] || pills[0];
    st.k = p.k; st.m = p.m;
    return p;
  }
  function tmControls(st, pills, id) {
    var segRow = !periodFamily() && D.segments.length > 1 ? '<div class="seg-toggle" data-tm-segs>' + D.segments.map(function(s) {
      return '<button class="seg-btn" data-tm-seg="' + s.key + '" aria-pressed="' + (s.key === st.k) + '">' + esc(s.label) + '</button>'; }).join('') + '</div>' : '';
    return segRow + '<div class="seg-toggle" id="' + id + '">' + pills.map(function(p) {
      return '<button class="seg-btn" data-tm-pill="' + p.k + '|' + p.m + '" aria-pressed="' + (p.k === st.k && p.m === st.m) + '">' + esc(p.label) + '</button>'; }).join('') + '</div>';
  }
  function wireTmControls(root, st, draw) {
    root.querySelectorAll('[data-tm-seg]').forEach(function(b) { b.onclick = function() { st.k = b.getAttribute('data-tm-seg'); setSeg(st.k); draw(); }; });
    root.querySelectorAll('[data-tm-pill]').forEach(function(b) { b.onclick = function() { var x = b.getAttribute('data-tm-pill').split('|'); st.k = x[0]; st.m = x[1]; draw(); }; });
  }
  function tmMarketNote(m) {
    return { ml: tieSport() ? 'Win % counts ties as games played' : 'A tied segment is a push: in the record, not the %',
             ml3: '3-way: a tied segment loses a team bet; Tie % is how often the segment was tied' }[m] || (tmNoPush(m) ? 'This market can’t push' : 'Pushes count in the record but not the %');
  }

  // ----------------------------------------------------------- Teams list
  var tl = { k: null, m: null, side: 'all', q: '', sortKey: 'units', sortDir: -1, today: false, grp: '' };
  var TL_MIN = 5;   // fewer games than this in the market: listed below everyone else, muted
  // The "All teams" filter: college groups (Power 4 / Group of 5 /
  // Independents; Power conferences / Mid-majors) then each conference;
  // pro sports each conference, then each division. [{v, label, test}]
  var POWER4 = /^(Southeastern|Big Ten|Big 12|Atlantic Coast) Conference$/;
  var POWER_HOOPS = /^(Southeastern|Big Ten|Big 12|Atlantic Coast|Big East) Conference$/;
  function tlGroups() {
    function vals(f) { var o = {}; Object.keys(D.teams).forEach(function(s) { var v = D.teams[s][f]; if (v) o[v] = 1; }); return Object.keys(o).sort(); }
    function conf(s) { return D.teams[s].conference || ''; }
    var out = [{ v: '', label: 'All teams', test: function() { return true; } }];
    if (D.sport === 'ncaaf') {
      out.push({ v: 'p4', label: 'Power 4', test: function(s) { return POWER4.test(conf(s)); } },
               { v: 'g5', label: 'Group of 5', test: function(s) { return !POWER4.test(conf(s)) && !/Independent/.test(conf(s)); } },
               { v: 'ind', label: 'Independents', test: function(s) { return /Independent/.test(conf(s)); } });
    } else if (D.sport === 'ncaab') {
      out.push({ v: 'power', label: 'Power conferences', test: function(s) { return POWER_HOOPS.test(conf(s)); } },
               { v: 'mid', label: 'Mid-majors', test: function(s) { return !POWER_HOOPS.test(conf(s)); } });
    }
    vals('conference').filter(function(c) { return D.sport !== 'ncaaf' || !/Independent/.test(c); }).forEach(function(c) {
      var label = D.sport === 'ncaaf' || D.sport === 'ncaab' ? c.replace(/ Conference$/, '') : { East: 'Eastern Conference', West: 'Western Conference' }[c] || c;
      out.push({ v: 'c:' + c, label: label, test: function(s) { return conf(s) === c; } });
    });
    vals('division').forEach(function(d) {
      out.push({ v: 'd:' + d, label: d + (/\s/.test(d) ? '' : ' Division'), test: function(s) { return D.teams[s].division === d; } });
    });
    return out;
  }
  function renderTeamsIndex() {
    if (!D.season) return;   // keep the plain list
    var weekly = D.schedule === 'week';
    var byTeam = {};
    Object.keys(D.teams).forEach(function(s) { byTeam[s] = teamGames(s); });
    var playing = {};
    tmSlate().forEach(function(g) {
      if (g.state === 'postponed' || g.state === 'canceled') return;
      playing[g.away] = { g: g, opp: g.home, at: true };
      playing[g.home] = { g: g, opp: g.away, at: false };
    });
    var anyPlaying = Object.keys(playing).some(function(s) { return D.teams[s]; });
    var groups = tlGroups();
    if (!groups.some(function(x) { return x.v === tl.grp; })) tl.grp = '';
    if (!tl.k) tl.k = getSeg();
    function draw() {
      var pills = tmPills(tl.k), p = tmPick(tl, pills), k = p.k, m = p.m, hasTie = m === 'ml3';
      var grp = groups.filter(function(x) { return x.v === tl.grp; })[0];
      var list = Object.keys(D.teams).filter(function(s) {
        var t = D.teams[s];
        if (tl.today && !playing[s]) return false;
        if (!grp.test(s)) return false;
        return !tl.q || (t.name + ' ' + (t.code || '') + ' ' + (t.short || '')).toLowerCase().indexOf(tl.q) !== -1;
      }).map(function(s) {
        var a = tmAgg(s, k, m, tl.side, byTeam[s]);
        a.slug = s; a.name = D.teams[s].name; a.conf = D.teams[s].conference || 'Other';
        a.u = a.priced ? a.units : null; a.runV = a.run ? (a.run.r === 'W' ? a.run.n : a.run.r === 'L' ? -a.run.n : 0) : null;
        return a;
      });
      var key = { units: 'u', streak: 'runV', rec: 'w', tie: 'tiePct' }[tl.sortKey] || tl.sortKey, dir = tl.sortDir;
      // teams with too few games sit below the rest, and no games at the very bottom, whatever the sort
      // (when no team has TL_MIN games yet, early in a market, nobody is set apart)
      var few = list.some(function(a) { return a.gp >= TL_MIN; }) ? TL_MIN : 1;
      function tier(a) { return !a.gp ? 2 : a.gp < few ? 1 : 0; }
      list.sort(function(a, b) {
        if (tier(a) !== tier(b)) return tier(a) - tier(b);
        if (key === 'name') return a.name.localeCompare(b.name) * dir;
        var va = a[key], vb = b[key];
        if (va === vb || (va == null && vb == null)) return (b.w + b.l) - (a.w + a.l) || a.name.localeCompare(b.name);
        if (va == null) return 1;
        if (vb == null) return -1;
        return (va - vb) * dir;
      });
      function rowHtml(r) {
        var pl = playing[r.slug], w = r.pct == null ? 0 : Math.round(r.pct * 100), tt = pl ? tmShortTime(pl.g) : '';
        var tag = pl ? '<span class="tm-today' + (tt === 'LIVE' ? ' live' : '') + '">' + esc(tt) + '</span>' : '';
        return '<tr class="tl-row' + (r.gp < few ? ' tl-few' : '') + '" data-href="' + teamUrl(r.slug) + '">' +
          '<td class="team-cell">' + badge(r.slug, 24) + '<a class="tl-name" href="' + teamUrl(r.slug) + '"><span class="tl-full">' + esc(r.name) + '</span><span class="tl-short">' + esc(tcode(r.slug)) + '</span></a>' + tag + '</td>' +
          '<td class="num rec-cell mono col-rec"><b>' + tmRecTxt(r, m) + '</b></td>' +
          '<td class="num col-pct"><div class="pct-cell"><div class="pct-bar"><span style="width:' + w + '%"></span></div><span class="pct-num mono">' + tmPct(r.pct) + '</span></div></td>' +
          (hasTie ? '<td class="num col-tie mono">' + tmPct(r.tiePct) + '</td>' : '') +
          '<td class="num col-l8 mono">' + tmL10(r.seq, m) + '</td>' +
          '<td class="num col-streak mono">' + tmRunHtml(r.run, m) + '</td>' +
          '<td class="num col-units mono">' + tmUnits(r) + '</td></tr>';
      }
      var ncol = hasTie ? 7 : 6, body;
      if (!list.length) body = '<tr><td colspan="' + ncol + '"><div class="empty-state">' + (tl.q ? 'No teams match &ldquo;' + esc(tl.q) + '&rdquo;.' : tl.today ? 'No teams playing ' + (weekly ? 'this week' : 'today') + '.' : 'No teams in ' + esc(grp.label) + '.') + '</div></td></tr>';
      else body = list.map(rowHtml).join('');
      function th(key, label, cls) {
        var on = tl.sortKey === key;
        return '<th class="' + (cls || '') + '" data-sort="' + key + '">' + label + '<span class="arrow">' + (on ? (tl.sortDir < 0 ? '▼' : '▲') : '') + '</span></th>';
      }
      function sidePill(v, label) { return '<button class="seg-btn" data-tl-side="' + v + '" aria-pressed="' + (tl.side === v) + '">' + label + '</button>'; }
      app.innerHTML = '<div id="teamView"><div class="controls tm-controls">' + tmControls(tl, pills, 'tlPills') +
        '<div class="seg-toggle">' + sidePill('all', 'All') + sidePill('home', 'Home') + sidePill('away', 'Away') + '</div>' +
        (anyPlaying ? '<button class="seg-btn tm-today-btn" id="tlToday" aria-pressed="' + tl.today + '">' + (weekly ? 'This week' : 'Today') + '</button>' : '') +
        (groups.length > 1 ? '<select class="tm-filter" id="tlGroup" aria-label="Filter teams">' + groups.map(function(x) {
          return '<option value="' + esc(x.v) + '"' + (x.v === tl.grp ? ' selected' : '') + '>' + esc(x.label) + '</option>'; }).join('') + '</select>' : '') +
        '<input class="search-box" id="tlSearch" type="search" placeholder="Search team&hellip;" aria-label="Search teams" value="' + esc(tl.q) + '"></div>' +
        '<div class="table-wrap"><div class="table-scroll"><table id="leagueTable" class="tm-table"><thead><tr>' +
        th('name', 'Team') + th('rec', tmRecHead(m), 'num col-rec') + th('pct', TM_INFO[m].pct, 'num col-pct') + (hasTie ? th('tie', 'Tie %', 'num col-tie') : '') +
        '<th class="num col-l8">L10</th>' + th('streak', 'Streak', 'num col-streak') + th('units', 'Units', 'num col-units') +
        '</tr></thead><tbody>' + body + '</tbody></table></div></div>' +
        '<p class="tl-note">' + esc(seg(k).label) + ' &middot; ' + esc(D.seasonLabel || '') + ' season &middot; ' + tmMarketNote(m) +
        ' &middot; Units: 1 unit a game at the closing price, only where prices were saved &middot; Fewer than ' + TL_MIN + ' games: listed last, dimmed.</p></div>';
      wireTmControls(app, tl, draw);
      app.querySelectorAll('[data-tl-side]').forEach(function(b) { b.onclick = function() { tl.side = b.getAttribute('data-tl-side'); draw(); }; });
      var gs = document.getElementById('tlGroup');
      if (gs) gs.onchange = function() { tl.grp = gs.value; draw(); };
      var tb = document.getElementById('tlToday');
      if (tb) tb.onclick = function() { tl.today = !tl.today; draw(); };
      app.querySelectorAll('th[data-sort]').forEach(function(h) {
        h.onclick = function() {
          var key2 = h.getAttribute('data-sort');
          if (tl.sortKey === key2) tl.sortDir *= -1; else { tl.sortKey = key2; tl.sortDir = key2 === 'name' ? 1 : -1; }
          draw();
        };
      });
      app.querySelectorAll('tr[data-href]').forEach(function(tr) {
        tr.onclick = function(e) { if (!e.target.closest('a')) window.location.href = tr.getAttribute('data-href'); };
      });
      var q = document.getElementById('tlSearch');
      q.oninput = function() {
        tl.q = q.value.trim().toLowerCase(); var pos = q.selectionStart; draw();
        var q2 = document.getElementById('tlSearch'); q2.focus(); q2.setSelectionRange(pos, pos);
      };
    }
    draw();
  }

  // ------------------------------------------------------------ team page
  // Next game, last game, season markets, home / away splits, current
  // streaks, line history, results history, Situational Results, game log.
  function tmSection(title, body, id) { return '<section class="tm-sec"' + (id ? ' id="' + id + '"' : '') + '><h2 class="team-section-title">' + title + '</h2>' + body + '</section>'; }
  function scoreWord() { return D.sport === 'nhl' ? 'goals' : D.sport === 'mlb' ? 'runs' : 'points'; }
  function ucFirst(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
  function num1(x) { var r = Math.round(x * 10) / 10; return String(r); }
  function signedLine(x) { var r = Math.round(x * 10) / 10; return (r > 0 ? '+' : '') + r; }
  function priceTxt(p) { return typeof p === 'number' ? (p > 0 ? '+' : '') + Math.round(p) : '&mdash;'; }
  function shortDate(g) { return g.start ? new Date(g.start).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'America/New_York' }) : ''; }
  function vsTxt(g, slug) { return (g.home === slug ? 'vs ' : '@ ') + tcode(g.home === slug ? g.away : g.home); }
  // the team's lines for one segment of a game, or '' when none are posted
  function tmLines(g, k, slug) {
    var o = (g.odds || {})[k] || {}, side = g.home === slug ? 'home' : 'away', opp = side === 'home' ? 'away' : 'home', out = [];
    tmMarkets(k).forEach(function(p) {
      var m = p.m;
      if (m === 'ml' && o.ml && typeof o.ml[side] === 'number') out.push('Moneyline ' + priceTxt(o.ml[side]));
      if (m === 'ats' && o.ats && o.ats[side] && typeof o.ats[side].line === 'number') out.push(esc(p.label.replace(/^F5 /, '')) + ' ' + signedLine(o.ats[side].line) + (o.ats[side].price != null ? ' (' + priceTxt(o.ats[side].price) + ')' : ''));
      if (m === 'total' && o.total && typeof o.total.line === 'number') out.push(D.sport === 'nhl' ? 'Over 1.5 ' + priceTxt(o.total.over) : 'Total ' + num1(o.total.line));
      if (m === 'btts' && o.btts && o.btts.yes != null) out.push('BTTS Yes ' + priceTxt(o.btts.yes) + ' / No ' + priceTxt(o.btts.no));
      if (m === 'rfi' && o.nrfi_yrfi && o.nrfi_yrfi.nrfi != null) out.push('NRFI ' + priceTxt(o.nrfi_yrfi.nrfi) + ' / YRFI ' + priceTxt(o.nrfi_yrfi.yrfi));
      if (m === 'ml3' && o.ml3 && o.ml3[side] != null) out.push('3-way ' + esc(tcode(g[side])) + ' ' + priceTxt(o.ml3[side]) + ' &middot; Tie ' + priceTxt(o.ml3.draw) + ' &middot; ' + esc(tcode(g[opp])) + ' ' + priceTxt(o.ml3[opp]));
    });
    return out.join(' &middot; ');
  }
  // a market's result for the team, in words, with its icon
  function tmResultWord(g, k, m, slug) {
    var b = tmBet(g, k, m, slug);
    if (!b) return null;
    var o = (g.odds || {})[k] || {}, side = g.home === slug ? 'home' : 'away', w;
    if (m === 'ml' || m === 'ml3') w = (m === 'ml3' ? '3-way: ' : 'Moneyline: ') + (b.r === 'W' ? 'Won' : b.r === 'L' ? 'Lost' : m === 'ml' && !tieSport() ? 'Push' : 'Tied');
    else if (m === 'ats') { var ln = (o.ats || {})[side] || {}; w = (D.sportType === 'baseball' ? 'Run line' : 'Spread') + (typeof ln.line === 'number' ? ' ' + signedLine(ln.line) : '') + ': ' + (b.r === 'W' ? 'Covered' : b.r === 'L' ? 'Didn’t cover' : 'Push'); }
    else if (m === 'total') w = (D.sport === 'nhl' ? 'Over 1.5' : 'Total' + (o.total && typeof o.total.line === 'number' ? ' ' + num1(o.total.line) : '')) + ': ' + (b.r === 'W' ? 'Over' : b.r === 'L' ? 'Under' : 'Push');
    else if (m === 'btts') w = 'BTTS: ' + (b.r === 'W' ? 'Yes' : 'No');
    else w = (b.r === 'W' ? 'NRFI' : 'YRFI');
    var ic = b.r === 'W' ? ['✓', 'tr-w'] : b.r === 'L' ? ['✗', 'tr-l'] : ['–', 'tr-p'];
    return '<span class="tm-res">' + esc(w) + ' <span class="tr-st ' + ic[1] + '">' + ic[0] + '</span></span>';
  }
  function tmScore(g, k, slug) {
    var r = (g.res || {})[k];
    if (!r || !r.sc) return null;
    return g.home === slug ? r.sc[1] + '–' + r.sc[0] : r.sc[0] + '–' + r.sc[1];
  }
  function tmLogLink(g, text) { return '<a href="#g-' + esc(String(g.id)) + '" data-glog="' + esc(String(g.id)) + '">' + text + '</a>'; }

  // this team's lines from the Trends page's Matchup Trends (lean 60%+ over 10+ games, or a run of 3+)
  function tmMatchupLines(g, slug) {
    var before = gameDay(g) || todayET(), out = [];
    D.segments.forEach(function(s) {
      var seqs = teamSeqs(before, s.key), done = {};
      tmMarkets(s.key).forEach(function(p) {
        var m = p.m === 'ml3' ? 'ml' : p.m;
        if (done[m] || !HIT[m]) return;
        done[m] = 1;
        var seq = ((seqs[slug] || {})[m]) || [], ln = leanOf(m, seq), st = streakOf(seq);
        var kind = ln ? ln.kind : st && st.n >= 3 ? st.kind : null;
        if (!kind) return;
        var c = countOf(m, seq, kind);
        out.push('<div class="mt-line"><span><b>' + esc(tcode(slug)) + '</b> ' + esc(lineWords(m, kind, s.key)) + ' in ' + c.x + ' of ' + c.y + ' &middot; ' + pct0(c.y ? c.x / c.y : 0) +
          (st && st.n >= 3 && st.kind === kind ? ' &middot; ' + st.n + ' straight' : '') + '</span>' + dots(seq, kind) + '</div>');
      });
    });
    return out;
  }

  var tm = { k: null, m: null, logK: null, logAll: false };
  function renderTeam() {
    var slug = TEAM, games = teamGames(slug);
    if (!games.length) return;   // keep the server-rendered empty sections
    var finals = games.filter(function(g) { return g.state === 'final'; });
    var graded = finals.filter(function(g) { return g.res; });
    var next = games.filter(function(g) { return g.state === 'pre' || g.state === 'in'; })[0];
    var last = finals[finals.length - 1];
    var name = shortName(slug);
    if (!tm.k) tm.k = getSeg();
    if (!tm.logK) tm.logK = D.segments[0].key;

    function nextLabel(g) {
      var vs = (g.home === slug ? 'vs ' : '@ ') + tcode(g.home === slug ? g.away : g.home);
      if (D.schedule === 'week') return (D.weeks && g.wk === currentWeek(D.weeks) ? 'This week ' : 'Next game: ' + new Date(g.start).toLocaleDateString('en-US', { weekday: 'short', timeZone: 'America/New_York' }) + ' ') + vs;
      return gameDay(g) === todayET() ? 'Tonight ' + vs : 'Next game: ' + new Date(g.start).toLocaleDateString('en-US', { weekday: 'short', timeZone: 'America/New_York' }) + ' ' + vs;
    }
    function nextHtml() {
      if (!next) return tmSection('Next Game', emptyNote('No upcoming game scheduled.'));
      var g = next, home = g.home === slug, opp = home ? g.away : g.home, day = gameDay(g);
      var when = D.schedule === 'week' ? timeET(g.start) : dateLabel(day) + ' &middot; ' + esc(timeET(g.start));
      var h = '<div class="tm-card"><div class="tm-ng-head"><span class="tm-when">' + when + '</span>' +
        (g.state === 'in' ? '<span class="tr-st tr-live"><i></i>LIVE</span>' : '') +
        '<span class="tm-opp">' + (home ? 'vs' : '@') + ' ' + badge(opp, 24) + teamLink(opp, esc(team(opp).name)) + '</span></div>';
      h += D.segments.map(function(s) {
        var lines = tmLines(g, s.key, slug), live = g.state === 'in' ? tmScore(g, s.key, slug) : null;
        return '<div class="tm-seg-line"><b>' + esc(s.label) + '</b><span>' + (live ? '<span class="tm-live">' + esc(tcode(slug)) + ' ' + live + ' ' + esc(tcode(opp)) + '</span> &middot; ' : '') +
          (lines || '<span class="tm-muted">Lines not posted yet</span>') + '</span></div>';
      }).join('');
      var mt = tmMatchupLines(g, slug);
      var trUrl = ROOT + SPORT_SLUG + '/trends/' + (D.schedule === 'week' ? '?week=' + encodeURIComponent(g.wk || '') : '?date=' + day);
      h += '<div class="tm-mt"><div class="tm-mt-head"><b>Matchup trends</b><a href="' + trUrl + '">See all Trends &rarr;</a></div>' +
        (mt.length ? mt.join('') : '<p class="mt-none">No matchup trends for this game.</p>') + '</div></div>';
      return tmSection('Next Game', h);
    }
    function lastHtml() {
      if (!last) return tmSection('Last Game', emptyNote('No games played yet.'));
      var g = last, home = g.home === slug, opp = home ? g.away : g.home;
      var fin = g.as != null && g.hs != null ? (home ? g.hs + '–' + g.as : g.as + '–' + g.hs) : '';
      var h = '<div class="tm-card"><div class="tm-ng-head"><span class="tm-when">' + esc(shortDate(g)) + '</span><span class="tm-opp">' + (home ? 'vs' : '@') + ' ' + badge(opp, 24) + teamLink(opp, esc(team(opp).name)) + '</span>' +
        (fin ? '<span class="tm-final">Final <b class="mono">' + fin + '</b>' + (g.ot ? ' ' + esc(g.ot) : '') + '</span>' : '') + '</div>';
      h += D.segments.map(function(s) {
        var sc = tmScore(g, s.key, slug);
        var res = tmMarkets(s.key).map(function(p) { return tmResultWord(g, s.key, p.m, slug); }).filter(Boolean);
        return '<div class="tm-seg-line"><b>' + esc(s.label) + '</b><span>' + (sc ? '<b class="mono">' + sc + '</b>' : '<span class="tm-muted">No score</span>') +
          (res.length ? ' &middot; ' + res.join(' ') : '') + '</span></div>';
      }).join('');
      return tmSection('Last Game', h + '</div>');
    }
    // 4 + 5: season markets and home / away splits, following the pills
    function marketsHtml() {
      var pills = tmPills(tm.k), p = tmPick(tm, pills), k = p.k, m = p.m, a = tmAgg(slug, k, m, 'all', graded);
      var card = '<div class="tm-mk-card"><div><span class="tm-mk-label">' + esc(tmRecHead(m)) + '</span><b class="mono">' + tmRecTxt(a, m) + '</b></div>' +
        '<div><span class="tm-mk-label">' + esc(TM_INFO[m].pct) + '</span><b class="mono">' + tmPct(a.pct) + '</b></div>' +
        (m === 'ml3' ? '<div><span class="tm-mk-label">Tie %</span><b class="mono">' + tmPct(a.tiePct) + '</b></div>' : '') +
        '<div><span class="tm-mk-label">Units</span><b class="mono">' + tmUnits(a) + '</b></div></div>';
      var ms = tmMarkets(k);
      var split = '<div class="table-scroll"><table class="gamelog tm-split"><thead><tr><th></th><th class="num">GP</th>' + ms.map(function(x) {
        return '<th class="num' + (x.m === m ? ' sit-hl' : '') + '">' + esc(x.label) + ' <small>' + esc(tmRecHead(x.m)) + '</small></th>'; }).join('') + '</tr></thead><tbody>' +
        [['all', 'All'], ['home', 'Home'], ['away', 'Away']].map(function(sd) {
          var gp = graded.filter(function(g) { return ((g.res || {})[k] || {}).sc && (sd[0] === 'all' || (sd[0] === 'home') === (g.home === slug)); }).length;
          return '<tr><th>' + sd[1] + '</th><td class="num mono">' + gp + '</td>' + ms.map(function(x) {
            var b = tmAgg(slug, k, x.m, sd[0], graded);
            return '<td class="num mono' + (x.m === m ? ' sit-hl' : '') + '">' + tmRecTxt(b, x.m) + (b.gp ? ' <small>' + tmPct(b.pct) + '</small>' : '') + '</td>';
          }).join('') + '</tr>';
        }).join('') + '</tbody></table></div>';
      return tmSection('Season Markets', '<div class="controls tm-controls">' + tmControls(tm, pills, 'tmPills') + '</div>' + card + '<p class="tl-note">' + esc(seg(k).label) + ' &middot; ' + esc(D.seasonLabel || '') + ' season &middot; ' + tmMarketNote(m) + '</p>') +
        tmSection('Home / Away Splits', split);
    }
    function streakWord(m, kind, k) {
      var s = segWord(k), sw = ucFirst(segWords(k));
      if (m === 'ml') return (kind === 'W' ? 'Won' : 'Lost') + ' the ' + s;
      if (m === 'ats') return (kind === 'W' ? 'Covered' : 'Failed to cover') + ' the ' + s + ' spread';
      if (m === 'total') return sw + ' have gone ' + (kind === 'O' ? 'Over' : 'Under') + (D.sport === 'nhl' ? ' 1.5' : '');
      if (m === 'btts') return sw + ' have gone BTTS ' + (kind === 'Y' ? 'Yes' : 'No');
      return sw + ' have gone ' + (kind === 'Y' ? 'YRFI' : 'NRFI');
    }
    function streaksHtml() {
      var rows = [];
      D.segments.forEach(function(s) {
        var seqs = teamSeqs('9999-12-31', s.key), done = {};
        tmMarkets(s.key).forEach(function(p) {
          var m = p.m === 'ml3' ? 'ml' : p.m;
          if (done[m] || !HIT[m]) return;
          done[m] = 1;
          var st = streakOf(((seqs[slug] || {})[m]) || []);
          if (!st || st.n < 3) return;
          var yn = m === 'total' || m === 'btts' || m === 'rfi';
          var cls = (yn ? 'sk-n' : st.kind === 'W' ? 'sk-w' : 'sk-l') + (st.n >= 7 ? '3' : st.n >= 5 ? '2' : '1');
          rows.push({ n: st.n, html: '<div class="sk-row"><span class="sk-len ' + cls + '">' + st.n + '</span><span class="sk-text">' + esc(streakWord(m, st.kind, s.key)) + ' ' + st.n + ' straight</span></div>' });
        });
      });
      rows.sort(function(a, b) { return b.n - a.n; });
      return tmSection('Current Streaks', rows.length ? '<div class="sk-list">' + rows.map(function(r) { return r.html; }).join('') + '</div>' : emptyNote('No current streaks.'));
    }
    // 7: average lines (home / away), season highs and lows, lines vs results
    function lineDefs(k) {
      return tmMarkets(k).filter(function(p) { return p.m !== 'ml3' && !(p.m === 'ml' && !tieSport()); }).map(function(p) {
        var m = p.m, isLine = m === 'ats' || (m === 'total' && D.sport !== 'nhl');
        var name = m === 'ats' ? (D.sportType === 'baseball' ? 'run line' : 'spread') : m === 'total' ? (D.sport === 'nhl' ? 'Over 1.5 price' : 'total') :
          m === 'ml' ? 'moneyline' : m === 'btts' ? 'BTTS Yes price' : 'NRFI price';
        return { m: m, name: name, line: isLine, val: function(g) {
          var o = (g.odds || {})[k] || {}, side = g.home === slug ? 'home' : 'away';
          if (m === 'ats') return ((o.ats || {})[side] || {}).line;
          if (m === 'total') return D.sport === 'nhl' ? (o.total || {}).over : (o.total || {}).line;
          if (m === 'ml') return (o.ml || {})[side];
          if (m === 'btts') return (o.btts || {}).yes;
          return (o.nrfi_yrfi || {}).nrfi;
        } };
      });
    }
    function fmtVal(d, v) { return d.m === 'ats' ? signedLine(v) : d.line ? num1(v) : priceTxt(v); }
    function avg(xs) { return xs.reduce(function(a, b) { return a + b; }, 0) / xs.length; }
    // prices average through their implied probability (-150 and +130 don't average to -10)
    function avgPrice(xs) {
      var p = avg(xs.map(function(x) { return x < 0 ? -x / (-x + 100) : 100 / (x + 100); }));
      return p >= 0.5 ? -100 * p / (1 - p) : 100 * (1 - p) / p;
    }
    function linesHtml() {
      var parts = [];
      ['home', 'away'].forEach(function(sd) {
        var segs = D.segments.map(function(s) {
          var bits = lineDefs(s.key).map(function(d) {
            var xs = finals.filter(function(g) { return (g.home === slug) === (sd === 'home'); }).map(d.val).filter(function(v) { return typeof v === 'number'; });
            if (!xs.length) return null;
            return (d.m === 'ats' ? '' : d.name.replace(' price', '') + ' ') + fmtVal(d, d.line || d.m === 'ats' ? avg(xs) : avgPrice(xs));
          }).filter(Boolean);
          return bits.length ? esc(s.tag) + ' ' + bits.join(', ') : null;
        }).filter(Boolean);
        if (segs.length) parts.push('<p><b>' + (sd === 'home' ? 'At home' : 'On the road') + ':</b> ' + segs.join(' &middot; ') + '</p>');
      });
      var hl = [], vs = [];
      D.segments.forEach(function(s) {
        lineDefs(s.key).forEach(function(d) {
          var xs = finals.filter(function(g) { return typeof d.val(g) === 'number'; });
          if (xs.length < 2) return;
          var hi = xs.reduce(function(a, g) { return d.val(g) > d.val(a) ? g : a; }), lo = xs.reduce(function(a, g) { return d.val(g) < d.val(a) ? g : a; });
          [['Highest', hi], ['Lowest', lo]].forEach(function(x) {
            hl.push('<li>' + x[0] + ' ' + esc(s.tag) + ' ' + esc(d.name) + ': ' + tmLogLink(x[1], '<b class="mono">' + fmtVal(d, d.val(x[1])) + '</b> ' + esc(vsTxt(x[1], slug)) + ', ' + esc(shortDate(x[1]))) + '</li>');
          });
        });
        var tg = finals.filter(function(g) { var o = (g.odds || {})[s.key] || {}, r = (g.res || {})[s.key] || {}; return o.total && typeof o.total.line === 'number' && r.sc; });
        if (tg.length >= 2) {
          var al = avg(tg.map(function(g) { return g.odds[s.key].total.line; })), aa = avg(tg.map(function(g) { return g.res[s.key].sc[0] + g.res[s.key].sc[1]; })), df = aa - al;
          vs.push('<p><b>' + esc(s.label) + ':</b> average total ' + num1(al) + ', average actual ' + num1(aa) + ' ' + scoreWord() + '. Their games ' +
            (Math.abs(df) < 0.05 ? 'landed right on the ' + esc(segWord(s.key)) + ' total on average.' : (df > 0 ? 'beat' : 'fell short of') + ' the ' + esc(segWord(s.key)) + ' total by ' + num1(Math.abs(df)) + ' on average.') + '</p>');
        }
      });
      if (!parts.length && !hl.length) return tmSection('Line History', emptyNote('No closing lines saved for this team yet.'));
      return tmSection('Line History', '<div class="tm-card">' + (parts.length ? '<h3 class="tm-sub">Average lines</h3>' + parts.join('') : '') +
        (hl.length ? '<h3 class="tm-sub">Season highs and lows</h3><ul class="tm-list">' + hl.join('') + '</ul>' : '') +
        (vs.length ? '<h3 class="tm-sub">Lines vs results</h3>' + vs.join('') : '') + '</div>');
    }
    // 8: streaks, best and worst, margins, scoring, per segment
    function resultsHtml() {
      var cards = D.segments.map(function(s) {
        var k = s.key, gs = finals.filter(function(g) { return ((g.res || {})[k] || {}).sc; });
        if (!gs.length) return '';
        var rows = gs.map(function(g) {
          var sc = g.res[k].sc, mine = g.home === slug ? sc[1] : sc[0], theirs = g.home === slug ? sc[0] : sc[1];
          return { g: g, mine: mine, theirs: theirs, mg: mine - theirs, r: mine > theirs ? 'W' : mine < theirs ? 'L' : 'T' };
        });
        function longest(r) {
          var best = null, cur = null;
          rows.forEach(function(x) {
            if (x.r === r) { cur = cur ? { n: cur.n + 1, a: cur.a, b: x.g } : { n: 1, a: x.g, b: x.g }; if (!best || cur.n > best.n) best = cur; }
            else cur = null;
          });
          return best ? best.n + ' (' + esc(shortDate(best.a)) + (best.n > 1 ? ' – ' + esc(shortDate(best.b)) : '') + ')' : 'None';
        }
        var wins = rows.filter(function(x) { return x.r === 'W'; }), losses = rows.filter(function(x) { return x.r === 'L'; });
        var bw = wins.length ? wins.reduce(function(a, x) { return x.mg > a.mg ? x : a; }) : null;
        var wl = losses.length ? losses.reduce(function(a, x) { return x.mg < a.mg ? x : a; }) : null;
        function gameTxt(x) { return tmLogLink(x.g, '<b class="mono">' + x.mine + '–' + x.theirs + '</b> ' + esc(vsTxt(x.g, slug)) + ', ' + esc(shortDate(x.g))); }
        var aw = wins.length ? avg(wins.map(function(x) { return x.mg; })) : null, al = losses.length ? avg(losses.map(function(x) { return -x.mg; })) : null;
        var plain = '';
        if (aw != null && al != null && Math.max(aw, al) >= 1.3 * Math.min(aw, al) && Math.max(aw, al) - Math.min(aw, al) >= 0.5) {
          plain = al > aw
            ? 'When the ' + esc(name) + ' lose the ' + esc(segWord(k)) + ', they lose it big: by ' + num1(al) + ' on average, vs +' + num1(aw) + ' in wins.'
            : 'When the ' + esc(name) + ' win the ' + esc(segWord(k)) + ', they win it big: by ' + num1(aw) + ' on average, vs −' + num1(al) + ' in losses.';
        }
        var most = rows.reduce(function(a, x) { return x.mine > a.mine ? x : a; }), fewest = rows.reduce(function(a, x) { return x.mine < a.mine ? x : a; });
        var w = scoreWord();
        return '<div class="tm-card"><h3 class="tm-sub">' + esc(s.label) + ' <small>' + rows.length + ' games</small></h3><ul class="tm-list">' +
          '<li>Longest win streak: ' + longest('W') + '</li><li>Longest losing streak: ' + longest('L') + '</li>' +
          (bw ? '<li>Best win: ' + gameTxt(bw) + '</li>' : '') + (wl ? '<li>Worst loss: ' + gameTxt(wl) + '</li>' : '') +
          '<li>Average margin: ' + (aw != null ? '+' + num1(aw) + ' in wins' : 'no wins') + ', ' + (al != null ? '−' + num1(al) + ' in losses' : 'no losses') + '</li>' +
          (plain ? '<li class="tm-plain">' + plain + '</li>' : '') +
          '<li>Most ' + w + ' scored: ' + gameTxt(most) + '</li><li>Fewest ' + w + ' scored: ' + gameTxt(fewest) + '</li>' +
          '<li>Average: ' + num1(avg(rows.map(function(x) { return x.mine; }))) + ' for, ' + num1(avg(rows.map(function(x) { return x.theirs; }))) + ' against</li></ul></div>';
      }).join('');
      return tmSection('Results History', cards || emptyNote('No games played yet.'));
    }
    function sitHtml() {
      if (!splitReg()) return tmSection('Situational Results', emptyNote('Situational Results aren’t set up for ' + esc(D.label) + ' yet.'));
      return '<div id="teamSit" class="team-sit tm-sec"></div>';
    }
    // 10: every game this season, newest first: the last 10, then Show all
    function logHtml() {
      var k = seg(tm.logK) ? tm.logK : D.segments[0].key, ms = tmMarkets(k).filter(function(p) { return p.m !== 'ml3'; });
      var eng = sitEngine(), ctx = {};
      if (eng) eng.contexts(k).forEach(function(e) { if (e.c.team === slug) ctx[e.c.g.id] = e.c; });
      var list = finals.slice().reverse(), shown = tm.logAll ? list : list.slice(0, 10);
      function tags(g) {
        var home = g.home === slug, out = [home ? 'Home' : 'Away'];
        if (eng && ctx[g.id]) out = out.concat(eng.tags(ctx[g.id]));
        else {
          var f = favSide((g.odds || {})[k]);
          if (f) out.push(f === (home ? 'home' : 'away') ? 'Fav' : 'Dog');
          var t = D.teams[slug] || {}, o = D.teams[home ? g.away : g.home] || {};
          if (t.division && t.division === o.division) out.push('Div');
        }
        return out.map(function(x) { return '<span class="sit-tag">' + esc(x) + '</span>'; }).join('');
      }
      function pill(g, m) {
        var b = tmBet(g, k, m, slug);
        return b ? '<span class="result-pill ' + (b.r === 'W' ? 'W' : b.r === 'L' ? 'L' : 'T') + '">' + tmLetter(b.r, m) + '</span>' : '<span class="result-pill T">&ndash;</span>';
      }
      var rows = shown.map(function(g) {
        var home = g.home === slug, opp = home ? g.away : g.home;
        var oppHtml = (home ? 'vs ' : '@ ') + (teamUrl(opp) ? '<a href="' + teamUrl(opp) + '">' + esc(shortName(opp)) + '</a>' : esc(shortName(opp)));
        var fin = g.as != null && g.hs != null ? (home ? g.hs + '–' + g.as : g.as + '–' + g.hs) + (g.ot ? ' ' + esc(g.ot) : '') : '&mdash;';
        var per = D.segments.map(function(s) { return '<td class="num mono' + (s.key === k ? ' sit-hl' : '') + '">' + (tmScore(g, s.key, slug) || '&mdash;') + '</td>'; }).join('');
        var res = ms.map(function(p) { return '<td class="num">' + pill(g, p.m) + '</td>'; }).join('');
        return { desk: '<tr id="g-' + esc(String(g.id)) + '"><td>' + esc(shortDate(g)) + '</td><td>' + oppHtml + '</td><td class="sit-tags">' + tags(g) + '</td>' + per + res + '<td class="num mono">' + fin + '</td></tr>',
          mob: '<div class="sit-gcard" id="gm-' + esc(String(g.id)) + '"><div class="sit-gl1"><span>' + esc(shortDate(g)) + '</span><span>' + oppHtml + '</span><span class="mono">' + (tmScore(g, k, slug) || '') + ' &middot; ' + fin + '</span></div>' +
            '<div class="sit-gl2"><span class="sit-tags">' + tags(g) + '</span><span class="sit-gb">' + ms.map(function(p) { return pill(g, p.m); }).join('') + '</span></div></div>' };
      });
      var more = list.length > 10 ? '<button class="seg-btn sit-more" id="tmLogMore" type="button">' + (tm.logAll ? 'Show the last 10 games' : 'Show all ' + list.length + ' games') + '</button>' : '';
      var segBtns = D.segments.length > 1 ? '<div class="seg-toggle" id="tmLogSeg">' + D.segments.map(function(s) {
        return '<button class="seg-btn" data-log-seg="' + s.key + '" aria-pressed="' + (s.key === k) + '">' + esc(s.label) + '</button>'; }).join('') + '</div>' : '';
      return tmSection('Game Log', segBtns + (list.length ? '<div class="sit-desk"><div class="gamelog-scroll"><table class="gamelog sit-log"><thead><tr><th>Date</th><th>Opp</th><th>Situations</th>' +
        D.segments.map(function(s) { return '<th class="num' + (s.key === k ? ' sit-hl' : '') + '">' + esc(s.tag) + '</th>'; }).join('') +
        ms.map(function(p) { return '<th class="num">' + esc(p.label.replace(/^F5 /, '')) + '</th>'; }).join('') + '<th class="num">Final</th></tr></thead><tbody>' +
        rows.map(function(x) { return x.desk; }).join('') + '</tbody></table></div></div><div class="sit-mob">' + rows.map(function(x) { return x.mob; }).join('') + '</div>' + more
        : emptyNote('No games played yet.')), 'tmLog');
    }
    function drawMarkets() {
      var box = document.getElementById('tmMarkets');
      box.innerHTML = marketsHtml();
      wireTmControls(box, tm, drawMarkets);
    }
    function drawLog() {
      var box = document.getElementById('tmLogBox');
      box.innerHTML = logHtml();
      var mb = document.getElementById('tmLogMore');
      if (mb) mb.onclick = function() { tm.logAll = !tm.logAll; drawLog(); };
      box.querySelectorAll('[data-log-seg]').forEach(function(b) { b.onclick = function() { tm.logK = b.getAttribute('data-log-seg'); drawLog(); }; });
    }
    app.innerHTML = nextHtml() + lastHtml() + '<div id="tmMarkets"></div>' + streaksHtml() + linesHtml() + resultsHtml() + sitHtml() + '<div id="tmLogBox"></div>';
    drawMarkets();
    drawLog();
    if (splitReg()) renderSit('teamSit', { mode: 'team', slug: slug, next: next ? { id: next.id, label: nextLabel(next) } : null });
    // a high / low / best / worst link opens the full log and scrolls to the game
    app.addEventListener('click', function(e) {
      var a = e.target.closest ? e.target.closest('[data-glog]') : null;
      if (!a) return;
      e.preventDefault();
      var id = a.getAttribute('data-glog');
      if (!document.getElementById('g-' + id)) { tm.logAll = true; drawLog(); }
      var row = document.getElementById('g-' + id), card = document.getElementById('gm-' + id);
      var el = card && card.offsetParent ? card : row;
      if (!el) return;
      el.classList.add('tm-flash');
      el.scrollIntoView({ block: 'center', behavior: 'smooth' });
      setTimeout(function() { el.classList.remove('tm-flash'); }, 2000);
    });
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
  // Season / This week / Last week (Overview and Splits). Daily sports' weeks
  // run Monday-Sunday, like NHL's; weekly sports (NFL, NCAAF) use the
  // league's own weeks, plus a Week dropdown for any week so far.
  var tf = { mode: 'all', wk: '' };
  function addDaysStr(d, n) { return new Date(new Date(d + 'T12:00:00Z').getTime() + n * 864e5).toISOString().slice(0, 10); }
  function mondayOf(d) { var day = new Date(d + 'T12:00:00Z').getUTCDay(); return addDaysStr(d, -((day + 6) % 7)); }
  function weeklySport() { return D.schedule === 'week' && (D.weeks || []).length; }
  function startedWeeks() {
    var t = todayET();
    var w = (D.weeks || []).filter(function(x) { return x.start <= t; });
    return w.length ? w : (D.weeks || []).slice(0, 1);
  }
  // the selected range: null (the season), {from, to, label}, or {none: true}
  function tfDates() {
    if (tf.mode === 'all') return null;
    if (weeklySport()) {
      var ws = startedWeeks(), w = null;
      if (tf.mode === 'week') w = ws[ws.length - 1];
      else if (tf.mode === 'lastweek') w = ws[ws.length - 2];
      else if (tf.mode === 'wk') w = (D.weeks || []).filter(function(x) { return x.key === tf.wk; })[0];
      return w ? { from: w.start, to: w.end, wk: w.key, label: esc(w.label) + ' (' + shortDay(w.start) + ' &ndash; ' + shortDay(w.end) + ')' } : { none: true };
    }
    var mon = addDaysStr(mondayOf(todayET()), tf.mode === 'week' ? 0 : -7), sun = addDaysStr(mon, 6);
    return { from: mon, to: sun, label: '(' + shortDay(mon) + ' &ndash; ' + shortDay(sun) + ')' };
  }
  // {games, line}: the graded games in the selected range, and the range
  function tfRange() {
    var r = tfDates();
    if (!r) return { games: finalGames(), line: '' };
    if (r.none) return { games: [], line: '<div class="sc-week">No week to show yet</div>' };
    var games = r.wk ? finalGames().filter(function(g) { return g.wk === r.wk; }) : finalGames(r.from, r.to);
    return { games: games, line: '<div class="sc-week">' + r.label + '</div>' };
  }
  function tfControls() {
    function btn(mode, label) { return '<button class="seg-btn" data-tf="' + mode + '" aria-pressed="' + (tf.mode === mode) + '">' + label + '</button>'; }
    var weekly = weeklySport();
    return '<div class="seg-toggle" role="group" aria-label="Time range">' + btn('all', 'Season') + btn('week', 'This week') + btn('lastweek', 'Last week') + '</div>' +
      (weekly ? '<select class="conf-select tf-week" id="tfWeek" aria-label="Pick a week"><option value="">Week&hellip;</option>' +
        startedWeeks().map(function(w) { return '<option value="' + esc(w.key) + '"' + (tf.mode === 'wk' && tf.wk === w.key ? ' selected' : '') + '>' + esc(w.label) + '</option>'; }).join('') +
        '</select>' : '');
  }
  // before(): return false to keep the old range (Splits: a premium-locked filter combination)
  function wireTf(draw, before) {
    function set(mode, wk) { var was = { mode: tf.mode, wk: tf.wk }; tf.mode = mode; tf.wk = wk; if (before && before() === false) { tf.mode = was.mode; tf.wk = was.wk; } draw(); }
    app.querySelectorAll('[data-tf]').forEach(function(b) { b.onclick = function() { set(b.getAttribute('data-tf'), ''); }; });
    var sel = document.getElementById('tfWeek');
    if (sel) sel.onchange = function() { if (sel.value) set('wk', sel.value); else set('all', ''); };
  }

  // ---- Scoring (Stats Overview; NHL has Goal Stats instead) ----
  // Three cards on the time filter's graded games with a score for the
  // segment the page toggle picks: the averages (and how often the segment
  // ends tied; MLB adds the NRFI rate), Most Common Scores (exact score,
  // higher first) and Scoring Distribution (combined score in buckets,
  // sortable by count or range; ?sort=common|range keeps the view linkable).
  var FB_BUCKETS = {
    '1q': [[0, 0], [1, 3], [4, 7], [8, 10], [11, 14], [15, 17], [18, 21], [22, null]],
    '1h': [[0, 0], [1, 3], [4, 7], [8, 10], [11, 14], [15, 17], [18, 21], [22, 24], [25, 28], [29, 31], [32, 35], [36, null]],
  };
  var MLB_BUCKETS = {
    '1i': [[0, 0], [1, 1], [2, 2], [3, null]],
    'f5': [[0, 0], [1, 1], [2, 2], [3, 3], [4, 4], [5, 5], [6, 6], [7, 7], [8, 9], [10, null]],
  };
  var fbState = null;
  function isFootball() { return D.sport === 'nfl' || D.sport === 'ncaaf'; }
  function fbInit() {
    if (fbState) return;
    var q = {};
    try { new URLSearchParams(window.location.search).forEach(function(v, key) { q[key] = v; }); } catch (e) {}
    fbState = { sort: q.sort === 'range' ? 'range' : 'common', open: false };
  }
  function fbSaveUrl() {
    try {
      var u = new URL(window.location.href);
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
  // the distribution's buckets: football and baseball fixed, basketball
  // from the sample (5-point steps for a quarter, 10 for a half; the
  // thinnest 3% at each end pooled into "or fewer" / "+" buckets)
  function scoreBuckets(k, totals) {
    if (isFootball()) return FB_BUCKETS[k] || FB_BUCKETS['1q'];
    if (D.sportType === 'baseball') return MLB_BUCKETS[k] || MLB_BUCKETS.f5;
    if (!totals.length) return [];
    var step = k === '1q' ? 5 : 10, srt = totals.slice().sort(function(a, b) { return a - b; });
    var lo = Math.floor(srt[Math.floor(srt.length * 0.03)] / step) * step, hi = Math.floor(srt[Math.ceil(srt.length * 0.97) - 1] / step) * step;
    var out = [[null, lo - 1]];
    for (var x = lo; x <= hi; x += step) out.push([x, x + step - 1]);
    out.push([hi + step, null]);
    return out.filter(function(b) { return totals.some(function(t) { return (b[0] == null || t >= b[0]) && (b[1] == null || t <= b[1]); }); });
  }
  function bucketLabel(b) { return b[0] == null ? '≤' + b[1] : b[1] == null ? b[0] + '+' : b[0] === b[1] ? String(b[0]) : b[0] + '–' + b[1]; }
  function scoringHtml(games, k) {
    var sample = [], missing = 0, rfiN = 0, rfiY = 0;
    games.forEach(function(g) {
      var r = (g.res || {})[k];
      if (r && r.sc && !r.na) { sample.push(r.sc); if (r.rfi === 'Y' || r.rfi === 'N') { rfiN++; if (r.rfi === 'N') rfiY++; } }
      else if (g.state === 'final') missing++;
    });
    var n = sample.length, s = seg(k), unit = scoreUnit();
    var totals = sample.map(function(sc) { return sc[0] + sc[1]; });
    var tied = sample.filter(function(sc) { return sc[0] === sc[1]; }).length;
    var avg = n ? totals.reduce(function(a, b) { return a + b; }, 0) / n : null;
    // card 1: averages
    var segName = isRfi(k) ? '1st-inning' : s.tag;
    var stats = [['Avg ' + segName + ' ' + unit, avg == null ? '&mdash;' : avg.toFixed(D.sportType === 'baseball' ? 2 : 1)],
                 ['Avg per team', avg == null ? '&mdash;' : (avg / 2).toFixed(D.sportType === 'baseball' ? 2 : 1)]];
    if (isRfi(k)) stats.push(['NRFI rate', rfiN ? fbPct(rfiY, rfiN) : '&mdash;']);
    var card0 = stats.map(function(x) { return '<div class="st-row st-stat"><span class="st-lbl">' + x[0] + '</span><span class="st-num mono">' + x[1] + '</span></div>'; }).join('') +
      (n && !isRfi(k) ? '<p class="st-line">' + fbPct(tied, n) + ' of ' + esc(segWords(k)) + ' end tied.</p>' : '');
    // card 2: exact scores, order-agnostic
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
    // card 3: combined score in buckets
    var rows = scoreBuckets(k, totals).map(function(b, i) {
      var c = totals.filter(function(t) { return (b[0] == null || t >= b[0]) && (b[1] == null || t <= b[1]); }).length;
      return { i: i, label: bucketLabel(b), n: c };
    });
    if (fbState.sort === 'common') rows.sort(function(a, b) { return b.n - a.n || a.i - b.i; });
    var max2 = Math.max.apply(null, rows.map(function(r) { return r.n; }).concat([0]));
    var card2 = rows.map(function(r) { return fbRow(r.label, r.n, n, max2, r.label); }).join('');
    var sub = n + ' game' + (n === 1 ? '' : 's') + (missing ? ' &middot; ' + missing + ' missing ' + esc(segWord(k)) + ' scores' : '');
    function sortLink(v, label) {
      return '<button type="button" class="fb-sort' + (fbState.sort === v ? ' on' : '') + '" data-fb-sort="' + v + '" aria-pressed="' + (fbState.sort === v) + '">' + label + '</button>';
    }
    var none = emptyNote('No games with ' + esc(s.label) + ' scores in this range.');
    return '<div class="st-grid">' +
      stCard(s.tag === 'NRFI' ? '1st Inning' : s.tag + ' Scoring', sub, n ? card0 : none) +
      stCard('Most Common Scores', sub, '<div class="hdist">' + (n ? card1 : none) + '</div>') +
      stCard('Scoring Distribution', sub, '<div class="fb-sorts">Sort: ' + sortLink('common', 'Common') + ' <span aria-hidden="true">|</span> ' + sortLink('range', 'Range') + '</div>' +
        '<div class="hdist" id="fbDist">' + (n ? card2 : none) + '</div>') +
      '</div>';
  }
  function renderScoring(games, k) {
    var box = document.getElementById('statsScoringBody');
    if (!box) return;
    fbInit();
    // FLIP: remember where each bucket row was, re-render, then slide rows
    // from their old spots to the new ones (~200ms), unless reduced motion
    var before = {};
    box.querySelectorAll('#fbDist [data-fb-key]').forEach(function(el) { before[el.getAttribute('data-fb-key')] = el.getBoundingClientRect().top; });
    box.innerHTML = scoringHtml(games, k);
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
    box.querySelectorAll('[data-fb-sort]').forEach(function(b) {
      b.onclick = function() { fbState.sort = b.getAttribute('data-fb-sort'); fbSaveUrl(); renderScoring(games, k); };
    });
    var more = document.getElementById('fbMore');
    if (more) more.onclick = function() { fbState.open = !fbState.open; renderScoring(games, k); };
  }

  // ------------------------------------------------------------ Stats pages
  // Three pages for every sport (Chris's spec, the sport-families rule in
  // CLAUDE.md): Overview (/stats/: Season Results, Scoring, Money Board and
  // a teaser for each other page), Splits (/stats/splits/: Situational
  // Results) and Edges (/stats/edges/: what happens after the opening
  // segment, Best Closers and Biggest Faders). Everything is counted here
  // from the graded games: res[k] (from the away side) and u[market] units
  // on each game, the same as the Teams pages.
  //
  // PREMIUM: one flag per section. Off = everyone sees it all. On = free
  // visitors (IS_PREMIUM false, or ?free=1) see each card's first 2 rows
  // and the rest blurred behind "Unlock with Premium". splitCombine: more
  // than one Splits filter at once; edgesPage: the whole Edges page.
  var PREMIUM = { board: false, edge1q: false, edge1h: false, edge1p: false, edgef5: false, tonightOnly: false, splitCombine: false, edgesPage: false };
  function periodFamily() { return D.sport === 'nhl' || D.sport === 'mlb'; }
  function spreadWord() { return 'Spread'; }
  function totalWord(k) { return D.sport === 'nhl' && k === '1p' ? 'O/U 1.5' : 'O/U'; }
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
  function statsUrl(page) { return ROOT + SPORT_SLUG + '/stats/' + (page ? page + '/' : ''); }
  // the one card style (Part 4): caps title, at most one muted subtitle,
  // chips in a fixed row under the header, rows on the shared grid
  function stCard(title, sub, body, chips, cls) {
    return '<div class="st-card' + (cls ? ' ' + cls : '') + '"><div class="st-head"><h4>' + title + '</h4>' + (sub ? '<div class="st-sub">' + sub + '</div>' : '') + '</div>' +
      (chips ? '<div class="st-chips">' + chips + '</div>' : '') + body + '</div>';
  }
  function stSection(id, title, controls, body) {
    return '<section class="st-sec" id="' + id + '"><div class="st-sec-head"><h2>' + title + '</h2>' + (controls ? '<div class="st-ctl">' + controls + '</div>' : '') + '</div>' + body + '</section>';
  }
  function stUnits(r) { return r.pr ? '<span class="st-u ' + unitCls(r.u) + '">' + fmtUnits(r.u) + '</span>' : '<span class="st-u st-none">&mdash;</span>'; }
  function stPct(w, l) { return w + l ? Math.round(100 * w / (w + l)) + '%' : '&mdash;'; }
  // one row: label | record | % | units, the columns lined up across cards
  function stRow(label, recTxt, pctTxt, unitsTxt, cls) {
    return '<div class="st-row' + (cls ? ' ' + cls : '') + '"><span class="st-lbl">' + label + '</span><span class="st-rec mono">' + recTxt + '</span>' +
      '<span class="st-pct mono">' + pctTxt + '</span>' + (unitsTxt == null ? '<span class="st-u"></span>' : unitsTxt) + '</div>';
  }
  function stHead(a, b, c) { return '<div class="st-row st-colhead"><span class="st-lbl"></span><span class="st-rec">' + a + '</span><span class="st-pct">' + b + '</span><span class="st-u">' + c + '</span></div>'; }

  // ---- Season Results ----
  // card = {id, title, gp, rows [{id, label, r {w, l, t, u, pr}, fmt 'T'|'P'|''}], tie (ML: tied games), stat}
  function sRec() { return { w: 0, l: 0, t: 0, u: 0, pr: 0 }; }
  function sAdd(r, res, u) {
    if (res === 'W') r.w++; else if (res === 'L') r.l++; else r.t++;
    if (u != null) { r.u += u; r.pr++; }
  }
  function newCard(id, title, rows, fmt) {
    var c = { id: id, title: title, gp: 0, rows: [], by: {} };
    rows.forEach(function(x) { var row = { id: x[0], label: x[1], r: sRec(), fmt: fmt }; c.rows.push(row); c.by[x[0]] = row; });
    return c;
  }
  function seasonCards(games, k) {
    var list = graded(games, k), t = seg(k).tag, nhl = D.sport === 'nhl';
    var pre = isRfi(k) ? '' : t + ' ';
    if (isRfi(k)) {
      var rf = newCard('rfi', 'NRFI/YRFI', [['YRFI', 'YRFI'], ['NRFI', 'NRFI']], '');
      list.forEach(function(g) {
        var r = g.res[k], u = (r.u || {}).rfi;
        if (r.rfi !== 'Y' && r.rfi !== 'N') return;
        rf.gp++;
        sAdd(rf.by.YRFI.r, r.rfi === 'Y' ? 'W' : 'L', u ? u[0] : null);
        sAdd(rf.by.NRFI.r, r.rfi === 'N' ? 'W' : 'L', u ? u[1] : null);
      });
      return [rf];
    }
    var ml = newCard('ml', pre + 'Moneyline', [['home', 'Home'], ['away', 'Away']], 'T');
    var mlfd = newCard('mlfd', pre + 'Moneyline', [['fav', 'Favorite'], ['dog', 'Underdog']], 'T');
    var sp = newCard('ats', pre + 'Spread', [['home', 'Home'], ['away', 'Away']], 'P');
    var tot = newCard('tot', pre + totalWord(k), [['over', 'Over'], ['under', 'Under']], nhl ? '' : 'P');
    var bt = newCard('btts', pre + 'BTTS', [['yes', 'Yes'], ['no', 'No']], '');
    var m3 = newCard('ml3', pre + '3-way ML', [['home', 'Home'], ['away', 'Away'], ['tie', 'Tie']], '');
    var fd = newCard('fd', pre + 'Favorites/Underdogs', [['mlfav', 'ML Fav'], ['mldog', 'ML Dog'], ['spfav', 'Spread Fav'], ['spdog', 'Spread Dog']], '');
    fd.rows[0].fmt = fd.rows[1].fmt = 'T'; fd.rows[2].fmt = fd.rows[3].fmt = 'P';
    var ha = newCard('ha', pre + 'Home/Away', [['hfav', 'Home Fav'], ['hdog', 'Home Dog'], ['rfav', 'Road Fav'], ['rdog', 'Road Dog']], 'P');
    ml.tie = 0; mlfd.tie = 0;
    var fdSeen = {};
    list.forEach(function(g) {
      var r = g.res[k], u = r.u || {}, o = (g.odds || {})[k] || {};
      if (hasMl(k) && r.su && r.su !== 'NA') {
        var aRes = r.su === 'P' ? 'T' : r.su, hRes = flipRes(aRes), us = u.su;
        ml.gp++; if (aRes === 'T') ml.tie++;
        sAdd(ml.by.home.r, hRes, us ? us[1] : null); sAdd(ml.by.away.r, aRes, us ? us[0] : null);
        var f = segFavSide(g, k);
        if (f) {
          var fi = f === 'away' ? 0 : 1, fRes = f === 'away' ? aRes : hRes;
          mlfd.gp++; if (aRes === 'T') mlfd.tie++;
          sAdd(mlfd.by.fav.r, fRes, us ? us[fi] : null); sAdd(mlfd.by.dog.r, flipRes(fRes), us ? us[1 - fi] : null);
          sAdd(fd.by.mlfav.r, fRes, us ? us[fi] : null); sAdd(fd.by.mldog.r, flipRes(fRes), us ? us[1 - fi] : null);
          fdSeen[g.id] = 1;
        }
        if (u.ml3) {
          m3.gp++;
          sAdd(m3.by.home.r, hRes === 'W' ? 'W' : 'L', u.ml3[1]); sAdd(m3.by.away.r, aRes === 'W' ? 'W' : 'L', u.ml3[0]);
          sAdd(m3.by.tie.r, aRes === 'T' ? 'W' : 'L', u.ml3[2]);
        }
      }
      if (r.ats && r.ats !== 'NA') {
        var aA = r.ats === 'T' ? 'P' : r.ats, hA = flipRes(aA), ua = u.ats;
        sp.gp++; sAdd(sp.by.home.r, hA, ua ? ua[1] : null); sAdd(sp.by.away.r, aA, ua ? ua[0] : null);
        var line = ((o.ats || {}).away || {}).line;
        if (typeof line === 'number' && line !== 0) {
          var sf = line < 0 ? 'away' : 'home', si = sf === 'away' ? 0 : 1, fA = sf === 'away' ? aA : hA;
          fdSeen[g.id] = 1;
          sAdd(fd.by.spfav.r, fA, ua ? ua[si] : null); sAdd(fd.by.spdog.r, flipRes(fA), ua ? ua[1 - si] : null);
          ha.gp++;
          sAdd(ha.by[sf === 'home' ? 'hfav' : 'hdog'].r, hA, ua ? ua[1] : null);
          sAdd(ha.by[sf === 'away' ? 'rfav' : 'rdog'].r, aA, ua ? ua[0] : null);
        }
      }
      if (r.tot && r.tot !== 'NA') {
        tot.gp++;
        var oRes = r.tot === 'O' ? 'W' : r.tot === 'U' ? 'L' : 'P';
        sAdd(tot.by.over.r, oRes, u.tot ? u.tot[0] : null); sAdd(tot.by.under.r, flipRes(oRes), u.tot ? u.tot[1] : null);
      }
      if (r.btts === 'Y' || r.btts === 'N') {
        bt.gp++;
        sAdd(bt.by.yes.r, r.btts === 'Y' ? 'W' : 'L', u.btts ? u.btts[0] : null); sAdd(bt.by.no.r, r.btts === 'N' ? 'W' : 'L', u.btts ? u.btts[1] : null);
      }
    });
    fd.gp = Object.keys(fdSeen).length;
    // NHL: Moneyline, O/U 1.5, BTTS, 3-way ML, Scoring, then Moneyline by
    // favorite. Spread family (and MLB's F5): Moneyline, Spread, O/U,
    // Favorites/Underdogs, Home/Away.
    var cards = nhl ? [ml, tot, bt, m3, scoringCard(list, k), mlfd] : [ml, sp, tot, fd, ha];
    return cards.filter(function(c) { return c.stat || c.gp; });
  }
  // NHL's Scoring card: the average 1st-period goals, 0-0 and tied rates
  function scoringCard(list, k) {
    var s = seg(k), n = list.length, pts = 0, zero = 0, tied = 0;
    list.forEach(function(g) { var sc = g.res[k].sc, t = sc[0] + sc[1]; pts += t; if (!t) zero++; if (sc[0] === sc[1]) tied++; });
    return { id: 'scoring', title: s.tag + ' Scoring', gp: n, stat: [
      ['Avg ' + s.tag + ' goals', n ? (pts / n).toFixed(2) : '&mdash;'],
      ['0&ndash;0', n ? zero + ' <small>(' + pctCell(zero, n) + ')</small>' : '&mdash;'],
      ['Tied after one', n ? tied + ' <small>(' + pctCell(tied, n) + ')</small>' : '&mdash;']] };
  }
  function recOf(r, fmt) { return r.w + '-' + r.l + (fmt ? '-' + r.t : ''); }
  function cardHtml(c, total) {
    var body;
    if (c.stat) body = c.stat.map(function(x) { return '<div class="st-row st-stat"><span class="st-lbl">' + x[0] + '</span><span class="st-num mono">' + x[1] + '</span></div>'; }).join('');
    else {
      var mark = c.gp < total ? '<sup class="st-mark" title="Games without a saved line aren&rsquo;t counted">*</sup>' : '';
      var fmts = c.rows.map(function(x) { return x.fmt; }).filter(Boolean);
      body = stHead(fmts.length ? (fmts.indexOf('T') !== -1 && fmts.indexOf('P') !== -1 ? 'Record' : 'W-L-' + fmts[0]) : 'W-L', '%', 'Units') +
        c.rows.map(function(x) { return stRow(x.label, recOf(x.r, x.fmt) + mark, stPct(x.r.w, x.r.l), stUnits(x.r)); }).join('');
      // ML only: a tied segment is a tie (0u); its own row, % of every game
      if (c.tie != null) body += stRow('Tie', String(c.tie), pctCell(c.tie, c.gp), null, 'st-tie');
    }
    return stCard(c.title, '', body);
  }
  function seasonMarked(cards, total) { return cards.some(function(c) { return !c.stat && c.gp < total; }); }

  // ---- NHL Goal Stats: 1st-period goals (from the old NHL page) ----
  function goalStats(games) {
    var list = graded(games, '1p').filter(function(g) { return g.state === 'final'; }), n = list.length;
    function tp(g) { return g.res['1p'].sc[0] + g.res['1p'].sc[1]; }
    function cnt(arr, fn) { return arr.filter(fn).length; }
    function bars(rows, of) {
      return rows.map(function(r) {
        return '<div class="st-row st-stat"><span class="st-lbl">' + r[0] + '</span><span class="st-num mono">' + r[1] + ' <small>(' + pctCell(r[1], of) + ')</small></span></div>' +
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
      ['Off a Shutout: Goals Scored', 'Team&rsquo;s own 1P goals the game after being shut out', m, bars([['0 goals', offShut.filter(function(x) { return x === 0; }).length], ['1 goal', offShut.filter(function(x) { return x === 1; }).length], ['2+ goals', offShut.filter(function(x) { return x >= 2; }).length]], m)],
      ['Off a Shutout: 1P Goals', 'Both teams, the game after a shutout loss', sg.length, bars([['Over 0.5', cnt(sg, function(g) { return tp(g) > 0; })], ['Over 1.5', cnt(sg, function(g) { return tp(g) > 1; })], ['Over 2.5', cnt(sg, function(g) { return tp(g) > 2; })]], sg.length)]
    ];
    return '<div class="st-grid">' + cards.map(function(c) { return stCard(c[0], c[1] + ' &middot; ' + c[2] + ' games', c[3]); }).join('') + '</div>';
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
    return stRow(label, a.w + '-' + a.l + '-' + a.t, boardState.view === 'pct' ? stPct(a.w, a.l) : '', boardState.view === 'pct' ? null : stUnits(a));
  }
  function boardCard(title, sub, rows, note, fmt) {
    return stCard(title, sub, stHead(fmt, boardState.view === 'pct' ? 'Win %' : '', boardState.view === 'pct' ? '' : 'Units') +
      lockRows(rows, 'board') + (note ? '<div class="st-note">' + note + '</div>' : ''));
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
      cards.push(boardCard('Home / Road Fav &amp; Dog', s.tag + ' moneyline by side', Object.keys(groups).map(function(g) { return boardRow(g, groups[g]); }), priced + ' games with a closing ' + s.tag + ' moneyline', 'W-L-T'));
      cards.push(boardCard('Odds Tiers', s.tag + ' moneyline by closing price', tiers.map(function(t, i) { return boardRow(t[0], tr[i]); }), 'Ties are 0u, left out of win %', 'W-L-T'));
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
      cards.push(boardCard('Favorites by line', s.tag + ' Spread cover rate', B.map(function(b, i) { return boardRow('Favored by ' + b[0], fav[i]); }), 'Pushes left out of cover %', 'W-L-P'));
      cards.push(boardCard('Underdogs by line', s.tag + ' Spread cover rate', B.map(function(b, i) { return boardRow('Getting ' + b[0], dog[i]); }), 'Units at the closing price (-110 when only the line was saved)', 'W-L-P'));
    }
    var pills = (canMl && canAts ? '<div class="seg-toggle" role="group" aria-label="Market"><button class="seg-btn" data-board-mk="ml" aria-pressed="' + (mk === 'ml') + '">Moneyline</button>' +
        '<button class="seg-btn" data-board-mk="ats" aria-pressed="' + (mk === 'ats') + '">Spread</button></div>' : '') +
      '<div class="seg-toggle" role="group" aria-label="Show"><button class="seg-btn" data-board-view="pct" aria-pressed="' + (boardState.view === 'pct') + '">Win %</button>' +
      '<button class="seg-btn" data-board-view="units" aria-pressed="' + (boardState.view === 'units') + '">Profit</button></div>';
    return stSection('statsBoard', 'Money Board', pills, '<p class="st-sec-sub">' + esc(s.tag) + ' ' + (mk === 'ml' ? 'Moneyline' : 'Spread') + ' at closing prices</p>' +
      '<div class="st-grid st-grid-2">' + cards.join('') + '</div>');
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
      if (hockey && g.als && g.hls && g.als.length > 1 && g.hls.length > 1) {   // live games carry only the periods so far
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
  // every finished game's edges per segment, counted once a page load
  var EDGE_CACHE = {};
  function edgeData(k) { return EDGE_CACHE[k] || (EDGE_CACHE[k] = edgeRows(finalGames(), k)); }
  function edgeRest(k) { return k === '1p' ? 'periods 2&ndash;3 (and OT)' : k === '1q' ? 'quarters 2&ndash;4' : k === 'f5' ? 'innings 6&ndash;9' : 'the 2nd half'; }
  // Best Closers / Biggest Faders: each team's record over the rest of the
  // game (after the segment); 3+ games, win % leaves ties out
  function closerBoards(k) {
    var E = edgeData(k);
    var teams = Object.keys(E.later).filter(function(t) { return D.teams[t]; }).map(function(t) {
      var x = E.later[t], d = x.w + x.l; return { t: t, x: x, p: d ? x.w / d : 0, q: d ? x.l / d : 0, d: d };
    }).filter(function(e) { return e.x.w + e.x.l + e.x.t >= 3 && e.d; });
    function by(key) { return teams.slice().sort(function(a, b) { return b[key] - a[key] || b.d - a.d || (a.t < b.t ? -1 : 1); }); }
    return { best: by('p'), worst: by('q') };
  }
  // a team's spot in the top 5 of either board: {k, kind 'best' | 'worst', rank}
  function edgeRank(slug) {
    var out = null;
    ['best', 'worst'].forEach(function(kind) {
      edgeSegs().forEach(function(s) {
        if (out) return;
        var i = closerBoards(s.key)[kind].slice(0, 5).map(function(e) { return e.t; }).indexOf(slug);
        if (i !== -1) out = { k: s.key, kind: kind, rank: i + 1 };
      });
    });
    return out;
  }
  function ordinal(n) { return n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] || 'th'); }
  // "3rd-best closer in the NHL" / "Biggest fader: 2nd" (with the segment's tag when the sport has two)
  function edgeRankWords(x) {
    var tag = edgeSegs().length > 1 ? seg(x.k).tag + ' ' : '';
    if (x.kind === 'best') return (x.rank === 1 ? 'Best ' : ordinal(x.rank) + '-best ') + tag + 'closer in the ' + D.label;
    return 'Biggest ' + tag + 'fader' + (x.rank === 1 ? ' in the ' + D.label : ': ' + ordinal(x.rank));
  }
  function closerRow(e, key) {
    return stRow(teamLink(e.t, badge(e.t, 22) + '<span class="st-abbr">' + esc(tcode(e.t)) + '</span>'), e.x.w + '-' + e.x.l + '-' + e.x.t, Math.round(100 * e[key]) + '%', null, 'st-team');
  }
  function edgeSection(k) {
    if (!(LEAD_CUTS[D.sport] || {})[k]) return '';
    var E = edgeData(k), name = EDGE_NAME[k], flag = 'edge' + k, cuts = LEAD_CUTS[D.sport][k];
    if (!E.n) return stSection('edges-' + k, name[0], '', emptyNote('No finished games with the ' + esc(seg(k).label) + ' graded yet.'));
    var rows = E.rows.map(function(x) { return stRow(x.label, String(x.n), pctCell(x.hit, x.n), x.pr ? stUnits({ u: x.u, pr: x.pr }) : null); });
    var tip = 'Games: finished games with the ' + esc(seg(k).label) + ' graded. Rate: how often the row came true. ' +
      'Units: 1 unit on that side at the closing pregame price (spreads and totals at -110); live prices after the break will differ. ' +
      'Lead sizes: ' + (cuts[0] === 1 ? '1' : '1&ndash;' + cuts[0]) + ' small, ' + (cuts[0] + 1) + '&ndash;' + cuts[1] + ' medium, ' + (cuts[1] + 1) + '+ big.';
    var B = closerBoards(k);
    var boards = B.best.length ? '<div class="st-grid st-grid-2">' +
      stCard('Best Closers', 'Win ' + edgeRest(k) + ' most', stHead('W-L-T', 'Win %', '') + lockRows(B.best.slice(0, 5).map(function(e) { return closerRow(e, 'p'); }), flag)) +
      stCard('Biggest Faders', 'Lose ' + edgeRest(k) + ' most', stHead('W-L-T', 'Loss %', '') + lockRows(B.worst.slice(0, 5).map(function(e) { return closerRow(e, 'q'); }), flag)) +
      '</div>' : '';
    return stSection('edges-' + k, name[0] + ' ' + infoTip(tip, true), '',
      '<p class="st-sec-sub">' + name[1] + ' &middot; ' + E.n + ' games</p>' +
      stCard(seg(k).tag + ' Edges', 'What happens over ' + edgeRest(k), stHead('Games', 'Rate', 'Units') + lockRows(rows, flag), '', 'st-wide') + boards);
  }

  // the page's segment toggle, pinned under the header like Matchups / Odds
  function statsSegBar(k) {
    return D.segments.length > 1 ? '<div class="ob-stick" id="stStick"><div class="sport-seg-row odds-controls">' + segToggle('statsSeg', k) + '</div></div>' : '';
  }
  function wireStatsSeg(draw) {
    var segEl = document.getElementById('statsSeg');
    if (segEl) segEl.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { setSeg(b.getAttribute('data-seg')); draw(); } };
    stickBelowNav(document.getElementById('stStick'));
  }
  function noStats() { app.innerHTML = emptyNote('No ' + esc(D.label) + ' games loaded yet &mdash; stats appear once games are played.'); }
  function keepPlace(anchor) {
    var keep = anchor ? { id: anchor.id, top: anchor.getBoundingClientRect().top } : null;
    return function() { if (keep) { var el = document.getElementById(keep.id); if (el) window.scrollBy(0, el.getBoundingClientRect().top - keep.top); } };
  }
  function splitsStandout(k) { var e = sitEngine(); return e && e.standout ? e.standout(k) : null; }
  function teaser(href, title, body, go) {
    return '<a class="st-card st-teaser" href="' + href + '"><div class="st-head"><h4>' + title + '</h4></div><p>' + body + '</p><span class="st-go">' + go + ' &rarr;</span></a>';
  }
  function statsTeasers(k) {
    var sd = splitReg() ? splitsStandout(k) : null;
    var t1 = sd ? teaser(statsUrl('splits'), 'Splits: ' + esc(sd.label), '<b class="mono">' + esc(sd.rec) + '</b> &middot; ' + sd.pct + '% ' + esc(sd.pctHead.replace(' %', '').toLowerCase()) + ' rate, ' + esc(seg(k).tag + ' ' + sd.market) + (sd.own ? '' : ' (home team)'), 'See all splits')
      : teaser(statsUrl('splits'), 'Splits', 'Records by home and road, favorite and underdog, rest and schedule.', 'See all splits');
    var es = edgeSegs()[0], top = es ? closerBoards(es.key).best[0] : null;
    var t2 = top ? teaser(statsUrl('edges'), 'Edges: Best closer: ' + badge(top.t, 22) + '<span class="st-abbr">' + esc(tcode(top.t)) + '</span>',
        '<b class="mono">' + top.x.w + '-' + top.x.l + '-' + top.x.t + '</b> &middot; ' + Math.round(100 * top.p) + '% over ' + edgeRest(es.key) + ' after the ' + esc(segWord(es.key)), 'See all edges')
      : teaser(statsUrl('edges'), 'Edges', 'What happens after the ' + esc(segWord((es || D.segments[0]).key)) + ', and who closes and fades.', 'See all edges');
    return '<div class="st-grid st-grid-2 st-teasers">' + t1 + t2 + '</div>';
  }

  // /stats/: Season Results, Scoring, Money Board, the two teasers
  function renderStats() {
    if (!D.season || !allDates().length) { noStats(); return; }
    function draw(anchor) {
      var back = keepPlace(anchor);
      var k = getSeg(), range = tfRange(), N = graded(range.games, k).length;
      var cards = seasonCards(range.games, k);
      var season = stSection('statsSeason', 'Season Results &middot; ' + N + ' game' + (N === 1 ? '' : 's'), tfControls(), range.line +
        (N ? '<div class="st-grid">' + cards.map(function(c) { return cardHtml(c, N); }).join('') + '</div>' +
          (seasonMarked(cards, N) ? '<p class="st-foot"><sup>*</sup> Games without a saved line aren&rsquo;t counted.</p>' : '')
          : emptyNote('No graded games in this range yet.')));
      var scoring = stSection('statsScoring', 'Scoring', '', D.sport === 'nhl' ? goalStats(finalGames()) : '<div id="statsScoringBody"></div>');
      app.innerHTML = statsSegBar(k) + season + scoring + moneyBoard(finalGames(), k) + statsTeasers(k);
      wireStatsSeg(function() { draw(document.getElementById('statsSeason')); });
      wireTf(function() { draw(document.getElementById('statsSeason')); });
      app.querySelectorAll('[data-board-view]').forEach(function(b) { b.onclick = function() { boardState.view = b.getAttribute('data-board-view'); draw(document.getElementById('statsBoard')); }; });
      app.querySelectorAll('[data-board-mk]').forEach(function(b) { b.onclick = function() { boardState.market = b.getAttribute('data-board-mk'); draw(document.getElementById('statsBoard')); }; });
      if (D.sport !== 'nhl') renderScoring(range.games, k);
      wireTips(app);
      back();
    }
    draw();
  }

  // /stats/splits/: Situational Results, league-wide
  function renderSplits() {
    if (!D.season || !allDates().length) { noStats(); return; }
    var eng = sitEngine();
    if (!eng) { app.innerHTML = emptyNote('Situational Results aren&rsquo;t set up for ' + esc(D.label) + ' yet.'); return; }
    // premium: one filter at a time (the time range here; View as and conference in situational.js)
    function comboOk() { return !(premiumLocked('splitCombine') && tf.mode !== 'all' && (eng.state.persp !== 'home' || eng.state.conf)); }
    function draw(anchor) {
      var back = keepPlace(anchor);
      var k = getSeg(), r = tfDates();
      eng.state.k = k;
      app.innerHTML = statsSegBar(k) + '<div id="statsSit"></div>';
      wireStatsSeg(function() { draw(document.getElementById('statsSit')); });
      renderSit('statsSit', { mode: 'league', range: r, noSeg: true, controls: tfControls(), line: r && r.label ? '<div class="sc-week">' + r.label + '</div>' : '',
        after: function() { wireTf(function() { draw(document.getElementById('statsSit')); }, comboOk); } });
      back();
    }
    SIT_ON_SEG = function(k, anchor) { setSeg(k); draw(anchor); };
    draw();
  }

  // /stats/edges/: the Intermission / Quarter / Halftime / F5 Edge per segment
  function renderEdges() {
    if (!D.season || !allDates().length) { noStats(); return; }
    var es = edgeSegs();
    if (!es.length) { app.innerHTML = emptyNote('Edges aren&rsquo;t set up for ' + esc(D.label) + ' yet.'); return; }
    var html = es.map(function(s) { return edgeSection(s.key); }).join('');
    if (premiumLocked('edgesPage')) html = '<div class="pm-blur" aria-hidden="true">' + html + '</div><a class="pm-unlock" href="' + ROOT + '#premium">Unlock with Premium</a>';
    app.innerHTML = html;
    wireTips(app);
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
      ' · league ' + pct0(c.base) + ' · <span class="' + unitCls(c.units) + '">' + fmtUnits(c.units) + '</span></div>' +
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
    return '<div class="mt-game" id="mt-' + esc(g.id) + '"><div class="mt-head"><span class="tr-time">' + esc(trTime(g.start)) + '</span>' +
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
    // the slate's record, and the season's next to it (every slate, same segment and market)
    var season = [0, 0];
    Object.keys(TR.slates || {}).forEach(function(key) {
      var x = dayRecord(TR.slates[key].cards.filter(function(c) { return c.seg === k && (TR_MKT === 'all' || c.mk === TR_MKT); }));
      season[0] += x[0]; season[1] += x[1];
    });
    if (cards.length || season[0] + season[1]) {
      var r = dayRecord(cards);
      html += '<p class="tr-day" title="' + esc(TR.tips.todays_record || '') + '">' + (cards.length ? esc(o.recLabel) + ' Trends: <b>' + r[0] + '–' + r[1] + '</b>' : '') +
        (season[0] + season[1] ? (cards.length ? ' &middot; ' : '') + 'This season: <b>' + season[0] + '–' + season[1] + '</b>' : '') + '</p>';
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
      // the hub's "See the full matchup" link: #mt-<game id>
      var hit = /^#mt-/.test(location.hash) && document.getElementById(location.hash.slice(1));
      if (hit) { hit.classList.add('mt-hit'); hit.scrollIntoView({ block: 'start' }); }
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
  // Football: one slate per week, like its Matchups page
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
      ties: periodFamily(), tonightLocked: function() { return premiumLocked('tonightOnly'); },
      locked: function() { return !IS_PREMIUM; }, lockHtml: function() { return LOCK_HTML; } });
    return SIT;
  }
  // view = {mode: 'league'} or {mode: 'team', slug}
  function renderSit(boxId, view) {
    var e = sitEngine();
    if (e) e.render(document.getElementById(boxId), view);
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
  // and finished games show each source's closing line; Open is always the
  // opening line. The best price per side gets a green outline (the key at
  // the bottom says so). The controls and the header row stay pinned.
  var MKT_CUR = null;
  // the market pills: totals read "O/U" (NHL "O/U 1.5", MLB "F5 O/U")
  function pillLabel(x) { return x[1] === 'total' ? x[2].replace('Total', 'O/U') : x[2]; }
  // "· FINAL" or "· LIVE · 1ST" after a game's start time (Odds and Matchups)
  function livePeriod(g) {
    var d = String(g.detail || '').trim(), p = d.split(' - ');
    if (/\b(AM|PM)\b|\bE[SD]?T\b/.test(d)) return '';   // still the scheduled start, not a clock
    return (p.length > 1 ? p[p.length - 1] : d).toUpperCase();
  }
  function oddsStatus(g) {
    if (g.state === 'final') return ' &middot; FINAL';
    // a game whose status never came back (off-season, postponed) isn't live
    var stale = g.start && Date.now() - Date.parse(g.start) > 8 * 3600e3;
    if ((g.state === 'live' || g.state === 'in') && !stale) { var p = livePeriod(g); return ' &middot; <span class="st-live">LIVE' + (p ? ' &middot; ' + esc(p) : '') + '</span>'; }
    return '';
  }
  // one side's result on a finished game (the Odds page's past dates): W / L
  // / P, from the game's res (away side: su, ats; tot O/U; btts and rfi Y/N)
  function oddsSideRes(g, k, m, s) {
    var r = g.state === 'final' && (g.res || {})[k];
    if (!r || !r.sc) return null;
    if (r.na) return 'P';
    function yn(x, yes, flip) { var v = !x || x === 'NA' || x === 'P' ? 'P' : x === yes ? 'W' : 'L'; return flip ? flipRes(v) : v; }
    if (m === 'ml' || m === 'ats') {
      var x = r[m === 'ml' ? 'su' : 'ats'];
      if (!x || x === 'NA') return 'P';
      x = s === 'home' ? flipRes(x) : x;
      return x === 'W' || x === 'L' ? x : 'P';
    }
    if (m === 'ml3') return !r.su || r.su === 'NA' ? 'P' : r.su === { away: 'W', home: 'L', draw: 'T' }[s] ? 'W' : 'L';
    if (m === 'total') return yn(r.tot, 'O', s === 'under');
    if (m === 'btts') return yn(r.btts, 'Y', s === 'no');
    if (m === 'rfi') return yn(r.rfi, 'Y', s === 'nrfi');
    return null;
  }
  // One cell style for Odds and Matchups: the line on top (large, bold), the
  // price under it (small, muted); a moneyline cell shows the price in the
  // line style.
  function oddsCell(line, price) {
    if (line == null) return price == null ? '' : '<span class="ob-ln">' + esc(signed(price)) + '</span>';
    return '<span class="ob-ln">' + esc(line) + '</span>' + (price != null ? '<span class="ob-pr">' + esc(signed(price)) + '</span>' : '');
  }
  // the name behind a logo or cell (data-tip): hover shows the title; a long
  // press (logos) or a tap (cells without a link) shows it on phones
  function wireTips(root) {
    if (root.__tips) return;
    root.__tips = true;
    var tip = null, timer = null;
    function hide() { if (tip) { tip.remove(); tip = null; } }
    function show(el) {
      hide();
      tip = document.createElement('div');
      tip.className = 'rt-tip';
      tip.textContent = el.getAttribute('data-tip');
      document.body.appendChild(tip);
      var r = el.getBoundingClientRect();
      tip.style.left = Math.max(8, Math.min(window.innerWidth - tip.offsetWidth - 8, r.left + r.width / 2 - tip.offsetWidth / 2)) + 'px';
      tip.style.top = (window.scrollY + r.top - tip.offsetHeight - 6) + 'px';
      setTimeout(hide, 1800);
    }
    root.addEventListener('touchstart', function(e) {
      var el = e.target.closest('[data-tip]');
      clearTimeout(timer);
      if (el) timer = setTimeout(function() { show(el); }, 450);
    }, { passive: true });
    root.addEventListener('touchend', function() { clearTimeout(timer); }, { passive: true });
    root.addEventListener('touchmove', function() { clearTimeout(timer); }, { passive: true });
    root.addEventListener('click', function(e) {
      var el = e.target.closest('[data-tip]');
      if (el && el.hasAttribute('data-tap') && !e.target.closest('a')) show(el);
    });
    root.addEventListener('contextmenu', function(e) { if (e.target.closest('img[data-tip]')) e.preventDefault(); });
    window.addEventListener('scroll', hide, { passive: true });
  }
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
      function cellTxt(v) { return oddsCell(v.line, v.price); }
      function name(b) { return (sources[b] || {}).name || 'Source ' + b; }
      // a book's logo (its name on hover, or on a long press on phones)
      function head(b) {
        var s = sources[b] || {};
        return s.logo ? '<img class="ob-logo" src="' + ROOT + s.logo + '" alt="' + esc(name(b)) + '" title="' + esc(name(b)) + '" data-tip="' + esc(name(b)) + '" loading="lazy">' : '<span class="ob-bname">' + esc(name(b)) + '</span>';
      }
      // the team (and, once the game starts, its score in the segment)
      function teamCell(g, sd, k) {
        if (sd[1]) return '<span class="ob-team"><span class="ob-tie">' + esc(sd[1]) + '</span></span>';
        var side = sd[2] || sd[0], slug = g[side], sc = g.state !== 'pre' && g.score && g.score[k];
        return '<span class="ob-team">' + badge(slug, 20) + '<span class="tn-full">' + esc(shortName(slug)) + '</span><span class="tn-short mono">' + esc(code(slug)) + '</span>' +
          (sc ? '<span class="ob-sc mono">' + esc(sc[side === 'away' ? 0 : 1]) + '</span>' : '') + '</span>';
      }
      // Team, Open and one column per source
      function colgroup(cols) { return '<colgroup><col class="ob-w-team"><col class="ob-w-open">' + cols.map(function() { return '<col class="ob-w-src">'; }).join('') + '</colgroup>'; }
      function columns(games, k, m) {
        var ids = {};
        games.forEach(function(g) { Object.keys((((g.books || {})[k] || {})[m]) || {}).forEach(function(b) { ids[b] = 1; }); });
        return order.filter(function(b) { return ids[b]; });
      }
      function table(games, k, m, kind, cols, lined) {
        var body = games.map(function(g) {
          var books = ((g.books || {})[k] || {})[m] || {};
          var best = ((g.best || {})[k] || {})[m], open = ((g.open || {})[k] || {})[m];
          var past = g.state !== 'pre';
          var rows = sides(m, kind).map(function(sd) {
            var s = sd[0], b = top(best, m, s), o = top(open, m, s);
            // a finished game: the side that won green, the loser dimmed, a tie or push yellow
            var rc = resultCls(oddsSideRes(g, k, m, s));
            return '<tr><th scope="row" class="ob-c-team">' + teamCell(g, sd, k) + '</th>' +
              '<td class="ob-c-open' + (o ? rc : '') + '">' + (o ? cellTxt(o) : '') + '</td>' +
              cols.map(function(id) {
                var v = val(books[id], m, s);
                if (!v) return '<td class="ob-na"></td>';
                var cls = 'ob-cell' + rc + (counts(id, m) && same(v, b) ? ' ob-best' : '');
                return '<td class="' + cls + '">' + (v.link && !past ? '<a href="' + esc(v.link) + '" target="_blank" rel="sponsored noopener" title="' + esc(name(id)) + '">' + cellTxt(v) + '</a>' : cellTxt(v)) + '</td>';
              }).join('') + '</tr>';
          }).join('');
          // timeET already names the day in week view
          var day = weeks && g.start && !(D && D.schedule === 'week') ? new Date(g.start).toLocaleDateString('en-US', { weekday: 'short', timeZone: 'America/New_York' }) + ' ' : '';
          // every game's time row carries Open and the book logos, over their columns
          return '<tbody class="ob-game"><tr class="ob-ghead"><th scope="col" class="ob-c-team"><span class="ob-time">' + esc(day) + (g.start ? esc(timeET(g.start)) : 'TBD') + oddsStatus(g) + '</span></th>' +
            '<th scope="col" class="ob-c-open">Open</th>' + cols.map(function(b) { return '<th scope="col" class="ob-src">' + head(b) + '</th>'; }).join('') + '</tr>' + rows + '</tbody>';
        }).join('');
        return '<div class="ob-scroll" id="obBody"><table class="ob-grid" style="--n:' + cols.length + '">' + colgroup(cols) + body + '</table></div>';
      }
      function draw(docs) {
        var k = getSeg(), ms = markets(k);
        var games = [];
        docs.forEach(function(doc) { (doc.games || []).forEach(function(g) { games.push(g); }); });
        // football weeks: finished games drop to the bottom, in start order
        if (weeks) games = games.filter(function(g) { return g.state !== 'final'; }).concat(games.filter(function(g) { return g.state === 'final'; }));
        if (!ms.some(function(x) { return x[1] === MKT_CUR; })) {
          // start on the first market with lines on this slate
          var withLines = ms.filter(function(x) { return games.some(function(g) { var b = ((g.books || {})[k] || {})[x[1]]; return b && Object.keys(b).length; }); });
          MKT_CUR = ((withLines[0] || ms[0]) || [])[1] || null;
        }
        var mk = ms.filter(function(x) { return x[1] === MKT_CUR; })[0];
        var m = mk ? mk[1] : null;
        var lined = mk && games.some(function(g) { var b = ((g.books || {})[k] || {})[m]; return b && Object.keys(b).length; });
        var cols = games.length ? columns(games, k, m) : [];
        var html = weeks ? weekBar(weeks, cur, thisWeek) : dateBar(cur, dates, true);
        html += '<div class="ob-stick" id="obStick"><div class="sport-seg-row odds-controls">' + (D.segments.length > 1 ? segToggle('pageSeg', k) : '') +
          '<div class="seg-toggle" id="oddsMkt">' + ms.map(function(x) {
            return '<button class="seg-btn" data-mkt="' + x[1] + '" aria-pressed="' + (x[1] === MKT_CUR) + '">' + esc(pillLabel(x)) + '</button>';
          }).join('') + '</div></div></div>';
        var first = slate()[0];
        if (!games.length) html += '<div class="no-games-note">No ' + esc(D.label) + ' games ' + (weeks ? 'this week' : 'on ' + esc(dateLabel(cur))) + '.</div>';
        else {
          if (!lined) html += '<div class="no-games-note">' + (first && first < todayET() ? 'Lines not available.' : 'No ' + esc(seg(k).label) + ' ' + (mk ? MKT_WORD[m] || esc(mk[2]) : 'lines') + ' posted yet.') + '</div>';
          html += table(games, k, m, mk ? mk[3] : 'side', cols, lined);
        }
        if (m === 'btts') html += '<p class="odds-note">Both teams to score in the 1st period. BTTS isn&rsquo;t on our odds feed, so our team enters ' + (cols[0] && cols[0] !== 'consensus' ? esc(name(cols[0])) + '&rsquo;s price' : 'a consensus price across the books') + '.</p>';
        app.innerHTML = html;
        stickBelowNav(document.getElementById('obStick'));
        wireTips(app);
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

  // ------------------------------------------------------------- Arena hub
  // /{sport}/: the sport's front page (Chris's Arena hub spec). Teasers, each
  // linking to its full page, from data.json (NHL: sport.json), trends.json
  // and hub.json (scripts/hub.py: Matchup of the Day and its record, The
  // Daily, the Learn link). Football says "this week" where others say "today".
  function hubSlate() {
    if (D.schedule === 'week') { var wk = (D.weeks || []).length ? currentWeek(D.weeks) : null; return { key: wk, games: wk ? weekGames(wk) : [] }; }
    return { key: todayET(), games: (D.games[todayET()] || []).slice() };
  }
  function hubPrev(slate) {
    if (D.schedule === 'week') {
      var keys = (D.weeks || []).map(function(w) { return w.key; }), i = keys.indexOf(slate.key);
      return i > 0 ? weekGames(keys[i - 1]) : [];
    }
    return D.games[addDaysStr(todayET(), -1)] || [];
  }
  // live = under way by the scoreboard or by the clock (the feed can lag)
  function hubLive(g) { return g.state === 'in' || (g.state !== 'final' && started(g)); }
  function hubSec(title, link, body, id) {
    return '<section class="hub-sec"' + (id ? ' id="' + id + '"' : '') + '><div class="hub-head"><h2>' + title + '</h2>' + (link || '') + '</div>' + body + '</section>';
  }
  function hubLink(href, txt) { return '<a class="hub-more" href="' + href + '">' + txt + ' &rarr;</a>'; }
  // the best Results-box row (record and units) from the last slate; never a losing one
  function hubBest(prev) {
    var rows = [];
    (periodFamily() ? [D.segments[0].key] : D.segments.map(function(s) { return s.key; })).forEach(function(k) {
      resultRows(prev, k).forEach(function(x) { if (x.n && x.u > 0 && x.w > x.l) rows.push({ x: x, k: k }); });
    });
    rows.sort(function(a, b) { return (b.x.pct - a.x.pct) || (b.x.u - a.x.u); });
    var top = rows[0];
    if (!top) {
      var n = prev.filter(function(g) { return g.state === 'final'; }).length;
      return n ? n + ' game' + (n === 1 ? '' : 's') + ' graded' : 'No games';
    }
    var x = top.x, segTxt = periodFamily() || D.segments.length < 2 ? '' : seg(top.k).tag + ' ';
    var ties = x.t ? ' (' + x.t + ' ' + (x.ties ? 'tie' : 'push') + (x.t === 1 ? '' : x.ties ? 's' : 'es') + ')' : '';
    return segTxt + x.label.replace(' (moneyline)', ' ML').replace(' (spread)', ' ATS').replace(' (F5 moneyline)', ' F5 ML') + ' went ' + x.w + '–' + x.l + ties + ', ' + fmtUnits(x.u).replace(/\.?0+u$/, 'u');
  }
  function hubHero(slate, prev) {
    var wk = D.schedule === 'week', live = slate.games.filter(hubLive).length;
    function n(v, l) { return '<div class="hub-num"><b class="mono">' + v + '</b><span>' + l + '</span></div>'; }
    return '<div class="hub-hero">' + n(slate.games.length, wk ? 'Matchups this week' : 'Matchups today') + n(live, 'Live now') +
      '<div class="hub-num hub-num-wide"><b>' + esc(hubBest(prev)) + '</b><span>' + (wk ? 'Last week&rsquo;s best' : 'Yesterday&rsquo;s best') + '</span></div></div>';
  }
  // 3 rows: live games, then the next to start; 3 finals once they're all done
  function hubGames(slate) {
    var live = slate.games.filter(hubLive);
    var pre = slate.games.filter(function(g) { return g.state !== 'final' && !hubLive(g); }).sort(function(a, b) { return (a.start || '') < (b.start || '') ? -1 : 1; });
    var fin = slate.games.filter(function(g) { return g.state === 'final'; });
    var rows = live.concat(pre);
    if (rows.length < 3) rows = rows.concat(fin.slice().reverse());
    rows = rows.slice(0, 3);
    if (!rows.length) return '<div class="no-games-note">No ' + esc(D.label) + ' games ' + (D.schedule === 'week' ? 'this week' : 'today') + '.</div>';
    return '<div class="hub-games">' + rows.map(function(g) {
      var st = g.state === 'final' ? 'Final' : hubLive(g) ? 'Live' : trTime(g.start);
      function side(slug, sc) { return '<span class="hub-gt">' + badge(slug, 20) + '<b>' + esc(tcode(slug)) + '</b>' + (sc != null ? '<span class="mono">' + esc(sc) + '</span>' : '') + '</span>'; }
      var show = (g.state === 'final' || hubLive(g)) && g.as != null;
      return '<a class="hub-game" href="' + ROOT + SPORT_SLUG + '/matchups/' + (D.schedule === 'week' ? '?week=' + g.wk : '') + '"><span class="hub-gs' + (hubLive(g) ? ' live' : '') + '">' + esc(st) + '</span>' +
        side(g.away, show ? g.as : null) + '<span class="hub-at">@</span>' + side(g.home, show ? g.hs : null) + '</a>';
    }).join('') + '</div>';
  }
  function hubPriceTxt(m) {
    var p = m.price, ln = p.line == null ? '' : m.mk === 'total' ? (m.pick === 'under' ? 'U ' : 'O ') + p.line + ' ' : m.mk === 'ats' ? signed(p.line) + ' ' : '';
    return ln + signed(p.price);
  }
  function hubMotd(H, slate) {
    var m = H.motd, wk = D.schedule === 'week', rec = H.motdRecord || {}, out;
    if (!m) out = '<p class="hub-none">No standout matchup ' + (wk ? 'this week' : 'today') + '.</p>';
    else {
      var g = findGame(m.id) || m, href = ROOT + SPORT_SLUG + '/trends/?' + (wk ? 'week=' + slate.key : 'date=' + m.date) + '&seg=' + m.seg + '#mt-' + m.id;
      out = '<div class="hub-motd"><div class="hub-motd-top"><span class="tr-time">' + esc(trTime(g.start)) + '</span>' +
        (m.label ? '<span class="mt-label">' + esc(m.label) + '</span>' : '') + '</div>' +
        '<div class="hub-motd-teams">' + badge(m.away, 26) + nameHtml(m.away) + '<span class="hub-at">@</span>' + badge(m.home, 26) + nameHtml(m.home) + '</div>' +
        '<p class="hub-motd-bet"><b>' + m.n + ' trends agree:</b> ' + esc(m.bet) +
        (m.price ? ' <span class="hub-price">Best price <b class="mono">' + esc(hubPriceTxt(m)) + '</b> at ' + esc(m.price.book) + '</span>' : '') + '</p>' +
        '<ul class="hub-motd-list">' + m.trends.map(function(t) { return '<li><span>' + esc(t.text) + '</span>' + (t.kind === 'streak' ? '' : '<b class="mono">' + esc(t.rec) + '</b>') + '</li>'; }).join('') + '</ul>' +
        hubLink(href, 'See the full matchup') + '</div>';
    }
    var last = rec.last, season = rec.season || [0, 0];
    var foot = (last ? '<span>' + (wk ? 'Last week' : 'Yesterday') + ': ' + ({ W: '✓', L: '✗', P: '–' }[last.result] || '') + ' ' + esc(last.bet) + (last.score ? ' (' + esc(last.score) + ')' : '') + '</span>' : '') +
      (season[0] + season[1] ? '<span>Season: <b class="mono">' + season[0] + '–' + season[1] + '</b></span>' : '');
    return out + (foot ? '<div class="hub-motd-rec">' + foot + '</div>' : '');
  }
  function hubDaily(H) {
    var wk = D.schedule === 'week', dl = H.daily || {};
    var names = wk ? { recap: 'Weekend Recap', preview: 'Week ' + ((((D.weeks || []).filter(function(w) { return w.key === hubSlate().key; })[0] || {}).label || '').replace(/^Week /, '')) + ' Preview' }
      : { recap: 'The Morning Run', preview: 'On Tap' };
    return '<div class="hub-daily">' + ['recap', 'preview'].map(function(kind) {
      var p = dl[kind] || {};
      if (p.path) return '<a class="dp-card hub-dcard" href="' + ROOT + p.path + '"><span class="hd-kicker">' + esc(names[kind]) + '</span><b>' + esc(p.title) + '</b><span class="muted">' + esc(p.teaser) + '</span><span class="dp-more">Read it &rarr;</span></a>';
      return '<div class="dp-card hub-dcard soon"><span class="hd-kicker">' + esc(names[kind]) + '</span><b>Coming ' + (wk ? p.due : 'at ' + p.due) + ' ET</b></div>';
    }).join('') + '</div>';
  }
  function hubTrends(slate) {
    var cards = (((TR || {}).slates || {})[slate.key] || {}).cards || [];
    // up to 5 rows a card, games still to play first (football weeks run long)
    function short(c) {
      var open = c.games.filter(function(x) { var g = findGame(x.id); return g && g.state !== 'final'; });
      var done = c.games.filter(function(x) { return open.indexOf(x) === -1; });
      return Object.assign({}, c, { games: open.concat(done).slice(0, 5) });
    }
    return cards.length ? '<div class="tr-cards">' + cards.slice(0, 3).map(function(c) { return trendCard(short(c), false); }).join('') + '</div>'
      : '<p class="hub-none">No trends meet our bar ' + (D.schedule === 'week' ? 'this week' : 'today') + '.</p>';
  }
  // the longest run (3+) among teams playing, preferring an opponent on the opposite run
  function hubStreak(slate) {
    var before = D.schedule === 'week' ? ((D.weeks || []).filter(function(w) { return w.key === slate.key; })[0] || {}).start : todayET(), best = null;
    D.segments.forEach(function(s) {
      var seqs = teamSeqs(before, s.key);
      (D.markets || []).filter(function(x) { return x[0] === s.key && HIT[x[1]]; }).forEach(function(x) {
        var m = x[1];
        slate.games.filter(function(g) { return g.state !== 'final'; }).forEach(function(g) {
          ['away', 'home'].forEach(function(side) {
            var me = g[side], opp = g[side === 'away' ? 'home' : 'away'];
            var st = streakOf(((seqs[me] || {})[m]) || []), os = streakOf(((seqs[opp] || {})[m]) || []);
            if (!st || st.n < 3) return;
            var pair = os && os.n >= 3 && os.kind !== st.kind && (m === 'ml' || m === 'ats') ? os : null;
            var score = [pair ? 1 : 0, st.n, pair ? pair.n : 0];
            if (!best || score[0] > best.score[0] || (score[0] === best.score[0] && (score[1] > best.score[1] || (score[1] === best.score[1] && score[2] > best.score[2]))))
              best = { score: score, me: me, opp: opp, m: m, k: s.key, st: st, os: pair };
          });
        });
      });
    });
    if (!best) return '<p class="hub-none">No team playing ' + (D.schedule === 'week' ? 'this week' : 'today') + ' is on a run of 3 or more.</p>';
    var txt = streakWords(best.me, best.m, best.st, best.k) + '. ' + (D.schedule === 'week' ? 'This week' : 'Tonight') + ' vs ' + tcode(best.opp);
    if (best.os) {
      var w = best.m === 'ml' ? (best.os.kind === 'W' ? 'won' : 'lost') : (best.os.kind === 'W' ? 'covered' : 'failed to cover');
      txt += ', who have ' + w + ' ' + best.os.n + ' straight';
    }
    return '<div class="hub-line">' + badge(best.me, 26) + '<p>' + esc(txt) + '.</p></div>';
  }
  // the team with the most of its next game's situations in its favor
  function hubTeam(slate) {
    var e = sitEngine();
    if (!e || !e.spots) return '<p class="hub-none">Situational results aren&rsquo;t set up for ' + esc(D.label) + ' yet.</p>';
    var k = D.segments[0].key, mk = (e.markets[0] || {}).id, best = null;
    slate.games.filter(function(g) { return g.state !== 'final'; }).forEach(function(g) {
      ['away', 'home'].forEach(function(side) {
        var sp = e.spots(k, g[side], g.id, mk), win = sp.filter(function(x) { return x.edge > 0; });
        if (!win.length) return;
        if (!best || win.length > best.win.length || (win.length === best.win.length && sp.length < best.all.length)) best = { slug: g[side], win: win, all: sp };
      });
    });
    if (!best) return '<p class="hub-none">No team has a situation in its favor ' + (D.schedule === 'week' ? 'this week' : 'tonight') + '.</p>';
    var mkLabel = (e.markets.filter(function(x) { return x.id === mk; })[0] || {}).label || '';
    return '<div class="hub-team">' + badge(best.slug, 30) + '<div><b class="hub-team-name">' + nameHtml(best.slug) + '</b>' +
      '<p class="muted">' + best.all.length + ' spot' + (best.all.length === 1 ? '' : 's') + ', ' + best.win.length + ' winning (' + esc(seg(k).tag + ' ' + mkLabel) + ')</p>' +
      '<ul class="hub-spots">' + best.win.map(function(x) { return '<li>' + esc(x.label) + ' <b class="mono">' + esc(x.rec) + '</b></li>'; }).join('') + '</ul>' +
      (teamUrl(best.slug) ? hubLink(teamUrl(best.slug), 'See the team') : '') + '</div></div>';
  }
  // one Season Results stat a day (the same for everyone that day)
  function hubNumber() {
    var out = [];
    D.segments.forEach(function(s) {
      var k = s.key, w = segWord(k), ws = segWords(k), cards = seasonCards(finalGames(), k);
      var spreadWord = (w + ' spreads').replace(/^(\S+) (\S+) spreads$/, '$1-$2 spreads');
      var PH = {
        'Home / Away / Tie': { Home: 'of ' + ws + ' are won by the home team', Away: 'of ' + ws + ' are won by the road team', Tie: 'of ' + ws + ' end tied' },
        'Favorite / Underdog / Tie': { Favorite: 'of ' + ws + ' are won by the favorite', Underdog: 'of ' + ws + ' are won by the underdog' },
        'Home / Away / Push': { Home: 'of ' + spreadWord + ' are covered by the home team', Away: 'of ' + spreadWord + ' are covered by the road team' },
        'Favorite / Underdog / Push': { Favorite: 'of ' + spreadWord + ' are covered by the favorite', Underdog: 'of ' + spreadWord + ' are covered by the underdog' },
        'Both teams score: Yes / No': { Yes: 'of ' + ws + ' see both teams score' },
        'A run in the 1st inning': { YRFI: 'of games have a run in the 1st inning' }
      };
      cards.forEach(function(c) {
        var ph = PH[c.sub] || (/^Over \/ Under/.test(c.sub) ? { Over: 'of ' + ws + ' go Over ' + (D.sport === 'nhl' ? '1.5' : 'the total') } : null);
        if (!ph || c.gp < 10) return;
        Object.keys(ph).forEach(function(l) { out.push({ pct: Math.round(100 * (c.n[l] || 0) / c.gp), txt: ph[l] }); });
      });
    });
    if (!out.length) return '<p class="hub-none">Stats start once games are graded.</p>';
    var day = Math.floor(Date.parse(todayET() + 'T12:00:00Z') / 864e5), x = out[day % out.length];
    return '<p class="hub-number"><b class="mono">' + x.pct + '%</b> ' + esc(x.txt) + ' this season.</p>';
  }
  function renderHub() {
    var slate = hubSlate(), prev = hubPrev(slate), wk = D.schedule === 'week';
    Promise.all([
      fetch(ROOT + SPORT_SLUG + '/hub.json').then(function(r) { return r.ok ? r.json() : {}; }).catch(function() { return {}; }),
      fetch(ROOT + SPORT_SLUG + '/trends.json').then(function(r) { return r.ok ? r.json() : null; }).catch(function() { return null; })
    ]).then(function(res) {
      var H = res[0] || {};
      TR = res[1] || { slates: {}, tips: {}, markets: [] };
      var segName = D.segments.map(function(s) { return s.label.toLowerCase(); }).join(' and ');
      app.innerHTML = hubHero(slate, prev) +
        hubSec(wk ? 'This Week&rsquo;s Matchups' : 'Today&rsquo;s Matchups', slate.games.length ? hubLink(ROOT + SPORT_SLUG + '/matchups/', 'All ' + slate.games.length + ' matchups') : '', hubGames(slate)) +
        hubSec(wk ? 'Matchup of the Week' : 'Matchup of the Day', '', hubMotd(H, slate)) +
        hubSec('The Daily', hubLink(ROOT + 'daily/', 'All of The Daily'), hubDaily(H)) +
        hubSec('Trends to Watch', hubLink(ROOT + SPORT_SLUG + '/trends/', 'All trends'), hubTrends(slate)) +
        hubSec('Streak to Watch', hubLink(ROOT + SPORT_SLUG + '/trends/#streaks', 'See streaks'), hubStreak(slate)) +
        hubSec('Team to Watch', '', hubTeam(slate)) +
        hubSec('The Number', hubLink(ROOT + SPORT_SLUG + '/stats/', 'See stats'), hubNumber()) +
        '<section class="hub-sec hub-learn"><a href="' + ROOT + String(H.learn || '/learn/').replace(/^\//, '') + '">New to ' + esc(segName) + ' betting? Read the guide &rarr;</a></section>';
    });
  }

  // ---------------------------------------------------------------- boot
  // "i" tooltips open on tap (phones) as well as hover
  document.addEventListener('click', function(e) {
    var tip = e.target.closest ? e.target.closest('.info-tip') : null;
    document.querySelectorAll('.info-tip.open').forEach(function(t) { if (t !== tip) t.classList.remove('open'); });
    if (tip) tip.classList.toggle('open');
  });
  // NHL's data.json is its own shape; its Matchups, Stats, Trends and Teams pages read the shared shape (nhl/sport.json)
  var DATA_FILE = SPORT_SLUG === 'nhl' && ['hub', 'games', 'stats', 'splits', 'edges', 'trends', 'teams', 'team'].indexOf(SECTION) !== -1 ? 'sport.json' : 'data.json';
  fetch(ROOT + SPORT_SLUG + '/' + DATA_FILE).then(function(r) { return r.json(); }).then(function(data) {
    D = data;
    if (SECTION === 'odds') { renderOdds(); return; }   // works from odds.json alone for NHL
    if (!D.segments || !D.segments.length) return;
    if (SECTION === 'hub') renderHub();
    else if (SECTION === 'games') renderGames();
    else if (SECTION === 'stats') renderStats();
    else if (SECTION === 'splits') renderSplits();
    else if (SECTION === 'edges') renderEdges();
    else if (SECTION === 'trends') renderTrends();
    else if (SECTION === 'team') renderTeam();
    else if (SECTION === 'teams') renderTeamsIndex();
    else if (SECTION === 'odds') renderOdds();
  }).catch(function(e) {
    if (SECTION !== 'team' && SECTION !== 'teams') app.innerHTML = emptyNote('Couldn&rsquo;t load ' + esc(SPORT_SLUG) + ' data. Try reloading.');
    if (window.console) console.error(e);
  });
})();
