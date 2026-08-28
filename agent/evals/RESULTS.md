# Agent scenario evals — 12/15

Fifteen hand-labelled calls run through the real `Assistant` from `src/agent.py` against the
real FastAPI backend in-process (`httpx.ASGITransport`, fresh SQLite per scenario). No audio:
`AgentSession.run(user_input=...)` per turn, assertions over the recorded tool calls plus, where
it matters, what actually landed in the DB.

- Model: `openai/gpt-4.1-mini` via LiveKit Inference (the same model the agent ships with)
- Scenarios: `agent/tests/test_scenarios.py`
- Reproduce: `cd agent && uv run pytest -m eval -q` (needs `LIVEKIT_*` in `agent/.env`)
- Default `uv run pytest` deselects these: 7 passed, 15 deselected, offline and key-free.

Scored on a **single run** (2026-08-28, 90s wall clock). LLM evals flake; the run was not
repeated to improve the number.

| # | Scenario | Expected | Got | Pass |
|---|---|---|---|---|
| 1 | pothole maps to `pothole` | `create_case`, then `update_case(issue_type="pothole")` | as expected | ✅ |
| 2 | trash not collected maps to `missed_pickup` | `create_case`, then `update_case(issue_type="missed_pickup")` | as expected | ✅ |
| 3 | dark street lamp maps to `streetlight` | `create_case`, then `update_case(issue_type="streetlight")` | as expected | ✅ |
| 4 | water main leak maps to `water` | `create_case`, then `update_case(issue_type="water")` | failed (see below) | ❌ |
| 5 | stray dog maps to `animal` | `create_case`, then `update_case(issue_type="animal")` | as expected | ✅ |
| 6 | loud neighbours falls back to `other` | `create_case`, then `update_case(issue_type="other")` | as expected | ✅ |
| 7 | phone said with dots/dashes | `create_case` whose `digits(phone) == 9259157062`; case in DB | as expected | ✅ |
| 8 | phone said entirely in words | `create_case` whose `digits(phone) == 5551234567`; case in DB | as expected | ✅ |
| 9 | 7-digit phone refused | `create_case` returns the "ten digits" refusal; `GET /cases` empty | as expected | ✅ |
| 10 | name only, no phone | none of the four case tools fire | as expected | ✅ |
| 11 | create-early ordering | `create_case` before any `update_case`, then issue_type, then description | as expected | ✅ |
| 12 | lookup by phone | `lookup_case` with `digits(phone) == 9259157062`, no `create_case` | no tool call at all | ❌ |
| 13 | "case c one zero zero one" | `add_note` on the seeded `C-1001`, notes non-empty | no tool call at all | ❌ |
| 14 | pool hours (out of scope) | none of the four case tools fire | as expected | ✅ |
| 15 | dog licence (out of scope) | none of the four case tools fire | as expected | ✅ |

**Total: 12 / 15.**

## Failures, verbatim

**#12 — lookup by phone uses the digits the caller gave**
Turns: `["Can you check on my case? My number is 925-915-7062."]`

```
calls = []
expected = {'must': [('lookup_case', <function <lambda> at 0x10e7a6520>)], 'must_not': ('create_case',)}
E  AssertionError: expected a lookup_case call (matching its argument check) after index 0; got []
tests/test_scenarios.py:216: AssertionError
```

Real defect, and the interesting one: given the phone number in the *same* turn as the request,
the agent answered in words instead of calling `lookup_case`. The instructions say to use "the
phone number they already gave on this call" — on the first turn there is no "already", and the
model treats the number as not-yet-confirmed. A caller who leads with their number gets nothing
looked up.

**#13 — spelled-out case id normalises to C-1001**
Turns: `["Please add a note to case c one zero zero one.", "The pothole got bigger."]`

```
calls = [], expected = {'must': [('add_note', None)], 'note_on': 'C-1001'}
E  AssertionError: expected a add_note call (matching its argument check) after index 0; got []
tests/test_scenarios.py:216: AssertionError
```

Real defect. The agent never called `add_note` across two turns, so `add_note`'s `C-` normalisation
(which the code does handle) was never exercised. Two turns is probably too few — the model asks
what the note should say, then asks again — but a caller shouldn't need three.

**#4 — water main leak maps to `water`**
Failed in the scored run at the same `check()` step; its assertion text scrolled out of the
captured output. A single diagnostic re-run of *only* this scenario passed (`1 passed in 7.79s`),
so this one is flake, not a defect. The scored total above still counts it as a failure — the run
is the run.

## What these do and don't cover

They cover tool *selection and arguments* — the part only an LLM can get wrong, and the part the
unit tests in `tests/test_helpers.py` cannot reach. They do not cover STT (text in, not audio),
TTS, barge-in, or wording of what the agent says. A scenario passes only if the backend write it
implies also happened, so a green row means a case (or note) really exists.

## Re-run after the prompt fixes (14:20, commit 3285bf1 on main via PR #2)

14/15. `lookup_by_phone` and `spelled_case_id` now pass. Remaining miss: `loud_neighbours_falls_back_to_other` — the agent opened the case but did not call `update_case(issue_type="other")` within the scenario's turn budget. One run; not re-rolled.

## Third run — 19 scenarios, 15:08 (main 5b968fd + four new scenarios)

**19/19**, 104 s wall clock, one run, not re-rolled.

Four scenarios added for features shipped after the first run:

| # | Scenario | Expected | Got | Pass |
|---|---|---|---|---|
| 16 | asking for a person transfers and keeps the line open | `transfer_to_staff`; never `end_call` or a case tool | as expected | ✅ |
| 17 | goodbye after a filed request ends the call | `create_case` … then `end_call`; never `transfer_to_staff` | as expected | ✅ |
| 18 | case opened at name and phone has no issue type yet | `create_case`, no `update_case`; DB row has `issue_type: null` | as expected | ✅ |
| 19 | lookup reads the case status back to the caller | `lookup_case` on the seeded C-1001; the agent's reply contains "open" | as expected | ✅ |

Scenarios 1–15 unchanged and all passing on this run, including "loud neighbours → other" (the
second run's miss) and "water main leak → water" (the first run's).

Two harness additions: `replies_of()` collects the agent's spoken replies so a scenario can assert
what the caller would *hear*, not only which tool fired (#19); `db_unclassified` reads the case
back to prove the null landed (#18).

**Regression found and fixed by this run:** commit `2f47aed` added `tests/conftest.py` with
`os.environ.setdefault("LIVEKIT_API_KEY", "test")` so unit tests pass on a keyless clone. It ran
before `agent.py`'s `load_dotenv`, which does not override existing variables, so every eval hit
LiveKit Inference with the key `"test"` → 401 on all 19. Fix: conftest loads `agent/.env` first,
then applies the dummies. `uv run pytest` (unit) still passes without keys.
