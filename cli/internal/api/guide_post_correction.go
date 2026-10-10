package api

import (
	"context"
	"encoding/json"
	"errors"
	"math/big"
	"net/http"
	"net/url"
	"unicode/utf8"
)

func (c *Client) CorrectGuidePostSubmission(ctx context.Context, project, guide, compilation, policy string, body json.RawMessage, key string) (Result[PostPolicyReceipt], error) {
	var result Result[PostPolicyReceipt]
	for _, id := range []string{project, guide, compilation, policy, key} {
		if !validUUID(id) || len(id) > 100 {
			return result, errors.New("project, guide, compilation, policy and --idempotency-key must be UUIDs")
		}
	}
	var input struct {
		Target PostPolicyTarget `json:"target"`
		Reason string           `json:"reason"`
	}
	fields, err := contextObject(body, &input, []string{"target", "reason"}, nil)
	if len(body) == 0 || len(body) > MaxGuideInputBytes || err != nil ||
		utf8.RuneCountInString(input.Reason) < 1 || utf8.RuneCountInString(input.Reason) > 4000 ||
		decodePostPolicyTarget(fields["target"], &input.Target) != nil ||
		!sameUUID(input.Target.Proposal.ProjectID, project) || !sameUUID(input.Target.Proposal.GuideID, guide) ||
		!sameUUID(input.Target.Proposal.CompilationID, compilation) || !sameUUID(input.Target.PolicyID, policy) {
		return result, errors.New("--input must contain the bounded public correction request with target and reason for the selected project, guide, compilation and policy")
	}
	raw, err := c.requestWithKey(ctx, http.MethodPost,
		"/api/v1/projects/"+url.PathEscape(project)+"/guides/"+url.PathEscape(guide)+"/compilations/"+url.PathEscape(compilation)+"/post-submission-policies/"+url.PathEscape(policy)+"/corrections",
		"", body, key, http.StatusCreated)
	if err != nil {
		return result, postCorrectionFailure(err)
	}
	var value PostPolicyReceipt
	fields, err = contextObject(raw, &value, []string{"operation_id", "kind", "target", "correction"}, nil)
	identity, valid := uuidIdentity(value.OperationID)
	if err != nil || !valid || identity[6]>>4 != 7 || identity[8]&0xc0 != 0x80 ||
		!c.safeMetadata(value.OperationID) || sameUUID(value.OperationID, c.token) || value.Kind != "correction" ||
		decodePostPolicyTarget(fields["target"], &value.Target) != nil || !samePostPolicyTarget(value.Target, input.Target) ||
		validateGuideCorrection(fields["correction"], value.Correction, input.Target.Upstream.TargetDigest) != nil {
		return result, postCorrectionFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	correction := value.Correction
	if !c.safeMetadata(correction.OperationID) || !c.safeMetadata(correction.SuccessorSetupRunID) ||
		!c.safeMetadata(correction.FeedbackHash) ||
		sameUUID(correction.OperationID, c.token) || sameUUID(correction.SuccessorSetupRunID, c.token) ||
		correction.SuccessorSetupGeneration.Cmp(new(big.Int).Add(input.Target.Proposal.SetupGeneration, big.NewInt(1))) != 0 {
		return result, postCorrectionFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[PostPolicyReceipt]{Raw: raw, Value: value}, nil
}

func postCorrectionFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "post-submission correction outcome unknown; replay only the unchanged project, guide, compilation, policy, input file contents and idempotency key"
	}
	return err
}
