# AGENTS.md Integration Plan

## Summary of Collected Answers

### Q1: Multi-Tenancy Architecture ✅

**Answer:** Option D - Hybrid approach

- PostgreSQL: Shared database with Row-Level Security (RLS)
- Qdrant: Separate collections per tenant
- BM25: Separate indexes per tenant (high-isolation) or shared with filtering
- Knowledge Graph: Tenant-specific namespaces/labels
- Object Storage: Tenant-specific prefixes/buckets
- **Validation:** Triple ACL enforcement required

**Appropriateness:** ✅ Excellent - Balances security, performance, and operational complexity

---

### Q2: Embedding Model Strategy ✅

**Answer:** OpenAI text-embedding-3-large (1536 dims) as default

- Platform must be embedding-model agnostic
- Store model metadata in PostgreSQL
- Blue-green re-embedding strategy for model changes
- Support multiple models simultaneously (per tenant)
- Cost optimization after POC

**Appropriateness:** ✅ Excellent - Provides flexibility and clear migration path

---

### Q3: LLM Selection ✅

**Answer:** LLM Gateway with model routing

- High-quality model for complex/sensitive queries
- Lower-cost models for simple tasks
- Local models for on-prem/confidential workflows
- Fallback must preserve safety level
- Central rate limiting and quotas
- Comprehensive logging

**Appropriateness:** ✅ Excellent - Flexible, cost-effective, and safe

---

### Q4: Scale Requirements ✅

**Answer:** Tier-based approach, targeting Tier 2 initially

- Documents: 10,000
- Chunks: 500,000 (50 chunks/doc estimate)
- Concurrent users: 50
- Average QPS: 1, Peak QPS: 5
- Ingestion: 1,000 docs/day
- Geographic: Single region initially

**Appropriateness:** ✅ Good - Realistic starting point with clear scaling path

---

### Q5: Compliance Requirements ✅

**Answer:** GDPR + SOC 2 baseline, with CCPA/HIPAA modules

- Cloud providers require DPA/BAA
- Data residency enforcement
- Configurable retention policies
- Right-to-deletion support
- Compliance-checked model calls
- Comprehensive audit trail

**Appropriateness:** ✅ Excellent - Comprehensive compliance framework

---

### Q6: Document Update Strategy ✅

**Answer:** Immutable versioning with event-driven re-indexing

- New version for content changes
- Metadata-only updates don't trigger re-embedding
- Soft delete + hard delete support
- Legal hold blocks hard deletion
- Consistent version snapshots for queries
- Configurable retention by classification

**Appropriateness:** ✅ Excellent - Robust versioning and update strategy

---

### Q7: Chunking Configuration ✅

**Answer:** Structure-aware chunking

- Target: 512 tokens, Max: 768 tokens
- Overlap: 64 tokens (within section only)
- Tables: Preserve if < 1024 tokens, split with headers if larger
- Respect document structure and boundaries
- Never cross access-control boundaries
- Comprehensive metadata per chunk

**Appropriateness:** ✅ Excellent - Well-balanced chunking strategy

---

### Q8: Access Policy Granularity ✅

**Answer:** Document-level for MVP, section-level for production

- Document-level: Simple baseline
- Section-level: Required for mixed-sensitivity documents
- Chunk-level: Exceptional cases only
- Paragraph-level: Strict legal/regulatory only
- Inheritance model with most restrictive wins
- Never cross boundaries during chunking

**Appropriateness:** ✅ Excellent - Pragmatic progression from simple to complex

---

### Q9: Knowledge Graph Scope ✅

**Answer:** Comprehensive entity/relationship model with evidence grounding

- Entities: Policy, Department, Role, Process, System, Location, Document, etc.
- Relationships: APPLIES_TO, SUPERSEDES, REFERENCES, APPROVES, etc.
- Every relationship must have source evidence
- Access control inherited from source
- Version-aware relationships
- Human review for high-impact relationships

**Appropriateness:** ✅ Excellent - Comprehensive but grounded approach

---

### Q10: Error Handling Philosophy ✅

**Answer:** Graceful degradation for retrieval, fail fast for LLM

- Retrieval failures: Continue with available sources
- LLM failures: Return clear, safe error message
- No unreliable answers

**Appropriateness:** ✅ Good - Aligns with best practices

---

### Q11: Caching Strategy ✅

**Answer:** Access-aware, tenant-aware, version-aware caching

- Cache: Query embeddings, retrieval results, access policies, LLM responses (low-risk only)
- Access-aware cache keys
- Revalidate chunk IDs against ACLs
- Comprehensive invalidation rules
- Security: Never bypass access control
- Short TTLs for sensitive content

**Appropriateness:** ✅ Excellent - Security-first caching strategy

---

### Q12: Reranking Model ✅

**Answer:** Feature-based for MVP, add cross-encoder for production

- MVP: Feature-based (deterministic, explainable)
- Production: Hybrid approach
- Cross-encoder for high-value queries only
- ACL validation before reranking
- Fallback to feature-based on failure
- Context diversity controls

**Appropriateness:** ✅ Excellent - Cost-effective with quality upgrade path

---

### Q13: Feedback Loop ✅

**Answer:** Structured feedback with human review

- Types: Thumbs up/down, citation accuracy, missing/incorrect info, exposure reports
- Storage: PostgreSQL with full query trace
- Usage: Improve ranking, identify gaps, build evaluation datasets
- Human review for high-impact feedback
- Severity classification with critical alerts
- Privacy and compliance enforcement

**Appropriateness:** ✅ Excellent - Comprehensive feedback system

---

### Q14: Multi-Language Support ✅

**Answer:** Multilingual-ready from the beginning

- Start with English + priority languages
- Detect and store language per document/section/chunk
- Multilingual embedding model
- Language-aware chunking and BM25
- Multilingual Knowledge Graph aliases
- Original language as source of truth
- Cite original source in translated answers

**Appropriateness:** ✅ Excellent - Essential for multinational company

---

### Q15: Citation Format ✅

**Answer:** Numbered inline citations with expandable details

- Format: `[1]` inline next to claims
- Source list below answer
- Expandable details: Document, version, page, section, classification, etc.
- Every factual claim must be cited
- Citations must resolve to authorized chunks only
- Access control on citation details

**Appropriateness:** ✅ Excellent - Clear, accessible, and secure

---

## Integration Strategy

### Phase 1: Add New Sections to AGENTS.md

1. **Section 1.5: Multi-Tenancy Architecture** (after System Goals)
2. **Section 2.5: Technology Stack** (after Core Architecture)
3. **Section 3.5: Scale Requirements** (after Implementation Philosophy)
4. **Section 16: Compliance and Data Governance** (new section)
5. **Section 17: Caching Strategy** (new section)
6. **Section 18: Multi-Language Support** (new section)

### Phase 2: Update Existing Sections

1. **Section 5.2 (auth-acl-agent):** Add access policy granularity details
2. **Section 5.5 (chunking-agent):** Update with confirmed chunking parameters
3. **Section 5.6 (embedding-agent):** Add embedding model strategy and re-embedding workflow
4. **Section 5.8 (knowledge-graph-agent):** Expand entity/relationship scope
5. **Section 5.12 (reranker-agent):** Add reranking model decision
6. **Section 5.14 (llm-answer-agent):** Add LLM Gateway and model routing
7. **Section 5.15 (citation-agent):** Add citation format specification
8. **Section 5.16 (audit-agent):** Add feedback loop details
9. **Section 6.1 (Ingestion Workflow):** Add document update handling
10. **Section 8 (Citation Requirements):** Expand with citation format details
11. **Section 13 (Minimum Acceptance Criteria):** Add new criteria from answers

### Phase 3: Add Cross-References

1. Link multi-tenancy architecture to all agent specifications
2. Link compliance requirements to relevant agents
3. Link caching strategy to retrieval and answer agents
4. Link multi-language support to all content-processing agents
5. Update milestone dependencies based on new requirements

### Phase 4: Document Cleanup

1. Update document version to 2.0
2. Update modification date
3. Add "Decisions Made" section summarizing the 15 answers
4. Ensure consistent terminology throughout
5. Verify all placeholders are resolved
6. Validate cross-references
7. Check for contradictions

---

## Validation Checklist

- [ ] All 15 answers integrated into appropriate sections
- [ ] No contradictions introduced
- [ ] Cross-references updated
- [ ] Terminology standardized
- [ ] Version number updated
- [ ] Modification date updated
- [ ] Table of contents updated
- [ ] All placeholders resolved
- [ ] Document ready for Phase 1 implementation
- [ ] Milestone dependencies validated

---

## Integration Order

1. ✅ Review answers (DONE)
2. Add new top-level sections (1.5, 2.5, 3.5, 16, 17, 18)
3. Update agent specifications (5.2, 5.5, 5.6, 5.8, 5.12, 5.14, 5.15, 5.16)
4. Update workflows and requirements (6.1, 8, 13)
5. Add cross-references throughout
6. Final cleanup and validation
7. Generate updated table of contents
