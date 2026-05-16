from __future__ import annotations

from pathlib import Path

import pytest

from sealedx.packaging.builder import package
from sealedx.packaging.registry import (
    list_packages,
    load_package,
    read_input_schema,
    read_output_schema,
    read_prompt,
)
from sealedx.security.hashing import hash_canonical_json, hash_text


def test_package_creation_and_hashing(video_planner_paths):
    pkg = package(
        name="immersive-video-planner",
        version="0.1.0",
        prompt_path=video_planner_paths["prompt"],
        input_schema_path=video_planner_paths["input_schema"],
        output_schema_path=video_planner_paths["output_schema"],
        publisher="AITrekker",
        license="Apache-2.0",
    )
    assert pkg.package_id.startswith("pkg_")
    assert pkg.prompt_hash == hash_text(video_planner_paths["prompt"].read_text())

    import json

    schema = json.loads(video_planner_paths["input_schema"].read_text())
    assert pkg.input_schema_hash == hash_canonical_json(schema)


def test_package_roundtrip(video_planner_paths):
    pkg = package(
        name="immersive-video-planner",
        version="0.1.0",
        prompt_path=video_planner_paths["prompt"],
        input_schema_path=video_planner_paths["input_schema"],
        output_schema_path=video_planner_paths["output_schema"],
    )
    loaded = load_package(pkg.package_id)
    assert loaded == pkg
    assert loaded.prompt_hash == pkg.prompt_hash


def test_list_packages_finds_created(video_planner_paths):
    pkg = package(
        name="immersive-video-planner",
        version="0.1.0",
        prompt_path=video_planner_paths["prompt"],
        input_schema_path=video_planner_paths["input_schema"],
        output_schema_path=video_planner_paths["output_schema"],
    )
    listed = list_packages()
    assert pkg.package_id in {p.package_id for p in listed}


def test_invalid_input_schema_rejected(tmp_path: Path, video_planner_paths):
    bad = tmp_path / "bad-input.schema.json"
    bad.write_text('{"type": "not-a-real-type"}')
    with pytest.raises(ValueError, match="input schema"):
        package(
            name="bad",
            version="0.0.1",
            prompt_path=video_planner_paths["prompt"],
            input_schema_path=bad,
            output_schema_path=video_planner_paths["output_schema"],
        )


def test_artifacts_readable_after_package(video_planner_paths):
    pkg = package(
        name="immersive-video-planner",
        version="0.1.0",
        prompt_path=video_planner_paths["prompt"],
        input_schema_path=video_planner_paths["input_schema"],
        output_schema_path=video_planner_paths["output_schema"],
    )
    assert read_prompt(pkg.package_id).strip().startswith("You are")
    assert read_input_schema(pkg.package_id)["type"] == "object"
    assert read_output_schema(pkg.package_id)["type"] == "object"
