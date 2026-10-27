package tui

import "testing"

func TestPreparationWindowsRejectsDeviceAndPipePathsBeforeOpen(t *testing.T) {
	for _, path := range []string{`NUL`, `CONIN$`, `C:\data\CON`, `\\.\pipe\workstream`, `\\?\pipe\workstream`, `\\server\pipe\workstream`} {
		f, err := openPreparationSource(path)
		if err == nil || f != nil {
			if f != nil {
				_ = f.Close()
			}
			t.Fatalf("device or pipe path opened: %q", path)
		}
	}
}
