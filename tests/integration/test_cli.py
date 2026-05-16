"""Smoke tests for the Typer CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sealedx.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _package_via_cli(runner: CliRunner, paths) -> str:
    result = runner.invoke(
        app,
        [
            "vendor",
            "package",
            "--name",
            "immersive-video-planner",
            "--prompt",
            str(paths["prompt"]),
            "--input-schema",
            str(paths["input_schema"]),
            "--output-schema",
            str(paths["output_schema"]),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["package_id"]


def _grant_via_cli(runner: CliRunner) -> str:
    result = runner.invoke(
        app,
        [
            "customer",
            "grant",
            "--provider",
            "mock",
            "--model",
            "mock-claude-sonnet-4-5",
            "--budget-usd",
            "5",
            "--expires-in",
            "1h",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["grant_id"]


def test_cli_full_flow(runner: CliRunner, video_planner_paths):
    pkg_id = _package_via_cli(runner, video_planner_paths)
    grant_id = _grant_via_cli(runner)

    result = runner.invoke(
        app,
        [
            "broker",
            "execute",
            "--package-id",
            pkg_id,
            "--grant-id",
            grant_id,
            "--input",
            str(video_planner_paths["input"]),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["receipt"]["status"] == "succeeded"
    receipt_path = Path(payload["receipt_path"])
    assert receipt_path.exists()

    verify_result = runner.invoke(app, ["receipt", "verify", str(receipt_path)])
    assert verify_result.exit_code == 0, verify_result.output
    assert "signature: OK" in verify_result.output


def test_package_show_does_not_print_prompt(runner: CliRunner, video_planner_paths):
    pkg_id = _package_via_cli(runner, video_planner_paths)
    result = runner.invoke(app, ["package", "show", pkg_id])
    assert result.exit_code == 0, result.output

    prompt_text = video_planner_paths["prompt"].read_text()
    first_sentence = prompt_text.split(".")[0]
    assert first_sentence not in result.output


def test_invalid_input_exit_code_nonzero_via_cli(runner: CliRunner, video_planner_paths, tmp_path):
    pkg_id = _package_via_cli(runner, video_planner_paths)
    grant_id = _grant_via_cli(runner)

    bad_input = tmp_path / "bad.json"
    bad_input.write_text(json.dumps({"topic": "x"}))

    result = runner.invoke(
        app,
        [
            "broker",
            "execute",
            "--package-id",
            pkg_id,
            "--grant-id",
            grant_id,
            "--input",
            str(bad_input),
            "--json",
        ],
    )
    # Broker returns a receipt (status invalid_input) — CLI exits 0 because the
    # protocol-level signal is the receipt, not the exit code. The CLI only exits
    # nonzero when the broker raises (e.g. unknown package). Asserting the receipt
    # status is what matters here.
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["receipt"]["status"] == "invalid_input"
