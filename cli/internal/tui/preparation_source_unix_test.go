//go:build unix

package tui

import (
	"context"
	"path/filepath"
	"syscall"
	"testing"
	"time"
)

func TestPreparationFIFOIsRejectedWithoutWaitingForWriter(t *testing.T) {
	path := filepath.Join(t.TempDir(), "bundle.zip")
	if err := syscall.Mkfifo(path, 0600); err != nil {
		t.Fatal(err)
	}
	done := make(chan error, 1)
	go func() { _, _, err := hashPreparationZIP(context.Background(), path); done <- err }()
	select {
	case err := <-done:
		if err == nil {
			t.Fatal("FIFO accepted as regular ZIP")
		}
	case <-time.After(time.Second):
		t.Fatal("FIFO open blocked local cancellation")
	}
}
