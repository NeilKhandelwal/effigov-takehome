"""The eval harness's own pure seam: how many attempts a scenario gets.

The retry loop itself only exists against a live LLM, but the decision it loops on is
`EVAL_RETRIES` arithmetic, and getting it wrong is silent -- a misread 0 would keep
retrying and a misread empty string would spend nothing on the retry the nightly needs.
"""
import pytest
from conftest import attempts_from_env


def test_attempts_default_to_one_retry():
    """Unset is the nightly's case: one roll plus one, so a single miss is not a red run."""
    assert attempts_from_env({}) == 2


def test_attempts_treat_empty_as_unset():
    """evals.yml passes `${{ vars.EVAL_RETRIES }}`, which is "" when the repo var is unset."""
    assert attempts_from_env({"EVAL_RETRIES": ""}) == 2
    assert attempts_from_env({"EVAL_RETRIES": " "}) == 2


def test_attempts_zero_restores_the_strict_single_roll():
    """0 has to survive the fallback: it is the only way back to one-miss-fails-the-run."""
    assert attempts_from_env({"EVAL_RETRIES": "0"}) == 1


def test_attempts_honour_more_retries():
    """A flakier model can be given more rolls without a code change."""
    assert attempts_from_env({"EVAL_RETRIES": "2"}) == 3


def test_attempts_refuse_a_negative():
    """-1 would mean zero attempts: the scenario never runs and the run is green for nothing."""
    with pytest.raises(ValueError):
        attempts_from_env({"EVAL_RETRIES": "-1"})
