// Package taskimport converts local CSV briefs into the server's sole JSON
// import format. The returned commitment identifies JSON bytes, never CSV bytes.
package taskimport

import (
	"bytes"
	"crypto/sha256"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"
)

const MaxBytes = 8 * 1024 * 1024
const MaxRows = 500

// Conversion carries the exact upload bytes and their independently reportable
// commitment. Callers must write/upload Bytes without reserializing the document.
type Conversion struct {
	Bytes     []byte
	SHA256    string
	ByteCount int
	RowCount  int
}

type document struct {
	SchemaVersion string   `json:"schema_version"`
	Metadata      metadata `json:"metadata"`
	Tasks         []row    `json:"tasks"`
}

type metadata struct {
	Label *string `json:"label"`
}

type row struct {
	TaskSize             string   `json:"task_size"`
	ExternalTaskID       string   `json:"external_task_id"`
	Title                string   `json:"title"`
	Description          string   `json:"description"`
	TaskType             string   `json:"task_type,omitempty"`
	Difficulty           string   `json:"difficulty,omitempty"`
	SkillTags            []string `json:"skill_tags"`
	EstimatedTimeMinutes *int     `json:"estimated_time_minutes,omitempty"`
	AcceptanceCriteria   string   `json:"acceptance_criteria,omitempty"`
	RejectionCriteria    string   `json:"rejection_criteria,omitempty"`
}

// InputError identifies a bounded CSV row/field failure without echoing briefs.
// Row is the one-based task row, excluding the header; zero denotes the document.
type InputError struct {
	Row   int
	Field string
	Code  string
}

func (e *InputError) Error() string {
	if e.Row > 0 {
		return fmt.Sprintf("CSV task row %d: %s (%s)", e.Row, e.Code, e.Field)
	}
	return fmt.Sprintf("CSV input: %s (%s)", e.Code, e.Field)
}

func invalid(index int, field, code string) error {
	return &InputError{Row: index, Field: field, Code: code}
}

// ConvertCSV accepts quoted UTF-8 CSV with required external_task_id (or source_id),
// title and description headers. category aliases task_type; semicolon-separated
// skill_tags, languages and tools concatenate in that order, omitting blank
// segments. Aliases cannot coexist. No input text is otherwise trimmed/repaired.
func ConvertCSV(input io.Reader, label string) (Conversion, error) {
	body, err := io.ReadAll(io.LimitReader(input, MaxBytes+1))
	if err != nil {
		return Conversion{}, invalid(0, "document", "unreadable")
	}
	if len(body) == 0 || len(body) > MaxBytes {
		return Conversion{}, invalid(0, "document", "requires_1_to_8388608_bytes")
	}
	if !utf8.Valid(body) || bytes.IndexByte(body, 0) >= 0 {
		return Conversion{}, invalid(0, "document", "requires_utf8_without_nul")
	}
	if label != "" && !validText(label, 255, true) {
		return Conversion{}, invalid(0, "label", "invalid_label")
	}
	csvBody := bytes.TrimPrefix(body, []byte{0xef, 0xbb, 0xbf})
	reader := csv.NewReader(bytes.NewReader(csvBody))
	reader.FieldsPerRecord = -1
	lineOffsets := csvLineOffsets(csvBody)
	header, err := reader.Read()
	if err != nil {
		return Conversion{}, invalid(0, "header", "invalid_csv_header")
	}
	columns, err := headers(header)
	if err != nil {
		return Conversion{}, err
	}
	doc := document{SchemaVersion: "workstream.task_import.v1", Tasks: make([]row, 0)}
	if label != "" {
		doc.Metadata.Label = &label
	}
	seen := make(map[string]struct{})
	for index := 1; ; index++ {
		values, readErr := reader.Read()
		if readErr == io.EOF {
			break
		}
		if index > MaxRows {
			return Conversion{}, invalid(index, "tasks", "maximum_500_rows")
		}
		if readErr != nil || len(values) != len(header) {
			return Conversion{}, invalid(index, "row", "invalid_csv_row")
		}
		if !preserveQuotedFields(csvBody, lineOffsets, reader, values) {
			return Conversion{}, invalid(index, "row", "invalid_csv_row")
		}
		value, parseErr := parseRow(values, columns, index)
		if parseErr != nil {
			return Conversion{}, parseErr
		}
		if _, duplicate := seen[value.ExternalTaskID]; duplicate {
			return Conversion{}, invalid(index, "external_task_id", "duplicate_external_task_id")
		}
		seen[value.ExternalTaskID] = struct{}{}
		doc.Tasks = append(doc.Tasks, value)
	}
	if len(doc.Tasks) == 0 {
		return Conversion{}, invalid(0, "tasks", "requires_at_least_one_row")
	}
	encoded, err := json.Marshal(doc)
	if err != nil {
		return Conversion{}, invalid(0, "document", "cannot_encode_json")
	}
	encoded = append(encoded, '\n')
	if len(encoded) > MaxBytes {
		return Conversion{}, invalid(0, "document", "json_exceeds_8388608_bytes")
	}
	sum := sha256.Sum256(encoded)
	return Conversion{Bytes: encoded, SHA256: "sha256:" + hex.EncodeToString(sum[:]), ByteCount: len(encoded), RowCount: len(doc.Tasks)}, nil
}

func csvLineOffsets(body []byte) []int {
	starts := []int{0}
	for index, value := range body {
		if value == '\n' {
			starts = append(starts, index+1)
		}
	}
	return starts
}

// preserveQuotedFields restores accepted quoted values from their exact source
// spans. encoding/csv remains the syntax authority, but intentionally normalizes
// CRLF inside quoted fields to LF; task instructions must retain those bytes.
func preserveQuotedFields(body []byte, lineOffsets []int, reader *csv.Reader, values []string) bool {
	recordEnd := int(reader.InputOffset())
	for index := range values {
		line, column := reader.FieldPos(index)
		if line < 1 || line > len(lineOffsets) || column < 1 {
			return false
		}
		start := lineOffsets[line-1] + column - 1
		if start < 0 || start > recordEnd || start > len(body) {
			return false
		}
		// A final unquoted empty field may start exactly at EOF.
		if start == recordEnd || start == len(body) || body[start] != '"' {
			continue
		}
		value, ok := exactQuotedField(body[start:recordEnd], len(values[index]))
		if !ok {
			return false
		}
		values[index] = value
	}
	return true
}

func exactQuotedField(source []byte, normalizedLength int) (string, bool) {
	value := make([]byte, 0, normalizedLength)
	for index := 1; index < len(source); {
		if source[index] != '"' {
			value = append(value, source[index])
			index++
			continue
		}
		if index+1 < len(source) && source[index+1] == '"' {
			value = append(value, '"')
			index += 2
			continue
		}
		return string(value), true
	}
	return "", false
}

func headers(values []string) (map[string]int, error) {
	allowed := map[string]bool{
		"external_task_id": true, "source_id": true, "title": true, "description": true,
		"task_type": true, "category": true, "difficulty": true, "task_size": true, "skill_tags": true,
		"languages": true, "tools": true, "estimated_time_minutes": true,
		"acceptance_criteria": true, "rejection_criteria": true,
	}
	columns := make(map[string]int)
	for index, field := range values {
		if !allowed[field] {
			return nil, invalid(0, "header", "unknown_header")
		}
		if _, exists := columns[field]; exists {
			return nil, invalid(0, "header", "duplicate_header")
		}
		columns[field] = index
	}
	for alias, canonical := range map[string]string{"source_id": "external_task_id", "category": "task_type"} {
		if index, exists := columns[alias]; exists {
			if _, conflict := columns[canonical]; conflict {
				return nil, invalid(0, "header", "conflicting_alias_headers")
			}
			columns[canonical] = index
		}
	}
	for _, required := range []string{"external_task_id", "title", "description"} {
		if _, present := columns[required]; !present {
			return nil, invalid(0, required, "required_header_missing")
		}
	}
	return columns, nil
}

func validText(value string, maximum int, nonblank bool) bool {
	return utf8.ValidString(value) && !strings.ContainsRune(value, 0) && utf8.RuneCountInString(value) <= maximum && (!nonblank || strings.TrimSpace(value) != "")
}

func parseRow(values []string, columns map[string]int, index int) (row, error) {
	get := func(field string) string {
		if column, exists := columns[field]; exists {
			return values[column]
		}
		return ""
	}
	result := row{
		TaskSize:       "small",
		ExternalTaskID: get("external_task_id"), Title: get("title"), Description: get("description"),
		TaskType: get("task_type"), Difficulty: get("difficulty"), SkillTags: []string{},
		AcceptanceCriteria: get("acceptance_criteria"), RejectionCriteria: get("rejection_criteria"),
	}
	if size := strings.TrimSpace(get("task_size")); size != "" {
		if size != "small" && size != "medium" && size != "large" {
			return row{}, invalid(index, "task_size", "invalid_task_size")
		}
		result.TaskSize = size
	}
	for _, field := range []struct {
		name     string
		value    string
		maximum  int
		nonblank bool
	}{
		{"external_task_id", result.ExternalTaskID, 200, true}, {"title", result.Title, 255, true},
		{"description", result.Description, 50000, true}, {"task_type", result.TaskType, 80, false},
		{"difficulty", result.Difficulty, 80, false}, {"acceptance_criteria", result.AcceptanceCriteria, 50000, false},
		{"rejection_criteria", result.RejectionCriteria, 50000, false},
	} {
		if !validText(field.value, field.maximum, field.nonblank) {
			return row{}, invalid(index, field.name, "invalid_field")
		}
	}
	if strings.TrimSpace(result.ExternalTaskID) != result.ExternalTaskID || strings.IndexFunc(result.ExternalTaskID, unicode.IsControl) >= 0 {
		return row{}, invalid(index, "external_task_id", "ambiguous_external_task_id")
	}
	for _, field := range []string{"skill_tags", "languages", "tools"} {
		for _, part := range strings.Split(get(field), ";") {
			tag := strings.TrimSpace(part)
			if tag == "" {
				continue
			}
			if !validText(tag, 200, true) {
				return row{}, invalid(index, field, "invalid_skill_tag")
			}
			result.SkillTags = append(result.SkillTags, tag)
		}
	}
	if len(result.SkillTags) > 100 {
		return row{}, invalid(index, "skill_tags", "maximum_100_tags")
	}
	if text := get("estimated_time_minutes"); text != "" {
		minutes, err := strconv.Atoi(text)
		if err != nil || minutes < 1 || minutes > 525600 {
			return row{}, invalid(index, "estimated_time_minutes", "invalid_minutes")
		}
		result.EstimatedTimeMinutes = &minutes
	}
	return result, nil
}
