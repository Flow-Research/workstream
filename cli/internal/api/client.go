package api

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"encoding/json/jsontext"
	jsonv2 "encoding/json/v2"
	"errors"
	"fmt"
	"io"
	"mime"
	"net"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

const maxResponseBytes = 64 * 1024

var bearerValue = regexp.MustCompile(`^[A-Za-z0-9\-._~+/]+=*$`)
var safeCode = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_]{0,99}$`)
var safeCorrelation = regexp.MustCompile(`^[0-9a-fA-F-]{36}$`)

// Failure contains only bounded, public error metadata. It never includes a
// credential, URL, response body, or transport exception.
type Failure struct {
	Code          string `json:"code"`
	Status        int    `json:"status,omitempty"`
	CorrelationID string `json:"correlation_id,omitempty"`
}

func (f *Failure) Error() string {
	if f.CorrelationID != "" {
		return fmt.Sprintf("%s (HTTP %d; correlation %s)", f.Code, f.Status, f.CorrelationID)
	}
	if f.Status != 0 {
		return fmt.Sprintf("%s (HTTP %d)", f.Code, f.Status)
	}
	return f.Code
}

type Client struct {
	origin string
	token  string
	http   *http.Client
}

type Profile struct {
	ActorProfileID    string   `json:"actor_profile_id"`
	ActorKind         string   `json:"actor_kind"`
	Status            string   `json:"status"`
	Domains           []string `json:"domains"`
	AdminRoles        []string `json:"admin_roles"`
	ProjectRoleGrants []string `json:"project_role_grants"`
	DisplayName       *string  `json:"display_name"`
	ContactEmail      *string  `json:"contact_email"`
	CreatedAt         string   `json:"created_at"`
	UpdatedAt         string   `json:"updated_at"`
	LastSeenAt        *string  `json:"last_seen_at"`
}

type AuthorizationContext struct {
	ActorProfileID     string   `json:"actor_profile_id"`
	Status             string   `json:"status"`
	ProjectID          string   `json:"project_id"`
	AdminRoles         []string `json:"admin_roles"`
	ProjectRoles       []string `json:"project_roles"`
	EffectiveActionIDs []string `json:"effective_action_ids"`
}

type Result[T any] struct {
	Raw   json.RawMessage
	Value T
}

func New(origin, token string) (*Client, error) {
	normalized, err := validateOrigin(origin)
	if err != nil {
		return nil, err
	}
	if len(token) == 0 || len(token) > 8192 || !bearerValue.MatchString(token) {
		return nil, errors.New("WORKSTREAM_TOKEN must contain one unprefixed bearer value")
	}
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil
	return &Client{
		origin: normalized,
		token:  token,
		http: &http.Client{
			Transport: transport,
			Timeout:   12 * time.Second,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
	}, nil
}

func validateOrigin(raw string) (string, error) {
	bad := errors.New("WORKSTREAM_API_URL must be an HTTPS origin or loopback HTTP origin without credentials")
	if raw == "" || strings.ContainsAny(raw, " \t\r\n\x00") {
		return "", bad
	}
	u, err := url.Parse(raw)
	if err != nil || u.Opaque != "" || u.Host == "" || u.User != nil ||
		(u.Path != "" && u.Path != "/") || u.RawPath != "" || u.ForceQuery ||
		u.RawQuery != "" || u.Fragment != "" || strings.ContainsAny(raw, "?#") ||
		(u.Scheme != "https" && u.Scheme != "http") {
		return "", bad
	}
	host := u.Hostname()
	if host == "" || strings.ContainsAny(host, "\x00\r\n\t ") {
		return "", bad
	}
	if port := u.Port(); port != "" {
		n, err := strconv.Atoi(port)
		if err != nil || n < 1 || n > 65535 {
			return "", bad
		}
	}
	if u.Scheme == "http" {
		ip := net.ParseIP(host)
		if host != "localhost" && (ip == nil || !ip.IsLoopback()) {
			return "", bad
		}
	}
	return strings.TrimSuffix(raw, "/"), nil
}

func (c *Client) Profile(ctx context.Context) (Result[Profile], error) {
	var result Result[Profile]
	raw, err := c.get(ctx, "/api/v1/actors/me", "")
	if err != nil {
		return result, err
	}
	value := Profile{Domains: []string{"contributor"}, AdminRoles: []string{}, ProjectRoleGrants: []string{}}
	err = decode(raw, &value, []string{
		"actor_profile_id", "actor_kind", "status", "display_name", "contact_email",
		"created_at", "updated_at", "last_seen_at",
	}, []string{"domains", "admin_roles", "project_role_grants"})
	_, validActorID := uuidIdentity(value.ActorProfileID)
	if err != nil || !validActorID || value.ActorKind != "human" || !validStatus(value.Status) ||
		len(value.Domains) != 1 || value.Domains[0] != "contributor" ||
		value.AdminRoles == nil || value.ProjectRoleGrants == nil ||
		!validTime(value.CreatedAt) || !validTime(value.UpdatedAt) ||
		(value.LastSeenAt != nil && !validTime(*value.LastSeenAt)) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[Profile]{Raw: raw, Value: value}, nil
}

func (c *Client) AuthorizationContext(ctx context.Context, projectID string) (Result[AuthorizationContext], error) {
	var result Result[AuthorizationContext]
	if projectID == "" || !utf8.ValidString(projectID) || utf8.RuneCountInString(projectID) > 100 || strings.ContainsRune(projectID, '\x00') {
		return result, errors.New("PROJECT_ID must be a nonempty project selector of at most 100 characters")
	}
	query := url.Values{"project_id": {projectID}}.Encode()
	raw, err := c.get(ctx, "/api/v1/actors/me/authorization-context", query)
	if err != nil {
		return result, err
	}
	var value AuthorizationContext
	err = decode(raw, &value, []string{
		"actor_profile_id", "status", "project_id", "admin_roles", "project_roles", "effective_action_ids",
	}, []string{"admin_roles", "project_roles", "effective_action_ids"})
	_, validActorID := uuidIdentity(value.ActorProfileID)
	returnedProject, validProjectID := uuidIdentity(value.ProjectID)
	selectedProject, validSelector := uuidIdentity(projectID)
	if err != nil || !validActorID || !validProjectID || !validSelector ||
		returnedProject != selectedProject || !validStatus(value.Status) ||
		value.AdminRoles == nil || value.ProjectRoles == nil || value.EffectiveActionIDs == nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[AuthorizationContext]{Raw: raw, Value: value}, nil
}

func validStatus(value string) bool {
	return value == "active" || value == "suspended" || value == "deactivated"
}

func validTime(value string) bool {
	_, err := time.Parse(time.RFC3339Nano, value)
	return err == nil
}

// Compare UUID values, not selector spelling. Keep the original selector on the
// wire; UUID normalization mirrors the backend's UUID selector resolution.
func uuidIdentity(value string) ([16]byte, bool) {
	var identity [16]byte
	value = strings.TrimPrefix(value, "urn:uuid:")
	if len(value) >= 2 && value[0] == '{' && value[len(value)-1] == '}' {
		value = value[1 : len(value)-1]
	}
	value = strings.ReplaceAll(value, "-", "")
	if len(value) != 32 {
		return identity, false
	}
	_, err := hex.Decode(identity[:], []byte(value))
	return identity, err == nil
}

func decode(raw json.RawMessage, value any, required, stringArrays []string) error {
	var fields map[string]json.RawMessage
	if err := jsonv2.Unmarshal(raw, &fields); err != nil || fields == nil {
		return errors.New("invalid object")
	}
	for _, key := range required {
		if _, ok := fields[key]; !ok {
			return errors.New("missing field")
		}
	}
	// JSON null decodes to a Go string's zero value. Inspect array members
	// explicitly so a malformed authority fact cannot become a success object.
	for _, key := range stringArrays {
		field, present := fields[key]
		if !present {
			continue // Optional profile arrays retain their schema defaults.
		}
		var members []*string
		if err := jsonv2.Unmarshal(field, &members); err != nil || members == nil {
			return errors.New("invalid string array")
		}
		for _, member := range members {
			if member == nil {
				return errors.New("null string array member")
			}
		}
	}
	return jsonv2.Unmarshal(raw, value, jsonv2.RejectUnknownMembers(true))
}

func (c *Client) safeMetadata(value string) bool {
	return !strings.Contains(strings.ToLower(value), strings.ToLower(c.token))
}

func (c *Client) get(ctx context.Context, path, query string) (json.RawMessage, error) {
	target := c.origin + path
	if query != "" {
		target += "?" + query
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
	if err != nil {
		return nil, &Failure{Code: "invalid_request"}
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Accept-Encoding", "identity")
	response, err := c.http.Do(req)
	if err != nil {
		return nil, &Failure{Code: "service_unavailable"}
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, maxResponseBytes+1))
	if err != nil || len(body) > maxResponseBytes {
		return nil, &Failure{Code: "invalid_api_response", Status: response.StatusCode}
	}
	correlation := response.Header.Get("X-Correlation-ID")
	if !safeCorrelation.MatchString(correlation) || !c.safeMetadata(correlation) {
		correlation = response.Header.Get("X-Request-ID")
		if !safeCorrelation.MatchString(correlation) || !c.safeMetadata(correlation) {
			correlation = ""
		}
	}
	if response.StatusCode != http.StatusOK {
		code := "api_error"
		if response.StatusCode >= 300 && response.StatusCode < 400 {
			code = "redirect_refused"
		} else {
			var envelope struct {
				Error struct {
					Code string `json:"code"`
				} `json:"error"`
			}
			if json.Unmarshal(body, &envelope) == nil && safeCode.MatchString(envelope.Error.Code) && c.safeMetadata(envelope.Error.Code) {
				code = envelope.Error.Code
			}
		}
		return nil, &Failure{Code: code, Status: response.StatusCode, CorrelationID: correlation}
	}
	mediaType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" || !jsontext.Value(body).IsValid() {
		return nil, &Failure{Code: "invalid_api_response", Status: response.StatusCode, CorrelationID: correlation}
	}
	return json.RawMessage(body), nil
}
