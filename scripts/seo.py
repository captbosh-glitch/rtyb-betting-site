"""
Search and sharing, run last in the build (build_site.py):

  - privacy/ and terms/ pages (write_legal). Details still to come are in
    [BRACKETS] (Chris's city and state).
  - every page's <head> gets share tags (Open Graph / Twitter, with the
    share image for its arena), a canonical link and the analytics snippet
    (finish), plus Beehiiv's attribution script and the signup handler
    (signup.py), whose boxes finish also fills in. The block sits between <!--seo--> markers, so re-running
    replaces it.
  - sitemap.xml (home, NHL, NBA, The Daily and Learn pages that aren't
    noindex) and robots.txt.

SITE_URL comes from the CNAME file once the domain is set up (Prompt 17),
else the GitHub Pages address. content/analytics.html holds the analytics snippet:
paste the provider's <script> tag(s) into it and the next build puts them
on every page; while it's only comments, nothing is added.

The share images (assets/share/{home,nhl,nba}.jpg, 1200x630) are drawn
once; they don't change with the data.
"""
import html
import os
import re

import signup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_URL = 'https://runtoyourbets.github.io/rtyb-betting-site/'
ANALYTICS_FILE = os.path.join(ROOT, 'content', 'analytics.html')
SKIP_DIRS = {'.git', 'admin', 'worker', 'tests', 'content', 'scripts', 'data_admin', 'data_feed', 'data_seed', 'trends_log', '__pycache__'}
SITEMAP_TOP = ('', 'nhl', 'nba', 'daily', 'column', 'learn')   # first path segment
SHARE = {'nhl': 'nhl', 'nba': 'nba'}                          # first segment -> image


def site_url():
    try:
        with open(os.path.join(ROOT, 'CNAME'), encoding='utf-8') as f:
            host = f.read().strip()
    except OSError:
        host = ''
    return f'https://{host}/' if host else PAGES_URL


def analytics():
    """The pasted snippet, or '' while the file is only comments."""
    try:
        with open(ANALYTICS_FILE, encoding='utf-8') as f:
            text = f.read()
    except OSError:
        return ''
    return text.strip() if re.sub(r'<!--.*?-->', '', text, flags=re.S).strip() else ''


# ------------------------------------------------------------- legal pages

PRIVACY = '''
<h1>Privacy Policy</h1>
<p class="dp-date">Last updated: November 26, 2026</p>
<p>This policy explains what RTYB &mdash; Run to Your Bets (&ldquo;RTYB&rdquo;, &ldquo;we&rdquo;) collects when you use
runtoyourbets.com, and what we do with it. RTYB is run by Christopher David, [CITY, STATE].</p>
<h2>What we collect</h2>
<ul>
<li><b>Usage data.</b> We use Cloudflare Web Analytics to count visits and see which pages are used: pages viewed,
referring site, device and browser type, and country. It doesn&rsquo;t use cookies or identify you; we only see
anonymous totals.</li>
<li><b>Your email address</b>, only if you sign up for the Running Tab, our newsletter. It&rsquo;s stored with Beehiiv,
our newsletter service, and used to send the emails you asked for. Every email has an unsubscribe link. Beehiiv&rsquo;s
signup form sets cookies to record which page you signed up from and that you&rsquo;ve already signed up, so it
doesn&rsquo;t ask you again.</li>
<li><b>Settings on your device.</b> Your light or dark theme choice is saved in your own browser (local storage).
It isn&rsquo;t sent to us.</li>
</ul>
<p>We don&rsquo;t ask for your name, address, payment details or betting history, and we don&rsquo;t sell personal information.</p>
<h2>Sportsbook links</h2>
<p>Odds on RTYB link to sportsbooks through our odds partner, Gambly. Those links carry a partner code that tells the
partner the visit came from RTYB, and RTYB may earn a commission when you sign up or bet there. Once you leave RTYB, that site&rsquo;s own privacy policy applies.</p>
<h2>Who we share it with</h2>
<p>Only the services named above, which process data for us, and anyone the law requires us to share it with.</p>
<h2>How long we keep it</h2>
<p>We keep your email address until you unsubscribe or ask us to delete it. Analytics are anonymous and aggregated,
so there&rsquo;s nothing in them tied to you.</p>
<h2>Your choices</h2>
<p>You can unsubscribe from emails at any time, block or clear cookies in your browser, and ask us to see or delete
the data we hold about you by writing to <a href="mailto:info@runtoyourbets.com">info@runtoyourbets.com</a>.</p>
<h2>Age</h2>
<p>RTYB is for adults 21 and over. We don&rsquo;t knowingly collect information from anyone under 21.</p>
<h2>Changes</h2>
<p>If this policy changes, we&rsquo;ll update the date above.</p>
<h2>Contact</h2>
<p><a href="mailto:info@runtoyourbets.com">info@runtoyourbets.com</a></p>
'''

TERMS = '''
<h1>Terms of Use</h1>
<p class="dp-date">Last updated: November 26, 2026</p>
<p>These terms cover your use of RTYB &mdash; Run to Your Bets (runtoyourbets.com), run by Christopher David.
By using the site you agree to them.</p>
<h2>21 and over</h2>
<p>RTYB is for people 21 and over, and only where sports betting is legal for you. You&rsquo;re responsible for knowing
and following the laws where you are.</p>
<h2>Information, not advice</h2>
<p>RTYB shows odds, stats, trends and records for information and entertainment. Nothing here is betting, financial or
legal advice, and nothing guarantees a result. Past results don&rsquo;t predict future ones. Records and units are for
tracking only. Odds change quickly and can differ from what a sportsbook shows: always check the price before you bet.
Any bet you place is your own decision and your own risk.</p>
<h2>Accuracy</h2>
<p>We work to keep the numbers right, but data comes from third-party sources and can be late, incomplete or wrong.
The site is provided &ldquo;as is&rdquo;, without warranties of any kind.</p>
<h2>Sportsbooks and other sites</h2>
<p>RTYB isn&rsquo;t a sportsbook and doesn&rsquo;t take bets. Links to sportsbooks and partners take you to sites we
don&rsquo;t control; their terms apply there. RTYB isn&rsquo;t affiliated with any league or team.</p>
<h2>Affiliate disclosure</h2>
<p>Our sportsbook links carry a partner code, and RTYB may earn a commission from sportsbook links when you sign up
or bet through them. That never changes the odds, stats or trends we show.</p>
<h2>Using the site</h2>
<p>Don&rsquo;t copy the site&rsquo;s content or data in bulk, scrape it, or use it to build a competing product without
our written permission.</p>
<h2>Limit of liability</h2>
<p>To the extent the law allows, Christopher David and RTYB aren&rsquo;t liable for any losses, including betting losses, that
come from using the site or relying on its information.</p>
<h2>Governing law</h2>
<p>These terms are governed by the laws of [STATE].</p>
<h2>Changes</h2>
<p>We may update these terms; the date above shows the latest version.</p>
<h2>Gambling problem?</h2>
<p>Call <a href="tel:18004262537">1-800-GAMBLER</a>. Help is free and confidential.</p>
<h2>Contact</h2>
<p><a href="mailto:info@runtoyourbets.com">info@runtoyourbets.com</a></p>
'''

LEGAL = {'privacy': ('RTYB — Privacy Policy', 'How RTYB — Run to Your Bets handles your data.', PRIVACY),
         'terms': ('RTYB — Terms of Use', 'The terms for using RTYB — Run to Your Bets.', TERMS)}


def write_legal(page, status, logo_svg):
    """privacy/ and terms/. `page` is home.page."""
    for slug, (title, desc, body) in LEGAL.items():
        out = page(title, desc, f'<article class="hp-sec dp-piece legal"><div class="dp-body">{body}</div></article>',
                   status, depth='../').replace('__LOGO_SVG__', logo_svg)
        os.makedirs(os.path.join(ROOT, slug), exist_ok=True)
        with open(os.path.join(ROOT, slug, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(out)


# ------------------------------------------------- head tags, sitemap, robots

def pages():
    """Relative dirs ('' for the home page) of every built page."""
    for d, dirs, files in os.walk(ROOT):
        rel = os.path.relpath(d, ROOT).replace(os.sep, '/')
        rel = '' if rel == '.' else rel + '/'
        dirs[:] = sorted(x for x in dirs if not (rel == '' and x in SKIP_DIRS) and not x.startswith('.'))
        if 'index.html' in files:
            yield rel


def meta(page_html, name):
    m = re.search(rf'<meta (?:name|property)="{name}" content="([^"]*)"', page_html)
    return html.unescape(m.group(1)) if m else ''


def head_block(rel, page_html, base, snippet):
    title = re.search(r'<title>(.*?)</title>', page_html, re.S)
    title = html.unescape(title.group(1).strip()) if title else 'RTYB — Run to Your Bets'
    desc = meta(page_html, 'description')
    img = f'{base}assets/share/{SHARE.get(rel.split("/")[0], "home")}.jpg'
    e = lambda s: html.escape(s, quote=True)
    tags = [f'<meta property="og:type" content="website">',
            f'<meta property="og:site_name" content="RTYB — Run to Your Bets">',
            f'<meta property="og:title" content="{e(title)}">',
            f'<meta property="og:description" content="{e(desc)}">',
            f'<meta property="og:url" content="{e(base + rel)}">',
            f'<meta property="og:image" content="{e(img)}">',
            '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">',
            '<meta name="twitter:card" content="summary_large_image">',
            f'<meta name="twitter:image" content="{e(img)}">']
    if 'rel="canonical"' not in re.sub(r'<!--seo-->.*?<!--/seo-->', '', page_html, flags=re.S):
        tags.append(f'<link rel="canonical" href="{e(base + rel)}">')
    tags.append(signup.ATTRIBUTION + signup.SIGNUP_JS)
    if snippet:
        tags.append(snippet)
    return '<!--seo-->' + ''.join(tags) + '<!--/seo-->'


def finish():
    """Share tags, canonical and analytics on every page; footer links;
    sitemap.xml and robots.txt. Returns the sitemap's URL count."""
    base, snippet, urls = site_url(), analytics(), []
    for rel in pages():
        path = os.path.join(ROOT, rel, 'index.html')
        with open(path, encoding='utf-8') as f:
            page_html = f.read()
        if 'http-equiv="refresh"' in page_html:   # redirect stubs
            continue
        out = signup.fill(page_html.replace('__ROOT__', '../' * rel.count('/')))
        block = head_block(rel, out, base, snippet)
        if '<!--seo-->' in out:
            out = re.sub(r'<!--seo-->.*?<!--/seo-->', lambda m: block, out, count=1, flags=re.S)
        else:
            out = out.replace('</head>', block + '</head>', 1)
        if out != page_html:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(out)
        if rel.split('/')[0] in SITEMAP_TOP and 'content="noindex"' not in out:
            urls.append(base + rel)
    with open(os.path.join(ROOT, 'sitemap.xml'), 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        f.writelines(f'  <url><loc>{html.escape(u)}</loc></url>\n' for u in urls)
        f.write('</urlset>\n')
    with open(os.path.join(ROOT, 'robots.txt'), 'w', encoding='utf-8') as f:
        f.write(f'User-agent: *\nDisallow: /admin/\n\nSitemap: {base}sitemap.xml\n')
    return len(urls)
