from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
from pathlib import Path
from uuid import UUID, uuid4


class Modality(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


class MediaValidationError(ValueError):
    """Raised when a multimodal asset violates the ingestion contract."""


@dataclass(frozen=True)
class MultimodalAsset:
    """Immutable descriptor for a user-provided multimodal artifact."""

    filename: str
    media_type: str
    size_bytes: int
    content_sha256: str
    modality: Modality
    workspace_id: UUID | None = None
    asset_id: UUID = field(default_factory=uuid4)
    metadata: tuple[tuple[str, str], ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    MAX_SIZE_BYTES = 50 * 1024 * 1024
    MAX_METADATA_ITEMS = 32
    MAX_METADATA_CHARS = 256

    def __post_init__(self) -> None:
        if not self.filename.strip() or Path(self.filename).name != self.filename:
            raise MediaValidationError("filename must be a non-empty basename")
        if self.size_bytes < 0 or self.size_bytes > self.MAX_SIZE_BYTES:
            raise MediaValidationError(f"asset size must be between 0 and {self.MAX_SIZE_BYTES} bytes")
        if not self.media_type.strip() or "/" not in self.media_type:
            raise MediaValidationError("media_type must be a MIME type")
        if len(self.content_sha256) != 64 or any(char not in "0123456789abcdef" for char in self.content_sha256):
            raise MediaValidationError("content_sha256 must be a lowercase SHA-256 digest")
        if len(self.metadata) > self.MAX_METADATA_ITEMS:
            raise MediaValidationError(f"metadata cannot contain more than {self.MAX_METADATA_ITEMS} items")
        if any(not key.strip() or len(key) > self.MAX_METADATA_CHARS or len(value) > self.MAX_METADATA_CHARS for key, value in self.metadata):
            raise MediaValidationError("metadata keys and values must be non-empty and bounded")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise MediaValidationError("created_at must include a timezone offset")

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        *,
        filename: str,
        media_type: str,
        modality: Modality,
        workspace_id: UUID | None = None,
        metadata: dict[str, str] | None = None,
    ) -> "MultimodalAsset":
        if len(data) > cls.MAX_SIZE_BYTES:
            raise MediaValidationError(f"asset size must not exceed {cls.MAX_SIZE_BYTES} bytes")
        normalized_metadata = tuple(sorted((str(key).strip(), str(value).strip()) for key, value in (metadata or {}).items()))
        return cls(
            filename=filename,
            media_type=media_type.lower().strip(),
            size_bytes=len(data),
            content_sha256=hashlib.sha256(data).hexdigest(),
            modality=modality,
            workspace_id=workspace_id,
            metadata=normalized_metadata,
        )


@dataclass(frozen=True)
class ModalityRoute:
    """Deterministic capability selection for multimodal processing."""

    modality: Modality
    capabilities: tuple[str, ...]


class MultimodalRouter:
    """Maps media modality to explicit, auditable processing capabilities."""

    _CAPABILITIES: dict[Modality, tuple[str, ...]] = {
        Modality.TEXT: ("text_understanding", "retrieval", "summarization"),
        Modality.IMAGE: ("vision_understanding", "ocr", "visual_grounding"),
        Modality.AUDIO: ("speech_to_text", "audio_understanding", "transcription"),
        Modality.VIDEO: ("frame_understanding", "speech_to_text", "temporal_grounding"),
    }

    @classmethod
    def route(cls, asset: MultimodalAsset) -> ModalityRoute:
        return ModalityRoute(asset.modality, cls._CAPABILITIES[asset.modality])

    @classmethod
    def validate_workspace(cls, asset: MultimodalAsset, workspace_id: UUID | None) -> bool:
        return asset.workspace_id == workspace_id


@dataclass(frozen=True)
class MultimodalEvidence:
    """Evidence envelope linking derived observations to the exact input asset."""

    asset_id: UUID
    content_sha256: str
    modality: Modality
    observation: str
    source: str = "derived"

    def __post_init__(self) -> None:
        if not self.observation.strip():
            raise MediaValidationError("evidence observation cannot be empty")
        if self.source not in {"derived", "model", "tool", "user"}:
            raise MediaValidationError("unsupported evidence source")

    def as_dict(self) -> dict[str, str]:
        return {
            "asset_id": str(self.asset_id),
            "content_sha256": self.content_sha256,
            "modality": self.modality.value,
            "observation": self.observation,
            "source": self.source,
        }
