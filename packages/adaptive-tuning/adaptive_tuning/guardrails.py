"""
Promotion / rollback decisions for a running experiment.

Order of checks (first match wins):
  1. Any ACL leak in any arm                 -> ROLLBACK everything, alert
  2. Candidate citation-failure rate worse   -> ROLLBACK candidate
  3. Candidate p95 latency regression        -> ROLLBACK candidate
  4. Not enough samples yet                  -> CONTINUE
  5. P(candidate > control) >= threshold and lift >= min_lift
                                             -> PROMOTE (or AWAIT_REVIEW for REVIEW params)
  6. P(candidate > control) <= 1 - threshold -> ROLLBACK candidate (it is worse)
  7. Max samples reached                     -> STOP, keep control
  8. otherwise                               -> CONTINUE

Offline evaluation on the golden set (evaluation.py) must also pass before a
promotion is applied; the caller combines both.
"""

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from adaptive_tuning.experiments import ArmStats, Experiment
from adaptive_tuning.registry import Safety


class Action(str, Enum):
    CONTINUE = "continue"
    PROMOTE = "promote"
    AWAIT_REVIEW = "await_review"
    ROLLBACK = "rollback"
    STOP = "stop"


@dataclass
class GuardrailPolicy:
    min_samples_per_arm: int = 200
    max_samples_per_arm: int = 5000
    prob_better_threshold: float = 0.95
    min_lift: float = 0.01
    max_citation_failure_increase: float = 0.0
    max_p95_latency_regression: float = 0.15
    monte_carlo_draws: int = 20000
    seed: int = 7


@dataclass
class Decision:
    action: Action
    arm_id: Optional[str] = None
    prob_better: Optional[float] = None
    lift: Optional[float] = None
    reasons: List[str] = field(default_factory=list)


def _p95(values: List[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]


def prob_better(candidate: ArmStats, control: ArmStats, draws: int, rng: random.Random) -> float:
    wins = sum(
        rng.betavariate(candidate.alpha, candidate.beta) > rng.betavariate(control.alpha, control.beta)
        for _ in range(draws)
    )
    return wins / draws


def decide(experiment: Experiment, safety: Safety, policy: GuardrailPolicy = GuardrailPolicy()) -> Decision:
    control = experiment.stats[experiment.control_arm_id]
    candidates = [a.arm_id for a in experiment.arms if a.arm_id != experiment.control_arm_id]

    leaking = [arm_id for arm_id, stats in experiment.stats.items() if stats.leak_count > 0]
    if leaking:
        return Decision(Action.ROLLBACK, reasons=[f"acl_leak in arms {sorted(leaking)}; security incident"])

    rng = random.Random(policy.seed)
    best: Optional[Decision] = None
    all_worse = True
    for arm_id in candidates:
        stats = experiment.stats[arm_id]
        if stats.n and control.n:
            increase = stats.citation_failures / stats.n - control.citation_failures / control.n
            if increase > policy.max_citation_failure_increase:
                return Decision(Action.ROLLBACK, arm_id, reasons=[f"citation failure rate +{increase:.3f}"])
        cand_p95, ctrl_p95 = _p95(stats.latencies_ms), _p95(control.latencies_ms)
        if cand_p95 and ctrl_p95 and cand_p95 > ctrl_p95 * (1 + policy.max_p95_latency_regression):
            return Decision(Action.ROLLBACK, arm_id, reasons=[f"p95 latency {cand_p95:.0f}ms vs {ctrl_p95:.0f}ms"])

        if stats.n < policy.min_samples_per_arm or control.n < policy.min_samples_per_arm:
            all_worse = False
            continue

        p = prob_better(stats, control, policy.monte_carlo_draws, rng)
        lift = stats.mean - control.mean
        if p >= policy.prob_better_threshold and lift >= policy.min_lift:
            action = Action.PROMOTE if safety is Safety.AUTO else Action.AWAIT_REVIEW
            if best is None or lift > (best.lift or 0):
                best = Decision(action, arm_id, p, lift, [f"P(better)={p:.3f}, lift={lift:+.3f}"])
        if p > 1 - policy.prob_better_threshold:
            all_worse = False

    if best:
        return best
    enough = all(experiment.stats[a].n >= policy.min_samples_per_arm for a in candidates)
    if candidates and enough and all_worse:
        return Decision(Action.ROLLBACK, reasons=["all candidates worse than control"])
    if all(experiment.stats[a].n >= policy.max_samples_per_arm for a in candidates + [experiment.control_arm_id]):
        return Decision(Action.STOP, experiment.control_arm_id, reasons=["no significant difference; keep control"])
    return Decision(Action.CONTINUE, reasons=["collecting samples"])
