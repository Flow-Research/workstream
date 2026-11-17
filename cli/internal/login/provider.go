package login

import (
	"context"
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/coreos/go-oidc/v3/oidc"
	"github.com/go-jose/go-jose/v4"
	"golang.org/x/oauth2"
)

const DefaultIssuer = "https://identity.flowresearch.tech/realms/flow"
const DefaultAPI = "https://workstream.flowresearch.tech"
const ClientID = "workstream-cli-login"
const Callback = "http://127.0.0.1:17843/callback"

var scopes = []string{"openid", "workstream:access", "workstream-api-audience"}

func origin(value string) (string, error) {
	u, err := url.Parse(value)
	if err != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" || (u.Path != "" && u.Path != "/") {
		return "", errors.New("API origin must be an exact HTTPS origin")
	}
	return strings.TrimSuffix(value, "/"), nil
}
func issuer(value string) error {
	u, err := url.Parse(value)
	if err != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" || u.Path != "/realms/flow" {
		return errors.New("issuer must be the exact HTTPS Flow realm URL")
	}
	return nil
}

// Client performs one bounded request per credential operation, without redirects.
type Client struct{ HTTP *http.Client }

func NewClient() *Client {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil
	return &Client{HTTP: &http.Client{Transport: boundedTransport{transport}, Timeout: 20 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}}
}

type boundedTransport struct{ inner http.RoundTripper }

func (t boundedTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	response, err := t.inner.RoundTrip(r)
	if err != nil {
		return nil, err
	}
	data, err := io.ReadAll(io.LimitReader(response.Body, 65537))
	response.Body.Close()
	if err != nil || len(data) > 65536 {
		return nil, errors.New("identity response exceeds the supported limit")
	}
	response.Body = io.NopCloser(strings.NewReader(string(data)))
	return response, nil
}
func (c *Client) provider(ctx context.Context, value string) (*oidc.Provider, *oauth2.Config, error) {
	if err := issuer(value); err != nil {
		return nil, nil, err
	}
	ctx = oidc.ClientContext(ctx, c.HTTP)
	p, err := oidc.NewProvider(ctx, value)
	if err != nil {
		return nil, nil, errors.New("cannot read trusted identity discovery")
	}
	var metadata struct {
		JWKS string `json:"jwks_uri"`
	}
	if p.Claims(&metadata) != nil || metadata.JWKS != value+"/protocol/openid-connect/certs" || p.Endpoint().AuthURL != value+"/protocol/openid-connect/auth" || p.Endpoint().TokenURL != value+"/protocol/openid-connect/token" {
		return nil, nil, errors.New("identity discovery endpoints do not match the trusted issuer")
	}
	endpoint := p.Endpoint()
	endpoint.AuthStyle = oauth2.AuthStyleInParams
	return p, &oauth2.Config{ClientID: ClientID, Endpoint: endpoint, RedirectURL: Callback, Scopes: scopes}, nil
}
func (c *Client) verify(ctx context.Context, p *oidc.Provider, t *oauth2.Token, subject string) (string, error) {
	if t == nil || len(t.AccessToken) > 8192 || len(t.RefreshToken) > 8192 || t.RefreshToken == "" || !strings.EqualFold(t.TokenType, "Bearer") {
		return "", errors.New("identity returned an invalid bearer credential")
	}
	parts := strings.Split(t.AccessToken, ".")
	if len(parts) != 3 {
		return "", errors.New("invalid API token encoding")
	}
	headerBytes, e := base64.RawURLEncoding.DecodeString(parts[0])
	if e != nil {
		return "", errors.New("invalid API token header")
	}
	var header map[string]any
	if json.Unmarshal(headerBytes, &header) != nil || header["alg"] != "RS256" {
		return "", errors.New("invalid API token algorithm")
	}
	kid, ok := header["kid"].(string)
	if !ok || kid == "" {
		return "", errors.New("missing API signing key identifier")
	}
	for _, field := range []string{"jku", "jwk", "x5u", "crit"} {
		if _, exists := header[field]; exists {
			return "", errors.New("unsupported API token header")
		}
	}
	var metadata struct {
		Issuer string `json:"issuer"`
		JWKS   string `json:"jwks_uri"`
	}
	if p.Claims(&metadata) != nil {
		return "", errors.New("invalid identity discovery")
	}
	key, err := c.signingKey(ctx, metadata.JWKS, kid)
	if err != nil {
		return "", err
	}
	token, err := oidc.NewVerifier(metadata.Issuer, &oidc.StaticKeySet{PublicKeys: []crypto.PublicKey{key}}, &oidc.Config{ClientID: "workstream-api", SupportedSigningAlgs: []string{"RS256"}}).Verify(ctx, t.AccessToken)
	if err != nil {
		return "", errors.New("API credential signature, issuer, audience or lifetime is invalid")
	}
	var claims struct {
		Scope   string `json:"scope"`
		Party   string `json:"azp"`
		Kind    string `json:"subject_kind"`
		Type    string `json:"typ"`
		Email   string `json:"email"`
		Issued  int64  `json:"iat"`
		Expires int64  `json:"exp"`
	}
	if token.Claims(&claims) != nil || token.Subject == "" || len(token.Subject) > 200 || len(claims.Email) > 320 || strings.ContainsFunc(token.Subject+claims.Email, func(r rune) bool { return r < 32 }) || len(token.Audience) != 1 || token.Audience[0] != "workstream-api" || claims.Expires != token.Expiry.Unix() || token.Expiry.Unix()-claims.Issued > 300 || (subject != "" && subject != token.Subject) || claims.Party != ClientID || claims.Kind != "human" || claims.Type != "Bearer" || strings.TrimSpace(claims.Email) == "" || claims.Issued <= 0 || claims.Issued > time.Now().Add(30*time.Second).Unix() || claims.Issued >= token.Expiry.Unix() {
		return "", errors.New("API credential does not match the expected participant")
	}
	scopeSet := map[string]bool{}
	for _, scope := range strings.Fields(claims.Scope) {
		scopeSet[scope] = true
	}
	if len(scopeSet) != 2 || !scopeSet["openid"] || !scopeSet["workstream:access"] {
		return "", errors.New("API credential has invalid access scopes")
	}
	t.Expiry = token.Expiry
	return token.Subject, nil
}
func randomValue() string {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return base64.RawURLEncoding.EncodeToString(b)
}

// Credential returns a current verified token only for its bound API origin.
func (c *Client) Credential(ctx context.Context, store Store, apiOrigin string) (string, string, error) {
	var access, bound string
	err := store.locked(func() error {
		s, err := store.read()
		if err != nil {
			return err
		}
		if s.Subject == "" {
			return errors.New("saved session has no participant identity; run workstream login")
		}
		bound, err = origin(s.APIOrigin)
		if err != nil {
			return err
		}
		if apiOrigin != "" {
			requested, e := origin(apiOrigin)
			if e != nil {
				return e
			}
			if requested != bound {
				return errors.New("saved login belongs to another API origin; log in to the intended server")
			}
		}
		if s.RefreshUncertain {
			return errors.New("previous refresh outcome is uncertain; run workstream login")
		}
		p, config, err := c.provider(ctx, s.Issuer)
		if err != nil {
			return err
		}
		if s.Token.Expiry.Before(time.Now().Add(30 * time.Second)) {
			s.RefreshUncertain = true
			if err = store.save(s); err != nil {
				return err
			}
			renewed, e := config.TokenSource(context.WithValue(ctx, oauth2.HTTPClient, c.HTTP), &oauth2.Token{RefreshToken: s.Token.RefreshToken}).Token()
			if e != nil {
				return errors.New("session renewal failed; run workstream login")
			}
			if _, e = c.verify(ctx, p, renewed, s.Subject); e != nil {
				return e
			}
			s.Token = renewed
			s.RefreshUncertain = false
			if err = store.save(s); err != nil {
				return err
			}
		} else if _, err = c.verify(ctx, p, s.Token, s.Subject); err != nil {
			return err
		}
		access = s.Token.AccessToken
		return nil
	})
	return bound, access, err
}

// Logout removes local credentials even when remote session closure is uncertain.
func (c *Client) Logout(ctx context.Context, store Store) error {
	return store.locked(func() error {
		s, err := store.read()
		if err != nil {
			return err
		}
		if err = store.remove(); err != nil {
			return err
		}
		if issuer(s.Issuer) != nil {
			return errors.New("local login removed; invalid issuer prevented remote logout")
		}
		data := url.Values{"client_id": {ClientID}, "refresh_token": {s.Token.RefreshToken}}
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, s.Issuer+"/protocol/openid-connect/logout", strings.NewReader(data.Encode()))
		if err != nil {
			return errors.New("local login removed; remote logout unavailable")
		}
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		response, err := c.HTTP.Do(req)
		if err != nil {
			return errors.New("local login removed; remote logout could not be confirmed")
		}
		defer response.Body.Close()
		if response.StatusCode != 204 && response.StatusCode != 200 {
			return errors.New("local login removed; remote logout rejected")
		}
		return nil
	})
}

// signingKey accepts exactly one bounded public signing key for the token's kid.
func (c *Client) signingKey(ctx context.Context, address, kid string) (*rsa.PublicKey, error) {
	fail := errors.New("identity signing key is invalid")
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, address, nil)
	if err != nil {
		return nil, fail
	}
	res, err := c.HTTP.Do(req)
	if err != nil {
		return nil, fail
	}
	defer res.Body.Close()
	var document struct {
		Keys []json.RawMessage `json:"keys"`
	}
	if res.StatusCode != 200 || json.NewDecoder(res.Body).Decode(&document) != nil || len(document.Keys) < 1 || len(document.Keys) > 16 {
		return nil, fail
	}
	var selected *rsa.PublicKey
	for _, raw := range document.Keys {
		var fields map[string]json.RawMessage
		if json.Unmarshal(raw, &fields) != nil {
			return nil, fail
		}
		var id string
		if json.Unmarshal(fields["kid"], &id) != nil || id != kid {
			continue
		}
		if selected != nil {
			return nil, fail
		}
		if _, exists := fields["d"]; exists {
			return nil, fail
		}
		if ops, exists := fields["key_ops"]; exists {
			var values []string
			if json.Unmarshal(ops, &values) != nil || len(values) != 1 || values[0] != "verify" {
				return nil, fail
			}
		}
		var key jose.JSONWebKey
		if json.Unmarshal(raw, &key) != nil || key.Algorithm != "RS256" || key.Use != "sig" || !key.IsPublic() {
			return nil, fail
		}
		value, ok := key.Key.(*rsa.PublicKey)
		if !ok || value.N.BitLen() < 2048 || value.N.BitLen() > 8192 {
			return nil, fail
		}
		selected = value
	}
	if selected == nil {
		return nil, fail
	}
	return selected, nil
}
