# -*- coding: utf-8 -*-
# Test suite for the "Download Artifact" composite GitHub Action.
# Testing library/framework: pytest (with optional PyYAML for structured YAML validation).
# ruff: noqa: S101

from pathlib import Path
import glob
import re
import pytest

def _find_download_artifact_action() -> Path:
    """
    Find the composite action file that matches:
      - name: Download Artifact
      - runs.using: composite
    Search common locations: .github/actions/**/action.yml|yaml, and fallbacks.
    """
    patterns = [
        ".github/actions/**/action.yml",
        ".github/actions/**/action.yaml",
        ".github/**/action.yml",
        ".github/**/action.yaml",
        "action.yml",
        "action.yaml",
    ]
    candidates = []
    for pat in patterns:
        for p in glob.glob(pat, recursive=True):
            fp = Path(p)
            try:
                text = fp.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "name: Download Artifact" in text and re.search(r"^\s*using:\s*composite\b", text, flags=re.M):
                candidates.append(fp)
    if not candidates:
        pytest.skip("Composite action 'Download Artifact' not found in the repository.")
    # Prefer actions living under .github/actions
    candidates.sort(key=lambda x: (0 if ".github/actions" in str(x) else 1, len(str(x))))
    return candidates[0]

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def _load_yaml_or_skip(path: Path):
    """
    Load YAML using PyYAML if available; otherwise skip structured tests.
    """
    yaml = pytest.importorskip("yaml", reason="PyYAML is required for structured validation of the action metadata.")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def _find_step_by_uses(steps, uses_prefix: str):
    for step in steps:
        if isinstance(step, dict) and isinstance(step.get("uses"), str) and step["uses"].startswith(uses_prefix):
            return step
    return None

def test_action_text_has_pinned_download_artifact_version_and_with_refs():
    """
    Text-level assertions that do not require a YAML parser.
    Ensures pinned version and correct 'with' input references are present.
    """
    action_path = _find_download_artifact_action()
    content = _read_text(action_path)

    assert "actions/download-artifact@v4.1.7" in content, "Action must pin actions/download-artifact to v4.1.7"
    assert "name: ${{ inputs.name }}" in content, "'with.name' must reference inputs.name"
    assert "path: ${{ inputs.path }}" in content, "'with.path' must reference inputs.path"

def test_action_text_if_condition_mentions_expected_predicates():
    """
    Verify the 'if:' expression references the intended predicates.
    """
    action_path = _find_download_artifact_action()
    content = _read_text(action_path)

    assert "inputs.force-use-github" in content, "'if' must check inputs.force-use-github"
    assert "runner.environment == 'github-hosted'" in content, "'if' must check runner.environment == 'github-hosted'"
    # Ensure equality against the string 'true'
    assert "== 'true'" in content, "'if' should compare against the string 'true'"

def test_action_yaml_top_level_and_runs_using():
    """
    Structured validation of top-level keys and composite runner usage.
    """
    action_path = _find_download_artifact_action()
    data = _load_yaml_or_skip(action_path)

    # Top-level presence
    for key in ("name", "description", "inputs", "runs"):
        assert key in data, f"Top-level key '{key}' must be present"

    assert data["name"] == "Download Artifact", "Action name must be 'Download Artifact'"
    assert isinstance(data.get("description"), str) and data["description"].strip(), "Description must be a non-empty string"

    runs = data["runs"]
    assert isinstance(runs, dict), "'runs' must be a mapping"
    assert runs.get("using") == "composite", "'runs.using' must be 'composite'"
    assert isinstance(runs.get("steps"), list) and runs["steps"], "'runs.steps' must be a non-empty list"

def test_action_yaml_inputs_schema_and_defaults():
    """
    Validate input schema: required fields, defaults, and boolean types.
    """
    action_path = _find_download_artifact_action()
    data = _load_yaml_or_skip(action_path)

    inputs = data.get("inputs") or {}
    for k in ("name", "path", "force-use-github"):
        assert k in inputs, f"Missing input: {k}"

    # name.default
    assert inputs["name"].get("default") == "artifact", "'inputs.name.default' must be 'artifact'"

    # path.required must be boolean True
    assert inputs["path"].get("required") is True, "'inputs.path.required' must be true"
    assert isinstance(inputs["path"].get("required"), bool), "'inputs.path.required' must be a boolean"

    # force-use-github defaults and required flags must be booleans (not strings)
    fug = inputs["force-use-github"]
    assert fug.get("default") is False, "'inputs.force-use-github.default' must be false (boolean)"
    if "required" in fug:
        assert isinstance(fug["required"], bool), "'inputs.force-use-github.required' must be a boolean when present"
        assert fug["required"] is False, "'inputs.force-use-github.required' should be false"
    # If required is omitted, that's acceptable per the source (treated as False/optional)

def test_action_yaml_step_download_from_github_uses_and_with_block():
    """
    Validate the download step: 'uses' pin, 'if' condition, and the 'with' params.
    """
    action_path = _find_download_artifact_action()
    data = _load_yaml_or_skip(action_path)

    steps = data["runs"]["steps"]
    step = _find_step_by_uses(steps, "actions/download-artifact@")
    assert step is not None, "Expected a step using 'actions/download-artifact@'"
    assert step.get("uses") == "actions/download-artifact@v4.1.7", "Must pin to v4.1.7"

    cond = step.get("if", "")
    assert isinstance(cond, str) and cond, "Step must include an 'if' condition"
    assert "inputs.force-use-github" in cond, "'if' must reference inputs.force-use-github"
    assert "runner.environment == 'github-hosted'" in cond, "'if' must check runner.environment == 'github-hosted'"

    w = step.get("with") or {}
    assert w.get("name") == "${{ inputs.name }}", "'with.name' must pass through inputs.name"
    assert w.get("path") == "${{ inputs.path }}", "'with.path' must pass through inputs.path"