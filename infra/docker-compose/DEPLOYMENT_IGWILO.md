# Deployment Guide for igwilo.com Server

**Server:** igwilo.com  
**SSL Certificate:** Wildcard certificate already configured  
**Date:** 2026-05-18  
**Phase:** 1 - Core Infrastructure

---

## Pre-Deployment Checklist

### ✅ Server Prerequisites (Already Configured)

- [x] Nginx installed and running
- [x] Let's Encrypt wildcard certificate for igwilo.com
  - Certificate: `/etc/letsencrypt/live/igwilo.com/fullchain.pem`
  - Private key: `/etc/letsencrypt/live/igwilo.com/privkey.pem`
  - Auto-renewal: Configured
- [x] Docker installed
- [x] Docker Compose installed

### 📋 Required Actions

- [ ] Configure OIDC provider
- [ ] Generate production secrets
- [ ] Deploy Docker Compose services
- [ ] Configure Nginx for RAG subdomain
- [ ] Test deployment

---

## Step 1: Prepare Deployment Directory

```bash
# Create deployment directory
sudo mkdir -p /opt/enterprise-rag
sudo chown $USER:$USER /opt/enterprise-rag

# Clone repository
cd /opt/enterprise-rag
git clone <your-repo-url> .

# Navigate to docker-compose directory
cd infra/docker-compose
```

---

## Step 2: Generate Production Secrets

```bash
# Make script executable
chmod +x scripts/generate-secrets.sh

# Generate production secrets
./scripts/generate-secrets.sh production

# This creates .env.production with secure passwords
```

---

## Step 3: Configure OIDC Provider

Edit `.env.production` and configure your OAuth2/OIDC provider:

```bash
nano .env.production
```

**Update these values:**

```bash
# OIDC Configuration
OIDC_PROVIDER_URL=https://your-oidc-provider.com
# Examples:
# - Okta: https://dev-12345.okta.com/oauth2/default
# - Auth0: https://your-tenant.auth0.com
# - Azure AD: https://login.microsoftonline.com/your-tenant-id/v2.0
# - Keycloak: https://keycloak.yourdomain.com/realms/your-realm

OIDC_CLIENT_ID=your-client-id-here
OIDC_CLIENT_SECRET=your-client-secret-here

# Domain Configuration
DOMAIN=igwilo.com
ALLOWED_ORIGINS=https://rag.igwilo.com,https://storage.igwilo.com

# SSL Configuration (already configured)
SSL_ENABLED=true
LETSENCRYPT_EMAIL=admin@igwilo.com

# Environment
ENVIRONMENT=production
```

**Save and exit:** `Ctrl+X`, then `Y`, then `Enter`

---

## Step 4: Configure Nginx for RAG Subdomain

### Option A: Add to Existing Nginx Configuration

```bash
# Copy RAG Nginx configuration
sudo cp ../nginx/nginx.conf /etc/nginx/sites-available/rag.igwilo.com

# Create symbolic link
sudo ln -s /etc/nginx/sites-available/rag.igwilo.com /etc/nginx/sites-enabled/

# Test Nginx configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

### Option B: Include in Main Configuration

```bash
# Edit main Nginx configuration
sudo nano /etc/nginx/nginx.conf

# Add this line in the http block:
# include /opt/enterprise-rag/infra/nginx/nginx.conf;

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

---

## Step 5: Deploy Docker Compose Services

```bash
# Start services
docker-compose --env-file .env.production up -d

# Check service status
docker-compose ps

# Expected output:
# NAME                              STATUS
# enterprise-rag-postgres           Up (healthy)
# enterprise-rag-redis              Up (healthy)
# enterprise-rag-minio              Up (healthy)
# enterprise-rag-canonical-db-api   Up (healthy)
# enterprise-rag-auth-acl-api       Up (healthy)
```

---

## Step 6: Verify Deployment

### Check Service Health

```bash
# Check all containers are running
docker-compose ps

# Check logs
docker-compose logs -f

# Check individual service logs
docker-compose logs postgres
docker-compose logs redis
docker-compose logs minio
```

### Test Endpoints

```bash
# Test main health endpoint
curl https://rag.igwilo.com/health

# Expected response:
# {"status":"healthy","timestamp":"2026-05-18T07:00:00Z","service":"enterprise-rag"}

# Test Canonical DB API
curl https://rag.igwilo.com/api/canonical-db/health

# Test Auth ACL API
curl https://rag.igwilo.com/api/auth-acl/health

# Test MinIO (should require authentication)
curl https://storage.igwilo.com/minio/health/live
```

### Verify Database

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U rag_admin -d enterprise_rag

# Check tables
\dt

# Expected tables:
# - tenants
# - users
# - document_sources
# - documents
# - document_chunks
# - access_policies
# - ingestion_jobs
# - audit_logs (partitioned)

# Check default tenant
SELECT tenant_name, tenant_slug FROM tenants;

# Check system admin
SELECT email, role FROM users WHERE role = 'SUPER_ADMIN';

# Exit
\q
```

### Verify MinIO

```bash
# Access MinIO Console
# Open browser: https://rag.igwilo.com/storage-console/

# Login with credentials from .env.production:
# Username: Value of MINIO_ROOT_USER
# Password: Value of MINIO_ROOT_PASSWORD
```

---

## Step 7: Configure DNS (If Not Already Done)

Add DNS records for:

```
rag.igwilo.com      A     <your-server-ip>
storage.igwilo.com  A     <your-server-ip>
```

Or use CNAME if you prefer:

```
rag.igwilo.com      CNAME igwilo.com
storage.igwilo.com  CNAME igwilo.com
```

---

## Step 8: Test SSL Certificate

```bash
# Test SSL certificate
curl -vI https://rag.igwilo.com 2>&1 | grep -i "SSL certificate"

# Check certificate details
openssl s_client -connect rag.igwilo.com:443 -servername rag.igwilo.com < /dev/null 2>/dev/null | openssl x509 -noout -text | grep -A2 "Subject Alternative Name"

# Should show:
# DNS:*.igwilo.com, DNS:igwilo.com
```

---

## Step 9: Create Test Tenant and User

```bash
# Connect to database
docker-compose exec postgres psql -U rag_admin -d enterprise_rag

# Create test tenant
INSERT INTO tenants (tenant_name, tenant_slug, default_language, timezone)
VALUES ('Test Organization', 'test-org', 'en', 'UTC');

# Create test user
INSERT INTO users (
    tenant_id,
    email,
    username,
    full_name,
    role,
    clearance_level,
    is_active,
    is_verified
)
SELECT
    tenant_id,
    'testuser@igwilo.com',
    'testuser',
    'Test User',
    'USER',
    'INTERNAL_GENERAL',
    true,
    true
FROM tenants WHERE tenant_slug = 'test-org';

# Exit
\q
```

---

## Step 10: Monitor Services

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f postgres

# Last 100 lines
docker-compose logs --tail=100 postgres
```

### Check Resource Usage

```bash
# Docker stats
docker stats

# Disk usage
df -h

# Check PostgreSQL size
docker-compose exec postgres psql -U rag_admin -d enterprise_rag -c "SELECT pg_size_pretty(pg_database_size('enterprise_rag'));"
```

---

## Troubleshooting

### Services Won't Start

```bash
# Check Docker daemon
sudo systemctl status docker

# Check logs
docker-compose logs

# Restart services
docker-compose restart

# Full restart
docker-compose down
docker-compose up -d
```

### Nginx Errors

```bash
# Check Nginx configuration
sudo nginx -t

# Check Nginx logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/rag_error.log

# Restart Nginx
sudo systemctl restart nginx
```

### Database Connection Issues

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

### SSL Certificate Issues

```bash
# Check certificate
sudo certbot certificates

# Renew certificate (if needed)
sudo certbot renew

# Test renewal
sudo certbot renew --dry-run
```

---

## Maintenance

### Backup Database

```bash
# Manual backup
docker-compose exec postgres pg_dump -U rag_admin enterprise_rag > backup_$(date +%Y%m%d_%H%M%S).sql

# Compress backup
gzip backup_*.sql
```

### Update Services

```bash
# Pull latest images
docker-compose pull

# Restart with new images
docker-compose up -d

# Remove old images
docker image prune -a
```

### Rotate Secrets

```bash
# Generate new secrets
./scripts/generate-secrets.sh production

# Update .env.production
nano .env.production

# Restart services
docker-compose restart
```

---

## Security Checklist

- [x] SSL/TLS enabled with wildcard certificate
- [x] Strong passwords generated for all services
- [x] Row-Level Security (RLS) enabled in PostgreSQL
- [x] Nginx rate limiting configured
- [x] Security headers configured
- [x] Firewall configured (ports 80, 443, 22 only)
- [ ] OIDC authentication configured
- [ ] Regular backups scheduled
- [ ] Monitoring and alerting configured
- [ ] Audit logging enabled

---

## Next Steps

1. **Configure OIDC Provider:**
   - Create OAuth2/OIDC application
   - Configure redirect URIs
   - Update .env.production

2. **Set Up Monitoring:**
   - Configure Prometheus (Phase 6)
   - Set up Grafana dashboards (Phase 6)
   - Configure alerts (Phase 6)

3. **Schedule Backups:**
   - Set up automated database backups
   - Configure MinIO backup
   - Test restore procedures

4. **Proceed to Phase 2:**
   - Implement document ingestion pipeline
   - Deploy document-ingestion-agent
   - Deploy document-parser-agent
   - Deploy chunking-agent

---

## Support

For issues:

- Check logs: `docker-compose logs -f`
- Review documentation: `/opt/enterprise-rag/infra/docker-compose/README.md`
- Check GitHub issues: <your-repo-url>/issues

---

## Quick Reference

### Service URLs

- **Main API:** https://rag.igwilo.com
- **Canonical DB API:** https://rag.igwilo.com/api/canonical-db/
- **Auth ACL API:** https://rag.igwilo.com/api/auth-acl/
- **MinIO Console:** https://rag.igwilo.com/storage-console/
- **MinIO API:** https://storage.igwilo.com

### Service Ports (Internal)

- PostgreSQL: 5432
- Redis: 6379
- MinIO API: 9000
- MinIO Console: 9001
- Canonical DB API: 8001
- Auth ACL API: 8002

### Important Files

- Environment: `/opt/enterprise-rag/infra/docker-compose/.env.production`
- Nginx Config: `/etc/nginx/sites-available/rag.igwilo.com`
- SSL Certificate: `/etc/letsencrypt/live/igwilo.com/fullchain.pem`
- Deployment Directory: `/opt/enterprise-rag`

---

**Deployment Status:** Ready for Production  
**Domain:** igwilo.com  
**Subdomains:** rag.igwilo.com, storage.igwilo.com  
**SSL:** Wildcard certificate configured  
**Phase:** 1 - Core Infrastructure
