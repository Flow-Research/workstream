package api

import (
	"context"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"math/big"
	"net/http"
	"net/url"
	"regexp"
	"strings"
)

// WorkContext is the server's contributor projection, not an authority token.
type WorkContext struct {
	Task                        ContributorTaskDetail `json:"task"`
	Project                     ContextProject        `json:"project"`
	Guide                       ContextGuide          `json:"guide"`
	ReviewPolicy                ContextPolicy         `json:"review_policy"`
	RevisionPolicy              ContextPolicy         `json:"revision_policy"`
	ContributionPolicyVersionID string                `json:"contribution_policy_version_id"`
	Lifecycle                   ContextLifecycle      `json:"lifecycle"`
	GuideDocuments              []TaskGuideDocument   `json:"guide_documents"`
}

type ContextProject struct {
	ID          string  `json:"id"`
	Name        string  `json:"name"`
	Slug        string  `json:"slug"`
	Description *string `json:"description"`
}

type ContextGuide struct {
	ID            string  `json:"id"`
	ProjectID     string  `json:"project_id"`
	Version       string  `json:"version"`
	ChangeSummary *string `json:"change_summary"`
	EffectiveAt   string  `json:"effective_at"`
}

type ContextPolicy struct {
	PolicyID   string `json:"policy_id"`
	Generation int64  `json:"generation"`
	PolicyHash string `json:"policy_hash"`
}

type ContextLifecycle struct {
	AssignedToCurrentActor bool     `json:"assigned_to_current_actor"`
	NextActions            []string `json:"next_actions"`
}

// SubmissionRequirements describes locked intake rules, not an upload action.
type SubmissionRequirements struct {
	TaskID                  string                `json:"task_id"`
	ProjectID               string                `json:"project_id"`
	GuideVersion            string                `json:"guide_version"`
	PolicySchemaVersion     *string               `json:"policy_schema_version"`
	MergeAlgorithmVersion   *string               `json:"merge_algorithm_version"`
	RequiredPacketFields    []string              `json:"required_packet_fields"`
	RequiredArtifacts       []ArtifactRequirement `json:"required_artifacts"`
	RequiredEvidence        []EvidenceRequirement `json:"required_evidence"`
	ForbiddenArtifacts      []ForbiddenArtifact   `json:"forbidden_artifacts"`
	AttestationTerms        []string              `json:"attestation_terms"`
	ManifestRequired        bool                  `json:"manifest_required"`
	ArtifactHashRequired    bool                  `json:"artifact_hash_required"`
	ArtifactHashAlgorithm   string                `json:"artifact_hash_algorithm"`
	AllowedStorageSchemes   []string              `json:"allowed_storage_schemes"`
	StorageReferenceRules   StorageReferenceRules `json:"storage_reference_rules"`
	MaximumFileSizeBytes    *big.Int              `json:"maximum_file_size_bytes"`
	MaximumPackageSizeBytes *big.Int              `json:"maximum_package_size_bytes"`
	MaximumArchiveEntries   *big.Int              `json:"maximum_archive_entries"`
	MaximumArchiveSizeBytes *big.Int              `json:"maximum_archive_size_bytes"`
	Packaging               PackagingRequirements `json:"packaging"`
}

type ArtifactRequirement struct {
	Key          string  `json:"key"`
	Path         string  `json:"path"`
	HashRequired bool    `json:"hash_required"`
	Required     bool    `json:"required"`
	Description  *string `json:"description"`
}

type EvidenceRequirement struct {
	Key          string  `json:"key"`
	Label        string  `json:"label"`
	HashRequired bool    `json:"hash_required"`
	Required     bool    `json:"required"`
	Description  *string `json:"description"`
}

type ForbiddenArtifact struct {
	Pattern         string  `json:"pattern"`
	Reason          *string `json:"reason"`
	WorkerFacingFix *string `json:"worker_facing_fix"`
	Severity        *string `json:"severity"`
}

type StorageReferenceRules struct {
	AllowedStorageSchemes []string `json:"allowed_storage_schemes"`
	AllowedURIPrefixes    []string `json:"allowed_uri_prefixes"`
	CredentialsAllowed    bool     `json:"credentials_allowed"`
	QueryStringsAllowed   bool     `json:"query_strings_allowed"`
	FragmentsAllowed      bool     `json:"fragments_allowed"`
	PathTraversalAllowed  bool     `json:"path_traversal_allowed"`
}

type PackagingRequirements struct {
	PackageRequired       bool     `json:"package_required"`
	AllowedPackageFormats []string `json:"allowed_package_formats"`
}

var contextPolicyDigest = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

// Up to 100 Unicode labels plus full original identities exceed the small
// default JSON envelope. This is a wire bound, not a project policy limit.
const maxGuideContextResponseBytes = 2 * 1024 * 1024

func (c *Client) readTaskContext(ctx context.Context, selector, suffix string) (json.RawMessage, error) {
	if !validUUID(selector) || len(selector) > 100 {
		return nil, errors.New("TASK_ID must be a UUID")
	}
	limit := maxResponseBytes
	if suffix == "/work-context" {
		limit = maxGuideContextResponseBytes
	}
	return c.requestWithResponseLimit(ctx, http.MethodGet, "/api/v1/tasks/"+url.PathEscape(selector)+suffix, "", nil, "", http.StatusOK, limit)
}

func (c *Client) WorkContext(ctx context.Context, selector string) (Result[WorkContext], error) {
	var result Result[WorkContext]
	raw, err := c.readTaskContext(ctx, selector, "/work-context")
	if err != nil {
		return result, err
	}
	var value WorkContext
	fields, err := contextObject(raw, &value, []string{
		"task", "project", "guide", "review_policy", "revision_policy", "contribution_policy_version_id", "lifecycle", "guide_documents",
	}, nil)
	if err != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if err := decodeTaskFields(fields["task"], &value.Task,
		[]string{"task_id", "project_id", "title", "description", "status", "created_at", "updated_at"},
		[]string{"skill_tags", "compensation"}); err != nil || !sameUUID(value.Task.TaskID, selector) ||
		!validTask(value.Task.TaskSummary, value.Project.ID) || !ValidCompensation(value.Task.Compensation) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if _, err := contextObject(fields["project"], &value.Project, []string{"id", "name", "slug"}, nil); err != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if _, err := contextObject(fields["guide"], &value.Guide, []string{"id", "project_id", "version", "effective_at"}, nil); err != nil ||
		!validUUID(value.Guide.ID) || !sameUUID(value.Guide.ProjectID, value.Project.ID) ||
		strings.TrimSpace(value.Guide.Version) == "" || !validTime(value.Guide.EffectiveAt) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	for _, policy := range []struct {
		key   string
		value *ContextPolicy
	}{{"review_policy", &value.ReviewPolicy}, {"revision_policy", &value.RevisionPolicy}} {
		if _, err := contextObject(fields[policy.key], policy.value, []string{"policy_id", "generation", "policy_hash"}, nil); err != nil ||
			!validUUID(policy.value.PolicyID) || policy.value.Generation <= 0 || !contextPolicyDigest.MatchString(policy.value.PolicyHash) {
			return result, &Failure{Code: "invalid_api_response"}
		}
	}
	if _, err := contextObject(fields["lifecycle"], &value.Lifecycle, []string{"assigned_to_current_actor", "next_actions"}, []string{"next_actions"}); err != nil ||
		len(value.Lifecycle.NextActions) > 1 || !validUUID(value.ContributionPolicyVersionID) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	for _, action := range value.Lifecycle.NextActions {
		if action != "claim" && action != "start" {
			return result, &Failure{Code: "invalid_api_response"}
		}
	}
	if err := validateGuideDocuments(fields["guide_documents"], value.GuideDocuments, value.Task.TaskID, value.Lifecycle.AssignedToCurrentActor); err != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[WorkContext]{Raw: raw, Value: value}, nil
}

func (c *Client) SubmissionRequirements(ctx context.Context, selector string) (Result[SubmissionRequirements], error) {
	var result Result[SubmissionRequirements]
	raw, err := c.readTaskContext(ctx, selector, "/submission-requirements")
	if err != nil {
		return result, err
	}
	var value SubmissionRequirements
	fields, err := contextObject(raw, &value, []string{
		"task_id", "project_id", "guide_version", "required_packet_fields", "required_artifacts", "required_evidence",
		"forbidden_artifacts", "attestation_terms", "manifest_required", "artifact_hash_required", "artifact_hash_algorithm",
		"allowed_storage_schemes", "storage_reference_rules", "packaging",
	}, []string{"required_packet_fields", "attestation_terms", "allowed_storage_schemes"})
	if err != nil || !sameUUID(value.TaskID, selector) || !validUUID(value.ProjectID) ||
		strings.TrimSpace(value.GuideVersion) == "" || value.ArtifactHashAlgorithm != "sha256" {
		return result, &Failure{Code: "invalid_api_response"}
	}
	for _, group := range []struct {
		key      string
		required []string
	}{
		{"required_artifacts", []string{"key", "path", "hash_required", "required"}},
		{"required_evidence", []string{"key", "label", "hash_required", "required"}},
		{"forbidden_artifacts", []string{"pattern"}},
	} {
		var entries []json.RawMessage
		if err := jsonv2.Unmarshal(fields[group.key], &entries); err != nil || entries == nil {
			return result, &Failure{Code: "invalid_api_response"}
		}
		for index, entry := range entries {
			var target any
			switch group.key {
			case "required_artifacts":
				target = &value.RequiredArtifacts[index]
			case "required_evidence":
				target = &value.RequiredEvidence[index]
			case "forbidden_artifacts":
				target = &value.ForbiddenArtifacts[index]
			}
			if _, err := contextObject(entry, target, group.required, nil); err != nil {
				return result, &Failure{Code: "invalid_api_response"}
			}
		}
	}
	if _, err := contextObject(fields["storage_reference_rules"], &value.StorageReferenceRules, []string{
		"allowed_storage_schemes", "allowed_uri_prefixes", "credentials_allowed", "query_strings_allowed", "fragments_allowed", "path_traversal_allowed",
	}, []string{"allowed_storage_schemes", "allowed_uri_prefixes"}); err != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	// The optional format array may be absent/null. A null member decodes to
	// an empty string, which the closed public format set below rejects.
	if _, err := contextObject(fields["packaging"], &value.Packaging, []string{"package_required"}, nil); err != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	for _, format := range value.Packaging.AllowedPackageFormats {
		if format != "zip" && format != "tar" && format != "tar.gz" && format != "tar.zst" {
			return result, &Failure{Code: "invalid_api_response"}
		}
	}
	return Result[SubmissionRequirements]{Raw: raw, Value: value}, nil
}

// contextObject extends the shared closed decoder with required non-null
// presence. JSON null must not turn booleans, integers or nested objects into
// Go zero values; optional fields retain the API's null/omission semantics.
func contextObject(raw json.RawMessage, value any, required, arrays []string) (map[string]json.RawMessage, error) {
	if err := decode(raw, value, required, arrays); err != nil {
		return nil, err
	}
	var fields map[string]json.RawMessage
	if err := jsonv2.Unmarshal(raw, &fields); err != nil {
		return nil, err
	}
	for _, key := range required {
		if strings.TrimSpace(string(fields[key])) == "null" {
			return nil, errors.New("null required context field")
		}
	}
	return fields, nil
}
