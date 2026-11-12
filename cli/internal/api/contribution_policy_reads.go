package api

import (
	"context"
	"encoding/json"
	"errors"
	"math/big"
	"net/http"
	"net/url"
	"regexp"
	"strings"
)

type ContributionPolicySelection struct {
	ProjectID                 string  `json:"project_id"`
	ContributionPolicyID      string  `json:"contribution_policy_id"`
	CurrentPublishedVersionID *string `json:"current_published_version_id"`
	OpenDraftVersionID        *string `json:"open_draft_version_id"`
}

// A view is retained Finance history, not permission, publication or readiness.
type ContributionPolicyVersion struct {
	ProjectID                   string                   `json:"project_id"`
	ContributionPolicyID        string                   `json:"contribution_policy_id"`
	Name                        string                   `json:"name"`
	PolicyStatus                string                   `json:"policy_status"`
	ContributionPolicyVersionID string                   `json:"contribution_policy_version_id"`
	VersionNumber               *big.Int                 `json:"version_number"`
	VersionStatus               string                   `json:"version_status"`
	RewardModelVersion          int                      `json:"reward_model_version"`
	InstrumentType              *string                  `json:"instrument_type"`
	UnitCode                    *string                  `json:"unit_code"`
	AdapterBindingID            *string                  `json:"adapter_binding_id"`
	Rules                       []ContributionPolicyRule `json:"rules"`
}

type ContributionPolicyRule struct {
	RuleID           string                         `json:"rule_id"`
	ContributionType string                         `json:"contribution_type"`
	CompensationMode string                         `json:"compensation_mode"`
	Definitions      []ContributionPolicyDefinition `json:"definitions"`
}

type ContributionPolicyDefinition struct {
	RewardModelVersion int     `json:"reward_model_version"`
	TaskSize           *string `json:"task_size"`
	DefinitionID       string  `json:"definition_id"`
	InstrumentType     string  `json:"instrument_type"`
	UnitCode           string  `json:"unit_code"`
	Quantity           string  `json:"quantity"`
	AdapterBindingID   string  `json:"adapter_binding_id"`
}

func contributionPolicyPath(project string) (string, error) {
	if !validUUID(project) || len(project) > 100 {
		return "", errors.New("PROJECT_ID must be a UUID")
	}
	return "/api/v1/projects/" + url.PathEscape(project) + "/contribution-policies", nil
}

func (c *Client) CurrentContributionPolicy(ctx context.Context, project string) (Result[ContributionPolicySelection], error) {
	var result Result[ContributionPolicySelection]
	path, err := contributionPolicyPath(project)
	if err != nil {
		return result, err
	}
	raw, err := c.request(ctx, http.MethodGet, path+"/current", "", nil)
	if err != nil {
		return result, err
	}
	var value ContributionPolicySelection
	fields, err := contextObject(raw, &value, []string{"project_id", "contribution_policy_id"}, nil)
	if err != nil || !requiredNullable(fields, "current_published_version_id", "open_draft_version_id") ||
		!sameUUID(value.ProjectID, project) || !validUUID(value.ContributionPolicyID) || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	for _, id := range []*string{value.CurrentPublishedVersionID, value.OpenDraftVersionID} {
		if id != nil && !validUUID(*id) {
			return result, &Failure{Code: "invalid_api_response"}
		}
	}
	if (value.CurrentPublishedVersionID == nil && value.OpenDraftVersionID == nil) ||
		(value.CurrentPublishedVersionID != nil && value.OpenDraftVersionID != nil && sameUUID(*value.CurrentPublishedVersionID, *value.OpenDraftVersionID)) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[ContributionPolicySelection]{Raw: raw, Value: value}, nil
}

func (c *Client) ContributionPolicy(ctx context.Context, project, policy string, version *string) (Result[ContributionPolicyVersion], error) {
	var result Result[ContributionPolicyVersion]
	path, err := contributionPolicyPath(project)
	if err != nil {
		return result, err
	}
	if !validUUID(policy) || len(policy) > 100 || (version != nil && (!validUUID(*version) || len(*version) > 100)) {
		return result, errors.New("POLICY_ID and an explicit --version must be UUIDs")
	}
	query := ""
	if version != nil {
		query = url.Values{"version_id": {*version}}.Encode()
	}
	raw, err := c.request(ctx, http.MethodGet, path+"/"+url.PathEscape(policy), query, nil)
	if err != nil {
		return result, err
	}
	var value ContributionPolicyVersion
	fields, err := contextObject(raw, &value, policyVersionFields, nil)
	if err != nil || !validPolicyVersion(fields, &value) || !sameUUID(value.ProjectID, project) ||
		!sameUUID(value.ContributionPolicyID, policy) ||
		(version != nil && !sameUUID(value.ContributionPolicyVersionID, *version)) || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[ContributionPolicyVersion]{Raw: raw, Value: value}, nil
}

var policyVersionFields = []string{
	"project_id", "contribution_policy_id", "name", "policy_status", "contribution_policy_version_id", "version_number", "version_status", "reward_model_version", "rules",
}

// validPolicyVersion checks one decoded version view and its closed rule graph.
func validPolicyVersion(fields map[string]json.RawMessage, value *ContributionPolicyVersion) bool {
	if !validUUID(value.ProjectID) || !validUUID(value.ContributionPolicyID) || !validUUID(value.ContributionPolicyVersionID) ||
		strings.TrimSpace(value.Name) == "" || value.VersionNumber == nil || value.VersionNumber.Sign() <= 0 ||
		(value.PolicyStatus != "draft" && value.PolicyStatus != "active" && value.PolicyStatus != "retired") ||
		(value.VersionStatus != "draft" && value.VersionStatus != "published" && value.VersionStatus != "retired") ||
		value.Rules == nil || (len(value.Rules) != 0 && len(value.Rules) != 2) || !requiredNullable(fields, "instrument_type", "unit_code", "adapter_binding_id") ||
		(value.RewardModelVersion != 1 && value.RewardModelVersion != 2) {
		return false
	}
	var rules []json.RawMessage
	if err := json.Unmarshal(fields["rules"], &rules); err != nil {
		return false
	}
	headerPresent := value.InstrumentType != nil && value.UnitCode != nil && value.AdapterBindingID != nil
	headerAbsent := value.InstrumentType == nil && value.UnitCode == nil && value.AdapterBindingID == nil
	if (!headerPresent && !headerAbsent) || (value.RewardModelVersion == 1 && !headerAbsent) ||
		(headerPresent && (!validUUID(*value.AdapterBindingID) || !validPolicyAmount(*value.InstrumentType, *value.UnitCode, "1"))) {
		return false
	}
	paid := false
	seenRules, seenDefinitions := make(map[[16]byte]bool), make(map[[16]byte]bool)
	seenTypes := make(map[string]bool)
	for index, rawRule := range rules {
		rule := &value.Rules[index]
		members, err := contextObject(rawRule, rule, []string{"rule_id", "contribution_type", "compensation_mode", "definitions"}, nil)
		id, valid := uuidIdentity(rule.RuleID)
		if err != nil || !valid || seenRules[id] || seenTypes[rule.ContributionType] ||
			(rule.ContributionType != "accepted_submission" && rule.ContributionType != "completed_review") ||
			(rule.CompensationMode != "unpaid" && rule.CompensationMode != "compensated") || rule.Definitions == nil {
			return false
		}
		seenRules[id], seenTypes[rule.ContributionType] = true, true
		var definitions []json.RawMessage
		if err := json.Unmarshal(members["definitions"], &definitions); err != nil {
			return false
		}
		paid = paid || rule.CompensationMode == "compensated"
		if rule.CompensationMode == "unpaid" && len(rule.Definitions) != 0 {
			return false
		}
		if rule.CompensationMode == "compensated" {
			expected := 1
			if value.RewardModelVersion == 2 && rule.ContributionType == "accepted_submission" {
				expected = 3
			}
			if value.RewardModelVersion == 1 {
				if len(rule.Definitions) < 1 || len(rule.Definitions) > 2 {
					return false
				}
			} else if len(rule.Definitions) != expected || !headerPresent {
				return false
			}
		}
		seenSizes := make(map[string]bool)
		seenInstruments := make(map[string]bool)
		for index, rawDefinition := range definitions {
			definition := &rule.Definitions[index]
			definitionFields, err := contextObject(rawDefinition, definition, []string{"definition_id", "instrument_type", "unit_code", "quantity", "adapter_binding_id", "reward_model_version"}, nil)
			id, valid := uuidIdentity(definition.DefinitionID)
			if err != nil || !valid || seenDefinitions[id] || !validUUID(definition.AdapterBindingID) ||
				!validPolicyAmount(definition.InstrumentType, definition.UnitCode, definition.Quantity) ||
				definition.RewardModelVersion != value.RewardModelVersion || !requiredNullable(definitionFields, "task_size") {
				return false
			}
			if value.RewardModelVersion == 1 {
				if definition.TaskSize != nil || seenInstruments[definition.InstrumentType] {
					return false
				}
			} else {
				if !headerPresent || definition.InstrumentType != *value.InstrumentType || definition.UnitCode != *value.UnitCode || !sameUUID(definition.AdapterBindingID, *value.AdapterBindingID) {
					return false
				}
				if rule.ContributionType == "accepted_submission" {
					if definition.TaskSize == nil || !oneOf(*definition.TaskSize, "small", "medium", "large") || seenSizes[*definition.TaskSize] {
						return false
					}
					seenSizes[*definition.TaskSize] = true
				} else if definition.TaskSize != nil {
					return false
				}
			}
			seenDefinitions[id], seenInstruments[definition.InstrumentType] = true, true
		}
	}
	if value.VersionStatus != "draft" && len(value.Rules) != 2 {
		return false
	}
	if value.RewardModelVersion == 2 && paid != headerPresent {
		return false
	}
	return true
}

var policyQuantity = regexp.MustCompile(`^(0|[1-9][0-9]{0,19})(\.[0-9]{1,18})?$`)
var policyCurrency = regexp.MustCompile(`^[A-Z]{3}$`)
var policyUnit = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9._:-]{0,31}$`)

func validPolicyAmount(instrument, unit, quantity string) bool {
	if !policyQuantity.MatchString(quantity) || !strings.ContainsAny(quantity, "123456789") {
		return false
	}
	return instrument == "money" && policyCurrency.MatchString(unit) ||
		instrument == "project_points" && policyUnit.MatchString(unit) && !strings.Contains(quantity, ".")
}

// ContributionPolicyVersionItem is one stored version with its lifecycle instants.
type ContributionPolicyVersionItem struct {
	ContributionPolicyVersion
	CreatedAt   string  `json:"created_at"`
	PublishedAt *string `json:"published_at"`
	RetiredAt   *string `json:"retired_at"`
}

type ContributionPolicyVersionPage struct {
	Items  []ContributionPolicyVersionItem `json:"items"`
	Cursor *string                         `json:"next_cursor"`
}

// ContributionPolicyVersions lists every stored version of the project's policies, oldest first.
func (c *Client) ContributionPolicyVersions(ctx context.Context, project string, q PageQuery) (Result[ContributionPolicyVersionPage], error) {
	var result Result[ContributionPolicyVersionPage]
	if q.ProjectID != nil || q.TaskID != nil || q.State != nil || q.Status != nil || q.UpdatedSince != nil || q.Outcome != nil {
		return result, errors.New("policy versions accept no filters")
	}
	path, err := contributionPolicyPath(project)
	if err != nil {
		return result, err
	}
	query, err := q.encode()
	if err != nil {
		return result, err
	}
	raw, fields, items, err := c.readPage(ctx, path, query, q.Limit)
	if err != nil {
		return result, err
	}
	page := ContributionPolicyVersionPage{Items: make([]ContributionPolicyVersionItem, 0, len(items))}
	if json.Unmarshal(fields["next_cursor"], &page.Cursor) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for _, item := range items {
		var value ContributionPolicyVersionItem
		itemFields, err := contextObject(item, &value, append(policyVersionFields[:len(policyVersionFields):len(policyVersionFields)], "created_at"), nil)
		id, _ := uuidIdentity(value.ContributionPolicyVersionID)
		if err != nil || !validPolicyVersion(itemFields, &value.ContributionPolicyVersion) || !sameUUID(value.ProjectID, project) ||
			!requiredNullable(itemFields, "published_at", "retired_at") || !validTime(value.CreatedAt) ||
			(value.PublishedAt != nil && !validTime(*value.PublishedAt)) || (value.RetiredAt != nil && !validTime(*value.RetiredAt)) ||
			(value.VersionStatus == "draft") != (value.PublishedAt == nil) || (value.VersionStatus == "retired") != (value.RetiredAt != nil) ||
			seen[id] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		page.Items = append(page.Items, value)
	}
	return Result[ContributionPolicyVersionPage]{Raw: raw, Value: page}, nil
}
