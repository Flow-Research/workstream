package taskimport

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"
)

// ValidateJSON checks the canonical server input without rewriting its bytes.
// The commitment is therefore usable for separate declaration and upload.
func ValidateJSON(body []byte) (Conversion, error) {
	if len(body) == 0 || len(body) > MaxBytes {
		return Conversion{}, invalid(0, "document", "requires_1_to_8388608_bytes")
	}
	if !utf8.Valid(body) {
		return Conversion{}, invalid(0, "document", "requires_utf8_without_nul")
	}
	fields, err := jsonObject(body, map[string]bool{"schema_version": true, "metadata": true, "tasks": true})
	if err != nil {
		return Conversion{}, invalid(0, "document", "invalid_json_document")
	}
	version, err := jsonString(fields["schema_version"], false)
	if err != nil || version != "workstream.task_import.v1" {
		return Conversion{}, invalid(0, "schema_version", "invalid_schema_version")
	}
	if raw, present := fields["metadata"]; present {
		metadata, err := jsonObject(raw, map[string]bool{"label": true})
		if err != nil {
			return Conversion{}, invalid(0, "metadata", "invalid_metadata")
		}
		if raw, present := metadata["label"]; present && !jsonNull(raw) {
			label, err := jsonString(raw, false)
			if err != nil || len(label) == 0 || !validText(label, 255, false) {
				return Conversion{}, invalid(0, "label", "invalid_label")
			}
		}
	}
	var members []json.RawMessage
	if jsonv2.Unmarshal(fields["tasks"], &members) != nil || len(members) < 1 || len(members) > MaxRows {
		return Conversion{}, invalid(0, "tasks", "requires_1_to_500_rows")
	}
	seen := make(map[string]bool)
	for index, raw := range members {
		id, err := validateJSONRow(raw, index+1)
		if err != nil {
			return Conversion{}, err
		}
		if seen[id] {
			return Conversion{}, invalid(index+1, "external_task_id", "duplicate_external_task_id")
		}
		seen[id] = true
	}
	sum := sha256.Sum256(body)
	return Conversion{Bytes: body, SHA256: "sha256:" + hex.EncodeToString(sum[:]), ByteCount: len(body), RowCount: len(members)}, nil
}

func jsonObject(raw []byte, allowed map[string]bool) (map[string]json.RawMessage, error) {
	var fields map[string]json.RawMessage
	if err := jsonv2.Unmarshal(raw, &fields); err != nil {
		return nil, err
	}
	if fields == nil {
		return nil, invalid(0, "object", "requires_object")
	}
	for field := range fields {
		if !allowed[field] {
			return nil, invalid(0, "object", "unknown_field")
		}
	}
	return fields, nil
}

func jsonString(raw []byte, nullable bool) (string, error) {
	if nullable && jsonNull(raw) {
		return "", nil
	}
	var value *string
	if err := jsonv2.Unmarshal(raw, &value); err != nil {
		return "", err
	}
	if value == nil {
		return "", invalid(0, "text", "requires_string")
	}
	return *value, nil
}

func jsonNull(raw []byte) bool { return bytes.Equal(bytes.TrimSpace(raw), []byte("null")) }

func validateJSONRow(raw []byte, index int) (string, error) {
	allowed := map[string]bool{
		"external_task_id": true, "title": true, "description": true, "task_type": true, "task_size": true,
		"difficulty": true, "skill_tags": true, "estimated_time_minutes": true,
		"acceptance_criteria": true, "rejection_criteria": true,
	}
	fields, err := jsonObject(raw, allowed)
	if err != nil {
		return "", invalid(index, "row", "invalid_json_row")
	}
	var id string
	for _, field := range []struct {
		name     string
		maximum  int
		required bool
	}{
		{"external_task_id", 200, true}, {"title", 255, true}, {"description", 50000, true},
		{"task_type", 80, false}, {"difficulty", 80, false},
		{"acceptance_criteria", 50000, false}, {"rejection_criteria", 50000, false},
	} {
		raw, present := fields[field.name]
		if !present && !field.required {
			continue
		}
		value, err := jsonString(raw, !field.required)
		if err != nil || !validText(value, field.maximum, field.required) {
			return "", invalid(index, field.name, "invalid_field")
		}
		if field.name == "external_task_id" {
			if strings.TrimSpace(value) != value || strings.IndexFunc(value, unicode.IsControl) >= 0 {
				return "", invalid(index, field.name, "ambiguous_external_task_id")
			}
			id = value
		}
	}
	if raw, present := fields["task_size"]; present {
		size, err := jsonString(raw, false)
		if err != nil || (size != "small" && size != "medium" && size != "large") {
			return "", invalid(index, "task_size", "invalid_task_size")
		}
	}
	if raw, present := fields["skill_tags"]; present {
		var tags []*string
		if jsonv2.Unmarshal(raw, &tags) != nil || tags == nil || len(tags) > 100 {
			return "", invalid(index, "skill_tags", "invalid_skill_tags")
		}
		for _, tag := range tags {
			if tag == nil || !validText(*tag, 200, true) {
				return "", invalid(index, "skill_tags", "invalid_skill_tag")
			}
		}
	}
	if raw, present := fields["estimated_time_minutes"]; present && !jsonNull(raw) {
		raw = bytes.TrimSpace(raw)
		// Pydantic's strict integer excludes JSON decimal/exponent notation.
		for _, digit := range raw {
			if digit < '0' || digit > '9' {
				return "", invalid(index, "estimated_time_minutes", "invalid_minutes")
			}
		}
		minutes, err := strconv.Atoi(string(raw))
		if err != nil || minutes < 1 || minutes > 525600 {
			return "", invalid(index, "estimated_time_minutes", "invalid_minutes")
		}
	}
	return id, nil
}
