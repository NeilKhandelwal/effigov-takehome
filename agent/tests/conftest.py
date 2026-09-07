import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Real keys first (the scenario evals need them), then dummies so the unit tests stay green
# on a keyless clone: Assistant() builds the LiveKit LLM client, which refuses to construct
# without a key, but the unit tests never touch the network. setdefault must come AFTER
# load_dotenv or the dummy wins and the evals fail with 401.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
for var in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
    os.environ.setdefault(var, "test")


# --- the eval spend cap ---------------------------------------------------------------
# The scenarios call a live LLM, so an agent that loops or a call that hangs spends real
# money with nobody watching -- the nightly CI run most of all. Two ceilings, both env:
# a hard count of completions for the whole run, and a wall clock per scenario.

# A real 21-scenario run spends 113 completions: 5.4 a scenario on average, 10 at the
# worst (agent/evals/RESULTS.md). 10 each leaves ~1.9x headroom over the whole run --
# room for a flakier night, none for a loop.
CALLS_PER_SCENARIO = 10
DEFAULT_SCENARIO_TIMEOUT_S = 90.0


class EvalBudgetError(RuntimeError):
    """Raised in place of the completion that would have gone over the cap."""


class EvalBudget:
    """The run's two ceilings, plus the completion count they are checked against.

    Counting inside the LLM client is the only honest seam: a scenario's turn count says
    nothing about how many completions a tool call costs, so only the client knows.
    """

    def __init__(self, limit, timeout_s):
        self.limit = limit
        self.timeout_s = timeout_s
        self.used = 0
        self.per_scenario = {}
        self.spent = False  # sticky: once over, every remaining scenario fails fast

    def spend(self, scenario):
        """Charge one completion *before* the request leaves, and refuse the one over."""
        if self.used >= self.limit:
            self.spent = True
            raise EvalBudgetError(
                f"LLM call cap reached: {self.used} completions used, "
                f"EVAL_MAX_LLM_CALLS={self.limit}. Remaining scenarios are not run. "
                f"Per scenario so far: {self.per_scenario}"
            )
        self.used += 1
        self.per_scenario[scenario] = self.per_scenario.get(scenario, 0) + 1

    def raise_if_spent(self):
        """AgentSession swallows errors raised inside a turn; this call does not."""
        if self.spent:
            raise EvalBudgetError(
                f"LLM call cap reached: EVAL_MAX_LLM_CALLS={self.limit} completions "
                f"spent by an earlier scenario; this one was not run"
            )


@pytest.fixture(scope="session")
def eval_budget(request):
    """One budget for the whole pytest session, so the cap is per run and not per test."""
    scenarios = sum(1 for item in request.session.items if item.get_closest_marker("eval"))
    limit = int(os.environ.get("EVAL_MAX_LLM_CALLS") or CALLS_PER_SCENARIO * max(scenarios, 1))
    timeout_s = float(os.environ.get("EVAL_SCENARIO_TIMEOUT_S") or DEFAULT_SCENARIO_TIMEOUT_S)
    budget = EvalBudget(limit, timeout_s)
    request.config._eval_budget = budget  # for the terminal summary below
    return budget


def pytest_terminal_summary(terminalreporter, config):
    """Print what the run actually spent: it is what the cap's default is tuned against."""
    budget = getattr(config, "_eval_budget", None)
    if budget is None or not budget.used:
        return
    terminalreporter.write_sep("-", "LLM calls")
    for scenario, n in budget.per_scenario.items():
        terminalreporter.write_line(f"{n:>4}  {scenario}")
    terminalreporter.write_line(f"{budget.used:>4}  total (cap {budget.limit})")
