//go:build !windows

package login

import (
	"os"
	"syscall"
)

func ownedPrivate(info os.FileInfo, regular bool) bool {
	stat, ok := info.Sys().(*syscall.Stat_t)
	return ok && stat.Uid == uint32(os.Geteuid()) && info.Mode().Perm()&0077 == 0 && (!regular || stat.Nlink == 1)
}
