from datetime import UTC, datetime
from uuid import uuid4

from packages.contracts.models import DocumentAsset, Modality, Provenance


def test_document_asset_contract_preserves_storage_and_provenance() -> None:
    """Verify extracted asset metadata is complete before repository persistence."""
    document_id = uuid4()
    asset = DocumentAsset(
        asset_id=uuid4(),
        document_id=document_id,
        tenant_id=uuid4(),
        modality=Modality.IMAGE,
        storage_key="tenant/document/assets/image.bin",
        provenance=Provenance(document_id=document_id, page_number=4, region_id="bbox:1"),
        created_at=datetime.now(UTC),
    )

    assert asset.provenance.document_id == document_id
    assert asset.storage_key.endswith("image.bin")
    assert asset.modality is Modality.IMAGE