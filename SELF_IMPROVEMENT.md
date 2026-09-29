# Self-Improvement Design

**Status:** foundation implemented (storage, library, capture APIs); loop activates once the query pipeline (Milestones 6–7) exists.
**Code:** `packages/adaptive-tuning/`, migrations `0002`/`0003`, canonical-db `/api/v1/retrieval-audit` and `/api/v1/feedback`.

## 1. What "self-improving" means here

The system gets better at answering by **measuring every answer, running controlled experiments on its own retrieval and generation parameters, and promoting only changes that win without breaking any guardrail.** It is a closed, auditable loop:

```text
 Observe ──► Attribute ──► Evaluate ──► Propose ──► Experiment ──► Guard ──► Promote / Roll back
    ▲                                                                              │
    └────────── golden set grows from feedback; change log records every step ◄────┘
```

What it deliberately does **not** do: rewrite its own code, let an LLM change access rules, or trade security for quality. Everything in AGENTS.md §14 is `LOCKED` in the parameter registry and cannot be the subject of an experiment.

## 2. Signals: what the system learns from

| Signal | Source | Stored in | Used for |
|---|---|---|---|
| Rating 1–5, thumbs ±1 | UI | `user_feedback.rating/thumbs` | Primary reward |
| Reason codes (`wrong_answer`, `outdated_source`, `bad_citation`, `incomplete`, `not_relevant`, `missing_source`, `too_slow`) | UI | `user_feedback.reason_codes` | Reward + diagnosis (which stage failed) |
| Helpful / unhelpful chunks | UI | `user_feedback.*_chunk_ids` (only chunks that were shown) | Reranker and chunking diagnostics |
| Citation clicked, quick re-ask, copy | UI events | orchestrator → reward job | Implicit reward (covers the ~95% of answers nobody rates) |
| Citation validation result | citation-agent | `retrieval_audit_logs.citation_validation_passed` | Hard zero reward on failure |
| Insufficient context | llm-answer-agent | `retrieval_audit_logs.insufficient_context` | Abstention quality; content-gap mining |
| Denied chunks + reasons | acl-validation | `retrieval_audit_logs.denied_*`, `audit_logs` | Pre-filter precision (how much the retrievers over-fetch) |
| Latency per stage, tokens, model | orchestrator | `retrieval_audit_logs.stage_latency_ms`, `*_tokens` | Cost/latency guardrails |
| Parameter values + experiment arm | `adaptive_tuning.resolve()` | `retrieval_audit_logs.parameter_snapshot`, `experiment_assignments` | **Attribution:** which change produced which outcome |

`adaptive_tuning.compute_reward()` folds these into one reward in `[0, 1]`. An ACL leak or an invalid citation always scores 0, whatever the user thought of the answer.

## 3. Parameters that drive self-improvement

Defined in `adaptive_tuning/registry.py` with bounds and step sizes. The full list is there; the most valuable ones:

| Stage | Parameter | Default | Range | Safety | What it trades |
|---|---|---|---|---|---|
| Retrieval | `retrieval.vector.top_k` / `bm25.top_k` / `graph.top_k` | 30 / 30 / 20 | 10–100 / 10–100 / 0–50 | AUTO | Recall vs latency and ACL load |
| Retrieval | `retrieval.fusion.method`, `rrf_k`, `weight.{vector,bm25,graph}` | rrf, 60, 1/1/0.7 | — | AUTO | Exact-ID queries (BM25) vs paraphrases (vector) vs relationships (KG) |
| Retrieval | `retrieval.graph.max_depth` | 2 | 1–3 | AUTO | Multi-hop recall vs noise |
| Query | `query.intent.min_confidence`, `query.graph.trigger_threshold` | 0.6, 0.5 | — | AUTO | When to take specialised retrieval paths |
| Query | `query.expansion.enabled`, `query.translation_expansion.enabled` | on, on | — | AUTO | Multilingual / acronym recall (§14.7) |
| Rerank | `rerank.top_n`, `rerank.weight.{semantic,keyword,entity,graph,recency,specificity,region_match,department_match}` | 8, … | — | AUTO | Ordering; implements §9 conflict priorities as learnable weights |
| Rerank | `rerank.model` | feature | feature / cohere-rerank-v3 | REVIEW | Quality vs cost; external provider needs approval |
| Context | `context.token_budget`, `max_chunks`, `neighbor_expansion`, `dedup_similarity` | 6000, 10, 0, 0.92 | — | AUTO | Completeness vs cost and dilution |
| Generation | `llm.temperature`, `llm.max_output_tokens` | 0.1, 800 | — | AUTO | Faithfulness vs fluency/length |
| Generation | `llm.tier`, `llm.prompt_template_version` | standard, v1 | — | REVIEW | Cost vs quality; prompts need human review |
| Ingestion | `chunking.target_tokens` / `max_tokens` / `overlap_tokens` | 512 / 768 / 64 | — | REVIEW | Needs re-index (blue-green, §5.6) |
| Cache | `cache.retrieval.ttl_seconds` | 300 | 0–3600 | AUTO | Latency vs freshness |

**LOCKED (never tuned):** `acl.postgres_validation`, `acl.enforce_clearance`, `retrieval.include_archived`, `citation.required`, `citation.min_valid_ratio` (= 1.0), `llm.treat_documents_as_untrusted`, `cache.llm_response.sensitive_enabled`. Stored overrides and experiments on these are rejected at resolution time.

Scope: every parameter can be set globally or per tenant (`tuning_parameters.tenant_id`), so a tenant with mostly German documents can converge on different fusion weights than an English-only tenant.

## 4. The loop in detail

1. **Resolve** (per request, in the orchestrator):
   `resolve(registry, unit_key=user_id, global_overrides, tenant_overrides, running_experiments)` returns the values plus `assignments`. Enrollment is a deterministic hash, so a user sees consistent behaviour. At most `traffic_fraction` (≤ 50%, default 10%) of users are enrolled.
2. **Record**: the orchestrator writes `parameter_snapshot` and `experiment_assignments` into `retrieval_audit_logs` (POST `/api/v1/retrieval-audit`). The API rejects records whose context contains unauthorized chunks or whose citations fall outside the context.
3. **Reward** (hourly job): join audit records with feedback and UI events, call `compute_reward()`, and update each arm's `ArmStats` (Beta posterior, leak count, citation failures, latencies) in `tuning_experiments.arm_stats`.
4. **Decide**: `decide(experiment, safety)` applies the guardrails in order:
   - Any leak rolls back **every** arm and raises a security incident.
   - A worse citation-failure rate, or a p95 latency regression above 15%, rolls back that candidate.
   - With fewer than 200 samples per arm, it keeps collecting.
   - It promotes when P(candidate > control) ≥ 0.95 and the lift is ≥ 1 point. `REVIEW` parameters go to `AWAIT_REVIEW` instead of being promoted.
   - Thompson sampling shifts traffic toward the better arm while the experiment runs, which limits the cost of trying worse values.
5. **Offline gate**: before applying a promotion, run the golden set (`evaluation_cases`) with the candidate value and `compare_to_baseline()`. Each case runs **as its stored user claims**, so ACL behaviour is part of every evaluation. Any leak or invalid citation fails the run outright. Otherwise the run fails if recall@10 or MRR drops more than 2 points, if abstention accuracy drops at all, or if p95 latency rises more than 15%.
6. **Apply**: upsert `tuning_parameters` and append to `tuning_change_log`, which the app role can insert into but never update or delete. Record the evidence (posterior, lift, eval run id) with the change.
7. **Propose next**: `propose_arms(spec, current)` generates neighbouring values within bounds. Rank the candidates by where the signals point: e.g. many `missing_source` reasons suggest raising `top_k` or `token_budget`, and many `outdated_source` reasons suggest raising `rerank.weight.recency`. Only one running experiment per parameter per scope is allowed, enforced by a unique index.

## 5. Beyond parameter tuning

The same signals drive four further improvement channels. Each is human-approved or data-only, and none needs code changes:

- **Golden-set growth:** answers with negative feedback become `evaluation_cases` (`origin = 'feedback_mined'`) after an admin labels the right chunks, so the offline gate keeps pace with real usage. Every ACL denial pattern from `audit_logs` can seed a `security_suite` case with `must_not_retrieve_chunk_ids`.
- **Content gaps:** clusters of `insufficient_context` queries become the admin portal's "popular unanswered questions" (§5.17). That tells document owners what to write, which is often the biggest quality lever.
- **Stale and conflicting sources:** `outdated_source` feedback concentrated on one document flags it for review or archival. Answers citing two conflicting versions feed the §9 conflict queue.
- **Vocabulary learning:** when a query is quickly rephrased and the rephrased version gets positive feedback, the pair becomes a candidate acronym/synonym for query expansion, and a candidate multilingual alias for the knowledge graph (§14.7). Candidates go to review before use.
- **Chunk quality:** chunks that users repeatedly mark unhelpful, while their siblings are marked helpful, are candidates for re-splitting at the next re-index (`chunking.*` is `REVIEW`).

## 6. Volume check (Tier 2)

At the Tier 2 average of 1 QPS there are about 86k queries/day. With 10% enrolled and 3 arms, each arm gets ~2.9k answers/day. With a ~3% explicit-feedback rate plus implicit signals on most answers, the 200-sample minimum per arm is reached within a day, and a typical 5-point lift is detectable in about 3–5 days. Run experiments sequentially per stage (retrieval, then rerank, then context) so effects don't interact.

## 7. Implementation status

| Piece | Status |
|---|---|
| Tables: `retrieval_audit_logs`, `user_feedback`, `tuning_parameters`, `tuning_experiments`, `tuning_change_log`, `evaluation_cases`, `evaluation_runs` (tenant RLS) | ✅ migrations 0002/0003 |
| Capture APIs: `POST /api/v1/retrieval-audit`, `POST /api/v1/feedback` | ✅ canonical-db-agent |
| Registry, resolver, bandit, rewards, guardrails, offline evaluation | ✅ `packages/adaptive-tuning` (tested) |
| Orchestrator calls `resolve()` and records the snapshot | ⏳ with rag-orchestrator (Milestone 6–7) |
| Hourly reward/decide job + admin approval UI for `REVIEW` changes | ⏳ with admin-agent / observability-agent (Milestone 8) |
