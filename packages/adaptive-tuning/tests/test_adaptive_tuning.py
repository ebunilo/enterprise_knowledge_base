import random

import pytest

from adaptive_tuning import (
    Action,
    EvalCase,
    EvalResult,
    Experiment,
    InvalidParameterValue,
    LockedParameterError,
    ParameterRegistry,
    Safety,
    Signals,
    choose_arm,
    compare_to_baseline,
    compute_reward,
    decide,
    evaluate,
    is_enrolled,
    propose_arms,
    resolve,
)
from adaptive_tuning.experiments import Arm

REGISTRY = ParameterRegistry()


# --- Registry -------------------------------------------------------------------

def test_security_parameters_are_locked():
    for key in ("acl.postgres_validation", "acl.enforce_clearance", "citation.required",
                "citation.min_valid_ratio", "retrieval.include_archived", "llm.treat_documents_as_untrusted"):
        assert REGISTRY.get(key).safety is Safety.LOCKED
        with pytest.raises(LockedParameterError):
            REGISTRY.validate_change(key, not REGISTRY.get(key).default if isinstance(
                REGISTRY.get(key).default, bool) else 0.5)


def test_locked_parameters_are_not_tunable():
    assert all(spec.safety is not Safety.LOCKED for spec in REGISTRY.tunable())
    with pytest.raises(PermissionError):
        propose_arms(REGISTRY.get("citation.required"), True)


def test_bounds_and_types_enforced():
    with pytest.raises(InvalidParameterValue):
        REGISTRY.validate_change("retrieval.vector.top_k", 1000)
    with pytest.raises(InvalidParameterValue):
        REGISTRY.validate_change("retrieval.vector.top_k", 12.5)
    with pytest.raises(InvalidParameterValue):
        REGISTRY.validate_change("retrieval.fusion.method", "magic")
    assert REGISTRY.validate_change("retrieval.vector.top_k", 40.0) == 40


def test_defaults_match_agents_md():
    defaults = REGISTRY.defaults()
    assert defaults["retrieval.vector.top_k"] == 30
    assert defaults["retrieval.bm25.top_k"] == 30
    assert defaults["retrieval.graph.top_k"] == 20
    assert defaults["chunking.target_tokens"] == 512
    assert defaults["chunking.max_tokens"] == 768
    assert defaults["chunking.overlap_tokens"] == 64


# --- Resolver ---------------------------------------------------------------------

def test_precedence_and_invalid_values_fall_back():
    resolution = resolve(
        REGISTRY, "user-1",
        global_overrides={"retrieval.vector.top_k": 40, "rerank.top_n": 6},
        tenant_overrides={"retrieval.vector.top_k": 50, "rerank.top_n": 999, "citation.required": False,
                          "not.a.param": 1},
    )
    assert resolution["retrieval.vector.top_k"] == 50
    assert resolution["rerank.top_n"] == 6          # invalid tenant value ignored
    assert resolution["citation.required"] is True  # locked
    assert set(resolution.rejected) == {"rerank.top_n", "citation.required", "not.a.param"}


def test_enrollment_is_deterministic_and_respects_traffic_fraction():
    experiment = Experiment("exp-1", "retrieval.vector.top_k",
                            [Arm("control", 30), Arm("candidate_1", 40)], traffic_fraction=0.2)
    users = [f"user-{i}" for i in range(5000)]
    enrolled = [u for u in users if is_enrolled(experiment, u)]
    assert 0.17 < len(enrolled) / len(users) < 0.23
    assert enrolled == [u for u in users if is_enrolled(experiment, u)]


def test_resolution_records_experiment_assignment():
    experiment = Experiment("exp-2", "rerank.top_n", [Arm("control", 8), Arm("candidate_1", 10)],
                            traffic_fraction=0.5, allocation="fixed_split")
    unit = next(u for u in (f"u{i}" for i in range(1000)) if is_enrolled(experiment, u))
    resolution = resolve(REGISTRY, unit, experiments=[experiment])
    arm_id = resolution.assignments["exp-2"]
    assert resolution["rerank.top_n"] == experiment.arm(arm_id).value


def test_experiment_on_locked_parameter_is_ignored():
    experiment = Experiment("exp-3", "citation.required", [Arm("control", True), Arm("candidate_1", False)],
                            traffic_fraction=0.5, allocation="fixed_split")
    for unit in (f"u{i}" for i in range(200)):
        assert resolve(REGISTRY, unit, experiments=[experiment])["citation.required"] is True


def test_propose_arms_stay_within_bounds():
    arms = propose_arms(REGISTRY.get("retrieval.graph.max_depth"), 3)
    assert [a.value for a in arms] == [3, 2, 1]
    arms = propose_arms(REGISTRY.get("retrieval.fusion.method"), "rrf")
    assert [a.value for a in arms] == ["rrf", "weighted"]


# --- Rewards ------------------------------------------------------------------------

def test_integrity_failures_score_zero_regardless_of_user_rating():
    assert compute_reward(Signals(rating=5, acl_leak=True)) == 0.0
    assert compute_reward(Signals(thumbs=1, citation_validation_passed=False)) == 0.0


def test_reward_combines_explicit_and_implicit():
    assert compute_reward(Signals(rating=5)) == 1.0
    assert compute_reward(Signals(thumbs=-1)) == 0.0
    assert compute_reward(Signals(rating=5, reason_codes=["wrong_answer"])) == 0.5
    assert compute_reward(Signals()) is None
    assert 0 < compute_reward(Signals(insufficient_context=True)) < 0.5
    slow = compute_reward(Signals(rating=5, latency_ms=20000))
    assert slow == pytest.approx(0.8)


# --- Guardrails -------------------------------------------------------------------------

def _run(true_rates, n_per_arm, rng, leak_arm=None):
    experiment = Experiment("exp", "rerank.top_n",
                            [Arm(arm_id, value) for arm_id, value in zip(true_rates, range(len(true_rates)))])
    for arm_id, rate in true_rates.items():
        for _ in range(n_per_arm):
            experiment.stats[arm_id].update(1.0 if rng.random() < rate else 0.0, latency_ms=1000)
    if leak_arm:
        experiment.stats[leak_arm].update(0.0, acl_leak=True)
    return experiment


def test_clearly_better_candidate_is_promoted():
    experiment = _run({"control": 0.55, "candidate_1": 0.70}, 800, random.Random(1))
    decision = decide(experiment, Safety.AUTO)
    assert decision.action is Action.PROMOTE
    assert decision.arm_id == "candidate_1"


def test_review_parameters_wait_for_a_human():
    experiment = _run({"control": 0.55, "candidate_1": 0.70}, 800, random.Random(1))
    assert decide(experiment, Safety.REVIEW).action is Action.AWAIT_REVIEW


def test_any_leak_rolls_back_everything():
    experiment = _run({"control": 0.55, "candidate_1": 0.90}, 800, random.Random(1), leak_arm="candidate_1")
    decision = decide(experiment, Safety.AUTO)
    assert decision.action is Action.ROLLBACK
    assert "acl_leak" in decision.reasons[0]


def test_worse_candidate_rolled_back_and_early_data_continues():
    worse = _run({"control": 0.70, "candidate_1": 0.50}, 800, random.Random(2))
    assert decide(worse, Safety.AUTO).action is Action.ROLLBACK
    early = _run({"control": 0.55, "candidate_1": 0.70}, 50, random.Random(3))
    assert decide(early, Safety.AUTO).action is Action.CONTINUE


def test_latency_regression_blocks_promotion():
    experiment = _run({"control": 0.55, "candidate_1": 0.70}, 800, random.Random(1))
    experiment.stats["candidate_1"].latencies_ms = [3000.0] * 800
    decision = decide(experiment, Safety.AUTO)
    assert decision.action is Action.ROLLBACK
    assert "latency" in decision.reasons[0]


def test_thompson_sampling_shifts_traffic_to_better_arm():
    rng = random.Random(11)
    experiment = Experiment("exp", "rerank.top_n", [Arm("control", 8), Arm("candidate_1", 10)])
    true_rates = {"control": 0.5, "candidate_1": 0.7}
    pulls = {"control": 0, "candidate_1": 0}
    for i in range(3000):
        arm = choose_arm(experiment, f"u{i}", rng)
        pulls[arm.arm_id] += 1
        experiment.stats[arm.arm_id].update(1.0 if rng.random() < true_rates[arm.arm_id] else 0.0)
    assert pulls["candidate_1"] > 2 * pulls["control"]


# --- Offline evaluation ----------------------------------------------------------------

def test_evaluation_fails_on_any_leak():
    cases = [EvalCase("c1", expected_chunk_ids={"a"}, must_not_retrieve_chunk_ids={"payroll"})]
    report = evaluate(cases, [EvalResult("c1", ["a", "payroll"], cited_chunk_ids=["a"])])
    assert not report.passed
    assert report.metrics["leak_count"] == 1


def test_evaluation_metrics_and_baseline_comparison():
    cases = [EvalCase("c1", expected_chunk_ids={"a"}), EvalCase("c2", expected_chunk_ids={"b"}),
             EvalCase("c3", expect_insufficient_context=True)]
    baseline = evaluate(cases, [EvalResult("c1", ["a"], ["a"]), EvalResult("c2", ["x", "b"], ["b"]),
                                EvalResult("c3", [], insufficient_context=True)])
    assert baseline.passed
    assert baseline.metrics["mrr"] == pytest.approx(0.75)
    assert baseline.metrics["abstention_accuracy"] == 1.0

    worse = evaluate(cases, [EvalResult("c1", ["x", "y", "a"], ["a"]), EvalResult("c2", ["x"], []),
                             EvalResult("c3", ["x"], ["x"], insufficient_context=False)])
    comparison = compare_to_baseline(baseline, worse)
    assert not comparison.passed
    assert any("recall" in f for f in comparison.failures)
    assert any("abstention" in f for f in comparison.failures)


def test_citation_outside_context_is_invalid():
    report = evaluate([EvalCase("c1", expected_chunk_ids={"a"})], [EvalResult("c1", ["a"], cited_chunk_ids=["z"])])
    assert report.metrics["invalid_citation_count"] == 1
    assert not report.passed
