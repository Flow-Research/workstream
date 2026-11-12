"""Sanitized desired Keycloak configuration; credentials are provisioned separately."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

ISSUER = "https://identity.flowresearch.tech/realms/flow"
API_AUDIENCE = "workstream-api"
MCP_RESOURCE = "https://workstream.flowresearch.tech/mcp"
EXCHANGE_CLIENT = "workstream-mcp"
IDENTITY_SCOPE = "workstream-identity"
ACCESS_SCOPE = "workstream:access"
EXCHANGE_MARKER = "workstream.exchange-policy"


def claim_mapper(name: str, mapper: str, config: dict[str, str]) -> dict:
    """Emit access-token-only observations using a stock Keycloak mapper."""
    return {
        "name": name, "protocol": "openid-connect", "protocolMapper": mapper,
        "consentRequired": False,
        "config": {
            "access.token.claim": "true", "id.token.claim": "false",
            "userinfo.token.claim": "false", "introspection.token.claim": "true",
            **config,
        },
    }


def audience_mapper(name: str, *, client: str | None = None, resource: str | None = None) -> dict:
    """Bind one audience without realm-role or automatic audience resolution."""
    config = {}
    if client is not None:
        config["included.client.audience"] = client
    if resource is not None:
        config["included.custom.audience"] = resource
    return claim_mapper(name, "oidc-audience-mapper", config)


def client_scope(name: str, mappers: list[dict], *, visible: bool = False) -> dict:
    """Separate visible permission scopes from hidden identity/audience mappers."""
    return {
        "name": name, "protocol": "openid-connect",
        "attributes": {
            "include.in.token.scope": str(visible).lower(),
            "display.on.consent.screen": str(visible).lower(),
            "consent.screen.text": "Access Workstream under your assigned permissions",
        },
        "protocolMappers": mappers,
    }


def restricted_client(client_id: str) -> dict:
    """Default every credential-acquisition flow to disabled."""
    return {
        "clientId": client_id, "protocol": "openid-connect", "enabled": True,
        "publicClient": False, "clientAuthenticatorType": "client-secret",
        "standardFlowEnabled": False, "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False, "serviceAccountsEnabled": False,
        "fullScopeAllowed": False, "consentRequired": False,
        "redirectUris": [], "webOrigins": [],
        "defaultClientScopes": ["basic", IDENTITY_SCOPE], "optionalClientScopes": [],
        "attributes": {
            "oauth2.device.authorization.grant.enabled": "false",
            "oidc.ciba.grant.enabled": "false",
            "standard.token.exchange.enabled": "false",
            "standard.token.exchange.enableRefreshRequestedTokenType": "NO",
            "standard.token.exchange.allowTokenExpirationAfterSubjectTokenExpiration": "false",
            "access.token.lifespan": "300",
        },
    }


def browser_client(client_id: str, callback: str, audience_scope: str) -> dict:
    """Enable only browser code plus mandatory S256 PKCE for an exact callback."""
    result = restricted_client(client_id)
    result.update(publicClient=True, standardFlowEnabled=True, consentRequired=True,
                  redirectUris=[callback], optionalClientScopes=[ACCESS_SCOPE, audience_scope])
    result["attributes"]["pkce.code.challenge.method"] = "S256"
    return result


def exchange_policy() -> tuple[dict, dict]:
    """Select only the administratively marked requester and enforce source claims."""
    profile = {
        "profiles": [{
            "name": "workstream-human-exchange",
            "executors": [
                {"executor": "downscope-assertion-grant-enforcer", "configuration": {}},
                {"executor": "jwt-claim-enforcer", "configuration": {
                    "claim-name": "subject_kind", "allowed-value": "^human$",
                }},
            ],
        }],
    }
    policy = {
        "policies": [{
            "name": "workstream-human-exchange", "enabled": True,
            "conditions": [{"condition": "client-attributes", "configuration": {
                "attributes": json.dumps([{"key": EXCHANGE_MARKER, "value": "human-only"}]),
            }}],
            "profiles": ["workstream-human-exchange"],
        }],
    }
    return profile, policy


def realm() -> dict:
    """Return a credential-free initial realm; never import users or signing keys."""
    identity = client_scope(IDENTITY_SCOPE, [
        claim_mapper("subject-kind", "oidc-usermodel-attribute-mapper", {
            "user.attribute": "workstream_subject_kind", "claim.name": "subject_kind",
            "jsonType.label": "String", "multivalued": "false", "aggregate.attrs": "false",
        }),
        claim_mapper("account-email", "oidc-usermodel-property-mapper", {
            "user.attribute": "email", "claim.name": "email", "jsonType.label": "String",
        }),
        claim_mapper("account-name", "oidc-full-name-mapper", {}),
    ])
    exchange = restricted_client(EXCHANGE_CLIENT)
    # Hidden default scopes survive the downscope executor; a client-dedicated
    # mapper is not an assigned scope and can be filtered from an exchange.
    exchange["defaultClientScopes"].extend([ACCESS_SCOPE, "workstream-api-audience"])
    exchange["attributes"].update({
        EXCHANGE_MARKER: "human-only", "standard.token.exchange.enabled": "true",
        "access.token.lifespan": "120",
    })
    api = restricted_client(API_AUDIENCE)
    api["defaultClientScopes"] = []
    profiles, policies = exchange_policy()
    return {
        "realm": "flow", "displayName": "Flow Identity", "enabled": True,
        "sslRequired": "all", "registrationAllowed": False,
        "loginWithEmailAllowed": True, "duplicateEmailsAllowed": False,
        "rememberMe": False, "resetPasswordAllowed": False, "verifyEmail": False,
        "bruteForceProtected": True, "permanentLockout": False, "failureFactor": 5,
        "waitIncrementSeconds": 60, "maxFailureWaitSeconds": 900,
        "minimumQuickLoginWaitSeconds": 60, "quickLoginCheckMilliSeconds": 1000,
        "passwordPolicy": "length(14)", "defaultSignatureAlgorithm": "RS256",
        "ssoSessionIdleTimeout": 1800, "ssoSessionMaxLifespan": 28800,
        "accessTokenLifespan": 300, "revokeRefreshToken": True, "refreshTokenMaxReuse": 0,
        "defaultDefaultClientScopes": ["basic"], "defaultOptionalClientScopes": [],
        "clientScopes": [
            # Explicit scope imports replace the provider's stock scope list.
            client_scope("basic", [
                claim_mapper("sub", "oidc-sub-mapper", {}),
                claim_mapper("auth_time", "oidc-usersessionmodel-note-mapper", {
                    "user.session.note": "AUTH_TIME", "claim.name": "auth_time",
                    "jsonType.label": "long", "id.token.claim": "true",
                }),
            ]),
            identity, client_scope(ACCESS_SCOPE, [], visible=True),
            client_scope("workstream-api-audience", [audience_mapper("api", client=API_AUDIENCE)]),
            client_scope("workstream-mcp-audience", [
                audience_mapper("mcp-client", client=EXCHANGE_CLIENT),
                audience_mapper("mcp-resource", resource=MCP_RESOURCE),
            ]),
        ],
        "clients": [
            browser_client("workstream-cli-login", "http://127.0.0.1:17843/callback", "workstream-api-audience"),
            browser_client("workstream-mcp-proof", "http://127.0.0.1:17844/callback", "workstream-mcp-audience"),
            exchange, api,
        ],
        "clientProfiles": profiles, "clientPolicies": policies,
    }


def human_profile(existing: dict) -> dict:
    """Preserve stock profile fields while restricting the human marker to admins."""
    result = json.loads(json.dumps(existing))
    attributes = result.setdefault("attributes", [])
    attributes[:] = [item for item in attributes if item.get("name") != "workstream_subject_kind"]
    attributes.append({
        "name": "workstream_subject_kind", "multivalued": False,
        "permissions": {"view": ["admin"], "edit": ["admin"]},
        "validations": {"options": {"options": ["human"]}},
    })
    # Keycloak represents disabled unmanaged attributes as an absent policy,
    # not a DISABLED enum value.
    result.pop("unmanagedAttributePolicy", None)
    for item in attributes:
        if item.get("name") == "email":
            item["required"] = {"roles": ["user", "admin"]}
    if not any(item.get("name") == "email" for item in attributes):
        raise ValueError("Stock email profile is missing; inspect the provider configuration")
    return result


def garden_client(client_id: str, callback: str) -> dict:
    """Build an inspected Garden registration; never invent its live callback."""
    parsed = urlsplit(callback)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path != "/api/oauth/callback"
            or "*" in callback or not client_id.startswith("garden-")):
        raise ValueError("Garden registration requires its exact HTTPS callback and dedicated client ID")
    return browser_client(client_id, callback, "workstream-mcp-audience")


def main() -> None:
    """Render only sanitized initial desired state, without applying or resetting it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--profile-input", type=Path,
                        help="Render a restricted profile from an exported stock user profile")
    source.add_argument("--garden-callback",
                        help="Render a Garden client with this exact HTTPS callback")
    parser.add_argument("--garden-client-id")
    args = parser.parse_args()
    if bool(args.garden_callback) != bool(args.garden_client_id):
        parser.error("Garden callback and client ID must be provided together")
    if args.profile_input:
        desired = human_profile(json.loads(args.profile_input.read_text(encoding="utf-8")))
    elif args.garden_callback:
        desired = garden_client(args.garden_client_id, args.garden_callback)
    else:
        desired = realm()
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(desired, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
