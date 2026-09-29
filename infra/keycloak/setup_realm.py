#!/usr/bin/env python3
"""
Create or update the Keycloak realm used by the Enterprise RAG System.

Idempotent: safe to re-run; existing objects are updated, never deleted.

  realm  enterprise-rag            one realm per tenant; every token carries a
                                   hard-coded tenant_id claim (the tenant slug)
  client enterprise-rag-web        public + PKCE, used by the web UI
  client enterprise-rag-api        confidential audience validated by auth-acl-agent
  scope  enterprise-rag-claims     tenant_id, groups (full path), department,
                                   role, region, country, clearance, is_employee
  groups internal-users, external-users, finance, hr, engineering, legal, security
  user profile attributes          admin-editable only (users cannot raise their
                                   own clearance)

Usage (stdlib only; prompts for the master-realm admin password):

  python3 infra/keycloak/setup_realm.py \
      --url https://auth.igwilo.com --admin-user admin \
      --origin https://rag.igwilo.com \
      [--set-github-secrets --repo ebunilo/enterprise_knowledge_base]

--set-github-secrets writes PRODUCTION_OIDC_PROVIDER_URL, PRODUCTION_OIDC_CLIENT_ID
and PRODUCTION_OIDC_CLIENT_SECRET with the gh CLI. The client secret is piped
straight to gh and never printed.
"""

import argparse
import getpass
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

API_CLIENT = "enterprise-rag-api"
WEB_CLIENT = "enterprise-rag-web"
CLAIMS_SCOPE = "enterprise-rag-claims"
GROUPS = ["internal-users", "external-users", "finance", "hr", "engineering", "legal", "security"]
# (attribute, display name). tenant_id is not a user attribute: the realm is the tenant.
USER_ATTRIBUTES = [
    ("department", "Department"),
    ("role", "Business role"),
    ("region", "Region"),
    ("country", "Country"),
    ("clearance", "Clearance level"),
    ("is_employee", "Is employee"),
]


class Keycloak:
    def __init__(self, base_url: str, token: str, dry_run: bool = False):
        self.base = base_url.rstrip("/")
        self.token = token
        self.dry_run = dry_run

    def request(self, method: str, path: str, body=None, expect=(200, 201, 204)):
        if self.dry_run and method != "GET":
            print(f"  [dry-run] {method} {path}")
            return None, 204
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{self.base}/admin{path}", data=data, method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return (json.loads(raw) if raw else None), resp.status
        except urllib.error.HTTPError as e:
            if e.code in expect:
                return None, e.code
            raise SystemExit(f"{method} {path} failed: {e.code} {e.read().decode()[:500]}")

    def get(self, path, expect=(200,)):
        return self.request("GET", path, expect=expect)[0]


def admin_token(base_url: str, user: str, password: str) -> str:
    data = urllib.parse.urlencode({
        "grant_type": "password", "client_id": "admin-cli", "username": user, "password": password,
    }).encode()
    url = f"{base_url.rstrip('/')}/realms/master/protocol/openid-connect/token"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=30) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Admin login failed ({e.code}); check --admin-user and password")


def attribute_mapper(attribute: str, json_type: str = "String") -> dict:
    return {
        "name": attribute, "protocol": "openid-connect", "protocolMapper": "oidc-usermodel-attribute-mapper",
        "config": {"user.attribute": attribute, "claim.name": attribute, "jsonType.label": json_type,
                   "id.token.claim": "true", "access.token.claim": "true", "userinfo.token.claim": "true",
                   "introspection.token.claim": "true"},
    }


def ensure_realm(kc: Keycloak, realm: str) -> bool:
    """Create or update the realm; returns whether it already existed."""
    settings = {
        "realm": realm, "enabled": True, "displayName": "Enterprise Knowledge Base",
        "sslRequired": "external", "registrationAllowed": False, "loginWithEmailAllowed": True,
        "duplicateEmailsAllowed": False, "resetPasswordAllowed": True, "bruteForceProtected": True,
        "accessTokenLifespan": 900, "ssoSessionIdleTimeout": 1800,
    }
    _, status = kc.request("GET", f"/realms/{realm}", expect=(200, 404))
    if status == 404:
        print(f"Creating realm {realm}")
        kc.request("POST", "/realms", settings)
        return False
    print(f"Updating realm {realm}")
    kc.request("PUT", f"/realms/{realm}", settings)
    return True


def ensure_user_profile(kc: Keycloak, realm: str) -> None:
    profile, status = kc.request("GET", f"/realms/{realm}/users/profile", expect=(200, 404))
    if status == 404 or profile is None:
        print("  Declarative user profile not available (Keycloak < 24); attributes are unmanaged")
        return
    existing = {a["name"] for a in profile.get("attributes", [])}
    for name, display in USER_ATTRIBUTES:
        if name not in existing:
            profile["attributes"].append({
                "name": name, "displayName": display, "multivalued": False,
                "permissions": {"view": ["admin", "user"], "edit": ["admin"]},
            })
    print("  User profile attributes: " + ", ".join(n for n, _ in USER_ATTRIBUTES))
    kc.request("PUT", f"/realms/{realm}/users/profile", profile)


def ensure_claims_scope(kc: Keycloak, realm: str, tenant_slug: str) -> str:
    scopes = kc.get(f"/realms/{realm}/client-scopes") or []
    scope = next((s for s in scopes if s["name"] == CLAIMS_SCOPE), None)
    if scope is None:
        kc.request("POST", f"/realms/{realm}/client-scopes", {
            "name": CLAIMS_SCOPE, "protocol": "openid-connect",
            "description": "Tenant and access-control claims for the Enterprise RAG System",
            "attributes": {"include.in.token.scope": "true", "display.on.consent.screen": "false"},
        })
        scopes = kc.get(f"/realms/{realm}/client-scopes") or []
        scope = next((s for s in scopes if s["name"] == CLAIMS_SCOPE), {"id": "dry-run"})

    mappers = [attribute_mapper(name, "boolean" if name == "is_employee" else "String")
               for name, _ in USER_ATTRIBUTES]
    mappers.append({
        "name": "tenant_id", "protocol": "openid-connect", "protocolMapper": "oidc-hardcoded-claim-mapper",
        "config": {"claim.name": "tenant_id", "claim.value": tenant_slug, "jsonType.label": "String",
                   "id.token.claim": "true", "access.token.claim": "true", "userinfo.token.claim": "true",
                   "introspection.token.claim": "true"},
    })
    mappers.append({
        "name": "groups", "protocol": "openid-connect", "protocolMapper": "oidc-group-membership-mapper",
        "config": {"claim.name": "groups", "full.path": "true", "id.token.claim": "true",
                   "access.token.claim": "true", "userinfo.token.claim": "true",
                   "introspection.token.claim": "true"},
    })
    base = f"/realms/{realm}/client-scopes/{scope['id']}/protocol-mappers/models"
    current = {m["name"]: m for m in (kc.get(base) or [])} if scope["id"] != "dry-run" else {}
    for mapper in mappers:
        if mapper["name"] in current:
            kc.request("PUT", f"{base}/{current[mapper['name']]['id']}", {**mapper, "id": current[mapper["name"]]["id"]})
        else:
            kc.request("POST", base, mapper)
    print(f"  Client scope {CLAIMS_SCOPE}: tenant_id={tenant_slug}, groups, " + ", ".join(n for n, _ in USER_ATTRIBUTES))
    return scope["id"]


def ensure_client(kc: Keycloak, realm: str, rep: dict, scope_id: str) -> str:
    found = kc.get(f"/realms/{realm}/clients?clientId={urllib.parse.quote(rep['clientId'])}") or []
    if found:
        client_id = found[0]["id"]
        kc.request("PUT", f"/realms/{realm}/clients/{client_id}", {**found[0], **rep})
    else:
        kc.request("POST", f"/realms/{realm}/clients", rep)
        found = kc.get(f"/realms/{realm}/clients?clientId={urllib.parse.quote(rep['clientId'])}") or [{"id": "dry-run"}]
        client_id = found[0]["id"]
    if client_id != "dry-run":
        kc.request("PUT", f"/realms/{realm}/clients/{client_id}/default-client-scopes/{scope_id}", expect=(204, 409))
    print(f"  Client {rep['clientId']}")
    return client_id


def ensure_groups(kc: Keycloak, realm: str) -> None:
    existing = {g["name"] for g in (kc.get(f"/realms/{realm}/groups") or [])}
    for group in GROUPS:
        if group not in existing:
            kc.request("POST", f"/realms/{realm}/groups", {"name": group})
    print("  Groups: " + ", ".join(GROUPS))


def set_github_secret(repo: str, name: str, value: str) -> None:
    subprocess.run(["gh", "secret", "set", name, "--repo", repo], input=value.encode(), check=True,
                   stdout=subprocess.DEVNULL)
    print(f"  GitHub secret {name} set")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="https://auth.igwilo.com")
    parser.add_argument("--realm", default="enterprise-rag")
    parser.add_argument("--tenant-slug", default="global-company",
                        help="must match tenants.tenant_slug in PostgreSQL")
    parser.add_argument("--admin-user", default=os.environ.get("KC_ADMIN_USER", "admin"))
    parser.add_argument("--origin", action="append", dest="origins",
                        help="web UI origin (repeatable); default https://rag.igwilo.com")
    parser.add_argument("--set-github-secrets", action="store_true")
    parser.add_argument("--repo", default="ebunilo/enterprise_knowledge_base")
    parser.add_argument("--secret-prefix", default="PRODUCTION")
    parser.add_argument("--dry-run", action="store_true", help="read-only: show what would change")
    args = parser.parse_args()
    origins = args.origins or ["https://rag.igwilo.com"]

    password = os.environ.get("KC_ADMIN_PASSWORD") or getpass.getpass(f"Keycloak admin password for {args.admin_user}: ")
    kc = Keycloak(args.url, admin_token(args.url, args.admin_user, password), args.dry_run)

    if not ensure_realm(kc, args.realm) and args.dry_run:
        print(f"[dry-run] realm does not exist; a real run would also create the claims scope, groups, "
              f"user profile attributes and clients {API_CLIENT} / {WEB_CLIENT}")
        return
    ensure_user_profile(kc, args.realm)
    scope_id = ensure_claims_scope(kc, args.realm, args.tenant_slug)
    ensure_groups(kc, args.realm)

    api_id = ensure_client(kc, args.realm, {
        "clientId": API_CLIENT, "name": "Enterprise RAG API (token audience)", "enabled": True,
        "protocol": "openid-connect", "publicClient": False, "clientAuthenticatorType": "client-secret",
        "standardFlowEnabled": False, "implicitFlowEnabled": False, "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
    }, scope_id)
    ensure_client(kc, args.realm, {
        "clientId": WEB_CLIENT, "name": "Enterprise RAG Web UI", "enabled": True,
        "protocol": "openid-connect", "publicClient": True,
        "standardFlowEnabled": True, "implicitFlowEnabled": False, "directAccessGrantsEnabled": False,
        "redirectUris": [f"{o.rstrip('/')}/*" for o in origins], "webOrigins": [o.rstrip("/") for o in origins],
        "attributes": {"pkce.code.challenge.method": "S256",
                       "post.logout.redirect.uris": "##".join(f"{o.rstrip('/')}/*" for o in origins)},
        "protocolMappers": [{
            "name": "audience-enterprise-rag-api", "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "config": {"included.client.audience": API_CLIENT, "access.token.claim": "true",
                       "id.token.claim": "false", "introspection.token.claim": "true"},
        }],
    }, scope_id)

    issuer = f"{args.url.rstrip('/')}/realms/{args.realm}"
    print(f"\nIssuer (OIDC_PROVIDER_URL): {issuer}\nOIDC_CLIENT_ID: {API_CLIENT}")

    if args.set_github_secrets and not args.dry_run:
        secret = kc.get(f"/realms/{args.realm}/clients/{api_id}/client-secret")["value"]
        prefix = args.secret_prefix
        set_github_secret(args.repo, f"{prefix}_OIDC_PROVIDER_URL", issuer)
        set_github_secret(args.repo, f"{prefix}_OIDC_CLIENT_ID", API_CLIENT)
        set_github_secret(args.repo, f"{prefix}_OIDC_CLIENT_SECRET", secret)
    elif not args.dry_run:
        print("Client secret: Keycloak admin console > Clients > enterprise-rag-api > Credentials")


if __name__ == "__main__":
    sys.exit(main())
