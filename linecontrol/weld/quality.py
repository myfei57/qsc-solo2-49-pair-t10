"""Seam quality grading from the welding parameters used at splice time.

The grade is derived from the heat input (voltage * current / speed), which is
the single figure that captures whether the seam was laid down with enough, but
not excessive, energy for the strip thickness. It is compared against the
configured process window:

* ``A`` -- heat input within ``tight`` of the target;
* ``B`` -- within ``loose`` but outside the tight band;
* ``C`` -- outside the loose band, or the parameters were unusable.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Default nominal heat input (J/mm) for the strip welded on this line.
DEFAULT_TARGET_HEAT = 4800.0

#: Relative deviation allowed for the A and B grades.
TIGHT_DEVIATION = 0.10
LOOSE_DEVIATION = 0.25

GRADE_A = "A"
GRADE_B = "B"
GRADE_C = "C"

#: Machine-readable reasons, mapped to operator text by the console.
REASON_IN_BAND = "in-band"
REASON_HOT = "heat-high"
REASON_COLD = "heat-low"
REASON_SPEED_MISSING = "speed-missing"
REASON_POWER_MISSING = "power-missing"


@dataclass(frozen=True, slots=True)
class WeldSpec:
    """Process window a weld's heat input is graded against."""

    target_heat: float = DEFAULT_TARGET_HEAT
    tight: float = TIGHT_DEVIATION
    loose: float = LOOSE_DEVIATION

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "WeldSpec":
        return cls(
            target_heat=float(raw.get("targetHeat", DEFAULT_TARGET_HEAT)),
            tight=float(raw.get("tight", TIGHT_DEVIATION)),
            loose=float(raw.get("loose", LOOSE_DEVIATION)),
        )

    def to_dict(self) -> dict[str, float]:
        return {"targetHeat": self.target_heat, "tight": self.tight, "loose": self.loose}


def grade_seam(
    voltage: float,
    current: float,
    speed: float,
    spec: WeldSpec | None = None,
) -> tuple[str, str, float]:
    """Return ``(grade, reason, heat_input)`` for the welding parameters."""

    spec = spec or WeldSpec()
    if voltage <= 0.0 or current <= 0.0:
        return GRADE_C, REASON_POWER_MISSING, 0.0
    if speed <= 0.0:
        return GRADE_C, REASON_SPEED_MISSING, 0.0
    heat_input = voltage * current / speed
    deviation = abs(heat_input - spec.target_heat) / spec.target_heat
    if deviation <= spec.tight:
        return GRADE_A, REASON_IN_BAND, heat_input
    if deviation <= spec.loose:
        return GRADE_B, REASON_HOT if heat_input > spec.target_heat else REASON_COLD, heat_input
    return GRADE_C, REASON_HOT if heat_input > spec.target_heat else REASON_COLD, heat_input
