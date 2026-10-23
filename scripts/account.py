"""
Phone header account controls (below 640px), shared by every page: the
sport pages (template.html, via __ACCOUNT__) and the home / Learn pages
(home.py). The desktop header is unchanged.

  signed out:  "Sign In" (outline) and "Go Premium" (gold) pills; under
               480px only Go Premium stays and Sign In lives in the menu
  signed in:   a round avatar (photo, or initials) that opens a small menu:
               Profile, Subscription (or Go Premium), Sign Out

There are no accounts yet, so the signed-in state comes from a small hook
the sign-in flow will call once it exists:

  window.rtybAccount.set({name: 'Pat D', photo: null, premium: false})
  window.rtybAccount.set(null)          // sign out

It keeps the user in localStorage ('rtyb-user'). Preview it on any page with
?user=1 (or ?user=premium); the preview isn't saved.

Every tap target is at least 44x44 (the pills are 44px tall hit areas around
a smaller visual pill). CSS lives in template.html (site.css), so both
headers share it.
"""


def account_html(root):
    """Markup for the phone account controls; `root` prefixes the links
    ('/' on sport pages, the relative depth on the home page)."""
    href = f'{root}#premium'
    return f'''<div class="acct-m" id="acctM">
      <a class="acct-pill acct-signin" href="{href}"><span>Sign In</span></a>
      <a class="acct-pill acct-gold" href="{href}"><span>Go Premium</span></a>
      <div class="acct-user" hidden>
        <button class="acct-avatar" id="acctAvatar" type="button" aria-haspopup="true" aria-expanded="false" aria-controls="acctMenu" aria-label="Account menu"><span class="acct-face" id="acctFace"></span></button>
        <div class="acct-menu" id="acctMenu" hidden>
          <div class="acct-name" id="acctName"></div>
          <a class="acct-item" href="{href}">Profile</a>
          <a class="acct-item" id="acctSub" href="{href}">Go Premium</a>
          <button class="acct-item" id="acctSignOut" type="button">Sign Out</button>
        </div>
      </div>
    </div>'''


ACCOUNT_JS = '''<script>
(function() {
  'use strict';
  var KEY = 'rtyb-user', preview = null;
  try {
    var m = /[?&]user=([^&#]*)/.exec(window.location.search);
    if (m) preview = { name: 'Test User', premium: m[1] === 'premium' };
  } catch (e) {}
  function current() {
    if (preview) return preview;
    try { var u = JSON.parse(localStorage.getItem(KEY) || 'null'); return u && u.name ? u : null; } catch (e) { return null; }
  }
  function initials(name) {
    var p = String(name).trim().split(/\\s+/);
    return ((p[0] || '').charAt(0) + (p.length > 1 ? p[p.length - 1].charAt(0) : '')).toUpperCase() || '?';
  }
  function render() {
    var box = document.getElementById('acctM');
    if (!box) return;
    var u = current(), signedIn = !!u;
    document.documentElement.classList.toggle('rtyb-signed-in', signedIn);
    box.querySelector('.acct-user').hidden = !signedIn;
    [].forEach.call(box.querySelectorAll('.acct-pill'), function(a) { a.hidden = signedIn; });
    if (!signedIn) return;
    var face = document.getElementById('acctFace');
    face.innerHTML = '';
    if (u.photo) { var img = document.createElement('img'); img.src = u.photo; img.alt = ''; face.appendChild(img); }
    else face.textContent = initials(u.name);
    document.getElementById('acctName').textContent = u.name;
    document.getElementById('acctSub').textContent = u.premium ? 'Subscription' : 'Go Premium';
  }
  function setMenu(open) {
    var menu = document.getElementById('acctMenu'), btn = document.getElementById('acctAvatar');
    if (!menu) return;
    menu.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  window.rtybAccount = {
    get: current,
    set: function(u) {
      preview = null;
      try { if (u) localStorage.setItem(KEY, JSON.stringify(u)); else localStorage.removeItem(KEY); } catch (e) {}
      setMenu(false); render();
    }
  };
  function init() {
    render();
    var btn = document.getElementById('acctAvatar');
    if (!btn) return;
    btn.addEventListener('click', function(e) { e.stopPropagation(); setMenu(document.getElementById('acctMenu').hidden); });
    document.getElementById('acctSignOut').addEventListener('click', function() { window.rtybAccount.set(null); });
    document.addEventListener('click', function(e) { if (!e.target.closest('.acct-user')) setMenu(false); });
    document.addEventListener('keydown', function(e) { if (e.key === 'Escape') setMenu(false); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
</script>'''
