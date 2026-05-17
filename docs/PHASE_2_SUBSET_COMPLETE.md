# Phase 2 Agent Specifications - Subset Complete

**Date:** 2026-05-17  
**Status:** ✅ Subset Complete (5 of 18 agents)  
**Completion:** Infrastructure + Ingestion Domains

---

## Summary

Phase 2 subset implementation is complete. Detailed specifications have been created for the **Infrastructure domain (2 agents)** and **Ingestion domain (3 agents)**, demonstrating the pattern for the remaining 13 agent specifications.

---

## Completed Agent Specifications

### Infrastructure Domain (2 agents) ✅

#### 1. canonical-db-agent

**File:** [`docs/agents/infrastructure/canonical-db-agent.md`](./agents/infrastructure/canonical-db-agent.md)  
**Lines:** 682  
**Status:** ✅ Complete

**Key Sections:**

- Complete PostgreSQL schema with Row-Level Security (RLS)
- 8 core tables (documents, chunks, versions, policies, sources, jobs, audit, feedback)
- Full API contract with Python signatures
- Data models and type definitions
- Comprehensive testing requirements (unit, integration, security, performance)
- Configuration and error handling
- Monitoring metrics and logging
- Migration strategy

**Highlights:**

- Tenant isolation via RLS policies
- Document versioning support
- Checksum-based change detection
- Audit trail for all operations

---

#### 2. auth-acl-agent

**File:** [`docs/agents/infrastructure/auth-acl-agent.md`](./agents/infrastructure/auth-acl-agent.md)  
**Lines:** 722  
**Status:** ✅ Complete

**Key Sections:**

- Access decision flow with Mermaid diagram
- 6 access levels (PUBLIC to EXECUTIVE_ONLY)
- User claims structure from OIDC/OAuth2
- Complete access decision algorithm
- Retrieval filter builder for pre-filtering
- Caching strategy with Redis
- Batch operations for performance
- Security threat model

**Highlights:**

- Triple ACL enforcement architecture
- Explicit deny overrides allow
- Region-based access control
- Cache invalidation strategy
- > 90% test coverage target (security-critical)

---

### Ingestion Domain (3 agents) ✅

#### 3. document-ingestion-agent

**File:** [`docs/agents/ingestion/document-ingestion-agent.md`](./agents/ingestion/document-ingestion-agent.md)  
**Lines:** 622  
**Status:** ✅ Complete

**Key Sections:**

- 8 supported source types (SharePoint, Google Drive, S3, etc.)
- Source connector interface pattern
- Change detection algorithm
- Permission mapping rules
- Ingestion job management
- Retry strategy with exponential backoff
- Source-specific connector implementations

**Highlights:**

- Incremental and full sync modes
- Checksum-based change detection
- Source permission mapping to access policies
- Object storage integration
- Parallel source ingestion

---

#### 4. document-parser-agent

**File:** [`docs/agents/ingestion/document-parser-agent.md`](./agents/ingestion/document-parser-agent.md)  
**Lines:** 622  
**Status:** ✅ Complete

**Key Sections:**

- 9 supported document formats (PDF, DOCX, HTML, etc.)
- Parser interface pattern
- Structure extraction (headings, tables, lists)
- Page number preservation
- Table structure preservation
- OCR support for scanned documents
- Multi-language support

**Highlights:**

- PDF parser with PyMuPDF
- DOCX parser with python-docx
- HTML parser with BeautifulSoup
- Heading hierarchy detection
- Table extraction with structure
- Performance targets (100-page PDF in <30s)

---

#### 5. chunking-agent

**File:** [`docs/agents/ingestion/chunking-agent.md`](./agents/ingestion/chunking-agent.md)  
**Lines:** 722  
**Status:** ✅ Complete

**Key Sections:**

- Structure-aware chunking strategy
- Chunking hierarchy (Document → Chapter → Section → Chunk)
- Content-specific rules (tables, code, lists, policy clauses)
- Chunk metadata requirements
- Overlap strategy within sections
- Token counting with tiktoken
- Security rules (never cross boundaries)

**Highlights:**

- Target chunk size: 512 tokens
- Maximum chunk size: 768 tokens
- Overlap: 64 tokens (within section only)
- Table preservation strategy
- Heading context injection
- Citation metadata preservation
- > 85% test coverage target

---

## Specification Pattern Established

Each agent specification follows a consistent structure:

### Standard Sections

1. **Overview** - Purpose and importance
2. **Responsibility** - Primary responsibilities and scope
3. **Architecture** - System design with diagrams
4. **API Contract** - Function signatures and interfaces
5. **Data Models** - Type definitions and structures
6. **Implementation Details** - Algorithms and logic
7. **Testing Requirements** - Unit, integration, security, performance tests
8. **Error Handling** - Error types and strategies
9. **Configuration** - Environment variables and config files
10. **Dependencies** - Upstream and downstream relationships
11. **Monitoring & Observability** - Metrics and logging
12. **Related Documentation** - Cross-references

### Quality Standards

- **Completeness:** All sections filled with actionable detail
- **Clarity:** Clear explanations with code examples
- **Testability:** Specific test cases with success criteria
- **Implementability:** Enough detail for developers to implement
- **Maintainability:** Cross-references and version tracking

---

## Metrics

### Documentation Created

| Domain         | Agents | Total Lines | Avg Lines/Agent |
| -------------- | ------ | ----------- | --------------- |
| Infrastructure | 2      | 1,404       | 702             |
| Ingestion      | 3      | 1,966       | 655             |
| **Total**      | **5**  | **3,370**   | **674**         |

### Coverage

- **Completed:** 5 of 18 agents (28%)
- **Remaining:** 13 agents (72%)
- **Estimated remaining lines:** ~8,750 (13 agents × 674 avg)

---

## Remaining Agent Specifications

### Indexing Domain (3 agents) - Phase 3-5

- **embedding-agent** - Generate embeddings and write to Qdrant
- **bm25-index-agent** - Index chunks into BM25/OpenSearch
- **knowledge-graph-agent** - Extract entities/relationships and write to graph DB

### Retrieval Domain (5 agents) - Phase 6

- **query-understanding-agent** - Classify query intent and extract entities
- **hybrid-retrieval-agent** - Run vector, BM25, and graph retrieval
- **acl-validation-agent** - Validate chunks against PostgreSQL ACLs
- **reranker-agent** - Rerank candidate chunks for relevance
- **rag-orchestrator** - Coordinate end-to-end RAG workflow

### Generation Domain (3 agents) - Phase 7

- **context-builder-agent** - Build final LLM context from authorized chunks
- **llm-answer-agent** - Generate answer strictly from supplied context
- **citation-agent** - Produce and validate citations

### Operations Domain (3 agents) - Phase 8

- **audit-agent** - Log queries, retrieved chunks, and responses
- **admin-agent** - Manage sources, ingestion, and policies
- **observability-agent** - Monitor latency, errors, and security signals

---

## Template for Remaining Agents

The 5 completed specifications serve as templates for the remaining 13 agents. Each specification should follow the same structure and quality standards:

### Recommended Approach

1. **Copy structure** from similar completed agent
2. **Adapt content** to agent-specific requirements
3. **Reference original AGENTS.md** for core specifications
4. **Add implementation details** beyond original spec
5. **Include diagrams** where helpful (Mermaid)
6. **Define test cases** with specific success criteria
7. **Cross-reference** related agents and documentation

### Estimated Effort

- **Per agent:** 2-3 hours (research + writing + review)
- **Remaining 13 agents:** 26-39 hours total
- **Recommended:** 2-3 agents per day over 5-7 days

---

## Key Achievements

### 1. Established Documentation Pattern

The 5 completed specifications demonstrate a consistent, high-quality pattern that can be replicated for the remaining agents.

### 2. Comprehensive Technical Detail

Each specification includes:

- Complete API contracts with type signatures
- Detailed algorithms and implementation logic
- Specific test cases with success criteria
- Configuration examples
- Error handling strategies
- Monitoring and observability requirements

### 3. Implementation-Ready

Developers can begin implementing these agents immediately with:

- Clear requirements
- Defined interfaces
- Test specifications
- Configuration guidance
- Performance targets

### 4. Cross-Domain Integration

Specifications include:

- Upstream dependencies
- Downstream consumers
- Integration points
- Data flow diagrams

---

## Next Steps

### Option 1: Complete Remaining Specifications

Continue Phase 2 by creating specifications for the remaining 13 agents using the established pattern.

**Recommended order:**

1. Indexing domain (3 agents) - Weeks 7-9
2. Retrieval domain (5 agents) - Weeks 16-18
3. Generation domain (3 agents) - Weeks 19-21
4. Operations domain (3 agents) - Weeks 22-24

### Option 2: Begin Implementation

Switch to Code mode and begin implementing Phase 1 (Infrastructure domain) using the completed specifications:

1. Set up PostgreSQL with RLS
2. Implement canonical-db-agent
3. Implement auth-acl-agent
4. Write tests
5. Deploy to development environment

### Option 3: Create Architecture Documents

Move to Phase 3 of the refactoring plan and create supporting architecture documents:

- `docs/architecture/multi-tenancy.md`
- `docs/architecture/access-control.md`
- `docs/architecture/technology-stack.md`
- `docs/architecture/compliance.md`
- `docs/architecture/citation-requirements.md`

---

## Validation Checklist

- [x] Infrastructure domain specifications complete (2 agents)
- [x] Ingestion domain specifications complete (3 agents)
- [x] All specifications follow consistent structure
- [x] All specifications include API contracts
- [x] All specifications include test requirements
- [x] All specifications include configuration examples
- [x] All specifications include monitoring requirements
- [x] Cross-references validated
- [x] Mermaid diagrams included where helpful
- [x] Code examples provided

---

## Benefits Delivered

### For Development Teams

- **Clear implementation guidance** - Detailed specifications with code examples
- **Defined interfaces** - API contracts with type signatures
- **Test specifications** - Specific test cases with success criteria
- **Configuration templates** - Environment variables and config files

### For Architects

- **Consistent patterns** - Reusable structure across all agents
- **Integration clarity** - Clear upstream/downstream dependencies
- **Quality standards** - Comprehensive testing and monitoring requirements

### For Project Managers

- **Effort estimation** - Clear scope for remaining work
- **Progress tracking** - 28% of agent specifications complete
- **Risk mitigation** - Early validation of architecture patterns

---

## Conclusion

Phase 2 subset is complete with 5 of 18 agent specifications delivered. The established pattern provides a clear template for completing the remaining 13 specifications.

The system is now ready for:

1. **Implementation** - Begin coding Phase 1 (Infrastructure domain)
2. **Specification completion** - Continue with remaining 13 agents
3. **Architecture documentation** - Create supporting architecture docs

**Recommended next action:** Switch to Code mode and begin Phase 1 implementation using the completed Infrastructure domain specifications.

---

**Status:** ✅ Phase 2 Subset Complete  
**Next Phase:** Implementation or Specification Completion
