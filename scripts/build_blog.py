#!/usr/bin/env python3
"""
Mirror the Medium feed into static pages under posts/.

Medium's RSS carries the full article in <content:encoded>, so every writeup can
be rendered as a real page on 0xsponge.me instead of being fetched in the
browser through a chain of CORS proxies.

The feed only ever returns the latest 10 posts, so posts/index.json is merged
rather than overwritten: once a writeup is mirrored it stays mirrored.

    python3 scripts/build_blog.py [--force]

--force re-renders pages that already exist (use after editing the template).
"""

import json
import os
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

FEED_URL = 'https://0xsponge.medium.com/feed'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(ROOT, 'posts')
INDEX_PATH = os.path.join(POSTS_DIR, 'index.json')
NS = {'content': 'http://purl.org/rss/1.0/modules/content/'}

# Medium emits a narrow set of tags; everything else is dropped rather than
# trusted, since the markup is pulled from a third party at build time.
ALLOWED = {
    'p', 'br', 'hr', 'h2', 'h3', 'h4', 'strong', 'b', 'em', 'i', 'u', 'del',
    'code', 'pre', 'blockquote', 'ul', 'ol', 'li', 'a', 'img', 'figure',
    'figcaption', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
}
VOID = {'br', 'hr', 'img'}
ALLOWED_ATTRS = {
    'a': {'href', 'title'},
    'img': {'src', 'alt'},
}

# Medium closes every feed item with a 1px view-counter and a "was originally
# published in ..." footer. The pixel would phone home from this domain (and
# renders as a broken image), and the footer duplicates the canonical note the
# template already prints.
TRACKER_SRC = re.compile(r'https?://medium\.com/_/stat', re.I)
MEDIUM_FOOTER = re.compile(
    r'\s*(?:<hr>)?\s*<p>(?:(?!</p>).)*?was originally published in(?:(?!</p>).)*?</p>\s*$',
    re.S | re.I,
)


class Sanitizer(HTMLParser):
    """Allowlist filter. Drops unknown tags, every event handler and any
    non-http(s) URL, and keeps the tag stack balanced."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.stack = []

    def _attrs(self, tag, attrs):
        keep = ALLOWED_ATTRS.get(tag, set())
        parts = []
        for name, value in attrs:
            if name not in keep or not value:
                continue
            if name in ('href', 'src') and not re.match(r'^https?://', value):
                continue
            parts.append(' %s="%s"' % (name, escape(value)))
        return ''.join(parts)

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED:
            return
        if tag == 'img' and any(n == 'src' and TRACKER_SRC.match(v or '') for n, v in attrs):
            return
        rendered = self._attrs(tag, attrs)
        if tag == 'a':
            rendered += ' target="_blank" rel="noopener noreferrer"'
        elif tag == 'img':
            rendered += ' loading="lazy"'
        if tag in VOID:
            self.out.append('<%s%s>' % (tag, rendered))
        else:
            self.out.append('<%s%s>' % (tag, rendered))
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in ALLOWED:
            self.out.append('<%s%s>' % (tag, self._attrs(tag, attrs)))

    def handle_endtag(self, tag):
        if tag in ALLOWED and tag not in VOID and tag in self.stack:
            # close anything Medium left open inside this element
            while self.stack:
                open_tag = self.stack.pop()
                self.out.append('</%s>' % open_tag)
                if open_tag == tag:
                    break

    def handle_data(self, data):
        self.out.append(escape(data, quotes=False))

    def result(self):
        while self.stack:
            self.out.append('</%s>' % self.stack.pop())
        return ''.join(self.out)


def escape(s, quotes=True):
    s = str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return s.replace('"', '&quot;').replace("'", '&#39;') if quotes else s


# ---------------------------------------------------------------------------
# Code blocks
#
# Medium ships <pre> as undifferentiated text. These blocks are the substance
# of a writeup, so they get an editor frame and are highlighted here rather
# than by a CDN highlighter at runtime: the pages stay static, and a payload is
# never re-parsed in the reader's browser. Every token is escaped on the way
# out, so the rendered text is byte-identical to the source.
# ---------------------------------------------------------------------------

KEYWORDS = {
    'javascript': ('const let var function return if else for while new await async await class '
                   'this typeof null undefined true false throw try catch import export default'),
    'python': ('def class return if elif else for while import from as with try except raise '
               'lambda None True False and or not in is pass yield global'),
    'bash': ('sudo curl wget cat grep awk sed echo chmod chown cd ls rm cp mv export set '
             'nmap ffuf gobuster nc ssh python3 git docker if then fi for do done'),
    'http': 'GET POST PUT PATCH DELETE HEAD OPTIONS TRACE CONNECT HTTP',
    'json': 'true false null',
    'sql': ('select from where union all order by group insert update delete drop table '
            'and or not like limit offset join on as'),
    'php': ('function return if else elseif foreach for while echo print new class public '
            'private protected static try catch throw require include define true false null'),
    'text': '',
    'html': '',
}

LANG_LABEL = {
    'javascript': 'javascript', 'python': 'python', 'bash': 'shell', 'http': 'http',
    'json': 'json', 'sql': 'sql', 'php': 'php', 'html': 'html', 'text': 'text',
}


def detect_lang(code):
    head = code.lstrip()
    first = head.split('\n', 1)[0]

    if re.match(r'^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+\S+|^HTTP/\d', first):
        return 'http'
    if re.match(r'^[\[{]', head) and re.search(r'"\s*:', head):
        return 'json'
    if re.search(r'<\?php|\$\w+\s*=|->\w+\(|\becho\s', head):
        return 'php'
    if re.search(r'\b(SELECT|UNION\s+SELECT|INSERT\s+INTO|DROP\s+TABLE)\b', head, re.I):
        return 'sql'
    if re.search(r'\b(const|let|var|function|=>|document\.|window\.|console\.)', head):
        return 'javascript'
    if re.search(r'^\s*(def|class|import|from)\s|\bprint\(', head, re.M):
        return 'python'
    if re.match(r'^[$#]\s|\b(curl|sudo|nmap|ffuf|gobuster|chmod|wget|grep)\b', head):
        return 'bash'
    if re.match(r'^\s*<[a-zA-Z/!]', head):
        return 'html'
    return 'text'


def highlight(code, lang):
    """Single-pass tokenizer. Anything unmatched is emitted as escaped text,
    so no input can be dropped or reordered."""
    words = KEYWORDS.get(lang, '').split()
    rules = []

    # one comment rule per language — PHP takes both styles
    comment = []
    if lang in ('bash', 'python', 'php'):
        comment.append(r'^[ \t]*#[^\n]*')
    if lang in ('javascript', 'sql', 'php'):
        comment.append(r'(?<!:)//[^\n]*|/\*.*?\*/')
    if comment:
        rules.append(('cm', '|'.join(comment)))
    if lang == 'http':
        # header names, before anything else can claim the colon
        rules.append(('at', r'^[A-Za-z][A-Za-z-]*(?=:\s)'))

    rules += [
        ('st', r'"(?:[^"\\\n]|\\.)*"' + r"|'(?:[^'\\\n]|\\.)*'"),
        ('ur', r'https?://[^\s"\'<>()]+'),
        ('nu', r'\b\d+(?:\.\d+)?\b'),
    ]
    if words:
        rules.append(('kw', r'\b(?:%s)\b' % '|'.join(re.escape(w) for w in words)))
    rules += [
        ('fn', r'\b[A-Za-z_]\w*(?=\()'),
        ('op', r'[=<>!+\-*/%&|^~?:;,.(){}\[\]]'),
    ]

    scanner = re.compile('|'.join('(?P<%s>%s)' % r for r in rules), re.S | re.M)

    out, pos = [], 0
    for m in scanner.finditer(code):
        if m.start() > pos:
            out.append(escape(code[pos:m.start()], quotes=False))
        out.append('<span class="t-%s">%s</span>' % (m.lastgroup, escape(m.group(), quotes=False)))
        pos = m.end()
    out.append(escape(code[pos:], quotes=False))
    return ''.join(out)


def unescape(s):
    return (s.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
             .replace('&#39;', "'").replace('&nbsp;', ' ').replace('&amp;', '&'))


PRE_RE = re.compile(r'<pre>(.*?)</pre>', re.S)


def decorate_code(html):
    """Wrap every <pre> in an editor frame and highlight its contents."""

    def one(m):
        inner = m.group(1)
        # a block carrying its own markup is framed but left untouched
        if re.search(r'<(?!br\s*/?>)[a-zA-Z]', inner):
            body, lang = inner, 'text'
        else:
            code = unescape(re.sub(r'<br\s*/?>', '\n', inner))
            lang = detect_lang(code)
            body = highlight(code, lang)

        return (
            '<div class="code-block" data-lang="%s">'
            '<div class="code-bar"><span class="dots"></span>'
            '<span class="code-lang">%s</span>'
            '<button class="code-copy" type="button">copy</button></div>'
            '<pre>%s</pre></div>'
        ) % (lang, LANG_LABEL.get(lang, lang), body)

    return PRE_RE.sub(one, html)


def sanitize(html):
    p = Sanitizer()
    p.feed(html or '')
    p.close()
    out = MEDIUM_FOOTER.sub('', p.result())
    # the pixel usually sat inside its own <figure>, now empty
    out = re.sub(r'<figure>\s*</figure>', '', out).strip()
    return decorate_code(out)


def strip_tags(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html or '')).strip()


def slugify(title):
    s = unicodedata.normalize('NFKD', title or '').encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()
    return (s or 'post')[:70].strip('-')


def first_image(html):
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html or '', re.I)
    return m.group(1) if m else None


def clean_link(url):
    """Drop Medium's ?source=rss- tracking parameter."""
    return str(url or '').split('?')[0]


def reading_time(html):
    words = len(strip_tags(html).split())
    return max(1, round(words / 220))


def fetch_feed():
    req = urllib.request.Request(FEED_URL, headers={'User-Agent': 'Mozilla/5.0 (0xsponge.me blog mirror)'})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read()


def parse_feed(xml_bytes):
    channel = ET.fromstring(xml_bytes).find('./channel')
    posts = []
    for item in channel.findall('item'):
        encoded = item.find('content:encoded', NS)
        body = (encoded.text if encoded is not None else None) or item.findtext('description') or ''
        title = (item.findtext('title') or 'Untitled').strip()
        link = clean_link(item.findtext('link') or item.findtext('guid'))
        raw_date = item.findtext('pubDate') or ''
        try:
            published = parsedate_to_datetime(raw_date).astimezone(timezone.utc)
        except (TypeError, ValueError):
            published = datetime.now(timezone.utc)

        posts.append({
            'slug': slugify(title),
            'title': title,
            'medium_url': link,
            'date': published.strftime('%Y-%m-%d'),
            'date_label': published.strftime('%b %-d, %Y') if os.name != 'nt' else published.strftime('%b %d, %Y'),
            'tags': [c.text for c in item.findall('category') if c.text][:3],
            'excerpt': strip_tags(body)[:220].rstrip() + '…',
            'thumbnail': first_image(body),
            'minutes': reading_time(body),
            'body': sanitize(body),
        })
    return posts


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title_attr} — 0xSponge</title>
    <meta name="description" content="{excerpt_attr}">
    <meta name="author" content="Adham Khairy">
    <link rel="canonical" href="{medium_url}">
    <meta property="og:title" content="{title_attr}">
    <meta property="og:description" content="{excerpt_attr}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="https://0xsponge.me/posts/{slug}.html">
    <meta property="article:published_time" content="{date}">
    {og_image}<meta name="twitter:card" content="summary_large_image">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🧽</text></svg>">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="../style.css">
</head>
<body>
    <header class="site-header">
        <a class="brand" href="../index.html">0x<span>Sponge</span></a>
        <nav class="nav">
            <a href="../index.html">Home</a>
            <a href="../about.html">About</a>
            <a href="../blog.html" class="active">Blog</a>
            <a href="../contact.html">Contact</a>
        </nav>
    </header>

    <main>
        <a class="back-link" href="../blog.html">← All writeups</a>

        <article class="post">
            <h1 class="post-title">{title}</h1>
            <div class="post-meta">
                <span>{date_label}</span>
                <span>·</span>
                <span>{minutes} min read</span>
                {tags}
            </div>

            <div class="post-body">
{body}
            </div>

            <p class="post-origin">
                Originally published on
                <a href="{medium_url}" target="_blank" rel="noopener">Medium ↗</a>
            </p>
        </article>
    </main>

    <footer class="site-footer">
        <div class="socials">
            <a href="https://www.linkedin.com/in/0xsponge/" target="_blank" rel="noopener" aria-label="LinkedIn profile">LinkedIn</a>
            <a href="https://hackerone.com/0xadham?type=user" target="_blank" rel="noopener" aria-label="HackerOne profile">HackerOne</a>
        </div>
        <p>© 2026 Adham Khairy (0xSponge) · All rights reserved</p>
    </footer>

    <script src="../app.js"></script>
</body>
</html>
"""


def render(post):
    tags = ''
    if post['tags']:
        chips = ''.join('<span class="blog-tag">%s</span>' % escape(t) for t in post['tags'])
        tags = '<div class="blog-tags">%s</div>' % chips
    og_image = ''
    if post['thumbnail']:
        og_image = '<meta property="og:image" content="%s">\n    ' % escape(post['thumbnail'])
    return PAGE.format(
        title=escape(post['title']),
        title_attr=escape(post['title']),
        excerpt_attr=escape(post['excerpt'][:160]),
        slug=post['slug'],
        date=post['date'],
        date_label=escape(post['date_label']),
        minutes=post['minutes'],
        medium_url=escape(post['medium_url']),
        og_image=og_image,
        tags=tags,
        body=post['body'],
    )


def main():
    force = '--force' in sys.argv
    os.makedirs(POSTS_DIR, exist_ok=True)

    try:
        existing = {p['slug']: p for p in json.load(open(INDEX_PATH, encoding='utf-8'))}
    except (OSError, ValueError):
        existing = {}

    posts = parse_feed(fetch_feed())
    print('feed: %d posts' % len(posts))

    added = updated = 0
    for post in posts:
        path = os.path.join(POSTS_DIR, post['slug'] + '.html')
        page = render(post)
        is_new = post['slug'] not in existing
        if not os.path.exists(path):
            changed = True
        else:
            changed = force or open(path, encoding='utf-8').read() != page
        if changed:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(page)
            if is_new:
                added += 1
                print('  + %s' % post['slug'])
            else:
                updated += 1
                print('  ~ %s' % post['slug'])

        meta = {k: v for k, v in post.items() if k != 'body'}
        meta['url'] = 'posts/%s.html' % post['slug']
        existing[post['slug']] = meta

    index = sorted(existing.values(), key=lambda p: p['date'], reverse=True)
    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
        f.write('\n')

    print('index: %d posts (%d new, %d updated)' % (len(index), added, updated))


if __name__ == '__main__':
    main()
