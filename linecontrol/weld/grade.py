"""Seam quality grading from the welding parameters used at splice time.

The heat input is ``voltage * current / line_speed``.  A seam is graded
against the process target heat input by how far its actual heat input
deviates from that target: a seam welded close to spec is an A, a seam
noticeably off is a B and a seam well outside the process window is a C.
Seams whose parameters were never captured, or before any target was
configured, stay ungraded (U) rather than being forced into a band.
"""

from __future__ import annotations

from enum import Enum


class SeamGrade(str, Enum):
    """Quality band assigned to a completed seam."""

    A = "A"
    B = "B"
    C = "C"
    #: Ungraded: missing parameters or no target heat input configured.
    U = "U"


#: Absolute deviation allowed for the top grade, as a fraction of target.
GRADE_A_TOLERANCE = 0.05

#: Absolute deviation allowed for the middle grade, as a fraction of target.
GRADE_B_TOLERANCE = 0.15


def grade_heat_input(heat_input: float, target: float) -> tuple[SeamGrade, float]:
    """Grade a heat input against the process target.

    Returns the grade and the signed relative deviation ``(actual-target)/
    target``.  The deviation is ``0`` for ungraded seams so that stored
    records never carry a misleading number.
    """

    if heat_input <= 0 or target <= 0:
        return SeamGrade.U, 0.0
    deviation = (heat_input - target) / target
    magnitude = abs(deviation)
    if magnitude <= GRADE_A_TOLERANCE:
        return SeamGrade.A, deviation
    if magnitude <= GRADE_B_TOLERANCE:
        return SeamGrade.B, deviation
    return SeamGrade.C, deviation
