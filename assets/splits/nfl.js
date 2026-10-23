/*
 * NFL Situational Results: the split registry. One row per split; the NFL
 * Stats page (league view) and every NFL team page (team view) render from
 * this list, so they always match. assets/sport.js has the engine
 * (situational*), which builds a context `c` for each team-game:
 *
 *   c.side 'away' | 'home'      c.team, c.opp (slugs)   c.home (bool)
 *   c.fav  true | false | null  (by the selected period's closing line; null = no line)
 *   c.dow  0 Sun .. 6 Sat, c.mins minutes after midnight (kickoff, ET)
 *   c.intl (played outside the US)   c.neutral
 *   c.ti, c.oi                  team / opponent info (conference, division)
 *   c.wk, c.prevWk, c.nextWk    regular-season week numbers (null if none)
 *   c.rest, c.oppRest           days since each team's previous game
 *   c.prev                      the team's previous game: {res 'W'|'L'|'T', pf, pa, ot,
 *                               side, dow, mins} (null for the first game)
 *
 * Row fields:
 *   id, label, short (mobile + game-log tag), group, def (one sentence),
 *   tier 'free' | 'pro' (no locking yet), indent (sub-row),
 *   own   true = the test picks the side itself (home, favorite, West Coast
 *         team...), so the league view counts each game once from that side;
 *         otherwise the league view applies "View as: Home team / Favorite"
 *   teamOnly (team view only), applies(slug, C) (team view: drop the row
 *   silently when it can't apply to the team), test(c, C).
 */
(function() {
  var C = {
    blowout: 17,         // "blowout" previous game: won / lost by this many or more
    oneScore: 8,         // "one-score" loss: lost by this many or fewer
    lowScore: 10,        // "scored 10 or fewer"
    primetime: 19 * 60,  // kickoffs at 7:00 PM ET or later
    westCoast: ['sea', 'sf', 'lar', 'lac', 'lv'],   // teams based in Pacific time
  };
  function sun(c) { return c.dow === 0; }
  function prime(c) { return c.mins >= C.primetime; }
  function margin(p) { return p.pf - p.pa; }

  var groups = [
    { id: 'ha', label: 'Home / Away · Favorite / Underdog',
      note: 'League view: Away and Underdog rows are the mirror of Home and Favorite (W and L swapped, margin negated); Away favorite mirrors Home underdog and Away underdog mirrors Home favorite.' },
    { id: 'opp', label: 'Opponent' },
    { id: 'ko', label: 'Kickoff Window' },
    { id: 'rest', label: 'Rest & Schedule' },
    { id: 'prev', label: 'Previous Game' },
  ];

  var rows = [
    // HOME / AWAY · FAVORITE / UNDERDOG
    { id: 'overall', label: 'Overall', short: 'Overall', group: 'ha', teamOnly: true, own: true, def: 'Every game this season.',
      test: function(c) { return true; } },
    { id: 'home', label: 'Home', short: 'Home', group: 'ha', own: true, def: 'Games as the home team.',
      test: function(c) { return c.home; } },
    { id: 'away', label: 'Away', short: 'Away', group: 'ha', own: true, def: 'Games as the road team.',
      test: function(c) { return !c.home; } },
    { id: 'fav', label: 'Favorite', short: 'Fav', group: 'ha', own: true, def: 'Favored by the period’s closing line.',
      test: function(c) { return c.fav === true; } },
    { id: 'hfav', label: 'Home favorite', short: 'Home fav', group: 'ha', indent: 1, own: true, def: 'Home team and favored.',
      test: function(c) { return c.home && c.fav === true; } },
    { id: 'afav', label: 'Away favorite', short: 'Away fav', group: 'ha', indent: 1, own: true, def: 'Road team and favored.',
      test: function(c) { return !c.home && c.fav === true; } },
    { id: 'dog', label: 'Underdog', short: 'Dog', group: 'ha', own: true, def: 'The underdog by the period’s closing line.',
      test: function(c) { return c.fav === false; } },
    { id: 'hdog', label: 'Home underdog', short: 'Home dog', group: 'ha', indent: 1, own: true, def: 'Home team and the underdog.',
      test: function(c) { return c.home && c.fav === false; } },
    { id: 'adog', label: 'Away underdog', short: 'Away dog', group: 'ha', indent: 1, own: true, def: 'Road team and the underdog.',
      test: function(c) { return !c.home && c.fav === false; } },

    // OPPONENT (the three rows don't overlap)
    { id: 'div', label: 'Division', short: 'Div', group: 'opp', def: 'Against a division rival.',
      test: function(c) { return c.ti && c.oi && c.ti.division === c.oi.division; } },
    { id: 'conf', label: 'Conference', short: 'Conf', group: 'opp', def: 'Against a same-conference team outside the division.',
      test: function(c) { return c.ti && c.oi && c.ti.conference === c.oi.conference && c.ti.division !== c.oi.division; } },
    { id: 'nonconf', label: 'Non-conference', short: 'Non-conf', group: 'opp', def: 'Against the other conference.',
      test: function(c) { return c.ti && c.oi && c.ti.conference !== c.oi.conference; } },

    // KICKOFF WINDOW
    { id: 'early', label: 'Early · 1:00 ET', short: '1:00 ET', group: 'ko', def: 'Sunday kickoffs before 2:00 PM ET.',
      test: function(c) { return sun(c) && c.mins < 14 * 60; } },
    { id: 'late', label: 'Late afternoon · 4:05/4:25 ET', short: '4:05/4:25', group: 'ko', def: 'Sunday kickoffs from 2:00 PM to 6:59 PM ET.',
      test: function(c) { return sun(c) && c.mins >= 14 * 60 && !prime(c); } },
    { id: 'prime', label: 'Primetime (all)', short: 'Primetime', group: 'ko', def: 'Any kickoff at 7:00 PM ET or later.',
      test: function(c) { return prime(c); } },
    { id: 'tnf', label: 'Thursday night', short: 'TNF', group: 'ko', indent: 1, def: 'Thursday kickoffs at 7:00 PM ET or later.',
      test: function(c) { return c.dow === 4 && prime(c); } },
    { id: 'snf', label: 'Sunday night', short: 'SNF', group: 'ko', indent: 1, def: 'Sunday kickoffs at 7:00 PM ET or later.',
      test: function(c) { return sun(c) && prime(c); } },
    { id: 'mnf', label: 'Monday night', short: 'MNF', group: 'ko', indent: 1, def: 'Monday kickoffs at 7:00 PM ET or later.',
      test: function(c) { return c.dow === 1 && prime(c); } },
    { id: 'intl', label: 'International', short: 'Intl', group: 'ko', def: 'Played outside the US.',
      test: function(c) { return c.intl === true; } },
    { id: 'west1', label: 'West Coast team · 1:00 ET', short: 'West @ 1:00', group: 'ko', own: true,
      def: 'A team based in Pacific time playing a 1:00 PM ET kickoff.',
      applies: function(slug) { return C.westCoast.indexOf(slug) !== -1; },
      test: function(c) { return C.westCoast.indexOf(c.team) !== -1 && sun(c) && c.mins >= 12 * 60 + 30 && c.mins < 14 * 60; } },

    // REST & SCHEDULE
    { id: 'prebye', label: 'Before bye', short: 'Pre-bye', group: 'rest', def: 'The last game before the team’s bye week.',
      test: function(c) { return c.wk != null && c.nextWk != null && c.nextWk - c.wk >= 2; } },
    { id: 'postbye', label: 'After bye', short: 'Post-bye', group: 'rest', def: 'The first game after the team’s bye week.',
      test: function(c) { return c.wk != null && c.prevWk != null && c.wk - c.prevWk >= 2; } },
    { id: 'short', label: 'Short week', short: 'Short wk', group: 'rest', def: 'A Thursday game right after a Sunday game.',
      test: function(c) { return c.dow === 4 && c.prev && c.prev.dow === 0; } },
    { id: 'aftermnf', label: 'After Monday night', short: 'Post-MNF', group: 'rest', def: 'The game after playing on Monday night.',
      test: function(c) { return c.prev && c.prev.dow === 1 && c.prev.mins >= C.primetime; } },
    { id: 'restadv', label: 'Rest advantage', short: 'Rest +', group: 'rest', def: 'Two or more days more rest than the opponent.',
      test: function(c) { return c.rest != null && c.oppRest != null && c.rest - c.oppRest >= 2; } },
    { id: 'restdis', label: 'Rest disadvantage', short: 'Rest −', group: 'rest', def: 'Two or more days less rest than the opponent.',
      test: function(c) { return c.rest != null && c.oppRest != null && c.oppRest - c.rest >= 2; } },
    { id: 'road2', label: '2nd straight road game', short: '2nd road', group: 'rest', own: true, def: 'A road game right after another road game.',
      test: function(c) { return !c.home && c.prev && c.prev.side === 'away'; } },

    // PREVIOUS GAME (full-game result)
    { id: 'pwin', label: 'After a win', short: 'Off W', group: 'prev', def: 'The team won its previous game.',
      test: function(c) { return c.prev && c.prev.res === 'W'; } },
    { id: 'ploss', label: 'After a loss', short: 'Off L', group: 'prev', def: 'The team lost its previous game.',
      test: function(c) { return c.prev && c.prev.res === 'L'; } },
    { id: 'plow', label: 'After scoring 10 or fewer', short: 'Off ≤10 pts', group: 'prev', def: 'The team scored 10 or fewer points in its previous game.',
      test: function(c) { return c.prev && c.prev.pf <= C.lowScore; } },
    { id: 'pshut', label: 'After being shut out', short: 'Off shutout', group: 'prev', indent: 1, def: 'The team was shut out in its previous game.',
      test: function(c) { return c.prev && c.prev.pf === 0; } },
    { id: 'pblowl', label: 'After blowout loss (17+)', short: 'Off blowout L', group: 'prev', def: 'The team lost its previous game by 17 or more.',
      test: function(c) { return c.prev && margin(c.prev) <= -C.blowout; } },
    { id: 'pbloww', label: 'After blowout win (17+)', short: 'Off blowout W', group: 'prev', def: 'The team won its previous game by 17 or more.',
      test: function(c) { return c.prev && margin(c.prev) >= C.blowout; } },
    { id: 'pclose', label: 'After one-score loss (8 or fewer)', short: 'Off 1-score L', group: 'prev', def: 'The team lost its previous game by 8 or fewer.',
      test: function(c) { return c.prev && c.prev.res === 'L' && margin(c.prev) >= -C.oneScore; } },
    { id: 'pot', label: 'After overtime game', short: 'Off OT', group: 'prev', def: 'The team’s previous game went to overtime.',
      test: function(c) { return c.prev && c.prev.ot; } },
  ];

  window.RTYB_SPLITS = window.RTYB_SPLITS || {};
  window.RTYB_SPLITS.nfl = { config: C, groups: groups, rows: rows, perspectives: [['home', 'Home team'], ['fav', 'Favorite']] };
})();
