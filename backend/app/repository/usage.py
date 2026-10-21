from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repository.models import UsageEvent


class UsageRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, garment_id: str, event_type: str, outfit_id: str | None = None) -> UsageEvent:
        row = UsageEvent(garment_id=garment_id, event_type=event_type, outfit_id=outfit_id)
        self._s.add(row)
        self._s.flush()
        return row

    def list_for_garment(self, garment_id: str) -> list[UsageEvent]:
        stmt = select(UsageEvent).where(UsageEvent.garment_id == garment_id)
        return list(self._s.scalars(stmt.order_by(UsageEvent.id)))
