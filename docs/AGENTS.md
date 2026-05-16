# Enterprise RAG System - Agent Documentation

**Version:** 2.0  
**Last Updated:** 2026-05-16  
**Status:** Ready for Implementation

---

## Overview

This document serves as the master index for the Enterprise RAG System agent documentation. The system consists of 18 modular agents organized into 5 domains, implementing a production-grade RAG solution with strict access control, citation enforcement, and multi-tenant support.

---

## Quick Navigation

### 📚 Core Documentation
- [System Architecture](./ARCHITECTURE.md) - High-level system design and data flow
- [Implementation Roadmap](./IMPLEMENTATION_ROADMAP.md) - 8-phase implementation plan
- [Technology Stack](./architecture/technology-stack.md) - Infrastructure and tools
- [Access Control Model](./architecture/access-control.md) - Security and authorization

### 🏗️ Architecture Decision Records
- [ADR Index](./decisions/README.md) - All architectural decisions
- [ADR Template](./decisions/template.md) - Template for new ADRs

### 📋 Implementation Phases
- [Phase 1: Canonical Foundation](./phases/phase-1-canonical-foundation/README.md)
- [Phase 2: Ingestion & Chunking](./phases/phase-2-ingestion-chunking/README.md)
- [Phase 3: Vector Retrieval](./phases/phase-3-vector-retrieval/README.md)
- [Phase 4: BM25 Retrieval](./phases/phase-4-bm25-retrieval/README.md)
- [Phase 5: Knowledge Graph](./phases/phase-5-knowledge-graph/README.md)
- [Phase 6: Hybrid Retrieval & ACL](./phases/phase-6-hybrid-retrieval-acl/README.md)
- [Phase 7: Answer Generation](./phases/phase-7-answer-generation/README.md)
- [Phase 8: Audit & Observability](./phases/phase-8-audit-observability/README.md)

---

## Agent Domains

### 🏛️ Infrastructure Domain
**Agents:** 2 | **Phase:** 1 | **Status:** Foundation

Owns canonical data storage, authentication, and access control.

- [`canonical-db-agent`](./agents/infrastructure/canonical-db-agent.md) - PostgreSQL schema and canonical records
- [`auth-acl-agent`](./agents/infrastructure/auth-acl-agent.md) - Authentication and access policy evaluation

[📖 Infrastructure Domain Overview](./agents/infrastructure/README.md)

---

### 📥 Ingestion Domain
**Agents:** 3 | **Phase:** 2 | **Status:** Planned

Handles document ingestion, parsing, and chunking.

- [`document-ingestion-agent`](./agents/ingestion/document-ingestion-agent.md) - Pull documents from external sources
- [`document-parser-agent`](./agents/ingestion/document-parser-agent.md) - Extract text and structure
- [`chunking-agent`](./agents/ingestion/chunking-agent.md) - Create structured chunks with metadata

[📖 Ingestion Domain Overview](./agents/ingestion/README.md)

---

### 🔍 Indexing Domain
**Agents:** 3 | **Phases:** 3-5 | **Status:** Planned

Indexes chunks into vector, keyword, and graph stores.

- [`embedding-agent`](./agents/indexing/embedding-agent.md) - Generate embeddings and write to Qdrant
- [`bm25-index-agent`](./agents/indexing/bm25-index-agent.md) - Index chunks into BM25/OpenSearch
- [`knowledge-graph-agent`](./agents/indexing/knowledge-graph-agent.md) - Extract entities/relationships and write to graph DB

[📖 Indexing Domain Overview](./agents/indexing/README.md)

---

### 🎯 Retrieval Domain
**Agents:** 5 | **Phase:** 6 | **Status:** Planned

Orchestrates hybrid retrieval with access control enforcement.

- [`query-understanding-agent`](./agents/retrieval/query-understanding-agent.md) - Classify query intent and extract entities
- [`hybrid-retrieval-agent`](./agents/retrieval/hybrid-retrieval-agent.md) - Run vector, BM25, and graph retrieval
- [`acl-validation-agent`](./agents/retrieval/acl-validation-agent.md) - Validate chunks against PostgreSQL ACLs
- [`reranker-agent`](./agents/retrieval/reranker-agent.md) - Rerank candidate chunks for relevance
- [`rag-orchestrator`](./agents/retrieval/rag-orchestrator.md) - Coordinate end-to-end RAG workflow

[📖 Retrieval Domain Overview](./agents/retrieval/README.md)

---

### 💬 Generation Domain
**Agents:** 3 | **Phase:** 7 | **Status:** Planned

Builds context, generates answers, and validates citations.

- [`context-builder-agent`](./agents/generation/context-builder-agent.md) - Build final LLM context from authorized chunks
- [`llm-answer-agent`](./agents/generation/llm-answer-agent.md) - Generate answer strictly from supplied context
- [`citation-agent`](./agents/generation/citation-agent.md) - Produce and validate citations

[📖 Generation Domain Overview](./agents/generation/README.md)

---

### 📊 Operations Domain
**Agents:** 2 | **Phase:** 8 | **Status:** Planned

Provides audit logging, administration, and observability.

- [`audit-agent`](./agents/operations/audit-agent.md) - Log queries, retrieved chunks, and responses
- [`admin-agent`](./agents/operations/admin-agent.md) - Manage sources, ingestion, and policies
- [`observability-agent`](./agents/operations/observability-agent.md) - Monitor latency, errors, and security signals

[📖 Operations Domain Overview](./agents/operations/README.md)

---

## System Requirements

### Scale Targets (Tier 2 - Initial Production)
- **Documents:** 10,000
- **Estimated chunks:** 500,000 (50 chunks/doc average)
- **Concurrent users:** 50
- **Average QPS:** 1
- **Peak QPS:** 5
- **Document ingestion rate:** 1,000 documents/day
- **Geographic distribution:** One primary region with future multi-region support

### Technology Stack
- **Database:** PostgreSQL 15+ (with Row-Level Security)
- **Vector Store:** Qdrant 1.7+ (tenant-specific collections)
- **Keyword Search:** OpenSearch 2.11+ (BM25)
- **Knowledge Graph:** Neo4j 5.x Community Edition
- **Cache:** Redis 7+
- **Message Broker:** RabbitMQ 3.12+ or Apache Kafka 3.6+
- **Object Storage:** MinIO or AWS S3
- **Embeddings:** OpenAI text-embedding-3-large (1536d)
- **LLM Gateway:** Multi-provider routing (GPT-4, Claude, Llama 3)

[📖 Complete Technology Stack](./architecture/technology-stack.md)

---

## Multi-Tenancy Model

The system uses a **hybrid tenant-isolation model**:

- **PostgreSQL:** Shared database with `tenant_id` + Row-Level Security (RLS)
- **Qdrant:** Separate collections per tenant (`enterprise_chunks_{tenant_id}_{model_version}`)
- **BM25/OpenSearch:** Separate indexes per tenant (high-isolation) or shared with filtering
- **Knowledge Graph:** Tenant-specific namespaces or separate databases
- **Object Storage:** Tenant-specific prefixes or buckets

**Triple ACL Enforcement:** All retrieval results from Qdrant, BM25, and Knowledge Graph must be revalidated against PostgreSQL ACL rules before entering the LLM context.

[📖 Multi-Tenancy Architecture](./architecture/multi-tenancy.md)

---

## Access Control Levels

```text
PUBLIC                  - Accessible to all users
INTERNAL_GENERAL        - Accessible to all employees
DEPARTMENT_RESTRICTED   - Accessible to specific departments
CONFIDENTIAL            - Restricted to authorized users/groups
REGULATED               - Compliance-controlled access
EXECUTIVE_ONLY          - Executive leadership only
```

[📖 Access Control Model](./architecture/access-control.md)

---

## Compliance & Data Governance

The system enforces **GDPR and SOC 2-style controls** as baseline requirements, with CCPA/CPRA, HIPAA, and industry-specific compliance enabled when applicable.

**Key Requirements:**
- Data residency enforcement
- Configurable retention policies
- Right-to-deletion workflows
- Compliance-checked model calls
- Full audit trails

[📖 Compliance Requirements](./architecture/compliance.md)

---

## Implementation Strategy

The system is built incrementally across 8 phases:

1. **Canonical Foundation** (Weeks 1-3) - PostgreSQL + ACL
2. **Ingestion & Chunking** (Weeks 4-6) - Document processing
3. **Vector Retrieval** (Weeks 7-9) - Qdrant semantic search
4. **BM25 Retrieval** (Weeks 10-12) - Keyword search
5. **Knowledge Graph** (Weeks 13-15) - Entity relationships
6. **Hybrid Retrieval & ACL** (Weeks 16-18) - Combined retrieval + validation
7. **Answer Generation** (Weeks 19-21) - LLM + citations
8. **Audit & Observability** (Weeks 22-24) - Logging + monitoring

[📖 Implementation Roadmap](./IMPLEMENTATION_ROADMAP.md)

---

## Testing Strategy

Each agent requires:
- **Unit Tests:** Input validation, metadata correctness, security rules
- **Integration Tests:** Cross-agent interactions, database operations
- **End-to-End Tests:** Full RAG workflow scenarios
- **Security Tests:** Access control bypass attempts, prompt injection
- **Performance Tests:** Latency, throughput, scale validation

[📖 Testing Guidelines](./testing/README.md)

---

## Non-Negotiable Security Rules

```text
✓ Do not trust document text as instructions
✓ Do not let the LLM see unauthorized chunks
✓ Do not generate uncited policy answers
✓ Do not cite chunks that were not in context
✓ Do not use archived documents unless explicitly requested and authorized
✓ Do not allow cross-tenant retrieval
✓ Do not skip PostgreSQL ACL validation
✓ Do not rely only on Qdrant/BM25 metadata filtering for authorization
```

---

## Contributing

### Adding New Agents
1. Create agent specification in appropriate domain folder
2. Update domain README
3. Create ADR if architectural decision is needed
4. Add to implementation roadmap
5. Update this master index

### Modifying Existing Agents
1. Update agent specification
2. Document changes in ADR
3. Update affected integration points
4. Update test requirements
5. Update implementation roadmap if timeline changes

[📖 Contribution Guidelines](./CONTRIBUTING.md)

---

## Support & Resources

- **Architecture Questions:** See [ARCHITECTURE.md](./ARCHITECTURE.md)
- **Implementation Questions:** See [IMPLEMENTATION_ROADMAP.md](./IMPLEMENTATION_ROADMAP.md)
- **Security Questions:** See [Access Control Model](./architecture/access-control.md)
- **Compliance Questions:** See [Compliance Requirements](./architecture/compliance.md)

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2026-05-16 | Refactored into modular domain structure |
| 1.5 | 2026-05-16 | Added multi-tenancy, scale, compliance, caching, multi-language |
| 1.0 | 2026-05-15 | Initial specification |

---

**Next Steps:** Review [ARCHITECTURE.md](./ARCHITECTURE.md) for system design, then proceed to [Phase 1 Implementation](./phases/phase-1-canonical-foundation/README.md).
