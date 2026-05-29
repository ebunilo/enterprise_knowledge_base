# Enterprise RAG System - Phase 1 Deployment Guide

**Version:** 1.0  
**Phase:** 1 - Core Infrastructure  
**Last Updated:** 2026-05-17

---

## Overview

This guide covers the deployment of Phase 1 infrastructure components:

- **PostgreSQL 15+** - Canonical database with Row-Level Security (RLS)
- **MinIO** - S3-compatible object storage for documents
- **Redis 7+** - Caching and session management
- **Canonical DB Agent API** - Document and chunk management
- **Auth ACL Agent API** - Authentication and access control

---

## Prerequisites

### System Requirements

**Minimum (Development):**

- 4 CPU cores
- 8GB RAM
- 50GB disk space
- Docker 20.10+
- Docker Compose 2.0+

**Recommended (Production):**

- 8 CPU cores
- 16GB RAM
- 200GB SSD storage
- Docker 20.10+
- Docker Compose 2.0+
- Nginx with Let's Encrypt
- Domain name with DNS configured

### Software Requirements

- Docker Engine 20.10 or later
- Docker Compose 2.0 or later
- OpenSSL (for generating secrets)
- curl (for health checks)
- Git (for deployment)

---

## Quick Start (Local Development)

### 1. Clone Repository

```bash
git clone https://github.com/your-org/enterprise-rag-system.git
cd enterprise-rag-system/infra/docker-compose
```

### 2. Create Environment File

```bash
cp .env.example .env
```

### 3. Generate Secure Passwords

```bash
# Generate PostgreSQL password
export POSTGRES_PASSWORD=$(openssl rand -base64 32)
echo "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" >> .env

# Generate MinIO password
export MINIO_ROOT_PASSWORD=$(openssl rand -base64 32)
echo "MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}" >> .env

# Generate Redis password
export REDIS_PASSWORD=$(openssl rand -base64 32)
echo "REDIS_PASSWORD=${REDIS_PASSWORD}" >> .env

# Generate secret key
export SECRET_KEY=$(openssl rand -hex 32)
echo "SECRET_KEY=${SECRET_KEY}" >> .env
```

### 4. Configure OIDC Provider

Edit `.env` and set your OAuth2/OIDC provider details:

```bash
OIDC_PROVIDER_URL=https://your-oidc-provider.com
OIDC_CLIENT_ID=your-client-id
OIDC_CLIENT_SECRET=your-client-secret
```

### 5. Start Services

```bash
# Start infrastructure services only
docker-compose up -d postgres redis minio

# Wait for services to be healthy
docker-compose ps

# Start API services
docker-compose up -d canonical-db-api auth-acl-api
```

### 6. Verify Deployment

```bash
# Check service health
curl http://localhost:8001/health  # Canonical DB API
curl http://localhost:8002/health  # Auth ACL API

# Check PostgreSQL
docker-compose exec postgres psql -U rag_admin -d enterprise_rag -c "\dt"

# Check MinIO
curl http://localhost:9000/minio/health/live

# Check Redis
docker-compose exec redis redis-cli ping
```

### 7. Access Services

- **Canonical DB API:** http://localhost:8001
- **Auth ACL API:** http://localhost:8002
- **MinIO Console:** http://localhost:9001
- **PostgreSQL:** localhost:5432
- **Redis:** localhost:6379

---

## Production Deployment

### 1. Server Preparation

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Create deployment directory
sudo mkdir -p /opt/enterprise-rag
sudo chown $USER:$USER /opt/enterprise-rag
```

### 2. Configure Nginx with Let's Encrypt

```bash
# Install Nginx and Certbot
sudo apt install nginx certbot python3-certbot-nginx -y

# Copy Nginx configuration
sudo cp ../nginx/nginx.conf /etc/nginx/sites-available/enterprise-rag

# Update domain in configuration
sudo sed -i 's/${DOMAIN}/your-domain.com/g' /etc/nginx/sites-available/enterprise-rag
sudo sed -i 's/${NGINX_CLIENT_MAX_BODY_SIZE:-100M}/100M/g' /etc/nginx/sites-available/enterprise-rag

# Enable site
sudo ln -s /etc/nginx/sites-available/enterprise-rag /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Obtain SSL certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Reload Nginx
sudo systemctl reload nginx
```

### 3. Deploy Application

```bash
cd /opt/enterprise-rag

# Clone repository
git clone https://github.com/your-org/enterprise-rag-system.git .

# Navigate to docker-compose directory
cd infra/docker-compose

# Create production .env file
cp .env.example .env

# Generate production secrets
./scripts/generate-secrets.sh production

# Configure OIDC provider
nano .env  # Edit OIDC settings

# Start services
docker-compose up -d

# Check logs
docker-compose logs -f
```

### 4. Verify Production Deployment

```bash
# Check service health
curl https://your-domain.com/health
curl https://your-domain.com/api/canonical-db/health
curl https://your-domain.com/api/auth-acl/health

# Check SSL certificate
curl -vI https://your-domain.com 2>&1 | grep -i "SSL certificate"

# Check all containers are running
docker-compose ps
```

---

## Configuration

### Environment Variables

See `.env.example` for all available configuration options.

**Critical Settings:**

```bash
# Environment
ENVIRONMENT=production

# Database
POSTGRES_PASSWORD=<strong-password>

# Object Storage
MINIO_ROOT_PASSWORD=<strong-password>

# Cache
REDIS_PASSWORD=<strong-password>

# Security
SECRET_KEY=<strong-secret>

# OIDC
OIDC_PROVIDER_URL=<your-provider>
OIDC_CLIENT_ID=<your-client-id>
OIDC_CLIENT_SECRET=<your-client-secret>

# Domain
DOMAIN=your-domain.com
SSL_ENABLED=true
```

### PostgreSQL Configuration

PostgreSQL is configured for production workloads in `postgres/conf/postgresql.conf`:

- **Shared Buffers:** 2GB (25% of RAM)
- **Effective Cache Size:** 6GB (75% of RAM)
- **Work Memory:** 16MB per operation
- **Maintenance Work Memory:** 512MB
- **Max Connections:** 200
- **Row-Level Security:** Enabled

To customize, edit `postgres/conf/postgresql.conf` before deployment.

### Resource Limits

Default resource limits in `docker-compose.yml`:

```yaml
postgres:
  deploy:
    resources:
      limits:
        cpus: "2"
        memory: 4G

minio:
  deploy:
    resources:
      limits:
        cpus: "1"
        memory: 2G

redis:
  deploy:
    resources:
      limits:
        cpus: "0.5"
        memory: 1G
```

Adjust based on your workload.

---

## Database Management

### Accessing PostgreSQL

```bash
# Using docker-compose
docker-compose exec postgres psql -U rag_admin -d enterprise_rag

# Using psql client
psql -h localhost -p 5432 -U rag_admin -d enterprise_rag
```

### Common Database Operations

```sql
-- List all tables
\dt

-- Check table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Check RLS policies
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual
FROM pg_policies
WHERE schemaname = 'public';

-- Check active connections
SELECT count(*) FROM pg_stat_activity;

-- Check database size
SELECT pg_size_pretty(pg_database_size('enterprise_rag'));
```

### Database Backup

```bash
# Manual backup
docker-compose exec postgres pg_dump -U rag_admin enterprise_rag > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore from backup
docker-compose exec -T postgres psql -U rag_admin -d enterprise_rag < backup_20260517_120000.sql
```

### Automated Backups

Backups are configured in `.env`:

```bash
BACKUP_ENABLED=true
BACKUP_SCHEDULE=0 2 * * *  # Daily at 2 AM UTC
BACKUP_RETENTION_DAYS=30
```

Backups are stored in `./backups/` directory.

---

## MinIO Management

### Accessing MinIO Console

Navigate to: `https://your-domain.com/storage-console/`

Or locally: `http://localhost:9001`

Login with:

- **Username:** Value of `MINIO_ROOT_USER`
- **Password:** Value of `MINIO_ROOT_PASSWORD`

### Creating Buckets

```bash
# Using MinIO client (mc)
docker run --rm -it --network enterprise-rag_rag_network \
  minio/mc alias set myminio http://minio:9000 minioadmin <password>

docker run --rm -it --network enterprise-rag_rag_network \
  minio/mc mb myminio/enterprise-rag-documents

docker run --rm -it --network enterprise-rag_rag_network \
  minio/mc mb myminio/enterprise-rag-backups
```

### S3-Compatible Access

MinIO is S3-compatible. Use any S3 client:

```python
import boto3

s3_client = boto3.client(
    's3',
    endpoint_url='https://storage.your-domain.com',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='<password>'
)

# List buckets
buckets = s3_client.list_buckets()
```

---

## Monitoring and Logs

### Viewing Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f postgres
docker-compose logs -f canonical-db-api

# Last 100 lines
docker-compose logs --tail=100 postgres
```

### Service Status

```bash
# Check running containers
docker-compose ps

# Check resource usage
docker stats

# Check service health
docker-compose ps | grep healthy
```

### PostgreSQL Monitoring

```sql
-- Active queries
SELECT pid, usename, application_name, state, query
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY query_start DESC;

-- Slow queries (from pg_stat_statements)
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;

-- Table statistics
SELECT schemaname, tablename, n_live_tup, n_dead_tup, last_vacuum, last_autovacuum
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;
```

---

## Troubleshooting

### Services Won't Start

```bash
# Check logs
docker-compose logs

# Check disk space
df -h

# Check Docker daemon
sudo systemctl status docker

# Restart Docker
sudo systemctl restart docker
```

### PostgreSQL Connection Issues

```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# Check PostgreSQL logs
docker-compose logs postgres

# Test connection
docker-compose exec postgres pg_isready -U rag_admin

# Check network
docker network inspect enterprise-rag_rag_network
```

### MinIO Access Issues

```bash
# Check MinIO logs
docker-compose logs minio

# Check MinIO health
curl http://localhost:9000/minio/health/live

# Verify credentials
docker-compose exec minio printenv | grep MINIO
```

### API Services Not Responding

```bash
# Check API logs
docker-compose logs canonical-db-api
docker-compose logs auth-acl-api

# Check if services are healthy
docker-compose ps

# Restart services
docker-compose restart canonical-db-api auth-acl-api
```

### SSL Certificate Issues

```bash
# Check certificate expiry
sudo certbot certificates

# Renew certificate
sudo certbot renew

# Test Nginx configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

---

## Maintenance

### Updating Services

```bash
# Pull latest images
docker-compose pull

# Restart services with new images
docker-compose up -d

# Remove old images
docker image prune -a
```

### Database Maintenance

```bash
# Vacuum database
docker-compose exec postgres psql -U rag_admin -d enterprise_rag -c "VACUUM ANALYZE;"

# Reindex database
docker-compose exec postgres psql -U rag_admin -d enterprise_rag -c "REINDEX DATABASE enterprise_rag;"

# Check for bloat
docker-compose exec postgres psql -U rag_admin -d enterprise_rag -c "
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

### Rotating Secrets

```bash
# Generate new secrets
./scripts/generate-secrets.sh production

# Update .env file
nano .env

# Restart services
docker-compose restart
```

---

## Security Best Practices

1. **Use Strong Passwords:** Generate with `openssl rand -base64 32`
2. **Enable SSL/TLS:** Always use HTTPS in production
3. **Restrict Network Access:** Use firewall rules
4. **Regular Updates:** Keep Docker and images updated
5. **Monitor Logs:** Check for suspicious activity
6. **Backup Regularly:** Automate database backups
7. **Rotate Secrets:** Change passwords periodically
8. **Limit Permissions:** Use least privilege principle
9. **Enable Audit Logging:** Track all access
10. **Use Private Networks:** Isolate services

---

## Performance Tuning

### PostgreSQL

```bash
# Adjust shared_buffers (25% of RAM)
# Edit postgres/conf/postgresql.conf
shared_buffers = 4GB  # For 16GB RAM

# Adjust effective_cache_size (75% of RAM)
effective_cache_size = 12GB  # For 16GB RAM

# Restart PostgreSQL
docker-compose restart postgres
```

### Redis

```bash
# Adjust maxmemory
# Edit docker-compose.yml
command: >
  redis-server
  --maxmemory 2gb
  --maxmemory-policy allkeys-lru

# Restart Redis
docker-compose restart redis
```

### API Services

```bash
# Adjust worker count (2-4 × CPU cores)
# Edit .env
API_WORKERS=8

# Restart API services
docker-compose restart canonical-db-api auth-acl-api
```

---

## Scaling

### Horizontal Scaling

```bash
# Scale API services
docker-compose up -d --scale canonical-db-api=3 --scale auth-acl-api=3

# Add load balancer (Nginx already configured)
```

### Vertical Scaling

```bash
# Increase resource limits in docker-compose.yml
postgres:
  deploy:
    resources:
      limits:
        cpus: '4'
        memory: 8G

# Restart services
docker-compose up -d
```

---

## Support

For issues and questions:

- **Documentation:** `/docs`
- **GitHub Issues:** https://github.com/your-org/enterprise-rag-system/issues
- **Email:** support@your-domain.com

---

## Next Steps

After Phase 1 deployment:

1. **Verify all services are healthy**
2. **Configure OIDC authentication**
3. **Create test users and tenants**
4. **Test API endpoints**
5. **Set up monitoring and alerting**
6. **Proceed to Phase 2: Ingestion Pipeline**

---

**Deployment Status:** ✅ Phase 1 Complete  
**Next Phase:** Phase 2 - Document Ingestion (Weeks 5-8)
