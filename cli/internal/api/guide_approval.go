package api

import (
	"context"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"net/http"
	"net/url"
	"slices"
	"strings"
)

type guideApprovalInput struct {
	Target                               ProposalTarget         `json:"target"`
	PreSubmitAttachments                 []guideImageAttachment `json:"pre_submit_attachments"`
	PostSubmitAttachments                []guideImageAttachment `json:"post_submit_attachments"`
	AcknowledgedWarningHashes            []string               `json:"acknowledged_warning_hashes"`
	ExpectedPreviousApprovalOperationID  *string                `json:"expected_previous_approval_operation_id"`
	ExpectedPreviousApprovalOutputDigest *string                `json:"expected_previous_approval_output_digest"`
}

type guideImageAttachment struct {
	RequirementID       string          `json:"requirement_id"`
	RegistryEntryID     string          `json:"registry_entry_id"`
	RegistryEntryDigest string          `json:"registry_entry_digest"`
	Configuration       json.RawMessage `json:"configuration"`
}

// GuideApproval is immutable intake approval, not post-policy or activation.
type GuideApproval struct {
	OperationID                string   `json:"operation_id"`
	TargetDigest               string   `json:"target_digest"`
	ArtifactPolicyID           string   `json:"artifact_policy_id"`
	EffectivePolicyID          string   `json:"effective_policy_id"`
	EffectivePolicyHash        string   `json:"effective_policy_hash"`
	PreSubmitPolicyID          string   `json:"pre_submit_policy_id"`
	PreSubmitBundleHash        string   `json:"pre_submit_bundle_hash"`
	EffectivePreSubmitPlanHash string   `json:"effective_pre_submit_plan_hash"`
	AcknowledgedWarningHashes  []string `json:"acknowledged_warning_hashes"`
}

func (c *Client) ApproveGuidePreSubmission(ctx context.Context, project, guide, compilation string, body json.RawMessage, key string) (Result[GuideApproval], error) {
	var result Result[GuideApproval]
	for _, id := range []string{project, guide, compilation, key} {
		if !validUUID(id) || len(id) > 100 {
			return result, errors.New("project, guide, compilation and --idempotency-key must be UUIDs")
		}
	}
	input, err := decodeGuideApprovalInput(body)
	if err != nil || !sameUUID(input.Target.ProjectID, project) || !sameUUID(input.Target.GuideID, guide) || !sameUUID(input.Target.CompilationID, compilation) {
		return result, errors.New("--input must contain the bounded public approval request for the selected project, guide and compilation")
	}
	raw, err := c.requestWithKey(ctx, http.MethodPost,
		"/api/v1/projects/"+url.PathEscape(project)+"/guides/"+url.PathEscape(guide)+"/compilations/"+url.PathEscape(compilation)+"/pre-submission-approval",
		"", body, key, http.StatusOK)
	if err != nil {
		return result, guideApprovalFailure(err)
	}
	var value GuideApproval
	_, err = contextObject(raw, &value, []string{
		"operation_id", "target_digest", "artifact_policy_id", "effective_policy_id", "effective_policy_hash",
		"pre_submit_policy_id", "pre_submit_bundle_hash", "effective_pre_submit_plan_hash", "acknowledged_warning_hashes",
	}, []string{"acknowledged_warning_hashes"})
	if err != nil || !validGuideApproval(value, input) {
		return result, guideApprovalFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[GuideApproval]{Raw: raw, Value: value}, nil
}

func decodeGuideApprovalInput(raw json.RawMessage) (guideApprovalInput, error) {
	value := guideApprovalInput{AcknowledgedWarningHashes: []string{}}
	if len(raw) == 0 || len(raw) > MaxGuideInputBytes {
		return value, errors.New("invalid approval input size")
	}
	fields, err := contextObject(raw, &value, []string{"target", "pre_submit_attachments", "post_submit_attachments"}, []string{"acknowledged_warning_hashes"})
	if err != nil || validateProposalTarget(fields["target"], &value.Target) != nil ||
		!validApprovalWarnings(value.AcknowledgedWarningHashes) ||
		!validGuideImageAttachments(fields["pre_submit_attachments"]) ||
		!validGuideImageAttachments(fields["post_submit_attachments"]) {
		return value, errors.New("invalid approval input")
	}
	previous, digest := value.ExpectedPreviousApprovalOperationID, value.ExpectedPreviousApprovalOutputDigest
	if (previous == nil) != (digest == nil) || (previous != nil && (!validUUID(*previous) || !contextPolicyDigest.MatchString(*digest))) {
		return value, errors.New("invalid previous approval identity")
	}
	return value, nil
}

func validGuideImageAttachments(raw json.RawMessage) bool {
	var members []json.RawMessage
	if jsonv2.Unmarshal(raw, &members) != nil || members == nil || len(members) > 200 {
		return false
	}
	previous := ""
	for _, member := range members {
		var attachment guideImageAttachment
		fields, err := contextObject(member, &attachment, []string{
			"requirement_id", "registry_entry_id", "registry_entry_digest", "configuration",
		}, nil)
		if err != nil || !proposalIdentifier.MatchString(attachment.RequirementID) ||
			attachment.RequirementID <= previous ||
			strings.HasPrefix(attachment.RequirementID, "workstream.") ||
			!contextPolicyDigest.MatchString(attachment.RegistryEntryDigest) {
			return false
		}
		identity, valid := uuidIdentity(attachment.RegistryEntryID)
		if !valid || identity[6]>>4 != 7 || identity[8]&0xc0 != 0x80 {
			return false
		}
		var configuration map[string]json.RawMessage
		if jsonv2.Unmarshal(fields["configuration"], &configuration) != nil || configuration == nil {
			return false
		}
		previous = attachment.RequirementID
	}
	return true
}

func validApprovalWarnings(values []string) bool {
	if len(values) > 200 || !proposalDigests(values) {
		return false
	}
	seen := make(map[string]bool, len(values))
	for _, value := range values {
		if seen[value] {
			return false
		}
		seen[value] = true
	}
	return true
}

func validGuideApproval(value GuideApproval, input guideApprovalInput) bool {
	for _, id := range []string{value.OperationID, value.ArtifactPolicyID, value.EffectivePolicyID, value.PreSubmitPolicyID} {
		identity, valid := uuidIdentity(id)
		// Match Python UUID.version: a v7 nibble alone is not an RFC UUIDv7.
		if !valid || identity[6]>>4 != 7 || identity[8]&0xc0 != 0x80 {
			return false
		}
	}
	return input.Target.ArtifactPolicyID != nil && sameUUID(value.ArtifactPolicyID, *input.Target.ArtifactPolicyID) &&
		proposalDigests([]string{value.TargetDigest, value.EffectivePolicyHash, value.PreSubmitBundleHash, value.EffectivePreSubmitPlanHash}) &&
		validApprovalWarnings(value.AcknowledgedWarningHashes) && slices.Equal(value.AcknowledgedWarningHashes, input.AcknowledgedWarningHashes)
}

func guideApprovalFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "intake approval outcome unknown; replay only the unchanged project, guide, compilation, input file contents and idempotency key"
	}
	return err
}
