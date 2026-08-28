from tests.test_cases import BODY


def test_call_lifecycle_sets_ended_at(client):
    """The agent opens a call, streams lines, then ends it; ended_at is what drops it from 'Live calls'."""
    r = client.post("/calls", json={})
    assert r.status_code == 201
    call = r.json()
    assert call == {"id": "CALL-1", "case_id": None, "status": "active",
                    "started_at": call["started_at"], "ended_at": None}
    assert client.post("/calls/CALL-1/transcript", json={"role": "user", "text": "hi"}).status_code == 201
    ended = client.patch("/calls/CALL-1", json={"status": "ended"}).json()
    assert ended["status"] == "ended" and ended["ended_at"].endswith("Z")
    assert client.get("/calls", params={"status": "active"}).json() == []
    assert [c["id"] for c in client.get("/calls").json()] == ["CALL-1"]


def test_get_call_includes_transcript_in_order(client):
    """/calls/[id] renders the conversation; out-of-order lines would read as nonsense."""
    client.post("/calls")
    for i, role in enumerate(["user", "agent", "user"]):
        r = client.post("/calls/CALL-1/transcript", json={"role": role, "text": f"line {i}"})
        assert r.status_code == 201 and r.json()["call_id"] == "CALL-1"
    lines = client.get("/calls/CALL-1").json()["transcript"]
    assert [(l["role"], l["text"]) for l in lines] == [("user", "line 0"), ("agent", "line 1"), ("user", "line 2")]
    assert client.get("/calls/CALL-9").status_code == 404
    assert client.post("/calls/CALL-9/transcript", json={"role": "user", "text": "x"}).status_code == 404


def test_patch_unknown_case_id_is_404(client):
    """Linking a call to a case the agent mistyped would orphan the transcript on the case page."""
    client.post("/calls")
    r = client.patch("/calls/CALL-1", json={"case_id": "C-9999"})
    assert r.status_code == 404 and r.json()["detail"] == "case not found"
    client.post("/cases", json=BODY)
    assert client.patch("/calls/CALL-1", json={"case_id": "C-1001"}).json()["case_id"] == "C-1001"


def test_case_calls_oldest_first_with_transcript(client):
    """Case detail shows the history of calls about that case, in the order they happened."""
    client.post("/cases", json=BODY)
    for _ in range(3):
        client.post("/calls")
    client.patch("/calls/CALL-2", json={"case_id": "C-1001"})
    client.patch("/calls/CALL-1", json={"case_id": "C-1001"})
    client.post("/calls/CALL-2/transcript", json={"role": "agent", "text": "hello"})
    calls = client.get("/cases/C-1001/calls").json()
    assert [c["id"] for c in calls] == ["CALL-1", "CALL-2"]
    assert calls[1]["transcript"][0]["text"] == "hello" and calls[0]["transcript"] == []
    assert client.get("/cases/C-9999/calls").status_code == 404


def test_ws_frame_after_write(client):
    """Dashboard refetches on any frame; without it, live calls lag behind the 2s poll."""
    with client.websocket_connect("/ws") as ws:
        client.post("/cases", json=BODY)
        assert ws.receive_json() == {"type": "case", "id": "C-1001"}
        client.post("/calls")
        client.post("/calls/CALL-1/transcript", json={"role": "user", "text": "hi"})
        assert ws.receive_json() == {"type": "call", "id": "CALL-1"}
        assert ws.receive_json() == {"type": "transcript", "id": "CALL-1"}
