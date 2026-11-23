package login

import (
	"bytes"
	"compress/zlib"
	"context"
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"io"
	"math/big"
	mathrand "math/rand"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/zalando/go-keyring"
	"golang.org/x/oauth2"
)

type fixture struct {
	server       *httptest.Server
	client       *Client
	key          *rsa.PrivateKey
	issuer       string
	refreshes    int
	fail         bool
	subject      string
	duplicateKey bool
	keyUse       string
	metadata     map[string]any
	tokenCalls   int
}

func newFixture(t *testing.T) *fixture {
	t.Helper()
	keyring.MockInit()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	f := &fixture{key: key, subject: "participant", keyUse: "sig"}
	f.server = httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/realms/flow/.well-known/openid-configuration":
			metadata := map[string]any{"issuer": f.issuer, "authorization_endpoint": f.issuer + "/protocol/openid-connect/auth", "token_endpoint": f.issuer + "/protocol/openid-connect/token", "jwks_uri": f.issuer + "/protocol/openid-connect/certs", "id_token_signing_alg_values_supported": []string{"RS256"}, "code_challenge_methods_supported": []string{"S256"}}
			for k, v := range f.metadata {
				metadata[k] = v
			}
			json.NewEncoder(w).Encode(metadata)
		case "/realms/flow/protocol/openid-connect/certs":
			enc := base64.RawURLEncoding.EncodeToString
			entry := map[string]any{"kty": "RSA", "kid": "test", "alg": "RS256", "use": f.keyUse, "n": enc(f.key.N.Bytes()), "e": enc(big.NewInt(int64(f.key.E)).Bytes())}
			keys := []any{entry}
			if f.duplicateKey {
				keys = append(keys, entry)
			}
			json.NewEncoder(w).Encode(map[string]any{"keys": keys})
		case "/realms/flow/protocol/openid-connect/token":
			f.tokenCalls++
			r.ParseForm()
			if r.Form.Get("grant_type") == "refresh_token" {
				f.refreshes++
			}
			if f.fail {
				w.WriteHeader(503)
				io.WriteString(w, `{"error":"private-provider-detail"}`)
				return
			}
			json.NewEncoder(w).Encode(map[string]any{"access_token": f.signed(nil), "refresh_token": "rotated-refresh", "token_type": "Bearer", "expires_in": 300})
		case "/realms/flow/protocol/openid-connect/logout":
			if f.fail {
				w.WriteHeader(503)
			} else {
				w.WriteHeader(204)
			}
		default:
			http.NotFound(w, r)
		}
	}))
	f.issuer = f.server.URL + "/realms/flow"
	h := f.server.Client()
	h.Timeout = 5 * time.Second
	h.Transport = boundedTransport{h.Transport}
	h.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	f.client = &Client{HTTP: h}
	t.Cleanup(f.server.Close)
	return f
}
func (f *fixture) signed(change map[string]any) string {
	claims := map[string]any{"iss": f.issuer, "aud": "workstream-api", "sub": f.subject, "azp": ClientID, "typ": "Bearer", "subject_kind": "human", "email": "person@example.test", "scope": "openid workstream:access", "iat": time.Now().Unix(), "exp": time.Now().Add(300 * time.Second).Unix()}
	for k, v := range change {
		claims[k] = v
	}
	h, _ := json.Marshal(map[string]string{"alg": "RS256", "kid": "test"})
	b, _ := json.Marshal(claims)
	data := base64.RawURLEncoding.EncodeToString(h) + "." + base64.RawURLEncoding.EncodeToString(b)
	hash := sha256.Sum256([]byte(data))
	sig, _ := rsa.SignPKCS1v15(rand.Reader, f.key, crypto.SHA256, hash[:])
	return data + "." + base64.RawURLEncoding.EncodeToString(sig)
}
func (f *fixture) save(t *testing.T, expired bool) Store {
	t.Helper()
	s := Store{Directory: filepath.Join(t.TempDir(), "login")}
	expiry := time.Now().Add(300 * time.Second)
	if expired {
		expiry = time.Now().Add(-time.Second)
	}
	if err := s.save(&Session{Issuer: f.issuer, APIOrigin: DefaultAPI, Subject: "participant", Token: &oauth2.Token{AccessToken: f.signed(nil), RefreshToken: "refresh", TokenType: "Bearer", Expiry: expiry}}); err != nil {
		t.Fatal(err)
	}
	return s
}
func TestVerifiedCredentialIsBoundToDestination(t *testing.T) {
	f := newFixture(t)
	s := f.save(t, false)
	if _, _, err := f.client.Credential(context.Background(), s, "https://foreign.example"); err == nil {
		t.Fatal("foreign origin accepted")
	}
	origin, token, err := f.client.Credential(context.Background(), s, DefaultAPI)
	if err != nil || origin != DefaultAPI || token == "" {
		t.Fatalf("credential: %v", err)
	}
}
func TestRejectSignedClaimSubstitution(t *testing.T) {
	f := newFixture(t)
	p, _, err := f.client.provider(context.Background(), f.issuer)
	if err != nil {
		t.Fatal(err)
	}
	cases := []map[string]any{{"iss": "https://other.example/realms/flow"}, {"aud": []string{"workstream-api", "other"}}, {"azp": "garden-dev"}, {"subject_kind": "service"}, {"typ": "ID"}, {"scope": "openid"}, {"email": ""}, {"sub": "other"}, {"exp": time.Now().Add(900 * time.Second).Unix()}, {"iat": time.Now().Add(time.Minute).Unix()}}
	for _, change := range cases {
		token := &oauth2.Token{AccessToken: f.signed(change), RefreshToken: "refresh", TokenType: "Bearer"}
		if _, err := f.client.verify(context.Background(), p, token, "participant"); err == nil {
			t.Fatalf("accepted substitution %v", change)
		}
	}
}
func TestRefreshRotationAndUncertainOutcome(t *testing.T) {
	f := newFixture(t)
	s := f.save(t, true)
	if _, _, err := f.client.Credential(context.Background(), s, ""); err != nil {
		t.Fatal(err)
	}
	saved, _ := s.read()
	if saved.Token.RefreshToken != "rotated-refresh" || saved.RefreshUncertain || f.refreshes != 1 {
		t.Fatal("rotation not retained")
	}
	s = f.save(t, true)
	f.fail = true
	for range 2 {
		if _, _, err := f.client.Credential(context.Background(), s, ""); err == nil || strings.Contains(err.Error(), "private-provider-detail") {
			t.Fatal("refresh failure not sanitized")
		}
	}
	if f.refreshes != 2 {
		t.Fatal("uncertain refresh was repeated")
	}
	if err := f.client.Logout(context.Background(), s); err == nil {
		t.Fatal("remote failure hidden")
	}
	if _, err := s.read(); err == nil {
		t.Fatal("local session retained")
	}
}
func TestRefreshCannotChangeParticipant(t *testing.T) {
	f := newFixture(t)
	s := f.save(t, true)
	f.subject = "other"
	if _, _, err := f.client.Credential(context.Background(), s, ""); err == nil {
		t.Fatal("subject changed")
	}
	saved, _ := s.read()
	if !saved.RefreshUncertain {
		t.Fatal("uncertain state lost")
	}
}
func TestCallbackRejectsSubstitutionBeforeAccepting(t *testing.T) {
	result := make(chan string, 1)
	handler := callback("expected", result)
	for _, address := range []string{"http://127.0.0.1:17843/callback?state=wrong&code=x", "http://127.0.0.1:17843/callback?state=expected&state=expected&code=x", "http://evil.example/callback?state=expected&code=x", "http://127.0.0.1:17843/callback?state=expected&code=x&code=y"} {
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, httptest.NewRequest("GET", address, nil))
		if w.Code != 400 {
			t.Fatal("invalid callback accepted")
		}
	}
	select {
	case <-result:
		t.Fatal("invalid callback consumed")
	default:
	}
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, httptest.NewRequest("GET", Callback+"?state=expected&code=valid", nil))
	if w.Code != 200 || <-result != "valid" {
		t.Fatal("valid callback rejected")
	}
}
func TestBrowserLoginUsesPKCEAndStoresVerifiedCredential(t *testing.T) {
	f := newFixture(t)
	s := Store{Directory: filepath.Join(t.TempDir(), "login")}
	var output strings.Builder
	err := f.client.Login(context.Background(), s, f.issuer, DefaultAPI, &output, func(address string) error {
		u, _ := url.Parse(address)
		q := u.Query()
		if q.Get("code_challenge_method") != "S256" || q.Get("code_challenge") == "" || q.Get("scope") != strings.Join(scopes, " ") {
			t.Fatal("missing PKCE/scopes")
		}
		r, err := http.Get(Callback + "?state=" + url.QueryEscape(q.Get("state")) + "&code=code")
		if err == nil {
			r.Body.Close()
		}
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	saved, err := s.read()
	if err != nil || saved.Subject != "participant" {
		t.Fatal("login not saved")
	}
	if strings.Contains(output.String(), saved.Token.AccessToken) || strings.Contains(output.String(), saved.Token.RefreshToken) {
		t.Fatal("token printed during login")
	}
}

func TestConsentDenialEndsLoginWithoutCredential(t *testing.T) {
	f := newFixture(t)
	s := Store{Directory: filepath.Join(t.TempDir(), "login")}
	err := f.client.Login(context.Background(), s, f.issuer, DefaultAPI, io.Discard, func(address string) error {
		u, _ := url.Parse(address)
		response, err := http.Get(Callback + "?state=" + url.QueryEscape(u.Query().Get("state")) + "&error=access_denied")
		if err == nil {
			response.Body.Close()
		}
		return err
	})
	if err == nil || !strings.Contains(err.Error(), "declined") {
		t.Fatalf("denial did not end login: %v", err)
	}
	if _, err := s.read(); err == nil {
		t.Fatal("denial saved credentials")
	}
}
func TestCredentialLockRejectsConcurrentOperation(t *testing.T) {
	f := newFixture(t)
	s := f.save(t, false)
	err := s.locked(func() error {
		_, _, err := f.client.Credential(context.Background(), s, "")
		if err == nil || !strings.Contains(err.Error(), "another login") {
			t.Fatal("concurrent login operation accepted")
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
}

func TestUnsafeLockPathsRejectBeforeCredentialAccess(t *testing.T) {
	if runtime.GOOS == "windows" {
		return
	} // Unix ownership/mode semantics.
	f := newFixture(t)
	for _, kind := range []string{"symlink", "hardlink", "public"} {
		t.Run(kind, func(t *testing.T) {
			s := f.save(t, false)
			if err := os.MkdirAll(s.Directory, 0700); err != nil {
				t.Fatal(err)
			}
			target := filepath.Join(t.TempDir(), "target")
			if err := os.WriteFile(target, []byte("owned"), 0600); err != nil {
				t.Fatal(err)
			}
			lock := filepath.Join(s.Directory, "session.lock")
			var err error
			switch kind {
			case "symlink":
				err = os.Symlink(target, lock)
			case "hardlink":
				err = os.Link(target, lock)
			case "public":
				err = os.WriteFile(lock, nil, 0644)
			}
			if err != nil {
				t.Fatal(err)
			}
			if _, _, err := f.client.Credential(context.Background(), s, ""); err == nil {
				t.Fatal("unsafe path accepted")
			}
		})
	}
}
func TestLockAcrossProcesses(t *testing.T) {
	if path := os.Getenv("WORKSTREAM_LOCK_TEST_DIRECTORY"); path != "" {
		err := (Store{Directory: path}).locked(func() error { t.Fatal("child entered locked operation"); return nil })
		if err == nil || !strings.Contains(err.Error(), "another login") {
			t.Fatal("wrong lock result")
		}
		return
	}
	s := Store{Directory: filepath.Join(t.TempDir(), "login")}
	err := s.locked(func() error {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		cmd := exec.CommandContext(ctx, os.Args[0], "-test.run=^TestLockAcrossProcesses$")
		cmd.Env = append(os.Environ(), "WORKSTREAM_LOCK_TEST_DIRECTORY="+s.Directory)
		output, err := cmd.CombinedOutput()
		if err != nil {
			t.Fatalf("child lock proof: %s", output)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
}

func TestRejectMatchingButInvalidSigningKey(t *testing.T) {
	for _, kind := range []string{"weak", "duplicate", "encryption"} {
		t.Run(kind, func(t *testing.T) {
			f := newFixture(t)
			switch kind {
			case "weak":
				key, err := rsa.GenerateKey(rand.Reader, 1024)
				if err != nil {
					t.Fatal(err)
				}
				f.key = key
			case "duplicate":
				f.duplicateKey = true
			case "encryption":
				f.keyUse = "enc"
			}
			p, _, err := f.client.provider(context.Background(), f.issuer)
			if err != nil {
				t.Fatal(err)
			}
			_, err = f.client.verify(context.Background(), p, &oauth2.Token{AccessToken: f.signed(nil), RefreshToken: "refresh", TokenType: "Bearer"}, "participant")
			if err == nil || err.Error() != "identity signing key is invalid" {
				t.Fatalf("expected key rejection: %v", err)
			}
		})
	}
}

func TestDiscoveryCannotRedirectCredentials(t *testing.T) {
	for _, field := range []string{"issuer", "authorization_endpoint", "token_endpoint", "jwks_uri", "code_challenge_methods_supported"} {
		t.Run(field, func(t *testing.T) {
			f := newFixture(t)
			f.metadata = map[string]any{field: "https://foreign.example/endpoint"}
			if field == "code_challenge_methods_supported" {
				f.metadata[field] = []string{"plain"}
			}
			s := f.save(t, true)
			launched := false
			err := f.client.Login(context.Background(), s, f.issuer, DefaultAPI, io.Discard, func(string) error { launched = true; return nil })
			if err == nil || launched || f.tokenCalls != 0 {
				t.Fatal("untrusted discovery reached browser or token endpoint")
			}
			if _, _, err = f.client.Credential(context.Background(), s, ""); err == nil || f.tokenCalls != 0 {
				t.Fatal("untrusted discovery reached refresh endpoint")
			}
		})
	}
}

func TestSessionEncodingFitsSmallCredentialStores(t *testing.T) {
	f := newFixture(t)
	token := f.signed(map[string]any{"name": strings.Repeat("Participant Long Name ", 60)})
	session := &Session{Issuer: f.issuer, APIOrigin: DefaultAPI, Subject: "participant", Token: &oauth2.Token{AccessToken: token, RefreshToken: f.signed(map[string]any{"typ": "Refresh"}), TokenType: "Bearer"}}
	plain, _ := json.Marshal(session)
	if len(plain) <= 2560 {
		t.Fatal("fixture does not exercise Windows size limit")
	}
	encoded, err := encodeSession(session)
	if err != nil {
		t.Fatal(err)
	}
	if len(encoded) > 2560 {
		t.Fatal("encoded session still exceeds small-store limit")
	}
	decoded, err := decodeSession(encoded)
	if err != nil || decoded.Token.AccessToken != token || decoded.Token.RefreshToken != session.Token.RefreshToken {
		t.Fatal("session did not round trip")
	}
}
func TestCapacityErrorIsNotReportedAsLockedKeychain(t *testing.T) {
	keyring.MockInitWithError(keyring.ErrSetDataTooBig)
	t.Cleanup(keyring.MockInit)
	err := (Store{}).save(&Session{Token: &oauth2.Token{AccessToken: "access", RefreshToken: "refresh"}})
	if err == nil || !strings.Contains(err.Error(), "capacity") || strings.Contains(err.Error(), "unlock") {
		t.Fatalf("wrong capacity error: %v", err)
	}
}
func TestOversizedSessionCannotReplacePriorCredential(t *testing.T) {
	f := newFixture(t)
	s := f.save(t, false)
	before, _ := keyring.Get(secretService, secretAccount)
	err := s.save(&Session{Token: &oauth2.Token{AccessToken: strings.Repeat("x", 65537)}})
	if err == nil {
		t.Fatal("oversized session accepted")
	}
	after, _ := keyring.Get(secretService, secretAccount)
	if before != after {
		t.Fatal("failed save replaced prior credential")
	}
}
func TestFailedNewLoginPreservesExistingSession(t *testing.T) {
	f := newFixture(t)
	s := f.save(t, false)
	before, _ := keyring.Get(secretService, secretAccount)
	f.subject = ""
	err := f.client.Login(context.Background(), s, f.issuer, DefaultAPI, io.Discard, func(address string) error {
		u, _ := url.Parse(address)
		response, err := http.Get(Callback + "?state=" + url.QueryEscape(u.Query().Get("state")) + "&code=code")
		if err == nil {
			response.Body.Close()
		}
		return err
	})
	if err == nil {
		t.Fatal("invalid participant accepted")
	}
	after, _ := keyring.Get(secretService, secretAccount)
	if before != after {
		t.Fatal("failed login replaced prior session")
	}
}

func TestCompressedSessionExpansionIsBounded(t *testing.T) {
	var packed bytes.Buffer
	writer := zlib.NewWriter(&packed)
	data, err := json.Marshal(&Session{Token: &oauth2.Token{AccessToken: strings.Repeat("x", 65537)}})
	if err != nil {
		t.Fatal(err)
	}
	writer.Write(data)
	writer.Close()
	if _, err := decodeSession(base64.RawStdEncoding.EncodeToString(packed.Bytes())); err == nil {
		t.Fatal("oversized expanded credential accepted")
	}
}

func TestEncodedSessionCannotReplacePriorCredential(t *testing.T) {
	f := newFixture(t)
	store := f.save(t, false)
	before, _ := keyring.Get(secretService, secretAccount)
	random := mathrand.New(mathrand.NewSource(42))
	alphabet := "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#$%()*+,-./:;=?@[]^_`{|}~"
	token := make([]byte, 65000)
	for i := range token {
		token[i] = alphabet[random.Intn(len(alphabet))]
	}
	session := &Session{Token: &oauth2.Token{RefreshToken: string(token)}}
	data, err := json.Marshal(session)
	if err != nil || len(data) > 65536 {
		t.Fatal("fixture exceeds JSON bound")
	}
	var packed bytes.Buffer
	writer := zlib.NewWriter(&packed)
	if _, err := writer.Write(data); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	if len(base64.RawStdEncoding.EncodeToString(packed.Bytes())) <= 65536 {
		t.Fatal("fixture does not exceed encoded bound")
	}
	if err := store.save(session); err == nil {
		t.Fatal("unreadable encoded session saved")
	}
	after, _ := keyring.Get(secretService, secretAccount)
	if before != after {
		t.Fatal("failed save replaced prior credential")
	}
}
