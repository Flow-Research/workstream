package api

import (
	"bytes"
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
const maxUpdateBytes = 8 * 1024

var bearerValue = regexp.MustCompile(`^[A-Za-z0-9\-._~+/]+=*$`)
var safeCode = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_]{0,99}$`)
var safeCorrelation = regexp.MustCompile(`^[0-9a-fA-F-]{36}$`)

// Failure contains only bounded, public error metadata. It never includes a
// credential, URL, response body, or transport exception.
type Failure struct {
	Code           string `json:"code"`
	Status         int    `json:"status,omitempty"`
	CorrelationID  string `json:"correlation_id,omitempty"`
	OutcomeUnknown bool   `json:"outcome_unknown,omitempty"`
	RecoveryHint   string `json:"-"`
}

func (f *Failure) Error() string {
	if f.OutcomeUnknown {
		known := *f
		known.OutcomeUnknown = false
		hint := f.RecoveryHint
		if hint == "" {
			hint = "update outcome unknown; read whoami before retrying"
		}
		return known.Error() + "; " + hint
	}
	if f.CorrelationID != "" {
		return fmt.Sprintf("%s (HTTP %d; correlation %s)", f.Code, f.Status, f.CorrelationID)
	}
	if f.Status != 0 {
		return fmt.Sprintf("%s (HTTP %d)", f.Code, f.Status)
	}
	return f.Code
}

type Client struct {
	origin    string
	token     string
	http      *http.Client
	guideHTTP *http.Client
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

// ProfileUpdate distinguishes absent fields from explicit clearing. Validation
// of text and authority remains with the public Workstream API.
type ProfileUpdate struct {
	DisplayName       *string
	ContactEmail      *string
	ClearDisplayName  bool
	ClearContactEmail bool
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
	client := &http.Client{
		Transport: transport,
		Timeout:   12 * time.Second,
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	// Binary guide transfers include server-side whole-original verification
	// up to 512 MiB. Keep them bounded without applying the JSON deadline.
	guideTransport := transport.Clone()
	guideTransport.ResponseHeaderTimeout = 2 * time.Minute
	guideHTTP := *client
	guideHTTP.Transport = guideTransport
	guideHTTP.Timeout = 10 * time.Minute
	return &Client{origin: normalized, token: token, http: client, guideHTTP: &guideHTTP}, nil
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
	raw, err := c.request(ctx, http.MethodGet, "/api/v1/actors/me", "", nil)
	if err != nil {
		return result, err
	}
	return decodeProfile(raw)
}

func decodeProfile(raw json.RawMessage) (Result[Profile], error) {
	var result Result[Profile]
	value := Profile{Domains: []string{"contributor"}, AdminRoles: []string{}, ProjectRoleGrants: []string{}}
	err := decode(raw, &value, []string{
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

func (c *Client) UpdateProfile(ctx context.Context, update ProfileUpdate) (Result[Profile], error) {
	var result Result[Profile]
	if (update.DisplayName != nil && !utf8.ValidString(*update.DisplayName)) ||
		(update.ContactEmail != nil && !utf8.ValidString(*update.ContactEmail)) {
		return result, errors.New("profile fields must be valid UTF-8")
	}
	if (update.DisplayName != nil && update.ClearDisplayName) ||
		(update.ContactEmail != nil && update.ClearContactEmail) {
		return result, errors.New("cannot set and clear the same profile field")
	}
	fields := make(map[string]*string)
	if update.DisplayName != nil || update.ClearDisplayName {
		fields["display_name"] = update.DisplayName
	}
	if update.ContactEmail != nil || update.ClearContactEmail {
		fields["contact_email"] = update.ContactEmail
	}
	if len(fields) == 0 {
		return result, errors.New("select at least one profile field")
	}
	body, err := json.Marshal(fields)
	if err != nil || len(body) > maxUpdateBytes {
		return result, errors.New("profile update exceeds the request size limit")
	}
	raw, err := c.request(ctx, http.MethodPatch, "/api/v1/actors/me", "", body)
	if err != nil {
		return result, err
	}
	result, err = decodeProfile(raw)
	if err != nil {
		var failure *Failure
		if errors.As(err, &failure) {
			// A malformed successful reply cannot establish the write outcome.
			failure.OutcomeUnknown = true
		}
	}
	return result, err
}

func (c *Client) AuthorizationContext(ctx context.Context, projectID string) (Result[AuthorizationContext], error) {
	var result Result[AuthorizationContext]
	if projectID == "" || !utf8.ValidString(projectID) || utf8.RuneCountInString(projectID) > 100 || strings.ContainsRune(projectID, '\x00') {
		return result, errors.New("PROJECT_ID must be a nonempty project selector of at most 100 characters")
	}
	query := url.Values{"project_id": {projectID}}.Encode()
	raw, err := c.request(ctx, http.MethodGet, "/api/v1/actors/me/authorization-context", query, nil)
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

func (c *Client) request(ctx context.Context, method, path, query string, body []byte) (json.RawMessage, error) {
	return c.requestWithKey(ctx, method, path, query, body, "", http.StatusOK)
}

func (c *Client) requestWithKey(ctx context.Context, method, path, query string, body []byte, key string, successStatus int) (json.RawMessage, error) {
	return c.requestWithResponseLimit(ctx, method, path, query, body, key, successStatus, maxResponseBytes)
}

func (c *Client) requestWithResponseLimit(ctx context.Context, method, path, query string, body []byte, key string, successStatus, responseLimit int) (json.RawMessage, error) {
	mutation := method == http.MethodPatch || method == http.MethodPost
	response, err := c.openRequest(ctx, c.http, method, path, query, body, key, "application/json")
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	responseBody, err := io.ReadAll(io.LimitReader(response.Body, int64(responseLimit)+1))
	if err != nil || len(responseBody) > responseLimit {
		return nil, &Failure{Code: "invalid_api_response", Status: response.StatusCode, OutcomeUnknown: mutation}
	}
	if response.StatusCode != successStatus {
		return nil, c.responseFailure(method, response, responseBody)
	}
	mediaType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" || !jsontext.Value(responseBody).IsValid() {
		return nil, &Failure{Code: "invalid_api_response", Status: response.StatusCode, CorrelationID: c.responseCorrelation(response), OutcomeUnknown: mutation}
	}
	return json.RawMessage(responseBody), nil
}

func (c *Client) openRequest(ctx context.Context, requestClient *http.Client, method, path, query string, body []byte, key, accept string) (*http.Response, error) {
	var reader io.Reader
	contentType := ""
	if body != nil {
		reader = bytes.NewReader(body)
		contentType = "application/json"
	}
	return c.openBodyRequest(ctx, requestClient, method, path, query, reader, int64(len(body)), key, accept, contentType)
}

func (c *Client) openBodyRequest(ctx context.Context, requestClient *http.Client, method, path, query string, reader io.Reader, length int64, key, accept, contentType string) (*http.Response, error) {
	mutation := method == http.MethodPatch || method == http.MethodPost
	target := c.origin + path
	if query != "" {
		target += "?" + query
	}
	req, err := http.NewRequestWithContext(ctx, method, target, reader)
	if err != nil {
		return nil, &Failure{Code: "invalid_request"}
	}
	if mutation {
		// NewRequest makes bytes.Reader bodies rewindable. Disable transport
		// replay after HTTP/2 GOAWAY/REFUSED_STREAM (or HTTP/1 connection
		// failure); write retries belong to the caller, even with a retry key.
		req.GetBody = nil
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Accept", accept)
	req.Header.Set("Accept-Encoding", "identity")
	if key != "" {
		req.Header.Set("Idempotency-Key", key)
	}
	if reader != nil {
		req.ContentLength = length
		req.Header.Set("Content-Type", contentType)
	}
	response, err := requestClient.Do(req)
	if err != nil {
		return nil, &Failure{Code: "service_unavailable", OutcomeUnknown: mutation}
	}
	return response, nil
}

func (c *Client) responseCorrelation(response *http.Response) string {
	correlation := response.Header.Get("X-Correlation-ID")
	if !safeCorrelation.MatchString(correlation) || !c.safeMetadata(correlation) {
		correlation = response.Header.Get("X-Request-ID")
		if !safeCorrelation.MatchString(correlation) || !c.safeMetadata(correlation) {
			correlation = ""
		}
	}
	return correlation
}

func (c *Client) responseFailure(method string, response *http.Response, responseBody []byte) error {
	mutation := method == http.MethodPatch || method == http.MethodPost
	correlation := c.responseCorrelation(response)
	code := "api_error"
	knownEnvelope := false
	if response.StatusCode >= 300 && response.StatusCode < 400 {
		code = "redirect_refused"
	} else {
		var envelope struct {
			Error struct {
				Code string `json:"code"`
			} `json:"error"`
		}
		knownEnvelope = jsonv2.Unmarshal(responseBody, &envelope) == nil && envelope.Error.Code != ""
		if knownEnvelope && safeCode.MatchString(envelope.Error.Code) && c.safeMetadata(envelope.Error.Code) {
			code = envelope.Error.Code
		}
	}
	if method == http.MethodPost {
		knownEnvelope = canonicalMutationError(responseBody, response.Header.Get("Content-Type"))
	}
	// A complete API 4xx envelope is a known denial, independent of code
	// spelling/redaction. A gateway reply without it cannot prove rollback.
	return &Failure{Code: code, Status: response.StatusCode, CorrelationID: correlation,
		OutcomeUnknown: mutation && (response.StatusCode < 400 || response.StatusCode >= 500 || !knownEnvelope)}
}

// POST writes need a complete public ApiError, not a gateway's code-shaped
// JSON. Profile PATCH deliberately retains its existing response contract.
func canonicalMutationError(raw []byte, contentType string) bool {
	mediaType, _, err := mime.ParseMediaType(contentType)
	if err != nil || mediaType != "application/json" {
		return false
	}
	var envelope struct {
		Error  json.RawMessage `json:"error"`
		Detail json.RawMessage `json:"detail"`
	}
	if decode(raw, &envelope, []string{"error"}, nil) != nil {
		return false
	}
	var value struct {
		Code          *string                    `json:"code"`
		Message       *string                    `json:"message"`
		Details       map[string]json.RawMessage `json:"details"`
		CorrelationID *string                    `json:"correlation_id"`
		Retryable     *bool                      `json:"retryable"`
	}
	return decode(envelope.Error, &value, []string{"code", "message", "details", "correlation_id", "retryable"}, nil) == nil &&
		value.Code != nil && *value.Code != "" && value.Message != nil && value.Details != nil &&
		value.CorrelationID != nil && validUUID(*value.CorrelationID) && value.Retryable != nil
}
