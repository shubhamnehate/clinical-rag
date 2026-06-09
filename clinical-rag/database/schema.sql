-- Clinical RAG System - PostgreSQL Schema
-- HIPAA-compliant schema with audit trail

-- Documents table with versioning
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(255) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    content_type VARCHAR(100),
    patient_id VARCHAR(255),
    document_date DATE,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    archived BOOLEAN DEFAULT FALSE,
    UNIQUE (document_id, version)
);
CREATE INDEX idx_documents_patient ON documents(patient_id);
CREATE INDEX idx_documents_type ON documents(content_type);

-- Chunks table
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    chunk_id VARCHAR(255) UNIQUE NOT NULL,
    document_id VARCHAR(255) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    section VARCHAR(255),
    text TEXT,
    token_count INTEGER,
    chunk_index INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_chunks_document ON chunks(document_id);
CREATE INDEX idx_chunks_section ON chunks(section);

-- FHIR resources (structured data)
CREATE TABLE IF NOT EXISTS fhir_resources (
    id SERIAL PRIMARY KEY,
    resource_id VARCHAR(255),
    resource_type VARCHAR(100),
    patient_id VARCHAR(255),
    resource_date DATE,
    data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_fhir_patient ON fhir_resources(patient_id);
CREATE INDEX idx_fhir_type ON fhir_resources(resource_type);

-- Medications (flattened for fast queries)
CREATE TABLE IF NOT EXISTS medications (
    id SERIAL PRIMARY KEY,
    patient_id VARCHAR(255),
    medication_name VARCHAR(500),
    dosage VARCHAR(255),
    route VARCHAR(100),
    frequency VARCHAR(255),
    status VARCHAR(50),
    prescribed_date DATE,
    source_document_id VARCHAR(255)
);
CREATE INDEX idx_medications_patient ON medications(patient_id);

-- Observations / Lab Results
CREATE TABLE IF NOT EXISTS observations (
    id SERIAL PRIMARY KEY,
    patient_id VARCHAR(255),
    observation_name VARCHAR(500),
    value NUMERIC,
    value_text VARCHAR(255),
    unit VARCHAR(100),
    reference_range VARCHAR(255),
    abnormal_flag VARCHAR(10),
    observed_date TIMESTAMPTZ,
    source_document_id VARCHAR(255)
);
CREATE INDEX idx_observations_patient ON observations(patient_id);
CREATE INDEX idx_observations_date ON observations(observed_date);

-- Conditions / Diagnoses
CREATE TABLE IF NOT EXISTS conditions (
    id SERIAL PRIMARY KEY,
    patient_id VARCHAR(255),
    condition_name VARCHAR(500),
    icd10_code VARCHAR(20),
    clinical_status VARCHAR(50),
    onset_date DATE,
    source_document_id VARCHAR(255)
);
CREATE INDEX idx_conditions_patient ON conditions(patient_id);

-- PII mappings (secure, encrypted - never in vector DB)
CREATE TABLE IF NOT EXISTS pii_mappings (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(255),
    entity_type VARCHAR(100),
    pseudonym VARCHAR(255),
    -- original value is NOT stored in plaintext
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit log (append-only, HIPAA compliant)
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id VARCHAR(255),
    patient_id VARCHAR(255),
    query_id VARCHAR(255),
    action VARCHAR(255) NOT NULL,
    resource VARCHAR(500),
    success BOOLEAN DEFAULT TRUE,
    details JSONB,
    -- Retention: 7 years (HIPAA requirement)
    retain_until TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 years'
);
CREATE INDEX idx_audit_patient ON audit_log(patient_id);
CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX idx_audit_type ON audit_log(event_type);

-- Query log
CREATE TABLE IF NOT EXISTS query_log (
    id SERIAL PRIMARY KEY,
    query_id VARCHAR(255) UNIQUE,
    query_text TEXT,
    patient_id VARCHAR(255),
    user_id VARCHAR(255),
    query_type VARCHAR(100),
    confidence NUMERIC(4,3),
    latency_ms INTEGER,
    cache_hit BOOLEAN DEFAULT FALSE,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_query_log_patient ON query_log(patient_id);
