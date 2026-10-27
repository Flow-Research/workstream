package api

import (
	"context"
	"crypto/sha256"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
)

func TestPreparationReviewedHashIsCheckedBeforePOST(t *testing.T) {
	var posts atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		posts.Add(1)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_, _ = fmt.Fprint(w, `{"put_attempt_id":"10000000-0000-7000-8000-000000000001","admission_id":null,"submission_bundle_preparation_status":"stored_pending_verification","replayed":false,"pre_submission_results":[]}`)
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
