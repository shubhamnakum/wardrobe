from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repository.models import AttributeEvidence


class EvidenceRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(
        self,
        garment_id: str,
        attribute_name: str,
        value: Any,
        source: str,
        *,
        confidence: float | None = None,
        model_version: str | None = None,
        confirmed_at: str | None = None,
    ) -> AttributeEvidence:
        row = AttributeEvidence(
            garment_id=garment_id,
            attribute_name=attribute_name,
            value=value,
            source=source,
            confidence=confidence,
            model_version=model_version,
            confirmed_at=confirmed_at,
        )
        self._s.add(row)
        self._s.flush()
        return row

    def list_for_garment(self, garment_id: str) -> list[AttributeEvidence]:
        stmt = select(AttributeEvidence).where(AttributeEvidence.garment_id == garment_id)
        return list(self._s.scalars(stmt.order_by(AttributeEvidence.id)))

    def latest(
        self, garment_id: str, attribute_name: str, *, source: str | None = None
    ) -> AttributeEvidence | None:
        stmt = select(AttributeEvidence).where(
            AttributeEvidence.garment_id == garment_id,
            AttributeEvidence.attribute_name == attribute_name,
        )
        if source:
            stmt = stmt.where(AttributeEvidence.source == source)
        return self._s.scalars(stmt.order_by(AttributeEvidence.id.desc()).limit(1)).first()
