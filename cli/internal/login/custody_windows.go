//go:build windows

package login

import "os"

// Windows credentials are protected by Credential Manager; Unix modes do not
// describe the ACL on the current user's configuration directory.
func ownedPrivate(info os.FileInfo, regular bool) bool { return true }
