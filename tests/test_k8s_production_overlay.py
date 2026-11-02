from pathlib import Path

import yaml


def test_production_overlay_contains_operational_controls() -> None:
    """Verify the production overlay declares ingress, scaling, budgets, and policy."""
    root = Path(__file__).parents[1] / "infra" / "k8s" / "production"
    kustomization = yaml.safe_load((root / "kustomization.yaml").read_text())
    assert set(kustomization["resources"]) == {
        "../",
        "ingress.yaml",
        "autoscaling.yaml",
        "disruption-budgets.yaml",
        "network-policy.yaml",
    }
    for filename in set(kustomization["resources"]) - {"../"}:
        documents = list(yaml.safe_load_all((root / filename).read_text()))
        assert all(document.get("apiVersion") and document.get("kind") for document in documents)
