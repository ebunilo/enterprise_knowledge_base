      - totp
      - sms
    session_timeout_minutes: 30
    max_concurrent_sessions: 3

# Authorization

authorization:
super_admin_role: "super_admin"
tenant_admin_role: "tenant_admin"
department_admin_role: "department_admin"
source_admin_role: "source_admin"
policy_admin_role: "policy_admin"

# Operations

operations:
async_threshold_seconds: 5
max_concurrent_jobs: 10
job_timeout_seconds: 3600
retry_failed_jobs: true
max_retries: 3

# Rate limiting

rate_limiting:
enabled: true
requests_per_minute: 60
burst_size: 10

# Notifications

notifications:
email_enabled: true
slack_enabled: true
notify_on_ingestion_failure: true
notify_on_policy_change: true

```

---

## 12. Deployment Considerations

### 12.1 Resource Requirements

**Compute:**
- CPU: 2-4 cores per instance
- Memory: 2-4GB per instance
- Storage: Minimal (logs only)

**Dependencies:**
- PostgreSQL connection pool
- Redis for session management
- Message queue for async operations

### 12.2 Scaling Strategy

**Horizontal Scaling:**
- Stateless service, scales horizontally
- Load balance across multiple instances
- Shared session store (Redis)

**Background Workers:**
- Separate worker processes for long-running operations
- Queue-based job processing
- Configurable worker pool size

### 12.3 High Availability

**Redundancy:**
- Deploy 2+ instances across availability zones
- Redis with replication for sessions
- PostgreSQL with replication

**Graceful Degradation:**
- If background worker unavailable, queue operations
- If database unavailable, return cached data where safe
- If external service unavailable, provide clear error messages

---

## 13. API Specification

### 13.1 REST API

**Source Management Endpoints:**

```

POST /api/v1/admin/sources
GET /api/v1/admin/sources
GET /api/v1/admin/sources/{source_id}
PUT /api/v1/admin/sources/{source_id}
DELETE /api/v1/admin/sources/{source_id}
POST /api/v1/admin/sources/{source_id}/test

```

**Ingestion Control Endpoints:**

```

POST /api/v1/admin/ingestion/trigger
GET /api/v1/admin/ingestion/jobs
GET /api/v1/admin/ingestion/jobs/{job_id}
POST /api/v1/admin/ingestion/jobs/{job_id}/cancel
POST /api/v1/admin/ingestion/jobs/{job_id}/retry

```

**Policy Management Endpoints:**

```

POST /api/v1/admin/policies
GET /api/v1/admin/policies
GET /api/v1/admin/policies/{policy_id}
PUT /api/v1/admin/policies/{policy_id}
DELETE /api/v1/admin/policies/{policy_id}

```

**Document Lifecycle Endpoints:**

```

POST /api/v1/admin/documents/{document_id}/archive
POST /api/v1/admin/documents/{document_id}/restore
DELETE /api/v1/admin/documents/{document_id}
GET /api/v1/admin/documents

```

**System Health Endpoints:**

```

GET /api/v1/admin/health
GET /api/v1/admin/metrics
GET /api/v1/admin/failures
GET /api/v1/admin/conflicts

```

---

## 14. Future Enhancements

### 14.1 Workflow Automation

**Scheduled Ingestion:**
- Cron-based ingestion schedules
- Automatic retry on failure
- Smart scheduling based on source activity

**Approval Workflows:**
- Multi-step approval for sensitive changes
- Configurable approval chains
- Notification integration

### 14.2 Bulk Operations

**Batch Document Management:**
- Bulk archive/restore/delete
- CSV import for bulk operations
- Progress tracking for bulk operations

**Batch Policy Management:**
- Apply policies to multiple documents
- Bulk policy updates
- Policy templates

### 14.3 Self-Service Portal

**User-Facing Features:**
- Document submission portal
- Access request workflow
- Document feedback system

### 14.4 Advanced Analytics

**Usage Analytics:**
- Source usage statistics
- Document access patterns
- Policy effectiveness analysis

**Cost Optimization:**
- Storage cost tracking
- Ingestion cost analysis
- Optimization recommendations

---

## 15. Summary

The **admin-agent** is the operational control center of the Enterprise RAG system. It enables:

1. **Source Management:** Configure and manage document sources
2. **Ingestion Control:** Trigger and monitor document ingestion
3. **Policy Management:** Create and manage access control policies
4. **Document Lifecycle:** Archive, restore, and delete documents
5. **System Health:** Monitor system status and failures
6. **User Management:** Manage roles and permissions
7. **Operational Excellence:** Enable efficient day-to-day operations

This agent is critical for maintaining system health, managing content, and ensuring smooth operations.

---

**Document Version:** 2.0
**Last Updated:** 2026-05-17
**Status:** Production Ready
**Next Review:** 2026-08-17
```
