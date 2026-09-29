"""HTTP console endpoints."""

from __future__ import annotations

from flask.testing import FlaskClient


def test_state_and_static(client: FlaskClient) -> None:
    response = client.get("/api/state")
    assert response.status_code == 200
    assert response.get_json()["state"]["phase"] == "idle"
    assert client.get("/").status_code == 200
    assert client.get("/app.js").status_code == 200
    assert client.get("/style.css").status_code == 200
    assert client.get("/missing.txt").status_code == 404


def test_read_only_endpoints(client: FlaskClient) -> None:
    for path in (
        "/api/report",
        "/api/machines",
        "/api/bus",
        "/api/store",
        "/api/events",
        "/api/audit",
        "/api/audit/summary",
        "/api/weld/seams",
        "/api/tension/persisted",
        "/api/strip/sag",
        "/api/sequence",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.get_json()["ok"] is True


def test_missing_parameter_is_a_bad_request(client: FlaskClient) -> None:
    response = client.post("/api/entry/sample")
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_domain_failure_is_a_conflict(client: FlaskClient) -> None:
    response = client.post("/api/entry/sample?value=abc")
    assert response.status_code == 400
    response = client.post("/api/pump/start?level=1.0")
    assert response.status_code == 409
    body = response.get_json()
    assert body["ok"] is False
    assert body["detail"]["code"] == "level-low"


def test_cycle_endpoint_runs_the_line(client: FlaskClient) -> None:
    response = client.post(
        "/api/cycle",
        query_string={
            "coil": "C-77",
            "target": 90,
            "level": 4.5,
            "voltage": 24,
            "current": 300,
            "speed": 1.4,
        },
    )
    assert response.status_code == 200
    sequence = response.get_json()["sequence"]
    assert sequence["label"] == "production"
    assert all(step["ok"] for step in sequence["steps"])
    state = client.get("/api/state").get_json()["state"]
    assert state["phase"] == "idle"
    assert state["weld"]["seam"]


def test_cycle_without_a_coil_is_rejected(client: FlaskClient) -> None:
    response = client.post("/api/cycle", query_string={"target": 90})
    assert response.status_code == 400


def test_weld_alarm_flow(client: FlaskClient) -> None:
    assert client.post("/api/weld/confirm").status_code == 409
    client.post("/api/cycle?coil=C-1&target=90&level=4.5&voltage=24&current=300&speed=1.4")
    client.post("/api/entry/sample?value=12")
    alarm = client.post("/api/weld/alarm").get_json()
    assert alarm["alarms"] == ["weld-overcurrent"]
    assert client.post("/api/weld/release").status_code == 409
    cleared = client.post("/api/weld/clear").get_json()
    assert cleared["cleared"] is True
    assert client.post("/api/weld/release").status_code == 200


def test_events_stream_records_bus_traffic(client: FlaskClient) -> None:
    client.post("/api/entry/sample?value=5")
    events = client.get("/api/events").get_json()["events"]
    assert isinstance(events, list)
    client.post("/api/cycle?coil=C-1&target=90&level=4.5&voltage=24&current=300&speed=1.4")
    events = client.get("/api/events").get_json()["events"]
    kinds = {event["kind"] for event in events}
    assert {"arc", "weld", "tension", "pump", "stop"} <= kinds


def test_audit_query_filters_by_kind(client: FlaskClient) -> None:
    client.post("/api/cycle?coil=C-1&target=90&level=4.5&voltage=24&current=300&speed=1.4")
    response = client.get("/api/audit?kind=arc&limit=5")
    events = response.get_json()["events"]
    assert events and all(event["kind"] == "arc" for event in events)
    summary = client.get("/api/audit/summary").get_json()["summary"]
    assert summary["arc"] >= 1


def test_store_view_lists_keys(client: FlaskClient) -> None:
    client.post("/api/cycle?coil=C-1&target=90&level=4.5&voltage=24&current=300&speed=1.4")
    view = client.get("/api/store").get_json()
    assert "weld.record" in view["keys"]
    assert "TensionSnapshot" in view["recordTypes"]


def test_machines_view(client: FlaskClient) -> None:
    machines = client.get("/api/machines").get_json()["machines"]
    assert set(machines) == {"weld", "pump", "dryer", "tension"}
    assert machines["weld"]["state"] == "idle"


def test_bus_view_reports_subscribers(client: FlaskClient) -> None:
    view = client.get("/api/bus").get_json()
    assert view["subscribers"]["arc"] >= 1


def test_taper_weight_and_eta(client: FlaskClient) -> None:
    taper = client.post("/api/exit/taper?base=40&diameter=120").get_json()
    assert taper["taper"] > 40.0
    weight = client.post(
        "/api/exit/weight?entry=2.5&exit=2.3&width=1250&length=4200"
    ).get_json()
    assert weight["weight"] > 0.0
    client.post("/api/strip/advance?delta=20")
    client.post("/api/strip/speed?speed=2")
    eta = client.get("/api/strip/eta?target=120").get_json()
    assert eta["eta"] > 0.0


def test_sequence_clear_endpoint(client: FlaskClient) -> None:
    client.post("/api/entry/sample?value=1")
    assert client.post("/api/sequence/clear").status_code == 200
    assert client.get("/api/sequence").get_json()["sequence"]["steps"] == []


CYCLE_QS = "coil=C-42&target=90&level=4.5&voltage=24&current=300&speed=1.4"


def test_seams_carry_grade_and_coil_and_filter_by_coil(client: FlaskClient) -> None:
    client.post("/api/weld/heat-target?value=4800")
    client.post(f"/api/cycle?{CYCLE_QS}")
    seams = client.get("/api/weld/seams").get_json()["seams"]
    assert seams
    assert all(seam["coil_id"] == "C-42" for seam in seams)
    assert {seam["grade"] for seam in seams} <= {"A", "B", "C", "U"}
    follow_up = next(seam for seam in seams if seam["heat_input"] > 0)
    assert follow_up["grade"] == "B"
    assert follow_up["voltage"] == 24
    assert follow_up["current"] == 300
    filtered = client.get("/api/weld/seams?coil=C-42").get_json()["seams"]
    assert len(filtered) == len(seams)
    assert client.get("/api/weld/seams?coil=C-other").get_json()["seams"] == []


def test_repair_registration_and_history(client: FlaskClient) -> None:
    client.post("/api/weld/heat-target?value=4800")
    client.post(f"/api/cycle?{CYCLE_QS}")
    seam = client.get("/api/weld/seams").get_json()["seams"][0]
    response = client.post(
        f"/api/weld/repair?id={seam['seam_id']}&reason=strip-break&operator=zhang"
    )
    assert response.status_code == 200
    repair = response.get_json()["repair"]
    assert repair["seam_id"] == seam["seam_id"]
    assert repair["coil_id"] == "C-42"
    detail = client.get(f"/api/weld/seam?id={seam['seam_id']}").get_json()
    assert len(detail["repairs"]) == 1
    repairs = client.get("/api/weld/repairs?coil=C-42").get_json()["repairs"]
    assert len(repairs) == 1
    assert client.post("/api/weld/repair?id=ghost").status_code == 409
    assert client.post("/api/weld/repair").status_code == 400


def test_manual_seam_registration(client: FlaskClient) -> None:
    client.post("/api/weld/heat-target?value=4800")
    response = client.post(
        "/api/weld/seam/manual?coil=C-55&pos=12&tension=80&heat=4800"
        "&voltage=24&current=300&speed=1.5"
    )
    seam = response.get_json()["seam"]
    assert seam["source"] == "manual"
    assert seam["grade"] == "A"
    assert seam["coil_id"] == "C-55"
    assert client.post("/api/weld/seam/manual?pos=1&tension=1&heat=1").status_code == 400


def test_heat_target_rejects_non_positive_values(client: FlaskClient) -> None:
    assert client.post("/api/weld/heat-target?value=0").status_code == 409
