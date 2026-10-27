//go:build unix

package tui

import (
	"os"
	"syscall"
)

func openPreparationSource(path string) (*os.File, error) {
	// A path replaced by a FIFO must not block before the common regular-file
	// check. O_NONBLOCK does not change ordinary regular-file reads.
	return os.OpenFile(path, os.O_RDONLY|syscall.O_NONBLOCK, 0)
}
