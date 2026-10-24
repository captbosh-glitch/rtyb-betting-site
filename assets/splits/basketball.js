/*
 * Shared NBA / WNBA Situational Results rows (assets/splits/nba.js and
 * wnba.js build their registries from this). Context fields: see
 * assets/situational.js. Favorite / underdog and spread buckets use the
 * closing full-game spread (c.fs, negative = favored); a pick'em is
 * neither. Times are ET.
 */
(function() {
  window.RTYB_BASKETBALL = function(o) {
    var C = { lossBy: 15, streak: 3, altitude: o.altitude || [] };
    function fav(c, lo, hi) { return c.fs != null && c.fs < 0 && -c.fs >= lo && -c.fs <= hi; }
    function dog(c, lo, hi) { return c.fs != null && c.fs > 0 && c.fs >= lo && c.fs <= hi; }
    function third(c, n) {
      if (c.segTotal == null || !c.cuts) return false;
      return n === 0 ? c.segTotal < c.cuts[0] : n === 1 ? c.segTotal >= c.cuts[0] && c.segTotal < c.cuts[1] : c.segTotal >= c.cuts[1];
    }
    function cutDef(n) {
      return function(C2, info) {
        var k = info.cuts;
        if (!k) return 'Not enough posted totals this season to split into thirds yet.';
        return ['Posted total under ' + k[0] + ' (bottom third this season).', 'Posted total ' + k[0] + ' to ' + (k[1] - 0.5) + ' (middle third).',
          'Posted total ' + k[1] + ' or higher (top third this season).'][n];
      };
    }
    var groups = [
      { id: 'ha', label: 'Home / Away / Favorite / Underdog',
        note: 'Away and Underdog rows are the mirror of Home and Favorite (W and L swapped, margin negated). Favorite / underdog by the closing full-game spread; a pick’em is neither.' },
      { id: 'opp', label: 'Opponent' }, { id: 'tip', label: 'Tip-off Window' }, { id: 'rest', label: 'Rest & Schedule' },
      { id: 'prev', label: 'Previous Game' }, { id: 'size', label: 'Total Size' },
    ];
    var rows = [
      { id: 'home', label: 'Home', short: 'Home', group: 'ha', own: true, def: 'Games as the home team.', test: function(c) { return c.home; } },
      { id: 'away', label: 'Away', short: 'Away', group: 'ha', own: true, def: 'Games as the road team.', test: function(c) { return !c.home; } },
      { id: 'fav', label: 'Favorite', short: 'Fav', group: 'ha', own: true, def: 'Favored by the closing full-game spread.', test: function(c) { return c.fav === true; } },
      { id: 'f1', label: 'Favorite by 1–3.5', short: 'Fav 1–3.5', group: 'ha', indent: 1, own: true, def: 'Favored by 1 to 3.5 points (full game).', test: function(c) { return fav(c, 0.5, 3.5); } },
      { id: 'f4', label: 'Favorite by 4–7.5', short: 'Fav 4–7.5', group: 'ha', indent: 1, own: true, def: 'Favored by 4 to 7.5 points (full game).', test: function(c) { return fav(c, 4, 7.5); } },
      { id: 'f8', label: 'Favorite by 8+', short: 'Fav 8+', group: 'ha', indent: 1, own: true, def: 'Favored by 8 or more points (full game).', test: function(c) { return fav(c, 8, 999); } },
      { id: 'dog', label: 'Underdog', short: 'Dog', group: 'ha', own: true, def: 'The underdog by the closing full-game spread.', test: function(c) { return c.fav === false; } },
      { id: 'd1', label: 'Underdog by 1–3.5', short: 'Dog 1–3.5', group: 'ha', indent: 1, own: true, def: 'Getting 1 to 3.5 points (full game).', test: function(c) { return dog(c, 0.5, 3.5); } },
      { id: 'd4', label: 'Underdog by 4–7.5', short: 'Dog 4–7.5', group: 'ha', indent: 1, own: true, def: 'Getting 4 to 7.5 points (full game).', test: function(c) { return dog(c, 4, 7.5); } },
      { id: 'd8', label: 'Underdog by 8+', short: 'Dog 8+', group: 'ha', indent: 1, own: true, def: 'Getting 8 or more points (full game).', test: function(c) { return dog(c, 8, 999); } },

      o.divisions ? { id: 'div', label: 'Division', short: 'Div', group: 'opp', def: 'Against a division rival.',
        test: function(c) { return c.ti && c.oi && c.ti.division && c.ti.division === c.oi.division; } } : null,
      { id: 'conf', label: 'Conference', short: 'Conf', group: 'opp', def: 'Against a team from the same conference.',
        test: function(c) { return c.ti && c.oi && c.ti.conference === c.oi.conference; } },
      o.eastWest ? { id: 'ew', label: 'East vs. West', short: 'E vs W', group: 'opp', def: 'Against the other conference.',
        test: function(c) { return c.ti && c.oi && c.ti.conference !== c.oi.conference; } } : null,
      { id: 'v500', label: 'Vs. teams at .500 or better', short: 'vs .500+', group: 'opp', def: 'The opponent was .500 or better going into the game (this season).',
        test: function(c) { return c.oppW + c.oppL > 0 && c.oppW >= c.oppL; } },
      { id: 'vsub', label: 'Vs. teams under .500', short: 'vs <.500', group: 'opp', def: 'The opponent was under .500 going into the game.',
        test: function(c) { return c.oppW + c.oppL > 0 && c.oppW < c.oppL; } },

      { id: 'aft', label: 'Afternoon', short: 'Afternoon', group: 'tip', def: 'Tip-off before 6:00 PM ET.', test: function(c) { return c.mins < 18 * 60; } },
      { id: 'early', label: 'Early night', short: 'Early night', group: 'tip', def: 'Tip-off 6:00 to 8:59 PM ET.', test: function(c) { return c.mins >= 18 * 60 && c.mins < 21 * 60; } },
      { id: 'late', label: 'Late', short: 'Late', group: 'tip', def: 'Tip-off at 9:00 PM ET or later.', test: function(c) { return c.mins >= 21 * 60; } },
      { id: 'tv', label: 'National TV', short: 'National TV', group: 'tip', def: 'On a national broadcast.', test: function(c) { return c.tvn; } },
      o.cup ? { id: 'cup', label: o.cup.label, short: o.cup.short, group: 'tip', def: o.cup.def, test: function(c) { return o.cup.re.test(c.note); } } : null,

      { id: 'b2b1', label: 'Back-to-back, 1st leg', short: 'B2B 1st leg', group: 'rest', own: true, def: 'The team plays again tomorrow.', test: function(c) { return c.b2bFirst; } },
      { id: 'b2b2', label: 'Back-to-back, 2nd leg', short: 'B2B 2nd leg', group: 'rest', own: true, def: 'The team played yesterday.', test: function(c) { return c.b2b; } },
      { id: 'ob2b', label: 'Opponent on 2nd leg of back-to-back', short: 'Opp on B2B', group: 'rest', own: true, def: 'The opponent played yesterday.', test: function(c) { return c.oppB2b; } },
      { id: 'three', label: '3 games in 4 nights', short: '3 in 4', group: 'rest', own: true, def: 'The team’s 3rd game within 4 days.', test: function(c) { return c.threeIn4; } },
      { id: 'radv', label: 'Rest advantage', short: 'Rest +', group: 'rest', own: true, def: 'More rest days than the opponent.', test: function(c) { return c.restDays != null && c.oppRestDays != null && c.restDays > c.oppRestDays; } },
      { id: 'rdis', label: 'Rest disadvantage', short: 'Rest −', group: 'rest', own: true, def: 'Fewer rest days than the opponent.', test: function(c) { return c.restDays != null && c.oppRestDays != null && c.restDays < c.oppRestDays; } },
      { id: 'reven', label: 'Even rest', short: 'Even rest', group: 'rest', def: 'Both teams had the same rest.', test: function(c) { return c.restDays != null && c.restDays === c.oppRestDays; } },
      { id: 'r2', label: '2+ days rest', short: '2+ days rest', group: 'rest', own: true, def: 'Two or more days off before the game.', test: function(c) { return c.restDays != null && c.restDays >= 2; } },
      { id: 'r4', label: 'After 4+ days off', short: '4+ days off', group: 'rest', own: true, def: 'Four or more days off before the game.', test: function(c) { return c.restDays != null && c.restDays >= 4; } },
      { id: 'trip3', label: '3rd+ game of a road trip', short: 'Road trip 3+', group: 'rest', own: true, def: 'At least the 3rd straight road game.', test: function(c) { return c.trip >= 3; } },
      { id: 'homeback', label: 'First home game after a road trip', short: 'Home from trip', group: 'rest', own: true, def: 'Home after two or more straight road games.', test: function(c) { return c.home && c.tripEnded >= 2; } },
      o.altitude ? { id: 'alt', label: 'At altitude', short: 'Altitude', group: 'rest', own: true, def: 'Road games in Denver or Utah.',
        test: function(c) { return !c.home && C.altitude.indexOf(c.g.home) !== -1; } } : null,

      { id: 'pw', label: 'After a win', short: 'Off W', group: 'prev', own: true, def: 'The team won its previous game.', test: function(c) { return c.prev && c.prev.res === 'W'; } },
      { id: 'pl', label: 'After a loss', short: 'Off L', group: 'prev', own: true, def: 'The team lost its previous game.', test: function(c) { return c.prev && c.prev.res === 'L'; } },
      { id: 'pl15', label: 'After a loss by 15+', short: 'Off L by 15+', group: 'prev', indent: 1, own: true, def: 'Lost its previous game by 15 or more.', test: function(c) { return c.prev && c.prev.pa - c.prev.pf >= C.lossBy; } },
      { id: 'pot', label: 'After an OT game', short: 'Off OT', group: 'prev', own: true, def: 'Its previous game went to overtime.', test: function(c) { return c.prev && c.prev.ot; } },
      { id: 'pseg', label: 'After losing the segment last game', short: 'Segment bounce', group: 'prev', own: true, def: 'Lost the same segment (1Q or 1H) last game.', test: function(c) { return c.prev && c.prev.segRes === 'L'; } },
      { id: 'ws', label: 'On a 3+ game win streak', short: 'W streak 3+', group: 'prev', own: true, def: 'Won its last 3 or more games.', test: function(c) { return c.streak >= C.streak; } },
      { id: 'ls', label: 'On a 3+ game losing streak', short: 'L streak 3+', group: 'prev', own: true, def: 'Lost its last 3 or more games.', test: function(c) { return c.streak <= -C.streak; } },

      { id: 'tlow', label: 'Low total', short: 'Low total', group: 'size', def: cutDef(0), test: function(c) { return third(c, 0); } },
      { id: 'tmid', label: 'Middle total', short: 'Mid total', group: 'size', def: cutDef(1), test: function(c) { return third(c, 1); } },
      { id: 'thigh', label: 'High total', short: 'High total', group: 'size', def: cutDef(2), test: function(c) { return third(c, 2); } },
    ].filter(Boolean);
    return { config: C, groups: groups, rows: rows, markets: [{ id: 'ats' }, { id: 'tot' }, { id: 'su' }], favBy: 'fg-spread', periods: 4,
             perspectives: [['home', 'Home team'], ['fav', 'Favorite']], defaultSeason: o.defaultSeason, smallSample: 10 };
  };
})();
