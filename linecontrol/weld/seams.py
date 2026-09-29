"""Persisted seam history and post-hoc repair registration."""

from __future__ import annotations

from uuid import uuid4

from ..domain.events import Event
from ..domain.kinds import EventKind
from ..domain.records import RepairRecord, WeldRecord, utcnow
from ..store.keys import KEY_WELD, REPAIR_PREFIX, SEAM_PREFIX
from ..store.snapshot import load_json, save_json
from .errors import WeldError, WeldErrorCode
from .grade import grade_heat_input


class SeamsOps:
    """Mixed into :class:`~linecontrol.weld.welder.Welder`."""

    def seam_history(self, limit: int = 0, coil_id: str = "") -> list[WeldRecord]:
        records: list[WeldRecord] = []
        for key in self.store.list(SEAM_PREFIX):
            record, ok = load_json(self.store, key, WeldRecord)
            if not ok:
                continue
            record = self._upgraded(record)
            if coil_id and record.coil_id != coil_id:
                continue
            records.append(record)
        records.sort(key=lambda item: item.at, reverse=True)
        if limit > 0:
            return records[:limit]
        return records

    def seam(self, seam_id: str) -> WeldRecord:
        record, ok = load_json(self.store, SEAM_PREFIX + seam_id, WeldRecord)
        if not ok:
            raise WeldError(WeldErrorCode.SEAM_NOT_FOUND, f"no seam {seam_id!r}")
        return self._upgraded(record)

    def register_repair(
        self,
        seam_id: str,
        reason: str = "",
        operator: str = "",
        note: str = "",
        coil_id: str = "",
    ) -> RepairRecord:
        """Register a repair performed on an existing seam after the fact."""

        seam = self.seam(seam_id)
        record = RepairRecord(
            repair_id=uuid4().hex,
            seam_id=seam_id,
            coil_id=coil_id or seam.coil_id,
            reason=reason.strip(),
            operator=operator.strip(),
            note=note.strip(),
            at=utcnow(),
        )
        save_json(self.store, REPAIR_PREFIX + record.repair_id, record)
        self.bus.publish(
            Event(
                kind=EventKind.WELD,
                source="weld",
                message="repair:" + seam_id,
                payload=seam.position,
            )
        )
        return record

    def repairs_for(self, seam_id: str) -> list[RepairRecord]:
        records: list[RepairRecord] = []
        for key in self.store.list(REPAIR_PREFIX):
            record, ok = load_json(self.store, key, RepairRecord)
            if ok and record.seam_id == seam_id:
                records.append(record)
        records.sort(key=lambda item: item.at)
        return records

    def repair_history(self, limit: int = 0, coil_id: str = "") -> list[RepairRecord]:
        records: list[RepairRecord] = []
        for key in self.store.list(REPAIR_PREFIX):
            record, ok = load_json(self.store, key, RepairRecord)
            if not ok:
                continue
            if coil_id and record.coil_id != coil_id:
                continue
            records.append(record)
        records.sort(key=lambda item: item.at, reverse=True)
        if limit > 0:
            return records[:limit]
        return records

    def last_weld(self) -> tuple[WeldRecord, bool]:
        record, ok = load_json(self.store, KEY_WELD, WeldRecord)
        if ok:
            record = self._upgraded(record)
        return record, ok

    def _upgraded(self, record: WeldRecord) -> WeldRecord:
        """Backfill a grade for older records stored before grading existed."""

        if record.grade and record.grade != "U":
            return record
        grade, deviation = grade_heat_input(record.heat_input, self.data.heat_target)
        if grade.value == record.grade:
            return record
        return WeldRecord(
            seam_id=record.seam_id,
            position=record.position,
            tension=record.tension,
            heat_input=record.heat_input,
            voltage=record.voltage,
            current=record.current,
            line_speed=record.line_speed,
            grade=grade.value,
            deviation=deviation,
            coil_id=record.coil_id,
            source=record.source,
            at=record.at,
        )
