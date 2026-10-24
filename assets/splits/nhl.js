/*
 * NHL Situational Results registry (Stats page). Markets: 1st-period
 * Moneyline, Over 1.5 and BTTS; a tied 1st period is a push on the
 * moneyline (0 units). Favorite / underdog by the closing full-game
 * moneyline (ESPN); a pick'em is neither. Times are ET. Rows marked `own`
 * count each team-game from that team's side (so "After a loss" counts
 * every team coming off a loss, as the old Bounce-Back card did); the rest
 * use "View as" (home team by default).
 */
(function() {
  var C = { heavy: -200, scored: 5, lossBy: 3 };
  var groups = [
    { id: 'ha', label: 'Home / Away / Favorite / Underdog',
      note: 'Away and Underdog rows are the mirror of Home and Favorite (W and L swapped, margin negated). Favorite / underdog by the closing full-game moneyline; a pick’em is neither.' },
    { id: 'opp', label: 'Opponent' }, { id: 'drop', label: 'Puck Drop Window' }, { id: 'rest', label: 'Rest & Schedule' },
    { id: 'prev', label: 'Previous Game' }, { id: 'goalie', label: 'Goalie' },
  ];
  function lost(p) { return p && p.res === 'L'; }
  var rows = [
    { id: 'home', label: 'Home', short: 'Home', group: 'ha', own: true, def: 'Games as the home team.', test: function(c) { return c.home; } },
    { id: 'away', label: 'Away', short: 'Away', group: 'ha', own: true, def: 'Games as the road team.', test: function(c) { return !c.home; } },
    { id: 'fav', label: 'Favorite', short: 'Fav', group: 'ha', own: true, def: 'Favored by the closing full-game moneyline.', test: function(c) { return c.fav === true; } },
    { id: 'heavy', label: 'Heavy favorite', short: 'Heavy fav', group: 'ha', indent: 1, own: true, def: 'Closing moneyline -200 or shorter.', test: function(c) { return c.fav === true && c.favMl != null && c.favMl <= C.heavy; } },
    { id: 'small', label: 'Small favorite', short: 'Small fav', group: 'ha', indent: 1, own: true, def: 'Closing moneyline -199 to -101.', test: function(c) { return c.fav === true && c.favMl != null && c.favMl > C.heavy && c.favMl <= -101; } },
    { id: 'dog', label: 'Underdog', short: 'Dog', group: 'ha', own: true, def: 'The underdog by the closing full-game moneyline.', test: function(c) { return c.fav === false; } },

    { id: 'div', label: 'Division', short: 'Div', group: 'opp', def: 'Against a division rival.', test: function(c) { return c.ti && c.oi && c.ti.division === c.oi.division; } },
    { id: 'conf', label: 'Conference', short: 'Conf', group: 'opp', def: 'Same conference, other division.', test: function(c) { return c.ti && c.oi && c.ti.conference === c.oi.conference && c.ti.division !== c.oi.division; } },
    { id: 'nonconf', label: 'Non-conference', short: 'Non-conf', group: 'opp', def: 'Against the other conference.', test: function(c) { return c.ti && c.oi && c.ti.conference !== c.oi.conference; } },

    { id: 'mat', label: 'Matinee', short: 'Matinee', group: 'drop', def: 'Puck drop before 5:00 PM ET.', test: function(c) { return c.mins < 17 * 60; } },
    { id: 'early', label: 'Early', short: 'Early', group: 'drop', def: 'Puck drop 5:00 to 7:59 PM ET.', test: function(c) { return c.mins >= 17 * 60 && c.mins < 20 * 60; } },
    { id: 'late', label: 'Late', short: 'Late', group: 'drop', def: 'Puck drop 8:00 to 9:59 PM ET.', test: function(c) { return c.mins >= 20 * 60 && c.mins < 22 * 60; } },
    { id: 'west', label: 'West Coast late', short: 'West late', group: 'drop', def: 'Puck drop at 10:00 PM ET or later.', test: function(c) { return c.mins >= 22 * 60; } },

    { id: 'rested', label: 'Rested', short: 'Rested', group: 'rest', own: true, def: 'More rest days than the opponent (the old Rest Edge card).', test: function(c) { return c.restDays != null && c.oppRestDays != null && c.restDays > c.oppRestDays; } },
    { id: 'tired', label: 'Tired', short: 'Tired', group: 'rest', own: true, def: 'Fewer rest days than the opponent.', test: function(c) { return c.restDays != null && c.oppRestDays != null && c.restDays < c.oppRestDays; } },
    { id: 'even', label: 'Even rest', short: 'Even rest', group: 'rest', def: 'Both teams had the same rest.', test: function(c) { return c.restDays != null && c.restDays === c.oppRestDays; } },
    { id: 'b2b', label: 'Back-to-back team', short: 'B2B team', group: 'rest', own: true, def: 'Played yesterday; the opponent didn’t.', test: function(c) { return c.b2b && !c.oppB2b; } },
    { id: 'ob2b', label: 'Opponent on back-to-back', short: 'Opp on B2B', group: 'rest', own: true, def: 'The opponent played yesterday; this team didn’t (fade the B2B team).', test: function(c) { return c.oppB2b && !c.b2b; } },
    { id: 'anyb2b', label: 'Either team on a back-to-back', short: 'Any B2B', group: 'rest', def: 'At least one team played yesterday.', test: function(c) { return c.b2b || c.oppB2b; } },
    { id: 'nob2b', label: 'Neither team on a back-to-back', short: 'No B2B', group: 'rest', def: 'Neither team played yesterday.', test: function(c) { return !c.b2b && !c.oppB2b; } },
    { id: 'three', label: '3 games in 4 nights', short: '3 in 4', group: 'rest', own: true, def: 'The team’s 3rd game within 4 days.', test: function(c) { return c.threeIn4; } },
    { id: 'trip3', label: '3rd+ game of a road trip', short: 'Road trip 3+', group: 'rest', own: true, def: 'At least the 3rd straight road game.', test: function(c) { return c.trip >= 3; } },
    { id: 'homeback', label: 'First home game after a road trip', short: 'Home from trip', group: 'rest', own: true, def: 'Home after a road trip of 3 or more games.', test: function(c) { return c.home && c.tripEnded >= 3; } },
    { id: 'tz', label: 'Crossed 2+ time zones', short: '2+ time zones', group: 'rest', own: true, def: 'Two or more time zones from the last game’s arena.', test: function(c) { return c.tzCrossed != null && c.tzCrossed >= 2; } },

    { id: 'pw', label: 'After a win', short: 'Off W', group: 'prev', own: true, def: 'Won its previous game.', test: function(c) { return c.prev && c.prev.res === 'W'; } },
    { id: 'pl', label: 'After a loss', short: 'Off L', group: 'prev', own: true, def: 'Lost its previous game (the old Bounce-Back card).', test: function(c) { return lost(c.prev); } },
    { id: 'pot', label: 'After an OT or shootout game', short: 'Off OT/SO', group: 'prev', own: true, def: 'Its previous game went past regulation.', test: function(c) { return c.prev && c.prev.ot; } },
    { id: 'p5', label: 'After scoring 5+', short: 'Off 5+ GF', group: 'prev', own: true, def: 'Scored 5 or more last game.', test: function(c) { return c.prev && c.prev.pf >= C.scored; } },
    { id: 'pa5', label: 'After allowing 5+', short: 'Off 5+ GA', group: 'prev', own: true, def: 'Allowed 5 or more last game.', test: function(c) { return c.prev && c.prev.pa >= C.scored; } },
    { id: 'pshut', label: 'After a shutout (scored 0)', short: 'Off shut out', group: 'prev', own: true, def: 'Was shut out last game (a shootout loss doesn’t count).', test: function(c) { return c.prev && c.prev.pf === 0 && c.prev.otType !== 'SO'; } },
    { id: 'pshutw', label: 'After a shutout win', short: 'Off shutout W', group: 'prev', own: true, def: 'Won its last game without allowing a goal.', test: function(c) { return c.prev && c.prev.res === 'W' && c.prev.pa === 0; } },
    { id: 'pfirst', label: 'Scored first last game', short: 'Scored 1st last', group: 'prev', own: true, def: 'Scored the first goal of its previous game.', test: function(c) { return c.prev && c.prev.scoredFirst === true; } },
    { id: 'pfirsta', label: 'Allowed first goal last game', short: 'Allowed 1st last', group: 'prev', own: true, def: 'Allowed the first goal of its previous game.', test: function(c) { return c.prev && c.prev.scoredFirst === false; } },
    { id: 'eloss', label: 'Either team off a loss', short: 'Any off L', group: 'prev', def: 'At least one team lost its previous game.', test: function(c) { return lost(c.prev) || lost(c.oppPrev); } },
    { id: 'eloss3', label: 'Either team off a loss by 3+', short: 'Any off L by 3+', group: 'prev', def: 'At least one team lost its previous game by 3 or more.',
      test: function(c) { return (c.prev && c.prev.pa - c.prev.pf >= C.lossBy) || (c.oppPrev && c.oppPrev.pa - c.oppPrev.pf >= C.lossBy); } },

    { id: 'starter', label: 'Starter', short: 'Starter', group: 'goalie', own: true, def: 'Started the team’s most-used goalie this season (to date).', test: function(c) { return c.starter === true; } },
    { id: 'backup', label: 'Backup', short: 'Backup', group: 'goalie', own: true, def: 'Started anyone else.', test: function(c) { return c.starter === false; } },
  ];
  window.RTYB_SPLITS = window.RTYB_SPLITS || {};
  window.RTYB_SPLITS.nhl = { config: C, groups: groups, rows: rows, favBy: 'fg-ml', periods: 3, smallSample: 10, pairUnits: 'both',
    markets: [{ id: 'su', label: 'Moneyline' }, { id: 'tot', label: 'Over 1.5', head: 'O/U 1.5', url: 'over15', pctHead: 'Over %' }, { id: 'btts', label: 'BTTS', url: 'btts' }],
    perspectives: [['home', 'Home team'], ['fav', 'Favorite']] };
})();
