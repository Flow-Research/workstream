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

// ContributionPolicyReceipt describes one immutable event, including on replay.
type ContributionPolicyReceipt struct {
	EventID                     string   `json:"event_id"`
	OperationID                 string   `json:"operation_id"`
	RequestDigest               string   `json:"request_digest"`
	EventType                   string   `json:"event_type"`
	ActorProfileID              string   `json:"actor_profile_id"`
	ProjectID                   string   `json:"project_id"`
	ContributionPolicyID        string   `json:"contribution_policy_id"`
	ContributionPolicyVersionID string   `json:"contribution_policy_version_id"`
	VersionNumber               *big.Int `json:"version_number"`
	PriorCurrentVersionID       *string  `json:"prior_current_version_id"`
	PriorCurrentVersionNumber   *big.Int `json:"prior_current_version_number"`
	FromPolicyStatus            *string  `json:"from_policy_status"`
	ToPolicyStatus              string   `json:"to_policy_status"`
	FromVersionStatus           *string  `json:"from_version_status"`
	ToVersionStatus             string   `json:"to_version_status"`
	OccurredAt                  string   `json:"occurred_at"`
}

type policyRuleInput struct {
	ContributionType string                `json:"contribution_type"`
	CompensationMode string                `json:"compensation_mode"`
	Quantities       *policySizeQuantities `json:"quantities"`
	Quantity         *string               `json:"quantity"`
}

type policySizeQuantities struct {
	Small  string `json:"small"`
	Medium string `json:"medium"`
	Large  string `json:"large"`
}

// Validate wire shape only; the public owner decides graph and economic validity.
func validatePolicyInput(action string, body json.RawMessage) error {
	invalid := errors.New("--input must contain the closed public contribution-policy input")
	if len(body) == 0 || len(body) > MaxGuideInputBytes {
		return invalid
	}
	if action == "create" {
		var input struct {
			Name string `json:"name"`
		}
		if _, err := contextObject(body, &input, []string{"name"}, nil); err != nil || utf8.RuneCountInString(input.Name) < 1 || utf8.RuneCountInString(input.Name) > 200 {
			return invalid
		}
		return nil
	}
	if action != "update" {
		var input struct{}
		_, err := contextObject(body, &input, nil, nil)
		return err
	}
	var input struct {
		InstrumentType   *string           `json:"instrument_type"`
		UnitCode         *string           `json:"unit_code"`
		AdapterBindingID *string           `json:"adapter_binding_id"`
		Rules            []policyRuleInput `json:"rules"`
	}
	fields, err := contextObject(body, &input, []string{"rules"}, nil)
	if err != nil || !requiredNullable(fields, "instrument_type", "unit_code", "adapter_binding_id") || len(input.Rules) != 2 {
		return invalid
	}
	var rules []json.RawMessage
	if json.Unmarshal(fields["rules"], &rules) != nil {
		return invalid
	}
	paid, seen := false, map[string]bool{}
	for i, raw := range rules {
		rule := &input.Rules[i]
		members, err := contextObject(raw, rule, []string{"contribution_type", "compensation_mode"}, nil)
		if err != nil || seen[rule.ContributionType] || !oneOf(rule.ContributionType, "accepted_submission", "completed_review") || !oneOf(rule.CompensationMode, "unpaid", "compensated") {
			return invalid
		}
		seen[rule.ContributionType] = true
		if rule.CompensationMode == "unpaid" {
			if len(members) != 2 {
				return invalid
			}
			continue
		}
		paid = true
		if input.InstrumentType == nil || input.UnitCode == nil || input.AdapterBindingID == nil || !validUUID(*input.AdapterBindingID) || len(members) != 3 {
			return invalid
		}
		if rule.ContributionType == "accepted_submission" {
			if rule.Quantities == nil {
				return invalid
			}
			if _, err := contextObject(members["quantities"], rule.Quantities, []string{"small", "medium", "large"}, nil); err != nil {
				return invalid
			}
			for _, quantity := range []string{rule.Quantities.Small, rule.Quantities.Medium, rule.Quantities.Large} {
				if !validPolicyAmount(*input.InstrumentType, *input.UnitCode, quantity) {
					return invalid
				}
			}
		} else if rule.Quantity == nil || !validPolicyAmount(*input.InstrumentType, *input.UnitCode, *rule.Quantity) {
			return invalid
		}
	}
	if !paid && (input.InstrumentType != nil || input.UnitCode != nil || input.AdapterBindingID != nil) {
		return invalid
	}

	return nil
}

// MutateContributionPolicy sends one explicit public decision with no preflight.
func (c *Client) MutateContributionPolicy(ctx context.Context, action, project, policy, version string, body json.RawMessage, key string) (Result[ContributionPolicyReceipt], error) {
	var result Result[ContributionPolicyReceipt]
	path, err := contributionPolicyPath(project)
	if err != nil {
		return result, err
	}
	if !validUUID(key) || len(key) > 100 {
		return result, errors.New("--idempotency-key must be a UUID")
	}
	method, status := http.MethodPost, http.StatusOK
	switch action {
	case "create":
		path += "/drafts"
		status = http.StatusCreated
	case "update", "publish", "retire":
		if !validUUID(policy) || len(policy) > 100 || !validUUID(version) || len(version) > 100 {
			return result, errors.New("POLICY_ID and VERSION_ID must be UUIDs")
		}
		path += "/" + url.PathEscape(policy) + "/versions/" + url.PathEscape(version)
		if action == "update" {
			method = http.MethodPut
		}
		if action == "publish" {
			path += "/publication"
		}
		if action == "retire" {
			path += "/retirement"
		}
	default:
		return result, errors.New("unknown contribution-policy operation")
	}
	if err := validatePolicyInput(action, body); err != nil {
		return result, err
	}
	raw, err := c.requestWithKey(ctx, method, path, "", body, key, status)
	if err != nil {
		return result, policyMutationFailure(err)
	}
	var value ContributionPolicyReceipt
	fields, err := contextObject(raw, &value, []string{
		"event_id", "operation_id", "request_digest", "event_type", "actor_profile_id", "project_id", "contribution_policy_id", "contribution_policy_version_id", "version_number", "to_policy_status", "to_version_status", "occurred_at",
	}, nil)
	if err != nil || !requiredNullable(fields, "prior_current_version_id", "prior_current_version_number", "from_policy_status", "from_version_status") ||
		!validUUID(value.EventID) || !validUUID(value.ActorProfileID) || !sameUUID(value.OperationID, key) || !sameUUID(value.ProjectID, project) ||
		!validUUID(value.ContributionPolicyID) || !validUUID(value.ContributionPolicyVersionID) ||
		(action != "create" && (!sameUUID(value.ContributionPolicyID, policy) || !sameUUID(value.ContributionPolicyVersionID, version))) ||
		value.VersionNumber == nil || value.VersionNumber.Sign() <= 0 || !contextPolicyDigest.MatchString(value.RequestDigest) || !validTime(value.OccurredAt) ||
		!validPolicyTransition(action, value) || !c.safeMutationResponse(raw) {
		return result, policyMutationFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[ContributionPolicyReceipt]{Raw: raw, Value: value}, nil
}

func validPolicyTransition(action string, v ContributionPolicyReceipt) bool {
	prior, number := v.PriorCurrentVersionID, v.PriorCurrentVersionNumber
	if (prior == nil) != (number == nil) || (prior != nil && (!validUUID(*prior) || number.Sign() <= 0)) {
		return false
	}
	if action != "retire" && prior != nil && (sameUUID(*prior, v.ContributionPolicyVersionID) || number.Cmp(v.VersionNumber) >= 0) {
		return false
	}
	fromPolicy, fromVersion := "", ""
	if v.FromPolicyStatus != nil {
		fromPolicy = *v.FromPolicyStatus
	}
	if v.FromVersionStatus != nil {
		fromVersion = *v.FromVersionStatus
	}
	consistentPrior := (fromPolicy == "draft" && prior == nil) || (fromPolicy == "active" && prior != nil)
	switch action {
	case "create":
		return v.EventType == "draft_created" && v.FromVersionStatus == nil && v.ToVersionStatus == "draft" &&
			((v.FromPolicyStatus == nil && v.ToPolicyStatus == "draft" && prior == nil) ||
				(fromPolicy == "active" && v.ToPolicyStatus == "active" && prior != nil))
	case "update":
		return v.EventType == "draft_updated" && consistentPrior && v.ToPolicyStatus == fromPolicy && fromVersion == "draft" && v.ToVersionStatus == "draft"
	case "publish":
		return v.EventType == "published" && consistentPrior && v.ToPolicyStatus == "active" && fromVersion == "draft" && v.ToVersionStatus == "published"
	case "retire":
		return v.EventType == "retired" && fromPolicy == "active" && v.ToPolicyStatus == "retired" && fromVersion == "published" && v.ToVersionStatus == "retired" &&
			prior != nil && sameUUID(*prior, v.ContributionPolicyVersionID) && number.Cmp(v.VersionNumber) == 0
	}
	return false
}

func policyMutationFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "contribution-policy outcome unknown; replay only the unchanged action, selectors, input file contents and idempotency key; a policy read is observation, not rollback proof"
	}
	return err
}
