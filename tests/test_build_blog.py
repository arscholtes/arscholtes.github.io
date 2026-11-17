"""Tests for tools/build-blog.py: Markdown posts in, static blog pages and a feed out."""

import datetime
import importlib.util
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "posts"
SITE = "https://arscholtes.github.io"

_spec = importlib.util.spec_from_file_location("build_blog", ROOT / "tools" / "build-blog.py")
blog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(blog)

POST = """---
title: Why the carrot page says add olive oil
date: 2026-11-17
summary: Two facts and one line.
---
Body text.
"""


class ParsePost(unittest.TestCase):
    def test_front_matter_gives_title_date_summary_and_the_file_name_gives_the_slug(self):
        post = blog.parse_post(POST, "carrot-olive-oil.md")
        self.assertEqual(post.slug, "carrot-olive-oil")
        self.assertEqual(post.title, "Why the carrot page says add olive oil")
        self.assertEqual(post.date, datetime.date(2026, 11, 17))
        self.assertEqual(post.summary, "Two facts and one line.")
        self.assertEqual(post.body.strip(), "Body text.")

    def test_a_post_without_a_title_is_refused_by_name(self):
        with self.assertRaisesRegex(ValueError, "no-title.md.*title"):
            blog.parse_post("---\ndate: 2026-11-17\n---\nText\n", "no-title.md")

    def test_a_post_without_front_matter_is_refused_by_name(self):
        with self.assertRaisesRegex(ValueError, "bare.md"):
            blog.parse_post("Just text\n", "bare.md")

    def test_a_date_that_is_not_a_date_is_refused_by_name(self):
        with self.assertRaisesRegex(ValueError, "bad-date.md.*date"):
            blog.parse_post("---\ntitle: T\ndate: Tuesday\n---\nText\n", "bad-date.md")


class RenderMarkdown(unittest.TestCase):
    def test_paragraphs_are_split_on_blank_lines(self):
        self.assertEqual(blog.render_markdown("One.\n\nTwo."), "<p>One.</p>\n<p>Two.</p>")

    def test_headings(self):
        self.assertEqual(blog.render_markdown("## What broke\n\n### Why"), "<h2>What broke</h2>\n<h3>Why</h3>")

    def test_emphasis_strong_and_inline_code(self):
        self.assertEqual(
            blog.render_markdown("A *small* and **big** `word_similarity` call."),
            "<p>A <em>small</em> and <strong>big</strong> <code>word_similarity</code> call.</p>",
        )

    def test_markdown_inside_inline_code_is_left_alone(self):
        self.assertEqual(blog.render_markdown("Run `a *b* c`."), "<p>Run <code>a *b* c</code>.</p>")

    def test_links_and_images(self):
        self.assertEqual(
            blog.render_markdown("See [the repo](https://github.com/arscholtes/nutridex) and ![a carrot](carrot.png)."),
            '<p>See <a href="https://github.com/arscholtes/nutridex">the repo</a> and <img src="carrot.png" alt="a carrot">.</p>',
        )

    def test_a_bare_link_in_a_sentence_becomes_a_link(self):
        self.assertEqual(
            blog.render_markdown("Try it at https://nutridex-8vtr.vercel.app today."),
            '<p>Try it at <a href="https://nutridex-8vtr.vercel.app">https://nutridex-8vtr.vercel.app</a> today.</p>',
        )

    def test_html_in_a_post_is_shown_as_text(self):
        self.assertEqual(
            blog.render_markdown('Text with <script>alert("x")</script> & more.'),
            "<p>Text with &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; more.</p>",
        )

    def test_a_link_cannot_run_script(self):
        self.assertNotIn("javascript:", blog.render_markdown("[click](javascript:alert(1))"))

    def test_unordered_and_ordered_lists(self):
        self.assertEqual(blog.render_markdown("- one\n- two"), "<ul>\n<li>one</li>\n<li>two</li>\n</ul>")
        self.assertEqual(blog.render_markdown("1. first\n2. second"), "<ol>\n<li>first</li>\n<li>second</li>\n</ol>")

    def test_fenced_code_keeps_its_text_escaped_and_unformatted(self):
        self.assertEqual(
            blog.render_markdown("```sql\nselect word_similarity('tumeric', name) < 0.4 *x*\n```"),
            "<pre><code class=\"language-sql\">select word_similarity('tumeric', name) &lt; 0.4 *x*</code></pre>",
        )

    def test_blockquote(self):
        self.assertEqual(blog.render_markdown("> A quote."), "<blockquote><p>A quote.</p></blockquote>")

    def test_a_youtube_link_on_its_own_line_becomes_a_video(self):
        for url in ("https://youtu.be/-pwyPnAWb2U", "https://www.youtube.com/watch?v=-pwyPnAWb2U", "https://youtube.com/shorts/-pwyPnAWb2U"):
            html = blog.render_markdown(url)
            self.assertIn('src="https://www.youtube-nocookie.com/embed/-pwyPnAWb2U"', html, url)
            self.assertIn('href="https://youtu.be/-pwyPnAWb2U"', html, url)

    def test_a_youtube_link_inside_a_sentence_stays_a_link(self):
        html = blog.render_markdown("Watch https://youtu.be/-pwyPnAWb2U first.")
        self.assertNotIn("<iframe", html)
        self.assertIn('<a href="https://youtu.be/-pwyPnAWb2U">', html)


class Build(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.out)

    def test_each_post_gets_a_page_and_the_index_lists_them_newest_first(self):
        blog.build(FIXTURES, self.out, SITE)
        page = (self.out / "newer-post" / "index.html").read_text()
        self.assertIn("<h1>A newer post &amp; more</h1>", page)
        self.assertIn("<h2>What happened</h2>", page)
        self.assertIn("youtube-nocookie.com/embed/-pwyPnAWb2U", page)
        self.assertIn('href="../../styles.css"', page)
        index = (self.out / "index.html").read_text()
        self.assertIn('href="../styles.css"', index)
        self.assertLess(index.index("A newer post"), index.index("An older post"))
        self.assertIn('href="newer-post/"', index)
        self.assertIn("The second one, with &lt;angle&gt; brackets.", index)

    def test_the_feed_is_rss_with_one_item_per_post_newest_first(self):
        blog.build(FIXTURES, self.out, SITE)
        channel = ET.parse(self.out / "feed.xml").getroot().find("channel")
        items = channel.findall("item")
        self.assertEqual([i.findtext("title") for i in items], ["A newer post & more", "An older post"])
        self.assertEqual(items[0].findtext("link"), f"{SITE}/blog/newer-post/")
        self.assertEqual(items[0].findtext("guid"), f"{SITE}/blog/newer-post/")
        self.assertEqual(items[0].findtext("pubDate"), "Tue, 17 Nov 2026 00:00:00 +0000")
        self.assertEqual(channel.findtext("link"), f"{SITE}/blog/")

    def test_a_page_whose_post_was_deleted_is_removed(self):
        (self.out / "gone-post").mkdir()
        (self.out / "gone-post" / "index.html").write_text("old")
        self.assertTrue((self.out / "gone-post" / "index.html").exists())
        blog.build(FIXTURES, self.out, SITE)
        self.assertFalse((self.out / "gone-post").exists())

    def test_no_posts_still_builds_an_index_and_a_feed(self):
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty)
        blog.build(empty, self.out, SITE)
        self.assertTrue((self.out / "index.html").exists())
        self.assertEqual(ET.parse(self.out / "feed.xml").getroot().find("channel").findall("item"), [])

    def test_two_posts_with_one_slug_are_refused(self):
        twin = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, twin)
        (twin / "same.md").write_text(POST)
        (twin / "same.markdown").write_text(POST)
        with self.assertRaisesRegex(ValueError, "same"):
            blog.build(twin, self.out, SITE)


if __name__ == "__main__":
    unittest.main()
