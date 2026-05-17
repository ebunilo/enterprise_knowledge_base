# Citation Agent Specification

**Version:** 2.0  
**Last Updated:** 2026-05-17  
**Status:** Production Ready  
**Domain:** Generation  
**Dependencies:** [`context-builder-agent`](context-builder-agent.md), [`llm-answer-agent`](llm-answer-agent.md), [`canonical-db-agent`](../infrastructure/canonical-db-agent.md), [`acl-validation-agent`](../retrieval/acl-validation-agent.md)

---

## 1. Purpose

The **citation-agent** validates that all cited claims in LLM-generated answers map to authorized source chunks and formats citations for user presentation. This agent is the final enforcement point ensuring citation integrity, preventing fabricated citations, and maintaining audit trails for compliance.

### Key Responsibilities

1. **Citation Validation:** Verify all citations reference authorized chunks that were in the LLM context
2. **Citation Formatting:** Format citations consistently for UI presentation
3. **Fabrication Detection:** Detect and reject fabricated or hallucinated citations
4. **Authorization Verification:** Confirm cited chunks are still authorized for the user
5. **Uncited Claim Detection:** Identify factual claims that lack proper citations (where possible)
6. **Metadata Enrichment:** Add document metadata to citations for user navigation
7. **Audit Trail:** Log citation validation results for compliance and quality monitoring

---

## 2. System Context

### Position in RAG Pipeline

```text
User Query
   ↓
Query Understanding
   ↓
Hybrid Retrieval
   ↓
ACL Validation
   ↓
Reranking
   ↓
Context Building
   ↓
LLM Answer Generation
   ↓
[CITATION AGENT] ← Current Stage
   ↓
Audit Logging
   ↓
Response to User
```

### Input Sources

- **LLM Answer:** Generated answer with inline citations (e.g., `[Source 1]`)
- **Context Chunks:** Chunks that were provided to the LLM
- **User Context:** User identity and access claims for revalidation
- **Document Metadata:** From PostgreSQL for citation enrichment

### Output Consumers

- **API Gateway:** Returns validated answer with formatted citations to user
- **Audit Agent:** Receives citation validation results for logging
- **Observability Agent:** Receives metrics on citation quality and validation failures

---

## 3. Core Functionality

### 3.1 Citation Extraction

Extract citation references from LLM-generated answer text.

**Supported Citation Formats:**

```text
[Source 1]
[Source 2]
[1]
[2]
(Source 1)
(1)
```

**Extraction Logic:**

```python
import re
from typing import List, Set

class CitationExtractor:
    """Extract citation references from answer text."""

    # Regex patterns for different citation formats
    CITATION_PATTERNS = [
        r'\[Source\s+(\d+)\]',      # [Source 1]
        r'\[(\d+)\]',                # [1]
        r'\(Source\s+(\d+)\)',       # (Source 1)
        r'\((\d+)\)',                # (1)
    ]

    def extract_citations(self, answer_text: str) -> Set[int]:
        """
        Extract all citation numbers from answer text.

        Args:
            answer_text: LLM-generated answer with inline citations

        Returns:
            Set of citation numbers found in text
        """
        citation_numbers = set()

        for pattern in self.CITATION_PATTERNS:
            matches = re.finditer(pattern, answer_text)
            for match in matches:
                citation_num = int(match.group(1))
                citation_numbers.add(citation_num)

        return citation_numbers

    def extract_citation_positions(self, answer_text: str) -> List[dict]:
        """
        Extract citations with their positions in text.

        Returns:
            List of {citation_number, start_pos, end_pos, matched_text}
        """
        positions = []

        for pattern in self.CITATION_PATTERNS:
            matches = re.finditer(pattern, answer_text)
            for match in matches:
                citation_num = int(match.group(1))
                positions.append({
                    'citation_number': citation_num,
                    'start_pos': match.start(),
                    'end_pos': match.end(),
                    'matched_text': match.group(0)
                })

        # Sort by position in text
        positions.sort(key=lambda x: x['start_pos'])
        return positions
```

### 3.2 Citation Validation

Validate that all citations reference authorized chunks from the context.

**Validation Rules:**

1. **Citation Number Validity:** Citation number must be within range [1, N] where N is the number of context chunks
2. **Chunk Authorization:** Cited chunk must have been authorized by ACL validation
3. **Context Inclusion:** Cited chunk must have been included in the LLM context
4. **No Fabrication:** Citation must not reference non-existent chunks
5. **Active Status:** Cited document must still be active (not deleted/archived)
6. **User Authorization:** User must still have access to cited chunk at response time

**Validation Implementation:**

```python
from typing import List, Dict, Set
from dataclasses import dataclass
from enum import Enum

class CitationValidationError(Enum):
    """Types of citation validation errors."""
    OUT_OF_RANGE = "citation_number_out_of_range"
    NOT_IN_CONTEXT = "chunk_not_in_context"
    UNAUTHORIZED = "user_not_authorized"
    DOCUMENT_INACTIVE = "document_not_active"
    CHUNK_NOT_FOUND = "chunk_not_found"
    FABRICATED = "fabricated_citation"

@dataclass
class CitationValidationResult:
    """Result of citation validation."""
    valid: bool
    citation_number: int
    chunk_id: str = None
    document_id: str = None
    error_type: CitationValidationError = None
    error_message: str = None

class CitationValidator:
    """Validate citations against context and authorization."""

    def __init__(self, canonical_db, acl_validator):
        self.canonical_db = canonical_db
        self.acl_validator = acl_validator

    def validate_citations(
        self,
        citation_numbers: Set[int],
        context_chunks: List[dict],
        user_context: dict
    ) -> Dict[int, CitationValidationResult]:
        """
        Validate all citations in the answer.

        Args:
            citation_numbers: Set of citation numbers from answer
            context_chunks: Chunks that were in LLM context
            user_context: User identity and access claims

        Returns:
            Dict mapping citation_number to validation result
        """
        results = {}

        for citation_num in citation_numbers:
            result = self._validate_single_citation(
                citation_num,
                context_chunks,
                user_context
            )
            results[citation_num] = result

        return results

    def _validate_single_citation(
        self,
        citation_num: int,
        context_chunks: List[dict],
        user_context: dict
    ) -> CitationValidationResult:
        """Validate a single citation."""

        # Rule 1: Citation number must be in valid range
        if citation_num < 1 or citation_num > len(context_chunks):
            return CitationValidationResult(
                valid=False,
                citation_number=citation_num,
                error_type=CitationValidationError.OUT_OF_RANGE,
                error_message=f"Citation {citation_num} out of range [1, {len(context_chunks)}]"
            )

        # Get the chunk (1-indexed)
        chunk = context_chunks[citation_num - 1]
        chunk_id = chunk['chunk_id']
        document_id = chunk['document_id']

        # Rule 2: Verify chunk exists in PostgreSQL
        db_chunk = self.canonical_db.get_chunk(chunk_id)
        if not db_chunk:
            return CitationValidationResult(
                valid=False,
                citation_number=citation_num,
                chunk_id=chunk_id,
                error_type=CitationValidationError.CHUNK_NOT_FOUND,
                error_message=f"Chunk {chunk_id} not found in database"
            )

        # Rule 3: Verify document is still active
        document = self.canonical_db.get_document(document_id)
        if not document or document['status'] not in ['active', 'current']:
            return CitationValidationResult(
                valid=False,
                citation_number=citation_num,
                chunk_id=chunk_id,
                document_id=document_id,
                error_type=CitationValidationError.DOCUMENT_INACTIVE,
                error_message=f"Document {document_id} is not active"
            )

        # Rule 4: Revalidate user authorization
        is_authorized = self.acl_validator.can_access(
            user_context,
            db_chunk
        )

        if not is_authorized:
            return CitationValidationResult(
                valid=False,
                citation_number=citation_num,
                chunk_id=chunk_id,
                document_id=document_id,
                error_type=CitationValidationError.UNAUTHORIZED,
                error_message=f"User no longer authorized for chunk {chunk_id}"
            )

        # All validations passed
        return CitationValidationResult(
            valid=True,
            citation_number=citation_num,
            chunk_id=chunk_id,
            document_id=document_id
        )
```

### 3.3 Citation Formatting

Format validated citations for user presentation with rich metadata.

**Citation Format:**

```text
[1] Travel Expense Policy v3.2, page 8, section "Expense Claims"
[2] Finance Reimbursement Guide v2.0, page 3, section "Approval Workflow"
[3] HR Leave Policy v1.5, pages 12-13, section "Annual Leave"
```

**Formatting Implementation:**

```python
from typing import List, Dict

@dataclass
class FormattedCitation:
    """Formatted citation for UI presentation."""
    citation_number: int
    chunk_id: str
    document_id: str
    document_title: str
    document_version: str
    page_start: int
    page_end: int
    section_title: str
    source_uri: str
    formatted_text: str
    viewer_link: str = None

class CitationFormatter:
    """Format citations for user presentation."""

    def __init__(self, canonical_db):
        self.canonical_db = canonical_db

    def format_citations(
        self,
        validation_results: Dict[int, CitationValidationResult],
        context_chunks: List[dict]
    ) -> List[FormattedCitation]:
        """
        Format validated citations with metadata.

        Args:
            validation_results: Results from citation validation
            context_chunks: Original context chunks

        Returns:
            List of formatted citations
        """
        formatted_citations = []

        for citation_num, result in sorted(validation_results.items()):
            if not result.valid:
                continue  # Skip invalid citations

            # Get chunk and document metadata
            chunk = context_chunks[citation_num - 1]
            document = self.canonical_db.get_document(result.document_id)

            formatted = self._format_single_citation(
                citation_num,
                chunk,
                document
            )
            formatted_citations.append(formatted)

        return formatted_citations

    def _format_single_citation(
        self,
        citation_num: int,
        chunk: dict,
        document: dict
    ) -> FormattedCitation:
        """Format a single citation."""

        # Build page reference
        page_ref = self._format_page_reference(
            chunk.get('page_start'),
            chunk.get('page_end')
        )

        # Build section reference
        section_ref = self._format_section_reference(
            chunk.get('section_title')
        )

        # Build formatted text
        parts = [document['title']]

        if document.get('version'):
            parts.append(f"v{document['version']}")

        if page_ref:
            parts.append(page_ref)

        if section_ref:
            parts.append(section_ref)

        formatted_text = f"[{citation_num}] {', '.join(parts)}"

        # Build viewer link if available
        viewer_link = self._build_viewer_link(
            document.get('source_uri'),
            chunk.get('page_start')
        )

        return FormattedCitation(
            citation_number=citation_num,
            chunk_id=chunk['chunk_id'],
            document_id=document['document_id'],
            document_title=document['title'],
            document_version=document.get('version', ''),
            page_start=chunk.get('page_start'),
            page_end=chunk.get('page_end'),
            section_title=chunk.get('section_title', ''),
            source_uri=document.get('source_uri', ''),
            formatted_text=formatted_text,
            viewer_link=viewer_link
        )

    def _format_page_reference(self, page_start: int, page_end: int) -> str:
        """Format page reference."""
        if not page_start:
            return ""

        if not page_end or page_start == page_end:
            return f"page {page_start}"

        return f"pages {page_start}-{page_end}"

    def _format_section_reference(self, section_title: str) -> str:
        """Format section reference."""
        if not section_title:
            return ""

        return f'section "{section_title}"'

    def _build_viewer_link(self, source_uri: str, page: int) -> str:
        """Build viewer link for document navigation."""
        if not source_uri:
            return None

        # Handle different source types
        if source_uri.startswith('s3://'):
            # Generate presigned URL or internal viewer link
            return f"/viewer/document?uri={source_uri}&page={page}"

        elif source_uri.startswith('sharepoint://'):
            # SharePoint viewer link
            return f"/viewer/sharepoint?uri={source_uri}&page={page}"

        elif source_uri.startswith('confluence://'):
            # Confluence viewer link
            return f"/viewer/confluence?uri={source_uri}"

        else:
            # Generic viewer
            return f"/viewer/document?uri={source_uri}&page={page}"
```

### 3.4 Uncited Claim Detection

Attempt to detect factual claims that lack proper citations.

**Detection Strategy:**

```python
import spacy
from typing import List, Set

class UncitedClaimDetector:
    """Detect factual claims that may lack citations."""

    def __init__(self):
        # Load spaCy model for NER
        self.nlp = spacy.load("en_core_web_lg")

        # Patterns indicating factual claims
        self.claim_indicators = [
            "must", "should", "required", "mandatory",
            "approved by", "responsible for", "owned by",
            "within", "days", "weeks", "months",
            "policy states", "according to", "as per",
            "deadline", "timeline", "due date"
        ]

    def detect_uncited_claims(
        self,
        answer_text: str,
        citation_positions: List[dict]
    ) -> List[dict]:
        """
        Detect sentences with factual claims that lack citations.

        Args:
            answer_text: LLM-generated answer
            citation_positions: List of citation positions in text

        Returns:
            List of potentially uncited claims
        """
        doc = self.nlp(answer_text)
        uncited_claims = []

        for sent in doc.sents:
            # Check if sentence contains claim indicators
            has_claim_indicator = any(
                indicator in sent.text.lower()
                for indicator in self.claim_indicators
            )

            # Check if sentence has citations
            has_citation = self._sentence_has_citation(
                sent.start_char,
                sent.end_char,
                citation_positions
            )

            # Flag if claim indicator present but no citation
            if has_claim_indicator and not has_citation:
                uncited_claims.append({
                    'text': sent.text,
                    'start_pos': sent.start_char,
                    'end_pos': sent.end_char,
                    'confidence': 'medium'  # This is heuristic-based
                })

        return uncited_claims

    def _sentence_has_citation(
        self,
        sent_start: int,
        sent_end: int,
        citation_positions: List[dict]
    ) -> bool:
        """Check if sentence contains any citations."""
        for citation in citation_positions:
            if sent_start <= citation['start_pos'] <= sent_end:
                return True
        return False
```

---

## 4. Data Models

### 4.1 Input Models

```python
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class CitationValidationRequest:
    """Request to validate citations in an answer."""
    answer_text: str
    context_chunks: List[dict]
    user_context: dict
    query_id: str
    tenant_id: str

@dataclass
class ContextChunk:
    """Chunk that was in LLM context."""
    chunk_id: str
    document_id: str
    text: str
    page_start: int
    page_end: int
    section_title: str
    citation_number: int  # Position in context (1-indexed)
```

### 4.2 Output Models

```python
@dataclass
class CitationValidationResponse:
    """Response from citation validation."""
    valid: bool
    citations: List[FormattedCitation]
    validation_errors: List[CitationValidationResult]
    uncited_claims: List[dict]
    total_citations: int
    valid_citations: int
    invalid_citations: int
    citation_coverage_score: float  # 0.0 to 1.0

@dataclass
class CitationMetrics:
    """Metrics for citation quality monitoring."""
    query_id: str
    tenant_id: str
    user_id: str
    total_citations: int
    valid_citations: int
    invalid_citations: int
    fabricated_citations: int
    unauthorized_citations: int
    uncited_claims_detected: int
    citation_coverage_score: float
    validation_latency_ms: float
    timestamp: str
```

---

## 5. Integration Points

### 5.1 PostgreSQL Integration

**Required Operations:**

```python
class CanonicalDBClient:
    """Client for PostgreSQL canonical database."""

    def get_chunk(self, chunk_id: str) -> dict:
        """Retrieve chunk metadata by ID."""
        pass

    def get_document(self, document_id: str) -> dict:
        """Retrieve document metadata by ID."""
        pass

    def get_chunks_by_ids(self, chunk_ids: List[str]) -> List[dict]:
        """Batch retrieve chunks by IDs."""
        pass
```

### 5.2 ACL Validation Integration

**Required Operations:**

```python
class ACLValidator:
    """Client for ACL validation."""

    def can_access(self, user_context: dict, chunk: dict) -> bool:
        """Check if user can access chunk."""
        pass

    def filter_authorized_chunks(
        self,
        user_context: dict,
        chunk_ids: List[str]
    ) -> List[str]:
        """Filter chunks to only authorized ones."""
        pass
```

### 5.3 Audit Integration

**Audit Events:**

```python
@dataclass
class CitationAuditEvent:
    """Audit event for citation validation."""
    event_type: str = "citation_validation"
    query_id: str
    tenant_id: str
    user_id: str
    total_citations: int
    valid_citations: int
    invalid_citations: int
    validation_errors: List[dict]
    uncited_claims: List[dict]
    timestamp: str
```

---

## 6. Error Handling

### 6.1 Validation Errors

**Error Types:**

```python
class CitationError(Exception):
    """Base exception for citation errors."""
    pass

class FabricatedCitationError(CitationError):
    """Citation references non-existent chunk."""
    pass

class UnauthorizedCitationError(CitationError):
    """Citation references unauthorized chunk."""
    pass

class InvalidCitationRangeError(CitationError):
    """Citation number out of valid range."""
    pass

class InactiveCitationError(CitationError):
    """Citation references deleted/archived document."""
    pass
```

### 6.2 Error Response

```python
@dataclass
class CitationErrorResponse:
    """Response when citation validation fails."""
    error_type: str
    error_message: str
    invalid_citations: List[int]
    suggested_action: str

    def to_dict(self) -> dict:
        return {
            'error': self.error_type,
            'message': self.error_message,
            'invalid_citations': self.invalid_citations,
            'suggested_action': self.suggested_action
        }
```

### 6.3 Fallback Strategy

When citation validation fails:

1. **Log Error:** Record validation failure in audit log
2. **Remove Invalid Citations:** Strip invalid citation markers from answer
3. **Add Disclaimer:** Add warning about citation validation failure
4. **Preserve Valid Citations:** Keep citations that passed validation
5. **Notify Monitoring:** Alert observability system

```python
def handle_validation_failure(
    answer_text: str,
    validation_results: Dict[int, CitationValidationResult]
) -> str:
    """Handle citation validation failure gracefully."""

    # Identify invalid citations
    invalid_citations = [
        num for num, result in validation_results.items()
        if not result.valid
    ]

    # Remove invalid citation markers
    cleaned_answer = answer_text
    for citation_num in sorted(invalid_citations, reverse=True):
        # Remove [Source N] markers
        cleaned_answer = re.sub(
            rf'\[Source\s+{citation_num}\]',
            '',
            cleaned_answer
        )

    # Add disclaimer
    disclaimer = (
        "\n\n⚠️ Note: Some citations could not be validated. "
        "Please verify information independently."
    )

    return cleaned_answer + disclaimer
```

---

## 7. Performance Requirements

### 7.1 Latency Targets

- **Citation Extraction:** < 10ms
- **Citation Validation:** < 50ms (for up to 10 citations)
- **Citation Formatting:** < 20ms
- **Total Processing:** < 100ms

### 7.2 Optimization Strategies

**Batch Database Queries:**

```python
def validate_citations_optimized(
    self,
    citation_numbers: Set[int],
    context_chunks: List[dict],
    user_context: dict
) -> Dict[int, CitationValidationResult]:
    """Optimized validation with batch queries."""

    # Extract all chunk IDs
    chunk_ids = [chunk['chunk_id'] for chunk in context_chunks]

    # Batch fetch chunks from database
    db_chunks = self.canonical_db.get_chunks_by_ids(chunk_ids)
    chunk_map = {chunk['chunk_id']: chunk for chunk in db_chunks}

    # Extract all document IDs
    document_ids = list(set(chunk['document_id'] for chunk in db_chunks))

    # Batch fetch documents
    documents = self.canonical_db.get_documents_by_ids(document_ids)
    document_map = {doc['document_id']: doc for doc in documents}

    # Validate each citation using cached data
    results = {}
    for citation_num in citation_numbers:
        result = self._validate_with_cache(
            citation_num,
            context_chunks,
            chunk_map,
            document_map,
            user_context
        )
        results[citation_num] = result

    return results
```

**Caching:**

```python
from functools import lru_cache

class CachedCitationValidator:
    """Citation validator with caching."""

    @lru_cache(maxsize=1000)
    def get_document_cached(self, document_id: str) -> dict:
        """Get document with caching."""
        return self.canonical_db.get_document(document_id)

    @lru_cache(maxsize=5000)
    def get_chunk_cached(self, chunk_id: str) -> dict:
        """Get chunk with caching."""
        return self.canonical_db.get_chunk(chunk_id)
```

---

## 8. Security Considerations

### 8.1 Authorization Revalidation

**Critical Rule:** Always revalidate user authorization at citation validation time, not just at retrieval time.

**Rationale:**

- User permissions may have changed between retrieval and response
- Document access policies may have been updated
- Documents may have been archived or deleted

### 8.2 Citation Leakage Prevention

**Prevent Information Leakage:**

```python
def sanitize_error_message(
    error: CitationValidationResult,
    user_context: dict
) -> str:
    """Sanitize error messages to prevent information leakage."""

    if error.error_type == CitationValidationError.UNAUTHORIZED:
        # Don't reveal document title or content
        return "Some citations reference documents you don't have access to."

    elif error.error_type == CitationValidationError.DOCUMENT_INACTIVE:
        # Don't reveal that document exists but is archived
        return "Some citations reference unavailable documents."

    elif error.error_type == CitationValidationError.OUT_OF_RANGE:
        # Generic message
        return "Some citations are invalid."

    else:
        return "Citation validation failed."
```

### 8.3 Audit Trail

**Log All Validation Events:**

```python
def log_citation_validation(
    query_id: str,
    validation_results: Dict[int, CitationValidationResult],
    user_context: dict
):
    """Log citation validation for audit trail."""

    audit_event = {
        'event_type': 'citation_validation',
        'query_id': query_id,
        'tenant_id': user_context['tenant_id'],
        'user_id': user_context['user_id'],
        'timestamp': datetime.utcnow().isoformat(),
        'total_citations': len(validation_results),
        'valid_citations': sum(1 for r in validation_results.values() if r.valid),
        'invalid_citations': sum(1 for r in validation_results.values() if not r.valid),
        'validation_errors': [
            {
                'citation_number': num,
                'error_type': result.error_type.value,
                'chunk_id': result.chunk_id,
                'document_id': result.document_id
            }
            for num, result in validation_results.items()
            if not result.valid
        ]
    }

    audit_logger.log(audit_event)
```

---

## 9. Testing Strategy

### 9.1 Unit Tests

**Test Cases:**

```python
class TestCitationExtraction:
    """Test citation extraction."""

    def test_extract_source_format(self):
        """Test [Source N] format extraction."""
        text = "Policy requires approval [Source 1] within 14 days [Source 2]."
        citations = extractor.extract_citations(text)
        assert citations == {1, 2}

    def test_extract_numeric_format(self):
        """Test [N] format extraction."""
        text = "According to policy [1], employees must [2]."
        citations = extractor.extract_citations(text)
        assert citations == {1, 2}

    def test_extract_mixed_formats(self):
        """Test mixed citation formats."""
        text = "Policy [Source 1] states [2] that approval (3) is required."
        citations = extractor.extract_citations(text)
        assert citations == {1, 2, 3}

    def test_no_citations(self):
        """Test text without citations."""
        text = "This is general information without sources."
        citations = extractor.extract_citations(text)
        assert citations == set()

class TestCitationValidation:
    """Test citation validation."""

    def test_valid_citation(self):
        """Test validation of valid citation."""
        result = validator.validate_single_citation(1, context_chunks, user_context)
        assert result.valid is True
        assert result.chunk_id is not None

    def test_out_of_range_citation(self):
        """Test citation number out of range."""
        result = validator.validate_single_citation(999, context_chunks, user_context)
        assert result.valid is False
        assert result.error_type == CitationValidationError.OUT_OF_RANGE

    def test_unauthorized_citation(self):
        """Test citation to unauthorized chunk."""
        # Mock ACL to deny access
        acl_validator.can_access = Mock(return_value=False)
        result = validator.validate_single_citation(1, context_chunks, user_context)
        assert result.valid is False
        assert result.error_type == CitationValidationError.UNAUTHORIZED

    def test_inactive_document_citation(self):
        """Test citation to deleted document."""
        # Mock document as deleted
        canonical_db.get_document = Mock(return_value={'status': 'deleted'})
        result = validator.validate_single_citation(1, context_chunks, user_context)
        assert result.valid is False
        assert result.error_type == CitationValidationError.DOCUMENT_INACTIVE

class TestCitationFormatting:
    """Test citation formatting."""

    def test_format_with_page_range(self):
        """Test formatting with page range."""
        citation = formatter.format_single_citation(1, chunk, document)
        assert "pages 12-13" in citation.formatted_text

    def test_format_with_single_page(self):
        """Test formatting with single page."""
        chunk['page_end'] = chunk['page_start']
        citation = formatter.format_single_citation(1, chunk, document)
        assert "page 12" in citation.formatted_text

    def test_format_with_section(self):
        """Test formatting with section title."""
        citation = formatter.format_single_citation(1, chunk, document)
        assert 'section "Expense Claims"' in citation.formatted_text

    def test_format_with_version(self):
        """Test formatting with document version."""
        citation = formatter.format_single_citation(1, chunk, document)
        assert "v3.2" in citation.formatted_text
```

### 9.2 Integration Tests

**Test Scenarios:**

```python
class TestCitationIntegration:
    """Integration tests for citation agent."""

    def test_end_to_end_validation(self):
        """Test complete citation validation flow."""
        # Generate answer with citations
        answer = "Employees must submit expenses within 14 days [Source 1]."

        # Validate citations
        response = citation_agent.validate_and_format(
            answer,
            context_chunks,
            user_context
        )

        assert response.valid is True
        assert len(response.citations) == 1
        assert response.citations[0].citation_number == 1

    def test_fabricated_citation_detection(self):
        """Test detection of fabricated citations."""
        # Answer references non-existent source
        answer = "Policy requires approval [Source 99]."

        response = citation_agent.validate_and_format(
            answer,
            context_chunks,
            user_context
        )

        assert response.valid is False
        assert len(response.validation_errors) == 1
        assert response.validation_errors[0].error_type == CitationValidationError.OUT_OF_RANGE

    def test_unauthorized_citation_handling(self):
        """Test handling of unauthorized citations."""
        # Mock ACL to deny access to chunk 2
        acl_validator.can_access = Mock(side_effect=lambda u, c: c['chunk_id'] != 'chunk_002')

        answer = "Policy [Source 1] requires [Source 2] approval."

        response = citation_agent.validate_and_format(
            answer,
            context_chunks,
            user_context
        )

        assert response.valid is False
        assert len(response.citations) == 1  # Only valid citation
        assert response.citations[0].citation_number == 1
```

### 9.3 Security Tests

**Security Test Cases:**

```python
class TestCitationSecurity:
    """Security tests for citation validation."""

    def test_cross_tenant_citation_blocked(self):
        """Test that cross-tenant citations are blocked."""
        # Context chunk from different tenant
        context_chunks[0]['tenant_id'] = 'other-tenant'

        response = citation_agent.validate_and_format(
            "Policy states [Source 1].",
            context_chunks,
            user_context
        )

        assert response.valid is False

    def test_deleted_document_citation_blocked(self):
        """Test that deleted document citations are blocked."""
        # Mock document as deleted
        canonical_db.get_document = Mock(return_value={'status': 'deleted'})

        response = citation_agent.validate_and_format(
            "Policy states [Source 1].",
            context_chunks,
            user_context
        )

        assert response.valid is False

    def test_permission_change_detected(self):
        """Test that permission changes are detected."""
        # User had access during retrieval but not at validation time
        acl_validator.can_access = Mock(return_value=False)

        response = citation_agent.validate_and_format(
            "Policy states [Source 1].",
            context_chunks,
            user_context
        )

        assert response.valid is False
        assert any(
            e.error_type == CitationValidationError.UNAUTHORIZED
            for e in response.validation_errors
        )
```

---

## 10. Monitoring and Observability

### 10.1 Key Metrics

**Citation Quality Metrics:**

```python
# Prometheus metrics
citation_validation_total = Counter(
    'citation_validation_total',
    'Total citation validations',
    ['tenant_id', 'result']
)

citation_validation_errors = Counter(
    'citation_validation_errors',
    'Citation validation errors',
    ['tenant_id', 'error_type']
)

citation_coverage_score = Histogram(
    'citation_coverage_score',
    'Citation coverage score distribution',
    ['tenant_id'],
    buckets=[0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 0.95, 1.0]
)

fabricated_citations = Counter(
    'fabricated_citations_total',
    'Fabricated citations detected',
    ['tenant_id']
)

unauthorized_citations = Counter(
    'unauthorized_citations_total',
    'Unauthorized citations detected',
    ['tenant_id']
)

citation_validation_latency = Histogram(
    'citation_validation_latency_seconds',
    'Citation validation latency',
    ['tenant_id'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)
```

### 10.2 Alerting Rules

**Critical Alerts:**

```yaml
# High fabricated citation rate
- alert: HighFabricatedCitationRate
  expr: rate(fabricated_citations_total[5m]) > 0.1
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "High rate of fabricated citations detected"
    description: "{{ $value }} fabricated citations per second"

# High unauthorized citation rate
- alert: HighUnauthorizedCitationRate
  expr: rate(unauthorized_citations_total[5m]) > 0.05
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High rate of unauthorized citations"
    description: "Possible ACL validation issues"

# Low citation coverage
- alert: LowCitationCoverage
  expr: avg(citation_coverage_score) < 0.7
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Low citation coverage detected"
    description: "Average citation coverage below 70%"
```

### 10.3 Logging

**Structured Logging:**

```python
import structlog

logger = structlog.get_logger()

def log_citation_validation(
    query_id: str,
    validation_results: Dict[int, CitationValidationResult],
    metrics: CitationMetrics
):
    """Log citation validation with structured data."""

    logger.info(
        "citation_validation_complete",
        query_id=query_id,
        tenant_id=metrics.tenant_id,
        user_id=metrics.user_id,
        total_citations=metrics.total_citations,
        valid_citations=metrics.valid_citations,
        invalid_citations=metrics.invalid_citations,
        fabricated_citations=metrics.fabricated_citations,
        unauthorized_citations=metrics.unauthorized_citations,
        citation_coverage_score=metrics.citation_coverage_score,
        validation_latency_ms=metrics.validation_latency_ms
    )

    # Log validation errors
    for citation_num, result in validation_results.items():
        if not result.valid:
            logger.warning(
                "citation_validation_error",
                query_id=query_id,
                citation_number=citation_num,
                error_type=result.error_type.value,
                error_message=result.error_message,
                chunk_id=result.chunk_id,
                document_id=result.document_id
            )
```

---

## 11. Configuration

### 11.1 Configuration Schema

```yaml
citation_agent:
  # Citation extraction
  extraction:
    supported_formats:
      - "[Source N]"
      - "[N]"
      - "(Source N)"
      - "(N)"

  # Validation settings
  validation:
    revalidate_authorization: true
    check_document_status: true
    allow_archived_documents: false
    batch_size: 100

  # Formatting settings
  formatting:
    include_version: true
    include_page_numbers: true
    include_section_titles: true
    generate_viewer_links: true

  # Uncited claim detection
  uncited_claim_detection:
    enabled: true
    confidence_threshold: 0.6
    spacy_model: "en_core_web_lg"

  # Performance settings
  performance:
    max_citations_per_answer: 20
    validation_timeout_ms: 100
    cache_ttl_seconds: 300

  # Error handling
  error_handling:
    remove_invalid_citations: true
    add_disclaimer: true
    preserve_valid_citations: true

  # Security settings
  security:
    sanitize_error_messages: true
    log_validation_failures: true
    alert_on_fabrication: true
```

---

## 12. Deployment Considerations

### 12.1 Resource Requirements

**Compute:**

- CPU: 0.5-1 core per instance
- Memory: 512MB-1GB per instance
- Storage: Minimal (logs only)

**Dependencies:**

- PostgreSQL connection pool
- Redis for caching (optional)
- spaCy model for uncited claim detection

### 12.2 Scaling Strategy

**Horizontal Scaling:**

- Stateless service, scales horizontally
- Load balance across multiple instances
- No shared state between instances

**Caching:**

- Cache document metadata (short TTL)
- Cache chunk metadata (short TTL)
- Cache validation results (very short TTL due to authorization changes)

### 12.3 High Availability

**Redundancy:**

- Deploy multiple instances across availability zones
- Use health checks for automatic failover
- Implement circuit breakers for database calls

**Graceful Degradation:**

- If validation fails, remove invalid citations and add disclaimer
- If database unavailable, skip revalidation but log warning
- If formatting fails, return basic citation format

---

## 13. API Specification

### 13.1 REST API

**Endpoint:** `POST /api/v1/citations/validate`

**Request:**

```json
{
  "answer_text": "Employees must submit expenses within 14 days [Source 1].",
  "context_chunks": [
    {
      "chunk_id": "chunk_001",
      "document_id": "doc_001",
      "text": "...",
      "page_start": 8,
      "page_end": 8,
      "section_title": "Expense Claims",
      "citation_number": 1
    }
  ],
  "user_context": {
    "user_id": "user_123",
    "tenant_id": "global-company",
    "department": "finance"
  },
  "query_id": "query_abc123"
}
```

**Response (Success):**

```json
{
  "valid": true,
  "citations": [
    {
      "citation_number": 1,
      "chunk_id": "chunk_001",
      "document_id": "doc_001",
      "document_title": "Travel Expense Policy",
      "document_version": "v3.2",
      "page_start": 8,
      "page_end": 8,
      "section_title": "Expense Claims",
      "formatted_text": "[1] Travel Expense Policy v3.2, page 8, section \"Expense Claims\"",
      "viewer_link": "/viewer/document?uri=s3://bucket/doc_001.pdf&page=8"
    }
  ],
  "validation_errors": [],
  "uncited_claims": [],
  "metrics": {
    "total_citations": 1,
    "valid_citations": 1,
    "invalid_citations": 0,
    "citation_coverage_score": 1.0,
    "validation_latency_ms": 45
  }
}
```

**Response (Validation Errors):**

```json
{
  "valid": false,
  "citations": [],
  "validation_errors": [
    {
      "citation_number": 2,
      "error_type": "citation_number_out_of_range",
      "error_message": "Citation 2 out of range [1, 1]"
    }
  ],
  "uncited_claims": [
    {
      "text": "Approval must be obtained within 48 hours.",
      "confidence": "medium"
    }
  ],
  "metrics": {
    "total_citations": 2,
    "valid_citations": 1,
    "invalid_citations": 1,
    "citation_coverage_score": 0.5,
    "validation_latency_ms": 52
  }
}
```

---

## 14. Future Enhancements

### 14.1 Advanced Citation Features

**Inline Citation Tooltips:**

- Hover over citation to see snippet
- Click citation to navigate to source
- Show confidence score for citation

**Citation Graphs:**

- Visualize citation relationships
- Show which sources support which claims
- Identify citation clusters

**Citation Quality Scoring:**

- Score citations based on source quality
- Prefer primary sources over secondary
- Weight by document recency and authority

### 14.2 ML-Based Improvements

**Claim-Citation Matching:**

- Use ML to verify citation supports claim
- Detect mismatched citations
- Suggest better citations

**Automatic Citation Insertion:**

- Suggest citations for uncited claims
- Rank candidate sources by relevance
- Insert citations automatically with confidence scores

**Citation Style Learning:**

- Learn user/tenant citation preferences
- Adapt formatting to domain conventions
- Support multiple citation styles (APA, MLA, Chicago, etc.)

---

## 15. Compliance and Audit

### 15.1 Audit Requirements

**Citation Audit Trail:**

- Log all citation validations
- Record validation errors
- Track unauthorized citation attempts
- Monitor fabricated citations

**Compliance Reporting:**

- Citation quality reports
- Unauthorized access attempts
- Fabrication detection rates
- Coverage metrics by department/region

### 15.2 Data Retention

**Retention Policies:**

- Citation validation logs: 90 days minimum
- Validation error logs: 1 year minimum
- Fabrication alerts: 2 years minimum
- Compliance reports: Per regulatory requirements

---

## 16. Summary

The **citation-agent** is the final enforcement point for citation integrity in the Enterprise RAG system. It ensures that:

1. **All citations are valid** and reference authorized chunks
2. **No fabricated citations** reach the user
3. **Authorization is revalidated** at response time
4. **Citations are formatted** consistently with rich metadata
5. **Uncited claims are detected** where possible
6. **Audit trails are maintained** for compliance

This agent is critical for maintaining trust in the RAG system and ensuring that all answers are properly sourced and verifiable.

---

**Document Version:** 2.0  
**Last Updated:** 2026-05-17  
**Status:** Production Ready  
**Next Review:** 2026-08-17
