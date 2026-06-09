# Clinical RAG System - Complete Documentation

A production-grade Retrieval-Augmented Generation (RAG) system for clinical question answering, designed for healthcare applications with HIPAA compliance, robust PII protection, and comprehensive evaluation.

---

## 📚 Documentation Index

This repository contains complete system specifications, configurations, and deployment guides for the Clinical RAG system:

### Core System Documentation

1. **[SYSTEM_PROMPTS.md](./SYSTEM_PROMPTS.md)** - Complete system prompts for all components
   - System architecture overview
   - Ingestion pipeline (loaders, PII detection, chunking, embedding)
   - Query intelligence (classification, routing, expansion)
   - Retrieval pipeline (dense, sparse, hybrid, reranking)
   - Context management & prompt construction
   - Generation & post-processing (with feedback loop)
   - Structured data handling (FHIR/HL7/DICOM)
   - Semantic cache system
   - Document versioning
   - Evaluation framework
   - Observability & monitoring

2. **[API_SPECIFICATIONS.md](./API_SPECIFICATIONS.md)** - Complete API documentation
   - Authentication & authorization
   - Query API
   - Document ingestion API
   - Structured query API
   - Cache management API
   - Evaluation API
   - Monitoring API
   - Webhook API
   - SDK examples (Python, JavaScript)
   - Rate limiting & pagination
   - Error handling

3. **[DATA_SCHEMAS.md](./DATA_SCHEMAS.md)** - Database schemas & data formats
   - Vector database schema
   - PostgreSQL schema (documents, chunks, FHIR, medications, observations, conditions, procedures, PII mappings, audit logs)
   - Cache schema (Redis)
   - Message formats
   - Index definitions
   - Data validation schemas
   - Backup and recovery

4. **[CONFIGURATION.yaml](./CONFIGURATION.yaml)** - Master configuration file
   - System settings
   - Database configuration
   - Embedding models
   - LLM configuration
   - Ingestion pipeline
   - Query intelligence
   - Retrieval pipeline
   - Prompt construction
   - Post-processing
   - Cache system
   - Structured data handling
   - Evaluation framework
   - Observability
   - Security
   - Deployment
   - Feature flags

5. **[DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)** - Production deployment guide
   - Prerequisites & cost estimates
   - Infrastructure setup (AWS/Kubernetes)
   - Database initialization
   - Service deployment
   - Configuration
   - Security hardening
   - Monitoring setup
   - Testing & validation
   - Go-live checklist
   - Troubleshooting

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      INGESTION PIPELINE                          │
├─────────────────────────────────────────────────────────────────┤
│  Document Loaders → PII Detection → Chunking → Embedding        │
│  (Text, PDF, DICOM, HL7, FHIR) → Pseudonymization → Storage     │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────────┐
│                    QUERY INTELLIGENCE                             │
├──────────────────────────────────────────────────────────────────┤
│  Classifier → Router → Query Expander → Cache Check              │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────────┐
│                    RETRIEVAL PIPELINE                             │
├──────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Dense Search │  │Sparse Search │  │ Structured   │           │
│  │  (Vector)    │  │   (BM25)     │  │   Query      │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
│         └──────────────────┴──────────────────┘                  │
│                     Hybrid Fusion                                │
│                          ↓                                        │
│                  Cross-Encoder Reranking                          │
│                          ↓                                        │
│                  Patient-Level Filtering                          │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────────┐
│                  PROMPT CONSTRUCTION                              │
├──────────────────────────────────────────────────────────────────┤
│  Context Assembly → PII Guard → Token Budget → Prompt Template   │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────────┐
│                    GENERATION (LLM)                               │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────────┐
│                   POST-PROCESSING                                 │
├──────────────────────────────────────────────────────────────────┤
│  Confidence Scoring → Output PII Scan → Validation               │
│                          ↓                                        │
│                  Low Confidence? ───────┐                         │
│                          ↓              │                         │
│                   Return Answer    Re-retrieve (FEEDBACK LOOP)    │
│                          ↓              │                         │
│                  Cache Result     ←─────┘                         │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────────┐
│                     OBSERVABILITY                                 │
├──────────────────────────────────────────────────────────────────┤
│  Logging → Metrics → Tracing → Audit Trail                       │
└──────────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

### Core Capabilities
- **Hybrid Retrieval**: Combines dense (vector), sparse (BM25), and structured queries
- **Query Intelligence**: Automatic query classification, routing, and expansion
- **Multi-Format Support**: Text, PDF, DICOM, HL7, FHIR
- **Structured Data Path**: Separate pipeline for FHIR/HL7 (no vector search for structured queries)
- **Document Versioning**: Track amendments and corrections with full audit trail
- **Semantic Cache**: Query caching with automatic invalidation on document updates
- **Feedback Loop**: Automatic retry with query expansion for low-confidence results

### Security & Compliance
- **3-Layer PII Protection**: Ingestion, prompt assembly, and output validation
- **HIPAA Compliant**: Full audit trail, encryption at rest and in transit
- **Patient-Level Access Control**: Prevents cross-patient data leakage
- **Audit Trail**: 7-year retention for compliance
- **Encryption**: AES-256-GCM at rest, TLS 1.3 in transit

### Quality & Performance
- **Confidence Scoring**: Automatic quality assessment with retry logic
- **Cross-Encoder Reranking**: Superior relevance vs. bi-encoders
- **Context Budget Management**: Efficient token usage within 200K window
- **Comprehensive Evaluation**: Factual QA, multi-hop, PII audit datasets
- **Sub-500ms Latency**: Optimized for production workloads

---

## 🚀 Quick Start

### 1. Review Documentation

Start with these documents in order:
1. [SYSTEM_PROMPTS.md](./SYSTEM_PROMPTS.md) - Understand the system design
2. [CONFIGURATION.yaml](./CONFIGURATION.yaml) - Review configuration options
3. [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) - Follow deployment steps

### 2. Set Up Infrastructure

```bash
# Clone repository (hypothetical)
git clone https://github.com/your-org/clinical-rag.git
cd clinical-rag

# Set up infrastructure with Terraform
cd infrastructure
terraform init
terraform apply

# Initialize databases
psql -h <postgres_host> -U postgres -d clinical_rag -f database/schema.sql

# Deploy services
kubectl apply -f k8s/
```

### 3. Configure System

```bash
# Copy and edit configuration
cp CONFIGURATION.yaml config/production.yaml
vim config/production.yaml

# Set environment variables
cp .env.example .env
vim .env
```

### 4. Test System

```bash
# Run integration tests
pytest tests/integration/ -v

# Run PII audit
pytest tests/pii_audit/ -v

# Run evaluation
python scripts/run_evaluation.py --dataset factual_qa
```

### 5. Query the System

```python
from clinical_rag import ClinicalRAGClient

client = ClinicalRAGClient(
    api_key="your_api_key",
    base_url="https://api.clinical-rag.example.com/v1"
)

response = client.query(
    query="What medications was the patient on at discharge?",
    patient_id="PATIENT_12345"
)

print(f"Answer: {response.answer}")
print(f"Confidence: {response.confidence}")
```

---

## 🔒 Security Considerations

### Critical Security Features

1. **PII Protection (3 Layers)**
   - ✅ Layer 1: Ingestion-time pseudonymization
   - ✅ Layer 2: Prompt assembly PII guard
   - ✅ Layer 3: Output PII scan (CRITICAL - closes the gap)

2. **Access Control**
   - Patient-level filtering (prevents cross-patient access)
   - Role-based access control (RBAC)
   - JWT authentication with expiration
   - Audit trail for all access

3. **Data Protection**
   - Encryption at rest (AES-256-GCM)
   - Encryption in transit (TLS 1.3)
   - Secure PII mapping storage (key vault)
   - No PII in logs or vector database

4. **Compliance**
   - HIPAA compliant
   - 7-year audit trail retention
   - Data retention policies
   - Regular security audits

---

## 📊 Evaluation & Metrics

### Evaluation Datasets

1. **Factual QA** (100 cases)
   - Simple factual questions
   - Metrics: Exact match, F1, retrieval recall

2. **Multi-Hop QA** (50 cases)
   - Complex questions requiring multiple documents
   - Metrics: Answer accuracy, retrieval coverage

3. **PII Audit** (30 cases)
   - Designed to test PII leakage
   - **Target: 0% leakage rate**

### Target Metrics

| Metric | Target | Critical? |
|--------|--------|-----------|
| Answer Accuracy (F1) | >0.85 | ✓ |
| Retrieval Recall@5 | >0.90 | ✓ |
| PII Leakage Rate | 0.00% | ✓✓✓ CRITICAL |
| Avg Latency | <500ms | ✓ |
| P95 Latency | <1000ms | - |
| Cache Hit Rate | >0.30 | - |
| Confidence > 0.7 | >0.80 | ✓ |

---

## 🔧 Troubleshooting

### Common Issues

**High Latency**
- Check vector DB performance
- Review retrieval k parameter (reduce if too high)
- Enable caching
- Scale compute resources

**Low Confidence Scores**
- Enable query expansion
- Increase retrieval k
- Check document coverage
- Review query classification

**PII Leakage Detected**
- **CRITICAL**: Immediate action required
- Review PII detection patterns
- Check pseudonymization pipeline
- Audit affected queries
- Report to security team

**Cache Not Invalidating**
- Check document dependency tracking
- Verify cache invalidation triggers
- Review TTL settings
- Clear cache manually if needed

See [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) for detailed troubleshooting.

---

## 📈 Performance Optimization

### Latency Optimization

1. **Enable Caching**
   - Semantic cache with 90% similarity threshold
   - Document-based invalidation
   - ~800ms latency savings on cache hit

2. **Optimize Retrieval**
   - Reduce k for simple queries
   - Use query classification to route appropriately
   - Enable reranking only when needed

3. **Batch Processing**
   - Batch embeddings during ingestion
   - Parallel retrieval (dense + sparse)
   - Async processing where possible

### Accuracy Optimization

1. **Query Expansion**
   - Medical terminology expansion (UMLS, SNOMED)
   - Abbreviation expansion
   - Related concept addition

2. **Reranking**
   - Cross-encoder for final ranking
   - Improves precision significantly

3. **Feedback Loop**
   - Automatic retry with expanded query
   - Up to 2 retries for low confidence

---

## 🏥 Clinical Use Cases

### Supported Query Types

1. **Factual Lookup**
   - "What medications is the patient on?"
   - "What was the diagnosis?"
   - "What were the lab values on [date]?"

2. **Explanation**
   - "Why was the patient started on antibiotics?"
   - "Explain the treatment approach for this patient"

3. **Comparison**
   - "How did vital signs change from admission to discharge?"
   - "Compare lab values from [date1] to [date2]"

4. **Multi-Hop**
   - "Was the treatment consistent with the diagnosis?"
   - "What complications occurred and how were they managed?"

5. **Summarization**
   - "Summarize the hospital course"
   - "Provide an overview of the patient's medical history"

6. **Temporal**
   - "What happened on January 15th?"
   - "Show all events from last week"

7. **Structured Query**
   - "List all active medications"
   - "Show lab results from last month"

---

## 🛠️ Development

### Project Structure

```
clinical-rag/
├── src/
│   ├── ingestion/
│   │   ├── loaders/
│   │   ├── pii_detection.py
│   │   ├── chunking.py
│   │   └── embedding.py
│   ├── query/
│   │   ├── classifier.py
│   │   ├── router.py
│   │   └── expander.py
│   ├── retrieval/
│   │   ├── dense.py
│   │   ├── sparse.py
│   │   ├── hybrid.py
│   │   └── reranker.py
│   ├── generation/
│   │   ├── prompt.py
│   │   └── llm.py
│   ├── post_processing/
│   │   ├── confidence.py
│   │   ├── validation.py
│   │   └── feedback_loop.py
│   ├── structured/
│   │   ├── fhir_parser.py
│   │   ├── hl7_parser.py
│   │   └── query_builder.py
│   ├── cache/
│   │   └── semantic_cache.py
│   └── observability/
│       ├── logging.py
│       ├── metrics.py
│       └── tracing.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── pii_audit/
├── config/
│   └── production.yaml
├── infrastructure/
│   └── main.tf
├── k8s/
│   └── *.yaml
├── database/
│   ├── schema.sql
│   └── indexes.sql
├── docs/
│   ├── SYSTEM_PROMPTS.md
│   ├── API_SPECIFICATIONS.md
│   ├── DATA_SCHEMAS.md
│   ├── CONFIGURATION.yaml
│   └── DEPLOYMENT_GUIDE.md
└── README.md
```

### Running Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# PII audit (CRITICAL)
pytest tests/pii_audit/ -v

# Load tests
locust -f tests/load/locustfile.py --host https://api.example.com
```

---

## 📋 Implementation Checklist

### Phase 1: Foundation (Week 1-2)
- [ ] Document loaders (text, PDF)
- [ ] PII detection & pseudonymization (CRITICAL - do first)
- [ ] Chunking
- [ ] Basic embedding & vector storage
- [ ] Query classifier (even stub version)

### Phase 2: Retrieval (Week 3-4)
- [ ] Dense retrieval
- [ ] Sparse retrieval (BM25)
- [ ] Hybrid fusion
- [ ] Patient-level filtering
- [ ] Basic structured query for FHIR (separate path from day 1)

### Phase 3: Generation (Week 5-6)
- [ ] Context assembly
- [ ] PII guard (Layer 2)
- [ ] Prompt construction
- [ ] LLM integration
- [ ] Confidence scoring
- [ ] Output validation with PII scan (Layer 3 - CRITICAL)
- [ ] Feedback loop (close the loop)

### Phase 4: Structured Data (Week 7-8)
- [ ] FHIR parser
- [ ] HL7 parser
- [ ] Structured query builder
- [ ] DICOM metadata extraction (as structured data)

### Phase 5: Advanced Features (Week 9-10)
- [ ] Cross-encoder reranking
- [ ] Query expansion
- [ ] Multi-hop retrieval
- [ ] Semantic cache with invalidation
- [ ] Document versioning

### Phase 6: Production Readiness (Week 11-12)
- [ ] Evaluation framework
- [ ] Observability (logging, metrics, tracing)
- [ ] Audit trail
- [ ] Performance optimization
- [ ] Security hardening

---

## 🚨 Pre-Production Checklist

### CRITICAL REQUIREMENTS

- [ ] **3-layer PII protection implemented**
  - [ ] Layer 1: Ingestion-time pseudonymization
  - [ ] Layer 2: Prompt assembly PII guard
  - [ ] Layer 3: Output PII scan (CRITICAL - runs before every response)

- [ ] **Feedback loop closes back to retrieval pipeline**
  - [ ] Low confidence triggers re-retrieval
  - [ ] Max 2 retry attempts
  - [ ] All retries logged

- [ ] **FHIR/HL7 bypass vector search**
  - [ ] Structured path separate from dense/sparse
  - [ ] Direct database queries
  - [ ] No vector embeddings for structured data

- [ ] **Document versioning tracks updates**
  - [ ] Version field on all documents
  - [ ] Archive old versions
  - [ ] Audit trail for changes

- [ ] **Cache invalidation triggers on document updates**
  - [ ] Document dependency tracking
  - [ ] Automatic invalidation
  - [ ] TTL as backup

- [ ] **Patient-level filtering prevents cross-patient data access**
  - [ ] Filter enforced in vector DB queries
  - [ ] Filter enforced in SQL queries
  - [ ] Tested and verified

- [ ] **Query classifier runs before retrieval**
  - [ ] Not after 2 weeks of testing
  - [ ] Integrated from day one
  - [ ] Routes appropriately

- [ ] **Audit trail captures all patient data access**
  - [ ] Logs to immutable storage
  - [ ] 7-year retention
  - [ ] Compliance verified

- [ ] **PII leakage rate = 0% in evaluation**
  - [ ] Run PII audit dataset
  - [ ] Zero tolerance for leakage
  - [ ] Tested in production-like environment

### Additional Requirements

- [ ] Load tests passing (100 req/min sustained)
- [ ] Integration tests passing (100% pass rate)
- [ ] Monitoring and alerting configured
- [ ] Backup and disaster recovery tested
- [ ] Security audit completed
- [ ] Documentation complete
- [ ] Team trained
- [ ] On-call rotation established

---

## 📞 Support

- **Documentation**: See docs/ folder
- **Issues**: Check DEPLOYMENT_GUIDE.md troubleshooting section
- **Security Issues**: security@example.com (CRITICAL issues)
- **On-Call**: oncall@example.com

---

## 📄 License

[Specify your license]

---

## 🙏 Acknowledgments

This system was designed with healthcare compliance and patient safety as top priorities. The architecture addresses critical gaps identified in initial design reviews, including:

1. ✅ Missing feedback loop from post-processor to retrieval
2. ✅ DICOM metadata handling as structured data
3. ✅ Output PII scan (3rd layer of protection)
4. ✅ FHIR/HL7 structured data routing (no vector search)
5. ✅ Query classification before retrieval
6. ✅ Document versioning with audit trail
7. ✅ Knowledge graph design (optional but architected)
8. ✅ Semantic cache with invalidation strategy

---

**Built for Healthcare. Designed for Safety. Optimized for Performance.**

---

END OF README

