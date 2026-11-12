package taskimport

import (
	"crypto/sha256"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"testing"
)

func TestQuotedUnicodeCSVCommitment(t *testing.T) {
	input := "\ufeffsource_id,title,description,category,skill_tags,languages,tools,estimated_time_minutes,acceptance_criteria\r\n" +
		"brief-É,\"Caption, français\",\"First line\r\nSecond line: 日本語\",caption,\" review ; ;accuracy\",fr;ja,editor,30,Usable caption\r\n"
	result, err := ConvertCSV(strings.NewReader(input), "Multilingual briefs")
	if err != nil {
		t.Fatal(err)
	}
	var value document
	if err := json.Unmarshal(result.Bytes, &value); err != nil {
		t.Fatal(err)
	}
	if value.SchemaVersion != "workstream.task_import.v1" || value.Metadata.Label == nil || *value.Metadata.Label != "Multilingual briefs" || len(value.Tasks) != 1 {
		t.Fatalf("unexpected document metadata: %#v", value)
	}
	task := value.Tasks[0]
	if task.ExternalTaskID != "brief-É" || task.Title != "Caption, français" || task.Description != "First line\r\nSecond line: 日本語" || task.TaskType != "caption" || strings.Join(task.SkillTags, ";") != "review;accuracy;fr;ja;editor" || task.EstimatedTimeMinutes == nil || *task.EstimatedTimeMinutes != 30 {
		t.Fatalf("CSV instructions were mapped incorrectly: %#v", task)
	}
	sum := sha256.Sum256(result.Bytes)
	if result.SHA256 != "sha256:"+hex.EncodeToString(sum[:]) || result.ByteCount != len(result.Bytes) || result.RowCount != 1 || result.Bytes[len(result.Bytes)-1] != '\n' {
		t.Fatal("commitment does not identify the complete written JSON bytes")
	}
	again, err := ConvertCSV(strings.NewReader(input), "Multilingual briefs")
	if err != nil || string(again.Bytes) != string(result.Bytes) {
		t.Fatal("unchanged conversion did not produce identical bytes")
	}
}

func TestQuotedFieldNewlinesArePreservedExactly(t *testing.T) {
	input := "external_task_id,title,description\r\n" +
		"one,\"Title, \"\"quoted\"\"\",\"First\r\nSecond 日本語\"\r\n" +
		"\r\n" +
		"two,T,\"Alpha\nBeta\"\n" +
		"three,T,\"Carriage\r\nand LF\nend\""
	result, err := ConvertCSV(strings.NewReader(input), "")
	if err != nil {
		t.Fatal(err)
	}
	var value document
	if err := json.Unmarshal(result.Bytes, &value); err != nil {
		t.Fatal(err)
	}
	if result.RowCount != 3 || len(value.Tasks) != 3 {
		t.Fatalf("blank physical lines must not create tasks: %#v", value.Tasks)
	}
	if value.Tasks[0].Title != "Title, \"quoted\"" || value.Tasks[0].Description != "First\r\nSecond 日本語" {
		t.Fatalf("escaped punctuation or CRLF changed: %#v", value.Tasks[0])
	}
	if value.Tasks[1].Description != "Alpha\nBeta" {
		t.Fatalf("LF changed: %#v", value.Tasks[1])
	}
	if value.Tasks[2].Description != "Carriage\r\nand LF\nend" {
		t.Fatalf("mixed newlines or final record changed: %#v", value.Tasks[2])
	}
}

func TestCSVRefusalsProduceNoOutput(t *testing.T) {
	for _, test := range []struct {
		name, input, code string
		row               int
	}{
		{"duplicate header", "external_task_id,title,title,description\na,T,T,D\n", "duplicate_header", 0},
		{"unknown header", "external_task_id,title,description,created_by\na,T,D,actor\n", "unknown_header", 0},
		{"missing id header", "title,description\nT,D\n", "required_header_missing", 0},
		{"crossed id aliases", "external_task_id,source_id,title,description\na,b,T,D\n", "conflicting_alias_headers", 0},
		{"crossed category aliases", "external_task_id,title,description,task_type,category\na,T,D,A,B\n", "conflicting_alias_headers", 0},
		{"no rows", "external_task_id,title,description\n", "requires_at_least_one_row", 0},
		{"bad quote", "external_task_id,title,description\na,\"unterminated,D\n", "invalid_csv_row", 1},
		{"wrong columns", "external_task_id,title,description\na,T,D,extra\n", "invalid_csv_row", 1},
		{"duplicate id", "external_task_id,title,description\na,T,D\na,T2,D2\n", "duplicate_external_task_id", 2},
		{"blank instructions", "external_task_id,title,description\na,  ,D\n", "invalid_field", 1},
		{"padded id", "external_task_id,title,description\n a,T,D\n", "ambiguous_external_task_id", 1},
		{"control id", "external_task_id,title,description\na\t,T,D\n", "ambiguous_external_task_id", 1},
		{"nul", "external_task_id,title,description\na,T,D\x00\n", "requires_utf8_without_nul", 0},
		{"invalid utf8", "external_task_id,title,description\na,T,D\xff\n", "requires_utf8_without_nul", 0},
		{"bad minutes", "external_task_id,title,description,estimated_time_minutes\na,T,D,0\n", "invalid_minutes", 1},
		{"oversized title", "external_task_id,title,description\na," + strings.Repeat("é", 256) + ",D\n", "invalid_field", 1},
		{"too many tags", "external_task_id,title,description,skill_tags\na,T,D," + strings.Repeat("tag;", 101) + "\n", "maximum_100_tags", 1},
	} {
		t.Run(test.name, func(t *testing.T) {
			result, err := ConvertCSV(strings.NewReader(test.input), "")
			var refusal *InputError
			if !errors.As(err, &refusal) || refusal.Code != test.code || refusal.Row != test.row || len(result.Bytes) != 0 {
				t.Fatalf("expected bounded refusal %s at row %d with zero output; got %#v, %v", test.code, test.row, result, err)
			}
		})
	}
}

func TestRowAndByteBoundaries(t *testing.T) {
	var input strings.Builder
	input.WriteString("external_task_id,title,description\n")
	for index := 0; index < MaxRows; index++ {
		fmt.Fprintf(&input, "task-%d,T,D\n", index)
	}
	result, err := ConvertCSV(strings.NewReader(input.String()), "")
	if err != nil || result.RowCount != MaxRows {
		t.Fatalf("500 rows should be admitted: %v", err)
	}
	input.WriteString("task-501,T,D\n")
	_, err = ConvertCSV(strings.NewReader(input.String()), "")
	var refusal *InputError
	if !errors.As(err, &refusal) || refusal.Code != "maximum_500_rows" || refusal.Row != 501 {
		t.Fatalf("501 rows should be refused: %v", err)
	}
	_, err = ConvertCSV(strings.NewReader(strings.Repeat("x", MaxBytes+1)), "")
	if !errors.As(err, &refusal) || refusal.Code != "requires_1_to_8388608_bytes" {
		t.Fatalf("oversized CSV should be refused before parsing: %v", err)
	}
	// JSON escapes these otherwise valid CSV instructions. Enforce the output
	// bound too; input within 8MiB must not produce an unuploadable document.
	var expanded strings.Builder
	writer := csv.NewWriter(&expanded)
	writer.Write([]string{"external_task_id", "title", "description"})
	for index := 0; index < 40; index++ {
		writer.Write([]string{fmt.Sprint(index), "T", strings.Repeat("\x01", 40000)})
	}
	writer.Flush()
	_, err = ConvertCSV(strings.NewReader(expanded.String()), "")
	if !errors.As(err, &refusal) || refusal.Code != "json_exceeds_8388608_bytes" {
		t.Fatalf("oversized converted JSON should be refused: %v", err)
	}
}

func TestExternalIDsAreCaseSensitive(t *testing.T) {
	result, err := ConvertCSV(strings.NewReader("external_task_id,title,description\na,T,D\nA,T,D\n"), "")
	if err != nil || result.RowCount != 2 {
		t.Fatalf("distinct case-sensitive IDs should survive: %v", err)
	}
}

func TestTaskSizeCSVAndJSONContract(t *testing.T) {
	for _, value := range []string{"", " small ", "medium", "large"} {
		converted, err := ConvertCSV(strings.NewReader("external_task_id,title,description,task_size\na,T,D,"+value+"\n"), "")
		if err != nil {
			t.Fatal(err)
		}
		var document document
		if err := json.Unmarshal(converted.Bytes, &document); err != nil {
			t.Fatal(err)
		}
		want := strings.TrimSpace(value)
		if want == "" {
			want = "small"
		}
		if document.Tasks[0].TaskSize != want {
			t.Fatalf("size: got %q, want %q", document.Tasks[0].TaskSize, want)
		}
	}
	omitted, err := ConvertCSV(strings.NewReader("external_task_id,title,description\na,T,D\n"), "")
	if err != nil || !strings.Contains(string(omitted.Bytes), `"task_size":"small"`) {
		t.Fatalf("omitted size default: %s %v", omitted.Bytes, err)
	}
	for _, invalid := range []string{"null", "Small", "giant"} {
		if _, err := ConvertCSV(strings.NewReader("external_task_id,title,description,task_size\na,T,D,"+invalid+"\n"), ""); err == nil {
			t.Fatalf("accepted CSV size %q", invalid)
		}
	}
	for _, field := range []string{``, `,"task_size":"small"`, `,"task_size":"medium"`, `,"task_size":"large"`} {
		raw := []byte(`{"schema_version":"workstream.task_import.v1","tasks":[{"external_task_id":"a","title":"T","description":"D"` + field + `}]}`)
		if _, err := ValidateJSON(raw); err != nil {
			t.Fatalf("valid JSON size %s: %v", field, err)
		}
	}
	for _, field := range []string{`"task_size":null`, `"task_size":"Small"`, `"task_size":"giant"`, `"quantity":"5"`, `"instrument_type":"money"`, `"unit_code":"USD"`} {
		raw := []byte(`{"schema_version":"workstream.task_import.v1","tasks":[{"external_task_id":"a","title":"T","description":"D",` + field + `}]}`)
		if _, err := ValidateJSON(raw); err == nil {
			t.Fatalf("accepted JSON field %s", field)
		}
	}
}
