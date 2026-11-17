package command

import (
	"bytes"
	"compress/zlib"
	"encoding/base64"
	"encoding/json"
	"path/filepath"
	"testing"
	"time"

	"github.com/Flow-Research/workstream/cli/internal/login"
	"github.com/zalando/go-keyring"
	"golang.org/x/oauth2"
)

func TestTokenCommandHonorsConfiguredAPIOrigin(t *testing.T) {
	keyring.MockInit()
	t.Setenv("XDG_CONFIG_HOME", filepath.Join(t.TempDir(), "config"))
	session := login.Session{Issuer: login.DefaultIssuer, APIOrigin: login.DefaultAPI, Subject: "participant", Token: &oauth2.Token{AccessToken: "private-access", RefreshToken: "private-refresh", TokenType: "Bearer", Expiry: time.Now().Add(time.Minute)}}
	raw, err := json.Marshal(session)
	if err != nil {
		t.Fatal(err)
	}
	var packed bytes.Buffer
	writer := zlib.NewWriter(&packed)
	writer.Write(raw)
	writer.Close()
	if err = keyring.Set("workstream-cli", "participant", base64.RawStdEncoding.EncodeToString(packed.Bytes())); err != nil {
		t.Fatal(err)
	}
	var out, errors bytes.Buffer
	result := Run([]string{"auth", "token"}, &out, &errors, func(name string) string {
		if name == "WORKSTREAM_API_URL" {
			return "https://foreign.example"
		}
		return ""
	}, "test")
	if result == 0 || out.Len() != 0 {
		t.Fatal("foreign destination exported token")
	}
	if !bytes.Contains(errors.Bytes(), []byte("another API origin")) {
		t.Fatalf("wrong rejection: %s", errors.String())
	}
	if bytes.Contains(errors.Bytes(), []byte("private-")) {
		t.Fatal("credential leaked")
	}
}
