"""Offline scenario evals: does the real agent call the right tools on the right turns?

The unit tests cover the pure helpers; these cover the part that only an LLM can get
wrong -- whether the model maps what a caller says onto the tool surface at all. Every
scenario is hand-labelled: `turns` is what a resident says, `expected` is the tool
behaviour a case worker would consider correct. Tools run against the real backend
in-process (httpx.ASGITransport over the FastAPI app, fresh SQLite per test), so a
scenario also proves the case really landed in the DB.

Marked `eval` and deselected by default -- they hit a live LLM and need LIVEKIT_* keys.
Run with: uv run pytest -m eval -q
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from livekit.agents import AgentSession, inference

AGENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_DIR / "src"))
sys.path.insert(0, str(AGENT_DIR.parent / "backend"))

import agent as agent_mod  # noqa: E402
from agent import Assistant, digits  # noqa: E402

MODEL = "openai/gpt-4.1-mini"
CASE_TOOLS = ("create_case", "update_case", "lookup_case", "add_note")


# --- expectations -------------------------------------------------------------------
# `must` is an ordered subsequence: the named calls have to occur in this relative order,
# other calls may interleave. `must_not` names tools that may never fire.


def issue(kind):
    return ("update_case", lambda a: a.get("issue_type") == kind)


def phone_is(number):
    return ("create_case", lambda a: digits(a.get("phone", "")) == number)


NAME_PHONE = ["Hi, my name is Maria Lopez.", "It's 925.915.7062.", "Yes, that's right."]

SCENARIOS = [
    (
        "pothole maps to pothole",
        [*NAME_PHONE, "There's a huge pothole on Elm Street."],
        {"must": [("create_case", None), issue("pothole")]},
    ),
    (
        "trash not collected maps to missed_pickup",
        [*NAME_PHONE, "My trash wasn't collected on Tuesday."],
        {"must": [("create_case", None), issue("missed_pickup")]},
    ),
    (
        "dark street lamp maps to streetlight",
        [*NAME_PHONE, "The street lamp outside my house has been dark for a week."],
        {"must": [("create_case", None), issue("streetlight")]},
    ),
    (
        "water main leak maps to water",
        [*NAME_PHONE, "Water is gushing out of a broken main on Third Avenue."],
        {"must": [("create_case", None), issue("water")]},
    ),
    (
        "stray dog maps to animal",
        [*NAME_PHONE, "There's a stray dog running loose in the park."],
        {"must": [("create_case", None), issue("animal")]},
    ),
    (
        "loud neighbours falls back to other",
        [*NAME_PHONE, "My neighbours are being really loud every night."],
        {"must": [("create_case", None), issue("other")]},
    ),
    (
        "phone spoken with dots and dashes",
        ["I'm Dan Reed.", "Nine two five dot nine one five dash seven zero six two.", "Correct."],
        {"must": [phone_is("9259157062")], "db_phone": "9259157062"},
    ),
    (
        "phone spoken entirely in words",
        [
            "This is Ana Diaz.",
            "My number is five five five, one two three, four five six seven.",
            "Yes.",
        ],
        {"must": [phone_is("5551234567")], "db_phone": "5551234567"},
    ),
    (
        "seven digit phone is refused and files nothing",
        ["I'm Sam Cole.", "It's 915-7062.", "Yes that's it."],
        {
            "must": [("create_case", None)],
            "output_contains": "ten",
            "db_empty": True,
        },
    ),
    (
        "name without a phone does not open a case",
        ["Hi, I'd like to report something. My name is Tom Blake."],
        {"must_not": CASE_TOOLS},
    ),
    (
        "case is opened before the issue is known",
        [*NAME_PHONE, "There's a pothole on Elm Street.", "It's about a foot wide near the curb."],
        {
            "must": [
                ("create_case", None),
                issue("pothole"),
                ("update_case", lambda a: bool(a.get("description"))),
            ],
            "create_before_update": True,
        },
    ),
    (
        "lookup by phone uses the digits the caller gave",
        ["Can you check on my case? My number is 925-915-7062."],
        {
            "must": [("lookup_case", lambda a: digits(a.get("phone", "")) == "9259157062")],
            "must_not": ("create_case",),
        },
    ),
    (
        "spelled-out case id normalises to C-1001",
        ["Please add a note to case c one zero zero one.", "The pothole got bigger."],
        {
            "must": [("add_note", None)],
            "note_on": "C-1001",
        },
    ),
    (
        "out of scope question touches no case tool",
        ["What time does the public pool open on Saturday?"],
        {"must_not": CASE_TOOLS},
    ),
    (
        "second out of scope question touches no case tool",
        ["Hi there.", "How much is a dog licence and where do I buy one?"],
        {"must_not": CASE_TOOLS},
    ),
    # --- added after warm transfer (#15), end_call, nullable issue_type (5b968fd) ---
    (
        "asking for a person transfers and keeps the line open",
        ["I don't want to talk to a robot. Put me through to a real person about my water bill."],
        {"must": [("transfer_to_staff", None)], "must_not": ("end_call", *CASE_TOOLS)},
    ),
    (
        "goodbye after a filed request ends the call",
        [*NAME_PHONE, "There's a pothole on Elm Street.", "About a foot wide by the curb.",
         "No, that's everything. Thanks, bye."],
        {"must": [("create_case", None), ("end_call", None)], "must_not": ("transfer_to_staff",)},
    ),
    (
        "case opened at name and phone has no issue type yet",
        NAME_PHONE,
        {"must": [("create_case", None)], "must_not": ("update_case",), "db_unclassified": True},
    ),
    (
        "lookup reads the case status back to the caller",
        ["Any update on my case? My number is 925-915-7062."],
        {"must": [("lookup_case", None)], "seed_case": "C-1001", "reply_contains": "open"},
    ),
]


# --- harness ------------------------------------------------------------------------


@pytest.fixture
def backend(tmp_path, monkeypatch):
    """The real FastAPI app on a throwaway DB, wired into the agent's httpx calls.

    Stubbing the backend would let a scenario "pass" while writing nothing; running the
    real app means a green scenario also means the case exists.
    """
    monkeypatch.setenv("CASES_DB", str(tmp_path / "evals.db"))
    from app import db, main

    monkeypatch.setattr(db, "DB_PATH", os.environ["CASES_DB"])
    db.init_db()  # ASGITransport does not run the lifespan that normally does this

    transport = httpx.ASGITransport(app=main.app)
    real_client = httpx.AsyncClient

    def client(*args, **kwargs):
        kwargs.setdefault("base_url", agent_mod.BACKEND)
        return real_client(*args, transport=transport, **kwargs)

    # patch the name inside agent.py, not httpx itself: the LLM client is also httpx,
    # and replacing httpx.AsyncClient globally would route inference at the backend too
    monkeypatch.setattr(agent_mod, "httpx", SimpleNamespace(AsyncClient=client))
    return main.app


def sync_client(app):
    """Same app, sync, for seeding and for reading the DB back after the run."""
    from fastapi.testclient import TestClient

    return TestClient(app)


def calls_of(results):
    """Flatten every RunResult into (tool_name, arguments, output) in chronological order."""
    out = []
    pending = {}
    for r in results:
        for ev in r.events:
            if ev.type == "function_call":
                try:
                    args = json.loads(ev.item.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                pending[ev.item.call_id] = [ev.item.name, args, ""]
                out.append(pending[ev.item.call_id])
            elif ev.type == "function_call_output":
                if ev.item.call_id in pending:
                    pending[ev.item.call_id][2] = str(ev.item.output)
    return [tuple(c) for c in out]


def replies_of(results):
    """Every assistant message the agent produced, in order (what the caller would hear)."""
    out = []
    for r in results:
        for ev in r.events:
            item = getattr(ev, "item", None)
            if ev.type == "message" and getattr(item, "role", None) == "assistant":
                out.append(item.text_content or "")
    return out


def check(calls, expected):
    """Turn a hand-labelled expectation into asserts with messages that name the miss."""
    seen = [(n, a) for n, a, _ in calls]

    i = 0
    for name, pred in expected.get("must", []):
        for j in range(i, len(calls)):
            if calls[j][0] == name and (pred is None or pred(calls[j][1])):
                i = j + 1
                break
        else:
            raise AssertionError(
                f"expected a {name} call (matching its argument check) after index {i}; got {seen}"
            )

    for name in expected.get("must_not", ()):
        assert name not in [n for n, _ in seen], f"{name} must not fire; got {seen}"

    if expected.get("create_before_update"):
        names = [n for n, _ in seen]
        assert "create_case" in names and "update_case" in names, f"got {seen}"
        assert names.index("create_case") < names.index("update_case"), (
            f"create_case must fire before any update_case; got {names}"
        )

    if "output_contains" in expected:
        needle = expected["output_contains"]
        assert any(needle in out for _, _, out in calls), (
            f"no tool output contained {needle!r}; got {[o for _, _, o in calls]}"
        )


async def run_scenario(turns):
    session = AgentSession(llm=inference.LLM(model=MODEL))
    async with session:
        await session.start(Assistant())
        return [await session.run(user_input=t) for t in turns]


@pytest.mark.eval
@pytest.mark.parametrize(
    "name,turns,expected", SCENARIOS, ids=[s[0].replace(" ", "_") for s in SCENARIOS]
)
async def test_scenario(name, turns, expected, backend):
    """Each scenario encodes a case worker's judgement of what should have been filed.

    A wrong issue_type or a case opened without a phone is a real intake defect, not a
    style difference, so these must fail when the agent stops behaving that way.
    """
    http = sync_client(backend)
    if expected.get("note_on") or expected.get("seed_case"):
        # a note needs a case to hang off; seed it through the backend's own endpoint
        seeded = http.post(
            "/cases",
            json={
                "name": "Maria Lopez",
                "phone": "9259157062",
                "issue_type": "pothole",
                "description": "Pothole on Elm St",
            },
        )
        want = expected.get("note_on") or expected["seed_case"]
        assert seeded.status_code == 201 and seeded.json()["id"] == want

    results = await run_scenario(turns)
    calls = calls_of(results)
    check(calls, expected)

    if expected.get("db_empty"):
        assert http.get("/cases").json() == [], (
            f"a refused phone number must leave no case behind; tool calls: {calls}"
        )
    if expected.get("db_phone"):
        stored = http.get("/cases", params={"phone": expected["db_phone"]}).json()
        assert stored, f"no case stored under {expected['db_phone']}; tool calls: {calls}"
    if expected.get("note_on"):
        notes = http.get(f"/cases/{expected['note_on']}").json()["notes"]
        assert notes.strip(), f"add_note left {expected['note_on']} without notes; calls: {calls}"
    if expected.get("db_unclassified"):
        # nullable issue_type: a case opened at name+phone must be stored as "not classified yet"
        stored = http.get("/cases").json()
        assert len(stored) == 1 and stored[0]["issue_type"] is None, f"expected one unclassified case; got {stored}"
    if expected.get("reply_contains"):
        said = " ".join(replies_of(results)).lower()
        assert expected["reply_contains"] in said, f"agent never said {expected['reply_contains']!r}; said: {said!r}"
