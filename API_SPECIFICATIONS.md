# Clinical RAG System - API Specifications

## API Overview

Base URL: `https://api.clinical-rag.example.com/v1`

Authentication: Bearer token (JWT)

Rate Limiting: 100 requests/minute per user

## Authentication

### POST /auth/login

Request:
```json
{
  "username": "dr.smith@hospital.com",
  "password": "secure_password",
  "mfa_token": "123456"
}
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "...",
  "expires_in": 3600,
  "token_type": "Bearer",
  "user": {
    "user_id": "[USER_xyz]",
    "role": "physician",
    "permissions": ["read:patient_records", "query:clinical_data"]
  }
}
```

---

## Query API

### POST /query

Primary endpoint for asking clinical questions.

Request:
```json
{
  "query": "What medications was the patient on at discharge?",
  "patient_id": "PATIENT_12345",
  "context": {
    "date_range": {
      "start": "2026-01-01",
      "end": "2026-01-31"
    },
    "document_types": ["discharge_summary", "progress_note"],
    "priority": "accuracy"  // or "speed"
  },
  "options": {
    "use_cache": true,
    "max_retries": 2,
    "confidence_threshold": 0.7,
    "return_sources": true
  }
}
```

Response (Success):
```json
{
  "query_id": "qry_abc123",
  "status": "success",
  "answer": "Based on the discharge summary dated 2026-01-20, the patient was prescribed five medications at discharge:\n\n1. Aspirin 81mg daily\n2. Clopidogrel 75mg daily\n3. Atorvastatin 80mg daily\n4. Metoprolol 25mg twice daily\n5. Lisinopril 10mg daily\n\nThese medications are standard post-myocardial infarction therapy.",
  "confidence": 0.92,
  "sources": [
    {
      "document_id": "doc_001",
      "document_type": "discharge_summary",
      "date": "2026-01-20",
      "section": "MEDICATIONS",
      "relevance_score": 0.95,
      "excerpt": "MEDICATIONS ON DISCHARGE:\n- Aspirin 81mg daily\n- Clopidogrel 75mg daily..."
    }
  ],
  "metadata": {
    "query_type": "factual_lookup",
    "retrieval_method": "hybrid",
    "cache_hit": false,
    "latency_ms": 450,
    "documents_retrieved": 5,
    "retry_count": 0
  },
  "timestamp": "2026-06-08T12:34:56.789Z"
}
```

Response (Low Confidence):
```json
{
  "query_id": "qry_abc456",
  "status": "low_confidence",
  "answer": "I was unable to find confident information about this query in the available records. This may be because:\n- The information is not documented in the retrieved records\n- The query requires information not available in the current context\n- Additional clarification may be needed",
  "confidence": 0.55,
  "sources": [],
  "metadata": {
    "query_type": "multi_hop",
    "retrieval_method": "hybrid",
    "cache_hit": false,
    "latency_ms": 1250,
    "documents_retrieved": 15,
    "retry_count": 2
  },
  "suggestions": [
    "Try narrowing the date range",
    "Specify which aspect of the query is most important",
    "Check if the information exists in paper records"
  ],
  "timestamp": "2026-06-08T12:35:10.123Z"
}
```

Response (Error):
```json
{
  "query_id": "qry_abc789",
  "status": "error",
  "error": {
    "code": "PII_DETECTED",
    "message": "The query or generated response contained protected health information that could not be properly de-identified. Please rephrase your query.",
    "severity": "critical"
  },
  "timestamp": "2026-06-08T12:36:00.000Z"
}
```

Error Codes:
- `AUTHENTICATION_FAILED`: Invalid or expired token
- `AUTHORIZATION_FAILED`: User lacks permission to access patient
- `PATIENT_NOT_FOUND`: Patient ID not found in system
- `INVALID_REQUEST`: Malformed request
- `PII_DETECTED`: PII leakage detected (critical)
- `RATE_LIMIT_EXCEEDED`: Too many requests
- `INTERNAL_ERROR`: Server error

---

## Document Ingestion API

### POST /documents/ingest

Ingest new clinical documents.

Request (Multipart form):
```
POST /documents/ingest
Content-Type: multipart/form-data

{
  "file": <binary file data>,
  "patient_id": "PATIENT_12345",
  "document_type": "discharge_summary",
  "document_date": "2026-01-20",
  "metadata": {
    "provider_id": "PROVIDER_001",
    "encounter_id": "ENC_789",
    "facility": "General Hospital"
  }
}
```

Response:
```json
{
  "document_id": "doc_001",
  "version": 1,
  "status": "ingested",
  "processing": {
    "pii_detected": true,
    "pii_entities_count": 5,
    "chunks_created": 12,
    "embeddings_generated": 12,
    "indexed": true
  },
  "metadata": {
    "patient_id": "[PATIENT_a3f7]",
    "document_type": "discharge_summary",
    "date": "2026-01-20"
  },
  "cache_invalidation": {
    "entries_invalidated": 3,
    "patient_id": "[PATIENT_a3f7]"
  },
  "timestamp": "2026-06-08T12:40:00.000Z"
}
```

### POST /documents/update

Update existing document (creates new version).

Request:
```json
{
  "document_id": "doc_001",
  "change_reason": "Corrected medication dosage",
  "file": "<base64 encoded file or multipart>",
  "metadata": {
    "modified_by": "PROVIDER_001",
    "modification_date": "2026-01-21"
  }
}
```

Response:
```json
{
  "document_id": "doc_001",
  "version": 2,
  "parent_version": 1,
  "status": "updated",
  "change_reason": "Corrected medication dosage",
  "processing": {
    "chunks_created": 12,
    "embeddings_generated": 12,
    "previous_version_archived": true
  },
  "cache_invalidation": {
    "entries_invalidated": 5,
    "patient_id": "[PATIENT_a3f7]"
  },
  "timestamp": "2026-06-08T14:20:00.000Z"
}
```

### GET /documents/{document_id}

Retrieve document metadata and content.

Query Parameters:
- `version`: Specific version (default: latest)
- `include_content`: Boolean (default: false)

Response:
```json
{
  "document_id": "doc_001",
  "version": 2,
  "status": "active",
  "patient_id": "[PATIENT_a3f7]",
  "document_type": "discharge_summary",
  "date": "2026-01-20",
  "content": "...",  // if include_content=true
  "metadata": {
    "provider_id": "[PROVIDER_xyz]",
    "facility": "General Hospital",
    "created_at": "2026-01-20T16:30:00Z",
    "modified_at": "2026-01-21T14:20:00Z",
    "chunks_count": 12
  },
  "versions": [
    {"version": 1, "status": "archived", "created_at": "2026-01-20T16:30:00Z"},
    {"version": 2, "status": "active", "created_at": "2026-01-21T14:20:00Z"}
  ]
}
```

---

## Structured Query API

### POST /query/structured

Query structured clinical data (FHIR resources).

Request:
```json
{
  "patient_id": "PATIENT_12345",
  "resource_type": "MedicationStatement",
  "filters": {
    "status": "active",
    "date_range": {
      "start": "2026-01-01",
      "end": "2026-01-31"
    }
  },
  "fields": ["medication", "dosage", "status", "effectiveDateTime"],
  "format": "fhir"  // or "simplified"
}
```

Response (Simplified format):
```json
{
  "query_id": "sqry_xyz123",
  "status": "success",
  "resource_type": "MedicationStatement",
  "count": 5,
  "results": [
    {
      "resource_id": "med_001",
      "medication": "Aspirin 81 MG Oral Tablet",
      "dosage": "81mg daily",
      "status": "active",
      "start_date": "2026-01-20",
      "codes": {
        "rxnorm": "197361"
      }
    },
    {
      "resource_id": "med_002",
      "medication": "Clopidogrel 75 MG Oral Tablet",
      "dosage": "75mg daily",
      "status": "active",
      "start_date": "2026-01-20",
      "codes": {
        "rxnorm": "309362"
      }
    }
  ],
  "metadata": {
    "execution_time_ms": 15,
    "query_method": "structured_database"
  },
  "timestamp": "2026-06-08T12:45:00.000Z"
}
```

Response (FHIR format):
```json
{
  "query_id": "sqry_xyz124",
  "status": "success",
  "resourceType": "Bundle",
  "type": "searchset",
  "total": 5,
  "entry": [
    {
      "resource": {
        "resourceType": "MedicationStatement",
        "id": "med_001",
        "status": "active",
        "medicationCodeableConcept": {
          "coding": [{
            "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
            "code": "197361",
            "display": "Aspirin 81 MG Oral Tablet"
          }]
        },
        "subject": {"reference": "Patient/PATIENT_12345"},
        "effectiveDateTime": "2026-01-20",
        "dosage": [{
          "text": "81mg daily"
        }]
      }
    }
  ]
}
```

---

## Cache Management API

### POST /cache/clear

Clear cache for specific patient or entire cache.

Request:
```json
{
  "scope": "patient",  // or "all"
  "patient_id": "PATIENT_12345",
  "reason": "Document updated"
}
```

Response:
```json
{
  "status": "success",
  "entries_cleared": 8,
  "scope": "patient",
  "patient_id": "[PATIENT_a3f7]",
  "timestamp": "2026-06-08T13:00:00.000Z"
}
```

### GET /cache/stats

Get cache statistics.

Response:
```json
{
  "status": "success",
  "stats": {
    "total_entries": 1542,
    "hit_rate": 0.38,
    "miss_rate": 0.62,
    "avg_age_seconds": 1200,
    "invalidations_last_hour": 5,
    "size_mb": 125
  },
  "timestamp": "2026-06-08T13:05:00.000Z"
}
```

---

## Evaluation API

### POST /eval/run

Run evaluation on test dataset.

Request:
```json
{
  "dataset": "factual_qa",  // or "multi_hop_qa", "pii_audit"
  "config": {
    "retrieval_k": 10,
    "confidence_threshold": 0.7
  }
}
```

Response:
```json
{
  "eval_run_id": "eval_abc123",
  "status": "running",
  "dataset": "factual_qa",
  "total_cases": 100,
  "estimated_time_seconds": 300,
  "started_at": "2026-06-08T13:10:00.000Z"
}
```

### GET /eval/{eval_run_id}

Get evaluation results.

Response:
```json
{
  "eval_run_id": "eval_abc123",
  "status": "completed",
  "dataset": "factual_qa",
  "total_cases": 100,
  "metrics": {
    "retrieval": {
      "recall@5": 0.92,
      "mrr": 0.85,
      "ndcg@5": 0.88
    },
    "answer": {
      "exact_match": 0.76,
      "f1_score": 0.89,
      "rouge_l": 0.87,
      "bertscore": 0.91
    },
    "pii": {
      "leakage_rate": 0.00,
      "false_positive_rate": 0.02
    },
    "system": {
      "avg_latency_ms": 450,
      "p95_latency_ms": 850
    }
  },
  "failed_cases": 5,
  "completed_at": "2026-06-08T13:15:00.000Z"
}
```

---

## Monitoring API

### GET /health

Health check endpoint.

Response:
```json
{
  "status": "healthy",
  "components": {
    "vector_database": "healthy",
    "structured_database": "healthy",
    "llm_service": "healthy",
    "cache": "healthy"
  },
  "timestamp": "2026-06-08T13:20:00.000Z"
}
```

### GET /metrics

System metrics.

Response:
```json
{
  "status": "success",
  "metrics": {
    "queries": {
      "total_today": 1523,
      "avg_latency_ms": 485,
      "p95_latency_ms": 920,
      "error_rate": 0.02
    },
    "cache": {
      "hit_rate": 0.38,
      "size_mb": 125
    },
    "retrieval": {
      "avg_results": 8.5,
      "avg_confidence": 0.83
    }
  },
  "timestamp": "2026-06-08T13:25:00.000Z"
}
```

### GET /audit/access

Audit trail for patient access.

Query Parameters:
- `patient_id`: Required
- `start_date`: ISO 8601 format
- `end_date`: ISO 8601 format
- `user_id`: Optional filter

Response:
```json
{
  "status": "success",
  "patient_id": "[PATIENT_a3f7]",
  "date_range": {
    "start": "2026-06-01",
    "end": "2026-06-08"
  },
  "access_log": [
    {
      "audit_id": "audit_001",
      "timestamp": "2026-06-08T10:15:00Z",
      "user_id": "[USER_xyz]",
      "user_role": "physician",
      "action": "query_executed",
      "query_fingerprint": "hash_...",
      "documents_accessed": ["doc_001", "doc_002"],
      "access_justification": "Clinical care",
      "ip_address": "10.0.1.50"
    }
  ],
  "total_accesses": 15
}
```

---

## Webhook API

### POST /webhooks/configure

Configure webhooks for events.

Request:
```json
{
  "url": "https://your-system.com/webhook",
  "events": [
    "document.ingested",
    "pii.detected",
    "query.low_confidence"
  ],
  "secret": "webhook_secret_key"
}
```

Response:
```json
{
  "webhook_id": "wh_abc123",
  "status": "active",
  "url": "https://your-system.com/webhook",
  "events": ["document.ingested", "pii.detected", "query.low_confidence"],
  "created_at": "2026-06-08T13:30:00Z"
}
```

Webhook Payload Example:
```json
{
  "event": "pii.detected",
  "timestamp": "2026-06-08T13:35:00Z",
  "data": {
    "severity": "critical",
    "component": "output_validator",
    "query_id": "qry_xyz789",
    "action_taken": "OUTPUT_BLOCKED"
  }
}
```

---

## SDK Examples

### Python SDK

```python
from clinical_rag import ClinicalRAGClient

client = ClinicalRAGClient(
    api_key="your_api_key",
    base_url="https://api.clinical-rag.example.com/v1"
)

# Query patient records
response = client.query(
    query="What medications was the patient on at discharge?",
    patient_id="PATIENT_12345",
    options={
        "use_cache": True,
        "return_sources": True
    }
)

print(f"Answer: {response.answer}")
print(f"Confidence: {response.confidence}")
print(f"Sources: {len(response.sources)}")

# Ingest document
with open("discharge_summary.pdf", "rb") as f:
    doc_response = client.ingest_document(
        file=f,
        patient_id="PATIENT_12345",
        document_type="discharge_summary",
        document_date="2026-01-20"
    )

print(f"Document ingested: {doc_response.document_id}")

# Query structured data
medications = client.query_structured(
    patient_id="PATIENT_12345",
    resource_type="MedicationStatement",
    filters={"status": "active"}
)

for med in medications:
    print(f"- {med.medication}: {med.dosage}")
```

### JavaScript SDK

```javascript
const { ClinicalRAGClient } = require('clinical-rag-sdk');

const client = new ClinicalRAGClient({
  apiKey: 'your_api_key',
  baseUrl: 'https://api.clinical-rag.example.com/v1'
});

// Query patient records
const response = await client.query({
  query: 'What medications was the patient on at discharge?',
  patientId: 'PATIENT_12345',
  options: {
    useCache: true,
    returnSources: true
  }
});

console.log(`Answer: ${response.answer}`);
console.log(`Confidence: ${response.confidence}`);

// Ingest document
const docResponse = await client.ingestDocument({
  file: fileBuffer,
  patientId: 'PATIENT_12345',
  documentType: 'discharge_summary',
  documentDate: '2026-01-20'
});

console.log(`Document ingested: ${docResponse.documentId}`);

// Query structured data
const medications = await client.queryStructured({
  patientId: 'PATIENT_12345',
  resourceType: 'MedicationStatement',
  filters: { status: 'active' }
});

medications.forEach(med => {
  console.log(`- ${med.medication}: ${med.dosage}`);
});
```

---

## Rate Limiting

Rate limits by endpoint:
- `/query`: 100 requests/minute per user
- `/documents/ingest`: 50 requests/minute per user
- `/query/structured`: 200 requests/minute per user
- `/eval/*`: 10 requests/hour per user

Rate limit headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1717848000
```

429 Response:
```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Please try again in 45 seconds.",
    "retry_after": 45
  }
}
```

---

## Pagination

For endpoints returning lists:

Request:
```
GET /documents?patient_id=PATIENT_12345&page=2&per_page=20
```

Response:
```json
{
  "data": [...],
  "pagination": {
    "page": 2,
    "per_page": 20,
    "total_pages": 5,
    "total_count": 95,
    "has_next": true,
    "has_prev": true
  }
}
```

---

## Error Handling Best Practices

1. Always check `status` field in response
2. Handle PII_DETECTED errors immediately (critical)
3. Implement exponential backoff for RATE_LIMIT_EXCEEDED
4. Log all errors with query_id for debugging
5. Never log full error responses (may contain PII)

---

END OF API SPECIFICATIONS

