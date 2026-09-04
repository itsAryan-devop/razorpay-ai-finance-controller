"""Many-to-one (batch) settlement matching.

Real Razorpay settlements pay out a BATCH of orders in one lump credit. Matching means
finding which subset of open orders sums (net of fees) to that credit — and, when more
than one subset fits, ESCALATING rather than guessing. These tests pin both: the
arithmetic is correct, and genuine ambiguity is deferred, never faked.
"""
import matcher


# ------------------------------------------------------------- the algorithm, in isolation
def test_subset_sum_finds_the_unique_batch():
    cands = [("a", 100), ("b", 250), ("c", 90), ("d", 999)]
    subsets = matcher.subset_sum_match(cands, target=440)     # a + b + c
    assert subsets == [("a", "b", "c")]


def test_subset_sum_reports_all_subsets_when_ambiguous():
    # two orders of 200 each + two decoys of 200 each; target 400 -> every pair fits
    cands = [("o1", 200), ("o2", 200), ("d1", 200), ("d2", 200)]
    subsets = matcher.subset_sum_match(cands, target=400)
    assert len(subsets) > 1                                   # genuinely ambiguous


def test_subset_sum_returns_nothing_when_impossible():
    cands = [("a", 100), ("b", 250)]
    assert matcher.subset_sum_match(cands, target=999) == []


def test_subset_sum_respects_the_size_cap():
    cands = [("a", 1), ("b", 1), ("c", 1), ("d", 1), ("e", 1), ("f", 1)]
    # target 6 needs all six, but max_size=5 -> no subset of size <=5 sums to 6
    assert matcher.subset_sum_match(cands, target=6, max_size=5) == []


# -------------------------------------------------------------- against the real fixture
def test_batch_fixture_resolves_correctly_and_escalates_the_ambiguous_one():
    bl, br = matcher._load_batch()
    assert br, "batch fixture missing — run generate_data.py"
    records = matcher.match_batch_settlements(bl, br)
    m = matcher.score_batches(records, matcher._load_batch_truth())

    assert m["total"] == 5
    assert m["correct"] == 4               # the 4 clean batches resolve to the right order-set
    assert m["escalated"] == 1             # the deliberately ambiguous batch is deferred
    assert m["wrong"] == 0                 # never a confidently wrong batch


def test_resolved_batches_match_the_answer_key_exactly():
    bl, br = matcher._load_batch()
    truth = matcher._load_batch_truth()
    for rec in matcher.match_batch_settlements(bl, br):
        if rec["route"] == "AUTO":
            assert rec["chosen"] == truth[rec["settlement_id"]]


def test_net_of_fees_is_integer_paise():
    v = matcher.net_of_fees(250000)
    assert isinstance(v, int) and 0 < v < 250000
