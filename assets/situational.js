/*
 * Situational Results: the split table every sport's Stats page uses (and
 * NFL / NCAAF team pages). Rows come from the sport's registry
 * (assets/splits/{sport}.js, window.RTYB_SPLITS[sport]); this file builds a
 * context `c` for every team-game in a segment and counts each row's games.
 *
 *   var sit = RTYBSit.create(src)
 *   sit.render(box, view)            view = {mode: 'league'} | {mode: 'team', slug}
 *   sit.contexts(k, 'current')       [{c, r}] for the team-page game log
 *   sit.tags(c)                      registry rows a team-game counts toward
 *
 * src: {sport, segments [{key, label, tag}], teams {slug: {name, conference,
 *   division}}, seasons: [{key: 'current', label, games: {date: [game]}},
 *   {key: 'prev', label, load: () => Promise<{date: [game]}>}], conf, rivals,
 *   tz {team: utc offset}, totalCuts {k: [lo, hi]}, locked, lockHtml, url}
 *
 * Games are in sport.js's shape: {id, start, state, away, home, as, hs,
 * als, hls, neutral, intl, note, post, wk, fs (home full-game spread),
 * fml {away, home}, tvn, ar, hr, ag / hg (NHL starting goalies),
 * firstGoal, ot, odds {k: {...}}, res {k: {sc, su, ats, tot, btts, u}}}.
 * res is from the away side; u[market] = [away units, home units]
 * ([over, under] / [yes, no]).
 *
 * Definitions (Chris's spec): rest days = days between games minus 1;
 * back-to-back = played the previous ET calendar day; 3 games in 4 nights =
 * 3rd game within a 4-day window ending today; road trip game number =
 * consecutive away games counting this one (a home game resets it); time
 * zones crossed = previous venue's zone vs this one (venue = home team);
 * previous game = the team's last game in the same season.
 */
(function() {
  'use strict';
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function flip(r) { return { W: 'L', L: 'W' }[r] || r; }
  function fmtU(u) { var r = Math.round(u * 100) / 100; return (r > 0 ? '+' : '') + r.toFixed(2) + 'u'; }
  function pill(u, n, prefix) {
    if (!n) return '<span class="u-pill u-none">&mdash;</span>';
    var r = Math.round(u * 100) / 100;
    var cls = r >= 3 ? 'u-pos2' : r > 0 ? 'u-pos1' : r === 0 ? 'u-zero' : r > -3 ? 'u-neg1' : 'u-neg2';
    return '<span class="u-pill ' + cls + '">' + (prefix || '') + fmtU(r) + '</span>';
  }
  var ET_FMT = null, DATE_FMT = null;
  function etParts(iso) {
    ET_FMT = ET_FMT || new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
    var o = {};
    ET_FMT.formatToParts(new Date(iso)).forEach(function(x) { o[x.type] = x.value; });
    return { dow: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(o.weekday), mins: (+o.hour % 24) * 60 + (+o.minute) };
  }
  function etDate(iso) { DATE_FMT = DATE_FMT || new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York' }); return DATE_FMT.format(new Date(iso)); }
  function dayDiff(a, b) { return Math.round((new Date(b + 'T12:00:00Z') - new Date(a + 'T12:00:00Z')) / 864e5); }
  function regWeek(g) { var m = /^2-(\d+)$/.exec(g.wk || ''); return m ? +m[1] : null; }
  function fbU(res) { return res === 'W' ? 0.9091 : res === 'L' ? -1 : 0; }   // -110 when only the line was saved
  function implied(p) { return p < 0 ? -p / (-p + 100) : 100 / (p + 100); }
  // favorite by a segment's own odds (moneyline, else the spread line)
  function segFav(o) {
    var ml = (o || {}).ml || {}, a = ml.away, h = ml.home;
    if (typeof a === 'number' && typeof h === 'number' && implied(a) !== implied(h)) return implied(a) > implied(h) ? 'away' : 'home';
    var line = (((o || {}).ats || {}).away || {}).line;
    if (typeof line === 'number' && line !== 0) return line < 0 ? 'away' : 'home';
    return null;
  }

  // Market definitions: how a result reads for a team-game and its units.
  var MARKETS = {
    su: { label: 'Moneyline', url: 'moneyline', head: 'W-L-T', pctHead: 'Win %' },
    ats: { label: 'Spread', url: 'spread', head: 'ATS W-L-P', pctHead: 'Cover %' },
    tot: { label: 'Total', url: 'total', head: 'O/U O-U-P', pctHead: 'Over %', pair: ['O', 'U'] },
    btts: { label: 'BTTS', url: 'btts', head: 'BTTS Y-N', pctHead: 'Yes %', pair: ['Y', 'N'] },
  };

  function create(src) {
    var REG = (window.RTYB_SPLITS || {})[src.sport];
    if (!REG) return null;
    var C = REG.config || {};
    var markets = (REG.markets || ['su', 'ats', 'tot']).map(function(m) {
      var id = typeof m === 'string' ? m : m.id;
      var base = MARKETS[id] || {};
      var o = {}; for (var x in base) o[x] = base[x];
      if (typeof m === 'object') for (var y in m) o[y] = m[y];
      o.id = id;
      return o;
    });
    var RIVAL = {};
    (src.rivals || []).forEach(function(p) { RIVAL[p[0] + '|' + p[1]] = RIVAL[p[1] + '|' + p[0]] = 1; });
    function isRival(a, b) { return !!RIVAL[a + '|' + b]; }
    var memberOf = null;
    function confOf(slug) {
      var m = (src.conf || {}).members;
      if (m) {
        if (!memberOf) { memberOf = {}; Object.keys(m).forEach(function(c) { m[c].forEach(function(s) { memberOf[s] = c; }); }); }
        return memberOf[slug] || null;
      }
      return (src.teams[slug] || {}).conference || null;
    }
    function isP4(slug) {
      var cf = src.conf || {}, c = confOf(slug);
      return (cf.power4 || []).indexOf(c) !== -1 || (cf.power4_teams || []).indexOf(slug) !== -1;
    }
    function isPower(slug) { return ((src.conf || {}).power || []).indexOf(confOf(slug)) !== -1; }
    function fgLine(g, side) { return g.fs == null ? null : side === 'home' ? g.fs : -g.fs; }
    // full-game favorite: by the registry's rule
    function fullFav(g, k) {
      if (REG.favBy === 'fg-ml') {
        var ml = g.fml || {};
        if (typeof ml.away !== 'number' || typeof ml.home !== 'number' || ml.away === ml.home) return null;
        return implied(ml.away) > implied(ml.home) ? 'away' : 'home';
      }
      if (REG.favBy === 'fg-spread') return g.fs ? (g.fs < 0 ? 'home' : 'away') : null;
      // football: the segment's own line, else the full-game spread
      return segFav((g.odds || {})[k]) || (g.fs ? (g.fs < 0 ? 'home' : 'away') : null);
    }

    var cache = {};
    // [{c, r}] for one season's games in segment k
    function seasonContexts(games, k, seasonKey) {
      var dates = Object.keys(games).sort();
      var byTeam = {};
      dates.forEach(function(d) {
        games[d].forEach(function(g) {
          if (g.state === 'postponed' || g.state === 'canceled') return;
          ['away', 'home'].forEach(function(side) { (byTeam[g[side]] = byTeam[g[side]] || []).push({ g: g, side: side, date: etDate(g.start) }); });
        });
      });
      var info = {};
      Object.keys(byTeam).forEach(function(slug) {
        var list = byTeam[slug].sort(function(a, b) { return a.g.start < b.g.start ? -1 : 1; });
        var w = 0, l = 0, streak = 0, trip = 0, starts = {};
        list.forEach(function(e, i) {
          var p = list[i - 1], n = list[i + 1], prev = null;
          if (p && p.g.state === 'final' && p.g.as != null && p.g.hs != null) {
            var pf = p.side === 'away' ? p.g.as : p.g.hs, pa = p.side === 'away' ? p.g.hs : p.g.as, pe = etParts(p.g.start);
            var pr = (p.g.res || {})[k];
            prev = { res: pf > pa ? 'W' : pf < pa ? 'L' : 'T', pf: pf, pa: pa, side: p.side, dow: pe.dow, mins: pe.mins,
                     ot: !!p.g.ot || Math.max((p.g.als || []).length, (p.g.hls || []).length) > (REG.periods || 4),
                     otType: typeof p.g.ot === 'string' ? p.g.ot : '', neutral: !!p.g.neutral,
                     fs: fgLine(p.g, p.side), rival: isRival(p.g.away, p.g.home),
                     scoredFirst: p.g.firstGoal ? p.g.firstGoal === p.side : null,
                     segRes: pr && pr.su ? (p.side === 'away' ? pr.su : flip(pr.su)) : null,
                     venue: p.g.home };
          }
          var three = 1;
          for (var j = i - 1; j >= 0 && dayDiff(list[j].date, e.date) <= 3; j--) three++;
          var mine = e.side === 'away' ? e.g.ag : e.g.hg;
          var top = null, best = 0;
          Object.keys(starts).forEach(function(id) { if (starts[id] > best) { best = starts[id]; top = id; } });
          info[e.g.id + '|' + slug] = {
            prev: prev, days: p ? dayDiff(p.date, e.date) : null, threeIn4: three >= 3,
            nextDays: n ? dayDiff(e.date, n.date) : null,
            prevWk: p ? regWeek(p.g) : null, nextWk: n ? regWeek(n.g) : null,
            next: n ? { rival: isRival(n.g.away, n.g.home), oppRank: n.side === 'away' ? n.g.hr : n.g.ar } : null,
            w: w, l: l, streak: streak,
            trip: e.side === 'away' ? trip + 1 : 0, tripEnded: e.side === 'home' ? trip : 0,
            goalie: mine ? mine.id : null, starter: mine ? (top == null || String(mine.id) === top) : null
          };
          // after this game: record, streak, road trip, goalie starts
          if (e.g.state === 'final' && e.g.as != null && e.g.hs != null) {
            var my = e.side === 'away' ? e.g.as : e.g.hs, th = e.side === 'away' ? e.g.hs : e.g.as;
            if (my > th) { w++; streak = streak > 0 ? streak + 1 : 1; } else if (my < th) { l++; streak = streak < 0 ? streak - 1 : -1; } else streak = 0;
          }
          trip = e.side === 'away' ? trip + 1 : 0;
          if (mine && mine.id != null) starts[mine.id] = (starts[mine.id] || 0) + 1;
        });
      });
      var out = [];
      dates.forEach(function(d) {
        games[d].forEach(function(g) {
          var r = (g.res || {})[k];
          if (!r || !r.sc || r.na) return;
          var fav = fullFav(g, k), et = etParts(g.start), o = (g.odds || {})[k] || {}, date = etDate(g.start);
          var segTotal = (o.total || {}).line;
          ['away', 'home'].forEach(function(side) {
            var team = g[side], opp = side === 'away' ? g.home : g.away, i = side === 'away' ? 0 : 1;
            var mi = info[g.id + '|' + team] || {}, oi = info[g.id + '|' + opp] || {};
            var fml = (g.fml || {})[side];
            var tzPrev = mi.prev && src.tz ? src.tz[mi.prev.venue] : null, tzNow = src.tz ? src.tz[g.home] : null;
            var c = { g: g, season: seasonKey, side: side, team: team, opp: opp, home: side === 'home', neutral: !!g.neutral, intl: g.intl,
              fav: fav ? fav === side : null, favMl: typeof fml === 'number' ? fml : null,
              dow: et.dow, mins: et.mins, month: +date.slice(5, 7), date: date,
              ti: src.teams[team] || null, oi: src.teams[opp] || null,
              wk: regWeek(g), prevWk: mi.prevWk, nextWk: mi.nextWk, prev: mi.prev, oppPrev: oi.prev, next: mi.next,
              rest: mi.days, oppRest: oi.days,
              restDays: mi.days == null ? null : mi.days - 1, oppRestDays: oi.days == null ? null : oi.days - 1,
              b2b: mi.days === 1, b2bFirst: mi.nextDays === 1, oppB2b: oi.days === 1,
              threeIn4: !!mi.threeIn4, trip: mi.trip || 0, tripEnded: mi.tripEnded || 0,
              tzCrossed: tzPrev != null && tzNow != null ? Math.abs(tzPrev - tzNow) : null,
              w: mi.w || 0, l: mi.l || 0, streak: mi.streak || 0, oppW: oi.w || 0, oppL: oi.l || 0,
              rank: side === 'away' ? g.ar : g.hr, oppRank: side === 'away' ? g.hr : g.ar,
              fs: fgLine(g, side), segTotal: typeof segTotal === 'number' ? segTotal : null, cuts: (src.totalCuts || {})[k] || null,
              tvn: !!g.tvn, note: g.note || '', post: !!g.post,
              goalie: mi.goalie, starter: mi.starter,
              teamConf: confOf(team), oppConf: confOf(opp), oppFcs: !src.teams[opp], oppP4: isP4(opp),
              teamPower: isPower(team), oppPower: isPower(opp), rival: isRival(g.away, g.home) };
            var res = { margin: r.sc[i] - r.sc[1 - i], lined: !!(o.ats || o.total || o.ml || o.btts) };
            var u = r.u || {};
            if (r.su && r.su !== 'NA') {
              res.su = side === 'away' ? r.su : flip(r.su);
              if (res.su === 'P') res.su = 'T';
              res.suU = u.su ? u.su[i] : null;
            }
            if (r.ats && r.ats !== 'NA') {
              res.ats = side === 'away' ? r.ats : flip(r.ats);
              res.atsU = u.ats ? u.ats[i] : fbU(res.ats === 'P' ? 'T' : res.ats);
            }
            if (r.tot && r.tot !== 'NA') {
              res.tot = r.tot;
              res.totA = u.tot ? u.tot[0] : (o.total ? fbU({ O: 'W', U: 'L' }[r.tot]) : null);
              res.totB = u.tot ? u.tot[1] : (o.total ? fbU({ O: 'L', U: 'W' }[r.tot]) : null);
            }
            if (r.btts) {
              res.btts = r.btts;
              res.bttsA = u.btts ? u.btts[0] : null;
              res.bttsB = u.btts ? u.btts[1] : null;
            }
            out.push({ c: c, r: res });
          });
        });
      });
      return out;
    }
    function contexts(k, mode) {
      var key = k + '|' + mode;
      if (cache[key]) return cache[key];
      var out = [];
      src.seasons.forEach(function(s) {
        if (s.key === 'prev' && mode !== 'since') return;
        if (!s.games) return;
        out = out.concat(seasonContexts(s.games, k, s.key));
      });
      return (cache[key] = out);
    }

    function agg(list) {
      var a = { gp: 0, marg: 0, lined: 0 };
      markets.forEach(function(m) { a[m.id] = { a: 0, b: 0, p: 0, n: 0, ua: 0, ub: 0, na: 0, nb: 0 }; });
      list.forEach(function(e) {
        var r = e.r;
        a.gp++; a.marg += r.margin; if (r.lined) a.lined++;
        markets.forEach(function(m) {
          var x = a[m.id], v = r[m.id];
          if (v == null) return;
          x.n++;
          if (m.pair) {
            if (v === m.pair[0]) x.a++; else if (v === m.pair[1]) x.b++; else x.p++;
            var ua = r[m.id + 'A'], ub = r[m.id + 'B'];
            if (ua != null) { x.ua += ua; x.na++; }
            if (ub != null) { x.ub += ub; x.nb++; }
          } else {
            if (v === 'W') x.a++; else if (v === 'L') x.b++; else x.p++;
            var u = r[m.id + 'U'];
            if (u != null) { x.ua += u; x.na++; }
          }
        });
      });
      return a;
    }
    function table(k, view, mode) {
      var all = contexts(k, mode);
      var pool = view.mode === 'team' ? all.filter(function(e) { return e.c.team === view.slug && e.c.season === 'current'; })
        : view.conf ? all.filter(function(e) { return e.c.teamConf === view.conf; }) : all;
      return REG.groups.map(function(gr) {
        var rows = [], hidden = [];
        REG.rows.forEach(function(row) {
          if (row.group !== gr.id) return;
          if (view.mode === 'league' && row.teamOnly) return;
          if (view.mode === 'team' && row.applies && !row.applies(view.slug, C)) return;
          var list = pool.filter(function(e) {
            if (view.mode === 'league' && !row.own && !view.conf) {
              if (view.persp === 'fav' ? e.c.fav !== true : !e.c.home) return false;
            }
            return !!row.test(e.c, C);
          });
          var a = agg(list);
          if (view.mode === 'team' && !a.gp) hidden.push(row); else rows.push({ row: row, agg: a });
        });
        return { group: gr, rows: rows, hidden: hidden };
      }).filter(function(x) { return x.rows.length || view.mode === 'league'; });
    }
    function tags(c) {
      var skip = { overall: 1, home: 1, away: 1 }, out = [], rows = REG.rows;
      rows.forEach(function(row, i) {
        if (skip[row.id] || row.teamOnly || !row.test(c, C)) return;
        if (row.applies && !row.applies(c.team, C)) return;
        if (!row.indent) { for (var j = i + 1; j < rows.length && rows[j].indent; j++) if (rows[j].test(c, C)) return; }
        out.push(row.short);
      });
      return out;
    }

    // ---- state, URL ----
    var st = { k: null, market: null, season: REG.defaultSeason || 'current', persp: 'home', conf: '', mob: null };
    var prevSeason = src.seasons.filter(function(s) { return s.key === 'prev'; })[0];
    var sinceUrl = prevSeason ? 'since-' + String(prevSeason.season || prevSeason.label).slice(0, 4) : 'since';
    if (!prevSeason) st.season = 'current';
    if (src.url) {
      try {
        var q = new URLSearchParams(window.location.search);
        if (q.get('segment')) st.k = q.get('segment');
        if (q.get('market')) markets.forEach(function(m) { if (m.url === q.get('market')) st.market = m.id; });
        if (q.get('season')) st.season = q.get('season') === 'current' ? 'current' : (prevSeason ? 'since' : 'current');
      } catch (e) {}
    }
    function saveUrl() {
      if (!src.url) return;
      try {
        var u = new URL(window.location.href);
        if (src.segments.length > 1) u.searchParams.set('segment', st.k);
        u.searchParams.set('market', (markets.filter(function(m) { return m.id === st.market; })[0] || markets[0]).url);
        if (prevSeason) u.searchParams.set('season', st.season === 'since' ? sinceUrl : 'current');
        history.replaceState(null, '', u.toString());
      } catch (e) {}
    }

    function render(box, view) {
      if (!box) return;
      var k = st.k && src.segments.some(function(s) { return s.key === st.k; }) ? st.k : src.segments[0].key;
      st.k = k;
      if (!st.market || !markets.some(function(m) { return m.id === st.market; })) st.market = markets[0].id;
      var mode = view.mode === 'league' ? st.season : 'current';
      if (mode === 'since' && prevSeason && !prevSeason.games) {
        box.innerHTML = '<div class="season-card sit"><div class="sit-loading">Loading ' + esc(prevSeason.label) + '&hellip;</div></div>';
        prevSeason.load().then(function(g) { prevSeason.games = g || {}; cache = {}; render(box, view); },
          function() { prevSeason.games = {}; render(box, view); });
        return;
      }
      var conf = view.mode === 'league' && REG.conferences ? st.conf : '';
      var v = view.mode === 'league' ? { mode: 'league', persp: st.persp, conf: conf } : view;
      var groups = table(k, v, mode);
      var all = contexts(k, mode);
      var gp = view.mode === 'team' ? all.filter(function(e) { return e.c.team === view.slug && e.c.season === 'current'; }).length
        : conf ? all.filter(function(e) { return e.c.teamConf === conf; }).length : all.length / 2;
      var confShort = conf ? (((src.conf || {}).short || {})[conf] || conf) : '';
      var who = view.mode !== 'league' ? '' : conf ? 'as ' + confShort + ' teams' : 'as ' + (st.persp === 'fav' ? 'favorite' : 'home team');
      var sel = markets.filter(function(m) { return m.id === st.market; })[0];
      var order = [sel].concat(markets.filter(function(m) { return m !== sel; }));
      var segLabel = src.segments.length > 1 ? '' : '<span class="sit-seglabel">' + esc(src.segments[0].label) + '</span>';

      // controls
      var ctl = '';
      if (src.segments.length > 1) ctl += '<div class="seg-toggle" role="group" aria-label="Segment">' + src.segments.map(function(s) {
        return '<button class="seg-btn" data-sit-seg="' + s.key + '" aria-pressed="' + (s.key === k) + '">' + esc(s.label) + '</button>'; }).join('') + '</div>';
      if (markets.length > 1) ctl += '<div class="seg-toggle" role="group" aria-label="Market">' + markets.map(function(m) {
        return '<button class="seg-btn" data-sit-mk="' + m.id + '" aria-pressed="' + (m.id === st.market) + '">' + esc(m.label) + '</button>'; }).join('') + '</div>';
      if (view.mode === 'league' && prevSeason) ctl += '<select class="conf-select" data-sit-season aria-label="Season">' +
        '<option value="current"' + (mode === 'current' ? ' selected' : '') + '>This season</option>' +
        '<option value="since"' + (mode === 'since' ? ' selected' : '') + '>Since ' + esc(prevSeason.label) + '</option></select>';
      if (view.mode === 'league' && REG.conferences) ctl += '<select class="conf-select" data-sit-conf aria-label="Conference"><option value="">' + esc(REG.allLabel || 'All') + '</option>' +
        REG.conferences.map(function(c) { return '<option value="' + esc(c) + '"' + (c === conf ? ' selected' : '') + '>' + esc(((src.conf || {}).short || {})[c] || c) + '</option>'; }).join('') + '</select>';
      if (view.mode === 'league' && !conf && REG.perspectives) ctl += '<div class="seg-toggle sit-persp" role="group" aria-label="View as"><span class="control-label">View as</span>' +
        REG.perspectives.map(function(p) { return '<button class="seg-btn" data-sit-persp="' + p[0] + '" aria-pressed="' + (st.persp === p[0]) + '">' + p[1] + '</button>'; }).join('') + '</div>';
      var seasonTxt = mode === 'since' ? 'Since ' + esc(prevSeason.label) : esc(src.seasons[0].label) + ' season';
      var head = '<div class="season-card-head"><h3>Situational Results' + segLabel + '</h3><div class="sc-right">' + ctl +
        '<span class="sc-gp">' + seasonTxt + ' &middot; ' + gp + ' GP</span></div></div>';

      function recTxt(m, x) { return x.n ? x.a + '-' + x.b + (m.pair ? (x.p ? '-' + x.p : '') : '-' + x.p) : '&mdash;'; }
      function pctOf(m, x) { var d = x.a + x.b; return d ? Math.round(100 * x.a / d) : null; }
      function unitsOf(m, x) {
        if (!m.pair) return pill(x.ua, x.na);
        if (!x.na && !x.nb) return pill(0, 0);
        if (REG.pairUnits === 'both') return '<span class="sit-both">' + pill(x.ua, x.na, m.pair[0] + ' ') + pill(x.ub, x.nb, m.pair[1] + ' ') + '</span>';
        var useA = x.na && (!x.nb || x.ua >= x.ub);
        return pill(useA ? x.ua : x.ub, useA ? x.na : x.nb, (useA ? m.pair[0] : m.pair[1]) + ' ');
      }
      function marg(a) { if (!a.gp) return '&mdash;'; var mm = Math.round(10 * a.marg / a.gp) / 10; return (mm > 0 ? '+' : '') + mm.toFixed(1); }
      function desc(row) {
        var d = typeof row.def === 'function' ? row.def(C, { cuts: (src.totalCuts || {})[k] }) : row.def;
        return d;
      }
      function labelCell(row, a) {
        return '<td class="sit-label' + (row.indent ? ' ind' : '') + '"><span class="sit-name">' + esc(row.label) + '</span>' +
          (a.gp && a.gp < (REG.smallSample || 10) ? ' <span class="sit-small">Small sample</span>' : '') +
          '<span class="sit-desc">' + esc(desc(row)) + (who && (conf || !row.own) ? ' &middot; ' + who : '') + '</span></td>';
      }
      function cells(row, a) {
        var x0 = a[sel.id], p = pctOf(sel, x0), cov = a.gp ? a.lined / a.gp : 0;
        var h = labelCell(row, a) + '<td class="num mono' + (a.gp && a.gp < 5 ? ' amber' : '') + '">' + (a.gp || '&mdash;') + '</td>' +
          '<td class="num mono sit-sel">' + recTxt(sel, x0) + '</td>' +
          '<td class="num"><div class="pct-cell"><div class="pct-bar"><span style="width:' + (p || 0) + '%"></span></div><span class="pct-num mono">' + (p == null ? '&mdash;' : p + '%') + '</span></div></td>' +
          '<td class="num">' + unitsOf(sel, x0) + '</td>';
        order.slice(1).forEach(function(m) { var x = a[m.id]; h += '<td class="num mono">' + recTxt(m, x) + '</td><td class="num">' + unitsOf(m, x) + '</td>'; });
        return h + '<td class="num mono">' + marg(a) + '</td>' +
          '<td class="num mono' + (a.gp && cov < 0.8 ? ' amber' : '') + '">' + (a.gp ? a.lined + '/' + a.gp : '&mdash;') + '</td>';
      }
      var ncol = 6 + 2 * (order.length - 1) + 2;
      var thead = '<tr><th class="sit-label">Split</th><th class="num">GP</th><th class="num">' + esc(sel.head) + '</th><th class="num">' + esc(sel.pctHead) +
        '</th><th class="num">Units</th>' + order.slice(1).map(function(m) { return '<th class="num">' + esc(m.head) + '</th><th class="num">' + esc(m.label) + ' Units</th>'; }).join('') +
        '<th class="num">Avg Margin</th><th class="num">Odds</th></tr>';
      var body = groups.map(function(G) {
        // the title sits in the pinned first column; the rest of the row is filler
        return '<tr class="sit-group"><td class="sit-label">' + esc(G.group.label) +
            (view.mode === 'league' && !conf && G.group.note ? '<div class="sit-note">' + esc(G.group.note) + '</div>' : '') + '</td>' +
            '<td colspan="' + (ncol - 1) + '"></td></tr>' +
          G.rows.map(function(x) { return '<tr>' + cells(x.row, x.agg) + '</tr>'; }).join('') +
          (G.hidden.length ? '<tr class="sit-notyet"><td colspan="' + ncol + '">Not yet: ' + G.hidden.map(function(r) { return esc(r.label); }).join(' &middot; ') + '</td></tr>' : '');
      }).join('');
      var tableHtml = '<div class="sit-desk' + (REG.mobileList ? '' : ' sit-scroll') + '"><div class="sit-wrap"><table class="sit-table"><thead>' + thead + '</thead><tbody>' + body + '</tbody></table></div></div>';

      // phone list (football)
      var mob = '';
      if (REG.mobileList) {
        mob = '<div class="sit-mob">' + groups.map(function(G) {
          return '<div class="sit-mgroup"><div class="sit-mtitle">' + esc(G.group.label) + '</div>' +
            (view.mode === 'league' && !conf && G.group.note ? '<div class="sit-note">' + esc(G.group.note) + '</div>' : '') +
            G.rows.map(function(x) {
              var a = x.agg, x0 = a[sel.id], p = pctOf(sel, x0);
              return '<details class="sit-mrow"><summary><span class="sit-mlabel' + (x.row.indent ? ' ind' : '') + '">' + esc(x.row.short) +
                  (a.gp && a.gp < (REG.smallSample || 10) ? ' <span class="sit-small">Small</span>' : '') +
                  (who && (conf || !x.row.own) ? '<span class="sit-who">' + who + '</span>' : '') + '</span>' +
                '<span class="mono sit-mrec">' + recTxt(sel, x0) + '</span><span class="sit-mval">' + (sel.id === 'su' ? '<span class="mono">' + (p == null ? '&mdash;' : p + '%') + '</span>' : unitsOf(sel, x0)) +
                '</span><span class="sit-chev" aria-hidden="true">&#9662;</span></summary>' +
                '<div class="sit-mbody"><p>' + esc(desc(x.row)) + '</p>' +
                  '<div class="pct-cell"><div class="pct-bar"><span style="width:' + (p || 0) + '%"></span></div><span class="pct-num mono">' + (p == null ? '&mdash;' : p + '%') + '</span></div>' +
                  '<div class="sit-m3">' + markets.map(function(m) { var xx = a[m.id]; return '<div><b>' + esc(m.label) + '</b><span class="mono">' + recTxt(m, xx) + '</span>' + unitsOf(m, xx) + '</div>'; }).join('') +
                  '<div><b>Margin</b><span class="mono">' + marg(a) + '</span></div></div>' +
                  '<div class="sit-mfoot' + (a.gp < 5 || (a.gp && a.lined / a.gp < 0.8) ? ' amber' : '') + '">' + a.gp + ' game' + (a.gp === 1 ? '' : 's') + ' &middot; ' + a.lined + ' with closing lines</div></div></details>';
            }).join('') +
            (G.hidden.length ? '<div class="sit-notyet">Not yet: ' + G.hidden.map(function(r) { return esc(r.short); }).join(' &middot; ') + '</div>' : '') + '</div>';
        }).join('') + '</div>';
      }
      var locked = view.mode === 'league' && src.locked && src.locked();
      box.className = 'adv-section' + (locked ? ' locked' : '');
      box.innerHTML = '<div class="season-card sit">' + head + tableHtml + mob +
        '<div class="sit-foot">' + esc(REG.foot || 'Records count every game; units count only games with saved closing odds, 1 unit at the closing price (spreads and totals at -110 when only the line was saved). Small sample under ' + (REG.smallSample || 10) + ' games; GP in amber under 5; Odds in amber under 80% coverage.') + '</div></div>' +
        (locked && src.lockHtml ? src.lockHtml() : '');
      function on(sel2, ev, fn) { box.querySelectorAll(sel2).forEach(function(el) { el['on' + ev] = function() { fn(el); saveUrl(); render(box, view); }; }); }
      on('[data-sit-seg]', 'click', function(b) { st.k = b.getAttribute('data-sit-seg'); });
      on('[data-sit-mk]', 'click', function(b) { st.market = b.getAttribute('data-sit-mk'); });
      on('[data-sit-persp]', 'click', function(b) { st.persp = b.getAttribute('data-sit-persp'); });
      on('[data-sit-season]', 'change', function(s) { st.season = s.value; });
      on('[data-sit-conf]', 'change', function(s) { st.conf = s.value; });
    }
    return { render: render, contexts: function(k, mode) { return contexts(k, mode || 'current'); }, tags: tags, reg: REG, state: st };
  }
  window.RTYBSit = { create: create, etParts: etParts };
})();
