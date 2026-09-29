"""
The catalogue of parameters the RAG system may tune about itself.

Every parameter has a safety class:

  AUTO    may be changed automatically when an experiment wins and passes
          every guardrail (retrieval depth, fusion weights, rerank weights,
          context budget...)
  REVIEW  may be experimented on, but promotion needs a human approval
          (model tier, chunking - which needs a re-index -, prompt template)
  LOCKED  never tunable. Security and compliance behaviour lives here so the
          optimiser cannot trade it for quality or cost (AGENTS.md 14).

Defaults follow AGENTS.md (5.5 chunking, 5.10 retrieval strategy, 14.6 caching).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple


class Safety(str, Enum):
    AUTO = "AUTO"
    REVIEW = "REVIEW"
    LOCKED = "LOCKED"


class Kind(str, Enum):
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    CHOICE = "choice"


class InvalidParameterValue(ValueError):
    pass


class LockedParameterError(PermissionError):
    pass


class UnknownParameterError(KeyError):
    pass


@dataclass(frozen=True)
class ParameterSpec:
    key: str
    kind: Kind
    default: Any
    stage: str
    description: str
    safety: Safety = Safety.AUTO
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    step: Optional[float] = None
    choices: Tuple[Any, ...] = field(default_factory=tuple)

    def validate(self, value: Any) -> Any:
        """Return the value coerced to the parameter's type, or raise."""
        if self.safety is Safety.LOCKED and value != self.default:
            raise LockedParameterError(f"{self.key} is locked and cannot be changed")
        if self.kind is Kind.BOOL:
            if not isinstance(value, bool):
                raise InvalidParameterValue(f"{self.key} must be a boolean")
            return value
        if self.kind is Kind.CHOICE:
            if value not in self.choices:
                raise InvalidParameterValue(f"{self.key} must be one of {list(self.choices)}")
            return value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidParameterValue(f"{self.key} must be numeric")
        if self.kind is Kind.INT:
            if int(value) != value:
                raise InvalidParameterValue(f"{self.key} must be an integer")
            value = int(value)
        else:
            value = float(value)
        if self.minimum is not None and value < self.minimum:
            raise InvalidParameterValue(f"{self.key} must be >= {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise InvalidParameterValue(f"{self.key} must be <= {self.maximum}")
        return value


def _int(key, default, lo, hi, step, stage, description, safety=Safety.AUTO):
    return ParameterSpec(key, Kind.INT, default, stage, description, safety, lo, hi, step)


def _float(key, default, lo, hi, step, stage, description, safety=Safety.AUTO):
    return ParameterSpec(key, Kind.FLOAT, default, stage, description, safety, lo, hi, step)


def _bool(key, default, stage, description, safety=Safety.AUTO):
    return ParameterSpec(key, Kind.BOOL, default, stage, description, safety)


def _choice(key, default, choices, stage, description, safety=Safety.AUTO):
    return ParameterSpec(key, Kind.CHOICE, default, stage, description, safety, choices=tuple(choices))


DEFAULT_PARAMETERS: Sequence[ParameterSpec] = (
    # --- Query understanding (5.9) ---------------------------------------------
    _float("query.intent.min_confidence", 0.6, 0.3, 0.95, 0.05, "query_understanding",
           "Below this intent confidence the query falls back to the generic retrieval plan."),
    _float("query.graph.trigger_threshold", 0.5, 0.1, 0.9, 0.1, "query_understanding",
           "Entity/relationship score above which knowledge-graph retrieval is run."),
    _bool("query.expansion.enabled", True, "query_understanding",
          "Add synonyms/acronym expansions to the BM25 query."),
    _bool("query.translation_expansion.enabled", True, "query_understanding",
          "Translate the query into the tenant's priority languages for retrieval (14.7)."),

    # --- Hybrid retrieval (5.10) ------------------------------------------------
    _int("retrieval.vector.top_k", 30, 10, 100, 10, "retrieval", "Qdrant candidates per query."),
    _int("retrieval.bm25.top_k", 30, 10, 100, 10, "retrieval", "BM25/OpenSearch candidates per query."),
    _int("retrieval.graph.top_k", 20, 0, 50, 5, "retrieval", "Knowledge-graph linked chunks per query."),
    _int("retrieval.graph.max_depth", 2, 1, 3, 1, "retrieval", "Maximum graph traversal depth."),
    _choice("retrieval.fusion.method", "rrf", ("rrf", "weighted"), "retrieval",
            "How ranked lists from the three retrievers are merged."),
    _int("retrieval.fusion.rrf_k", 60, 10, 200, 10, "retrieval", "Reciprocal-rank-fusion constant."),
    _float("retrieval.fusion.weight.vector", 1.0, 0.0, 3.0, 0.25, "retrieval", "Fusion weight of vector results."),
    _float("retrieval.fusion.weight.bm25", 1.0, 0.0, 3.0, 0.25, "retrieval", "Fusion weight of BM25 results."),
    _float("retrieval.fusion.weight.graph", 0.7, 0.0, 3.0, 0.25, "retrieval", "Fusion weight of graph results."),

    # --- Reranking (5.12) -------------------------------------------------------
    _int("rerank.top_n", 8, 3, 20, 1, "rerank", "Chunks kept after reranking."),
    _float("rerank.weight.semantic", 1.0, 0.0, 3.0, 0.1, "rerank", "Semantic relevance signal."),
    _float("rerank.weight.keyword", 0.5, 0.0, 3.0, 0.1, "rerank", "Keyword match signal."),
    _float("rerank.weight.entity", 0.4, 0.0, 3.0, 0.1, "rerank", "Entity match signal."),
    _float("rerank.weight.graph", 0.3, 0.0, 3.0, 0.1, "rerank", "Graph relationship signal."),
    _float("rerank.weight.recency", 0.2, 0.0, 2.0, 0.1, "rerank", "Document recency signal."),
    _float("rerank.weight.specificity", 0.3, 0.0, 2.0, 0.1, "rerank", "Specific-over-general policy signal."),
    _float("rerank.weight.region_match", 0.4, 0.0, 2.0, 0.1, "rerank", "Region-specific-over-global signal (9)."),
    _float("rerank.weight.department_match", 0.3, 0.0, 2.0, 0.1, "rerank", "Department match signal."),
    _choice("rerank.model", "feature", ("feature", "cohere-rerank-v3"), "rerank",
            "Reranker implementation; external model needs provider approval (14.5).", Safety.REVIEW),

    # --- Context building (5.13) --------------------------------------------------
    _int("context.token_budget", 6000, 2000, 16000, 1000, "context", "Tokens of evidence given to the LLM."),
    _int("context.max_chunks", 10, 3, 25, 1, "context", "Maximum chunks in the context."),
    _int("context.neighbor_expansion", 0, 0, 2, 1, "context", "Adjacent chunks added around each hit."),
    _float("context.dedup_similarity", 0.92, 0.8, 0.99, 0.01, "context", "Near-duplicate removal threshold."),

    # --- Generation (5.14) ----------------------------------------------------------
    _choice("llm.tier", "standard", ("standard", "high_quality"), "generation",
            "Default model tier for non-sensitive queries; routing for confidential data is fixed by "
            "compliance rules, not by this parameter.", Safety.REVIEW),
    _float("llm.temperature", 0.1, 0.0, 0.5, 0.05, "generation", "Sampling temperature."),
    _int("llm.max_output_tokens", 800, 200, 2000, 100, "generation", "Answer length cap."),
    _choice("llm.prompt_template_version", "v1", ("v1",), "generation",
            "System prompt template; new versions are added here after review.", Safety.REVIEW),

    # --- Ingestion (5.5) - offline, needs re-index --------------------------------
    _int("chunking.target_tokens", 512, 256, 1024, 64, "ingestion", "Target chunk size.", Safety.REVIEW),
    _int("chunking.max_tokens", 768, 384, 1536, 64, "ingestion", "Hard chunk size limit.", Safety.REVIEW),
    _int("chunking.overlap_tokens", 64, 0, 128, 16, "ingestion", "Overlap within a section.", Safety.REVIEW),

    # --- Caching (14.6) --------------------------------------------------------------
    _int("cache.retrieval.ttl_seconds", 300, 0, 3600, 60, "cache", "Retrieval-result cache TTL (chunk IDs only)."),

    # --- LOCKED: security and compliance (AGENTS.md 14) -----------------------------
    _bool("acl.postgres_validation", True, "security",
          "Revalidate every candidate against PostgreSQL ACLs.", Safety.LOCKED),
    _bool("acl.enforce_clearance", True, "security", "Clearance >= classification for CONFIDENTIAL+.", Safety.LOCKED),
    _bool("retrieval.include_archived", False, "security",
          "Archived versions in normal retrieval.", Safety.LOCKED),
    _bool("citation.required", True, "security", "Every policy answer must be cited.", Safety.LOCKED),
    _float("citation.min_valid_ratio", 1.0, 1.0, 1.0, None, "security",
           "Share of citations that must resolve to authorized context chunks.", Safety.LOCKED),
    _bool("llm.treat_documents_as_untrusted", True, "security",
          "Ignore instructions inside retrieved documents.", Safety.LOCKED),
    _bool("cache.llm_response.sensitive_enabled", False, "security",
          "Cache answers built from confidential/regulated content.", Safety.LOCKED),
)


class ParameterRegistry:
    def __init__(self, specs: Iterable[ParameterSpec] = DEFAULT_PARAMETERS):
        self._specs: Dict[str, ParameterSpec] = {}
        for spec in specs:
            if spec.key in self._specs:
                raise ValueError(f"Duplicate parameter {spec.key}")
            spec.validate(spec.default)
            self._specs[spec.key] = spec

    def __contains__(self, key: str) -> bool:
        return key in self._specs

    def __iter__(self):
        return iter(self._specs.values())

    def get(self, key: str) -> ParameterSpec:
        try:
            return self._specs[key]
        except KeyError:
            raise UnknownParameterError(key) from None

    def defaults(self) -> Dict[str, Any]:
        return {key: spec.default for key, spec in self._specs.items()}

    def tunable(self, safety: Optional[Safety] = None) -> list[ParameterSpec]:
        specs = [s for s in self._specs.values() if s.safety is not Safety.LOCKED]
        return [s for s in specs if safety is None or s.safety is safety]

    def validate_change(self, key: str, value: Any) -> Any:
        """Validate a proposed new value (manual change or experiment arm)."""
        return self.get(key).validate(value)
