"""
The site nav, defined once for every page (home, Learn, The Daily, Picks,
Streaks and every sport page; admin has its own):

  Sports ▾ (the launched sports) · Trends · Odds · The Daily · Learn
  ... Sign in · Go Premium · account · theme toggle

Phones get a hamburger that opens a full-screen menu with the same links.
Picks and Streaks stay reachable by URL but aren't linked here. Styles
live with the rest of the site's in template.html's <style> (the .hn / .hm
rules), which the build writes out as assets/site.css.

`base` prefixes every link: the relative depth on the home-style pages
('', '../'), '/' on sport pages (SITE_ROOT is added at load).
"""
import html

import account
import icons
import sports


def esc(s):
    return html.escape('' if s is None else str(s), quote=True)


def _sport_items(base, status, section):
    """Sports menu rows. status: [(sport, live, short)]; a sport page passes
    its section so the menu switches sport and keeps the page."""
    out = ''
    for sp, live, short in status:
        sec = section if section in sp['sections'] else 'games'
        out += (f'<a class="hn-sport-item" href="{base}{sports.section_path(sp, sec).lstrip("/")}">'
                f'<span class="hn-sport-name">{icons.sport_icon(sp)}{esc(sp["label"])}</span>'
                f'<span class="hn-badge{" live" if live else ""}">{"LIVE" if live else esc(short)}</span></a>')
    return out


def links(base):
    """[(label, href)] after the Sports menu. Trends and Odds open the NHL
    pages for now."""
    nhl = sports.BY_KEY['nhl']
    return [('Trends', base + sports.section_path(nhl, 'trends').lstrip('/')),
            ('Odds', base + sports.section_path(nhl, 'odds').lstrip('/')),
            ('The Daily', base + 'daily/'),
            ('Learn', base + 'learn/')]


def header(base, status, sport=None, section=None, home_href=None):
    """The nav bar and phone menu. sport: the sport page being shown (its
    name labels the Sports button)."""
    home_href = home_href or base or './'
    items = _sport_items(base, status, section)
    label = f'{icons.sport_icon(sport)}{esc(sport["label"])}' if sport else 'Sports'
    desk = ''.join(f'<a class="hn-link" href="{h}">{esc(t)}</a>' for t, h in links(base))
    phone = ''.join(f'<a class="hm-item" href="{h}">{esc(t)}</a>' for t, h in links(base))
    premium = f'{base}#premium'
    return f'''
<header class="hn">
  <div class="hn-inner">
    <a class="brand" href="{home_href}" aria-label="RTYB home">__LOGO_SVG__</a>
    <nav class="hn-links" aria-label="Main">
      <div class="hn-drop">
        <button class="hn-link hn-drop-btn" id="hnSportsBtn" type="button" aria-expanded="false" aria-haspopup="true">{label} <span aria-hidden="true">&#9662;</span></button>
        <div class="hn-drop-menu" id="hnSportsMenu">{items}</div>
      </div>
      {desk}
    </nav>
    <div class="hn-right">
      <a class="hn-link hn-signin" href="{premium}">Sign in</a>
      <a class="hn-premium" href="{premium}">Go Premium</a>
      {account.account_html(base)}
      <button class="theme-toggle" id="themeToggle" type="button" aria-label="Toggle light/dark theme">&#9681;</button>
      <button class="hn-burger" id="hnBurger" type="button" aria-label="Open menu" aria-expanded="false" aria-controls="hnMenu">
        <span></span><span></span><span></span></button>
    </div>
  </div>
</header>
<div class="hm" id="hnMenu" hidden>
  <div class="hm-head">
    <a class="brand" href="{home_href}" aria-label="RTYB home">__LOGO_SVG__</a>
    <button class="hm-close" id="hnClose" type="button" aria-label="Close menu">&times;</button>
  </div>
  <div class="hm-body">
    <button class="hm-acc" id="hmSportsBtn" type="button" aria-expanded="true" aria-controls="hmSports">Sports <span aria-hidden="true">&#9662;</span></button>
    <div class="hm-sports" id="hmSports">{items}</div>
    {phone}
    <a class="hm-item hm-signin" href="{premium}">Sign in</a>
    <button class="hm-item hm-theme" id="hmTheme" type="button">Light / dark theme</button>
  </div>
  <a class="hm-premium" href="{premium}">Go Premium</a>
</div>{JS}'''


# Menus and the phone sheet. The theme toggle itself is wired by each
# page's own script (sport pages also re-render on a theme change); the
# phone menu's theme row just presses it.
JS = '''
<script>
(function() {
  'use strict';
  var sBtn = document.getElementById('hnSportsBtn'), sMenu = document.getElementById('hnSportsMenu');
  sBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    var open = !sMenu.classList.contains('open');
    sMenu.classList.toggle('open', open);
    sBtn.setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('click', function(e) {
    if (!sMenu.contains(e.target)) { sMenu.classList.remove('open'); sBtn.setAttribute('aria-expanded', 'false'); }
  });
  var menu = document.getElementById('hnMenu'), burger = document.getElementById('hnBurger');
  function setMenu(open) {
    menu.hidden = !open;
    burger.setAttribute('aria-expanded', String(open));
    document.body.classList.toggle('hm-open', open);
    if (open) document.getElementById('hnClose').focus(); else burger.focus();
  }
  burger.addEventListener('click', function() { setMenu(true); });
  document.getElementById('hnClose').addEventListener('click', function() { setMenu(false); });
  document.addEventListener('keydown', function(e) { if (e.key === 'Escape' && !menu.hidden) setMenu(false); });
  menu.querySelectorAll('a').forEach(function(a) { a.addEventListener('click', function() { setMenu(false); }); });
  document.getElementById('hmTheme').addEventListener('click', function() { document.getElementById('themeToggle').click(); });
  var acc = document.getElementById('hmSportsBtn'), accBody = document.getElementById('hmSports');
  acc.addEventListener('click', function() {
    var open = acc.getAttribute('aria-expanded') !== 'true';
    acc.setAttribute('aria-expanded', String(open));
    accBody.hidden = !open;
  });
})();
</script>'''
