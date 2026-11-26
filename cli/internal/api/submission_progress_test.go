package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func progressJSON() map[string]any {
	return map[string]any{"operation_id": testRun, "task_id": testTask, "assignment_id": testFinding,
		"idempotency_key": testSubmission, "operation_state": "finalization_pending", "processing_stage": "finalization_pending",
		"accepted_at": "2026-11-16T12:00:00Z", "task_status_at_acceptance": "evaluation_pending", "current_task_status": nil,
		"submission_id": nil, "submission_version": nil, "evaluation_request_id": nil, "pre_submission_results": []any{},
		"failure_code": nil, "operationally_stalled": false, "post_submission_progress": nil, "next_action": "wait"}
}

func TestSubmissionProgressSelectorsAndNoMutation(t *testing.T) {
	requests := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests++
		if r.Method != "GET" || r.URL.Path != "/api/v1/tasks/"+testTask+"/submission-operations" || r.Header.Get("Idempotency-Key") != "" {
			t.Error("unexpected mutation or route", r)
		}
		if len(r.URL.Query()) != 1 || (r.URL.Query().Get("operation_id") != testRun && r.URL.Query().Get("idempotency_key") != testSubmission) {
			t.Error("selector lost", r.URL)
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(progressJSON())
	}))
	defer server.Close()
	client, err := New(server.URL, "fixture-token")
	if err != nil {
		t.Fatal(err)
	}
	for _, selectors := range [][2]string{{testRun, ""}, {"", testSubmission}} {
		got, err := client.SubmissionOperation(context.Background(), testTask, selectors[0], selectors[1])
		if err != nil || got.Value.Stage != "finalization_pending" || got.Value.SubmissionID != nil {
			t.Fatal(got, err)
		}
	}
	for _, selectors := range [][2]string{{"", ""}, {testRun, testSubmission}, {"invalid", ""}} {
		if _, err := client.SubmissionOperation(context.Background(), testTask, selectors[0], selectors[1]); err == nil {
			t.Fatal("invalid selectors accepted")
		}
	}
	if requests != 2 {
		t.Fatal("unexpected HTTP requests", requests)
	}
}

func TestSubmissionProgressRefusesUnboundOrMalformedEvidence(t *testing.T) {
	for _, field := range []string{"task_id", "operation_id", "idempotency_key", "assignment_id", "processing_stage", "next_action", "provider_key", "submission_version", "pre_submission_results", "current_task_status"} {
		t.Run(field, func(t *testing.T) {
			value := progressJSON()
			value[field] = "invalid"
			raw, _ := json.Marshal(value)
			if _, err := decodeSubmissionProgress(raw, testTask, testRun, testSubmission); err == nil {
				t.Fatal("accepted invalid field", field)
			}
		})
	}
	for _, field := range []string{"accepted_at", "submission_id", "submission_version", "evaluation_request_id", "current_task_status", "failure_code", "task_status_at_acceptance"} {
		value := progressJSON()
		delete(value, field)
		raw, _ := json.Marshal(value)
		if _, err := decodeSubmissionProgress(raw, testTask, testRun, ""); err == nil {
			t.Fatal("missing nullable accepted", field)
		}
	}
	for _, stage := range []string{"evaluation_pending", "evaluation_running", "review_pending", "needs_revision", "accepted", "rejected", "operationally_stalled"} {
		value := progressJSON()
		value["operation_state"] = "finalized"
		value["processing_stage"] = stage
		value["submission_id"] = testFinding
		value["submission_version"] = 2
		value["evaluation_request_id"] = testSubmission
		value["operationally_stalled"] = stage == "operationally_stalled"
		action := "inspect_governed_outcome"
		if stage == "operationally_stalled" {
			action = "contact_operator"
			value["failure_code"] = "post_submission_outcome_unknown"
		}
		value["next_action"] = action
		raw, _ := json.Marshal(value)
		got, err := decodeSubmissionProgress(raw, testTask, testRun, "")
		if err != nil || got.Stage != stage || got.NextAction != action {
			t.Fatal(stage, err)
		}
	}
}
