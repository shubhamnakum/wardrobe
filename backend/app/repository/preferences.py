from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repository.models import Preference
from app.repository.util import utcnow_iso


class PreferenceRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def set(self, key: str, value: str, weight: float | None = None) -> Preference:
        """Insert or update a preference."""
        row = self._s.merge(
            Preference(key=key, value=value, weight=weight, updated_at=utcnow_iso())
        )
        self._s.flush()
        return row

    def get(self, key: str) -> Preference | None:
        return self._s.get(Preference, key)

    def all(self) -> list[Preference]:
        return list(self._s.scalars(select(Preference).order_by(Preference.key)))
