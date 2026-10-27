package api

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"mime"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strings"
)

// SubmissionPacket is shared unchanged between explicit preparation and creation.
// ART's current public header boundary requires ASCII; no client normalization.
type SubmissionPacket struct {
	Assignment  string  `json:"assignment_id"`
	Predecessor *string `json:"predecessor_submission_id,omitempty"`
	Summary     *string `json:"summary,omitempty"`
	Attestation *string `json:"contributor_attestation,omitempty"`
}

// RevisionAcknowledgement is preparation-only; it is not part of Submission JSON.
type RevisionAcknowledgement struct {
	PreparationID     string
	PreparationSHA256 string
}

var revisionPreparationDigest = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

type PreparationReceipt struct {
	PutAttemptID string            `json:"put_attempt_id"`
	AdmissionID  *string           `json:"admission_id"`
	Status       string            `json:"submission_bundle_preparation_status"`
	Replayed     bool              `json:"replayed"`
	Feedback     []json.RawMessage `json:"pre_submission_results,omitempty"`
}

type SubmissionReceipt struct {
	SubmissionID        string   `json:"submission_id"`
	Version             *big.Int `json:"submission_version"`
	AdmissionID         string   `json:"admission_id"`
	EvaluationRequestID string   `json:"evaluation_request_id"`
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
				return errors.New("packet text must be printable ASCII for the public preparation API")
			}
		}
	}
	return nil
}

func submissionFailure(err error, preparation bool) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "Submission outcome unknown; inspect task submissions; replay only the same task, assignment, admission and packet"
		if preparation {
			failure.RecoveryHint = "preparation outcome unknown; explicitly replay only the same task, assignment, ZIP bytes, packet, revision acknowledgement and idempotency key; no Submission was requested by this command"
		}
	}
	return err
}

// PrepareSubmission streams one regular ZIP once. A receipt is not a Submission.
func (c *Client) PrepareSubmission(ctx context.Context, task, key string, packet SubmissionPacket, acknowledgement *RevisionAcknowledgement, source *os.File, expectedSHA256 string) (Result[PreparationReceipt], error) {
	var result Result[PreparationReceipt]
	if err := packet.validate(task); err != nil {
		return result, err
	}
	if !submissionSelector(key) || source == nil {
		return result, errors.New("preparation requires a caller UUID key and a regular ZIP file")
	}
	if packet.Predecessor == nil {
		if acknowledgement != nil {
			return result, errors.New("initial preparation cannot acknowledge a revision")
		}
	} else if acknowledgement == nil || !submissionSelector(acknowledgement.PreparationID) ||
		!revisionPreparationDigest.MatchString(acknowledgement.PreparationSHA256) {
		return result, errors.New("revision preparation requires its exact preparation ID and sha256 digest")
	}
	initial, err := source.Stat()
	if err != nil || !initial.Mode().IsRegular() || initial.Size() <= 0 || initial.Size() > MaxGuideDocumentBytes {
		return result, errors.New("ZIP must be a nonempty regular file of at most 512MiB")
	}
	expected, err := uploadSourceHash(source, initial.Size())
	if err != nil {
		return result, err
	}
	// A reviewed fingerprint is checked against this operation's own pre-send
	// hash, not an earlier independent read. Empty preserves explicit CLI input.
	if expectedSHA256 != "" && expected != expectedSHA256 {
		return result, errors.New("reviewed ZIP changed; no preparation request was sent")
	}
	if err := ctx.Err(); err != nil {
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
		"/api/v1/tasks/"+url.PathEscape(task)+"/submission-bundle-preparations", "",
		io.NewSectionReader(source, 0, initial.Size()), initial.Size(), key, "application/json", "application/zip", headers)
	if err != nil {
		return result, submissionFailure(err, true)
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(response.Body, maxSubmissionReadBytes+1))
	invalid := &Failure{Code: "invalid_api_response", Status: response.StatusCode, OutcomeUnknown: true}
	if err != nil || len(raw) > maxSubmissionReadBytes {
		return result, submissionFailure(invalid, true)
	}
	if response.StatusCode != http.StatusAccepted {
		failure := c.responseFailure(http.MethodPost, response, raw)
		if response.StatusCode == 422 {
			var typed *Failure
			if errors.As(failure, &typed) && typed.Code == "pre_submission_checker_failed" {
				if typed.OutcomeUnknown || !c.safeMutationResponse(raw) {
					return result, submissionFailure(invalid, true)
				}
				details, err := preparationFeedback(raw)
				if err != nil {
					return result, submissionFailure(invalid, true)
				}
				typed.Details = details
			}
		}
		return result, submissionFailure(failure, true)
	}
	kind, _, typeErr := mime.ParseMediaType(response.Header.Get("Content-Type"))
	var value PreparationReceipt
	fields, decodeErr := contextObject(raw, &value, []string{"put_attempt_id", "submission_bundle_preparation_status", "replayed", "pre_submission_results"}, nil)
	if typeErr != nil || kind != "application/json" || decodeErr != nil || !requiredNullable(fields, "admission_id") ||
		!validUUID(value.PutAttemptID) || !c.safeMutationResponse(raw) ||
		value.Feedback == nil || !validPreSubmissionResults(value.Feedback, true) ||
		(response.Header.Get("Content-Encoding") != "" && response.Header.Get("Content-Encoding") != "identity") {
		return result, submissionFailure(invalid, true)
	}
	switch value.Status {
	case "ready":
		if value.AdmissionID == nil || !validUUID(*value.AdmissionID) {
			return result, submissionFailure(invalid, true)
		}
	case "prepared", "put_in_flight", "object_confirmed", "stored_pending_verification", "observed_confirmed",
		"acknowledgement_unknown", "provider_unavailable", "conflict", "integrity_mismatch", "missing", "absent_replay_required", "stale":
		if value.AdmissionID != nil {
			return result, submissionFailure(invalid, true)
		}
	default:
		return result, submissionFailure(invalid, true)
	}
	finalHash, hashErr := uploadSourceHash(source, initial.Size())
	final, statErr := source.Stat()
	if hashErr != nil || statErr != nil || final.Size() != initial.Size() || !final.ModTime().Equal(initial.ModTime()) || finalHash != expected {
		return result, submissionFailure(&Failure{Code: "submission_source_changed", OutcomeUnknown: true}, true)
	}
	return Result[PreparationReceipt]{Raw: raw, Value: value}, nil
}

func (c *Client) CreateSubmission(ctx context.Context, task, admission string, packet SubmissionPacket) (Result[SubmissionReceipt], error) {
	var result Result[SubmissionReceipt]
	if err := packet.validate(task); err != nil {
		return result, err
	}
	if !submissionSelector(admission) {
		return result, errors.New("admission must be a UUID")
	}
	body, err := json.Marshal(struct {
		SubmissionPacket
		Admission string `json:"admission_id"`
	}{packet, admission})
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithKey(ctx, http.MethodPost, "/api/v1/tasks/"+url.PathEscape(task)+"/submissions", "", body, "", http.StatusCreated)
	if err != nil {
		return result, submissionFailure(err, false)
	}
	var value SubmissionReceipt
	_, err = contextObject(raw, &value, []string{"submission_id", "submission_version", "admission_id", "evaluation_request_id"}, nil)
	if err != nil || !validUUID(value.SubmissionID) || value.Version == nil || value.Version.Sign() <= 0 ||
		!sameUUID(value.AdmissionID, admission) || !validUUID(value.EvaluationRequestID) || !c.safeMutationResponse(raw) {
		return result, submissionFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true}, false)
	}
	return Result[SubmissionReceipt]{Raw: raw, Value: value}, nil
}
