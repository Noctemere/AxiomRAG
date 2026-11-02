from pathlib import Path

import yaml


def test_kustomize_resources_exist_and_parse() -> None:
    """Verify every Kustomize resource exists and contains valid YAML documents."""
    root = Path(__file__).parents[1] / "infra" / "k8s"
    resources = [
        "namespace.yaml",
        "configmap.yaml",
        "secret.example.yaml",
        "deployments.yaml",
        "services.yaml",
    ]
    for resource in resources:
        documents = list(yaml.safe_load_all((root / resource).read_text()))
        assert documents
        assert all(document.get("apiVersion") and document.get("kind") for document in documents)

    kustomization = yaml.safe_load((root / "kustomization.yaml").read_text())
    assert kustomization["resources"] == resources
