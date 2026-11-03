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
	ResultSchemaVersion            string         `json:"result_schema_version"`
	GuideVersion                   string         `json:"guide_version"`
	SourceSnapshotID               string         `json:"source_snapshot_id"`
	SourceSnapshotHash             string         `json:"source_snapshot_hash"`
	SetupRunID                     string         `json:"setup_run_id"`
	SetupGeneration                *big.Int       `json:"setup_generation"`
	FinalizationID                 string         `json:"finalization_id"`
	FinalizationFactsDigest        string         `json:"finalization_facts_digest"`
	ResultHash                     string         `json:"result_hash"`
	ComponentHashes                ProposalHashes `json:"component_hashes"`
	ArtifactPolicyID               *string        `json:"artifact_policy_id"`
	ArtifactPolicyHash             *string        `json:"artifact_policy_hash"`
	ArtifactProjectionOperationID  *string        `json:"artifact_projection_operation_id"`
	ArtifactProjectionOutputDigest *string        `json:"artifact_projection_output_digest"`
}

type ProposalHashes struct {
	SchemaVersion            string `json:"schema_version"`
	SufficiencyHash          string `json:"sufficiency_hash"`
	ArtifactPolicyHash       string `json:"artifact_policy_hash"`
	RequirementInventoryHash string `json:"requirement_inventory_hash"`
	PreSubmitHash            string `json:"pre_submit_hash"`
	PostSubmitHash           string `json:"post_submit_hash"`
}

type ProposalResult struct {
	Status                   string                `json:"status"`
	Findings                 []ProposalFinding     `json:"findings"`
	SubmissionArtifactPolicy *ProposalIntakePolicy `json:"submission_artifact_policy"`
	Requirements             []ProposalRequirement `json:"requirements"`
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
	SuggestionID            string                     `json:"suggestion_id"`
	Statement               string                     `json:"statement"`
	Stage                   string                     `json:"stage"`
	ClassificationRationale string                     `json:"classification_rationale"`
	CheckSpecification      ProposalCheckSpecification `json:"check_specification"`
	EvidenceRefs            []ProposalEvidence         `json:"evidence_refs"`
}

type ProposalCheckSpecification struct {
	EvaluationMethod    string                        `json:"evaluation_method"`
	Inputs              []ProposalCheckInput          `json:"inputs"`
	CheckSteps          []string                      `json:"check_steps"`
	PassConditions      []string                      `json:"pass_conditions"`
	FailureFindings     []ProposalCheckFailureFinding `json:"failure_findings"`
	PositiveTests       []string                      `json:"positive_tests"`
	NegativeTests       []ProposalCheckNegativeTest   `json:"negative_tests"`
	ImplementationNeeds []string                      `json:"implementation_needs"`
	InabilityToEvaluate []ProposalCheckInability      `json:"inability_to_evaluate"`
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

type ProposalCheckInability struct {
	Code      string `json:"code"`
	Condition string `json:"condition"`
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
		"project_id", "guide_id", "compilation_id", "result_schema_version", "guide_version", "source_snapshot_id", "source_snapshot_hash",
		"setup_run_id", "setup_generation", "finalization_id", "finalization_facts_digest", "result_hash", "component_hashes",
	}, nil)
	if err != nil || value.ResultSchemaVersion != "project_guide_check_specification.v1" {
		return errors.New("invalid proposal target")
	}
	for _, key := range []string{"artifact_policy_id", "artifact_policy_hash", "artifact_projection_operation_id", "artifact_projection_output_digest"} {
		if _, present := fields[key]; !present {
			return errors.New("missing nullable target")
		}
	}
	if value.SetupGeneration == nil || value.SetupGeneration.Sign() <= 0 {
		return errors.New("invalid generation")
	}
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
	if !proposalDigests([]string{value.SourceSnapshotHash, value.FinalizationFactsDigest, value.ResultHash}) {
		return errors.New("invalid target digest")
	}
	_, err = contextObject(fields["component_hashes"], &value.ComponentHashes, []string{
		"schema_version", "sufficiency_hash", "artifact_policy_hash", "requirement_inventory_hash", "pre_submit_hash", "post_submit_hash",
	}, nil)
	if err != nil || value.ComponentHashes.SchemaVersion != "project_guide_check_specification_hashes.v1" || !proposalDigests([]string{
		value.ComponentHashes.SufficiencyHash, value.ComponentHashes.ArtifactPolicyHash, value.ComponentHashes.RequirementInventoryHash,
		value.ComponentHashes.PreSubmitHash, value.ComponentHashes.PostSubmitHash,
	}) {
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
	if _, present := fields["agent_name"]; !present {
		value.AgentName = "ProjectGuideCompilationAgent"
	}
	if _, present := fields["schema_version"]; !present {
		value.SchemaVersion = "project_guide_check_specification.v1"
	}
	for _, key := range []string{"agent_name", "schema_version"} {
		if string(fields[key]) == "null" {
			return errors.New("null result field")
		}
	}
	if value.AgentName != "ProjectGuideCompilationAgent" || value.SchemaVersion != "project_guide_check_specification.v1" {
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
	for _, key := range []string{"findings", "requirements"} {
		if _, present := fields[key]; !present {
			continue
		}
		var members []json.RawMessage
		if jsonv2.Unmarshal(fields[key], &members) != nil || members == nil {
			return errors.New("invalid result array")
		}
		for _, member := range members {
			var nested map[string]json.RawMessage
			if key == "findings" {
				var item ProposalFinding
				nested, err = contextObject(member, &item, []string{"severity", "code", "message"}, nil)
				if err == nil && item.Severity != "blocking_gap" && item.Severity != "warning" && item.Severity != "info" {
					err = errors.New("invalid finding type")
				}
			} else {
				var item ProposalRequirement
				nested, err = contextObject(member, &item, []string{"suggestion_id", "statement", "stage", "classification_rationale", "check_specification", "evidence_refs"}, nil)
				if err == nil && (!proposalIdentifier.MatchString(item.SuggestionID) || !proposalStage(item.Stage) ||
					!proposalProse(item.Statement) || !proposalProse(item.ClassificationRationale) || len(item.EvidenceRefs) == 0) {
					err = errors.New("invalid check suggestion")
				}
				if err == nil {
					err = validateProposalCheckSpecification(nested["check_specification"], &item.CheckSpecification)
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

func validateProposalCheckSpecification(raw json.RawMessage, value *ProposalCheckSpecification) error {
	fields, err := contextObject(raw, value, []string{
		"evaluation_method", "inputs", "check_steps", "pass_conditions", "failure_findings",
		"positive_tests", "negative_tests", "implementation_needs", "inability_to_evaluate",
	}, nil)
	if err != nil || !proposalProse(value.EvaluationMethod) {
		return errors.New("invalid check specification")
	}
	for _, field := range []string{"check_steps", "pass_conditions", "positive_tests", "implementation_needs"} {
		maximum := 20
		if field == "positive_tests" || field == "implementation_needs" {
			maximum = 10
		}
		if err := validateProposalStringList(fields[field], 1, maximum); err != nil {
			return err
		}
	}
	inputs, err := proposalObjectMembers(fields["inputs"], 1, 20)
	if err != nil {
		return err
	}
	inputIDs := make(map[string]bool)
	for index, member := range inputs {
		item := &value.Inputs[index]
		itemFields, decodeErr := contextObject(member, item, []string{"input_id", "kind", "purpose"}, nil)
		if decodeErr != nil || !proposalIdentifier.MatchString(item.InputID) || !proposalIdentifier.MatchString(item.Kind) ||
			inputIDs[item.InputID] || !proposalProse(item.Purpose) {
			return errors.New("invalid check input")
		}
		if rawPath, present := itemFields["relative_path"]; present && (string(rawPath) == "null" || item.RelativePath == nil || !proposalRelativePath(*item.RelativePath)) {
			return errors.New("invalid input path")
		}
		inputIDs[item.InputID] = true
	}
	findingLevels := make(map[string]string)
	findings, err := proposalObjectMembers(fields["failure_findings"], 1, 20)
	if err != nil {
		return err
	}
	for index, member := range findings {
		item := &value.FailureFindings[index]
		if _, decodeErr := contextObject(member, item, []string{"code", "level", "condition", "message"}, nil); decodeErr != nil ||
			!proposalIdentifier.MatchString(item.Code) || findingLevels[item.Code] != "" ||
			!proposalProse(item.Condition) || !proposalProse(item.Message) || (item.Level != "warning" && item.Level != "error") {
			return errors.New("invalid failure finding")
		}
		findingLevels[item.Code] = item.Level
	}
	inabilityCodes := make(map[string]bool)
	inabilities, err := proposalObjectMembers(fields["inability_to_evaluate"], 1, 10)
	if err != nil {
		return err
	}
	for index, member := range inabilities {
		item := &value.InabilityToEvaluate[index]
		if _, decodeErr := contextObject(member, item, []string{"code", "condition"}, nil); decodeErr != nil ||
			!proposalIdentifier.MatchString(item.Code) || inabilityCodes[item.Code] || findingLevels[item.Code] != "" || !proposalProse(item.Condition) {
			return errors.New("invalid inability to evaluate")
		}
		inabilityCodes[item.Code] = true
	}
	negativeNames := make(map[string]bool)
	negativeTests, err := proposalObjectMembers(fields["negative_tests"], 1, 10)
	if err != nil {
		return err
	}
	for index, member := range negativeTests {
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
