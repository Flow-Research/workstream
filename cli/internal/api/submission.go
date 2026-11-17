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
	"regexp"
	"strings"
	"time"
)

// MaxSubmissionZipBytes bounds the compressed submission ZIP, independently of guide uploads.
// Project limits may enforce a smaller allowance.
const MaxSubmissionZipBytes = 500 * 1024 * 1024

// SubmissionPacket is the exact metadata for one source submission.
// ART's current public header boundary requires ASCII; no client normalization.
type SubmissionPacket struct {
	Assignment  string  `json:"assignment_id"`
	Predecessor *string `json:"predecessor_submission_id,omitempty"`
	Summary     *string `json:"summary,omitempty"`
	Attestation *string `json:"contributor_attestation,omitempty"`
}

// RevisionAcknowledgement binds the current governed revision context.
type RevisionAcknowledgement struct {
	PreparationID     string
	PreparationSHA256 string
}

var revisionPreparationDigest = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

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

func (p SubmissionPacket) validate(task string) error {
	if !submissionSelector(task) || !submissionSelector(p.Assignment) ||
		(p.Predecessor != nil && !submissionSelector(*p.Predecessor)) {
		return errors.New("task, assignment and predecessor must be UUIDs")
	}
	for _, text := range []*string{p.Summary, p.Attestation} {
		if text == nil {
			continue
		}
		if len(*text) > 64*1024 || strings.TrimSpace(*text) != *text {
			return errors.New("packet text must fit 64KiB without header-edge whitespace")
		}
		for _, value := range []byte(*text) {
			if value < 32 || value > 126 {
				return errors.New("packet text must be printable ASCII for the public submission API")
			}
		}
	}
	return nil
}

func submissionFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "Observe the submission operation using the same actor and idempotency key, or explicitly replay the same task, assignment, ZIP bytes, packet and revision acknowledgement; do not create a new key while the outcome is unknown"
	}
	return err
}

// SubmitSubmission streams one regular ZIP once and returns its committed acceptance snapshot.
func (c *Client) SubmitSubmission(ctx context.Context, task, key string, packet SubmissionPacket, acknowledgement *RevisionAcknowledgement, source *os.File) (Result[SubmissionReceipt], error) {
	var result Result[SubmissionReceipt]
	if err := packet.validate(task); err != nil {
		return result, err
	}
	if !submissionSelector(key) || source == nil {
		return result, errors.New("submission requires a caller UUID key and a regular ZIP file")
	}
	if packet.Predecessor == nil {
		if acknowledgement != nil {
			return result, errors.New("initial submission cannot acknowledge a revision")
		}
	} else if acknowledgement == nil || !submissionSelector(acknowledgement.PreparationID) ||
		!revisionPreparationDigest.MatchString(acknowledgement.PreparationSHA256) {
		return result, errors.New("revision preparation requires its exact preparation ID and sha256 digest")
	}
	initial, err := source.Stat()
	if err != nil || !initial.Mode().IsRegular() || initial.Size() <= 0 || initial.Size() > MaxSubmissionZipBytes {
		return result, errors.New("ZIP must be a nonempty regular file of at most 500MiB")
	}
	expected, err := uploadSourceHash(source, initial.Size())
	if err != nil {
		return result, err
	}
	headers := http.Header{"X-Task-Assignment-Id": {packet.Assignment}}
	for name, value := range map[string]*string{
		"X-Submission-Summary": packet.Summary, "X-Contributor-Attestation": packet.Attestation,
		"X-Predecessor-Submission-Id": packet.Predecessor,
	} {
		if value != nil {
			headers.Set(name, *value)
		}
	}
	if acknowledgement != nil {
		headers.Set("X-Revision-Preparation-Id", acknowledgement.PreparationID)
		headers.Set("X-Revision-Preparation-Sha256", acknowledgement.PreparationSHA256)
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
		!validUUID(value.OperationID) || !sameUUID(value.TaskID, task) || !sameUUID(value.AssignmentID, packet.Assignment) ||
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
