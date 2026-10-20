from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
from epub_support import make_epub
from typer.testing import CliRunner

from ssmdconvert import cli as cli_module
from ssmdconvert.cli import app

runner = CliRunner()


@pytest.mark.parametrize(
    "command",
    (
        ("report",),
        ("txt",),
        ("speech", "audit"),
        ("speech", "annotate"),
        ("speech", "freeze"),
        ("bundle", "convert"),
    ),
)
def test_analysis_cli_commands_expose_spacy_and_progress_flags(command: tuple[str, ...]) -> None:
    result = runner.invoke(app, [*command, "--help"])

    assert result.exit_code == 0, result.output
    assert "--spacy" in result.output
    assert "--progress" in result.output
    assert "--no-progress" in result.output


def test_report_progress_stays_on_stderr_and_no_progress_is_silent(tmp_path: Path) -> None:
    source = tmp_path / "sample.ssmd"
    source.write_text(
        '---\nssmd_version: "0.9"\nlanguage: en-US\n---\nMeasure 5 kg.\n',
        encoding="utf-8",
    )

    shown = runner.invoke(app, ["report", str(source), "--format", "json", "--progress"])

    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.stdout)["schema"] == "ssmdconvert.report.v1"
    assert "Starting Analysis cache" in shown.stderr
    assert "Completed: SSMD report complete" in shown.stderr

    hidden = runner.invoke(app, ["report", str(source), "--format", "json", "--no-progress"])

    assert hidden.exit_code == 0, hidden.output
    assert json.loads(hidden.stdout)["schema"] == "ssmdconvert.report.v1"
    assert hidden.stderr == ""


def test_auto_spacy_fallback_is_warned_even_when_progress_is_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "spacy", None)
    source = tmp_path / "sample.ssmd"
    source.write_text(
        '---\nssmd_version: "0.9"\nlanguage: en-US\n---\nMeasure 5 kg.\n',
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["report", str(source), "--format", "json", "--spacy", "auto", "--no-progress"],
    )

    assert result.exit_code == 0, result.output
    json.loads(result.stdout)
    assert "spaCy auto fallback for en-US" in result.stderr
    assert "Continuing without linguistic hints" in result.stderr


def test_missing_explicit_spacy_model_fails_cleanly_without_partial_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "spacy", None)
    source = tmp_path / "book.epub"
    output = tmp_path / "book.ssmd-bundle"
    make_epub(source)

    result = runner.invoke(
        app,
        ["bundle", "convert", str(source), "--output", str(output), "--spacy", "sm"],
    )

    assert result.exit_code == 1
    assert "Error: spaCy is required for --spacy sm" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""
    assert not output.exists()


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_progress_mode_respects_no_color_term_dumb_and_tty_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_module.sys, "stderr", _Tty())
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert cli_module._CliProgress(None).use_rich

    monkeypatch.setenv("NO_COLOR", "1")
    no_color = cli_module._CliProgress(None)
    assert no_color.enabled and not no_color.use_rich

    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("TERM", "dumb")
    dumb = cli_module._CliProgress(None)
    assert dumb.enabled and not dumb.use_rich

    monkeypatch.setattr(cli_module.sys, "stderr", io.StringIO())
    plain = cli_module._CliProgress(True)
    assert plain.enabled and not plain.use_rich
    assert not cli_module._CliProgress(False).enabled
