from pathlib import Path

from typer.testing import CliRunner

from ssmdconvert.cli import app

runner = CliRunner()


def test_direct_cli_conversion_is_local(tmp_path: Path) -> None:
    source = tmp_path / "book.txt"
    target = tmp_path / "book.ssmd"
    source.write_text("Hello.", encoding="utf-8")
    result = runner.invoke(app, ["convert", str(source), "-o", str(target)])
    assert result.exit_code == 0, result.output
    assert target.is_file()
    assert "no content was sent to JEV" in result.output


def test_enrich_requires_explicit_cloud_ack(tmp_path: Path) -> None:
    source = tmp_path / "book.ssmd"
    source.write_text('---\nssmd_version: "0.9"\n---\nHello.\n', encoding="utf-8")
    result = runner.invoke(app, ["enrich", str(source), "--speakers"])
    assert result.exit_code != 0
    assert "--yes-cloud" in result.output
