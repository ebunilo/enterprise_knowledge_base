"""
Normalisation of Keycloak token claims into the ACL engine's user model.

Keycloak specifics handled here:
  * `groups` from the group-membership mapper are full paths ("/finance");
    from a user-attribute mapper they may be plain names or a single string.
  * Roles can come from the custom `role` attribute, `realm_access.roles`
    and `resource_access.<client>.roles`.
  * Custom attributes (tenant_id, clearance, ...) are free text, so casing
    varies ("confidential" vs "CONFIDENTIAL", "Finance" vs "finance").

All comparisons in the ACL engine are case-insensitive; values are
lowercased here, except clearance which uses the uppercase enum names.
"""

import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

CLEARANCE_LEVELS = [
    "PUBLIC",
    "INTERNAL_GENERAL",
    "DEPARTMENT_RESTRICTED",
    "CONFIDENTIAL",
    "REGULATED",
    "EXECUTIVE_ONLY",
]
CLEARANCE_RANK = {level: rank for rank, level in enumerate(CLEARANCE_LEVELS)}

_CLEARANCE_ALIASES = {"INTERNAL": "INTERNAL_GENERAL", "RESTRICTED": "DEPARTMENT_RESTRICTED", "EXECUTIVE": "EXECUTIVE_ONLY"}

# Roles Keycloak adds to every user; they carry no authorization meaning here.
_KEYCLOAK_DEFAULT_ROLES = {"offline_access", "uma_authorization"}

_TRUE = {"true", "1", "yes", "y"}
_FALSE = {"false", "0", "no", "n"}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part for part in (p.strip() for p in value.split(",")) if part]
    if isinstance(value, Iterable):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value)]


def _norm(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    text = _norm(value)
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def normalize_clearance(value: Any) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    level = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    level = _CLEARANCE_ALIASES.get(level, level)
    return level if level in CLEARANCE_RANK else None


def normalize_groups(value: Any) -> list[str]:
    groups = []
    for group in _as_list(value):
        normalised = group.strip().lstrip("/").lower()
        if normalised and normalised not in groups:
            groups.append(normalised)
    return groups


def extract_roles(token: dict, client_id: str) -> list[str]:
    roles: list[str] = []
    candidates = _as_list(token.get("role")) + _as_list(token.get("roles"))
    candidates += _as_list((token.get("realm_access") or {}).get("roles"))
    candidates += _as_list(((token.get("resource_access") or {}).get(client_id) or {}).get("roles"))
    for role in candidates:
        normalised = role.lower()
        if normalised in _KEYCLOAK_DEFAULT_ROLES or normalised.startswith("default-roles-"):
            continue
        if normalised not in roles:
            roles.append(normalised)
    return roles


def normalize_claims(token: dict, client_id: str, external_groups: set[str]) -> dict:
    """Map validated token claims to the fields of schemas.UserClaims."""
    groups = normalize_groups(token.get("groups"))
    roles = extract_roles(token, client_id)
    raw_clearance = token.get("clearance")
    clearance = normalize_clearance(raw_clearance)
    if raw_clearance and clearance is None:
        logger.warning("Unrecognised clearance claim %r; treating as PUBLIC", raw_clearance)
        clearance = "PUBLIC"

    explicit_employee = _as_bool(token.get("is_employee"))
    if explicit_employee is not None:
        is_employee = explicit_employee
    else:
        # Fail closed: external group members and PUBLIC-cleared users are
        # not employees, whatever else the token says.
        is_employee = not (set(groups) & external_groups) and clearance != "PUBLIC"

    if clearance is None:
        clearance = "INTERNAL_GENERAL" if is_employee else "PUBLIC"

    return {
        "user_id": token.get("sub"),
        "email": token.get("email"),
        "username": token.get("preferred_username"),
        "tenant_ref": _norm(token.get("tenant_id")),
        "department": _norm(token.get("department")),
        "groups": groups,
        "roles": roles,
        "region": _norm(token.get("region")),
        "country": _norm(token.get("country")),
        "clearance": clearance,
        "is_employee": is_employee,
        "exp": token.get("exp"),
        "iat": token.get("iat"),
    }
