# Deployment Troubleshooting Guide

## Current Issue: Logging Configuration Error

The canonical-db-api container is failing with a logging configuration error. The code has been fixed, but the Docker images need to be rebuilt.

## Manual Deployment Steps

### 1. SSH to the Server

```bash
ssh user@your-server
cd /home/user/enterprise_knowledge_base
```

### 2. Check Current Status

```bash
# Check running containers
docker compose ps

# Check logs
docker compose logs canonical-db-api --tail=50
docker compose logs auth-acl-api --tail=50
```

### 3. Rebuild and Restart

The issue is that the old Docker images are cached. You need to rebuild them:

```bash
# Stop all services
docker compose down

# Remove old images (force rebuild)
docker compose rm -f canonical-db-api auth-acl-api
docker rmi ekb-canonical-db-api ekb-auth-acl-api

# Rebuild images from scratch
docker compose build --no-cache canonical-db-api auth-acl-api

# Start all services
docker compose up -d

# Watch the logs
docker compose logs -f canonical-db-api
```

### 4. Verify the Fix

```bash
# Check if containers are healthy
docker compose ps

# Test health endpoints
curl http://localhost:9401/health
curl http://localhost:9402/health

# Check logs for errors
docker compose logs canonical-db-api | grep -i error
docker compose logs auth-acl-api | grep -i error
```

## Alternative: Force GitHub Actions to Rebuild

If you want GitHub Actions to rebuild the images, you need to either:

### Option 1: Clear Docker Build Cache on Server

```bash
ssh user@server
cd /home/user/enterprise_knowledge_base
docker compose down
docker system prune -a -f
```

Then trigger a new deployment from GitHub.

### Option 2: Add --build Flag to Workflow

The workflow currently uses `docker compose up -d` which doesn't rebuild if images exist. We can change it to force rebuild.

## Quick Fix Commands

```bash
# One-liner to rebuild and restart
cd /home/user/enterprise_knowledge_base && \
docker compose down && \
docker compose build --no-cache && \
docker compose up -d && \
docker compose ps

# Check if it worked
docker compose logs canonical-db-api --tail=20
```

## Expected Output After Fix

You should see:

```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Instead of:

```
ValueError: Invalid format 'json' for '%' style
```

## Common Issues

### Issue 1: Old Images Cached

**Symptom:** Same error after code changes
**Solution:** `docker compose build --no-cache`

### Issue 2: Port Already in Use

**Symptom:** "port is already allocated"
**Solution:** Check `.env` file has correct ports (5433, 6380, 9310, 9311, 9401, 9402)

### Issue 3: Database Connection Failed

**Symptom:** "could not connect to server"
**Solution:**

```bash
# Check PostgreSQL is running
docker compose ps postgres

# Check DATABASE_URL in .env
cat .env | grep DATABASE_URL

# Test connection
docker compose exec postgres psql -U rag_admin -d enterprise_rag -c "SELECT 1;"
```

### Issue 4: Missing Environment Variables

**Symptom:** "required environment variable not set"
**Solution:**

```bash
# Check .env file exists and has all variables
cat .env | wc -l  # Should be 60+ lines

# Check specific variables
cat .env | grep -E "POSTGRES_|REDIS_|MINIO_|SECRET_KEY|OIDC_"
```

## Debugging Commands

```bash
# Check container logs in real-time
docker compose logs -f

# Check specific service
docker compose logs -f canonical-db-api

# Check last 100 lines
docker compose logs --tail=100 canonical-db-api

# Check container inspect
docker compose ps -a
docker inspect enterprise-rag-canonical-db-api

# Check environment variables inside container
docker compose exec canonical-db-api env | grep -E "LOG_|DATABASE_|REDIS_"

# Test health endpoint from inside container
docker compose exec canonical-db-api curl -f http://localhost:8000/health

# Check if app is listening on port 8000
docker compose exec canonical-db-api netstat -tlnp | grep 8000
```

## Manual Test After Fix

```bash
# 1. Check all containers are healthy
docker compose ps

# Expected output:
# NAME                              STATUS
# enterprise-rag-postgres           Up (healthy)
# enterprise-rag-redis              Up (healthy)
# enterprise-rag-minio              Up (healthy)
# enterprise-rag-canonical-db-api   Up (healthy)
# enterprise-rag-auth-acl-api       Up (healthy)

# 2. Test API endpoints
curl http://localhost:9401/health
# Expected: {"status":"healthy",...}

curl http://localhost:9402/health
# Expected: {"status":"healthy",...}

# 3. Check logs are clean
docker compose logs canonical-db-api --tail=20
# Should NOT contain "ValueError" or "Invalid format"
```

## Contact Support

If issues persist after rebuilding:

1. Share the output of `docker compose logs canonical-db-api --tail=100`
2. Share the output of `cat .env | grep -E "LOG_|DATABASE_"`
3. Share the output of `docker compose ps -a`

---

**Last Updated:** 2026-05-31
**Issue:** Logging configuration bug
**Status:** Code fixed, needs image rebuild
