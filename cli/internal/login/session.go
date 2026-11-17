// Package login owns participant OAuth credentials for the standalone CLI.
package login

import (
	"bytes"
	"compress/zlib"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"

	"github.com/gofrs/flock"
	"github.com/zalando/go-keyring"
	"golang.org/x/oauth2"
)

const secretService = "workstream-cli"
const secretAccount = "participant"

// Session binds one credential to its issuing identity and destination API.
type Session struct {
	Issuer           string        `json:"issuer"`
	APIOrigin        string        `json:"api_origin"`
	Subject          string        `json:"subject"`
	Token            *oauth2.Token `json:"token"`
	RefreshUncertain bool          `json:"refresh_uncertain"`
}

// Store uses the operating system credential store, never a plaintext fallback.
type Store struct{ Directory string }

func DefaultStore() (Store, error) {
	root, err := os.UserConfigDir()
	if err != nil {
		return Store{}, errors.New("cannot locate the user configuration directory")
	}
	return Store{Directory: filepath.Join(root, "workstream")}, nil
}

func (s Store) locked(action func() error) error {
	if err := os.MkdirAll(s.Directory, 0700); err != nil {
		return errors.New("cannot create private login directory")
	}
	info, err := os.Lstat(s.Directory)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 || !ownedPrivate(info, false) {
		return errors.New("login directory must be private and not a symlink")
	}
	path := filepath.Join(s.Directory, "session.lock")
	if info, err := os.Lstat(path); err == nil {
		if !info.Mode().IsRegular() || !ownedPrivate(info, true) {
			return errors.New("unsafe login lock file")
		}
	} else if !os.IsNotExist(err) {
		return errors.New("cannot inspect login lock")
	}
	lock := flock.New(path, flock.SetPermissions(0600))
	ok, err := lock.TryLock()
	if err != nil || !ok {
		return errors.New("another login operation is running; retry after it finishes")
	}
	defer lock.Close()
	return action()
}

func (s Store) read() (*Session, error) {
	raw, err := keyring.Get(secretService, secretAccount)
	if errors.Is(err, keyring.ErrNotFound) {
		return nil, errors.New("not signed in; run workstream login")
	}
	if err != nil {
		return nil, errors.New("cannot access the OS credential store; unlock your desktop keychain")
	}
	return decodeSession(raw)
}

func decodeSession(raw string) (*Session, error) {
	invalid := errors.New("invalid saved session; run workstream login")
	if len(raw) > 65536 {
		return nil, invalid
	}
	packed, err := base64.RawStdEncoding.DecodeString(raw)
	if err != nil {
		return nil, invalid
	}
	reader, err := zlib.NewReader(bytes.NewReader(packed))
	if err != nil {
		return nil, invalid
	}
	defer reader.Close()
	data, err := io.ReadAll(io.LimitReader(reader, 65537))
	if err != nil || len(data) > 65536 {
		return nil, invalid
	}
	var result Session
	if json.Unmarshal(data, &result) != nil || result.Token == nil {
		return nil, invalid
	}
	return &result, nil
}

func encodeSession(session *Session) (string, error) {
	data, err := json.Marshal(session)
	if err != nil || len(data) > 65536 {
		return "", errors.New("cannot encode login session")
	}
	var packed bytes.Buffer
	writer := zlib.NewWriter(&packed)
	if _, err = writer.Write(data); err != nil {
		return "", errors.New("cannot encode login session")
	}
	if err = writer.Close(); err != nil {
		return "", errors.New("cannot encode login session")
	}
	return base64.RawStdEncoding.EncodeToString(packed.Bytes()), nil
}

func (s Store) save(session *Session) error {
	data, err := encodeSession(session)
	if err != nil {
		return err
	}
	if err = keyring.Set(secretService, secretAccount, data); err != nil {
		if errors.Is(err, keyring.ErrSetDataTooBig) {
			return errors.New("login session exceeds this OS credential store's capacity; contact the identity administrator to reduce token claims")
		}
		return errors.New("cannot save session in the OS credential store; unlock your desktop keychain")
	}
	return nil
}

func (s Store) remove() error {
	err := keyring.Delete(secretService, secretAccount)
	if err != nil && !errors.Is(err, keyring.ErrNotFound) {
		return errors.New("cannot remove session from the OS credential store")
	}
	return nil
}
