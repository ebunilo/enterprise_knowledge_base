"""
Turn the signals observed for one answer into a reward in [0, 1].

Signals come from retrieval_audit_logs (system outcome) and user_feedback
(explicit rating/thumbs/reason codes), plus optional implicit UI events.
Integrity failures are not traded off against quality: an answer built on a
leaked chunk or with an invalid citation scores 0 whatever the user thought.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Signals:
    # Explicit feedback
    rating: Optional[int] = None          # 1..5
    thumbs: Optional[int] = None          # -1 / 1
    reason_codes: List[str] = field(default_factory=list)
    # System outcome
    citation_validation_passed: Optional[bool] = None
    insufficient_context: Optional[bool] = None
    acl_leak: bool = False
    latency_ms: Optional[float] = None
    cost_usd: Optional[float] = None
    # Implicit feedback
    citation_clicked: Optional[bool] = None
    reformulated_quickly: Optional[bool] = None   # user re-asked within ~60s


@dataclass
class RewardWeights:
    explicit: float = 0.7
    implicit: float = 0.3
    latency_budget_ms: float = 8000
    cost_budget_usd: float = 0.05
    over_budget_penalty: float = 0.2
    insufficient_context_reward: float = 0.3  # honest "I don't know" beats a wrong answer


NEGATIVE_REASONS = {"wrong_answer", "bad_citation", "outdated_source", "not_relevant"}


def compute_reward(signals: Signals, weights: RewardWeights = RewardWeights()) -> Optional[float]:
    """Reward in [0, 1], or None when there is no quality signal at all."""
    if signals.acl_leak or signals.citation_validation_passed is False:
        return 0.0

    explicit = []
    if signals.rating is not None:
        explicit.append((signals.rating - 1) / 4)
    if signals.thumbs is not None:
        explicit.append(1.0 if signals.thumbs > 0 else 0.0)
    if set(signals.reason_codes) & NEGATIVE_REASONS:
        explicit.append(0.0)

    implicit = []
    if signals.citation_clicked is not None:
        implicit.append(1.0 if signals.citation_clicked else 0.5)
    if signals.reformulated_quickly is not None:
        implicit.append(0.0 if signals.reformulated_quickly else 0.7)

    if explicit and implicit:
        quality = weights.explicit * _mean(explicit) + weights.implicit * _mean(implicit)
    elif explicit:
        quality = _mean(explicit)
    elif implicit:
        quality = _mean(implicit)
    elif signals.insufficient_context:
        quality = weights.insufficient_context_reward
    else:
        return None

    if signals.latency_ms is not None and signals.latency_ms > weights.latency_budget_ms:
        quality *= 1 - weights.over_budget_penalty
    if signals.cost_usd is not None and signals.cost_usd > weights.cost_budget_usd:
        quality *= 1 - weights.over_budget_penalty
    return max(0.0, min(1.0, quality))


def _mean(values: List[float]) -> float:
    return sum(values) / len(values)
