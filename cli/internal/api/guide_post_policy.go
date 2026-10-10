package api

import (
	"context"
	"encoding/json"
	"errors"
	"math/big"
	"net/http"
	"net/url"
	"regexp"
	"slices"
)

// GuidePostPolicy is an observation of one retained policy, not readiness or authority.
type GuidePostPolicy struct {
	Target              PostPolicyTarget       `json:"target"`
	Policy              CompiledPostPolicy     `json:"policy"`
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

type CompiledPostPolicy struct {
	SchemaVersion          string            `json:"schema_version"`
	CompilerVersion        string            `json:"compiler_version"`
	ProjectID              string            `json:"project_id"`
	GuideVersion           string            `json:"guide_version"`
	CatalogueID            string            `json:"catalogue_id"`
	CatalogueSourceVersion string            `json:"catalogue_source_version"`
	CatalogueSchemaVersion string            `json:"catalogue_schema_version"`
	CatalogueManifestHash  string            `json:"catalogue_manifest_sha256"`
	Entries                []PostPolicyEntry `json:"entries"`
	BlockingSeverities     []string          `json:"blocking_severities"`
}

type PostPolicyEntry struct {
	CheckerID             string          `json:"checker_id"`
	DefinitionVersion     string          `json:"definition_version"`
	ImplementationVersion string          `json:"implementation_version"`
	Classification        string          `json:"classification"`
	Configuration         json.RawMessage `json:"configuration"`
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
		validateCompiledPostPolicy(fields["policy"], &value.Policy, value.Target.Proposal) != nil ||
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
	fields, err := contextObject(raw, value, []string{"proposal", "upstream", "upstream_output_digest", "policy_id", "projection_operation_id", "policy_hash"}, nil)
	if err != nil || !sameUUID(value.PolicyID, policy) || !validUUID(value.ProjectionOperationID) ||
		(value.PredecessorPolicyID != nil && !validUUID(*value.PredecessorPolicyID)) ||
		!proposalDigests([]string{value.UpstreamOutputDigest, value.PolicyHash}) ||
		validateProposalTarget(fields["proposal"], &value.Proposal) != nil || !sameProposalTarget(value.Proposal, proposal.Target) {
		return errors.New("invalid post-policy target")
	}
	_, err = contextObject(fields["upstream"], &value.Upstream, []string{
		"operation_id", "target_digest", "artifact_policy_id", "effective_policy_id", "effective_policy_hash",
		"pre_submit_policy_id", "pre_submit_bundle_hash", "effective_pre_submit_plan_hash", "acknowledged_warning_hashes",
	}, []string{"acknowledged_warning_hashes"})
	if err != nil || !validGuideApproval(value.Upstream, guideApprovalInput{Target: value.Proposal, AcknowledgedWarningHashes: value.Upstream.AcknowledgedWarningHashes}) ||
		value.Upstream.TargetDigest != proposal.TargetDigest {
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
		a.SourceSnapshotHash == b.SourceSnapshotHash && a.FinalizationFactsDigest == b.FinalizationFactsDigest &&
		a.ResultHash == b.ResultHash && a.ComponentHashes == b.ComponentHashes &&
		a.PreCatalogueID == b.PreCatalogueID && a.PreCatalogueVersion == b.PreCatalogueVersion &&
		a.PreCatalogueSchemaVersion == b.PreCatalogueSchemaVersion && a.PreCatalogueManifestHash == b.PreCatalogueManifestHash &&
		a.PostCatalogueID == b.PostCatalogueID && a.PostCatalogueVersion == b.PostCatalogueVersion &&
		a.PostCatalogueSchemaVersion == b.PostCatalogueSchemaVersion && a.PostCatalogueManifestHash == b.PostCatalogueManifestHash &&
		sameNullableText(a.ArtifactPolicyHash, b.ArtifactPolicyHash) && sameNullableText(a.ArtifactProjectionOutputDigest, b.ArtifactProjectionOutputDigest)
}

func sameNullableText(a, b *string) bool {
	return (a == nil && b == nil) || (a != nil && b != nil && *a == *b)
}

var postPolicyIdentifier = regexp.MustCompile(`^[a-z][a-z0-9_.-]{0,99}$`)

func validateCompiledPostPolicy(raw json.RawMessage, value *CompiledPostPolicy, target ProposalTarget) error {
	// Public schema defaults are wire values, not a local compiler implementation.
	*value = CompiledPostPolicy{SchemaVersion: "post_submit_checker_policy", CompilerVersion: "workstream-post-submit-compiler",
		CatalogueID: "workstream.post_submission_checkers", CatalogueSourceVersion: "v0.1", CatalogueSchemaVersion: "post_submission_checker_capability_projection"}
	fields, err := contextObject(raw, value, []string{"project_id", "guide_version", "catalogue_manifest_sha256", "entries", "blocking_severities"}, []string{"blocking_severities"})
	if err != nil || value.SchemaVersion != "post_submit_checker_policy" || value.CompilerVersion != "workstream-post-submit-compiler" ||
		value.CatalogueID != "workstream.post_submission_checkers" || value.CatalogueSourceVersion != "v0.1" || value.CatalogueSchemaVersion != "post_submission_checker_capability_projection" ||
		!sameUUID(value.ProjectID, target.ProjectID) || value.GuideVersion != target.GuideVersion ||
		value.CatalogueID != target.PostCatalogueID || value.CatalogueSourceVersion != target.PostCatalogueVersion ||
		value.CatalogueSchemaVersion != target.PostCatalogueSchemaVersion || value.CatalogueManifestHash != target.PostCatalogueManifestHash ||
		len(value.Entries) < 1 || len(value.Entries) > 9 || len(value.BlockingSeverities) < 2 || len(value.BlockingSeverities) > 5 {
		return errors.New("invalid compiled post-policy")
	}
	var entries []json.RawMessage
	if json.Unmarshal(fields["entries"], &entries) != nil {
		return errors.New("invalid entries")
	}
	seen := make(map[string]bool, len(value.Entries))
	for i := range value.Entries {
		entry := &value.Entries[i]
		_, err := contextObject(entries[i], entry, []string{"checker_id", "definition_version", "implementation_version", "classification", "configuration"}, nil)
		var configuration struct{}
		if err != nil || seen[entry.CheckerID] || !postPolicyIdentifier.MatchString(entry.CheckerID) || !postPolicyIdentifier.MatchString(entry.ImplementationVersion) ||
			entry.DefinitionVersion != "v0.1" || !slices.Contains([]string{"platform_default", "project_required", "project_warning"}, entry.Classification) ||
			decode(entry.Configuration, &configuration, nil, nil) != nil {
			return errors.New("invalid policy entry")
		}
		seen[entry.CheckerID] = true
	}
	// These are public response invariants, not local catalogue evaluation.
	canonical := make([]string, 0, 5)
	for _, severity := range []string{"critical", "high", "medium", "low", "info"} {
		if slices.Contains(value.BlockingSeverities, severity) {
			canonical = append(canonical, severity)
		}
	}
	if !slices.Contains(canonical, "critical") || !slices.Contains(canonical, "high") || !slices.Equal(canonical, value.BlockingSeverities) {
		return errors.New("invalid blocking severities")
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
			_, err := contextObject(fields[[]string{"review", "revision"}[i]], selection, []string{"policy_id", "generation", "policy_hash"}, nil)
			if err != nil || !validUUID(selection.PolicyID) || selection.Generation.Sign() <= 0 || !contextPolicyDigest.MatchString(selection.PolicyHash) {
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
