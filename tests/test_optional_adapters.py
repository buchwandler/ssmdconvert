from pathlib import Path

import pytest

from ssmdconvert import Converter


def test_docx_adapter_when_dependency_is_available(tmp_path: Path) -> None:
    docx = pytest.importorskip("docx")
    source = tmp_path / "sample.docx"
    document = docx.Document()
    document.core_properties.title = "DOCX Demo"
    document.add_heading("Chapter", level=1)
    document.add_paragraph("Hello world.")
    document.save(source)
    result = Converter().convert(source)
    assert result.document.metadata["title"] == "DOCX Demo"
    assert "# Chapter" in result.ssmd
    assert "Hello world." in result.ssmd
