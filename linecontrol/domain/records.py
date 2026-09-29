"""Persisted and in-flight process records."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from .events import utcnow


def _stamp(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        return datetime.fromisoformat(raw)
    return utcnow()


@dataclass(frozen=True, slots=True)
class Confirm:
    """Outcome of a strip head alignment check."""

    ok: bool = False
    position: float = 0.0
    at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "position": self.position, "at": self.at.isoformat()}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Confirm":
        return cls(
            ok=bool(raw.get("ok", False)),
            position=float(raw.get("position", 0.0)),
            at=_stamp(raw.get("at")),
        )


@dataclass(frozen=True, slots=True)
class RepairRecord:
    """A post-hoc repair registered against an existing seam."""

    note: str = ""
    at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {"note": self.note, "at": self.at.isoformat()}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RepairRecord":
        return cls(note=str(raw.get("note", "")), at=_stamp(raw.get("at")))


@dataclass(frozen=True, slots=True)
class WeldRecord:
    """A completed weld seam."""

    seam_id: str = ""
    position: float = 0.0
    tension: float = 0.0
    heat_input: float = 0.0
    voltage: float = 0.0
    current: float = 0.0
    weld_speed: float = 0.0
    coil_id: str = ""
    grade: str = ""
    grade_reason: str = ""
    repairs: tuple[RepairRecord, ...] = ()
    at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seam_id": self.seam_id,
            "position": self.position,
            "tension": self.tension,
            "heat_input": self.heat_input,
            "voltage": self.voltage,
            "current": self.current,
            "weld_speed": self.weld_speed,
            "coil_id": self.coil_id,
            "grade": self.grade,
            "grade_reason": self.grade_reason,
            "repairs": [repair.to_dict() for repair in self.repairs],
            "at": self.at.isoformat(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "WeldRecord":
        raw_repairs = raw.get("repairs", ())
        repairs: tuple[RepairRecord, ...] = ()
        if isinstance(raw_repairs, list):
            repairs = tuple(
                RepairRecord.from_dict(item)
                for item in raw_repairs
                if isinstance(item, dict)
            )
        return cls(
            seam_id=str(raw.get("seam_id", "")),
            position=float(raw.get("position", 0.0)),
            tension=float(raw.get("tension", 0.0)),
            heat_input=float(raw.get("heat_input", 0.0)),
            voltage=float(raw.get("voltage", 0.0)),
            current=float(raw.get("current", 0.0)),
            weld_speed=float(raw.get("weld_speed", 0.0)),
            coil_id=str(raw.get("coil_id", "")),
            grade=str(raw.get("grade", "")),
            grade_reason=str(raw.get("grade_reason", "")),
            repairs=repairs,
            at=_stamp(raw.get("at")),
        )

    def with_repair(self, repair: RepairRecord) -> "WeldRecord":
        """Return a copy of the record with one more repair entry."""

        return replace(self, repairs=(*self.repairs, repair))


@dataclass(frozen=True, slots=True)
class TensionSnapshot:
    value: float = 0.0
    gain: float = 1.0
    saved: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "gain": self.gain, "saved": self.saved.isoformat()}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TensionSnapshot":
        return cls(
            value=float(raw.get("value", 0.0)),
            gain=float(raw.get("gain", 1.0)),
            saved=_stamp(raw.get("saved")),
        )


@dataclass(frozen=True, slots=True)
class AcidSnapshot:
    level: float = 0.0
    offset: float = 0.0
    saved: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level, "offset": self.offset, "saved": self.saved.isoformat()}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AcidSnapshot":
        return cls(
            level=float(raw.get("level", 0.0)),
            offset=float(raw.get("offset", 0.0)),
            saved=_stamp(raw.get("saved")),
        )


@dataclass(frozen=True, slots=True)
class PumpSnapshot:
    running: bool = False
    saved: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {"running": self.running, "saved": self.saved.isoformat()}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PumpSnapshot":
        return cls(running=bool(raw.get("running", False)), saved=_stamp(raw.get("saved")))


@dataclass(frozen=True, slots=True)
class TrackSnapshot:
    position: float = 0.0
    seam_id: str = ""
    saved: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "seam_id": self.seam_id,
            "saved": self.saved.isoformat(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TrackSnapshot":
        return cls(
            position=float(raw.get("position", 0.0)),
            seam_id=str(raw.get("seam_id", "")),
            saved=_stamp(raw.get("saved")),
        )


@dataclass(frozen=True, slots=True)
class RinseSnapshot:
    active: bool = False
    saved: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {"active": self.active, "saved": self.saved.isoformat()}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RinseSnapshot":
        return cls(active=bool(raw.get("active", False)), saved=_stamp(raw.get("saved")))


@dataclass(frozen=True, slots=True)
class LatchSnapshot:
    interlock: bool = False
    alarm: bool = False
    saved: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "interlock": self.interlock,
            "alarm": self.alarm,
            "saved": self.saved.isoformat(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LatchSnapshot":
        return cls(
            interlock=bool(raw.get("interlock", False)),
            alarm=bool(raw.get("alarm", False)),
            saved=_stamp(raw.get("saved")),
        )
