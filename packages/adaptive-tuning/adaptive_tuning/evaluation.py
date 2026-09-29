"""
Offline evaluation on the golden set (evaluation_cases table).

Each case is run through the real pipeline *as the case's user*, so ACL
behaviour is part of every evaluation. A run fails outright on any leak or
invalid citation; otherwise it is compared to the baseline run of the
current parameters and fails on regressions beyond tolerance.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set


@dataclass
class EvalCase:
    case_id: str
    expected_chunk_ids: Set[str] = field(default_factory=set)
    must_not_retrieve_chunk_ids: Set[str] = field(default_factory=set)
    expect_insufficient_context: bool = False


@dataclass
class EvalResult:
    case_id: str
    context_chunk_ids: List[str]          # ranked, as given to the LLM
    cited_chunk_ids: List[str] = field(default_factory=list)
    insufficient_context: bool = False
    citation_valid: bool = True
    latency_ms: Optional[float] = None


@dataclass
class EvalReport:
    metrics: Dict[str, float]
    passed: bool
    failures: List[str]


@dataclass
class Tolerances:
    recall_drop: float = 0.02
    mrr_drop: float = 0.02
    abstention_drop: float = 0.0
    p95_latency_increase: float = 0.15


def _recall_at_k(ranked: Sequence[str], expected: Set[str], k: int) -> float:
    return len(set(ranked[:k]) & expected) / len(expected)


def _reciprocal_rank(ranked: Sequence[str], expected: Set[str]) -> float:
    for index, chunk_id in enumerate(ranked, start=1):
        if chunk_id in expected:
            return 1.0 / index
    return 0.0


def _ndcg_at_k(ranked: Sequence[str], expected: Set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 2) for i, c in enumerate(ranked[:k]) if c in expected)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(expected), k)))
    return dcg / ideal if ideal else 0.0


def evaluate(cases: Sequence[EvalCase], results: Sequence[EvalResult], k: int = 10) -> EvalReport:
    by_case = {r.case_id: r for r in results}
    failures: List[str] = []
    recall, rr, ndcg, latencies = [], [], [], []
    leaks = invalid_citations = abstain_total = abstain_correct = 0

    for case in cases:
        result = by_case.get(case.case_id)
        if result is None:
            failures.append(f"missing result for case {case.case_id}")
            continue
        leaked = set(result.context_chunk_ids) & case.must_not_retrieve_chunk_ids
        if leaked:
            leaks += len(leaked)
            failures.append(f"case {case.case_id}: unauthorized chunks in context {sorted(leaked)}")
        if not result.citation_valid or not set(result.cited_chunk_ids) <= set(result.context_chunk_ids):
            invalid_citations += 1
            failures.append(f"case {case.case_id}: invalid citation")
        if case.expect_insufficient_context:
            abstain_total += 1
            abstain_correct += int(result.insufficient_context)
        elif case.expected_chunk_ids:
            recall.append(_recall_at_k(result.context_chunk_ids, case.expected_chunk_ids, k))
            rr.append(_reciprocal_rank(result.context_chunk_ids, case.expected_chunk_ids))
            ndcg.append(_ndcg_at_k(result.context_chunk_ids, case.expected_chunk_ids, k))
        if result.latency_ms is not None:
            latencies.append(result.latency_ms)

    def avg(values):
        return sum(values) / len(values) if values else 0.0

    latencies.sort()
    metrics = {
        f"recall_at_{k}": avg(recall),
        "mrr": avg(rr),
        f"ndcg_at_{k}": avg(ndcg),
        "leak_count": float(leaks),
        "invalid_citation_count": float(invalid_citations),
        "abstention_accuracy": abstain_correct / abstain_total if abstain_total else 1.0,
        "p95_latency_ms": latencies[min(len(latencies) - 1, int(round(0.95 * (len(latencies) - 1))))]
        if latencies else 0.0,
    }
    return EvalReport(metrics=metrics, passed=not failures, failures=failures)


def compare_to_baseline(baseline: EvalReport, candidate: EvalReport, k: int = 10,
                        tolerances: Tolerances = Tolerances()) -> EvalReport:
    """Candidate must pass on its own and not regress beyond tolerance."""
    failures = list(candidate.failures)
    b, c = baseline.metrics, candidate.metrics
    if c[f"recall_at_{k}"] < b[f"recall_at_{k}"] - tolerances.recall_drop:
        failures.append(f"recall@{k} {c[f'recall_at_{k}']:.3f} < baseline {b[f'recall_at_{k}']:.3f}")
    if c["mrr"] < b["mrr"] - tolerances.mrr_drop:
        failures.append(f"mrr {c['mrr']:.3f} < baseline {b['mrr']:.3f}")
    if c["abstention_accuracy"] < b["abstention_accuracy"] - tolerances.abstention_drop:
        failures.append("abstention accuracy regressed")
    if b["p95_latency_ms"] and c["p95_latency_ms"] > b["p95_latency_ms"] * (1 + tolerances.p95_latency_increase):
        failures.append(f"p95 latency {c['p95_latency_ms']:.0f}ms vs {b['p95_latency_ms']:.0f}ms")
    return EvalReport(metrics=c, passed=not failures, failures=failures)
