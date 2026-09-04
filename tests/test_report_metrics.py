"""Tests for the reporting aggregations: confidence calibration, rupee attribution,
and the absolute wrong-match count.

These exist because all three are CLAIMS about honesty — "our confidence means
something", "every rupee is accounted for", "zero wrong matches". A claim nobody tests
is just a sentence in a README.
"""
import matcher
import pipeline
import report_metrics


def test_every_rupee_of_the_ledger_is_attributed():
    """The headline honesty property: ledger value splits exactly into settled +
    never-settled, with nothing falling through the cracks."""
    ledger, recon = matcher._load()
    results = matcher.reconcile(ledger, recon)
    m = report_metrics.money_impact(results, ledger, recon)

    assert m["total_ledger"] > 0
    assert m["settled_value"] + m["never_settled_value"] == m["total_ledger"]
    assert m["unattributed_value"] == 0          # the residual must be exactly zero
    assert m["settled_orders"] + m["never_settled_orders"] == len(ledger)


def test_money_is_integer_paise_never_float():
    """A reconciler must never float money — every reported figure stays an int."""
    ledger, recon = matcher._load()
    results = matcher.reconcile(ledger, recon)
    m = report_metrics.money_impact(results, ledger, recon)
    for key, value in m.items():
        assert isinstance(value, int), f"{key} is {type(value).__name__}, expected int"


def test_resolved_credits_reduce_unexplained_money():
    """Once the handler pairs an orphan credit to its true order, that money is no
    longer 'unexplained' — the rupee figure must drop accordingly."""
    ledger, recon = matcher._load()
    results = matcher.reconcile(ledger, recon)
    before = report_metrics.money_impact(results, ledger, recon)

    orphan = next(r.entity_id for r in results if r.label == "EXTRA_CREDIT")
    after = report_metrics.money_impact(results, ledger, recon,
                                        resolved_credits={orphan})
    assert after["unexplained_credits"] == before["unexplained_credits"] - 1
    assert after["unexplained_value"] < before["unexplained_value"]


def test_calibration_reports_empirical_accuracy_not_asserted_confidence():
    """A high-confidence band must be graded against the answer key, not trusted."""
    truth = {"orderA": "creditA", "orderB": "creditB"}
    records = [
        {"entity_id": "orderA", "chosen": "creditA", "confidence": 0.9},   # right
        {"entity_id": "orderB", "chosen": "creditZZ", "confidence": 0.9},  # confidently WRONG
    ]
    rows = {r["band"]: r for r in report_metrics.confidence_calibration(records, truth)}
    auto = rows["AUTO_RESOLVE"]
    assert auto["n"] == 2 and auto["gradeable"] == 2
    assert auto["correct"] == 1
    assert auto["accuracy"] == 0.5      # the wrong one is NOT hidden by its confidence


def test_calibration_does_not_score_ungradeable_rows_as_correct():
    """A decision whose entity isn't in the answer key can't be graded — it must be
    excluded from accuracy, never silently counted as a win."""
    records = [{"entity_id": "unknown_order", "chosen": "creditX", "confidence": 0.9}]
    rows = {r["band"]: r for r in report_metrics.confidence_calibration(records, {})}
    auto = rows["AUTO_RESOLVE"]
    assert auto["n"] == 1
    assert auto["gradeable"] == 0
    assert auto["accuracy"] is None     # honest "unknown", not a fabricated 1.00


def test_bands_are_stable_even_when_empty():
    rows = report_metrics.confidence_calibration([], {})
    assert [r["band"] for r in rows] == ["AUTO_RESOLVE", "FLAG", "ESCALATE"]
    assert all(r["n"] == 0 and r["accuracy"] is None for r in rows)


def test_pipeline_reports_zero_wrong_matches_and_full_attribution():
    """End to end on the golden path: no wrong pairings, every rupee attributed."""
    r = pipeline.run(commit=False, provider="heuristic")
    assert r["pairing"]["wrong_after"] == 0
    assert r["pairing"]["wrong_before"] == 0
    assert r["money"]["unattributed_value"] == 0
    assert r["calibration"]                       # calibration table is populated
