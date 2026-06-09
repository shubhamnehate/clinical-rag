# Clinical RAG System - Data Schemas

## Table of Contents
1. [Vector Database Schema](#vector-database-schema)
2. [Structured Database Schema](#structured-database-schema)
3. [Cache Schema](#cache-schema)
4. [Message Formats](#message-formats)
5. [Index Definitions](#index-definitions)

---

## Vector Database Schema

### Collection: `clinical_chunks`

Used for storing embedded text chunks from clinical documents.

```json
{
  "id": "doc_001_chunk_0",
  "vector": [0.123, -0.456, 0.789, ...],  // 384 dimensions
  "metadata": {
    "document_id": "doc_001",
    "document_version": 1,
    "patient_id": "[PATIENT_a3f7]",
    "document_type": "discharge_summary",
    "document_date": "2026-01-20",
    "section": "MEDICATIONS",
    "chunk_index": 0,
    "token_count": 450,
    "has_overlap_prev": false,
    "has_overlap_next": true,
    "created_at": "2026-01-20T16:30:00Z",
    "status": "active",
    "pii_pseudonymized": true
  },
  "content": "MEDICATIONS ON DISCHARGE:\n- Aspirin 81mg daily\n- Clopidogrel 75mg daily\n- Atorvastatin 80mg daily..."
}
```

### Indexes

```python
# Vector index
chunks_collection.create_index(
    field_name="vector",
    index_type="HNSW",
    params={
        "M": 16,
        "ef_construction": 200
    }
)

# Metadata filters
chunks_collection.create_index(field_name="metadata.patient_id", index_type="TAG")
chunks_collection.create_index(field_name="metadata.document_type", index_type="TAG")
chunks_collection.create_index(field_name="metadata.document_date", index_type="NUMERIC")
chunks_collection.create_index(field_name="metadata.status", index_type="TAG")
chunks_collection.create_index(field_name="metadata.document_version", index_type="NUMERIC")
```

---

## Structured Database Schema

### PostgreSQL Schema

#### Table: `documents`

```sql
CREATE TABLE documents (
    document_id VARCHAR(50) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    patient_id VARCHAR(50) NOT NULL,
    document_type VARCHAR(50) NOT NULL,
    document_date DATE NOT NULL,
    content TEXT,
    content_hash VARCHAR(64),
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, archived, deleted
    parent_version INTEGER,
    change_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by VARCHAR(50),
    modified_at TIMESTAMP,
    modified_by VARCHAR(50),
    metadata JSONB,
    PRIMARY KEY (document_id, version)
);

CREATE INDEX idx_documents_patient ON documents(patient_id) WHERE status = 'active';
CREATE INDEX idx_documents_date ON documents(document_date) WHERE status = 'active';
CREATE INDEX idx_documents_type ON documents(document_type) WHERE status = 'active';
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_metadata ON documents USING GIN(metadata);

-- Latest version view
CREATE VIEW documents_latest AS
SELECT DISTINCT ON (document_id) *
FROM documents
WHERE status = 'active'
ORDER BY document_id, version DESC;
```

#### Table: `chunks`

```sql
CREATE TABLE chunks (
    chunk_id VARCHAR(100) PRIMARY KEY,
    document_id VARCHAR(50) NOT NULL,
    document_version INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    section VARCHAR(100),
    embedding_id VARCHAR(100),  -- Reference to vector DB
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (document_id, document_version) REFERENCES documents(document_id, version)
);

CREATE INDEX idx_chunks_document ON chunks(document_id, document_version);
```

#### Table: `fhir_resources`

```sql
CREATE TABLE fhir_resources (
    resource_id VARCHAR(100) PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    status VARCHAR(20),
    effective_date TIMESTAMP,
    resource_json JSONB NOT NULL,
    extracted_fields JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE INDEX idx_fhir_patient ON fhir_resources(patient_id);
CREATE INDEX idx_fhir_type ON fhir_resources(resource_type);
CREATE INDEX idx_fhir_date ON fhir_resources(effective_date);
CREATE INDEX idx_fhir_status ON fhir_resources(status);
CREATE INDEX idx_fhir_json ON fhir_resources USING GIN(resource_json);
CREATE INDEX idx_fhir_extracted ON fhir_resources USING GIN(extracted_fields);
```

#### Table: `medications`

Extracted and flattened from FHIR for faster queries.

```sql
CREATE TABLE medications (
    medication_id VARCHAR(100) PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    medication_name VARCHAR(255) NOT NULL,
    medication_code VARCHAR(50),
    coding_system VARCHAR(50),  -- RxNorm, SNOMED, etc.
    dosage TEXT,
    frequency VARCHAR(100),
    route VARCHAR(50),
    status VARCHAR(20) NOT NULL,  -- active, completed, stopped
    start_date DATE,
    end_date DATE,
    prescriber_id VARCHAR(50),
    source_resource_id VARCHAR(100),  -- FK to fhir_resources
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (source_resource_id) REFERENCES fhir_resources(resource_id)
);

CREATE INDEX idx_medications_patient ON medications(patient_id);
CREATE INDEX idx_medications_status ON medications(status);
CREATE INDEX idx_medications_name ON medications(medication_name);
CREATE INDEX idx_medications_code ON medications(medication_code);
CREATE INDEX idx_medications_dates ON medications(start_date, end_date);
```

#### Table: `observations`

Labs, vitals, and clinical observations.

```sql
CREATE TABLE observations (
    observation_id VARCHAR(100) PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    observation_type VARCHAR(50) NOT NULL,  -- lab, vital, clinical
    observation_code VARCHAR(50),  -- LOINC code
    observation_name VARCHAR(255) NOT NULL,
    value_numeric DECIMAL(10, 3),
    value_text TEXT,
    unit VARCHAR(50),
    interpretation VARCHAR(10),  -- H, L, N, etc.
    reference_range VARCHAR(100),
    effective_datetime TIMESTAMP NOT NULL,
    status VARCHAR(20),  -- final, preliminary, corrected
    source_resource_id VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (source_resource_id) REFERENCES fhir_resources(resource_id)
);

CREATE INDEX idx_observations_patient ON observations(patient_id);
CREATE INDEX idx_observations_type ON observations(observation_type);
CREATE INDEX idx_observations_code ON observations(observation_code);
CREATE INDEX idx_observations_date ON observations(effective_datetime);
CREATE INDEX idx_observations_name ON observations(observation_name);
```

#### Table: `conditions`

Diagnoses and conditions.

```sql
CREATE TABLE conditions (
    condition_id VARCHAR(100) PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    condition_name VARCHAR(255) NOT NULL,
    icd10_code VARCHAR(10),
    snomed_code VARCHAR(50),
    clinical_status VARCHAR(20),  -- active, resolved, inactive
    verification_status VARCHAR(20),  -- confirmed, provisional
    severity VARCHAR(20),
    onset_date DATE,
    resolution_date DATE,
    source_resource_id VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (source_resource_id) REFERENCES fhir_resources(resource_id)
);

CREATE INDEX idx_conditions_patient ON conditions(patient_id);
CREATE INDEX idx_conditions_status ON conditions(clinical_status);
CREATE INDEX idx_conditions_icd10 ON conditions(icd10_code);
CREATE INDEX idx_conditions_snomed ON conditions(snomed_code);
```

#### Table: `procedures`

```sql
CREATE TABLE procedures (
    procedure_id VARCHAR(100) PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    procedure_name VARCHAR(255) NOT NULL,
    procedure_code VARCHAR(50),
    coding_system VARCHAR(50),  -- CPT, SNOMED, etc.
    status VARCHAR(20),
    performed_date TIMESTAMP,
    performer_id VARCHAR(50),
    source_resource_id VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    FOREIGN KEY (source_resource_id) REFERENCES fhir_resources(resource_id)
);

CREATE INDEX idx_procedures_patient ON procedures(patient_id);
CREATE INDEX idx_procedures_date ON procedures(performed_date);
CREATE INDEX idx_procedures_code ON procedures(procedure_code);
```

#### Table: `pii_mappings`

Secure storage for PII pseudonym mappings (encrypted at rest).

```sql
CREATE TABLE pii_mappings (
    mapping_id VARCHAR(100) PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,  -- patient, provider, location
    pseudonym VARCHAR(100) NOT NULL UNIQUE,
    encrypted_value BYTEA NOT NULL,  -- Encrypted original value
    encryption_key_id VARCHAR(50) NOT NULL,  -- Reference to key vault
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    accessed_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP
);

CREATE UNIQUE INDEX idx_pii_pseudonym ON pii_mappings(pseudonym);
CREATE INDEX idx_pii_entity_type ON pii_mappings(entity_type);

-- This table should have strictest access controls
GRANT SELECT ON pii_mappings TO authorized_admin ONLY;
```

#### Table: `audit_log`

```sql
CREATE TABLE audit_log (
    audit_id VARCHAR(100) PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    user_role VARCHAR(50),
    patient_id VARCHAR(50),
    action VARCHAR(100) NOT NULL,
    query_fingerprint VARCHAR(64),
    documents_accessed TEXT[],
    access_justification TEXT,
    ip_address INET,
    session_id VARCHAR(100),
    status VARCHAR(20),
    metadata JSONB
);

CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX idx_audit_user ON audit_log(user_id);
CREATE INDEX idx_audit_patient ON audit_log(patient_id);
CREATE INDEX idx_audit_event ON audit_log(event_type);

-- Audit log is append-only
CREATE RULE no_delete_audit AS ON DELETE TO audit_log DO INSTEAD NOTHING;
CREATE RULE no_update_audit AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
```

#### Table: `query_log`

```sql
CREATE TABLE query_log (
    query_id VARCHAR(100) PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    user_id VARCHAR(50) NOT NULL,
    patient_id VARCHAR(50) NOT NULL,
    query_text_hash VARCHAR(64) NOT NULL,  -- Hash, not full text (PII risk)
    query_type VARCHAR(50),
    confidence_score DECIMAL(3, 2),
    retrieval_method VARCHAR(50),
    documents_retrieved INTEGER,
    cache_hit BOOLEAN,
    retry_count INTEGER,
    latency_ms INTEGER,
    status VARCHAR(20),
    error_code VARCHAR(50)
);

CREATE INDEX idx_query_timestamp ON query_log(timestamp);
CREATE INDEX idx_query_user ON query_log(user_id);
CREATE INDEX idx_query_patient ON query_log(patient_id);
CREATE INDEX idx_query_type ON query_log(query_type);

-- Retention policy: 90 days
CREATE TABLE query_log_archive (LIKE query_log INCLUDING ALL);
```

---

## Cache Schema

### Redis Schema

#### Key Pattern: `query_cache:{patient_id_hash}:{query_hash}`

```json
{
  "cache_key": "qcache:a3f7:abc123",
  "patient_id": "[PATIENT_a3f7]",
  "query_hash": "abc123",
  "query_embedding": [0.123, -0.456, ...],
  "original_query": "What medications was the patient on at discharge?",
  "result": {
    "answer": "Based on the discharge summary...",
    "confidence": 0.92,
    "sources": [...]
  },
  "metadata": {
    "query_type": "factual_lookup",
    "retrieval_method": "hybrid",
    "latency_ms": 450
  },
  "document_dependencies": ["doc_001", "doc_002"],
  "cached_at": "2026-06-08T10:30:00Z",
  "hit_count": 3,
  "ttl": 3600
}
```

TTL: 1 hour (3600 seconds)

#### Key Pattern: `cache_invalidation:{document_id}`

Tracks which cache entries depend on a document.

```json
{
  "document_id": "doc_001",
  "dependent_cache_keys": [
    "qcache:a3f7:abc123",
    "qcache:a3f7:def456",
    "qcache:a3f7:ghi789"
  ]
}
```

No TTL (persists until document updated)

#### Key Pattern: `patient_cache_index:{patient_id}`

Index of all cache entries for a patient.

```json
{
  "patient_id": "[PATIENT_a3f7]",
  "cache_keys": [
    "qcache:a3f7:abc123",
    "qcache:a3f7:def456",
    "qcache:a3f7:ghi789",
    "qcache:a3f7:jkl012"
  ],
  "total_entries": 4,
  "total_size_bytes": 15420,
  "last_invalidated": "2026-06-08T14:20:00Z"
}
```

---

## Message Formats

### Query Request Message

```json
{
  "query_id": "qry_abc123",
  "timestamp": "2026-06-08T12:34:56.789Z",
  "user_id": "[USER_xyz]",
  "patient_id": "[PATIENT_a3f7]",
  "query": {
    "text": "What medications was the patient on at discharge?",
    "type": "factual_lookup",
    "confidence": 0.95
  },
  "context": {
    "date_range": {
      "start": "2026-01-01",
      "end": "2026-01-31"
    },
    "document_types": ["discharge_summary", "progress_note"],
    "exclude_archived": true
  },
  "options": {
    "use_cache": true,
    "max_retries": 2,
    "confidence_threshold": 0.7,
    "return_sources": true,
    "max_latency_ms": 5000
  }
}
```

### Retrieval Results Message

```json
{
  "query_id": "qry_abc123",
  "timestamp": "2026-06-08T12:34:56.950Z",
  "retrieval_method": "hybrid",
  "results": [
    {
      "chunk_id": "doc_001_chunk_5",
      "rank": 1,
      "dense_score": 0.87,
      "sparse_score": 15.3,
      "rerank_score": 0.92,
      "final_score": 0.90,
      "content": "MEDICATIONS ON DISCHARGE:\n- Aspirin 81mg daily...",
      "metadata": {
        "document_id": "doc_001",
        "document_type": "discharge_summary",
        "document_date": "2026-01-20",
        "section": "MEDICATIONS"
      }
    }
  ],
  "total_results": 5,
  "latency_ms": 120
}
```

### LLM Generation Message

```json
{
  "query_id": "qry_abc123",
  "timestamp": "2026-06-08T12:34:57.200Z",
  "prompt": {
    "system": "You are an expert clinical assistant...",
    "context": "=== Document: Discharge Summary (2026-01-20) ===\n...",
    "query": "What medications was the patient on at discharge?",
    "total_tokens": 5850
  },
  "generation": {
    "model": "claude-sonnet-4.5",
    "temperature": 0.1,
    "max_tokens": 2000
  },
  "response": {
    "answer": "Based on the discharge summary dated 2026-01-20...",
    "tokens_used": 180,
    "latency_ms": 300
  }
}
```

### Post-Processing Message

```json
{
  "query_id": "qry_abc123",
  "timestamp": "2026-06-08T12:34:57.250Z",
  "confidence_scoring": {
    "score": 0.92,
    "level": "high",
    "factors": {
      "retrieval_quality": 0.90,
      "answer_grounding": 0.95,
      "query_complexity": 0.85,
      "context_coverage": 0.95
    }
  },
  "validation": {
    "pii_detected": false,
    "hallucination_detected": false,
    "answer_completeness": "complete",
    "safety_check": "pass",
    "status": "PASS"
  },
  "action": "return_answer"
}
```

### Event Stream Message (WebSocket)

```json
{
  "event": "query_progress",
  "query_id": "qry_abc123",
  "timestamp": "2026-06-08T12:34:57.000Z",
  "stage": "retrieval",
  "progress": 0.4,
  "message": "Searching documents...",
  "details": {
    "documents_searched": 120,
    "results_found": 8
  }
}
```

---

## Index Definitions

### Elasticsearch (for BM25 sparse retrieval)

```json
{
  "settings": {
    "analysis": {
      "analyzer": {
        "clinical_analyzer": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "clinical_stopwords",
            "clinical_synonyms"
          ]
        }
      },
      "filter": {
        "clinical_stopwords": {
          "type": "stop",
          "stopwords": ["the", "is", "at", "which"]
        },
        "clinical_synonyms": {
          "type": "synonym",
          "synonyms": [
            "MI, myocardial infarction, heart attack",
            "BP, blood pressure",
            "HR, heart rate"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "chunk_id": {"type": "keyword"},
      "content": {
        "type": "text",
        "analyzer": "clinical_analyzer"
      },
      "patient_id": {"type": "keyword"},
      "document_type": {"type": "keyword"},
      "document_date": {"type": "date"},
      "section": {"type": "keyword"},
      "status": {"type": "keyword"}
    }
  }
}
```

---

## Data Validation Schemas

### JSON Schema: Document Metadata

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["document_id", "patient_id", "document_type", "document_date"],
  "properties": {
    "document_id": {
      "type": "string",
      "pattern": "^doc_[a-zA-Z0-9]+$"
    },
    "patient_id": {
      "type": "string",
      "pattern": "^\\[PATIENT_[a-zA-Z0-9]+\\]$"
    },
    "document_type": {
      "type": "string",
      "enum": [
        "discharge_summary",
        "progress_note",
        "lab_report",
        "radiology_report",
        "operative_note",
        "consult_note"
      ]
    },
    "document_date": {
      "type": "string",
      "format": "date"
    },
    "provider_id": {
      "type": "string",
      "pattern": "^\\[PROVIDER_[a-zA-Z0-9]+\\]$"
    }
  }
}
```

### JSON Schema: Query Request

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["query", "patient_id"],
  "properties": {
    "query": {
      "type": "string",
      "minLength": 3,
      "maxLength": 1000
    },
    "patient_id": {
      "type": "string",
      "pattern": "^PATIENT_[a-zA-Z0-9]+$"
    },
    "context": {
      "type": "object",
      "properties": {
        "date_range": {
          "type": "object",
          "properties": {
            "start": {"type": "string", "format": "date"},
            "end": {"type": "string", "format": "date"}
          }
        },
        "document_types": {
          "type": "array",
          "items": {"type": "string"}
        }
      }
    },
    "options": {
      "type": "object",
      "properties": {
        "use_cache": {"type": "boolean", "default": true},
        "max_retries": {"type": "integer", "minimum": 0, "maximum": 3},
        "confidence_threshold": {"type": "number", "minimum": 0, "maximum": 1},
        "return_sources": {"type": "boolean", "default": true}
      }
    }
  }
}
```

---

## Data Migration Scripts

### Version 1 to Version 2 Migration

```sql
-- Add version column to documents
ALTER TABLE documents ADD COLUMN version INTEGER NOT NULL DEFAULT 1;

-- Update primary key
ALTER TABLE documents DROP CONSTRAINT documents_pkey;
ALTER TABLE documents ADD PRIMARY KEY (document_id, version);

-- Add parent_version column
ALTER TABLE documents ADD COLUMN parent_version INTEGER;
ALTER TABLE documents ADD COLUMN change_reason TEXT;

-- Migrate existing data
UPDATE documents SET version = 1 WHERE version IS NULL;

-- Create latest version view
CREATE VIEW documents_latest AS
SELECT DISTINCT ON (document_id) *
FROM documents
WHERE status = 'active'
ORDER BY document_id, version DESC;
```

---

## Backup and Recovery

### Backup Schema

```json
{
  "backup_id": "backup_20260608_120000",
  "timestamp": "2026-06-08T12:00:00Z",
  "components": {
    "postgres": {
      "database": "clinical_rag",
      "size_gb": 45.3,
      "tables": [
        "documents",
        "chunks",
        "fhir_resources",
        "medications",
        "observations",
        "conditions",
        "procedures",
        "audit_log"
      ],
      "backup_file": "s3://backups/postgres_20260608_120000.dump"
    },
    "vector_db": {
      "collection": "clinical_chunks",
      "vectors_count": 1250000,
      "size_gb": 12.8,
      "backup_file": "s3://backups/vectors_20260608_120000.tar.gz"
    },
    "redis": {
      "cache_entries": 1542,
      "size_mb": 125,
      "backup_file": "s3://backups/redis_20260608_120000.rdb"
    }
  },
  "verification": {
    "checksums": {
      "postgres": "sha256:abc123...",
      "vector_db": "sha256:def456...",
      "redis": "sha256:ghi789..."
    },
    "verified": true
  }
}
```

---

END OF DATA SCHEMAS

