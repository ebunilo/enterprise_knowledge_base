"""
Self-improvement primitives for the Enterprise RAG System (see SELF_IMPROVEMENT.md).

Dependency-free so any service in the query path can import it.
"""

from adaptive_tuning.evaluation import EvalCase, EvalReport, EvalResult, compare_to_baseline, evaluate
from adaptive_tuning.experiments import Arm, ArmStats, Experiment, choose_arm, is_enrolled, propose_arms
from adaptive_tuning.guardrails import Action, Decision, GuardrailPolicy, decide
from adaptive_tuning.registry import (
    DEFAULT_PARAMETERS,
    InvalidParameterValue,
    LockedParameterError,
    ParameterRegistry,
    ParameterSpec,
    Safety,
)
from adaptive_tuning.resolver import Resolution, resolve
from adaptive_tuning.rewards import RewardWeights, Signals, compute_reward

__all__ = [
    "Action", "Arm", "ArmStats", "DEFAULT_PARAMETERS", "Decision", "EvalCase", "EvalReport", "EvalResult",
    "Experiment", "GuardrailPolicy", "InvalidParameterValue", "LockedParameterError", "ParameterRegistry",
    "ParameterSpec", "Resolution", "RewardWeights", "Safety", "Signals", "choose_arm", "compare_to_baseline",
    "compute_reward", "decide", "evaluate", "is_enrolled", "propose_arms", "resolve",
]
