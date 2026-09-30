from .base import InputAdapter
from .docx import DocxAdapter
from .epub import EpubAdapter
from .html import HtmlAdapter
from .markdown import MarkdownAdapter
from .pdf import PdfAdapter
from .ssmd import SsmdAdapter
from .text import TextAdapter


def default_adapters() -> list[InputAdapter]:
    # Specific formats first; TXT is deliberately last.
    return [
        SsmdAdapter(),
        EpubAdapter(),
        MarkdownAdapter(),
        HtmlAdapter(),
        PdfAdapter(),
        DocxAdapter(),
        TextAdapter(),
    ]


__all__ = [
    "DocxAdapter",
    "EpubAdapter",
    "HtmlAdapter",
    "InputAdapter",
    "MarkdownAdapter",
    "PdfAdapter",
    "SsmdAdapter",
    "TextAdapter",
    "default_adapters",
]
