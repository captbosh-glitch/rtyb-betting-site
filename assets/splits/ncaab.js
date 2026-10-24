/*
 * NCAAB Situational Results registry: 1st Half only (two halves, no
 * quarters). Context fields: see assets/situational.js. Favorite /
 * underdog by the closing full-game spread; AP Top 25 at game time; power
 * conferences from data_seed/conferences/ncaab/{season}.json (editable).
 */
(function() {
  var C = { lossBy: 15, streak: 3 };
  function fav(c, lo, hi) { return c.fs != null && c.fs < 0 && -c.fs >= lo && -c.fs <= hi; }
  function dog(c, lo, hi) { return c.fs != null && c.fs > 0 && c.fs >= lo && c.fs <= hi; }
  function ranked(r) { return r != null; }
  function confTourney(c) { return c.month === 3 && /Tournament|Championship/i.test(c.note) && !/NCAA Men|NIT|Crown/i.test(c.note); }
  function third(c, n) {
    if (c.segTotal == null || !c.cuts) return false;
    return n === 0 ? c.segTotal < c.cuts[0] : n === 1 ? c.segTotal >= c.cuts[0] && c.segTotal < c.cuts[1] : c.segTotal >= c.cuts[1];
  }
  function cutDef(n) {
    return function(C2, info) {
      var k = info.cuts;
      if (!k) return 'Not enough posted 1H totals this season to split into thirds yet.';
      return ['Posted 1H total under ' + k[0] + ' (bottom third this season).', 'Posted 1H total ' + k[0] + ' to ' + (k[1] - 0.5) + ' (middle third).',
        'Posted 1H total ' + k[1] + ' or higher (top third this season).'][n];
    };
  }
  var groups = [
    { id: 'ha', label: 'Home / Away / Favorite / Underdog',
      note: 'Away and Underdog rows are the mirror of Home and Favorite (W and L swapped, margin negated). Home + Away + Neutral = every game.' },
    { id: 'opp', label: 'Opponent' }, { id: 'tip', label: 'Tip-off Window' }, { id: 'rest', label: 'Rest & Schedule' },
    { id: 'prev', label: 'Previous Game' }, { id: 'size', label: 'Total Size' },
  ];
  var rows = [
    { id: 'home', label: 'Home', short: 'Home', group: 'ha', own: true, def: 'Games as the home team (not neutral site).', test: function(c) { return c.home && !c.neutral; } },
    { id: 'away', label: 'Away', short: 'Away', group: 'ha', own: true, def: 'Games as the road team (not neutral site).', test: function(c) { return !c.home && !c.neutral; } },
    { id: 'neutral', label: 'Neutral site', short: 'Neutral', group: 'ha', def: 'Tournaments and other neutral-site games.', test: function(c) { return c.neutral; } },
    { id: 'fav', label: 'Favorite', short: 'Fav', group: 'ha', own: true, def: 'Favored by the closing full-game spread.', test: function(c) { return c.fav === true; } },
    { id: 'f1', label: 'Favorite by 1–4.5', short: 'Fav 1–4.5', group: 'ha', indent: 1, own: true, def: 'Favored by 1 to 4.5 points.', test: function(c) { return fav(c, 0.5, 4.5); } },
    { id: 'f5', label: 'Favorite by 5–9.5', short: 'Fav 5–9.5', group: 'ha', indent: 1, own: true, def: 'Favored by 5 to 9.5 points.', test: function(c) { return fav(c, 5, 9.5); } },
    { id: 'f10', label: 'Favorite by 10–14.5', short: 'Fav 10–14.5', group: 'ha', indent: 1, own: true, def: 'Favored by 10 to 14.5 points.', test: function(c) { return fav(c, 10, 14.5); } },
    { id: 'f15', label: 'Favorite by 15+', short: 'Fav 15+', group: 'ha', indent: 1, own: true, def: 'Favored by 15 or more points.', test: function(c) { return fav(c, 15, 999); } },
    { id: 'dog', label: 'Underdog', short: 'Dog', group: 'ha', own: true, def: 'The underdog by the closing full-game spread.', test: function(c) { return c.fav === false; } },
    { id: 'd1', label: 'Underdog by 1–4.5', short: 'Dog 1–4.5', group: 'ha', indent: 1, own: true, def: 'Getting 1 to 4.5 points.', test: function(c) { return dog(c, 0.5, 4.5); } },
    { id: 'd5', label: 'Underdog by 5–9.5', short: 'Dog 5–9.5', group: 'ha', indent: 1, own: true, def: 'Getting 5 to 9.5 points.', test: function(c) { return dog(c, 5, 9.5); } },
    { id: 'd10', label: 'Underdog by 10–14.5', short: 'Dog 10–14.5', group: 'ha', indent: 1, own: true, def: 'Getting 10 to 14.5 points.', test: function(c) { return dog(c, 10, 14.5); } },
    { id: 'd15', label: 'Underdog by 15+', short: 'Dog 15+', group: 'ha', indent: 1, own: true, def: 'Getting 15 or more points.', test: function(c) { return dog(c, 15, 999); } },

    { id: 'conf', label: 'Conference', short: 'Conf', group: 'opp', def: 'Against a conference opponent (including the conference tournament).', test: function(c) { return c.teamConf && c.teamConf === c.oppConf; } },
    { id: 'nonconf', label: 'Non-conference', short: 'Non-conf', group: 'opp', def: 'Against a team outside the conference.', test: function(c) { return !(c.teamConf && c.teamConf === c.oppConf); } },
    { id: 'rvu', label: 'Ranked vs. unranked', short: 'Rk vs unrk', group: 'opp', own: true, def: 'A ranked team (AP Top 25 at game time) against an unranked one.', test: function(c) { return ranked(c.rank) && !ranked(c.oppRank); } },
    { id: 'uvr', label: 'Unranked vs. ranked', short: 'Unrk vs rk', group: 'opp', own: true, def: 'An unranked team against a ranked one.', test: function(c) { return !ranked(c.rank) && ranked(c.oppRank); } },
    { id: 'rvr', label: 'Ranked vs. ranked', short: 'Rk vs rk', group: 'opp', def: 'Both teams in the AP Top 25 at game time.', test: function(c) { return ranked(c.rank) && ranked(c.oppRank); } },
    { id: 'pvm', label: 'Power conference vs. mid-major', short: 'Power vs mid', group: 'opp', own: true, def: 'A power-conference team against a mid-major.', test: function(c) { return c.teamPower && !c.oppPower && !c.oppFcs; } },
    { id: 'mvp', label: 'Mid-major vs. power conference', short: 'Mid vs power', group: 'opp', own: true, def: 'A mid-major against a power-conference team.', test: function(c) { return !c.teamPower && c.oppPower && !c.oppFcs; } },

    { id: 'wkday', label: 'Weekday', short: 'Weekday', group: 'tip', def: 'Monday through Friday.', test: function(c) { return c.dow >= 1 && c.dow <= 5; } },
    { id: 'sat', label: 'Saturday', short: 'Saturday', group: 'tip', def: 'Saturday games.', test: function(c) { return c.dow === 6; } },
    { id: 'sun', label: 'Sunday', short: 'Sunday', group: 'tip', def: 'Sunday games.', test: function(c) { return c.dow === 0; } },
    { id: 'aft', label: 'Afternoon', short: 'Afternoon', group: 'tip', def: 'Tip-off before 6:00 PM ET.', test: function(c) { return c.mins < 18 * 60; } },
    { id: 'night', label: 'Night', short: 'Night', group: 'tip', def: 'Tip-off at 6:00 PM ET or later.', test: function(c) { return c.mins >= 18 * 60; } },

    { id: 'r4', label: 'After 4+ days off', short: '4+ days off', group: 'rest', own: true, def: 'Four or more days off before the game.', test: function(c) { return c.restDays != null && c.restDays >= 4; } },
    { id: 'g2in3', label: '2nd game in 3 days', short: '2nd in 3 days', group: 'rest', own: true, def: 'Played within the last two days (tournament and holiday stretches).', test: function(c) { return c.restDays != null && c.restDays <= 1; } },
    { id: 'nov', label: 'November tournaments and neutral-site events', short: 'Neutral events', group: 'rest', def: 'Regular-season neutral-site games (multi-team events, showcases).', test: function(c) { return c.neutral && !c.post && !confTourney(c) && !/NCAA Men|NIT|Crown/i.test(c.note); } },
    { id: 'ctour', label: 'Conference tournament games', short: 'Conf tourney', group: 'rest', def: 'Conference tournament games in March.', test: function(c) { return confTourney(c); } },
    { id: 'march', label: 'March games', short: 'March', group: 'rest', def: 'Every game played in March.', test: function(c) { return c.month === 3; } },

    { id: 'pw', label: 'After a win', short: 'Off W', group: 'prev', own: true, def: 'The team won its previous game.', test: function(c) { return c.prev && c.prev.res === 'W'; } },
    { id: 'pl', label: 'After a loss', short: 'Off L', group: 'prev', own: true, def: 'The team lost its previous game.', test: function(c) { return c.prev && c.prev.res === 'L'; } },
    { id: 'pl15', label: 'After a loss by 15+', short: 'Off L by 15+', group: 'prev', indent: 1, own: true, def: 'Lost its previous game by 15 or more.', test: function(c) { return c.prev && c.prev.pa - c.prev.pf >= C.lossBy; } },
    { id: 'pseg', label: 'After losing the 1st half last game', short: '1H bounce', group: 'prev', own: true, def: 'Trailed at the half last game.', test: function(c) { return c.prev && c.prev.segRes === 'L'; } },
    { id: 'ws', label: 'On a 3+ game win streak', short: 'W streak 3+', group: 'prev', own: true, def: 'Won its last 3 or more games.', test: function(c) { return c.streak >= C.streak; } },
    { id: 'ls', label: 'On a 3+ game losing streak', short: 'L streak 3+', group: 'prev', own: true, def: 'Lost its last 3 or more games.', test: function(c) { return c.streak <= -C.streak; } },

    { id: 'tlow', label: 'Low 1H total', short: 'Low total', group: 'size', def: cutDef(0), test: function(c) { return third(c, 0); } },
    { id: 'tmid', label: 'Middle 1H total', short: 'Mid total', group: 'size', def: cutDef(1), test: function(c) { return third(c, 1); } },
    { id: 'thigh', label: 'High 1H total', short: 'High total', group: 'size', def: cutDef(2), test: function(c) { return third(c, 2); } },
  ];
  window.RTYB_SPLITS = window.RTYB_SPLITS || {};
  window.RTYB_SPLITS.ncaab = { config: C, groups: groups, rows: rows, markets: [{ id: 'ats' }, { id: 'tot' }, { id: 'su' }], favBy: 'fg-spread', periods: 2,
    perspectives: [['home', 'Home team'], ['fav', 'Favorite']], smallSample: 10 };
})();
