-- 0004: Tenant for the `enterprise-rag` Keycloak realm.
--
-- The realm stamps every token with tenant_id = 'global-company'
-- (infra/keycloak/setup_realm.py); auth-acl-agent resolves that slug here.

INSERT INTO tenants (tenant_name, tenant_slug, default_language, allowed_languages, timezone)
VALUES ('Global Company', 'global-company', 'en', ARRAY['en'], 'UTC')
ON CONFLICT (tenant_slug) DO NOTHING;
