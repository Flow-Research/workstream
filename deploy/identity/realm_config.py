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


def client_scope(
    name: str, mappers: list[dict], *, include_in_token_scope: bool = False,
    display_on_consent_screen: bool = False,
) -> dict:
    """Keep credential-renewal scope inclusion separate from consent presentation."""
    return {
        "name": name, "protocol": "openid-connect",
        "attributes": {
            "include.in.token.scope": str(include_in_token_scope).lower(),
            "display.on.consent.screen": str(display_on_consent_screen).lower(),
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


def swagger_client(api_origin: str = "https://workstream.flowresearch.tech") -> dict:
    """Register the API documentation browser with one exact callback and origin."""
    parsed = urlsplit(api_origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Swagger requires an exact HTTPS API origin")
    origin = api_origin.rstrip("/")
    client = browser_client("workstream-swagger", origin + "/docs/oauth2-redirect", "workstream-api-audience")
    client["webOrigins"] = [origin]
    return client


def direct_api_client() -> dict:
    """Allow human password grants at the issuer after required actions finish."""
    client = restricted_client("workstream-api-login")
    client.update(publicClient=True, directAccessGrantsEnabled=True,
                  optionalClientScopes=[ACCESS_SCOPE, "workstream-api-audience"])
    return client


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
        "loginTheme": "flow", "emailTheme": "flow",
        "eventsListeners": ["jboss-logging", "flow-human-registration"],
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
            identity, client_scope(ACCESS_SCOPE, [], include_in_token_scope=True,
                                   display_on_consent_screen=True),
            client_scope("workstream-api-audience", [audience_mapper("api", client=API_AUDIENCE)]),
            client_scope("workstream-mcp-audience", [
                audience_mapper("mcp-client", client=EXCHANGE_CLIENT),
                audience_mapper("mcp-resource", resource=MCP_RESOURCE),
            ], include_in_token_scope=True),
        ],
        "clients": [
            browser_client("workstream-cli-login", "http://127.0.0.1:17843/callback", "workstream-api-audience"),
            browser_client("workstream-mcp-proof", "http://127.0.0.1:17844/callback", "workstream-mcp-audience"),
            swagger_client(), direct_api_client(), exchange, api,
        ],
        "clientProfiles": profiles, "clientPolicies": policies,
    }


def self_service_settings(existing: dict, server_info: dict, profile: dict) -> dict:
    """Render an existing-realm activation patch after operator email-delivery proof."""
    if existing.get("realm") != "flow":
        raise ValueError("Self-service configuration belongs only to the Flow realm")
    providers = server_info.get("providers", {}).get("eventsListener", {}).get("providers", {})
    if "flow-human-registration" not in providers:
        raise ValueError("Deploy the Flow registration provider before enabling signup")
    marker = next((item for item in profile.get("attributes", [])
                   if item.get("name") == "workstream_subject_kind"), None)
    if marker is None or marker.get("permissions") != {"view": ["admin"], "edit": ["admin"]}:
        raise ValueError("Restore the administrator-only human identity profile before signup")
    smtp = existing.get("smtpServer", {})
    if not smtp.get("host") or not smtp.get("from"):
        raise ValueError("Configure and prove SMTP delivery before enabling signup")
    if smtp.get("ssl") != "true" and smtp.get("starttls") != "true":
        raise ValueError("Production email delivery requires TLS")
    listeners = list(existing.get("eventsListeners", []))
    if "flow-human-registration" not in listeners:
        listeners.append("flow-human-registration")
    return {
        "registrationAllowed": True, "registrationEmailAsUsername": True,
        "resetPasswordAllowed": True, "verifyEmail": True,
        "loginTheme": "flow", "emailTheme": "flow", "eventsListeners": listeners,
        "duplicateEmailsAllowed": False, "loginWithEmailAllowed": True,
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
    source.add_argument("--self-service-realm-input", type=Path,
                        help="Render an activation patch from an existing realm after SMTP delivery proof")
    parser.add_argument("--server-info-input", type=Path)
    parser.add_argument("--self-service-profile-input", type=Path)
    parser.add_argument("--garden-client-id")
    args = parser.parse_args()
    if bool(args.garden_callback) != bool(args.garden_client_id):
        parser.error("Garden callback and client ID must be provided together")
    if len({bool(args.self_service_realm_input), bool(args.server_info_input), bool(args.self_service_profile_input)}) != 1:
        parser.error("Self-service activation requires realm, server-info and user-profile input")
    if args.self_service_realm_input:
        desired = self_service_settings(
            json.loads(args.self_service_realm_input.read_text(encoding="utf-8")),
            json.loads(args.server_info_input.read_text(encoding="utf-8")),
            json.loads(args.self_service_profile_input.read_text(encoding="utf-8")),
        )
    elif args.profile_input:
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
