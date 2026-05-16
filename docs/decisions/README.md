# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records (ADRs) for the Enterprise RAG System. ADRs document significant architectural decisions, their context, alternatives considered, and rationale.

---

## What is an ADR?

An Architecture Decision Record (ADR) captures an important architectural decision made along with its context and consequences. ADRs help teams:

- Understand why decisions were made
- Avoid revisiting settled decisions
- Onboard new team members
- Track architectural evolution
- Learn from past decisions

---

## ADR Format

All ADRs follow the template defined in [`template.md`](./template.md).

Key sections:

- **Context and Problem Statement:** What problem are we solving?
- **Decision Drivers:** What factors influenced the decision?
- **Considered Options:** What alternatives did we evaluate?
- **Decision Outcome:** What did we choose and why?
- **Pros and Cons:** Trade-offs of each option

---

## ADR Lifecycle

### Status Values

- **Proposed:** Decision is under discussion
- **Accepted:** Decision has been approved and is being implemented
- **Deprecated:** Decision is no longer recommended but may still be in use
- **Superseded:** Decision has been replaced by a newer ADR

### Creating a New ADR

1. Copy [`template.md`](./template.md)
2. Name it `ADR-XXX-short-title.md` (use next available number)
3. Fill in all sections
4. Submit for review
5. Update status to "Accepted" after approval
6. Link from related documentation

---

## ADR Index

### Infrastructure & Data

| ADR                                                | Title                         | Status     | Date |
| -------------------------------------------------- | ----------------------------- | ---------- | ---- |
| [ADR-001](./ADR-001-multi-tenancy-model.md)        | Multi-Tenancy Isolation Model | 📋 Planned | TBD  |
| [ADR-002](./ADR-002-postgresql-rls.md)             | PostgreSQL Row-Level Security | 📋 Planned | TBD  |
| [ADR-003](./ADR-003-qdrant-collection-strategy.md) | Qdrant Collection Strategy    | 📋 Planned | TBD  |

### Retrieval & Search

| ADR                                               | Title                     | Status     | Date |
| ------------------------------------------------- | ------------------------- | ---------- | ---- |
| [ADR-004](./ADR-004-hybrid-retrieval-strategy.md) | Hybrid Retrieval Strategy | 📋 Planned | TBD  |
| [ADR-005](./ADR-005-embedding-model-selection.md) | Embedding Model Selection | 📋 Planned | TBD  |
| [ADR-006](./ADR-006-reranking-approach.md)        | Reranking Approach        | 📋 Planned | TBD  |

### Generation & LLM

| ADR                                                 | Title                         | Status     | Date |
| --------------------------------------------------- | ----------------------------- | ---------- | ---- |
| [ADR-007](./ADR-007-llm-gateway-design.md)          | LLM Gateway Design            | 📋 Planned | TBD  |
| [ADR-008](./ADR-008-citation-enforcement.md)        | Citation Enforcement Strategy | 📋 Planned | TBD  |
| [ADR-009](./ADR-009-prompt-injection-prevention.md) | Prompt Injection Prevention   | 📋 Planned | TBD  |

### Security & Compliance

| ADR                                            | Title                  | Status     | Date |
| ---------------------------------------------- | ---------------------- | ---------- | ---- |
| [ADR-010](./ADR-010-triple-acl-enforcement.md) | Triple ACL Enforcement | 📋 Planned | TBD  |

---

## Planned ADRs

The following ADRs are planned for creation during implementation:

### Phase 1: Canonical Foundation

- **ADR-001:** Multi-Tenancy Isolation Model
- **ADR-002:** PostgreSQL Row-Level Security
- **ADR-010:** Triple ACL Enforcement

### Phase 3: Vector Retrieval

- **ADR-003:** Qdrant Collection Strategy
- **ADR-005:** Embedding Model Selection

### Phase 6: Hybrid Retrieval

- **ADR-004:** Hybrid Retrieval Strategy
- **ADR-006:** Reranking Approach

### Phase 7: Answer Generation

- **ADR-007:** LLM Gateway Design
- **ADR-008:** Citation Enforcement Strategy
- **ADR-009:** Prompt Injection Prevention

---

## ADR Guidelines

### When to Create an ADR

Create an ADR when:

- Making a significant architectural decision
- Choosing between multiple viable alternatives
- Establishing a pattern or standard
- Making a decision with long-term impact
- Resolving a contentious technical debate

### When NOT to Create an ADR

Don't create an ADR for:

- Trivial implementation details
- Decisions easily reversed
- Temporary workarounds
- Obvious choices with no alternatives

### Writing Good ADRs

**Do:**

- Be concise and clear
- Document alternatives considered
- Explain trade-offs honestly
- Include relevant context
- Link to supporting documentation
- Update status as decisions evolve

**Don't:**

- Write novels (keep it focused)
- Hide negative consequences
- Skip the "why" behind decisions
- Forget to update related docs
- Leave status ambiguous

---

## ADR Review Process

1. **Draft:** Author creates ADR from template
2. **Review:** Team reviews and provides feedback
3. **Discussion:** Team discusses alternatives and trade-offs
4. **Decision:** Team reaches consensus or escalates
5. **Approval:** Tech lead or architect approves
6. **Implementation:** Decision is implemented
7. **Validation:** Decision is validated in practice

---

## Related Documentation

- [System Architecture](../ARCHITECTURE.md)
- [Implementation Roadmap](../IMPLEMENTATION_ROADMAP.md)
- [Agent Documentation](../AGENTS.md)

---

## References

- [ADR GitHub Organization](https://adr.github.io/)
- [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [ADR Tools](https://github.com/npryce/adr-tools)
