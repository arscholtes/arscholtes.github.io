#!/usr/bin/env python3
"""Builds the blog: each Markdown post in posts/ becomes blog/<slug>/index.html, with an index and an RSS feed.

Usage: python3 tools/build-blog.py [--posts DIR] [--out DIR] [--site URL]

Everything in blog/ is generated. Edit the posts, then run this again.
"""

import argparse
import datetime
import html
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://arscholtes.github.io"
POST_SUFFIXES = (".md", ".markdown")
GENERATED_FILES = {"index.html", "feed.xml"}

FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
YOUTUBE = re.compile(r"^https?://(?:www\.)?(?:youtu\.be/|youtube\.com/watch\?v=|youtube\.com/shorts/)([\w-]{11})(?:[?&#]\S*)?$")
FENCE = "```"
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET = re.compile(r"^[-*]\s+(.*)$")
NUMBERED = re.compile(r"^\d+\.\s+(.*)$")
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
SAFE_SCHEMES = ("http:", "https:", "mailto:")

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wdth,wght@12..96,75..100,400;'
    "12..96,75..100,700;12..96,75..100,800&family=Public+Sans:ital,wght@0,400;0,500;0,600;1,400&"
    'family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">'
)


@dataclass(frozen=True)
class Post:
    """One post: where it lives, what it is called, when, and its Markdown body."""

    slug: str
    title: str
    date: datetime.date
    summary: str
    body: str


def parse_post(text: str, name: str) -> Post:
    """Read a post file's front matter and body.

    @param text the file's contents
    @param name the file's name, which gives the slug and names the file in errors
    @return the post
    """
    match = FRONT_MATTER.match(text.replace("\r\n", "\n"))
    if not match:
        raise ValueError(f"{name}: no front matter; a post starts with --- lines holding title and date")
    fields = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"{name}: front matter line {line!r} is not 'key: value'")
        fields[key.strip()] = value.strip()
    if not fields.get("title"):
        raise ValueError(f"{name}: front matter has no title")
    try:
        date = datetime.date.fromisoformat(fields.get("date", ""))
    except ValueError:
        raise ValueError(f"{name}: front matter date {fields.get('date')!r} is not YYYY-MM-DD") from None
    slug = Path(name).stem
    if not SLUG.match(slug):
        raise ValueError(f"{name}: the file name becomes the address, so use lowercase letters, digits and hyphens")
    return Post(slug, fields["title"], date, fields.get("summary", ""), match.group(2))


def _safe_url(url: str) -> bool:
    return not SCHEME.match(url) or url.lower().startswith(SAFE_SCHEMES)


def _trim_url(url: str) -> tuple[str, str]:
    """Split trailing punctuation and escaped quotes off a bare URL; they end the sentence, not the link."""
    tail = ""
    while True:
        for end in ("&quot;", "&#x27;", ".", ",", ";", ":", "!", "?", ")"):
            if url.endswith(end):
                url, tail = url[: -len(end)], end + tail
                break
        else:
            return url, tail


def _emphasis(text: str) -> str:
    text = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![*\w])\*(?=\S)(.+?)(?<=\S)\*(?![*\w])", r"<em>\1</em>", text)
    return re.sub(r"(?<![_\w])_(?=\S)(.+?)(?<=\S)_(?![_\w])", r"<em>\1</em>", text)


def render_inline(text: str) -> str:
    """Render one block's text: code, images, links, bare URLs, then emphasis. Any HTML in it shows as text.

    @param text Markdown text with no block structure
    @return HTML
    """
    held: list[str] = []

    def hold(fragment: str) -> str:
        held.append(fragment)
        return f"\x00{len(held) - 1}\x00"

    text = re.sub(r"`([^`]+)`", lambda m: hold(f"<code>{html.escape(m.group(1), quote=False)}</code>"), text)
    text = html.escape(text)

    def image(m: re.Match) -> str:
        alt, src = m.group(1), m.group(2)
        return hold(f'<img src="{src}" alt="{alt}">') if _safe_url(html.unescape(src)) else alt

    def link(m: re.Match) -> str:
        label, href = _emphasis(m.group(1)), m.group(2)
        return hold(f'<a href="{href}">{label}</a>') if _safe_url(html.unescape(href)) else label

    def bare(m: re.Match) -> str:
        url, tail = _trim_url(m.group(0))
        return hold(f'<a href="{url}">{url}</a>') + tail

    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", image, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)
    text = re.sub(r"https?://[^\s\x00]+", bare, text)
    text = _emphasis(text)
    while "\x00" in text:
        text = re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], text)
    return text


def _video(video_id: str) -> str:
    return (
        '<figure class="video">'
        f'<iframe src="https://www.youtube-nocookie.com/embed/{video_id}" title="YouTube video" loading="lazy" '
        'referrerpolicy="strict-origin-when-cross-origin" '
        'allow="accelerometer; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>'
        f'<figcaption><a href="https://youtu.be/{video_id}">Watch on YouTube</a></figcaption>'
        "</figure>"
    )


def _starts_block(line: str) -> bool:
    return bool(line.startswith((FENCE, ">")) or HEADING.match(line) or BULLET.match(line) or NUMBERED.match(line))


def render_markdown(md: str) -> str:
    """Render the Markdown a build post needs: paragraphs, headings, lists, quotes, code blocks and videos.

    @param md the post's body
    @return HTML, one block per line
    """
    lines = md.replace("\r\n", "\n").strip("\n").split("\n")
    blocks: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith(FENCE):
            lang = line[len(FENCE):].strip()
            end = i + 1
            while end < len(lines) and not lines[end].startswith(FENCE):
                end += 1
            if end == len(lines):
                raise ValueError(f"the code block opened on line {i + 1} is never closed with {FENCE}")
            code = html.escape("\n".join(lines[i + 1 : end]), quote=False)
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            blocks.append(f"<pre><code{cls}>{code}</code></pre>")
            i = end + 1
        elif heading := HEADING.match(line):
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{render_inline(heading.group(2).strip())}</h{level}>")
            i += 1
        elif line.startswith(">"):
            quoted = []
            while i < len(lines) and lines[i].startswith(">"):
                quoted.append(lines[i][1:].removeprefix(" "))
                i += 1
            blocks.append(f"<blockquote>{render_markdown(chr(10).join(quoted))}</blockquote>")
        elif BULLET.match(line) or NUMBERED.match(line):
            pattern, tag = (BULLET, "ul") if BULLET.match(line) else (NUMBERED, "ol")
            items = []
            while i < len(lines) and (item := pattern.match(lines[i])):
                items.append(f"<li>{render_inline(item.group(1))}</li>")
                i += 1
            blocks.append(f"<{tag}>\n" + "\n".join(items) + f"\n</{tag}>")
        else:
            paragraph = []
            while i < len(lines) and lines[i].strip() and not (paragraph and _starts_block(lines[i])):
                paragraph.append(lines[i])
                i += 1
            video = YOUTUBE.match(paragraph[0].strip()) if len(paragraph) == 1 else None
            blocks.append(_video(video.group(1)) if video else f"<p>{render_inline(chr(10).join(paragraph))}</p>")
    return "\n".join(blocks)


def _long_date(date: datetime.date) -> str:
    return f"{date.day} {date:%B %Y}"


def _page(title: str, description: str, root: str, content: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="alternate" type="application/rss+xml" title="Alex Scholtes: blog" href="{root}blog/feed.xml">
{FONTS}
<link rel="stylesheet" href="{root}styles.css">
</head>
<body>
<main class="blog">
  <div class="wrap">
{content}
  </div>
</main>
</body>
</html>
"""


def post_page(post: Post) -> str:
    """@param post the post @return its page, which sits two folders below the site's root"""
    nav = '    <nav class="blog-nav"><a href="../../">Alex Scholtes</a><span class="sep">/</span><a href="../">Blog</a></nav>'
    article = (
        '    <article class="post">\n'
        f'      <p class="eyebrow"><time datetime="{post.date.isoformat()}">{_long_date(post.date)}</time></p>\n'
        f"      <h1>{html.escape(post.title)}</h1>\n"
        f"{render_markdown(post.body)}\n"
        "    </article>"
    )
    return _page(f"{post.title} — Alex Scholtes", post.summary or post.title, "../../", f"{nav}\n{article}")


def index_page(posts: list[Post]) -> str:
    """@param posts every post, newest first @return the blog's front page, one folder below the site's root"""
    nav = '    <nav class="blog-nav"><a href="../">Alex Scholtes</a></nav>'
    if posts:
        items = "\n".join(
            f'      <li><a href="{p.slug}/"><time datetime="{p.date.isoformat()}">{_long_date(p.date)}</time>'
            f'<span class="post-list-title">{html.escape(p.title)}</span></a>'
            + (f"<p>{html.escape(p.summary)}</p>" if p.summary else "")
            + "</li>"
            for p in posts
        )
        listing = f'    <ol class="post-list">\n{items}\n    </ol>'
    else:
        listing = '    <p class="lede">No posts yet.</p>'
    return _page("Blog — Alex Scholtes", "Posts by Alex Scholtes.", "../", f'{nav}\n    <h1 class="blog-title">Blog</h1>\n{listing}')


def feed(posts: list[Post], site: str) -> str:
    """@param posts every post, newest first @param site the site's address @return an RSS 2.0 feed"""

    def text(value: str) -> str:
        return html.escape(value, quote=False)

    items = "".join(
        "<item>"
        f"<title>{text(p.title)}</title>"
        f"<link>{site}/blog/{p.slug}/</link>"
        f"<guid>{site}/blog/{p.slug}/</guid>"
        f"<pubDate>{format_datetime(datetime.datetime(p.date.year, p.date.month, p.date.day, tzinfo=datetime.UTC))}</pubDate>"
        f"<description>{text(p.summary)}</description>"
        "</item>\n"
        for p in posts
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<rss version="2.0"><channel>\n'
        "<title>Alex Scholtes: blog</title>\n"
        f"<link>{site}/blog/</link>\n"
        "<description>Posts by Alex Scholtes.</description>\n"
        f"{items}"
        "</channel></rss>\n"
    )


def _check_generated(out_dir: Path) -> None:
    """Refuse to replace a folder holding anything this script would not have written."""
    for entry in out_dir.iterdir():
        ours = entry.name in GENERATED_FILES if entry.is_file() else {c.name for c in entry.iterdir()} <= {"index.html"}
        if not ours:
            raise ValueError(f"{entry} was not written by build-blog.py, so {out_dir} is not replaced; move it out first")


def build(posts_dir: Path, out_dir: Path, site: str) -> list[Post]:
    """Write every post's page, the index and the feed into out_dir, replacing what was there.

    @param posts_dir where the Markdown posts are; a missing folder means no posts yet
    @param out_dir the blog folder to write
    @param site the site's address, for the feed's links
    @return the posts, newest first
    """
    posts: list[Post] = []
    files: dict[str, Path] = {}
    paths = sorted(p for p in posts_dir.iterdir() if p.suffix in POST_SUFFIXES) if posts_dir.exists() else []
    for path in paths:
        post = parse_post(path.read_text(encoding="utf-8"), path.name)
        if post.slug in files:
            raise ValueError(f"{files[post.slug].name} and {path.name} would both be blog/{post.slug}/")
        files[post.slug] = path
        posts.append(post)
    posts.sort(key=lambda p: (p.date, p.slug), reverse=True)

    pages = {}
    for post in posts:
        try:
            pages[post.slug] = post_page(post)
        except ValueError as error:
            raise ValueError(f"{files[post.slug].name}: {error}") from None

    staging = Path(tempfile.mkdtemp(prefix="blog-", dir=out_dir.parent))
    try:
        for slug, page in pages.items():
            (staging / slug).mkdir()
            (staging / slug / "index.html").write_text(page, encoding="utf-8")
        (staging / "index.html").write_text(index_page(posts), encoding="utf-8")
        (staging / "feed.xml").write_text(feed(posts, site), encoding="utf-8")
        if out_dir.exists():
            _check_generated(out_dir)
            shutil.rmtree(out_dir)
        staging.rename(out_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return posts


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--posts", type=Path, default=ROOT / "posts")
    parser.add_argument("--out", type=Path, default=ROOT / "blog")
    parser.add_argument("--site", default=SITE)
    args = parser.parse_args(argv)
    posts = build(args.posts, args.out, args.site.rstrip("/"))
    print(f"wrote {len(posts)} post{'s' if len(posts) != 1 else ''}, the index and the feed to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
