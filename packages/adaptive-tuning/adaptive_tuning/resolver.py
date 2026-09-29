"""
Resolve the effective parameter values for one request.

Precedence: registry default < global override < tenant override < experiment
arm (for enrolled units). Invalid stored values fall back to the next level
instead of breaking the request, and LOCKED parameters always resolve to
their default. The returned snapshot and assignments are what the
orchestrator writes to retrieval_audit_logs so outcomes can be attributed.
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional

from adaptive_tuning.experiments import Experiment, choose_arm, is_enrolled
from adaptive_tuning.registry import InvalidParameterValue, LockedParameterError, ParameterRegistry, Safety

logger = logging.getLogger(__name__)


@dataclass
class Resolution:
    values: Dict[str, Any]
    assignments: Dict[str, str] = field(default_factory=dict)  # experiment_id -> arm_id
    rejected: Dict[str, str] = field(default_factory=dict)     # key -> reason

    def __getitem__(self, key: str) -> Any:
        return self.values[key]


def resolve(
    registry: ParameterRegistry,
    unit_key: str,
    global_overrides: Optional[Mapping[str, Any]] = None,
    tenant_overrides: Optional[Mapping[str, Any]] = None,
    experiments: Iterable[Experiment] = (),
    rng: Optional[random.Random] = None,
) -> Resolution:
    resolution = Resolution(values=registry.defaults())

    for layer in (global_overrides or {}, tenant_overrides or {}):
        for key, value in layer.items():
            if key not in registry:
                resolution.rejected[key] = "unknown_parameter"
                continue
            try:
                resolution.values[key] = registry.validate_change(key, value)
            except (InvalidParameterValue, LockedParameterError) as e:
                resolution.rejected[key] = str(e)
                logger.warning("Ignoring stored value for %s: %s", key, e)

    for experiment in experiments:
        if not experiment.running or experiment.param_key not in registry:
            continue
        spec = registry.get(experiment.param_key)
        if spec.safety is Safety.LOCKED or not is_enrolled(experiment, unit_key):
            continue
        arm = choose_arm(experiment, unit_key, rng)
        try:
            resolution.values[spec.key] = spec.validate(arm.value)
            resolution.assignments[experiment.experiment_id] = arm.arm_id
        except (InvalidParameterValue, LockedParameterError) as e:
            resolution.rejected[spec.key] = f"experiment {experiment.experiment_id}: {e}"

    return resolution
