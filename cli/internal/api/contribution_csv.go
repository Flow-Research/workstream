package api

import (
	"bytes"
	"encoding/csv"
	"encoding/json"
	"errors"
	"io"
	"reflect"
	"slices"
	"strings"
	"unicode/utf8"
)

// Exact public CSV schema; the backend owns serialization and neutralization.
var contributionColumns = []string{
	"contribution_id", "award_id", "project_id", "task_id", "task_size", "external_task_id",
	"source_type", "source_ref", "task_title", "submission_id", "contributor_id",
	"contributor_display_name", "contribution_type", "recorded_at", "accepted_at",
	"acceptance_source", "acceptance_review_id", "acceptance_routing_manifest_id",
	"source_final_acceptance_id", "source_review_id", "source_review_lease_id",
	"source_task_assignment_id", "artifact_hash", "contribution_policy_version_id",
	"policy_version_number", "award_definition_id", "instrument", "unit", "quantity",
}

func (c *Client) decodeContributionCSV(
	body []byte, filters ContributionFilters,
) ([]ContributionRecord, int, error) {
	bad := errors.New("invalid contribution CSV")
	if !utf8.Valid(body) {
		return nil, 0, bad
	}
	reader := csv.NewReader(bytes.NewReader(body))
	header, err := reader.Read()
	if err != nil || !slices.Equal(header, contributionColumns) {
		return nil, 0, bad
	}
	headerEnd := bytes.IndexByte(body, '\n') + 1
	if headerEnd == 0 {
		return nil, 0, bad
	}
	records := make([]map[string]any, 0)
	var previous map[string]any
	var previousID [16]byte
	var currentAwards []map[string]string
	for count := 0; ; count++ {
		row, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil || count >= 1000 {
			return nil, 0, bad
		}
		cells := make(map[string]string, len(header))
		for i, key := range header {
			if !c.safeMetadata(row[i]) || sameUUID(row[i], c.token) {
				return nil, 0, bad
			}
			cells[key] = row[i]
		}
		for _, key := range []string{"external_task_id", "source_type", "source_ref", "task_title", "contributor_display_name", "unit"} {
			value := cells[key]
			if strings.HasPrefix(value, "\t") || strings.HasPrefix(value, "\r") || strings.HasPrefix(value, "\n") ||
				strings.ContainsAny(firstRune(strings.TrimSpace(value)), "=+-@＝＋－＠") {
				return nil, 0, bad
			}
		}
		record := make(map[string]any)
		for _, key := range append(slices.Clone(contributionRequired[:len(contributionRequired)-1]), contributionNullable...) {
			value := cells[key]
			if key == "policy_version_number" {
				record[key] = json.Number(value)
			} else if value == "" && slices.Contains(contributionNullable, key) {
				record[key] = nil
			} else {
				record[key] = value
			}
		}
		id, valid := uuidIdentity(cells["contribution_id"])
		if !valid {
			return nil, 0, bad
		}
		if previous != nil && id == previousID {
			// Normalized identity selects the group; other repeated facts must
			// remain identical. A zero-award row cannot precede an award row.
			record["contribution_id"] = previous["contribution_id"]
			if !reflect.DeepEqual(record, previous) || len(currentAwards) == 0 || cells["award_id"] == "" {
				return nil, 0, bad
			}
		} else {
			previous, previousID = record, id
			currentAwards = make([]map[string]string, 0)
			records = append(records, record)
		}
		if cells["award_id"] == "" {
			for _, key := range []string{"award_definition_id", "instrument", "unit", "quantity"} {
				if cells[key] != "" {
					return nil, 0, bad
				}
			}
		} else {
			award := make(map[string]string)
			for _, key := range []string{"award_id", "award_definition_id", "instrument", "unit", "quantity"} {
				award[key] = cells[key]
			}
			currentAwards = append(currentAwards, award)
		}
		// Keep grouping comparison free of the per-row award set.
		copy := make(map[string]any, len(record)+1)
		for key, value := range record {
			copy[key] = value
		}
		copy["awards"] = currentAwards
		records[len(records)-1] = copy
	}
	raw, err := json.Marshal(records)
	if err != nil {
		return nil, 0, bad
	}
	if validateContributionRecords(raw, filters) != nil {
		return nil, 0, bad
	}
	var values []ContributionRecord
	if json.Unmarshal(raw, &values) != nil || values == nil {
		return nil, 0, bad
	}
	return values, headerEnd, nil
}

func firstRune(value string) string {
	for _, r := range value {
		return string(r)
	}
	return ""
}
