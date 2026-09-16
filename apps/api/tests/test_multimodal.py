from datetime import datetime
from uuid import uuid4

import pytest

from nexus.core.multimodal import MediaValidationError, Modality, MultimodalAsset, MultimodalEvidence, MultimodalRouter


def test_multimodal_asset_is_content_addressed_and_bounded() -> None:
    workspace_id = uuid4()
    asset = MultimodalAsset.from_bytes(
        b"hello image bytes",
        filename="scan.png",
        media_type="IMAGE/PNG",
        modality=Modality.IMAGE,
        workspace_id=workspace_id,
        metadata={"source": "upload"},
    )
    assert asset.media_type == "image/png"
    assert asset.size_bytes == len(b"hello image bytes")
    assert len(asset.content_sha256) == 64
    assert asset.workspace_id == workspace_id
    assert asset.created_at.tzinfo is not None


def test_multimodal_asset_rejects_unsafe_or_oversized_metadata() -> None:
    with pytest.raises(MediaValidationError, match="basename"):
        MultimodalAsset.from_bytes(b"x", filename="../secret.png", media_type="image/png", modality=Modality.IMAGE)
    with pytest.raises(MediaValidationError, match="metadata"):
        MultimodalAsset.from_bytes(
            b"x",
            filename="image.png",
            media_type="image/png",
            modality=Modality.IMAGE,
            metadata={"k": "v" * 257},
        )
    with pytest.raises(MediaValidationError, match="SHA-256"):
        MultimodalAsset(
            filename="image.png",
            media_type="image/png",
            size_bytes=1,
            content_sha256="A" * 64,
            modality=Modality.IMAGE,
        )


def test_multimodal_router_is_deterministic_and_workspace_scoped() -> None:
    workspace_id = uuid4()
    image = MultimodalAsset.from_bytes(b"pixels", filename="photo.jpg", media_type="image/jpeg", modality=Modality.IMAGE, workspace_id=workspace_id)
    route = MultimodalRouter.route(image)
    assert route.modality is Modality.IMAGE
    assert route.capabilities == ("vision_understanding", "ocr", "visual_grounding")
    assert MultimodalRouter.validate_workspace(image, workspace_id)
    assert not MultimodalRouter.validate_workspace(image, uuid4())


def test_evidence_binds_observation_to_exact_asset() -> None:
    asset = MultimodalAsset.from_bytes(b"audio", filename="note.wav", media_type="audio/wav", modality=Modality.AUDIO)
    evidence = MultimodalEvidence(
        asset_id=asset.asset_id,
        content_sha256=asset.content_sha256,
        modality=asset.modality,
        observation="Transcript contains the requested phrase.",
        source="model",
    )
    payload = evidence.as_dict()
    assert payload["asset_id"] == str(asset.asset_id)
    assert payload["content_sha256"] == asset.content_sha256
    assert payload["modality"] == "audio"
    with pytest.raises(MediaValidationError, match="observation"):
        MultimodalEvidence(asset_id=asset.asset_id, content_sha256=asset.content_sha256, modality=asset.modality, observation="")


def test_multimodal_asset_requires_timezone() -> None:
    with pytest.raises(MediaValidationError, match="timezone"):
        MultimodalAsset(
            filename="image.png",
            media_type="image/png",
            size_bytes=1,
            content_sha256="a" * 64,
            modality=Modality.IMAGE,
            created_at=datetime(2026, 1, 1),
        )
