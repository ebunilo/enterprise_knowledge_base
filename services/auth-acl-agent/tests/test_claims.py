"""Keycloak claim normalisation."""

from app.claims import normalize_claims

CLIENT = "enterprise-rag"
EXTERNAL = {"external-users"}


def test_keycloak_documented_claims():
    # Shape from docs/KEYCLOAK_OIDC_SETUP.md
    token = {
        "sub": "f1b2", "email": "ada@igwilo.com", "tenant_id": "global-company",
        "department": "Engineering", "groups": ["/engineering", "internal-users"],
        "role": "senior_engineer", "region": "emea", "country": "United Kingdom",
        "clearance": "department_restricted",
    }
    claims = normalize_claims(token, CLIENT, EXTERNAL)
    assert claims["tenant_ref"] == "global-company"
    assert claims["department"] == "engineering"
    assert claims["groups"] == ["engineering", "internal-users"]
    assert claims["roles"] == ["senior_engineer"]
    assert claims["clearance"] == "DEPARTMENT_RESTRICTED"
    assert claims["country"] == "united kingdom"
    assert claims["is_employee"] is True


def test_enterprise_rag_realm_token_shape():
    # Access token as issued by infra/keycloak/setup_realm.py via enterprise-rag-web
    token = {
        "sub": "0f6c", "azp": "enterprise-rag-web", "aud": ["enterprise-rag-api", "account"],
        "typ": "Bearer", "tenant_id": "global-company", "groups": ["/finance", "/internal-users"],
        "department": "Finance", "role": "finance_manager", "region": "emea", "country": "Germany",
        "clearance": "confidential", "is_employee": True,
        "realm_access": {"roles": ["default-roles-enterprise-rag", "offline_access", "uma_authorization"]},
    }
    claims = normalize_claims(token, "enterprise-rag-api", EXTERNAL)
    assert claims["tenant_ref"] == "global-company"
    assert claims["groups"] == ["finance", "internal-users"]
    assert claims["roles"] == ["finance_manager"]
    assert claims["clearance"] == "CONFIDENTIAL"
    assert claims["is_employee"] is True


def test_realm_and_client_roles_merged_without_keycloak_defaults():
    token = {
        "sub": "u", "role": "Finance_Manager",
        "realm_access": {"roles": ["offline_access", "uma_authorization", "default-roles-enterprise", "auditor"]},
        "resource_access": {CLIENT: {"roles": ["policy_admin"]}, "other-client": {"roles": ["ignored"]}},
    }
    assert normalize_claims(token, CLIENT, EXTERNAL)["roles"] == ["finance_manager", "auditor", "policy_admin"]


def test_external_user_is_not_employee():
    token = {"sub": "x", "groups": ["/external-users"], "clearance": "public"}
    claims = normalize_claims(token, CLIENT, EXTERNAL)
    assert claims["is_employee"] is False
    assert claims["clearance"] == "PUBLIC"


def test_missing_clearance_defaults_by_employment():
    assert normalize_claims({"sub": "a", "groups": ["staff"]}, CLIENT, EXTERNAL)["clearance"] == "INTERNAL_GENERAL"
    assert normalize_claims({"sub": "b", "groups": ["external-users"]}, CLIENT, EXTERNAL)["clearance"] == "PUBLIC"


def test_unknown_clearance_fails_closed():
    claims = normalize_claims({"sub": "a", "clearance": "top-secret"}, CLIENT, EXTERNAL)
    # A misconfigured clearance loses access (visible, quickly fixed) rather
    # than risking over-grant.
    assert claims["clearance"] == "PUBLIC"
    assert claims["is_employee"] is False


def test_explicit_is_employee_claim_wins():
    assert normalize_claims({"sub": "a", "is_employee": "false"}, CLIENT, EXTERNAL)["is_employee"] is False
    assert normalize_claims({"sub": "a", "is_employee": True, "groups": ["external-users"]},
                            CLIENT, EXTERNAL)["is_employee"] is True


def test_groups_as_comma_string():
    assert normalize_claims({"sub": "a", "groups": "finance, hr"}, CLIENT, EXTERNAL)["groups"] == ["finance", "hr"]
