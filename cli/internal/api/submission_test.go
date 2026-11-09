package api

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
)

func TestPrepareSubmissionRejectsOversizedCompressedZipBeforeHTTP(t *testing.T) {
	var requests atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests.Add(1)
		w.WriteHeader(http.StatusRequestEntityTooLarge)
	}))
	defer server.Close()
	client, err := New(server.URL, "test-token")
	if err != nil {
		t.Fatal(err)
	}
	file, err := os.Create(filepath.Join(t.TempDir(), "oversized.zip"))
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	// Sparse: exercise the real file-size boundary without a large allocation.
	if err := file.Truncate(524288001); err != nil {
		t.Fatal(err)
	}
	_, err = client.PrepareSubmission(context.Background(), testTask, testRun,
		SubmissionPacket{Assignment: testSubmission}, nil, file)
	if err == nil || err.Error() != "ZIP must be a nonempty regular file of at most 500MiB" {
		t.Fatalf("expected local compressed ZIP limit rejection, got %v", err)
	}
	if got := requests.Load(); got != 0 {
		t.Fatalf("oversized ZIP caused %d HTTP requests", got)
	}
}
