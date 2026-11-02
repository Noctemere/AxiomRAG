from pathlib import Path

import yaml


def test_release_workflow_builds_all_runtime_images() -> None:
    """Verify release CI covers API, worker, and web Dockerfiles."""
    workflow = yaml.safe_load(
        (Path(__file__).parents[1] / ".github" / "workflows" / "release.yml").read_text()
    )
    matrix = workflow["jobs"]["containers"]["strategy"]["matrix"]["include"]
    assert {item["name"] for item in matrix} == {"api", "worker", "web"}
    assert all(item["dockerfile"].startswith("infra/docker/") for item in matrix)
