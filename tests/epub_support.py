from __future__ import annotations

from pathlib import Path

from ebooklib import epub


def make_epub(
    path: Path,
    *,
    with_navigation: bool = True,
    nested_navigation: bool = False,
    duplicate_visible_titles: bool = False,
    include_empty_spine_item: bool = False,
    chapter_one_suffix: str = "",
    language: str | None = "en",
) -> None:
    book = epub.EpubBook()
    book.set_identifier("demo-id")
    book.set_title("Demo Book")
    if language is not None:
        book.set_language(language)
    book.add_author("A. Author")
    book.add_metadata("DC", "publisher", "Demo Press")

    chapter_one = epub.EpubHtml(title="One", file_name="c1.xhtml", lang="en")
    chapter_one.content = (
        "<html><head><style>.italic { font-style: italic; }</style></head>"
        "<body><h1>One</h1><h2>Opening</h2>"
        "<p>Hello, 世界, <em>emphasis</em> and <strong>strong</strong>, "
        '<span style="font-style: italic">CSS emphasis</span>, '
        '<a href="https://example.test"><em>linked text</em></a>.' + chapter_one_suffix + "</p>"
        "<hr/><p>After the break.</p></body></html>"
    )
    chapter_two = epub.EpubHtml(
        title="One" if duplicate_visible_titles else "Two",
        file_name="c2.xhtml",
        lang="en",
    )
    chapter_two.content = "<html><body><h1>Two</h1><p>World.</p></body></html>"
    book.add_item(chapter_one)
    book.add_item(chapter_two)
    spine = [chapter_one, chapter_two]

    if include_empty_spine_item:
        empty_chapter = epub.EpubHtml(
            title="",
            file_name="empty.xhtml",
            lang="en",
        )
        empty_chapter.content = "<html><body><div></div></body></html>"
        book.add_item(empty_chapter)
        spine.insert(1, empty_chapter)
    if nested_navigation:
        chapter_three = epub.EpubHtml(title="Three", file_name="c3.xhtml", lang="en")
        chapter_three.content = "<html><body><h1>Three</h1><p>Third.</p></body></html>"
        book.add_item(chapter_three)
        spine.append(chapter_three)

    if with_navigation:
        book.add_item(epub.EpubNav())
        if nested_navigation:
            book.toc = (
                (
                    epub.Section("Part One", "c1.xhtml"),
                    (
                        epub.Link("c1.xhtml", "One", "one"),
                        epub.Link(
                            "c2.xhtml",
                            "One" if duplicate_visible_titles else "Two",
                            "two",
                        ),
                    ),
                ),
                epub.Link("c3.xhtml", "Three", "three"),
            )
        else:
            book.toc = (
                epub.Link("c1.xhtml", "One", "one"),
                epub.Link(
                    "c2.xhtml",
                    "One" if duplicate_visible_titles else "Two",
                    "two",
                ),
            )
        book.spine = ["nav", *spine]
    else:
        book.add_item(epub.EpubNcx())
        book.spine = spine

    epub.write_epub(str(path), book)
