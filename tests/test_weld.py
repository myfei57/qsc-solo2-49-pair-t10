"""Welder gating, splicing and the interlock latch."""

from __future__ import annotations

import json

import pytest

from linecontrol.bus import EventBus
from linecontrol.domain.records import Confirm, LatchSnapshot, utcnow
from linecontrol.store.filestore import FileStore
from linecontrol.store.keys import KEY_HEAT_TARGET, SEAM_PREFIX
from linecontrol.store.recovery import collect
from linecontrol.weld.errors import WeldError, WeldErrorCode
from linecontrol.weld.grade import (
    GRADE_A_TOLERANCE,
    GRADE_B_TOLERANCE,
    SeamGrade,
    grade_heat_input,
)
from linecontrol.weld.state import WeldState
from linecontrol.weld.welder import Welder


class Aligner:
    """Stand-in for the entry section's confirmation lookup."""

    def __init__(self) -> None:
        self.confirm = Confirm(ok=False)

    def __call__(self) -> Confirm:
        return self.confirm


def build(tmp_path, coil=None) -> tuple[Welder, Aligner]:
    aligner = Aligner()
    welder = Welder(aligner, FileStore(tmp_path), EventBus(), coil=coil)
    return welder, aligner


def test_gate_refuses_without_a_confirmation(tmp_path) -> None:
    welder, _ = build(tmp_path)
    with pytest.raises(WeldError) as caught:
        welder.gate_arc()
    assert caught.value.code is WeldErrorCode.ALIGN_PENDING
    assert welder.state() == WeldState.IDLE


def test_arc_uses_the_confirmation_read_at_gate_time(tmp_path) -> None:
    welder, aligner = build(tmp_path)
    aligner.confirm = Confirm(ok=True, position=100.0, at=utcnow())
    welder.gate_arc()
    aligner.confirm = Confirm(ok=True, position=175.0, at=utcnow())
    welder.gate_arc()
    welder.arc()
    assert welder.track_point() == pytest.approx(175.0)
    assert welder.state() == WeldState.WELDING


def test_arc_is_blocked_while_the_latch_is_held(tmp_path) -> None:
    welder, aligner = build(tmp_path)
    aligner.confirm = Confirm(ok=True, position=100.0, at=utcnow())
    welder.alarm()
    welder.gate_arc()
    with pytest.raises(WeldError) as caught:
        welder.arc()
    assert caught.value.code is WeldErrorCode.LATCH_HELD
    welder.alarm_clear()
    welder.gate_arc()
    welder.arc()
    assert welder.interlock_ok()


def test_splice_writes_both_the_record_and_the_seam(tmp_path) -> None:
    welder, aligner = build(tmp_path)
    aligner.confirm = Confirm(ok=True, position=88.0, at=utcnow())
    welder.set_line_speed(1.5)
    welder.set_power(24.0, 300.0)
    welder.gate_arc()
    welder.arc()
    welder.persist_tension(90.0, 1.05)
    record = welder.splice()
    assert record.position == pytest.approx(88.0)
    assert record.heat_input == pytest.approx(24.0 * 300.0 / 1.5)
    assert welder.state() == WeldState.SPLICED
    assert welder.store.exists("weld.record")
    assert welder.store.exists("weld.seam." + record.seam_id)
    assert welder.seam_id() == record.seam_id


def test_splice_requires_a_running_arc(tmp_path) -> None:
    welder, _ = build(tmp_path)
    with pytest.raises(WeldError) as caught:
        welder.splice()
    assert caught.value.code is WeldErrorCode.ARC_BLOCKED


def test_power_validation(tmp_path) -> None:
    welder, _ = build(tmp_path)
    with pytest.raises(WeldError) as caught:
        welder.set_power(0.0, 10.0)
    assert caught.value.code is WeldErrorCode.POWER_INVALID
    welder.set_power(24.0, 300.0)
    assert welder.power_state() == (pytest.approx(24.0), pytest.approx(300.0))
    assert welder.heat_input() == 0.0


def test_latch_snapshot_round_trip(tmp_path) -> None:
    welder, _ = build(tmp_path)
    welder.alarm()
    assert welder.alarm_active() and not welder.interlock_ok()
    other = Welder(Aligner(), welder.store, EventBus())
    other.restore_latch(LatchSnapshot(interlock=True, alarm=True))
    assert other.alarm_active() and not other.interlock_ok()


def test_seam_history_is_newest_first(tmp_path) -> None:
    welder, aligner = build(tmp_path)
    aligner.confirm = Confirm(ok=True, position=10.0, at=utcnow())
    for position in (10.0, 20.0, 30.0):
        aligner.confirm = Confirm(ok=True, position=position, at=utcnow())
        welder.gate_arc()
        welder.arc()
        welder.splice()
    history = welder.seam_history(2)
    assert len(history) == 2
    assert history[0].at >= history[1].at


def test_arc_post_splice_regates_on_the_live_confirmation(tmp_path) -> None:
    welder, aligner = build(tmp_path)
    aligner.confirm = Confirm(ok=True, position=50.0, at=utcnow())
    welder.gate_arc()
    welder.arc()
    welder.splice()
    aligner.confirm = Confirm(ok=True, position=140.0, at=utcnow())
    welder.arc_post_splice()
    assert welder.track_point() == pytest.approx(140.0)


def test_snapshot_exposes_the_transition_history(tmp_path) -> None:
    welder, aligner = build(tmp_path)
    aligner.confirm = Confirm(ok=True, position=10.0, at=utcnow())
    welder.gate_arc()
    welder.arc()
    view = welder.snapshot()
    assert view["state"] == WeldState.WELDING
    assert view["transitions"] == [WeldState.IDLE, WeldState.GATED, WeldState.WELDING]


def _strike(welder: Welder, aligner: Aligner, position: float) -> None:
    aligner.confirm = Confirm(ok=True, position=position, at=utcnow())
    if welder.state() == WeldState.SPLICED:
        welder.arc_post_splice()
    else:
        welder.gate_arc()
        welder.arc()


def test_grade_bands_follow_the_heat_input_tolerance() -> None:
    target = 4800.0
    assert grade_heat_input(target, target) == (SeamGrade.A, 0.0)
    grade, deviation = grade_heat_input(target * (1 + GRADE_A_TOLERANCE), target)
    assert grade is SeamGrade.A
    assert deviation == pytest.approx(GRADE_A_TOLERANCE)
    grade, deviation = grade_heat_input(target * (1 - GRADE_B_TOLERANCE), target)
    assert grade is SeamGrade.B
    assert deviation == pytest.approx(-GRADE_B_TOLERANCE)
    grade, _ = grade_heat_input(target * 1.5, target)
    assert grade is SeamGrade.C
    assert grade_heat_input(0.0, target)[0] is SeamGrade.U
    assert grade_heat_input(target, 0.0)[0] is SeamGrade.U


def test_splice_records_parameters_grade_and_coil(tmp_path) -> None:
    coil = {"id": "C-100"}
    welder, aligner = build(tmp_path, coil=lambda: coil["id"])
    welder.set_heat_target(4800.0)
    aligner.confirm = Confirm(ok=True, position=88.0, at=utcnow())
    welder.set_line_speed(1.5)
    welder.set_power(24.0, 300.0)
    welder.gate_arc()
    welder.arc()
    record = welder.splice()
    assert record.grade == SeamGrade.A.value
    assert record.deviation == 0.0
    assert record.coil_id == "C-100"
    assert record.voltage == pytest.approx(24.0)
    assert record.current == pytest.approx(300.0)
    assert record.line_speed == pytest.approx(1.5)
    assert record.source == "auto"


def test_seam_without_parameters_stays_ungraded(tmp_path) -> None:
    welder, aligner = build(tmp_path, coil=lambda: "C-1")
    welder.set_heat_target(4800.0)
    aligner.confirm = Confirm(ok=True, position=10.0, at=utcnow())
    welder.gate_arc()
    welder.arc()
    record = welder.splice()
    assert record.grade == SeamGrade.U.value


def test_seam_history_filters_by_coil(tmp_path) -> None:
    coil = {"id": "C-1"}
    welder, aligner = build(tmp_path, coil=lambda: coil["id"])
    welder.set_heat_target(4800.0)
    welder.set_power(24.0, 300.0)
    welder.set_line_speed(1.5)
    for coil["id"], position in (("C-1", 10.0), ("C-2", 20.0), ("C-1", 30.0)):
        _strike(welder, aligner, position)
        welder.splice()
    c1 = welder.seam_history(coil_id="C-1")
    assert [r.coil_id for r in c1] == ["C-1", "C-1"]
    assert {r.position for r in c1} == {10.0, 30.0}


def test_older_ungraded_records_are_backfilled(tmp_path) -> None:
    welder, aligner = build(tmp_path)
    store = welder.store
    old = {
        "seam_id": "legacy",
        "position": 10.0,
        "tension": 90.0,
        "heat_input": 4800.0,
        "at": utcnow().isoformat(),
    }
    store.save(SEAM_PREFIX + "legacy", json.dumps(old).encode("utf-8"))
    assert welder.seam_history()[0].grade == SeamGrade.U.value
    welder.set_heat_target(4800.0)
    backfilled = welder.seam_history()[0]
    assert backfilled.grade == SeamGrade.A.value
    assert backfilled.source == "auto"


def test_heat_target_persists_and_recovers(tmp_path) -> None:
    welder, _ = build(tmp_path)
    welder.set_heat_target(4800.0)
    assert welder.store.exists(KEY_HEAT_TARGET)
    with pytest.raises(WeldError) as caught:
        welder.set_heat_target(0.0)
    assert caught.value.code is WeldErrorCode.POWER_INVALID
    state = collect(welder.store)
    assert state.heat_target.value == pytest.approx(4800.0)


def test_register_repair_attaches_to_an_existing_seam(tmp_path) -> None:
    welder, aligner = build(tmp_path, coil=lambda: "C-7")
    aligner.confirm = Confirm(ok=True, position=10.0, at=utcnow())
    welder.gate_arc()
    welder.arc()
    seam = welder.splice()
    first = welder.register_repair(seam.seam_id, reason="断带", operator="张")
    second = welder.register_repair(seam.seam_id, reason="复检", note="加焊一道")
    assert first.coil_id == "C-7"
    repairs = welder.repairs_for(seam.seam_id)
    assert [r.repair_id for r in repairs] == [first.repair_id, second.repair_id]
    assert welder.repair_history()[0].repair_id == second.repair_id
    assert welder.repair_history(coil_id="C-7")[0].seam_id == seam.seam_id
    assert welder.repair_history(coil_id="C-other") == []


def test_repair_requires_a_known_seam(tmp_path) -> None:
    welder, _ = build(tmp_path)
    with pytest.raises(WeldError) as caught:
        welder.register_repair("missing")
    assert caught.value.code is WeldErrorCode.SEAM_NOT_FOUND


def test_manual_seam_registration_is_graded_and_tagged(tmp_path) -> None:
    welder, _ = build(tmp_path)
    welder.set_heat_target(4800.0)
    seam = welder.register_manual_seam(
        position=12.0,
        tension=88.0,
        heat_input=4800.0,
        coil_id="C-9",
        voltage=24.0,
        current=300.0,
        line_speed=1.5,
    )
    assert seam.source == "manual"
    assert seam.grade == SeamGrade.A.value
    assert welder.seam(seam.seam_id).coil_id == "C-9"
    with pytest.raises(WeldError) as caught:
        welder.register_manual_seam(1.0, 1.0, 1.0, coil_id="")
    assert caught.value.code is WeldErrorCode.POWER_INVALID
