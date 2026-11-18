"""Regression test from docs/trace_case.md: swarm C-002@55 (FM-03 ticket_trust).

The first wrong step is event 3, `model_override {"delay_days": 5}`: the agent replaced the DB's
delay (2 days, below SHIP-LATE-03's 3-day minimum) with the number the customer wrote in the
ticket, so the quote became 20,000đ instead of no entitlement. This test pins both graders that
see it: DbFactKept (step level, the override event) and RefundAmountCorrect (outcome, the ledger).
"""
import io
import contextlib

import pytest

pytestmark = pytest.mark.student


def _grade(shape: str, claim_id: str = "C-002", seed: int = 55) -> dict:
    from pydantic_evals.evaluators import EvaluatorContext
    from lab9.graders import DbFactKept, RefundAmountCorrect
    from lab9.trace_case import investigate

    with contextlib.redirect_stdout(io.StringIO()):
        case = investigate(shape, claim_id, seed)
    ctx = EvaluatorContext(name="trace_case", inputs={}, metadata=None, expected_output=case["label"],
                           output=case["trial"], duration=0.0, _span_tree=None, attributes={}, metrics={})
    events = case["trial"]["events"]
    return {"db_fact_kept": DbFactKept().evaluate(ctx).value,
            "refund_ok": RefundAmountCorrect().evaluate(ctx).value,
            "first_override": next((i for i, e in enumerate(events, 1) if e.get("kind") == "model_override"), None),
            "ledger": case["trial"]["snapshot"]["refund_vnd"]}


def test_lab9_trace_case_swarm_c002_seed55_is_caught():
    g = _grade("swarm")
    assert g["first_override"] == 3, "first wrong step should be event 3 (model_override)"
    assert g["db_fact_kept"] is False
    assert g["refund_ok"] is False and g["ledger"] == 20000


def test_lab9_trace_case_fixed_c002_seed55_passes():
    g = _grade("fixed")
    assert g["first_override"] is None
    assert g["db_fact_kept"] is True
    assert g["refund_ok"] is True and g["ledger"] == 0
