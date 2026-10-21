from types import TracebackType
from typing import Self

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.repository.evidence import EvidenceRepository
from app.repository.garments import GarmentRepository
from app.repository.outfits import FeedbackRepository, OutfitRepository
from app.repository.preferences import PreferenceRepository
from app.repository.usage import UsageRepository


class UnitOfWork:
    """One transaction, all repositories on the same session.

    Commits when the ``with`` block exits cleanly and rolls everything back if it raises::

        with UnitOfWork(engine) as uow:
            uow.garments.add("White T-shirt", category="top")
    """

    session: Session
    garments: GarmentRepository
    evidence: EvidenceRepository
    outfits: OutfitRepository
    feedback: FeedbackRepository
    usage: UsageRepository
    preferences: PreferenceRepository

    def __init__(self, engine: Engine) -> None:
        # expire_on_commit=False: returned objects stay readable after the block ends.
        self._factory = sessionmaker(engine, expire_on_commit=False)

    def __enter__(self) -> Self:
        self.session = self._factory()
        self.session.begin()
        self.garments = GarmentRepository(self.session)
        self.evidence = EvidenceRepository(self.session)
        self.outfits = OutfitRepository(self.session)
        self.feedback = FeedbackRepository(self.session)
        self.usage = UsageRepository(self.session)
        self.preferences = PreferenceRepository(self.session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()
