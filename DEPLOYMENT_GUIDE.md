# Clinical RAG System - Deployment Guide

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Infrastructure Setup](#infrastructure-setup)
3. [Database Initialization](#database-initialization)
4. [Service Deployment](#service-deployment)
5. [Configuration](#configuration)
6. [Security Hardening](#security-hardening)
7. [Monitoring Setup](#monitoring-setup)
8. [Testing & Validation](#testing--validation)
9. [Go-Live Checklist](#go-live-checklist)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Tools
- Docker 20.10+
- Kubernetes 1.24+ or AWS ECS
- Terraform 1.0+ (for infrastructure)
- kubectl CLI
- AWS CLI or Azure CLI
- PostgreSQL 14+
- Redis 6.2+
- Python 3.9+

### Required Accounts
- AWS Account (or Azure/GCP)
- Anthropic API key
- Pinecone account (or Milvus/Weaviate)
- Domain and SSL certificates

### Estimated Costs (Monthly)
- Compute: $2,000 - $5,000
- Databases: $1,500 - $3,000
- Vector DB: $500 - $1,500
- LLM API calls: $500 - $2,000
- Storage: $200 - $500
- **Total: $4,700 - $12,000/month**

---

## Infrastructure Setup

### 1. AWS Infrastructure (Terraform)

Create `infrastructure/main.tf`:

```hcl
provider "aws" {
  region = "us-west-2"
}

# VPC
module "vpc" {
  source = "terraform-aws-modules/vpc/aws"

  name = "clinical-rag-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["us-west-2a", "us-west-2b", "us-west-2c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  enable_vpn_gateway = false

  tags = {
    Environment = "production"
    Project     = "clinical-rag"
  }
}

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "clinical-rag-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# RDS PostgreSQL
resource "aws_db_instance" "postgres" {
  identifier = "clinical-rag-postgres"

  engine         = "postgres"
  engine_version = "14.7"
  instance_class = "db.r5.xlarge"

  allocated_storage     = 1000
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "clinical_rag"
  username = var.postgres_username
  password = var.postgres_password

  vpc_security_group_ids = [aws_security_group.postgres.id]
  db_subnet_group_name   = aws_db_subnet_group.postgres.name

  backup_retention_period = 30
  backup_window          = "03:00-04:00"
  maintenance_window     = "sun:04:00-sun:05:00"

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  tags = {
    Name        = "clinical-rag-postgres"
    Environment = "production"
  }
}

# ElastiCache Redis
resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "clinical-rag-redis"
  engine               = "redis"
  engine_version       = "6.2"
  node_type            = "cache.r5.xlarge"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis6.x"

  subnet_group_name    = aws_elasticache_subnet_group.redis.name
  security_group_ids   = [aws_security_group.redis.id]

  snapshot_retention_limit = 5
  snapshot_window         = "03:00-04:00"

  tags = {
    Name        = "clinical-rag-redis"
    Environment = "production"
  }
}

# S3 Bucket for document storage
resource "aws_s3_bucket" "documents" {
  bucket = "clinical-rag-documents-${var.account_id}"

  tags = {
    Name        = "clinical-rag-documents"
    Environment = "production"
  }
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_encryption" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Secrets Manager
resource "aws_secretsmanager_secret" "api_keys" {
  name = "clinical-rag/api-keys"

  tags = {
    Environment = "production"
  }
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "app" {
  name              = "/aws/clinical-rag/app"
  retention_in_days = 90

  tags = {
    Environment = "production"
  }
}
```

Deploy:
```bash
cd infrastructure
terraform init
terraform plan
terraform apply
```

### 2. Kubernetes Deployment (Alternative to ECS)

Create `k8s/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: clinical-rag-api
  namespace: clinical-rag
spec:
  replicas: 3
  selector:
    matchLabels:
      app: clinical-rag-api
  template:
    metadata:
      labels:
        app: clinical-rag-api
    spec:
      containers:
      - name: api
        image: clinical-rag/api:1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: POSTGRES_HOST
          valueFrom:
            configMapKeyRef:
              name: clinical-rag-config
              key: postgres_host
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: clinical-rag-secrets
              key: postgres_password
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: clinical-rag-api
  namespace: clinical-rag
spec:
  type: LoadBalancer
  ports:
  - port: 443
    targetPort: 8000
    protocol: TCP
  selector:
    app: clinical-rag-api
```

Deploy:
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

---

## Database Initialization

### 1. PostgreSQL Setup

```bash
# Connect to PostgreSQL
psql -h <postgres_host> -U postgres -d clinical_rag

# Run schema creation
\i database/schema.sql
\i database/indexes.sql
\i database/views.sql

# Create roles
CREATE ROLE clinical_rag_app WITH LOGIN PASSWORD '<secure_password>';
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO clinical_rag_app;

CREATE ROLE clinical_rag_readonly WITH LOGIN PASSWORD '<secure_password>';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO clinical_rag_readonly;

# Verify
\dt
\di
```

Database files in `database/`:

**schema.sql**:
```sql
-- Use schemas from DATA_SCHEMAS.md
-- documents table
-- chunks table
-- fhir_resources table
-- medications table
-- observations table
-- conditions table
-- procedures table
-- pii_mappings table
-- audit_log table
-- query_log table
```

**indexes.sql**:
```sql
-- All indexes from DATA_SCHEMAS.md
```

### 2. Vector Database Setup

#### Pinecone:
```python
import pinecone

pinecone.init(
    api_key="<your_api_key>",
    environment="us-west1-gcp"
)

# Create index
pinecone.create_index(
    name="clinical-chunks",
    dimension=384,
    metric="cosine",
    pods=2,
    replicas=1,
    metadata_config={
        "indexed": ["patient_id", "document_type", "document_date", "status"]
    }
)
```

#### Milvus (self-hosted):
```python
from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection

# Connect
connections.connect(host="localhost", port="19530")

# Define schema
fields = [
    FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
    FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=384),
    FieldSchema(name="patient_id", dtype=DataType.VARCHAR, max_length=50),
    FieldSchema(name="document_type", dtype=DataType.VARCHAR, max_length=50),
    FieldSchema(name="document_date", dtype=DataType.VARCHAR, max_length=20),
    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=10000)
]

schema = CollectionSchema(fields=fields, description="Clinical document chunks")

# Create collection
collection = Collection(name="clinical_chunks", schema=schema)

# Create index
index_params = {
    "index_type": "HNSW",
    "metric_type": "L2",
    "params": {"M": 16, "efConstruction": 200}
}
collection.create_index(field_name="vector", index_params=index_params)

# Load collection
collection.load()
```

### 3. Elasticsearch Setup

```bash
# Create index
curl -X PUT "localhost:9200/clinical_chunks" -H 'Content-Type: application/json' -d @elasticsearch/index_config.json

# Verify
curl -X GET "localhost:9200/clinical_chunks/_mapping"
```

---

## Service Deployment

### 1. Build Docker Images

**Dockerfile.api**:
```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY config/ ./config/

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and push:
```bash
# Build
docker build -f Dockerfile.api -t clinical-rag/api:1.0.0 .
docker build -f Dockerfile.worker -t clinical-rag/worker:1.0.0 .
docker build -f Dockerfile.embedding -t clinical-rag/embedding:1.0.0 .

# Tag
docker tag clinical-rag/api:1.0.0 <your-registry>/clinical-rag/api:1.0.0

# Push
docker push <your-registry>/clinical-rag/api:1.0.0
```

### 2. Deploy Services

Using Docker Compose (development):
```bash
docker-compose up -d
docker-compose ps
docker-compose logs -f api
```

Using Kubernetes (production):
```bash
kubectl apply -f k8s/
kubectl get pods -n clinical-rag
kubectl logs -f deployment/clinical-rag-api -n clinical-rag
```

Using AWS ECS:
```bash
aws ecs create-service \
  --cluster clinical-rag-cluster \
  --service-name clinical-rag-api \
  --task-definition clinical-rag-api:1 \
  --desired-count 3 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=DISABLED}"
```

---

## Configuration

### 1. Create Configuration File

```bash
# Copy example config
cp CONFIGURATION.yaml config/production.yaml

# Edit with production values
vim config/production.yaml
```

### 2. Set Environment Variables

Create `.env` file (DO NOT commit):
```bash
# Database
POSTGRES_USER=clinical_rag_app
POSTGRES_PASSWORD=<secure_password>
POSTGRES_HOST=postgres.clinical-rag.internal
POSTGRES_DB=clinical_rag

# Redis
REDIS_PASSWORD=<secure_password>
REDIS_HOST=redis.clinical-rag.internal

# Vector DB
PINECONE_API_KEY=<your_api_key>

# LLM
ANTHROPIC_API_KEY=<your_api_key>

# PII
PII_SALT=<random_secure_salt>
KEY_VAULT_URL=<your_key_vault_url>
ENCRYPTION_KEY_ID=<your_key_id>

# JWT
JWT_SECRET=<random_secure_secret>

# AWS
AWS_REGION=us-west-2
AWS_ACCESS_KEY_ID=<your_key>
AWS_SECRET_ACCESS_KEY=<your_secret>
```

### 3. Store Secrets Securely

AWS Secrets Manager:
```bash
aws secretsmanager create-secret \
  --name clinical-rag/postgres-password \
  --secret-string "<secure_password>"

aws secretsmanager create-secret \
  --name clinical-rag/anthropic-api-key \
  --secret-string "<your_api_key>"
```

---

## Security Hardening

### 1. Network Security

```bash
# Security groups (AWS)
aws ec2 authorize-security-group-ingress \
  --group-id sg-postgres \
  --protocol tcp \
  --port 5432 \
  --source-group sg-api

# Disable public access
aws rds modify-db-instance \
  --db-instance-identifier clinical-rag-postgres \
  --no-publicly-accessible
```

### 2. Enable Encryption

```bash
# RDS encryption (must be enabled at creation)
# S3 encryption
aws s3api put-bucket-encryption \
  --bucket clinical-rag-documents \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'
```

### 3. Configure TLS

```bash
# Generate certificate (or use ACM)
openssl req -x509 -newkey rsa:4096 \
  -keyout key.pem \
  -out cert.pem \
  -days 365 \
  -nodes

# Configure in load balancer
aws elbv2 create-listener \
  --load-balancer-arn <arn> \
  --protocol HTTPS \
  --port 443 \
  --certificates CertificateArn=<cert_arn> \
  --default-actions Type=forward,TargetGroupArn=<target_arn>
```

### 4. IAM Policies

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::clinical-rag-documents/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:clinical-rag/*"
    }
  ]
}
```

---

## Monitoring Setup

### 1. Prometheus

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'clinical-rag-api'
    static_configs:
      - targets: ['api:9090']
    metrics_path: '/metrics'
```

### 2. Grafana Dashboards

Import dashboards:
- Clinical RAG Overview
- Query Performance
- PII Audit Dashboard
- System Health

### 3. Alerting

```yaml
# alertmanager.yml
route:
  receiver: 'pagerduty'
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h

  routes:
    - match:
        severity: critical
      receiver: 'pagerduty'

    - match:
        severity: warning
      receiver: 'slack'

receivers:
  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: '<your_service_key>'

  - name: 'slack'
    slack_configs:
      - api_url: '<webhook_url>'
        channel: '#alerts'
```

---

## Testing & Validation

### 1. Health Checks

```bash
# API health
curl https://api.clinical-rag.example.com/health

# Database connectivity
psql -h <host> -U clinical_rag_app -d clinical_rag -c "SELECT 1"

# Redis connectivity
redis-cli -h <host> -a <password> ping

# Vector DB
python scripts/test_vector_db.py
```

### 2. Integration Tests

```bash
# Run test suite
pytest tests/integration/ -v

# Specific tests
pytest tests/integration/test_query_pipeline.py::test_end_to_end -v
```

### 3. Load Testing

```bash
# Using Locust
locust -f tests/load/locustfile.py \
  --host https://api.clinical-rag.example.com \
  --users 100 \
  --spawn-rate 10 \
  --run-time 10m
```

---

## Go-Live Checklist

### Pre-Launch

- [ ] Infrastructure provisioned and tested
- [ ] Databases initialized with schemas
- [ ] All services deployed and running
- [ ] Configuration verified
- [ ] Security hardening complete
- [ ] TLS/SSL certificates installed
- [ ] Monitoring and alerting configured
- [ ] Backup and disaster recovery tested
- [ ] Integration tests passing
- [ ] Load tests passing
- [ ] PII detection tested (leakage rate = 0%)
- [ ] Audit trail enabled and tested
- [ ] Documentation complete
- [ ] Team trained on system

### Launch Day

- [ ] Final smoke tests
- [ ] Monitor error rates
- [ ] Monitor latency
- [ ] Monitor PII detection alerts
- [ ] Check audit logs
- [ ] Verify cache hit rates
- [ ] On-call team ready

### Post-Launch (Week 1)

- [ ] Daily metric reviews
- [ ] Incident response readiness
- [ ] User feedback collection
- [ ] Performance optimization
- [ ] Documentation updates

---

## Troubleshooting

### Common Issues

**Issue: High Query Latency**
```bash
# Check database
SELECT * FROM pg_stat_activity WHERE state = 'active';

# Check vector DB performance
# Review query logs
tail -f /var/log/clinical-rag/query.log | grep latency_ms

# Solutions:
# - Increase database resources
# - Optimize indexes
# - Increase vector DB pods
# - Enable caching
```

**Issue: PII Leakage Detected**
```bash
# CRITICAL - Immediate action required
# 1. Check audit logs
SELECT * FROM audit_log WHERE event_type = 'pii_detected' ORDER BY timestamp DESC;

# 2. Review affected queries
# 3. Block affected users if necessary
# 4. Report to security team
# 5. Review PII detection patterns
```

**Issue: Cache Not Working**
```bash
# Check Redis connectivity
redis-cli -h <host> -a <password> ping

# Check cache stats
curl https://api.clinical-rag.example.com/cache/stats

# Clear cache if needed
curl -X POST https://api.clinical-rag.example.com/cache/clear \
  -H "Authorization: Bearer <token>" \
  -d '{"scope": "all"}'
```

**Issue: Service Crash**
```bash
# Check logs
kubectl logs deployment/clinical-rag-api -n clinical-rag --tail=100

# Check resources
kubectl top pods -n clinical-rag

# Restart if needed
kubectl rollout restart deployment/clinical-rag-api -n clinical-rag
```

---

## Rollback Procedure

If critical issues arise:

```bash
# 1. Immediate rollback
kubectl rollout undo deployment/clinical-rag-api -n clinical-rag

# 2. Or to specific revision
kubectl rollout history deployment/clinical-rag-api -n clinical-rag
kubectl rollout undo deployment/clinical-rag-api --to-revision=2 -n clinical-rag

# 3. Verify
kubectl rollout status deployment/clinical-rag-api -n clinical-rag

# 4. Check health
curl https://api.clinical-rag.example.com/health
```

---

## Support Contacts

- **On-Call Engineer**: oncall@clinical-rag.example.com
- **Security Team**: security@clinical-rag.example.com
- **Infrastructure Team**: infra@clinical-rag.example.com

---

END OF DEPLOYMENT GUIDE

