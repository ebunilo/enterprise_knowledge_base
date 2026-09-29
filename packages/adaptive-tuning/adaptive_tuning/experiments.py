"""
Online experiments over a single parameter.

Enrollment is deterministic per (experiment, unit) so a user sees consistent
behaviour; only `traffic_fraction` of units are enrolled, the rest get the
current value. Enrolled units are allocated to arms either by a fixed hash
split or by Thompson sampling over Beta posteriors of the reward, which
shifts traffic toward better arms while the experiment runs.
"""

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from adaptive_tuning.registry import Kind, ParameterSpec, Safety


@dataclass
class ArmStats:
    """Beta posterior over a reward in [0, 1] (fractional rewards allowed)."""
    alpha: float = 1.0
    beta: float = 1.0
    n: int = 0
    leak_count: int = 0
    citation_failures: int = 0
    latencies_ms: List[float] = field(default_factory=list)

    def update(self, reward: float, latency_ms: Optional[float] = None,
               acl_leak: bool = False, citation_failed: bool = False) -> None:
        if not 0.0 <= reward <= 1.0:
            raise ValueError("reward must be in [0, 1]")
        self.alpha += reward
        self.beta += 1.0 - reward
        self.n += 1
        self.leak_count += int(acl_leak)
        self.citation_failures += int(citation_failed)
        if latency_ms is not None:
            self.latencies_ms.append(latency_ms)

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def to_dict(self) -> Dict[str, Any]:
        return {"alpha": self.alpha, "beta": self.beta, "n": self.n,
                "leak_count": self.leak_count, "citation_failures": self.citation_failures}


@dataclass
class Arm:
    arm_id: str
    value: Any


@dataclass
class Experiment:
    experiment_id: str
    param_key: str
    arms: List[Arm]
    control_arm_id: str = "control"
    traffic_fraction: float = 0.1
    allocation: str = "thompson"  # or "fixed_split"
    stats: Dict[str, ArmStats] = field(default_factory=dict)
    running: bool = True

    def __post_init__(self):
        if not 0.0 < self.traffic_fraction <= 0.5:
            raise ValueError("traffic_fraction must be in (0, 0.5]")
        arm_ids = [arm.arm_id for arm in self.arms]
        if self.control_arm_id not in arm_ids or len(set(arm_ids)) != len(arm_ids):
            raise ValueError("arms must be unique and include the control arm")
        for arm_id in arm_ids:
            self.stats.setdefault(arm_id, ArmStats())

    def arm(self, arm_id: str) -> Arm:
        return next(arm for arm in self.arms if arm.arm_id == arm_id)


def _unit_hash(*parts: str) -> float:
    digest = hashlib.sha256(":".join(parts).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def is_enrolled(experiment: Experiment, unit_key: str) -> bool:
    return experiment.running and _unit_hash(experiment.experiment_id, unit_key) < experiment.traffic_fraction


def choose_arm(experiment: Experiment, unit_key: str, rng: Optional[random.Random] = None) -> Arm:
    """Pick the arm for an enrolled unit."""
    if experiment.allocation == "fixed_split":
        index = int(_unit_hash(experiment.experiment_id, "arm", unit_key) * len(experiment.arms))
        return experiment.arms[index]
    rng = rng or random.Random()
    samples = {arm.arm_id: rng.betavariate(experiment.stats[arm.arm_id].alpha, experiment.stats[arm.arm_id].beta)
               for arm in experiment.arms}
    return experiment.arm(max(samples, key=samples.get))


def propose_arms(spec: ParameterSpec, current: Any, max_candidates: int = 2) -> List[Arm]:
    """Control plus neighbouring values within the parameter's bounds."""
    if spec.safety is Safety.LOCKED:
        raise PermissionError(f"{spec.key} is locked")
    candidates: List[Any] = []
    if spec.kind is Kind.BOOL:
        candidates = [not current]
    elif spec.kind is Kind.CHOICE:
        candidates = [choice for choice in spec.choices if choice != current]
    else:
        step = spec.step or (abs(current) * 0.1 or 1)
        for value in (current + step, current - step, current + 2 * step, current - 2 * step):
            if spec.minimum is not None and value < spec.minimum:
                continue
            if spec.maximum is not None and value > spec.maximum:
                continue
            value = int(value) if spec.kind is Kind.INT else round(value, 6)
            if value != current and value not in candidates:
                candidates.append(value)
    arms = [Arm("control", current)]
    arms += [Arm(f"candidate_{i + 1}", value) for i, value in enumerate(candidates[:max_candidates])]
    return arms
