package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
)

// These are retained, privacy-bounded observations, never local authority facts.
type AdminActor struct {
	ActorProfileID     string  `json:"actor_profile_id"`
	ActorKind          string  `json:"actor_kind"`
	Status             string  `json:"status"`
	ProvisioningMethod string  `json:"provisioning_method"`
	ServiceIdentity    *string `json:"service_identity"`
	DisplayName        *string `json:"display_name"`
	CreatedAt          string  `json:"created_at"`
	UpdatedAt          string  `json:"updated_at"`
	LastSeenAt         *string `json:"last_seen_at"`
	SuspendedAt        *string `json:"suspended_at"`
	ReactivatedAt      *string `json:"reactivated_at"`
	DeactivatedAt      *string `json:"deactivated_at"`
}

type AdminIdentityLink struct {
	IdentityLinkID string  `json:"identity_link_id"`
	ActorProfileID string  `json:"actor_profile_id"`
	SubjectKind    string  `json:"subject_kind"`
	Status         string  `json:"status"`
	LinkedAt       string  `json:"linked_at"`
	LastVerifiedAt *string `json:"last_verified_at"`
	RevokedAt      *string `json:"revoked_at"`
	ReactivatedAt  *string `json:"reactivated_at"`
}

type AdminRoleGrant struct {
	GrantID                   string  `json:"grant_id"`
	TargetActorProfileID      string  `json:"target_actor_profile_id"`
	Role                      string  `json:"role"`
	ScopeType                 string  `json:"scope_type"`
	ScopeProjectID            *string `json:"scope_project_id"`
	Status                    string  `json:"status"`
	Version                   int     `json:"version"`
	GrantedByRefKind          string  `json:"granted_by_ref_kind"`
	GrantedByRef              string  `json:"granted_by_ref"`
	GrantedByAdminRoleGrantID *string `json:"granted_by_admin_role_grant_id"`
	GrantReason               string  `json:"grant_reason"`
	GrantedAt                 string  `json:"granted_at"`
	RevokedByActorProfileID   *string `json:"revoked_by_actor_profile_id"`
	RevokedByAdminRoleGrantID *string `json:"revoked_by_admin_role_grant_id"`
	RevokedReason             *string `json:"revoked_reason"`
	RevokedAt                 *string `json:"revoked_at"`
}

type AdminRoleGrantPage struct {
	Items      []AdminRoleGrant `json:"items"`
	Total      int              `json:"total"`
	NextCursor *string          `json:"next_cursor"`
}

type AdminGrantQuery struct {
	Scope     string
	ProjectID *string
	Status    *string
	Limit     int
	Cursor    *string
}

type PermissionDefinition struct {
	PermissionID string `json:"permission_id"`
}
type PermissionCatalogue struct {
	Items []PermissionDefinition `json:"items"`
	Total int                    `json:"total"`
}
type AdminRoleDefinition struct {
	Role          string   `json:"role"`
	AllowedScopes []string `json:"allowed_scopes"`
	PermissionIDs []string `json:"permission_ids"`
}
type AdminRoleDefinitions struct {
	Items []AdminRoleDefinition `json:"items"`
	Total int                   `json:"total"`
}

const maxAdminGrantReadBytes = 256 * 1024

var permissionToken = regexp.MustCompile(`^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`)

func adminActorPath(actor string) (string, error) {
	if !validUUID(actor) || len(actor) > 100 {
		return "", errors.New("ACTOR_ID must be a UUID")
	}
	return "/api/v1/actors/" + url.PathEscape(actor), nil
}

func (c *Client) AdminActor(ctx context.Context, actor string) (Result[AdminActor], error) {
	var result Result[AdminActor]
	path, err := adminActorPath(actor)
	if err != nil {
		return result, err
	}
	raw, err := c.request(ctx, http.MethodGet, path, "", nil)
	if err != nil {
		return result, err
	}
	var value AdminActor
	fields, err := contextObject(raw, &value, []string{"actor_profile_id", "actor_kind", "status", "provisioning_method", "created_at", "updated_at"}, nil)
	if err != nil || !requiredNullable(fields, "service_identity", "display_name", "last_seen_at", "suspended_at", "reactivated_at", "deactivated_at") ||
		!sameUUID(value.ActorProfileID, actor) || !oneOf(value.ActorKind, "human", "service") || !validStatus(value.Status) ||
		!oneOf(value.ProvisioningMethod, "automatic_first_access", "manual_service_provisioning") ||
		(value.ActorKind == "service") != (value.ServiceIdentity != nil) ||
		(value.ServiceIdentity != nil && !validServiceIdentity(*value.ServiceIdentity)) ||
		!validTime(value.CreatedAt) || !validTime(value.UpdatedAt) || !optionalTime(value.LastSeenAt) ||
		!optionalTime(value.SuspendedAt) || !optionalTime(value.ReactivatedAt) || !optionalTime(value.DeactivatedAt) || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if !validAdminActorLifecycle(value) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[AdminActor]{Raw: raw, Value: value}, nil
}

func validAdminActorLifecycle(value AdminActor) bool {
	switch value.Status {
	case "active":
		return value.SuspendedAt == nil && value.DeactivatedAt == nil
	case "suspended":
		return value.SuspendedAt != nil && value.DeactivatedAt == nil
	case "deactivated":
		// A deactivated actor may retain an earlier suspension timestamp.
		return value.DeactivatedAt != nil
	}
	return false
}

func (c *Client) AdminIdentityLink(ctx context.Context, actor string) (Result[AdminIdentityLink], error) {
	var result Result[AdminIdentityLink]
	path, err := adminActorPath(actor)
	if err != nil {
		return result, err
	}
	raw, err := c.request(ctx, http.MethodGet, path+"/identity-links", "", nil)
	if err != nil {
		return result, err
	}
	var value AdminIdentityLink
	fields, err := contextObject(raw, &value, []string{"identity_link_id", "actor_profile_id", "subject_kind", "status", "linked_at"}, nil)
	if err != nil || !requiredNullable(fields, "last_verified_at", "revoked_at", "reactivated_at") ||
		!validUUID(value.IdentityLinkID) || !sameUUID(value.ActorProfileID, actor) ||
		!oneOf(value.SubjectKind, "human", "service") || !oneOf(value.Status, "active", "revoked") ||
		!validTime(value.LinkedAt) || !optionalTime(value.LastVerifiedAt) || !optionalTime(value.RevokedAt) ||
		!optionalTime(value.ReactivatedAt) || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if (value.Status == "active") != (value.RevokedAt == nil) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[AdminIdentityLink]{Raw: raw, Value: value}, nil
}

func optionalAdminUUID(value *string) bool { return value == nil || validUUID(*value) }

// ACTORS publishes a closed v0.1 service-principal vocabulary. These are
// identity names, not cached permissions or locally evaluated roles.
func validServiceIdentity(value string) bool {
	return oneOf(value,
		"workstream.artifact.verifier", "workstream.artifact.put_resolver",
		"workstream.artifact.scheduler", "workstream.artifact.binding",
		"workstream.artifact.guide_reader", "workstream.artifact.materializer",
		"workstream.artifact.checker_output", "workstream.task.assignment_reconciler",
		"workstream.task.revision_expirer", "workstream.task.post_submit_router",
		"workstream.checker.pre_submit", "workstream.checker.post_submit",
		"workstream.outbox.dispatcher", "workstream.project.setup",
		"workstream.review.preference_expiry", "workstream.review.lease_expiry",
		"workstream.review.authority_invalidation_reconciliation",
		"workstream.review.reconciliation", "workstream.review.artifact_reference_reconciliation",
		"workstream.review.projection", "workstream.compensation.adapter",
	)
}
func validAdminScope(value string) bool { return oneOf(value, "system", "project") }

func (q AdminGrantQuery) encode() (string, error) {
	if !validAdminScope(q.Scope) || (q.Scope == "project") != (q.ProjectID != nil) ||
		(q.ProjectID != nil && (!validUUID(*q.ProjectID) || len(*q.ProjectID) > 100)) ||
		(q.Status != nil && !oneOf(*q.Status, "active", "revoked", "all")) ||
		q.Limit < 1 || q.Limit > 100 || (q.Cursor != nil && !validTaskCursor(*q.Cursor)) {
		return "", errors.New("select --scope system|project with --project-id UUID only for project; --status active|revoked|all, --limit 1–100 and a bounded cursor")
	}
	values := url.Values{"scope_type": {q.Scope}, "limit": {strconv.Itoa(q.Limit)}}
	if q.ProjectID != nil {
		values.Set("scope_project_id", *q.ProjectID)
	}
	if q.Status != nil {
		values.Set("status", *q.Status)
	}
	if q.Cursor != nil {
		values.Set("cursor", *q.Cursor)
	}
	return values.Encode(), nil
}

func (c *Client) AdminRoleGrants(ctx context.Context, actor *string, query AdminGrantQuery) (Result[AdminRoleGrantPage], error) {
	var result Result[AdminRoleGrantPage]
	path := "/api/v1/admin-role-grants"
	if actor != nil {
		base, err := adminActorPath(*actor)
		if err != nil {
			return result, err
		}
		path = base + "/admin-role-grants"
	}
	encoded, err := query.encode()
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path, encoded, nil, "", http.StatusOK, maxAdminGrantReadBytes)
	if err != nil {
		return result, err
	}
	var page AdminRoleGrantPage
	fields, err := contextObject(raw, &page, []string{"items", "total"}, nil)
	if err != nil || !requiredNullable(fields, "next_cursor") || page.Items == nil || page.Total < 0 ||
		len(page.Items) > query.Limit || page.Total < len(page.Items) ||
		(page.NextCursor != nil && (!validTaskCursor(*page.NextCursor) || len(page.Items) == 0)) || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	var members []json.RawMessage
	if err := json.Unmarshal(fields["items"], &members); err != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := make(map[[16]byte]bool)
	for index, member := range members {
		grant := &page.Items[index]
		if !validAdminGrant(member, grant, actor, query) {
			return result, &Failure{Code: "invalid_api_response"}
		}
		id, _ := uuidIdentity(grant.GrantID)
		if seen[id] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
	}
	return Result[AdminRoleGrantPage]{Raw: raw, Value: page}, nil
}

func validAdminGrant(raw json.RawMessage, value *AdminRoleGrant, actor *string, query AdminGrantQuery) bool {
	// Omitting status on the wire asks the backend for its default active page.
	// Match that effective selection in the response without sending a new flag.
	expectedStatus := "active"
	if query.Status != nil {
		expectedStatus = *query.Status
	}
	fields, err := contextObject(raw, value, []string{
		"grant_id", "target_actor_profile_id", "role", "scope_type", "status", "version",
		"granted_by_ref_kind", "granted_by_ref", "grant_reason", "granted_at",
	}, nil)
	if err != nil || !requiredNullable(fields, "scope_project_id", "granted_by_admin_role_grant_id", "revoked_by_actor_profile_id", "revoked_by_admin_role_grant_id", "revoked_reason", "revoked_at") ||
		!validUUID(value.GrantID) || !validUUID(value.TargetActorProfileID) ||
		(actor != nil && !sameUUID(value.TargetActorProfileID, *actor)) ||
		!validAdminRole(value.Role) || value.ScopeType != query.Scope ||
		(value.ScopeProjectID == nil) != (query.ProjectID == nil) ||
		(value.ScopeProjectID != nil && !sameUUID(*value.ScopeProjectID, *query.ProjectID)) ||
		(expectedStatus != "all" && value.Status != expectedStatus) ||
		!validAdminGrantScopeAndLifecycle(*value) ||
		!oneOf(value.GrantedByRefKind, "actor_profile", "system_principal") ||
		value.GrantedByRef == "" ||
		(value.GrantedByRefKind == "actor_profile" && !validUUID(value.GrantedByRef)) ||
		!optionalAdminUUID(value.GrantedByAdminRoleGrantID) ||
		!validTime(value.GrantedAt) || !optionalAdminUUID(value.RevokedByActorProfileID) ||
		!optionalAdminUUID(value.RevokedByAdminRoleGrantID) || !optionalTime(value.RevokedAt) {
		return false
	}
	return true
}

func validAdminGrantScopeAndLifecycle(value AdminRoleGrant) bool {
	if value.ScopeType == "project" && oneOf(value.Role, "access_administrator", "operator") {
		return false
	}
	switch value.Status {
	case "active":
		return value.Version == 1 && value.RevokedByActorProfileID == nil &&
			value.RevokedByAdminRoleGrantID == nil && value.RevokedReason == nil && value.RevokedAt == nil
	case "revoked":
		return value.Version == 2 && value.RevokedByActorProfileID != nil &&
			value.RevokedByAdminRoleGrantID != nil && value.RevokedReason != nil &&
			len(*value.RevokedReason) >= 1 && len(*value.RevokedReason) <= 500 &&
			value.RevokedAt != nil
	}
	return false
}

func (c *Client) AdminPermissions(ctx context.Context) (Result[PermissionCatalogue], error) {
	var result Result[PermissionCatalogue]
	raw, err := c.request(ctx, http.MethodGet, "/api/v1/authorization/permissions", "", nil)
	if err != nil {
		return result, err
	}
	var value PermissionCatalogue
	fields, err := contextObject(raw, &value, []string{"items", "total"}, nil)
	// The public PermissionDefinitionsResponse schema fixes total to Literal[95].
	if err != nil || value.Items == nil || value.Total != 95 || len(value.Items) != value.Total || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	var members []json.RawMessage
	if json.Unmarshal(fields["items"], &members) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := make(map[string]bool)
	for index, member := range members {
		var item PermissionDefinition
		if _, err := contextObject(member, &item, []string{"permission_id"}, nil); err != nil || !permissionToken.MatchString(item.PermissionID) || seen[item.PermissionID] || value.Items[index].PermissionID != item.PermissionID {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[item.PermissionID] = true
	}
	return Result[PermissionCatalogue]{Raw: raw, Value: value}, nil
}

func (c *Client) AdminRoleDefinitions(ctx context.Context) (Result[AdminRoleDefinitions], error) {
	var result Result[AdminRoleDefinitions]
	raw, err := c.request(ctx, http.MethodGet, "/api/v1/authorization/admin-role-definitions", "", nil)
	if err != nil {
		return result, err
	}
	var value AdminRoleDefinitions
	fields, err := contextObject(raw, &value, []string{"items", "total"}, nil)
	// The public AdminRoleDefinitionsResponse schema fixes total to Literal[5].
	if err != nil || value.Items == nil || value.Total != 5 || len(value.Items) != value.Total || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	var members []json.RawMessage
	if json.Unmarshal(fields["items"], &members) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := make(map[string]bool)
	for index, member := range members {
		item := &value.Items[index]
		_, err := contextObject(member, item, []string{"role", "allowed_scopes", "permission_ids"}, []string{"allowed_scopes", "permission_ids"})
		if err != nil || !validAdminRole(item.Role) || seen[item.Role] || item.AllowedScopes == nil || item.PermissionIDs == nil {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[item.Role] = true
		for _, scope := range item.AllowedScopes {
			if !validAdminScope(scope) {
				return result, &Failure{Code: "invalid_api_response"}
			}
		}
		for _, permission := range item.PermissionIDs {
			if !permissionToken.MatchString(permission) {
				return result, &Failure{Code: "invalid_api_response"}
			}
		}
	}
	return Result[AdminRoleDefinitions]{Raw: raw, Value: value}, nil
}
