package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"slices"
)

// PostPolicyApproval is a retained decision receipt, not guide activation.
type PostPolicyApproval struct {
	OperationID string           `json:"operation_id"`
	Kind        string           `json:"kind"`
	Target      PostPolicyTarget `json:"target"`
	Correction  *GuideCorrection `json:"correction"`
}

func (c *Client) ApproveGuidePostSubmission(ctx context.Context, project, guide, compilation, policy string, body json.RawMessage, key string) (Result[PostPolicyApproval], error) {
	var result Result[PostPolicyApproval]
	for _, id := range []string{project, guide, compilation, policy, key} {
		if !validUUID(id) || len(id) > 100 {
			return result, errors.New("project, guide, compilation, policy and --idempotency-key must be UUIDs")
		}
	}
	var input struct {
		Target PostPolicyTarget `json:"target"`
	}
	fields, err := contextObject(body, &input, []string{"target"}, nil)
	if len(body) == 0 || len(body) > MaxGuideInputBytes || err != nil ||
		decodePostPolicyTarget(fields["target"], &input.Target) != nil ||
		!sameUUID(input.Target.Proposal.ProjectID, project) || !sameUUID(input.Target.Proposal.GuideID, guide) ||
		!sameUUID(input.Target.Proposal.CompilationID, compilation) || !sameUUID(input.Target.PolicyID, policy) {
		return result, errors.New("--input must contain the bounded public approval request for the selected project, guide, compilation and policy")
	}
	raw, err := c.requestWithKey(ctx, http.MethodPost,
		"/api/v1/projects/"+url.PathEscape(project)+"/guides/"+url.PathEscape(guide)+"/compilations/"+url.PathEscape(compilation)+"/post-submission-policies/"+url.PathEscape(policy)+"/approval",
		"", body, key, http.StatusOK)
	if err != nil {
		return result, postApprovalFailure(err)
	}
	var value PostPolicyApproval
	fields, err = contextObject(raw, &value, []string{"operation_id", "kind", "target"}, nil)
	identity, valid := uuidIdentity(value.OperationID)
	if err != nil || !valid || identity[6]>>4 != 7 || identity[8]&0xc0 != 0x80 || !c.safeMetadata(value.OperationID) ||
		value.Kind != "approve" || !requiredNullable(fields, "correction") || value.Correction != nil ||
		decodePostPolicyTarget(fields["target"], &value.Target) != nil || !samePostPolicyTarget(value.Target, input.Target) {
		return result, postApprovalFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[PostPolicyApproval]{Raw: raw, Value: value}, nil
}

func samePostPolicyTarget(a, b PostPolicyTarget) bool {
	if !sameProposalTarget(a.Proposal, b.Proposal) || !sameUUID(a.PolicyID, b.PolicyID) ||
		!sameUUID(a.ProjectionOperationID, b.ProjectionOperationID) || a.PolicyHash != b.PolicyHash ||
		a.UpstreamOutputDigest != b.UpstreamOutputDigest ||
		(a.PredecessorPolicyID == nil) != (b.PredecessorPolicyID == nil) ||
		(a.PredecessorPolicyID != nil && !sameUUID(*a.PredecessorPolicyID, *b.PredecessorPolicyID)) {
		return false
	}
	x, y := a.Upstream, b.Upstream
	return sameUUID(x.OperationID, y.OperationID) && sameUUID(x.ArtifactPolicyID, y.ArtifactPolicyID) &&
		sameUUID(x.EffectivePolicyID, y.EffectivePolicyID) && sameUUID(x.PreSubmitPolicyID, y.PreSubmitPolicyID) &&
		x.TargetDigest == y.TargetDigest && x.EffectivePolicyHash == y.EffectivePolicyHash &&
		x.PreSubmitBundleHash == y.PreSubmitBundleHash && x.EffectivePreSubmitPlanHash == y.EffectivePreSubmitPlanHash &&
		slices.Equal(x.AcknowledgedWarningHashes, y.AcknowledgedWarningHashes)
}

func postApprovalFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "post-submission approval outcome unknown; replay only the unchanged project, guide, compilation, policy, input file contents and idempotency key"
	}
	return err
}
