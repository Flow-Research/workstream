package api

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

// MaxSubmissionZipBytes bounds the compressed submission ZIP, independently of guide uploads.
// Project limits may enforce a smaller allowance.
const MaxSubmissionZipBytes = 500 * 1024 * 1024

// SubmissionInput carries the contributor's exact assignment and optional project feedback.
type SubmissionInput struct {
	Assignment string
	Feedback   *string
}

const MaxSubmissionFeedbackBytes = 4096

type SubmissionReceipt struct {
	OperationID     string            `json:"operation_id"`
	TaskID          string            `json:"task_id"`
	AssignmentID    string            `json:"assignment_id"`
	Status          string            `json:"status"`
	AcceptedAt      string            `json:"accepted_at"`
	TaskStatus      string            `json:"task_status_at_acceptance"`
	ProcessingStage string            `json:"processing_stage_at_acceptance"`
	Replayed        bool              `json:"replayed"`
	Feedback        []json.RawMessage `json:"pre_submission_results,omitempty"`
}

func submissionSelector(value string) bool { return len(value) <= 100 && validUUID(value) }

func (p SubmissionInput) validate(task string) error {
	if !submissionSelector(task) || !submissionSelector(p.Assignment) {
		return errors.New("task and assignment must be UUIDs")
	}
	if p.Feedback == nil {
		return nil
	}
	text := *p.Feedback
	if len(text) > MaxSubmissionFeedbackBytes || strings.TrimSpace(text) != text {
		return errors.New("feedback accepts at most 4096 bytes without leading or trailing whitespace")
	}
	for _, value := range []byte(text) {
		if value < 32 || value > 126 {
			return errors.New("feedback must be printable ASCII")
		}
	}
	return nil
}

func submissionFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "Observe the submission operation using the same actor and idempotency key, or explicitly replay the same task, assignment, ZIP bytes and feedback; do not create a new key while the outcome is unknown"
	}
	return err
}

// SubmitSubmission streams one regular ZIP once and returns its committed acceptance snapshot.
func (c *Client) SubmitSubmission(ctx context.Context, task, key string, input SubmissionInput, source *os.File) (Result[SubmissionReceipt], error) {
	var result Result[SubmissionReceipt]
	if err := input.validate(task); err != nil {
		return result, err
	}
	if !submissionSelector(key) || source == nil {
		return result, errors.New("submission requires a caller UUID key and a regular ZIP file")
	}
	initial, err := source.Stat()
	if err != nil || !initial.Mode().IsRegular() || initial.Size() <= 0 || initial.Size() > MaxSubmissionZipBytes {
		return result, errors.New("ZIP must be a nonempty regular file of at most 500MiB")
	}
	expected, err := uploadSourceHash(source, initial.Size())
	if err != nil {
		return result, err
	}
	headers := http.Header{"X-Task-Assignment-Id": {input.Assignment}}
	if input.Feedback != nil {
		headers.Set("X-Submission-Feedback", *input.Feedback)
	}
	response, err := c.openBodyRequest(ctx, c.guideHTTP, http.MethodPost,
		"/api/v1/tasks/"+url.PathEscape(task)+"/submissions", "",
		io.NewSectionReader(source, 0, initial.Size()), initial.Size(), key, "application/json", "application/zip", headers)
	if err != nil {
		return result, submissionFailure(err)
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(response.Body, maxSubmissionReadBytes+1))
	invalid := &Failure{Code: "invalid_api_response", Status: response.StatusCode, OutcomeUnknown: true}
	if err != nil || len(raw) > maxSubmissionReadBytes {
		return result, submissionFailure(invalid)
	}
	if response.StatusCode != http.StatusAccepted {
		failure := c.responseFailure(http.MethodPost, response, raw)
		if response.StatusCode == 422 {
			var typed *Failure
			if errors.As(failure, &typed) && typed.Code == "pre_submission_checker_failed" {
				if typed.OutcomeUnknown || !c.safeMutationResponse(raw) {
					return result, submissionFailure(invalid)
				}
				details, err := preparationFeedback(raw)
				if err != nil {
					return result, submissionFailure(invalid)
				}
				typed.Details = details
			}
		}
		return result, submissionFailure(failure)
	}
	kind, _, typeErr := mime.ParseMediaType(response.Header.Get("Content-Type"))
	var value SubmissionReceipt
	_, decodeErr := contextObject(raw, &value, []string{"operation_id", "task_id", "assignment_id", "status", "accepted_at", "task_status_at_acceptance", "processing_stage_at_acceptance", "replayed", "pre_submission_results"}, nil)
	_, acceptedErr := time.Parse(time.RFC3339Nano, value.AcceptedAt)
	if typeErr != nil || kind != "application/json" || decodeErr != nil || acceptedErr != nil ||
		!validUUID(value.OperationID) || !sameUUID(value.TaskID, task) || !sameUUID(value.AssignmentID, input.Assignment) ||
		value.Status != "accepted" || value.TaskStatus != "evaluation_pending" || value.ProcessingStage != "finalization_pending" ||
		!c.safeMutationResponse(raw) || value.Feedback == nil || !validPreSubmissionResults(value.Feedback, true) ||
		(response.Header.Get("Content-Encoding") != "" && response.Header.Get("Content-Encoding") != "identity") {
		return result, submissionFailure(invalid)
	}
	finalHash, hashErr := uploadSourceHash(source, initial.Size())
	final, statErr := source.Stat()
	if hashErr != nil || statErr != nil || final.Size() != initial.Size() || !final.ModTime().Equal(initial.ModTime()) || finalHash != expected {
		return result, submissionFailure(&Failure{Code: "submission_source_changed", OutcomeUnknown: true})
	}
	return Result[SubmissionReceipt]{Raw: raw, Value: value}, nil
}
