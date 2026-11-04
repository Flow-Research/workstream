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
	"slices"
	"strings"
	"unicode/utf8"
)

// GuidePostPolicy is an observation of one retained policy, not readiness or authority.
type GuidePostPolicy struct {
	Target              PostPolicyTarget       `json:"target"`
	Policy              ExternalPostPolicy     `json:"policy"`
	Proposal            GuideProposal          `json:"proposal"`
	ActivationContext   GuideActivationContext `json:"activation_context"`
	LifecycleStatus     string                 `json:"lifecycle_status"`
	Current             bool                   `json:"current"`
	ApprovalOperationID *string                `json:"approval_operation_id"`
	Correction          *GuideCorrection       `json:"correction"`
}

type PostPolicyTarget struct {
	Proposal              ProposalTarget `json:"proposal"`
	Upstream              GuideApproval  `json:"upstream"`
	UpstreamOutputDigest  string         `json:"upstream_output_digest"`
	PolicyID              string         `json:"policy_id"`
	ProjectionOperationID string         `json:"projection_operation_id"`
	PolicyHash            string         `json:"policy_hash"`
	PredecessorPolicyID   *string        `json:"predecessor_policy_id"`
}

type ExternalPostPolicy struct {
	SchemaVersion string                   `json:"schema_version"`
	Entries       []ExternalCheckerBinding `json:"entries"`
	PolicyHash    string                   `json:"policy_sha256"`
}

type ExternalCheckerBinding struct {
	RequirementID     string                       `json:"requirement_id"`
	Stage             string                       `json:"stage"`
	Registry          ExternalCheckerRegistryEntry `json:"registry"`
	Configuration     json.RawMessage              `json:"configuration"`
	ConfigurationHash string                       `json:"configuration_sha256"`
}

type ExternalCheckerRegistryEntry struct {
	CapabilityID                 string                        `json:"capability_id"`
	CapabilityVersion            string                        `json:"capability_version"`
	Phase                        string                        `json:"phase"`
	ImageDigest                  string                        `json:"image_digest"`
	ConfigurationSchema          ExternalCheckerSchema         `json:"configuration_schema"`
	InputSchema                  ExternalCheckerSchema         `json:"input_schema"`
	OutputSchema                 ExternalCheckerSchema         `json:"output_schema"`
	Resources                    ExternalCheckerResourceLimits `json:"resources"`
	RegistryEntryID              string                        `json:"registry_entry_id"`
	EntryDigest                  string                        `json:"entry_digest"`
	RegistrationOperationID      string                        `json:"registration_operation_id"`
	RegisteredByActorProfileID   string                        `json:"registered_by_actor_profile_id"`
	AuthorizationDecisionEventID string                        `json:"authorization_decision_event_id"`
	CreatedAt                    string                        `json:"created_at"`
}

type ExternalCheckerSchema struct {
	SchemaID      string          `json:"schema_id"`
	SchemaVersion string          `json:"schema_version"`
	Document      json.RawMessage `json:"document"`
	SchemaHash    string          `json:"schema_sha256"`
}

type ExternalCheckerResourceLimits struct {
	CPUMillis          *big.Int `json:"cpu_millis"`
	MemoryBytes        *big.Int `json:"memory_bytes"`
	DeadlineMillis     *big.Int `json:"deadline_ms"`
	MaximumOutputBytes *big.Int `json:"maximum_output_bytes"`
}

type GuideActivationContext struct {
	GuideMutationGeneration               *big.Int              `json:"guide_mutation_generation"`
	Review                                *GuidePolicySelection `json:"review"`
	Revision                              *GuidePolicySelection `json:"revision"`
	Contribution                          *GuideContributionIDs `json:"contribution"`
	ExpectedPreviousActiveGuideID         *string               `json:"expected_previous_active_guide_id"`
	ExpectedPreviousActiveGuideGeneration *big.Int              `json:"expected_previous_active_guide_generation"`
	PostApprovalOperationID               *string               `json:"post_approval_operation_id"`
	PostApprovalOutputDigest              *string               `json:"post_approval_output_digest"`
}

type GuidePolicySelection struct {
	PolicyID   string   `json:"policy_id"`
	Generation *big.Int `json:"generation"`
	PolicyHash string   `json:"policy_hash"`
}

type GuideContributionIDs struct {
	PolicyID        string `json:"contribution_policy_id"`
	PolicyVersionID string `json:"contribution_policy_version_id"`
}

type GuideCorrection struct {
	OperationID              string   `json:"operation_id"`
	TargetDigest             string   `json:"target_digest"`
	SuccessorSetupRunID      string   `json:"successor_setup_run_id"`
	SuccessorSetupGeneration *big.Int `json:"successor_setup_generation"`
	FeedbackHash             string   `json:"feedback_hash"`
	Status                   string   `json:"status"`
}

func (c *Client) GuidePostPolicy(ctx context.Context, project, guide, compilation, policy string) (Result[GuidePostPolicy], error) {
	var result Result[GuidePostPolicy]
	for _, selector := range []string{project, guide, compilation, policy} {
		if !validUUID(selector) || len(selector) > 100 {
			return result, errors.New("PROJECT_ID, GUIDE_ID, COMPILATION_ID and POLICY_ID must be UUIDs")
		}
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet,
		"/api/v1/projects/"+url.PathEscape(project)+"/guides/"+url.PathEscape(guide)+"/compilations/"+url.PathEscape(compilation)+"/post-submission-policies/"+url.PathEscape(policy),
		"", nil, "", http.StatusOK, maxProposalResponseBytes)
	if err != nil {
		return result, err
	}
	var value GuidePostPolicy
	fields, err := contextObject(raw, &value, []string{"target", "policy", "proposal", "activation_context", "lifecycle_status", "current"}, nil)
	if err != nil || !requiredNullable(fields, "approval_operation_id", "correction") ||
		!slices.Contains([]string{"compiled", "approved", "superseded"}, value.LifecycleStatus) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	proposal, err := decodeGuideProposal(fields["proposal"], project, guide, compilation)
	if err != nil || validatePostTarget(fields["target"], &value.Target, proposal.Value, policy) != nil ||
		validateExternalPostPolicy(fields["policy"], &value.Policy, value.Target.PolicyHash) != nil ||
		validateActivationContext(fields["activation_context"], &value.ActivationContext) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if (value.ApprovalOperationID == nil) != (value.ActivationContext.PostApprovalOperationID == nil) ||
		(value.ApprovalOperationID != nil && !sameUUID(*value.ApprovalOperationID, *value.ActivationContext.PostApprovalOperationID)) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if value.Correction != nil && validateGuideCorrection(fields["correction"], value.Correction, proposal.Value.TargetDigest) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[GuidePostPolicy]{Raw: raw, Value: value}, nil
}

// Required nullable fields distinguish an explicit absence from a truncated package.
func requiredNullable(fields map[string]json.RawMessage, keys ...string) bool {
	for _, key := range keys {
		if _, present := fields[key]; !present {
			return false
		}
	}
	return true
}

func validatePostTarget(raw json.RawMessage, value *PostPolicyTarget, proposal GuideProposal, policy string) error {
	if decodePostPolicyTarget(raw, value) != nil || !sameUUID(value.PolicyID, policy) ||
		!sameProposalTarget(value.Proposal, proposal.Target) || value.Upstream.TargetDigest != proposal.TargetDigest {
		return errors.New("invalid post-policy target")
	}
	return nil
}

func decodePostPolicyTarget(raw json.RawMessage, value *PostPolicyTarget) error {
	fields, err := contextObject(raw, value, []string{"proposal", "upstream", "upstream_output_digest", "policy_id", "projection_operation_id", "policy_hash"}, nil)
	if err != nil || !validUUID(value.PolicyID) || !validUUID(value.ProjectionOperationID) ||
		(value.PredecessorPolicyID != nil && !validUUID(*value.PredecessorPolicyID)) ||
		!proposalDigests([]string{value.UpstreamOutputDigest, value.PolicyHash}) ||
		validateProposalTarget(fields["proposal"], &value.Proposal) != nil {
		return errors.New("invalid post-policy target")
	}
	_, err = contextObject(fields["upstream"], &value.Upstream, []string{
		"operation_id", "target_digest", "artifact_policy_id", "effective_policy_id", "effective_policy_hash",
		"pre_submit_policy_id", "pre_submit_bundle_hash", "effective_pre_submit_plan_hash", "acknowledged_warning_hashes",
	}, []string{"acknowledged_warning_hashes"})
	if err != nil || !validGuideApproval(value.Upstream, guideApprovalInput{Target: value.Proposal, AcknowledgedWarningHashes: value.Upstream.AcknowledgedWarningHashes}) {
		return errors.New("invalid upstream receipt")
	}
	return nil
}

func sameProposalTarget(a, b ProposalTarget) bool {
	// Compare exposed source facts, not their business digest or current approval.
	for i, id := range []string{a.ProjectID, a.GuideID, a.CompilationID, a.SourceSnapshotID, a.SetupRunID, a.FinalizationID} {
		if !sameUUID(id, []string{b.ProjectID, b.GuideID, b.CompilationID, b.SourceSnapshotID, b.SetupRunID, b.FinalizationID}[i]) {
			return false
		}
	}
	for i, id := range []*string{a.ArtifactPolicyID, a.ArtifactProjectionOperationID} {
		other := []*string{b.ArtifactPolicyID, b.ArtifactProjectionOperationID}[i]
		if (id == nil) != (other == nil) || (id != nil && !sameUUID(*id, *other)) {
			return false
		}
	}
	return a.SetupGeneration.Cmp(b.SetupGeneration) == 0 && a.GuideVersion == b.GuideVersion &&
		a.ResultSchemaVersion == b.ResultSchemaVersion &&
		a.SourceSnapshotHash == b.SourceSnapshotHash && a.FinalizationFactsDigest == b.FinalizationFactsDigest &&
		a.ResultHash == b.ResultHash && a.ComponentHashes == b.ComponentHashes &&
		sameNullableText(a.ArtifactPolicyHash, b.ArtifactPolicyHash) && sameNullableText(a.ArtifactProjectionOutputDigest, b.ArtifactProjectionOutputDigest)
}

func sameNullableText(a, b *string) bool {
	return (a == nil && b == nil) || (a != nil && b != nil && *a == *b)
}

var postPolicyIdentifier = regexp.MustCompile(`^[a-z][a-z0-9_.-]{0,99}$`)
var postPolicySchemaVersion = regexp.MustCompile(`^[a-z0-9][a-z0-9_.-]{0,49}$`)

func validateExternalPostPolicy(raw json.RawMessage, value *ExternalPostPolicy, targetHash string) error {
	fields, err := contextObject(raw, value, []string{"schema_version", "entries", "policy_sha256"}, nil)
	if err != nil || value.SchemaVersion != "external_post_submit_policy.v1" ||
		!contextPolicyDigest.MatchString(value.PolicyHash) || value.PolicyHash != targetHash {
		return errors.New("invalid external post-policy")
	}
	var entries []json.RawMessage
	if jsonv2.Unmarshal(fields["entries"], &entries) != nil || entries == nil || len(entries) != len(value.Entries) {
		return errors.New("invalid external post-policy entries")
	}
	var previous [3]string
	for i := range value.Entries {
		entry := &value.Entries[i]
		if validateExternalCheckerBinding(entries[i], entry) != nil {
			return errors.New("invalid external checker binding")
		}
		identity := [3]string{entry.RequirementID, entry.Registry.CapabilityID, entry.Registry.CapabilityVersion}
		if i > 0 && compareCheckerBindingIdentity(identity, previous) <= 0 {
			return errors.New("external checker bindings are not canonical")
		}
		previous = identity
	}
	return nil
}

func compareCheckerBindingIdentity(left, right [3]string) int {
	for i := range left {
		if comparison := strings.Compare(left[i], right[i]); comparison != 0 {
			return comparison
		}
	}
	return 0
}

func validateExternalCheckerBinding(raw json.RawMessage, value *ExternalCheckerBinding) error {
	fields, err := contextObject(raw, value, []string{"requirement_id", "stage", "registry", "configuration", "configuration_sha256"}, nil)
	if err != nil || utf8.RuneCountInString(value.RequirementID) < 1 || utf8.RuneCountInString(value.RequirementID) > 100 || value.Stage != "post_submit" ||
		!contextPolicyDigest.MatchString(value.ConfigurationHash) || validateJSONObject(value.Configuration) != nil ||
		validateExternalCheckerRegistry(fields["registry"], &value.Registry) != nil || value.Registry.Phase != value.Stage {
		return errors.New("invalid external checker binding")
	}
	return nil
}

func validateExternalCheckerRegistry(raw json.RawMessage, value *ExternalCheckerRegistryEntry) error {
	fields, err := contextObject(raw, value, []string{
		"capability_id", "capability_version", "phase", "image_digest", "configuration_schema", "input_schema", "output_schema", "resources",
		"registry_entry_id", "entry_digest", "registration_operation_id", "registered_by_actor_profile_id", "authorization_decision_event_id", "created_at",
	}, nil)
	if err != nil || !postPolicyIdentifier.MatchString(value.CapabilityID) || !postPolicySchemaVersion.MatchString(value.CapabilityVersion) ||
		value.Phase != "post_submit" || !contextPolicyDigest.MatchString(value.ImageDigest) || !contextPolicyDigest.MatchString(value.EntryDigest) ||
		!validUUID(value.RegistryEntryID) || !validUUID(value.RegistrationOperationID) || !validUUID(value.RegisteredByActorProfileID) ||
		!validUUID(value.AuthorizationDecisionEventID) || !validTime(value.CreatedAt) ||
		validateExternalCheckerSchema(fields["configuration_schema"], &value.ConfigurationSchema, "") != nil ||
		validateExternalCheckerSchema(fields["input_schema"], &value.InputSchema, "external_checker_post_submit_input") != nil ||
		validateExternalCheckerSchema(fields["output_schema"], &value.OutputSchema, "external_checker_result") != nil ||
		validateExternalCheckerResources(fields["resources"], &value.Resources) != nil {
		return errors.New("invalid external checker registry entry")
	}
	identity, valid := uuidIdentity(value.RegistryEntryID)
	if !valid || identity[6]>>4 != 7 || identity[8]&0xc0 != 0x80 {
		return errors.New("invalid external checker registry identity")
	}
	return nil
}

func validateExternalCheckerSchema(raw json.RawMessage, value *ExternalCheckerSchema, requiredID string) error {
	_, err := contextObject(raw, value, []string{"schema_id", "schema_version", "document", "schema_sha256"}, nil)
	if err != nil || !postPolicyIdentifier.MatchString(value.SchemaID) || !postPolicySchemaVersion.MatchString(value.SchemaVersion) ||
		(requiredID != "" && value.SchemaID != requiredID) || !contextPolicyDigest.MatchString(value.SchemaHash) ||
		validateJSONObject(value.Document) != nil {
		return errors.New("invalid external checker schema")
	}
	return nil
}

func validateExternalCheckerResources(raw json.RawMessage, value *ExternalCheckerResourceLimits) error {
	_, err := contextObject(raw, value, []string{"cpu_millis", "memory_bytes", "deadline_ms", "maximum_output_bytes"}, nil)
	if err != nil || !boundedInteger(value.CPUMillis, 100, 64_000) || !boundedInteger(value.MemoryBytes, 16*1024*1024, 64*1024*1024*1024) ||
		!boundedInteger(value.DeadlineMillis, 100, 3_600_000) || !boundedInteger(value.MaximumOutputBytes, 256, 65_536) {
		return errors.New("invalid external checker resources")
	}
	return nil
}

func boundedInteger(value *big.Int, minimum, maximum int64) bool {
	return value != nil && value.IsInt64() && value.Int64() >= minimum && value.Int64() <= maximum
}

func validateJSONObject(raw json.RawMessage) error {
	var value map[string]json.RawMessage
	if err := jsonv2.Unmarshal(raw, &value); err != nil || value == nil {
		return errors.New("invalid JSON object")
	}
	return nil
}

func validateActivationContext(raw json.RawMessage, value *GuideActivationContext) error {
	fields, err := contextObject(raw, value, []string{"guide_mutation_generation"}, nil)
	if err != nil || !requiredNullable(fields, "review", "revision", "contribution", "expected_previous_active_guide_id", "expected_previous_active_guide_generation", "post_approval_operation_id", "post_approval_output_digest") ||
		value.GuideMutationGeneration.Sign() <= 0 ||
		(value.ExpectedPreviousActiveGuideID == nil) != (value.ExpectedPreviousActiveGuideGeneration == nil) ||
		(value.PostApprovalOperationID == nil) != (value.PostApprovalOutputDigest == nil) {
		return errors.New("invalid activation context")
	}
	if value.ExpectedPreviousActiveGuideID != nil && (!validUUID(*value.ExpectedPreviousActiveGuideID) || value.ExpectedPreviousActiveGuideGeneration.Sign() <= 0) {
		return errors.New("invalid previous guide")
	}
	if value.PostApprovalOperationID != nil && (!validUUID(*value.PostApprovalOperationID) || !contextPolicyDigest.MatchString(*value.PostApprovalOutputDigest)) {
		return errors.New("invalid post approval")
	}
	for i, selection := range []*GuidePolicySelection{value.Review, value.Revision} {
		if selection != nil {
			if validateGuidePolicySelection(fields[[]string{"review", "revision"}[i]], selection) != nil {
				return errors.New("invalid policy selection")
			}
		}
	}
	if value.Contribution != nil {
		_, err := contextObject(fields["contribution"], value.Contribution, []string{"contribution_policy_id", "contribution_policy_version_id"}, nil)
		if err != nil || !validUUID(value.Contribution.PolicyID) || !validUUID(value.Contribution.PolicyVersionID) {
			return errors.New("invalid contribution selection")
		}
	}
	return nil
}

func validateGuidePolicySelection(raw json.RawMessage, value *GuidePolicySelection) error {
	_, err := contextObject(raw, value, []string{"policy_id", "generation", "policy_hash"}, nil)
	if err != nil || !validUUID(value.PolicyID) || value.Generation.Sign() <= 0 || !contextPolicyDigest.MatchString(value.PolicyHash) {
		return errors.New("invalid policy selection")
	}
	return nil
}

func validateGuideCorrection(raw json.RawMessage, value *GuideCorrection, targetDigest string) error {
	value.Status = "correction_requested"
	_, err := contextObject(raw, value, []string{"operation_id", "target_digest", "successor_setup_run_id", "successor_setup_generation", "feedback_hash"}, nil)
	if err != nil || value.Status != "correction_requested" || value.TargetDigest != targetDigest ||
		!proposalDigests([]string{value.TargetDigest, value.FeedbackHash}) || value.SuccessorSetupGeneration.Sign() <= 0 {
		return errors.New("invalid correction receipt")
	}
	for _, id := range []string{value.OperationID, value.SuccessorSetupRunID} {
		identity, valid := uuidIdentity(id)
		if !valid || identity[6]>>4 != 7 || identity[8]&0xc0 != 0x80 {
			return errors.New("invalid correction identity")
		}
	}
	return nil
}
