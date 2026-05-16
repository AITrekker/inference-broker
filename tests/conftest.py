"""Test fixtures.

Every test gets its own ephemeral ``$SEALEDX_HOME`` so the local store under the user's
home directory is never touched. Tests run with no provider credentials.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_sealedx_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "sealedx_home"
    home.mkdir()
    monkeypatch.setenv("SEALEDX_HOME", str(home))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("SEALEDX_UNSAFE_DEBUG_PROMPT", raising=False)
    return home


@pytest.fixture
def examples_root() -> Path:
    return Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def video_planner_paths(examples_root: Path) -> dict[str, Path]:
    base = examples_root / "immersive-video-planner"
    return {
        "name": "immersive-video-planner",
        "prompt": base / "prompt.md",
        "input_schema": base / "input.schema.json",
        "output_schema": base / "output.schema.json",
        "input": base / "input.json",
    }
