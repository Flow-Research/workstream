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
	"unicode"
	"unicode/utf8"
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
	RequirementID           string                      `json:"requirement_id"`
	Statement               string                      `json:"statement"`
	Disposition             string                      `json:"disposition"`
	ClassificationRationale *string                     `json:"classification_rationale"`
	CheckSpecification      *ProposalCheckSpecification `json:"check_specification"`
	PlatformCoverage        *ProposalPlatformCoverage   `json:"platform_coverage"`
	EvidenceRefs            []ProposalEvidence          `json:"evidence_refs"`
}

type ProposalCheckSpecification struct {
	EvaluationMethod       string                               `json:"evaluation_method"`
	ExecutionMode          string                               `json:"execution_mode"`
	MaximumDurationSeconds *big.Int                             `json:"maximum_duration_seconds"`
	StageRationale         string                               `json:"stage_rationale"`
	Inputs                 []ProposalCheckInput                 `json:"inputs"`
	CheckSteps             []string                             `json:"check_steps"`
	PassConditions         []string                             `json:"pass_conditions"`
	FailureFindings        []ProposalCheckFailureFinding        `json:"failure_findings"`
	PositiveTests          []string                             `json:"positive_tests"`
	NegativeTests          []ProposalCheckNegativeTest          `json:"negative_tests"`
	RuntimeDependencies    []ProposalCheckRuntimeDependency     `json:"runtime_dependencies"`
	InfrastructureFailures []ProposalCheckInfrastructureFailure `json:"infrastructure_failures"`
}

type ProposalCheckInput struct {
	InputID      string  `json:"input_id"`
	Kind         string  `json:"kind"`
	RelativePath *string `json:"relative_path"`
	Purpose      string  `json:"purpose"`
}

type ProposalCheckFailureFinding struct {
	Code      string `json:"code"`
	Level     string `json:"level"`
	Condition string `json:"condition"`
	Message   string `json:"message"`
}

type ProposalCheckNegativeTest struct {
	Name                 string   `json:"name"`
	Scenario             string   `json:"scenario"`
	ExpectedVerdict      string   `json:"expected_verdict"`
	ExpectedFindingCodes []string `json:"expected_finding_codes"`
}

type ProposalCheckRuntimeDependency struct {
	DependencyID    string `json:"dependency_id"`
	Kind            string `json:"kind"`
	Provisioning    string `json:"provisioning"`
	Purpose         string `json:"purpose"`
	UnavailableCode string `json:"unavailable_code"`
}

type ProposalCheckInfrastructureFailure struct {
	Code      string `json:"code"`
	Condition string `json:"condition"`
}

type ProposalPlatformCoverage struct {
	CapabilityID      string `json:"capability_id"`
	CapabilityVersion string `json:"capability_version"`
	Stage             string `json:"stage"`
}

type ProposalPreBinding struct {
	RequirementID     string              `json:"requirement_id"`
	CapabilityID      string              `json:"capability_id"`
	CapabilityVersion string              `json:"capability_version"`
	Stage             string              `json:"stage"`
	Parameters        []ProposalParameter `json:"parameters"`
}

type ProposalPostBinding struct {
	ProposalPreBinding
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
	return decodeGuideProposal(raw, project, guide, compilation)
}

func decodeGuideProposal(raw json.RawMessage, project, guide, compilation string) (Result[GuideProposal], error) {
	var result Result[GuideProposal]
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
		policyFields, err := contextObject(policy, value.SubmissionArtifactPolicy, nil, []string{"allowed_storage_schemes", "required_artifacts", "forbidden_artifacts", "required_evidence", "attestation_terms"})
		if err != nil {
			return err
		}
		// These are the public wire field ranges, not client-side evaluation of
		// the proposed policy. Optional archive limits retain arbitrary range.
		ceiling := big.NewInt(10 * 1024 * 1024 * 1024)
		for _, limit := range []*big.Int{value.SubmissionArtifactPolicy.MaximumFileSizeBytes, value.SubmissionArtifactPolicy.MaximumPackageSizeBytes} {
			if limit != nil && (limit.Sign() <= 0 || limit.Cmp(ceiling) > 0) {
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
				if err == nil {
					err = validateProposalRequirementSpecification(nested, &item)
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
				if err == nil && item.Stage != "pre_submit" {
					err = errors.New("invalid binding stage")
				}
				if err == nil {
					err = validateProposalParameters(nested["parameters"])
				}
			case "post_submit_bindings":
				var item ProposalPostBinding
				nested, err = contextObject(member, &item, []string{"requirement_id", "capability_id", "capability_version", "stage"}, nil)
				if err == nil && item.Stage != "post_submit" {
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

var proposalIdentifier = regexp.MustCompile(`^[a-z][a-z0-9_.-]{0,99}$`)

func validateProposalRequirementSpecification(fields map[string]json.RawMessage, value *ProposalRequirement) error {
	rationaleRaw, rationalePresent := fields["classification_rationale"]
	if rationalePresent {
		if string(rationaleRaw) == "null" || value.ClassificationRationale == nil || !proposalProse(*value.ClassificationRationale) {
			return errors.New("invalid classification rationale")
		}
	}
	raw, present := fields["check_specification"]
	if present && (string(raw) == "null" || value.CheckSpecification == nil) {
		return errors.New("invalid check specification")
	}
	checkerStage := ""
	supported := false
	switch value.Disposition {
	case "supported_pre_submit":
		checkerStage, supported = "pre_submit", true
	case "pre_submit_capability_gap":
		checkerStage = "pre_submit"
	case "supported_post_submit":
		checkerStage, supported = "post_submit", true
	case "post_submit_capability_gap":
		checkerStage = "post_submit"
	default:
		if present {
			return errors.New("check specification on non-checker requirement")
		}
	}
	if present && (!rationalePresent || len(value.EvidenceRefs) == 0) {
		return errors.New("incomplete typed check requirement")
	}
	if checkerStage != "" && rationalePresent && !present {
		return errors.New("typed check requirement lacks specification")
	}
	if !present {
		return nil // Retained results predate the typed specification fields.
	}
	return validateProposalCheckSpecification(raw, value.CheckSpecification, checkerStage, supported)
}

func validateProposalCheckSpecification(raw json.RawMessage, value *ProposalCheckSpecification, stage string, supported bool) error {
	fields, err := contextObject(raw, value, []string{
		"evaluation_method", "execution_mode", "maximum_duration_seconds", "stage_rationale", "inputs", "check_steps",
		"pass_conditions", "failure_findings", "positive_tests", "negative_tests", "runtime_dependencies", "infrastructure_failures",
	}, nil)
	if err != nil || stage == "" || value.MaximumDurationSeconds == nil || value.MaximumDurationSeconds.Sign() <= 0 || value.MaximumDurationSeconds.Cmp(big.NewInt(3600)) > 0 || !proposalProse(value.StageRationale) {
		return errors.New("invalid check specification")
	}
	if (stage == "pre_submit" && (value.ExecutionMode != "bounded_pre_submit" || value.MaximumDurationSeconds.Cmp(big.NewInt(60)) > 0)) ||
		(stage == "post_submit" && value.ExecutionMode != "background") {
		return errors.New("check stage conflicts with execution budget")
	}
	if value.EvaluationMethod != "static_inspection" && value.EvaluationMethod != "isolated_execution" && value.EvaluationMethod != "model_evaluation" {
		return errors.New("invalid evaluation method")
	}
	if stage == "pre_submit" && value.EvaluationMethod == "model_evaluation" {
		return errors.New("model evaluation must run after submission")
	}
	if err = validateProposalStringList(fields["check_steps"], 1, 20); err != nil {
		return err
	}
	if err = validateProposalStringList(fields["pass_conditions"], 1, 20); err != nil {
		return err
	}
	if err = validateProposalStringList(fields["positive_tests"], 1, 10); err != nil {
		return err
	}

	inputKinds := make(map[string]bool)
	inputIDs := make(map[string]bool)
	inputs, err := proposalObjectMembers(fields["inputs"], 1, 20)
	if err != nil {
		return err
	}
	for index, member := range inputs {
		item := &value.Inputs[index]
		itemFields, decodeErr := contextObject(member, item, []string{"input_id", "kind", "purpose"}, nil)
		if decodeErr != nil || !proposalIdentifier.MatchString(item.InputID) || inputIDs[item.InputID] || !proposalProse(item.Purpose) {
			return errors.New("invalid check input")
		}
		inputIDs[item.InputID] = true
		switch item.Kind {
		case "package", "manifest", "request_metadata", "task_context", "guide_context", "prepared_material":
			if _, hasPath := itemFields["relative_path"]; hasPath {
				return errors.New("unexpected input path")
			}
		case "relative_file", "relative_directory":
			pathRaw, hasPath := itemFields["relative_path"]
			if !hasPath || string(pathRaw) == "null" || item.RelativePath == nil || !proposalRelativePath(*item.RelativePath) {
				return errors.New("invalid input path")
			}
		default:
			return errors.New("invalid input kind")
		}
		inputKinds[item.Kind] = true
	}

	findingLevels := make(map[string]string)
	findingMembers, err := proposalObjectMembers(fields["failure_findings"], 1, 20)
	if err != nil {
		return err
	}
	for index, member := range findingMembers {
		item := &value.FailureFindings[index]
		if _, decodeErr := contextObject(member, item, []string{"code", "level", "condition", "message"}, nil); decodeErr != nil ||
			!proposalIdentifier.MatchString(item.Code) || findingLevels[item.Code] != "" || proposalInfraCode(item.Code) ||
			!proposalProse(item.Condition) || !proposalProse(item.Message) ||
			(item.Level != "warning" && item.Level != "error" && item.Level != "coverage_incomplete") {
			return errors.New("invalid failure finding")
		}
		findingLevels[item.Code] = item.Level
	}

	negativeNames := make(map[string]bool)
	negativeMembers, err := proposalObjectMembers(fields["negative_tests"], 1, 10)
	if err != nil {
		return err
	}
	for index, member := range negativeMembers {
		item := &value.NegativeTests[index]
		if _, decodeErr := contextObject(member, item, []string{"name", "scenario", "expected_verdict", "expected_finding_codes"}, []string{"expected_finding_codes"}); decodeErr != nil ||
			!proposalIdentifier.MatchString(item.Name) || negativeNames[item.Name] || !proposalProse(item.Scenario) ||
			(item.ExpectedVerdict != "passed" && item.ExpectedVerdict != "failed") || len(item.ExpectedFindingCodes) < 1 || len(item.ExpectedFindingCodes) > 10 {
			return errors.New("invalid negative test")
		}
		negativeNames[item.Name] = true
		seenCodes := make(map[string]bool)
		hasError := false
		for _, code := range item.ExpectedFindingCodes {
			level, exists := findingLevels[code]
			if !exists || seenCodes[code] {
				return errors.New("invalid expected finding code")
			}
			seenCodes[code] = true
			hasError = hasError || level == "error"
		}
		if (item.ExpectedVerdict == "failed") != hasError {
			return errors.New("negative test verdict conflicts with findings")
		}
	}

	dependencyKinds := make(map[string]bool)
	dependencyIDs := make(map[string]bool)
	usesTrial := false
	dependencyMembers, err := proposalObjectMembers(fields["runtime_dependencies"], 0, 10)
	if err != nil {
		return err
	}
	for index, member := range dependencyMembers {
		item := &value.RuntimeDependencies[index]
		if _, decodeErr := contextObject(member, item, []string{"dependency_id", "kind", "provisioning", "purpose", "unavailable_code"}, nil); decodeErr != nil ||
			!proposalIdentifier.MatchString(item.DependencyID) || dependencyIDs[item.DependencyID] || !proposalProse(item.Purpose) || !proposalInfraCode(item.UnavailableCode) {
			return errors.New("invalid runtime dependency")
		}
		expected := map[string][2]string{
			"checker_tool":       {"checker_implementation", "implementation_unavailable"},
			"isolated_execution": {"current_runner", "implementation_unavailable"},
			"nested_sandbox":     {"runtime_gap", "implementation_unavailable"},
			"task_context":       {"runtime_gap", "material_unavailable"},
			"guide_context":      {"runtime_gap", "material_unavailable"},
			"execution_capacity": {"runtime_gap", "capacity_exceeded"},
			"prepared_material":  {"runtime_gap", "material_unavailable"},
		}[item.Kind]
		valid := expected != [2]string{} && item.Provisioning == expected[0] && item.UnavailableCode == expected[1]
		if item.Kind == "model_service" {
			valid = item.UnavailableCode == "implementation_unavailable" &&
				(item.Provisioning == "model_proxy" || (!supported && item.Provisioning == "runtime_gap"))
		}
		if (item.Kind == "nested_sandbox" || item.Kind == "prepared_material") && item.Provisioning == "trial_proxy" {
			valid = stage == "post_submit" && item.UnavailableCode == expected[1]
			usesTrial = true
		}
		if !valid || (supported && item.Provisioning == "runtime_gap") {
			return errors.New("invalid runtime dependency provisioning")
		}
		dependencyIDs[item.DependencyID], dependencyKinds[item.Kind] = true, true
	}
	if usesTrial && !dependencyKinds["nested_sandbox"] {
		return errors.New("trial material requires an isolated trial dependency")
	}
	for _, kind := range []string{"task_context", "guide_context", "prepared_material"} {
		if inputKinds[kind] != dependencyKinds[kind] {
			return errors.New("material inputs and dependencies must match")
		}
	}
	if (value.EvaluationMethod == "model_evaluation" && !dependencyKinds["model_service"]) ||
		(value.EvaluationMethod == "isolated_execution" && !dependencyKinds["isolated_execution"]) {
		return errors.New("missing runtime dependency")
	}
	if stage == "pre_submit" && dependencyKinds["model_service"] {
		return errors.New("model service must run after submission")
	}

	infraCodes := make(map[string]bool)
	infraMembers, err := proposalObjectMembers(fields["infrastructure_failures"], 1, 5)
	if err != nil {
		return err
	}
	for index, member := range infraMembers {
		item := &value.InfrastructureFailures[index]
		if _, decodeErr := contextObject(member, item, []string{"code", "condition"}, nil); decodeErr != nil ||
			!proposalInfraCode(item.Code) || infraCodes[item.Code] || !proposalProse(item.Condition) {
			return errors.New("invalid infrastructure failure")
		}
		infraCodes[item.Code] = true
	}
	for _, dependency := range value.RuntimeDependencies {
		if !infraCodes[dependency.UnavailableCode] {
			return errors.New("dependency failure is not specified")
		}
	}
	return nil
}

func proposalObjectMembers(raw json.RawMessage, minimum, maximum int) ([]json.RawMessage, error) {
	var members []json.RawMessage
	if jsonv2.Unmarshal(raw, &members) != nil || members == nil || len(members) < minimum || len(members) > maximum {
		return nil, errors.New("invalid object array")
	}
	return members, nil
}

func validateProposalStringList(raw json.RawMessage, minimum, maximum int) error {
	var values []string
	if jsonv2.Unmarshal(raw, &values) != nil || values == nil || len(values) < minimum || len(values) > maximum {
		return errors.New("invalid text array")
	}
	for _, value := range values {
		if !proposalProse(value) {
			return errors.New("invalid specification text")
		}
	}
	return nil
}

func proposalProse(value string) bool {
	length := utf8.RuneCountInString(value)
	return utf8.ValidString(value) && length >= 1 && length <= 1000
}

func proposalInfraCode(value string) bool {
	switch value {
	case "capacity_exceeded", "deadline_exceeded", "material_unavailable", "implementation_unavailable", "invalid_output":
		return true
	default:
		return false
	}
}

func proposalRelativePath(value string) bool {
	// NFC is validated by the backend owner; this reader never resolves paths.
	if value == "" || !utf8.ValidString(value) || utf8.RuneCountInString(value) > 500 || strings.TrimSpace(value) != value || strings.HasPrefix(value, "/") || strings.HasPrefix(value, "~") ||
		strings.ContainsAny(value, `\\:%#`+"`$;|<>*?[]") {
		return false
	}
	for _, segment := range strings.Split(value, "/") {
		if segment == "" || segment == "." || segment == ".." {
			return false
		}
		for _, r := range segment {
			if unicode.Is(unicode.Cc, r) || unicode.Is(unicode.Cs, r) || unicode.Is(unicode.Cf, r) {
				return false
			}
		}
	}
	return true
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
	if jsonv2.Unmarshal(raw, &members) != nil || members == nil || len(members) > 50 {
		return errors.New("invalid parameters")
	}
	names := make(map[string]bool)
	for _, member := range members {
		var value ProposalParameter
		if _, err := contextObject(member, &value, []string{"name", "value"}, nil); err != nil || !proposalIdentifier.MatchString(value.Name) || names[value.Name] {
			return errors.New("invalid parameter")
		}
		names[value.Name] = true
		var scalar any
		if jsonv2.Unmarshal(value.Value, &scalar) != nil {
			return errors.New("invalid scalar")
		}
		switch item := scalar.(type) {
		case string, bool, float64:
		case []any:
			if len(item) == 0 || len(item) > 50 {
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
