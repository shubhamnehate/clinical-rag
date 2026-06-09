# Clinical RAG System

A production-grade Retrieval-Augmented Generation (RAG) system for clinical question answering with HIPAA compliance, 3-layer PII protection, and comprehensive evaluation framework.

---

## Quick Start

### Prerequisites

- Python 3.9+
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_ORG/clinical-rag.git
cd clinical-rag
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate          # Windows
```

### 3. Install Dependencies

For a minimal setup (testing without GPU):
```bash
pip install numpy pydantic python-dotenv pytest
```

For full ML capabilities:
```bash
pip install -r requirements.txt
```

Or install by feature group:
```bash
pip install -e ".[ml]"      # sentence-transformers, BM25
pip install -e ".[llm]"     # Anthropic Claude
pip install -e ".[clinical]" # DICOM, HL7, PDF support
pip install -e ".[all]"     # Everything
```

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:
```env
# Required for LLM (skip for mock mode)
ANTHROPIC_API_KEY=your_key_here

# Required for PII protection (change this!)
PII_SALT=your_random_secret_string
```

### 5. Run Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/ -v

# Critical PII audit (must pass with 0% leakage)
pytest tests/pii_audit/ -v

# Integration tests
pytest tests/integration/ -v
```

### 6. Try the Pipeline

```python
from src.pipeline import ClinicalRAGPipeline

# Initialize (mock_llm=True means no API key needed)
pipeline = ClinicalRAGPipeline(mock_llm=True)

# Ingest a clinical document
pipeline.ingest_text(
    document_id="discharge_001",
    text="""DISCHARGE SUMMARY
CHIEF COMPLAINT: Chest pain
MEDICATIONS AT DISCHARGE:
1. Aspirin 81mg daily
2. Atorvastatin 80mg nightly
3. Metoprolol 25mg twice daily
ASSESSMENT: Anterior STEMI, post-PCI with DES to LAD.""",
    content_type="discharge_summary",
    patient_id="PATIENT_001",
)

# Query the system
response = pipeline.query(
    query="What medications was the patient discharged with?",
    patient_id="PATIENT_001",
)

print(f"Answer: {response.answer}")
print(f"Confidence: {response.confidence:.0%}")
print(f"Latency: {response.latency_ms:.0f}ms")
```

---

## System Architecture

```
INGESTION PIPELINE
  Document Loaders (Text, PDF, DICOM, HL7, FHIR)
        ↓
  [Layer 1] PII Detection & Pseudonymization
        ↓
  Chunking (Section-aware + Sliding Window)
        ↓
  Embedding & Vector Storage + BM25 Index

QUERY PIPELINE
  User Query
        ↓
  Query Classifier  ← Runs FIRST (critical requirement)
        ↓
  Query Expander (Medical Synonyms, Abbreviations)
        ↓
  Query Router
    ├─ STRUCTURED → FHIR/HL7 Direct Query (no vector search)
    └─ UNSTRUCTURED → Hybrid Retrieval
                         ├─ Dense (Vector)
                         └─ Sparse (BM25)
                              ↓
                         Reciprocal Rank Fusion
                              ↓
                         Cross-Encoder Reranking
                              ↓
  [Layer 2] PII Guard (Prompt Assembly)
        ↓
  LLM Generation (Claude Sonnet)
        ↓
  [Layer 3] Output PII Scan ← CRITICAL last line of defense
        ↓
  Confidence Scoring
        ↓
  Feedback Loop ──────────────────────────────→ Re-retrieve if low confidence
        ↓
  Cache Result → Return to User
```

---

## Key Features

| Feature | Description |
|---------|-------------|
| **3-Layer PII Protection** | Ingestion + Prompt Assembly + Output scan |
| **HIPAA Compliance** | Audit trail, encryption, 7-year retention |
| **Hybrid Retrieval** | Dense (vector) + Sparse (BM25) + RRF fusion |
| **Query Intelligence** | Auto-classify, route, and expand medical queries |
| **Structured Data Path** | FHIR/HL7 bypass vector search entirely |
| **Feedback Loop** | Auto-retry with expanded query on low confidence |
| **Semantic Cache** | Cache with document-based invalidation |
| **Document Versioning** | Track amendments with full audit trail |
| **Multi-Format Support** | Text, PDF, DICOM, HL7, FHIR |

---

## Project Structure

```
clinical-rag/
├── src/
│   ├── ingestion/
│   │   ├── loaders.py          # Document loaders (Text, PDF, DICOM, HL7, FHIR)
│   │   ├── pii_detection.py    # PII detection & pseudonymization (Layer 1)
│   │   ├── chunking.py         # Section-aware chunking
│   │   └── embedding.py        # Embeddings + in-memory vector store
│   ├── query/
│   │   ├── classifier.py       # Query type classifier (runs first)
│   │   ├── router.py           # Route to retrieval strategy
│   │   └── expander.py         # Medical synonym expansion
│   ├── retrieval/
│   │   ├── dense.py            # Dense vector retrieval
│   │   ├── sparse.py           # BM25 sparse retrieval
│   │   ├── hybrid.py           # Reciprocal Rank Fusion
│   │   └── reranker.py         # Cross-encoder reranking
│   ├── generation/
│   │   ├── prompt.py           # Prompt construction + PII guard (Layer 2)
│   │   └── llm.py              # Claude API client with retry
│   ├── post_processing/
│   │   ├── confidence.py       # Answer confidence scoring
│   │   ├── validation.py       # Output PII scan (Layer 3) + validation
│   │   └── feedback_loop.py    # Re-retrieval on low confidence
│   ├── structured/
│   │   ├── fhir_parser.py      # FHIR R4 parser
│   │   ├── hl7_parser.py       # HL7 v2.x parser
│   │   └── query_builder.py    # Structured query builder
│   ├── cache/
│   │   └── semantic_cache.py   # Semantic cache + invalidation
│   ├── observability/
│   │   ├── logging_config.py   # Structured logging
│   │   ├── metrics.py          # System metrics
│   │   └── audit.py            # HIPAA audit trail
│   └── pipeline.py             # Main orchestrator
├── tests/
│   ├── unit/                   # Component tests
│   ├── integration/            # End-to-end tests
│   └── pii_audit/              # CRITICAL: PII leakage tests (must be 0%)
├── config/
│   └── config.yaml             # System configuration
├── database/
│   └── schema.sql              # PostgreSQL schema
├── .env.example                # Environment variables template
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## Configuration

All configuration lives in `config/config.yaml` and can be overridden by environment variables.

### Critical Settings

```yaml
# config/config.yaml
databases:
  vector_db:
    type: "in_memory"   # Change to "pinecone" for production

llm:
  provider: "anthropic"
  anthropic:
    model: "claude-sonnet-4-5-20250929"

ingestion:
  pii:
    pseudonymization:
      salt: "${PII_SALT}"   # MUST be set via environment variable
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | For real LLM | Claude API key |
| `PII_SALT` | **Critical** | Salt for PII hashing (keep secret!) |
| `POSTGRES_PASSWORD` | Production | Database password |
| `REDIS_PASSWORD` | Production | Cache password |
| `PINECONE_API_KEY` | Production | Vector DB API key |

---

## Running with Docker

```bash
# Copy environment file
cp .env.example .env
# Edit .env with your values

# Build and run
docker-compose up -d

# Check logs
docker-compose logs -f clinical-rag
```

---

## Security

### 3-Layer PII Protection (Zero Tolerance)

```
Layer 1 (Ingestion):  PII detected and pseudonymized BEFORE storage
Layer 2 (Prompt):     PII guard scans context BEFORE sending to LLM
Layer 3 (Output):     PII scan on LLM response BEFORE returning to user
```

**CRITICAL**: PII leakage rate must be **0.00%**. Run PII audit before every deployment:
```bash
pytest tests/pii_audit/ -v
```

### HIPAA Compliance

- All patient data access logged to immutable audit trail
- 7-year audit log retention
- Encryption at rest (AES-256-GCM) and in transit (TLS 1.3)
- Patient-level access control prevents cross-patient data leakage
- No PII stored in vector database or application logs

---

## Testing

```bash
# Run all tests with coverage
pytest --cov=src tests/ -v

# Unit tests (fast, no dependencies)
pytest tests/unit/ -v

# CRITICAL: PII audit (must pass 0% leakage)
pytest tests/pii_audit/ -v

# Integration tests
pytest tests/integration/ -v
```

### Target Metrics

| Metric | Target | Critical |
|--------|--------|----------|
| Answer Accuracy (F1) | > 0.85 | Yes |
| Retrieval Recall@5 | > 0.90 | Yes |
| **PII Leakage Rate** | **0.00%** | **CRITICAL** |
| Avg Latency | < 500ms | Yes |
| Cache Hit Rate | > 0.30 | No |
| Confidence > 0.7 | > 0.80 | Yes |

---

## Supported Query Types

| Type | Example | Retrieval Strategy |
|------|---------|-------------------|
| Factual Lookup | "What medications is the patient on?" | Hybrid (k=5) |
| Explanation | "Why was the patient started on antibiotics?" | Dense only (k=10) |
| Comparison | "How did vitals change from admission to discharge?" | Hybrid + temporal sort |
| Multi-hop | "Was the treatment consistent with the diagnosis?" | Iterative retrieval |
| Summarization | "Summarize the hospital course" | Document-level (k=50) |
| Temporal | "What happened on January 15th?" | Hybrid + date filter |
| Structured | "List all lab values from last week" | Direct DB query (no vectors) |

---

## Production Deployment

See [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) for full deployment instructions including:
- AWS infrastructure with Terraform
- Kubernetes manifests
- Database initialization
- Security hardening
- Monitoring setup (Prometheus + Grafana)
- Go-live checklist

### Pre-Production Checklist

- [ ] 3-layer PII protection tested (0% leakage rate)
- [ ] Feedback loop closes back to retrieval
- [ ] FHIR/HL7 bypass vector search
- [ ] Document versioning working
- [ ] Cache invalidation on document updates
- [ ] Patient-level filtering enforced
- [ ] Query classifier runs before retrieval
- [ ] Audit trail capturing all access
- [ ] Load tests passing (100 req/min)
- [ ] Security audit complete

---

## Troubleshooting

**High latency**
- Enable caching (`cache_enabled=True`)
- Reduce retrieval `k` parameter
- Scale embedding service

**Low confidence scores**
- Enable query expansion (`QueryExpander`)
- Increase retrieval k
- Check document coverage

**PII detected in output**
- CRITICAL: Check all 3 layers are active
- Review PII detection patterns
- Audit affected queries immediately

**No results returned**
- Check patient_id filtering
- Verify documents are ingested
- Check embedding store size: `pipeline.get_metrics()['store_size']`

---

## License

[Specify your license]

---

Built for Healthcare. Designed for Safety. Optimized for Performance.
