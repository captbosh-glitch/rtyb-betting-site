/*
 * NCAAF Situational Results: the split registry (same shape and engine as
 * assets/splits/nfl.js; see that file for the row fields). Extra context
 * the engine fills in for college football:
 *
 *   c.fs                 the team's closing full-game spread (negative = favored)
 *   c.rank, c.oppRank    AP rank at kickoff (that week's poll), null = unranked
 *   c.teamConf, c.oppConf  conference by season (data_seed/conferences)
 *   c.oppFcs, c.oppP4    opponent is FCS / Power 4 (P4 conferences + Notre Dame)
 *   c.rival              this game is a rivalry game (data_seed/rivalries)
 *   c.next               the team's next game: {rival, oppRank} (null if none)
 *   c.prev               previous game, plus .fs (its full-game spread), .rival
 */
(function() {
  var C = {
    blowout: 28,       // college blowouts: 17-point games are routine, 28 separates
    oneScore: 8,
    upset: 7,          // "upset" previous result: lost as a 7+ favorite / won as a 7+ underdog
    // teams based in Pacific or Mountain time (incl. Arizona and Hawaii)
    west: ['air-force-falcons', 'arizona-state-sun-devils', 'arizona-wildcats', 'boise-state-broncos', 'byu-cougars',
      'california-golden-bears', 'colorado-buffaloes', 'colorado-state-rams', 'fresno-state-bulldogs', 'hawaii-rainbow-warriors',
      'nevada-wolf-pack', 'new-mexico-lobos', 'new-mexico-state-aggies', 'oregon-ducks', 'oregon-state-beavers',
      'sacramento-state-hornets', 'san-diego-state-aztecs', 'san-jos-state-spartans', 'stanford-cardinal', 'ucla-bruins',
      'unlv-rebels', 'usc-trojans', 'utah-state-aggies', 'utah-utes', 'utep-miners', 'washington-huskies',
      'washington-state-cougars', 'wyoming-cowboys'],
  };
  function fav(c, lo, hi) { return c.fs != null && c.fs < 0 && -c.fs >= lo && -c.fs <= hi; }
  function dog(c, lo, hi) { return c.fs != null && c.fs > 0 && c.fs >= lo && c.fs <= hi; }
  function margin(p) { return p.pf - p.pa; }
  function ranked(r) { return r != null; }

  var groups = [
    { id: 'ha', label: 'Home / Away · Favorite / Underdog',
      note: 'All FBS view: Away and Underdog rows are the mirror of Home and Favorite (W and L swapped, margin negated); Away favorite mirrors Home underdog and Away underdog mirrors Home favorite.' },
    { id: 'spread', label: 'Spread Size (closing full-game spread)' },
    { id: 'opp', label: 'Opponent' },
    { id: 'rank', label: 'Rankings · AP Top 25 (rank at kickoff)' },
    { id: 'ko', label: 'Kickoff Window' },
    { id: 'rest', label: 'Rest & Schedule' },
    { id: 'prev', label: 'Previous Game' },
  ];

  var rows = [
    // HOME / AWAY · FAVORITE / UNDERDOG
    { id: 'overall', label: 'Overall', short: 'Overall', group: 'ha', teamOnly: true, own: true, def: 'Every game this season.',
      test: function(c) { return true; } },
    { id: 'home', label: 'Home', short: 'Home', group: 'ha', own: true, def: 'Games as the home team (not neutral site).',
      test: function(c) { return c.home && !c.neutral; } },
    { id: 'away', label: 'Away', short: 'Away', group: 'ha', own: true, def: 'Games as the road team (not neutral site).',
      test: function(c) { return !c.home && !c.neutral; } },
    { id: 'neutral', label: 'Neutral site', short: 'Neutral', group: 'ha', def: 'Kickoff classics, bowls and other neutral stadiums.',
      test: function(c) { return c.neutral; } },
    { id: 'fav', label: 'Favorite', short: 'Fav', group: 'ha', own: true, def: 'Favored by the period’s closing line (the full-game line when the period has none).',
      test: function(c) { return c.fav === true; } },
    { id: 'hfav', label: 'Home favorite', short: 'Home fav', group: 'ha', indent: 1, own: true, def: 'Home team and favored.',
      test: function(c) { return c.home && c.fav === true; } },
    { id: 'afav', label: 'Away favorite', short: 'Away fav', group: 'ha', indent: 1, own: true, def: 'Road team and favored.',
      test: function(c) { return !c.home && c.fav === true; } },
    { id: 'dog', label: 'Underdog', short: 'Dog', group: 'ha', own: true, def: 'The underdog by the period’s closing line (the full-game line when the period has none).',
      test: function(c) { return c.fav === false; } },
    { id: 'hdog', label: 'Home underdog', short: 'Home dog', group: 'ha', indent: 1, own: true, def: 'Home team and the underdog.',
      test: function(c) { return c.home && c.fav === false; } },
    { id: 'adog', label: 'Away underdog', short: 'Away dog', group: 'ha', indent: 1, own: true, def: 'Road team and the underdog.',
      test: function(c) { return !c.home && c.fav === false; } },

    // SPREAD SIZE (closing full-game spread)
    { id: 'f0', label: 'Favorite 0–6.5', short: 'Fav 0–6.5', group: 'spread', own: true, def: 'Favored by 0.5 to 6.5 points (full game).',
      test: function(c) { return fav(c, 0.5, 6.5); } },
    { id: 'f7', label: 'Favorite 7–13.5', short: 'Fav 7–13.5', group: 'spread', own: true, def: 'Favored by 7 to 13.5 points (full game).',
      test: function(c) { return fav(c, 7, 13.5); } },
    { id: 'f14', label: 'Favorite 14–20.5', short: 'Fav 14–20.5', group: 'spread', own: true, def: 'Favored by 14 to 20.5 points (full game).',
      test: function(c) { return fav(c, 14, 20.5); } },
    { id: 'f21', label: 'Favorite 21+', short: 'Fav 21+', group: 'spread', own: true, def: 'Favored by 21 or more points (full game).',
      test: function(c) { return fav(c, 21, 999); } },
    { id: 'd0', label: 'Underdog 0–6.5', short: 'Dog 0–6.5', group: 'spread', own: true, def: 'Getting 0.5 to 6.5 points (full game).',
      test: function(c) { return dog(c, 0.5, 6.5); } },
    { id: 'd7', label: 'Underdog 7–13.5', short: 'Dog 7–13.5', group: 'spread', own: true, def: 'Getting 7 to 13.5 points (full game).',
      test: function(c) { return dog(c, 7, 13.5); } },
    { id: 'd14', label: 'Underdog 14–20.5', short: 'Dog 14–20.5', group: 'spread', own: true, def: 'Getting 14 to 20.5 points (full game).',
      test: function(c) { return dog(c, 14, 20.5); } },
    { id: 'd21', label: 'Underdog 21+', short: 'Dog 21+', group: 'spread', own: true, def: 'Getting 21 or more points (full game).',
      test: function(c) { return dog(c, 21, 999); } },

    // OPPONENT
    { id: 'conf', label: 'Conference', short: 'Conf', group: 'opp', def: 'Against a conference opponent, including the conference championship.',
      test: function(c) { return c.teamConf && c.teamConf === c.oppConf && !/Independent/.test(c.teamConf); } },
    { id: 'nonconf', label: 'Non-conference', short: 'Non-conf', group: 'opp', def: 'Against a team outside the conference.',
      test: function(c) { return !(c.teamConf && c.teamConf === c.oppConf && !/Independent/.test(c.teamConf)); } },
    { id: 'vp4', label: 'vs Power 4', short: 'vs P4', group: 'opp', indent: 1, def: 'Non-conference game against the SEC, Big Ten, ACC, Big 12 or Notre Dame.',
      test: function(c) { return c.teamConf !== c.oppConf && c.oppP4; } },
    { id: 'vg5', label: 'vs Group of 5', short: 'vs G5', group: 'opp', indent: 1, def: 'Non-conference game against an FBS team outside the Power 4.',
      test: function(c) { return c.teamConf !== c.oppConf && !c.oppP4 && !c.oppFcs; } },
    { id: 'vfcs', label: 'vs FCS', short: 'vs FCS', group: 'opp', indent: 1, def: 'Against an FCS team.',
      test: function(c) { return c.oppFcs; } },

    // RANKINGS · AP TOP 25 (rank at kickoff)
    { id: 'asrk', label: 'As a ranked team', short: 'Ranked', group: 'rank', def: 'Ranked in that week’s AP Top 25.',
      test: function(c) { return ranked(c.rank); } },
    { id: 'asur', label: 'As an unranked team', short: 'Unranked', group: 'rank', def: 'Not in that week’s AP Top 25.',
      test: function(c) { return !ranked(c.rank); } },
    { id: 'vrk', label: 'vs ranked opponent', short: 'vs ranked', group: 'rank', def: 'The opponent is in that week’s AP Top 25.',
      test: function(c) { return ranked(c.oppRank); } },
    { id: 'vur', label: 'vs unranked opponent', short: 'vs unranked', group: 'rank', def: 'The opponent is not in that week’s AP Top 25.',
      test: function(c) { return !ranked(c.oppRank); } },
    { id: 'rvr', label: 'Ranked vs ranked', short: 'Rk vs rk', group: 'rank', indent: 1, def: 'Both teams in that week’s AP Top 25.',
      test: function(c) { return ranked(c.rank) && ranked(c.oppRank); } },
    { id: 'uvr', label: 'Unranked vs ranked (upset spot)', short: 'Upset spot', group: 'rank', indent: 1, def: 'An unranked team facing a ranked one.',
      test: function(c) { return !ranked(c.rank) && ranked(c.oppRank); } },
    { id: 'vt10', label: 'vs Top 10', short: 'vs Top 10', group: 'rank', def: 'The opponent is ranked 1–10 that week.',
      test: function(c) { return ranked(c.oppRank) && c.oppRank <= 10; } },

    // KICKOFF WINDOW (ET)
    { id: 'noon', label: 'Noon ET', short: 'Noon', group: 'ko', def: 'Kickoffs from 11:00 AM to 1:59 PM ET.',
      test: function(c) { return c.mins >= 11 * 60 && c.mins < 14 * 60; } },
    { id: 'aft', label: 'Afternoon · 3:30 ET', short: '3:30', group: 'ko', def: 'Kickoffs from 2:00 PM to 5:59 PM ET.',
      test: function(c) { return c.mins >= 14 * 60 && c.mins < 18 * 60; } },
    { id: 'night', label: 'Night · 7–8 ET', short: 'Night', group: 'ko', def: 'Kickoffs from 6:00 PM to 9:59 PM ET.',
      test: function(c) { return c.mins >= 18 * 60 && c.mins < 22 * 60; } },
    { id: 'late', label: 'Late night · 10:00+ ET', short: 'Late night', group: 'ko', def: 'Kickoffs at 10:00 PM ET or later.',
      test: function(c) { return c.mins >= 22 * 60 || c.mins < 4 * 60; } },
    { id: 'wkday', label: 'Weekday (Tue–Fri)', short: 'Weekday', group: 'ko', def: 'Games played Tuesday through Friday.',
      test: function(c) { return c.dow >= 2 && c.dow <= 5; } },
    { id: 'westnoon', label: 'West team · Noon ET', short: 'West @ noon', group: 'ko', own: true,
      def: 'A team based in Pacific or Mountain time playing a Noon ET kickoff.',
      applies: function(slug) { return C.west.indexOf(slug) !== -1; },
      test: function(c) { return C.west.indexOf(c.team) !== -1 && c.mins >= 11 * 60 && c.mins < 14 * 60; } },

    // REST & SCHEDULE
    { id: 'prebye', label: 'Before bye', short: 'Pre-bye', group: 'rest', def: 'The last game before the team’s bye week.',
      test: function(c) { return c.wk != null && c.nextWk != null && c.nextWk - c.wk >= 2; } },
    { id: 'postbye', label: 'After bye', short: 'Post-bye', group: 'rest', def: 'The first game after the team’s bye week.',
      test: function(c) { return c.wk != null && c.prevWk != null && c.wk - c.prevWk >= 2; } },
    { id: 'restadv', label: 'Rest advantage', short: 'Rest +', group: 'rest', def: 'Two or more days more rest than the opponent.',
      test: function(c) { return c.rest != null && c.oppRest != null && c.rest - c.oppRest >= 2; } },
    { id: 'restdis', label: 'Rest disadvantage', short: 'Rest −', group: 'rest', def: 'Two or more days less rest than the opponent.',
      test: function(c) { return c.rest != null && c.oppRest != null && c.oppRest - c.rest >= 2; } },
    { id: 'road2', label: '2nd straight road game', short: '2nd road', group: 'rest', own: true, def: 'A road game right after another road game.',
      test: function(c) { return !c.home && !c.neutral && c.prev && c.prev.side === 'away' && !c.prev.neutral; } },
    { id: 'look', label: 'Lookahead', short: 'Lookahead', group: 'rest', def: 'The game right before facing a rival or a ranked opponent.',
      test: function(c) { return c.next && (c.next.rival || c.next.oppRank != null); } },
    { id: 'letdown', label: 'Letdown', short: 'Letdown', group: 'rest', def: 'The game right after a rivalry game or an upset win.',
      test: function(c) { return c.prev && (c.prev.rival || (c.prev.res === 'W' && c.prev.fs != null && c.prev.fs > 0)); } },

    // PREVIOUS GAME (full-game result)
    { id: 'pwin', label: 'After a win', short: 'Off W', group: 'prev', def: 'The team won its previous game.',
      test: function(c) { return c.prev && c.prev.res === 'W'; } },
    { id: 'ploss', label: 'After a loss', short: 'Off L', group: 'prev', def: 'The team lost its previous game.',
      test: function(c) { return c.prev && c.prev.res === 'L'; } },
    { id: 'pbloww', label: 'After blowout win (28+)', short: 'Off blowout W', group: 'prev', def: 'The team won its previous game by 28 or more.',
      test: function(c) { return c.prev && margin(c.prev) >= C.blowout; } },
    { id: 'pblowl', label: 'After blowout loss (28+)', short: 'Off blowout L', group: 'prev', def: 'The team lost its previous game by 28 or more.',
      test: function(c) { return c.prev && margin(c.prev) <= -C.blowout; } },
    { id: 'pupl', label: 'After upset loss (lost as a favorite of 7+)', short: 'Off upset L', group: 'prev', def: 'The team lost its previous game as a 7-point or bigger favorite.',
      test: function(c) { return c.prev && c.prev.res === 'L' && c.prev.fs != null && c.prev.fs <= -C.upset; } },
    { id: 'pupw', label: 'After upset win (won as an underdog of 7+)', short: 'Off upset W', group: 'prev', def: 'The team won its previous game as a 7-point or bigger underdog.',
      test: function(c) { return c.prev && c.prev.res === 'W' && c.prev.fs != null && c.prev.fs >= C.upset; } },
    { id: 'pclose', label: 'After one-score loss (8 or fewer)', short: 'Off 1-score L', group: 'prev', def: 'The team lost its previous game by 8 or fewer.',
      test: function(c) { return c.prev && c.prev.res === 'L' && margin(c.prev) >= -C.oneScore; } },
    { id: 'pot', label: 'After overtime game', short: 'Off OT', group: 'prev', def: 'The team’s previous game went to overtime.',
      test: function(c) { return c.prev && c.prev.ot; } },
  ];

  window.RTYB_SPLITS = window.RTYB_SPLITS || {};
  window.RTYB_SPLITS.ncaaf = { config: C, groups: groups, rows: rows, perspectives: [['home', 'Home team'], ['fav', 'Favorite']],
    conferences: ['Big Ten Conference', 'Southeastern Conference', 'Atlantic Coast Conference', 'Big 12 Conference', 'American Conference',
      'Conference USA', 'Mid-American Conference', 'Mountain West Conference', 'Pac-12 Conference', 'Sun Belt Conference', 'FBS Independents'] };
})();
