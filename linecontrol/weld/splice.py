"""Seam generation and its persisted record."""

from __future__ import annotations

from uuid import uuid4

from ..domain.events import Event
from ..domain.kinds import EventKind
from ..domain.records import WeldRecord, utcnow
from ..store.keys import KEY_WELD, SEAM_PREFIX
from ..store.snapshot import save_json
from .errors import WeldError, WeldErrorCode
from .grade import grade_heat_input
from .state import WeldState


class SpliceOps:
    """Mixed into :class:`~linecontrol.weld.welder.Welder`."""

    def splice(self, coil_id: str = "") -> WeldRecord:
        if self.state() != WeldState.WELDING:
            raise WeldError(WeldErrorCode.ARC_BLOCKED, "no arc running")
        record = self._build_record(
            position=self.data.track,
            tension=self.data.tension,
            heat_input=self.heat_input(),
            voltage=self.data.voltage,
            current=self.data.current,
            line_speed=self.data.line_speed,
            coil_id=coil_id or self.coil_lookup(),
            source="auto",
        )
        self._store_record(record)
        self.data.seam_id = record.seam_id
        self.machine.enter(WeldState.SPLICED)
        self.bus.publish(
            Event(
                kind=EventKind.WELD,
                source="weld",
                message=record.seam_id,
                payload=record.position,
            )
        )
        return record

    def register_manual_seam(
        self,
        position: float,
        tension: float,
        heat_input: float,
        coil_id: str,
        voltage: float = 0.0,
        current: float = 0.0,
        line_speed: float = 0.0,
        at=None,
    ) -> WeldRecord:
        """Register a seam welded (or found) outside the normal arc cycle.

        Used for seams that were physically made but never went through a
        tracked splice, so that they still appear in per-coil traceability.
        Parameters are optional: when absent the seam is stored with whatever
        heat input is given and graded only if a target is configured.
        """

        if not coil_id:
            raise WeldError(WeldErrorCode.POWER_INVALID, "manual seam needs a coil id")
        record = self._build_record(
            position=float(position),
            tension=float(tension),
            heat_input=float(heat_input),
            voltage=float(voltage),
            current=float(current),
            line_speed=float(line_speed),
            coil_id=coil_id,
            source="manual",
            at=at or utcnow(),
        )
        self._store_record(record)
        self.bus.publish(
            Event(
                kind=EventKind.WELD,
                source="weld",
                message="manual:" + record.seam_id,
                payload=record.position,
            )
        )
        return record

    def _build_record(
        self,
        position: float,
        tension: float,
        heat_input: float,
        voltage: float,
        current: float,
        line_speed: float,
        coil_id: str,
        source: str,
        at=None,
    ) -> WeldRecord:
        grade, deviation = grade_heat_input(heat_input, self.data.heat_target)
        return WeldRecord(
            seam_id=uuid4().hex,
            position=float(position),
            tension=float(tension),
            heat_input=float(heat_input),
            voltage=float(voltage),
            current=float(current),
            line_speed=float(line_speed),
            grade=grade.value,
            deviation=float(deviation),
            coil_id=str(coil_id),
            source=source,
            at=at or utcnow(),
        )

    def _store_record(self, record: WeldRecord) -> None:
        save_json(self.store, KEY_WELD, record)
        save_json(self.store, SEAM_PREFIX + record.seam_id, record)

    def track_point(self) -> float:
        return self.data.track

    def seam_id(self) -> str:
        return self.data.seam_id
