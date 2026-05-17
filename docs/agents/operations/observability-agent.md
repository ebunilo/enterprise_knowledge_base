# Observability Agent Specification

**Version:** 2.0  
**Last Updated:** 2026-05-17  
**Status:** Production Ready  
**Domain:** Operations  
**Dependencies:** All RAG pipeline agents

---

## 1. Purpose

The **observability-agent** tracks metrics, traces, logs, and system health for performance monitoring and alerting. This agent enables proactive incident detection, performance optimization, capacity planning, and SLA compliance monitoring.

### Key Responsibilities

1. **Metrics Collection:** Collect performance and business metrics from all agents
2. **Distributed Tracing:** Implement end-to-end request tracing
3. **Log Aggregation:** Centralize logs from all services
4. **Alerting:** Define and evaluate alert rules
5. **Dashboards:** Provide pre-built and custom dashboards
6. **Health Monitoring:** Track system component health
7. **SLA Monitoring:** Monitor and report SLA compliance
8. **Performance Analysis:** Enable performance debugging and optimization

---

## 2. System Context

### Position in System Architecture

```text
All RAG Agents
   ↓
[OBSERVABILITY AGENT]
   ├─ Metrics → Prometheus
   ├─ Traces → Jaeger
   ├─ Logs → Loki
   └─ Alerts → Alertmanager
   ↓
Grafana Dashboards
Alert Notifications
```

### Input Sources

- **All RAG Agents:** Metrics, traces, logs
- **Infrastructure:** System metrics (CPU, memory, disk, network)
- **Databases:** PostgreSQL, Qdrant, OpenSearch, Neo4j metrics
- **External Services:** OpenAI, Anthropic API metrics

### Output Consumers

- **Operations Team:** Dashboards, alerts, reports
- **Development Team:** Performance metrics, traces, logs
- **Management:** SLA reports, capacity planning
- **Audit Agent:** Observability data for compliance

---

## 3. Core Functionality

### 3.1 Metrics Collection

Collect comprehensive metrics from all system components.

**Metric Categories:**

```python
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional
from prometheus_client import Counter, Histogram, Gauge, Summary

class MetricType(Enum):
    """Types of metrics."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"

class MetricCategory(Enum):
    """Categories of metrics."""
    PERFORMANCE = "performance"
    BUSINESS = "business"
    QUALITY = "quality"
    SECURITY = "security"
    INFRASTRUCTURE = "infrastructure"

@dataclass
class MetricDefinition:
    """Definition of a metric."""
    name: str
    type: MetricType
    category: MetricCategory
    description: str
    labels: List[str]
    unit: Optional[str] = None
    buckets: Optional[List[float]] = None  # For histograms
```

**Core Metrics:**

```python
from prometheus_client import Counter, Histogram, Gauge

# Query metrics
query_requests_total = Counter(
    'query_requests_total',
    'Total query requests',
    ['tenant_id', 'status']
)

query_latency_seconds = Histogram(
    'query_latency_seconds',
    'Query latency in seconds',
    ['tenant_id'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
)

# Retrieval metrics
retrieval_latency_seconds = Histogram(
    'retrieval_latency_seconds',
    'Retrieval latency by source',
    ['tenant_id', 'source'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5]
)

vector_search_latency_seconds = Histogram(
    'vector_search_latency_seconds',
    'Vector search latency',
    ['tenant_id'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

bm25_search_latency_seconds = Histogram(
    'bm25_search_latency_seconds',
    'BM25 search latency',
    ['tenant_id'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

graph_search_latency_seconds = Histogram(
    'graph_search_latency_seconds',
    'Knowledge graph search latency',
    ['tenant_id'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5]
)

# ACL validation metrics
acl_validation_latency_seconds = Histogram(
    'acl_validation_latency_seconds',
    'ACL validation latency',
    ['tenant_id'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25]
)

unauthorized_access_attempts_total = Counter(
    'unauthorized_access_attempts_total',
    'Unauthorized access attempts',
    ['tenant_id', 'user_id', 'classification']
)

# Reranking metrics
reranker_latency_seconds = Histogram(
    'reranker_latency_seconds',
    'Reranker latency',
    ['tenant_id', 'reranker_type'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

# LLM metrics
llm_latency_seconds = Histogram(
    'llm_latency_seconds',
    'LLM generation latency',
    ['tenant_id', 'model', 'provider'],
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 30.0]
)

llm_tokens_consumed_total = Counter(
    'llm_tokens_consumed_total',
    'Total LLM tokens consumed',
    ['tenant_id', 'model', 'provider', 'token_type']
)

llm_api_errors_total = Counter(
    'llm_api_errors_total',
    'LLM API errors',
    ['tenant_id', 'model', 'provider', 'error_type']
)

# Citation metrics
citation_validation_failures_total = Counter(
    'citation_validation_failures_total',
    'Citation validation failures',
    ['tenant_id', 'error_type']
)

fabricated_citations_total = Counter(
    'fabricated_citations_total',
    'Fabricated citations detected',
    ['tenant_id']
)

citation_coverage_score = Histogram(
    'citation_coverage_score',
    'Citation coverage score distribution',
    ['tenant_id'],
    buckets=[0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 0.95, 1.0]
)

# Quality metrics
empty_answer_rate = Gauge(
    'empty_answer_rate',
    'Rate of empty answers',
    ['tenant_id']
)

insufficient_context_rate = Gauge(
    'insufficient_context_rate',
    'Rate of insufficient context',
    ['tenant_id']
)

uncited_claim_rate = Gauge(
    'uncited_claim_rate',
    'Rate of uncited claims',
    ['tenant_id']
)

# Ingestion metrics
ingestion_failure_rate = Gauge(
    'ingestion_failure_rate',
    'Ingestion failure rate',
    ['tenant_id', 'source_type']
)

embedding_failure_rate = Gauge(
    'embedding_failure_rate',
    'Embedding generation failure rate',
    ['tenant_id']
)

documents_ingested_total = Counter(
    'documents_ingested_total',
    'Total documents ingested',
    ['tenant_id', 'source_id', 'status']
)

chunks_created_total = Counter(
    'chunks_created_total',
    'Total chunks created',
    ['tenant_id', 'source_id']
)

# Infrastructure metrics
database_connection_pool_size = Gauge(
    'database_connection_pool_size',
    'Database connection pool size',
    ['database', 'pool']
)

database_query_latency_seconds = Histogram(
    'database_query_latency_seconds',
    'Database query latency',
    ['database', 'operation'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
)

cache_hit_rate = Gauge(
    'cache_hit_rate',
    'Cache hit rate',
    ['cache_name']
)

# Business metrics
active_users_total = Gauge(
    'active_users_total',
    'Number of active users',
    ['tenant_id', 'time_window']
)

queries_per_user = Histogram(
    'queries_per_user',
    'Queries per user distribution',
    ['tenant_id'],
    buckets=[1, 5, 10, 25, 50, 100, 250, 500]
)

user_satisfaction_score = Histogram(
    'user_satisfaction_score',
    'User satisfaction score (1-5)',
    ['tenant_id'],
    buckets=[1, 2, 3, 4, 5]
)
```

### 3.2 Distributed Tracing

Implement end-to-end request tracing using OpenTelemetry.

**Trace Implementation:**

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from typing import Dict, Any

class DistributedTracer:
    """Distributed tracing implementation."""

    def __init__(self, service_name: str, jaeger_endpoint: str):
        # Set up tracer provider
        trace.set_tracer_provider(TracerProvider())

        # Configure Jaeger exporter
        jaeger_exporter = JaegerExporter(
            agent_host_name=jaeger_endpoint.split(':')[0],
            agent_port=int(jaeger_endpoint.split(':')[1])
        )

        # Add span processor
        trace.get_tracer_provider().add_span_processor(
            BatchSpanProcessor(jaeger_exporter)
        )

        # Get tracer
        self.tracer = trace.get_tracer(service_name)

        # Auto-instrument libraries
        RequestsInstrumentor().instrument()
        Psycopg2Instrumentor().instrument()

    def start_span(
        self,
        name: str,
        attributes: Dict[str, Any] = None
    ):
        """Start a new span."""
        span = self.tracer.start_span(name)

        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)

        return span

    def trace_query(self, query_id: str, tenant_id: str, user_id: str):
        """Create trace for RAG query."""
        with self.tracer.start_as_current_span(
            "rag_query",
            attributes={
                "query_id": query_id,
                "tenant_id": tenant_id,
                "user_id": user_id
            }
        ) as query_span:
            return query_span

    def trace_retrieval(self, query_id: str, retrieval_type: str):
        """Create trace for retrieval operation."""
        with self.tracer.start_as_current_span(
            f"retrieval_{retrieval_type}",
            attributes={
                "query_id": query_id,
                "retrieval_type": retrieval_type
            }
        ) as retrieval_span:
            return retrieval_span

    def trace_llm_call(self, query_id: str, model: str, provider: str):
        """Create trace for LLM call."""
        with self.tracer.start_as_current_span(
            "llm_generation",
            attributes={
                "query_id": query_id,
                "model": model,
                "provider": provider
            }
        ) as llm_span:
            return llm_span

    def add_event(self, span, name: str, attributes: Dict[str, Any] = None):
        """Add event to span."""
        span.add_event(name, attributes=attributes)

    def set_error(self, span, error: Exception):
        """Mark span as error."""
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(error)))
        span.record_exception(error)
```

**Trace Context Propagation:**

```python
from opentelemetry.propagate import inject, extract
from typing import Dict

class TraceContextPropagator:
    """Propagate trace context across services."""

    @staticmethod
    def inject_context(headers: Dict[str, str]) -> Dict[str, str]:
        """Inject trace context into headers."""
        inject(headers)
        return headers

    @staticmethod
    def extract_context(headers: Dict[str, str]):
        """Extract trace context from headers."""
        return extract(headers)
```

### 3.3 Log Aggregation

Centralize logs from all services using structured logging.

**Structured Logging:**

```python
import structlog
from typing import Dict, Any

class StructuredLogger:
    """Structured logging implementation."""

    def __init__(self, service_name: str):
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        self.logger = structlog.get_logger(service_name)

    def log_query_event(
        self,
        query_id: str,
        tenant_id: str,
        user_id: str,
        event: str,
        **kwargs
    ):
        """Log query event."""
        self.logger.info(
            event,
            query_id=query_id,
            tenant_id=tenant_id,
            user_id=user_id,
            **kwargs
        )

    def log_error(
        self,
        error_type: str,
        error_message: str,
        **kwargs
    ):
        """Log error."""
        self.logger.error(
            "error_occurred",
            error_type=error_type,
            error_message=error_message,
            **kwargs
        )

    def log_performance(
        self,
        operation: str,
        latency_ms: float,
        **kwargs
    ):
        """Log performance metric."""
        self.logger.info(
            "performance_metric",
            operation=operation,
            latency_ms=latency_ms,
            **kwargs
        )
```

### 3.4 Alerting

Define and evaluate alert rules.

**Alert Rules:**

```python
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

class AlertSeverity(Enum):
    """Alert severity levels."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"

class AlertState(Enum):
    """Alert states."""
    FIRING = "firing"
    RESOLVED = "resolved"
    PENDING = "pending"

@dataclass
class AlertRule:
    """Alert rule definition."""
    rule_id: str
    name: str
    description: str
    severity: AlertSeverity

    # Rule expression (PromQL)
    expression: str

    # Evaluation
    evaluation_interval_seconds: int
    for_duration_seconds: int

    # Notification
    notification_channels: List[str]

    # Metadata
    labels: Dict[str, str]
    annotations: Dict[str, str]

    # State
    state: AlertState
    active: bool

# Pre-defined alert rules
ALERT_RULES = [
    AlertRule(
        rule_id="high_query_latency",
        name="High Query Latency",
        description="Query latency exceeds threshold",
        severity=AlertSeverity.WARNING,
        expression='histogram_quantile(0.95, rate(query_latency_seconds_bucket[5m])) > 5',
        evaluation_interval_seconds=60,
        for_duration_seconds=300,
        notification_channels=["slack", "email"],
        labels={"component": "rag_pipeline"},
        annotations={"summary": "Query latency p95 > 5s"},
        state=AlertState.RESOLVED,
        active=True
    ),
    AlertRule(
        rule_id="high_error_rate",
        name="High Error Rate",
        description="Error rate exceeds threshold",
        severity=AlertSeverity.CRITICAL,
        expression='rate(query_requests_total{status="error"}[5m]) > 0.05',
        evaluation_interval_seconds=60,
        for_duration_seconds=300,
        notification_channels=["pagerduty", "slack"],
        labels={"component": "rag_pipeline"},
        annotations={"summary": "Error rate > 5%"},
        state=AlertState.RESOLVED,
        active=True
    ),
    AlertRule(
        rule_id="unauthorized_access_spike",
        name="Unauthorized Access Spike",
        description="Spike in unauthorized access attempts",
        severity=AlertSeverity.CRITICAL,
        expression='rate(unauthorized_access_attempts_total[5m]) > 0.1',
        evaluation_interval_seconds=60,
        for_duration_seconds=300,
        notification_channels=["security_team", "slack"],
        labels={"component": "security"},
        annotations={"summary": "Possible security incident"},
        state=AlertState.RESOLVED,
        active=True
    ),
    AlertRule(
        rule_id="high_llm_error_rate",
        name="High LLM Error Rate",
        description="LLM API error rate exceeds threshold",
        severity=AlertSeverity.WARNING,
        expression='rate(llm_api_errors_total[5m]) > 0.02',
        evaluation_interval_seconds=60,
        for_duration_seconds=300,
        notification_channels=["slack", "email"],
        labels={"component": "llm_gateway"},
        annotations={"summary": "LLM API errors > 2%"},
        state=AlertState.RESOLVED,
        active=True
    ),
    AlertRule(
        rule_id="low_citation_coverage",
        name="Low Citation Coverage",
        description="Citation coverage below threshold",
        severity=AlertSeverity.WARNING,
        expression='avg(citation_coverage_score) < 0.7',
        evaluation_interval_seconds=300,
        for_duration_seconds=600,
        notification_channels=["slack"],
        labels={"component": "quality"},
        annotations={"summary": "Citation coverage < 70%"},
        state=AlertState.RESOLVED,
        active=True
    ),
    AlertRule(
        rule_id="high_ingestion_failure_rate",
        name="High Ingestion Failure Rate",
        description="Ingestion failure rate exceeds threshold",
        severity=AlertSeverity.WARNING,
        expression='ingestion_failure_rate > 0.1',
        evaluation_interval_seconds=300,
        for_duration_seconds=600,
        notification_channels=["slack", "email"],
        labels={"component": "ingestion"},
        annotations={"summary": "Ingestion failures > 10%"},
        state=AlertState.RESOLVED,
        active=True
    )
]
```

### 3.5 Dashboards

Provide pre-built Grafana dashboards.

**Dashboard Definitions:**

```python
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class Dashboard:
    """Dashboard definition."""
    dashboard_id: str
    title: str
    description: str
    tags: List[str]
    panels: List[Dict]

# Pre-built dashboards
DASHBOARDS = {
    "rag_overview": Dashboard(
        dashboard_id="rag_overview",
        title="RAG System Overview",
        description="High-level overview of RAG system health and performance",
        tags=["rag", "overview"],
        panels=[
            {
                "title": "Query Rate",
                "type": "graph",
                "query": "rate(query_requests_total[5m])",
                "legend": "Queries/sec"
            },
            {
                "title": "Query Latency (p95)",
                "type": "graph",
                "query": "histogram_quantile(0.95, rate(query_latency_seconds_bucket[5m]))",
                "legend": "Latency (s)"
            },
            {
                "title": "Error Rate",
                "type": "graph",
                "query": "rate(query_requests_total{status='error'}[5m])",
                "legend": "Errors/sec"
            },
            {
                "title": "Active Users",
                "type": "stat",
                "query": "active_users_total",
                "legend": "Users"
            }
        ]
    ),
    "retrieval_performance": Dashboard(
        dashboard_id="retrieval_performance",
        title="Retrieval Performance",
        description="Detailed retrieval performance metrics",
        tags=["retrieval", "performance"],
        panels=[
            {
                "title": "Vector Search Latency",
                "type": "graph",
                "query": "histogram_quantile(0.95, rate(vector_search_latency_seconds_bucket[5m]))",
                "legend": "p95 latency (s)"
            },
            {
                "title": "BM25 Search Latency",
                "type": "graph",
                "query": "histogram_quantile(0.95, rate(bm25_search_latency_seconds_bucket[5m]))",
                "legend": "p95 latency (s)"
            },
            {
                "title": "Graph Search Latency",
                "type": "graph",
                "query": "histogram_quantile(0.95, rate(graph_search_latency_seconds_bucket[5m]))",
                "legend": "p95 latency (s)"
            }
        ]
    ),
    "quality_metrics": Dashboard(
        dashboard_id="quality_metrics",
        title="Quality Metrics",
        description="RAG quality and citation metrics",
        tags=["quality", "citations"],
        panels=[
            {
                "title": "Citation Coverage",
                "type": "graph",
                "query": "avg(citation_coverage_score)",
                "legend": "Coverage score"
            },
            {
                "title": "Fabricated Citations",
                "type": "graph",
                "query": "rate(fabricated_citations_total[5m])",
                "legend": "Fabrications/sec"
            },
            {
                "title": "Insufficient Context Rate",
                "type": "graph",
                "query": "insufficient_context_rate",
                "legend": "Rate"
            }
        ]
    ),
    "security_monitoring": Dashboard(
        dashboard_id="security_monitoring",
        title="Security Monitoring",
        description="Security events and access control",
        tags=["security", "access_control"],
        panels=[
            {
                "title": "Unauthorized Access Attempts",
                "type": "graph",
                "query": "rate(unauthorized_access_attempts_total[5m])",
                "legend": "Attempts/sec"
            },
            {
                "title": "Access Denied by Classification",
                "type": "pie",
                "query": "sum by (classification) (unauthorized_access_attempts_total)",
                "legend": "By classification"
            }
        ]
    )
}
```

---

## 4. Data Models

### 4.1 Metric Models

```python
@dataclass
class MetricSample:
    """Single metric sample."""
    metric_name: str
    value: float
    labels: Dict[str, str]
    timestamp: float

@dataclass
class MetricQuery:
    """Query for metrics."""
    query: str
    start_time: float
    end_time: float
    step: Optional[int] = None
```

### 4.2 Trace Models

```python
@dataclass
class Span:
    """Trace span."""
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    operation_name: str
    start_time: float
    duration_ms: float
    tags: Dict[str, Any]
    logs: List[Dict]

@dataclass
class Trace:
    """Complete trace."""
    trace_id: str
    spans: List[Span]
    duration_ms: float
    service_count: int
```

---

## 5. Integration Points

### 5.1 Prometheus Integration

**Metrics Export:**

```python
from prometheus_client import start_http_server, REGISTRY

class PrometheusExporter:
    """Export metrics to Prometheus."""

    def __init__(self, port: int = 9090):
        self.port = port

    def start(self):
        """Start Prometheus HTTP server."""
        start_http_server(self.port, registry=REGISTRY)

    def register_custom_collector(self, collector):
        """Register custom metric collector."""
        REGISTRY.register(collector)
```

### 5.2 Jaeger Integration

**Trace Export:**

```python
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

class JaegerTraceExporter:
    """Export traces to Jaeger."""

    def __init__(self, agent_host: str, agent_port: int):
        self.exporter = JaegerExporter(
            agent_host_name=agent_host,
            agent_port=agent_port
        )

    def export_spans(self, spans):
        """Export spans to Jaeger."""
        self.exporter.export(spans)
```

### 5.3 Loki Integration

**Log Export:**

```python
import logging
from logging_loki import LokiHandler

class LokiLogExporter:
    """Export logs to Loki."""

    def __init__(self, loki_url: str, labels: Dict[str, str]):
        self.handler = LokiHandler(
            url=loki_url,
            tags=labels,
            version="1"
        )

        # Configure root logger
        logging.root.addHandler(self.handler)
        logging.root.setLevel(logging.INFO)
```

---

## 6. Error Handling

### 6.1 Error Types

```python
class ObservabilityError(Exception):
    """Base exception for observability errors."""
    pass

class MetricCollectionError(ObservabilityError):
    """Error collecting metrics."""
    pass

class TraceExportError(ObservabilityError):
    """Error exporting traces."""
    pass

class AlertEvaluationError(ObservabilityError):
    """Error evaluating alert rules."""
    pass
```

### 6.2 Fallback Strategy

When observability fails:

1. **Log Error:** Record observability failure
2. **Continue Operation:** Do not block application
3. **Buffer Data:** Buffer metrics/traces temporarily
4. **Retry:** Attempt retry with exponential backoff
5. **Alert:** Notify operations team

---

## 7. Performance Requirements

### 7.1 Overhead Targets

- **Metric Collection:** <10ms overhead per operation
- **Trace Creation:** <5ms overhead per span
- **Log Writing:** <1ms overhead per log entry
- **Alert Evaluation:** <100ms per rule

### 7.2 Sampling Strategy

**Trace Sampling:**

```python
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ParentBased

class AdaptiveSampler:
    """Adaptive trace sampling."""

    def __init__(self, default_rate: float = 0.1):
        self.default_rate = default_rate
        self.sampler = ParentBased(
            root=TraceIdRatioBased(default_rate)
        )

    def should_sample(self, trace_id: str, attributes: Dict) -> bool:
        """Determine if trace should be sampled."""
        # Always sample errors
        if attributes.get('error'):
            return True

        # Always sample slow requests
        if attributes.get('latency_ms', 0) > 5000:
            return True

        # Use default sampling for others
        return self.sampler.should_sample(trace_id, attributes)
```

---

## 8. Security Considerations

### 8.1 Metric Sanitization

**Remove Sensitive Data:**

```python
class MetricSanitizer:
    """Sanitize metrics to remove sensitive data."""

    SENSITIVE_LABELS = ['user_email', 'api_key', 'password']

    @classmethod
    def sanitize_labels(cls, labels: Dict[str, str]) -> Dict[str, str]:
        """Remove sensitive labels."""
        return {
            k: v for k, v in labels.items()
            if k not in cls.SENSITIVE_LABELS
        }
```

### 8.2 Dashboard Access Control

**Role-Based Dashboard Access:**

```python
class DashboardAccessControl:
    """Control access to dashboards."""

    @staticmethod
    def can_access_dashboard(
        user_context: Dict,
        dashboard_id: str
    ) -> bool:
        """Check if user can access dashboard."""
        user_role = user_context.get('role')

        # Super admin can access all dashboards
        if user_role == 'super_admin':
            return True

        # Security dashboards require security role
        if dashboard_id.startswith('security_'):
            return user_role in ['security_analyst', 'super_admin']

        # Operations dashboards require ops role
        if dashboard_id.startswith('ops_'):
            return user_role in ['ops_engineer', 'super_admin']

        # Default: allow access
        return True
```

---

## 9. Testing Strategy

### 9.1 Unit Tests

**Test Cases:**

```python
class TestMetricsCollection:
    """Test metrics collection."""

    def test_counter_increment(self):
        """Test counter increments correctly."""
        initial = query_requests_total._value.get()
        query_requests_total.labels(tenant_id='test', status='success').inc()
        assert query_requests_total._value.get() > initial

    def test_histogram_observe(self):
        """Test histogram observes values."""
        query_latency_seconds.labels(tenant_id='test').observe(1.5)
        # Verify histogram bucket counts

class TestDistributedTracing:
    """Test distributed tracing."""

    def test_span_creation(self):
        """Test span creation."""
        tracer = DistributedTracer('test_service', 'localhost:6831')
        with tracer.start_span('test_operation') as span:
            assert span is not None
            assert span.name == 'test_operation'

    def test_trace_context_propagation(self):
        """Test trace context propagation."""
        headers = {}
        TraceContextPropagator.inject_context(headers)
        assert 'traceparent' in headers
```

### 9.2 Integration Tests

**Test Scenarios:**

```python
class TestObservabilityIntegration:
    """Integration tests for observability."""

    def test_end_to_end_tracing(self):
        """Test complete trace through RAG pipeline."""
        # Execute query
        response = rag_orchestrator.process_query(
            query="What is the policy?",
            user_context=user_context
        )

        # Verify trace created
        traces = jaeger_client.get_traces(
            service='rag_orchestrator',
            operation='rag_query',
            limit=1
        )

        assert len(traces) == 1
        trace = traces[0]

        # Verify all expected spans present
        span_names = [span.operation_name for span in trace.spans]
        assert 'query_understanding' in span_names
        assert 'hybrid_retrieval' in span_names
        assert 'llm_generation' in span_names

    def test_alert_firing(self):
        """Test alert fires when threshold exceeded."""
        # Simulate high error rate
        for _ in range(100):
            query_requests_total.labels(
                tenant_id='test',
                status='error'
            ).inc()

        # Wait for alert evaluation
        time.sleep(70)

        # Verify alert fired
        alerts = alertmanager_client.get_alerts(
            rule_name='high_error_rate'
        )
        assert len(alerts) > 0
        assert alerts[0].state == AlertState.FIRING
```

---

## 10. Monitoring and Observability

### 10.1 Self-Monitoring

**Monitor the Monitoring System:**

```python
# Observability system metrics
observability_metric_collection_errors_total = Counter(
    'observability_metric_collection_errors_total',
    'Metric collection errors'
)

observability_trace_export_errors_total = Counter(
    'observability_trace_export_errors_total',
    'Trace export errors'
)

observability_alert_evaluation_errors_total = Counter(
    'observability_alert_evaluation_errors_total',
    'Alert evaluation errors'
)
```

### 10.2 Health Checks

**Observability Health:**

```python
class ObservabilityHealthCheck:
    """Health check for observability system."""

    def check_prometheus(self) -> bool:
        """Check Prometheus connectivity."""
        try:
            response = requests.get(f"{prometheus_url}/-/healthy")
            return response.status_code == 200
        except:
            return False

    def check_jaeger(self) -> bool:
        """Check Jaeger connectivity."""
        try:
            response = requests.get(f"{jaeger_url}/api/services")
            return response.status_code == 200
        except:
            return False

    def check_loki(self) -> bool:
        """Check Loki connectivity."""
        try:
            response = requests.get(f"{loki_url}/ready")
            return response.status_code == 200
        except:
            return False

    def overall_health(self) -> Dict:
        """Get overall observability health."""
        return {
            'prometheus': self.check_prometheus(),
            'jaeger': self.check_jaeger(),
            'loki': self.check_loki()
        }
```

---

## 11. Configuration

### 11.1 Configuration Schema

```yaml
observability_agent:
  # Metrics configuration
  metrics:
    provider: prometheus
    scrape_interval_seconds: 15
    retention_days: 15
    remote_write_enabled: false

  # Tracing configuration
  tracing:
    provider: jaeger
    sampling_rate: 0.1
    adaptive_sampling: true
    max_spans_per_trace: 1000

  # Logging configuration
  logging:
    provider: loki
    retention_days: 30
    log_level: INFO
    structured_logging: true

  # Alerting configuration
  alerting:
    provider: alertmanager
    evaluation_interval_seconds: 60
    notification_channels:
      - slack
      - email
      - pagerduty

  # Dashboards
  dashboards:
    provider: grafana
    auto_provision: true
    default_refresh_interval_seconds: 30
```

---

## 12. Deployment Considerations

### 12.1 Resource Requirements

**Compute:**

- CPU: 2-4 cores per instance
- Memory: 4-8GB per instance

**Storage:**

- Prometheus: 50GB+ for metrics
- Jaeger: 100GB+ for traces
- Loki: 100GB+ for logs

### 12.2 Scaling Strategy

**Horizontal Scaling:**

- Prometheus federation for multi-cluster
- Jaeger with Cassandra/Elasticsearch backend
- Loki with object storage backend

### 12.3 High Availability

**Redundancy:**

- Deploy Prometheus with Thanos for HA
- Deploy Jaeger with replicated backend
- Deploy Loki with replication

---

## 13. Summary

The **observability-agent** provides comprehensive monitoring and alerting for the Enterprise RAG system. It enables:

1. **Performance Monitoring:** Track latency, throughput, and errors
2. **Distributed Tracing:** Debug complex request flows
3. **Log Aggregation:** Centralize logs for analysis
4. **Alerting:** Proactive incident detection
5. **Dashboards:** Visualize system health
6. **SLA Monitoring:** Track and report compliance
7. **Capacity Planning:** Inform infrastructure decisions
8. **Quality Tracking:** Monitor RAG quality metrics

This agent is critical for maintaining system reliability, performance, and quality.

---

**Document Version:** 2.0  
**Last Updated:** 2026-05-17  
**Status:** Production Ready  
**Next Review:** 2026-08-17
