package api

import (
	"context"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"math/big"
	"net/http"
	"net/url"
)

const maxProposalResponseBytes = 8 * 1024 * 1024

// GuideProposal is the public display package, never an approval capability.
type GuideProposal struct {
	Target                      ProposalTarget `json:"target"`
	TargetDigest                string         `json:"target_digest"`
	Result                      ProposalResult `json:"result"`
	Current                     bool           `json:"current"`
	ArtifactPolicyStatus        *string        `json:"artifact_policy_status"`
	WarningHashes               []string       `json:"warning_hashes"`
	CurrentApprovalOperationID  *string        `json:"current_approval_operation_id"`
	CurrentApprovalOutputDigest *string        `json:"current_approval_output_digest"`
	PostSubmitPolicyID          *string        `json:"post_submit_policy_id"`
}

type ProposalTarget struct {
	ProjectID                      string         `json:"project_id"`
	GuideID                        string         `json:"guide_id"`
	CompilationID                  string         `json:"compilation_id"`
	GuideVersion                   string         `json:"guide_version"`
	SourceSnapshotID               string         `json:"source_snapshot_id"`
	SourceSnapshotHash             string         `json:"source_snapshot_hash"`
	SetupRunID                     string         `json:"setup_run_id"`
	SetupGeneration                *big.Int       `json:"setup_generation"`
	FinalizationID                 string         `json:"finalization_id"`
	FinalizationFactsDigest        string         `json:"finalization_facts_digest"`
	ResultHash                     string         `json:"result_hash"`
	ComponentHashes                ProposalHashes `json:"component_hashes"`
	PreCatalogueID                 string         `json:"pre_catalogue_id"`
	PreCatalogueVersion            string         `json:"pre_catalogue_version"`
	PreCatalogueSchemaVersion      string         `json:"pre_catalogue_schema_version"`
	PreCatalogueManifestHash       string         `json:"pre_catalogue_manifest_hash"`
	PostCatalogueID                string         `json:"post_catalogue_id"`
	PostCatalogueVersion           string         `json:"post_catalogue_version"`
	PostCatalogueSchemaVersion     string         `json:"post_catalogue_schema_version"`
	PostCatalogueManifestHash      string         `json:"post_catalogue_manifest_hash"`
	ArtifactPolicyID               *string        `json:"artifact_policy_id"`
	ArtifactPolicyHash             *string        `json:"artifact_policy_hash"`
	ArtifactProjectionOperationID  *string        `json:"artifact_projection_operation_id"`
	ArtifactProjectionOutputDigest *string        `json:"artifact_projection_output_digest"`
}

type ProposalHashes struct {
	SufficiencyHash           string `json:"sufficiency_hash"`
	ArtifactPolicyHash        string `json:"artifact_policy_hash"`
	RequirementInventoryHash  string `json:"requirement_inventory_hash"`
	PreSubmitHash             string `json:"pre_submit_hash"`
	PostSubmitHash            string `json:"post_submit_hash"`
	CapabilitySuggestionsHash string `json:"capability_suggestions_hash"`
	SetupNotesHash            string `json:"setup_notes_hash"`
}

type ProposalResult struct {
	Status                   string                `json:"status"`
	Findings                 []ProposalFinding     `json:"findings"`
	SubmissionArtifactPolicy *ProposalIntakePolicy `json:"submission_artifact_policy"`
	Requirements             []ProposalRequirement `json:"requirements"`
	PreSubmitBindings        []ProposalPreBinding  `json:"pre_submit_bindings"`
	PostSubmitBindings       []ProposalPostBinding `json:"post_submit_bindings"`
	CapabilitySuggestions    []ProposalSuggestion  `json:"capability_suggestions"`
	SetupNotes               []string              `json:"setup_notes"`
	AgentName                string                `json:"agent_name"`
	AgentVersion             string                `json:"agent_version"`
	SchemaVersion            string                `json:"schema_version"`
}

type ProposalEvidence struct {
	DocumentNumber *big.Int `json:"document_number"`
	StartPage      *big.Int `json:"start_page"`
	EndPage        *big.Int `json:"end_page"`
	Section        *string  `json:"section"`
}

type ProposalFinding struct {
	Severity     string             `json:"severity"`
	Code         string             `json:"code"`
	Message      string             `json:"message"`
	EvidenceRefs []ProposalEvidence `json:"evidence_refs"`
}

type ProposalRequirement struct {
	RequirementID    string                    `json:"requirement_id"`
	Statement        string                    `json:"statement"`
	Disposition      string                    `json:"disposition"`
	PlatformCoverage *ProposalPlatformCoverage `json:"platform_coverage"`
	EvidenceRefs     []ProposalEvidence        `json:"evidence_refs"`
}

type ProposalPlatformCoverage struct {
	CapabilityID      string `json:"capability_id"`
	CapabilityVersion string `json:"capability_version"`
	Stage             string `json:"stage"`
}

type ProposalPreBinding struct {
	RequirementID     string `json:"requirement_id"`
	CapabilityID      string `json:"capability_id"`
	CapabilityVersion string `json:"capability_version"`
	Stage             string `json:"stage"`
}

type ProposalPostBinding struct {
	ProposalPreBinding
	Parameters []ProposalParameter `json:"parameters"`
}

type ProposalParameter struct {
	Name  string          `json:"name"`
	Value json.RawMessage `json:"value"`
}

type ProposalSuggestion struct {
	RequirementID string             `json:"requirement_id"`
	Stage         string             `json:"stage"`
	Title         string             `json:"title"`
	Rationale     string             `json:"rationale"`
	EvidenceRefs  []ProposalEvidence `json:"evidence_refs"`
}

type ProposalIntakePolicy struct {
	Packaging               string   `json:"packaging"`
	MaximumFileSizeBytes    *big.Int `json:"maximum_file_size_bytes"`
	MaximumPackageSizeBytes *big.Int `json:"maximum_package_size_bytes"`
	MaximumArchiveSizeBytes *big.Int `json:"maximum_archive_size_bytes"`
	MaximumArchiveEntries   *big.Int `json:"maximum_archive_entries"`
	AllowedStorageSchemes   []string `json:"allowed_storage_schemes"`
	RequiredArtifacts       []string `json:"required_artifacts"`
	ForbiddenArtifacts      []string `json:"forbidden_artifacts"`
	RequiredEvidence        []string `json:"required_evidence"`
	AttestationTerms        []string `json:"attestation_terms"`
}

func (c *Client) GuideProposal(ctx context.Context, project, guide, compilation string) (Result[GuideProposal], error) {
	var result Result[GuideProposal]
	for _, selector := range []string{project, guide, compilation} {
		if !validUUID(selector) || len(selector) > 100 {
			return result, errors.New("PROJECT_ID, GUIDE_ID and COMPILATION_ID must be UUIDs")
		}
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet,
		"/api/v1/projects/"+url.PathEscape(project)+"/guides/"+url.PathEscape(guide)+"/compilations/"+url.PathEscape(compilation)+"/proposal",
		"", nil, "", http.StatusOK, maxProposalResponseBytes)
	if err != nil {
		return result, err
	}
	var value GuideProposal
	fields, err := contextObject(raw, &value, []string{"target", "target_digest", "result", "current", "warning_hashes"}, []string{"warning_hashes"})
	if err != nil || !contextPolicyDigest.MatchString(value.TargetDigest) ||
		!sameUUID(value.Target.ProjectID, project) || !sameUUID(value.Target.GuideID, guide) || !sameUUID(value.Target.CompilationID, compilation) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if _, present := fields["artifact_policy_status"]; !present {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if value.ArtifactPolicyStatus != nil && *value.ArtifactPolicyStatus != "draft" && *value.ArtifactPolicyStatus != "approved" && *value.ArtifactPolicyStatus != "superseded" {
		return result, &Failure{Code: "invalid_api_response"}
	}
	for _, id := range []*string{value.CurrentApprovalOperationID, value.PostSubmitPolicyID} {
		if id != nil && !validUUID(*id) {
			return result, &Failure{Code: "invalid_api_response"}
		}
	}
	if (value.CurrentApprovalOutputDigest != nil && !contextPolicyDigest.MatchString(*value.CurrentApprovalOutputDigest)) ||
		!proposalDigests(value.WarningHashes) || validateProposalTarget(fields["target"], &value.Target) != nil ||
		validateProposalResult(fields["result"], &value.Result) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[GuideProposal]{Raw: raw, Value: value}, nil
}

func proposalDigests(values []string) bool {
	for _, value := range values {
		if !contextPolicyDigest.MatchString(value) {
			return false
		}
	}
	return true
}

func validateProposalTarget(raw json.RawMessage, value *ProposalTarget) error {
	fields, err := contextObject(raw, value, []string{
		"project_id", "guide_id", "compilation_id", "guide_version", "source_snapshot_id", "source_snapshot_hash",
		"setup_run_id", "setup_generation", "finalization_id", "finalization_facts_digest", "result_hash", "component_hashes",
		"pre_catalogue_id", "pre_catalogue_version", "pre_catalogue_schema_version", "pre_catalogue_manifest_hash",
		"post_catalogue_id", "post_catalogue_version", "post_catalogue_schema_version", "post_catalogue_manifest_hash",
	}, nil)
	if err != nil {
		return err
	}
	for _, key := range []string{"artifact_policy_id", "artifact_policy_hash", "artifact_projection_operation_id", "artifact_projection_output_digest"} {
		if _, present := fields[key]; !present {
			return errors.New("missing nullable target")
		}
	}
	if value.SetupGeneration.Sign() <= 0 {
		return errors.New("invalid generation")
	}
	// This tuple is one nullable response identity, not four independent facts.
	present := 0
	for _, field := range []*string{value.ArtifactPolicyID, value.ArtifactPolicyHash, value.ArtifactProjectionOperationID, value.ArtifactProjectionOutputDigest} {
		if field != nil {
			present++
		}
	}
	if present != 0 && present != 4 {
		return errors.New("incomplete policy identity")
	}
	for _, id := range []string{value.ProjectID, value.GuideID, value.CompilationID, value.SourceSnapshotID, value.SetupRunID, value.FinalizationID} {
		if !validUUID(id) {
			return errors.New("invalid target identity")
		}
	}
	for _, id := range []*string{value.ArtifactPolicyID, value.ArtifactProjectionOperationID} {
		if id != nil && !validUUID(*id) {
			return errors.New("invalid policy identity")
		}
	}
	for _, hash := range []*string{value.ArtifactPolicyHash, value.ArtifactProjectionOutputDigest} {
		if hash != nil && !contextPolicyDigest.MatchString(*hash) {
			return errors.New("invalid policy digest")
		}
	}
	if !proposalDigests([]string{value.SourceSnapshotHash, value.FinalizationFactsDigest, value.ResultHash, value.PreCatalogueManifestHash, value.PostCatalogueManifestHash}) {
		return errors.New("invalid target digest")
	}
	_, err = contextObject(fields["component_hashes"], &value.ComponentHashes, []string{
		"sufficiency_hash", "artifact_policy_hash", "requirement_inventory_hash", "pre_submit_hash", "post_submit_hash", "capability_suggestions_hash", "setup_notes_hash",
	}, nil)
	if err != nil || !proposalDigests([]string{value.ComponentHashes.SufficiencyHash, value.ComponentHashes.ArtifactPolicyHash, value.ComponentHashes.RequirementInventoryHash, value.ComponentHashes.PreSubmitHash, value.ComponentHashes.PostSubmitHash, value.ComponentHashes.CapabilitySuggestionsHash, value.ComponentHashes.SetupNotesHash}) {
		return errors.New("invalid component identities")
	}
	return nil
}

func validateProposalResult(raw json.RawMessage, value *ProposalResult) error {
	fields, err := contextObject(raw, value, []string{"status", "agent_version"}, []string{"setup_notes"})
	if err != nil {
		return err
	}
	if value.Status != "guide_blocked" && value.Status != "draft_ready" && value.Status != "draft_ready_with_warnings" {
		return errors.New("invalid proposal classification")
	}
	// Defaults mirror the public response model, not provider-input completeness.
	if _, present := fields["agent_name"]; !present {
		value.AgentName = "ProjectGuideCompilationAgent"
	}
	if _, present := fields["schema_version"]; !present {
		value.SchemaVersion = "project_guide_compilation_result.v1"
	}
	for _, key := range []string{"agent_name", "schema_version"} {
		if string(fields[key]) == "null" {
			return errors.New("null result field")
		}
	}
	if value.AgentName != "ProjectGuideCompilationAgent" || value.SchemaVersion != "project_guide_compilation_result.v1" {
		return errors.New("invalid proposal protocol")
	}
	if policy := fields["submission_artifact_policy"]; len(policy) > 0 && string(policy) != "null" {
		policyFields, err := contextObject(policy, value.SubmissionArtifactPolicy, []string{"maximum_file_size_bytes", "maximum_package_size_bytes"}, []string{"allowed_storage_schemes", "required_artifacts", "forbidden_artifacts", "required_evidence", "attestation_terms"})
		if err != nil {
			return err
		}
		// These are the public wire field ranges, not client-side evaluation of
		// the proposed policy. Optional archive limits retain arbitrary range.
		ceiling := big.NewInt(10 * 1024 * 1024 * 1024)
		for _, limit := range []*big.Int{value.SubmissionArtifactPolicy.MaximumFileSizeBytes, value.SubmissionArtifactPolicy.MaximumPackageSizeBytes} {
			if limit.Sign() <= 0 || limit.Cmp(ceiling) > 0 {
				return errors.New("invalid intake byte limit")
			}
		}
		for _, limit := range []*big.Int{value.SubmissionArtifactPolicy.MaximumArchiveSizeBytes, value.SubmissionArtifactPolicy.MaximumArchiveEntries} {
			if limit != nil && limit.Sign() <= 0 {
				return errors.New("invalid optional intake limit")
			}
		}
		if string(policyFields["packaging"]) == "null" {
			return errors.New("null packaging")
		}
		if _, present := policyFields["packaging"]; present && value.SubmissionArtifactPolicy.Packaging != "zip" {
			return errors.New("invalid packaging type")
		}
	}
	for _, key := range []string{"findings", "requirements", "pre_submit_bindings", "post_submit_bindings", "capability_suggestions"} {
		if _, present := fields[key]; !present {
			continue
		}
		var members []json.RawMessage
		if jsonv2.Unmarshal(fields[key], &members) != nil || members == nil {
			return errors.New("invalid result array")
		}
		for _, member := range members {
			var nested map[string]json.RawMessage
			switch key {
			case "findings":
				var item ProposalFinding
				nested, err = contextObject(member, &item, []string{"severity", "code", "message"}, nil)
				if err == nil && item.Severity != "blocking_gap" && item.Severity != "warning" && item.Severity != "info" {
					err = errors.New("invalid finding type")
				}
			case "requirements":
				var item ProposalRequirement
				nested, err = contextObject(member, &item, []string{"requirement_id", "statement", "disposition"}, nil)
				if err == nil {
					switch item.Disposition {
					case "platform_covered", "supported_pre_submit", "pre_submit_capability_gap", "supported_post_submit", "post_submit_capability_gap", "human_review", "project_lifecycle_policy", "guide_blocker", "informational":
					default:
						err = errors.New("invalid requirement classification")
					}
				}
				if err == nil && item.PlatformCoverage != nil {
					_, err = contextObject(nested["platform_coverage"], item.PlatformCoverage, []string{"capability_id", "capability_version", "stage"}, nil)
					if err == nil && !proposalStage(item.PlatformCoverage.Stage) {
						err = errors.New("invalid coverage stage")
					}
				}
			case "capability_suggestions":
				var item ProposalSuggestion
				nested, err = contextObject(member, &item, []string{"requirement_id", "stage", "title", "rationale", "evidence_refs"}, nil)
				if err == nil && len(item.EvidenceRefs) == 0 {
					err = errors.New("missing suggestion evidence")
				}
				if err == nil && !proposalStage(item.Stage) {
					err = errors.New("invalid suggestion stage")
				}
			case "pre_submit_bindings":
				var item ProposalPreBinding
				nested, err = contextObject(member, &item, []string{"requirement_id", "capability_id", "capability_version", "stage"}, nil)
				if err == nil && !proposalStage(item.Stage) {
					err = errors.New("invalid binding stage")
				}
			case "post_submit_bindings":
				var item ProposalPostBinding
				nested, err = contextObject(member, &item, []string{"requirement_id", "capability_id", "capability_version", "stage"}, nil)
				if err == nil && !proposalStage(item.Stage) {
					err = errors.New("invalid binding stage")
				}
				if err == nil {
					err = validateProposalParameters(nested["parameters"])
				}
			}
			if err != nil {
				return err
			}
			if err = validateProposalEvidence(nested["evidence_refs"]); err != nil {
				return err
			}
		}
	}
	return nil
}

func proposalStage(value string) bool { return value == "pre_submit" || value == "post_submit" }

func validateProposalEvidence(raw json.RawMessage) error {
	if len(raw) == 0 {
		return nil
	}
	var members []json.RawMessage
	if jsonv2.Unmarshal(raw, &members) != nil || members == nil {
		return errors.New("invalid evidence array")
	}
	for _, member := range members {
		var value ProposalEvidence
		fields, err := contextObject(member, &value, []string{"document_number"}, nil)
		if err != nil {
			return err
		}
		if value.DocumentNumber.Sign() <= 0 {
			return errors.New("invalid document number")
		}
		for _, key := range []string{"start_page", "end_page", "section"} {
			if _, present := fields[key]; !present {
				return errors.New("missing evidence field")
			}
		}
	}
	return nil
}

func validateProposalParameters(raw json.RawMessage) error {
	if len(raw) == 0 {
		return nil
	}
	var members []json.RawMessage
	if jsonv2.Unmarshal(raw, &members) != nil || members == nil {
		return errors.New("invalid parameters")
	}
	for _, member := range members {
		var value ProposalParameter
		if _, err := contextObject(member, &value, []string{"name", "value"}, nil); err != nil {
			return err
		}
		var scalar any
		if jsonv2.Unmarshal(value.Value, &scalar) != nil {
			return errors.New("invalid scalar")
		}
		switch item := scalar.(type) {
		case string, bool, float64:
		case []any:
			if len(item) == 0 {
				return errors.New("empty parameter array")
			}
			for _, atom := range item {
				switch atom.(type) {
				case string, bool, float64:
				default:
					return errors.New("invalid scalar array")
				}
			}
		default:
			return errors.New("invalid parameter value")
		}
	}
	return nil
}
