package tui

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
)

func openPreparationSource(path string) (*os.File, error) {
	// Accept ordinary filesystem paths, not Win32 device namespaces or named
	// pipe shares. Reject reserved device basenames before opening a handle.
	normalized := strings.ReplaceAll(path, "/", `\`)
	if strings.HasPrefix(normalized, `\\.\`) || strings.HasPrefix(normalized, `\\?\`) ||
		strings.HasPrefix(normalized, `\??\`) || !filepath.IsLocal(filepath.Base(normalized)) {
		return nil, errors.New("ZIP requires an ordinary filesystem path")
	}
	if strings.HasPrefix(normalized, `\\`) {
		parts := strings.Split(strings.TrimPrefix(normalized, `\\`), `\`)
		if len(parts) > 1 && strings.EqualFold(parts[1], "pipe") {
			return nil, errors.New("ZIP requires an ordinary filesystem path")
		}
	}
	return os.Open(path)
}
