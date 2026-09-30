"""Shared EPUB chapter extraction options."""

from epub2text import ChapterMarkdownOptions


def default_epub_chapter_options() -> ChapterMarkdownOptions:
    return ChapterMarkdownOptions(
        include_title=False,
        minimum_body_heading_level=2,
        preserve_emphasis=True,
        preserve_strong=True,
        link_mode="preserve",
        code_mode="preserve",
        resolve_css_emphasis=True,
        preserve_scene_breaks=True,
    )
