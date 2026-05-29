#!/bin/bash

# Enterprise RAG System - Secret Generation Script
# Generates secure passwords and secrets for deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if environment argument is provided
if [ -z "$1" ]; then
    print_error "Usage: $0 <environment>"
    echo "Example: $0 development"
    echo "Example: $0 staging"
    echo "Example: $0 production"
    exit 1
fi

ENVIRONMENT=$1
ENV_FILE="../.env.${ENVIRONMENT}"

print_info "Generating secrets for ${ENVIRONMENT} environment..."

# Check if .env file already exists
if [ -f "$ENV_FILE" ]; then
    print_warning "Environment file ${ENV_FILE} already exists."
    read -p "Do you want to overwrite it? (yes/no): " -r
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        print_info "Aborted. No changes made."
        exit 0
    fi
    # Backup existing file
    cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    print_info "Backup created: ${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
fi

# Copy template
cp ../.env.example "$ENV_FILE"

print_info "Generating secure passwords..."

# Generate PostgreSQL password
POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)
print_info "✓ PostgreSQL password generated"

# Generate MinIO password
MINIO_ROOT_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)
print_info "✓ MinIO password generated"

# Generate Redis password
REDIS_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)
print_info "✓ Redis password generated"

# Generate secret key
SECRET_KEY=$(openssl rand -hex 32)
print_info "✓ Secret key generated"

# Update .env file
sed -i.bak "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${POSTGRES_PASSWORD}/" "$ENV_FILE"
sed -i.bak "s/MINIO_ROOT_PASSWORD=.*/MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}/" "$ENV_FILE"
sed -i.bak "s/REDIS_PASSWORD=.*/REDIS_PASSWORD=${REDIS_PASSWORD}/" "$ENV_FILE"
sed -i.bak "s/SECRET_KEY=.*/SECRET_KEY=${SECRET_KEY}/" "$ENV_FILE"
sed -i.bak "s/ENVIRONMENT=.*/ENVIRONMENT=${ENVIRONMENT}/" "$ENV_FILE"

# Remove backup file
rm "${ENV_FILE}.bak"

print_info "Secrets have been written to ${ENV_FILE}"

# Create secrets file for reference
SECRETS_FILE="../secrets/${ENVIRONMENT}_secrets_$(date +%Y%m%d_%H%M%S).txt"
mkdir -p ../secrets

cat > "$SECRETS_FILE" << EOF
# Enterprise RAG System - ${ENVIRONMENT} Secrets
# Generated: $(date)
# IMPORTANT: Store this file securely and never commit to version control

POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
SECRET_KEY=${SECRET_KEY}

# Next Steps:
# 1. Configure OIDC provider settings in ${ENV_FILE}
# 2. Update DOMAIN setting for production
# 3. Review and adjust resource limits
# 4. Set up SSL certificates for production
# 5. Configure backup settings

# Security Reminders:
# - Store this file in a secure location (password manager, vault, etc.)
# - Do not share secrets via email or chat
# - Rotate secrets regularly (every 90 days recommended)
# - Use different secrets for each environment
# - Enable MFA for admin accounts
EOF

chmod 600 "$SECRETS_FILE"

print_info "Secrets reference saved to: ${SECRETS_FILE}"
print_warning "IMPORTANT: Store this file securely and delete it after saving to your password manager!"

echo ""
print_info "Next steps:"
echo "1. Edit ${ENV_FILE} and configure:"
echo "   - OIDC_PROVIDER_URL"
echo "   - OIDC_CLIENT_ID"
echo "   - OIDC_CLIENT_SECRET"
echo "   - DOMAIN (for production)"
echo "   - ALLOWED_ORIGINS"
echo ""
echo "2. For production, also configure:"
echo "   - SSL_ENABLED=true"
echo "   - LETSENCRYPT_EMAIL"
echo "   - BACKUP_ENABLED=true"
echo ""
echo "3. Deploy with:"
echo "   cd .. && docker-compose --env-file .env.${ENVIRONMENT} up -d"
echo ""

print_info "Secret generation complete!"

# Made with Bob
