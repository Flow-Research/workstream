package api

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
)

type preparationTransport func(*http.Request) (*http.Response, error)

func (f preparationTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

const preparationAcceptedJSON = `{"put_attempt_id":"10000000-0000-7000-8000-000000000001","admission_id":null,"submission_bundle_preparation_status":"stored_pending_verification","replayed":false,"pre_submission_results":[]}`

func TestPreparationReviewedHashIsCheckedBeforePOST(t *testing.T) {
	var posts atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		posts.Add(1)
		if _, err := io.Copy(io.Discard, r.Body); err != nil {
			t.Error(err)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_, _ = fmt.Fprint(w, preparationAcceptedJSON)
	}))
	defer server.Close()
	c := &Client{origin: server.URL, token: "test-token", guideHTTP: server.Client()}
	path := filepath.Join(t.TempDir(), "bundle.zip")
	// The expected fingerprint belongs to earlier reviewed bytes. Removing the
	// shared-operation guard would send these changed bytes and validate 202.
	if err := os.WriteFile(path, []byte("changed bytes"), 0600); err != nil {
		t.Fatal(err)
	}
	f, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	packet := SubmissionPacket{Assignment: "20000000-0000-7000-8000-000000000001"}
	expected := fmt.Sprintf("sha256:%x", sha256.Sum256([]byte("reviewed bytes")))
	_, err = c.PrepareSubmission(context.Background(), "30000000-0000-7000-8000-000000000001", "40000000-0000-7000-8000-000000000001", packet, nil, f, expected)
	if err == nil || !strings.Contains(err.Error(), "reviewed ZIP changed") || posts.Load() != 0 {
		t.Fatal("reviewed bytes did not guard the shared POST", err, posts.Load())
	}
	// Empty is intentional for explicit CLI callers; their behavior is retained.
	_, err = c.PrepareSubmission(context.Background(), "30000000-0000-7000-8000-000000000001", "40000000-0000-7000-8000-000000000001", packet, nil, f, "")
	if err != nil || posts.Load() != 1 {
		t.Fatal("explicit CLI behavior changed", err, posts.Load())
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err = c.PrepareSubmission(ctx, "30000000-0000-7000-8000-000000000001", "40000000-0000-7000-8000-000000000001", packet, nil, f, "")
	if err != context.Canceled || posts.Load() != 1 {
		t.Fatal("cancelled operation sent", err, posts.Load())
	}
}

func TestPreparationRejectsTransientStreamMutationRestoredBeforeFinalHash(t *testing.T) {
	for _, reviewed := range []bool{false, true} {
		t.Run(fmt.Sprintf("reviewed=%t", reviewed), func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "bundle.zip")
			original, changed := []byte("reviewed original"), []byte("unreviewed bytes!")
			if len(original) != len(changed) {
				t.Fatal("regression requires same-size bytes")
			}
			if err := os.WriteFile(path, original, 0600); err != nil {
				t.Fatal(err)
			}
			source, err := os.Open(path)
			if err != nil {
				t.Fatal(err)
			}
			defer source.Close()
			before, err := source.Stat()
			if err != nil {
				t.Fatal(err)
			}
			var consumed []byte
			calls := 0
			transport := preparationTransport(func(r *http.Request) (*http.Response, error) {
				calls++
				if err := os.WriteFile(path, changed, 0600); err != nil {
					t.Fatal(err)
				}
				consumed, err = io.ReadAll(r.Body)
				if err != nil {
					t.Fatal(err)
				}
				_ = r.Body.Close()
				if err := os.WriteFile(path, original, 0600); err != nil {
					t.Fatal(err)
				}
				if err := os.Chtimes(path, before.ModTime(), before.ModTime()); err != nil {
					t.Fatal(err)
				}
				return &http.Response{StatusCode: 202, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(strings.NewReader(preparationAcceptedJSON))}, nil
			})
			c := &Client{origin: "https://example.test", token: "test-token", guideHTTP: &http.Client{Transport: transport}}
			expected := ""
			if reviewed {
				expected = fmt.Sprintf("sha256:%x", sha256.Sum256(original))
			}
			result, err := c.PrepareSubmission(context.Background(), "30000000-0000-7000-8000-000000000001", "40000000-0000-7000-8000-000000000001", SubmissionPacket{Assignment: "20000000-0000-7000-8000-000000000001"}, nil, source, expected)
			var failure *Failure
			if calls != 1 || string(consumed) != string(changed) || !errors.As(err, &failure) || !failure.OutcomeUnknown || failure.Code != "submission_source_changed" || result.Value.PutAttemptID != "" {
				t.Fatal("transient unreviewed stream was confirmed", calls, string(consumed), result, err)
			}
		})
	}
}

func TestPreparationAcceptedReceiptRequiresCompleteConsumedBody(t *testing.T) {
	for _, mode := range []string{"none", "partial", "complete"} {
		t.Run(mode, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "bundle.zip")
			if err := os.WriteFile(path, []byte("reviewed ZIP bytes"), 0600); err != nil {
				t.Fatal(err)
			}
			source, err := os.Open(path)
			if err != nil {
				t.Fatal(err)
			}
			defer source.Close()
			transport := preparationTransport(func(r *http.Request) (*http.Response, error) {
				if mode == "complete" {
					_, _ = io.Copy(io.Discard, r.Body)
				}
				if mode == "partial" {
					_, _ = io.ReadFull(r.Body, make([]byte, 1))
				}
				_ = r.Body.Close()
				return &http.Response{StatusCode: 202, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(strings.NewReader(preparationAcceptedJSON))}, nil
			})
			c := &Client{origin: "https://example.test", token: "test-token", guideHTTP: &http.Client{Transport: transport}}
			result, err := c.PrepareSubmission(context.Background(), "30000000-0000-7000-8000-000000000001", "40000000-0000-7000-8000-000000000001", SubmissionPacket{Assignment: "20000000-0000-7000-8000-000000000001"}, nil, source, "")
			if mode == "complete" {
				if err != nil || result.Value.Status != "stored_pending_verification" {
					t.Fatal("complete matching stream refused", err)
				}
			} else {
				var failure *Failure
				if !errors.As(err, &failure) || !failure.OutcomeUnknown || result.Value.PutAttemptID != "" {
					t.Fatal("incomplete stream confirmed", result, err)
				}
			}
		})
	}
}

func TestPreparationEarlyDenialDoesNotRequireConsumedBody(t *testing.T) {
	for _, status := range []int{401, 403, 404, 422} {
		t.Run(fmt.Sprint(status), func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "bundle.zip")
			if err := os.WriteFile(path, []byte("reviewed ZIP bytes"), 0600); err != nil {
				t.Fatal(err)
			}
			source, err := os.Open(path)
			if err != nil {
				t.Fatal(err)
			}
			defer source.Close()
			transport := preparationTransport(func(r *http.Request) (*http.Response, error) {
				body := `{"error":{"code":"permission_denied","message":"Denied","details":{},"correlation_id":"50000000-0000-7000-8000-000000000001","retryable":false}}`
				if status == 422 {
					body = `{"error":{"code":"pre_submission_checker_failed","message":"Intake failed","details":{"status":"failed","eligible_to_submit":false,"results":[{"source":"workstream_default","status":"failed","check_id":"manifest","failure_code":"manifest_missing","finding_count":1}]},"correlation_id":"50000000-0000-7000-8000-000000000001","retryable":false}}`
				}
				return &http.Response{StatusCode: status, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(strings.NewReader(body))}, nil
			})
			c := &Client{origin: "https://example.test", token: "test-token", guideHTTP: &http.Client{Transport: transport}}
			_, err = c.PrepareSubmission(context.Background(), "30000000-0000-7000-8000-000000000001", "40000000-0000-7000-8000-000000000001", SubmissionPacket{Assignment: "20000000-0000-7000-8000-000000000001"}, nil, source, "")
			var failure *Failure
			if !errors.As(err, &failure) || failure.OutcomeUnknown || failure.Status != status || (status == 422 && len(failure.Details) == 0) {
				t.Fatal("known early refusal became uncertain", err)
			}
		})
	}
}

func TestPreparationSealsBodyBeforeReturningToCallerWithAsyncTransport(t *testing.T) {
	path := filepath.Join(t.TempDir(), "bundle.zip")
	if err := os.WriteFile(path, []byte("reviewed ZIP bytes"), 0600); err != nil {
		t.Fatal(err)
	}
	source, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer source.Close()
	release, done := make(chan struct{}), make(chan error, 1)
	transport := preparationTransport(func(r *http.Request) (*http.Response, error) {
		go func() {
			<-release
			_, readErr := r.Body.Read(make([]byte, 1))
			_ = r.Body.Close()
			done <- readErr
		}()
		return &http.Response{StatusCode: 202, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(strings.NewReader(preparationAcceptedJSON))}, nil
	})
	c := &Client{origin: "https://example.test", token: "test-token", guideHTTP: &http.Client{Transport: transport}}
	_, err = c.PrepareSubmission(context.Background(), "30000000-0000-7000-8000-000000000001", "40000000-0000-7000-8000-000000000001", SubmissionPacket{Assignment: "20000000-0000-7000-8000-000000000001"}, nil, source, "")
	_ = source.Close() // The owner may close immediately after PrepareSubmission.
	close(release)
	if readErr := <-done; readErr != io.ErrClosedPipe {
		t.Fatal("late transport read reached caller-owned source", readErr)
	}
	var failure *Failure
	if !errors.As(err, &failure) || !failure.OutcomeUnknown {
		t.Fatal("unconsumed early 202 confirmed", err)
	}
}
