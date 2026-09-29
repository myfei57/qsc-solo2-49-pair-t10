"""Persisted seam history."""

from __future__ import annotations

from ..domain.events import Event
from ..domain.kinds import EventKind
from ..domain.records import RepairRecord, WeldRecord, utcnow
from ..store.keys import KEY_WELD, SEAM_PREFIX
from ..store.snapshot import load_json, save_json
from .errors import WeldError, WeldErrorCode


class SeamsOps:
    """Mixed into :class:`~linecontrol.weld.welder.Welder`."""

    def seam_history(self, limit: int = 0, coil_id: str = "") -> list[WeldRecord]:
        records: list[WeldRecord] = []
        for key in self.store.list(SEAM_PREFIX):
            record, ok = load_json(self.store, key, WeldRecord)
            if ok and (not coil_id or record.coil_id == coil_id):
                records.append(record)
        records.sort(key=lambda item: item.at, reverse=True)
        if limit > 0:
            return records[:limit]
        return records

    def last_weld(self) -> tuple[WeldRecord, bool]:
        return load_json(self.store, KEY_WELD, WeldRecord)

    def get_seam(self, seam_id: str) -> WeldRecord:
        if not seam_id:
            raise WeldError(WeldErrorCode.SEAM_MISSING, "no seam id given")
        record, ok = load_json(self.store, SEAM_PREFIX + seam_id, WeldRecord)
        if not ok:
            raise WeldError(WeldErrorCode.SEAM_MISSING, f"seam {seam_id} not found")
        return record

    def register_repair(self, seam_id: str, note: str) -> WeldRecord:
        """Append an after-the-fact repair entry to a stored seam.

        The original grade and parameters are kept; repairs are append-only so
        the seam's history shows both how it was welded and what was later done
        to it.
        """

        note = (note or "").strip()
        record = self.get_seam(seam_id).with_repair(RepairRecord(note=note, at=utcnow()))
        save_json(self.store, SEAM_PREFIX + seam_id, record)
        self.bus.publish(
            Event(
                kind=EventKind.WELD,
                source="weld",
                message="repair:" + seam_id,
                payload=float(len(record.repairs)),
            )
        )
        return record
