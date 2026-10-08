package api

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"encoding/json/jsontext"
	"errors"
	"io"
	"mime"
	"net/http"
	"net/url"
	"os"
)

// MaxGuideDocumentBytes is ART's hard transfer ceiling, not the configured
// project/document allowance. Workstream may enforce a smaller limit.
const MaxGuideDocumentBytes = 512 * 1024 * 1024

type GuideUploadReceipt struct {
	DocumentID string `json:"document_id"`
	SHA256     string `json:"sha256"`
	ByteCount  int64  `json:"byte_count"`
	Status     string `json:"status"`
	Replayed   bool   `json:"replayed"`
}

// UploadGuideDocument sends the exact original once. Its receipt proves only
// stored bytes, not setup completion, policy approval or guide activation.
func (c *Client) UploadGuideDocument(ctx context.Context, project, guide, document string, source *os.File, size int64, mediaType, key string) (Result[GuideUploadReceipt], error) {
	var result Result[GuideUploadReceipt]
	if !validUUID(project) || !validUUID(guide) || !validUUID(document) || !validUUID(key) ||
		len(project) > 100 || len(guide) > 100 || len(document) > 100 || len(key) > 100 || !guideMediaType(mediaType) {
		return result, errors.New("upload selectors and --idempotency-key must be UUIDs; use a declared guide media type")
	}
	if source == nil || size <= 0 || size > MaxGuideDocumentBytes {
		return result, errors.New("upload requires a nonempty bounded original")
	}
	initial, err := source.Stat()
	if err != nil || !initial.Mode().IsRegular() || initial.Size() != size {
		return result, errors.New("cannot read unchanged original")
	}
	expectedHash, err := guideOriginalHash(source, size)
	if err != nil {
		return result, err
	}
	path := "/api/v1/projects/" + url.PathEscape(project) + "/guides/" + url.PathEscape(guide) +
		"/documents/" + url.PathEscape(document) + "/content"
	response, err := c.openBodyRequest(ctx, c.guideHTTP, http.MethodPost, path, "",
		io.NewSectionReader(source, 0, size), size, key, "application/json", mediaType)
	if err != nil {
		return result, guideUploadFailure(err)
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(response.Body, maxResponseBytes+1))
	invalid := &Failure{Code: "invalid_api_response", Status: response.StatusCode, OutcomeUnknown: true}
	if err != nil || len(raw) > maxResponseBytes {
		return result, guideUploadFailure(invalid)
	}
	if response.StatusCode != http.StatusAccepted {
		return result, guideUploadFailure(c.responseFailure(http.MethodPost, response, raw))
	}
	responseType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || responseType != "application/json" || !jsontext.Value(raw).IsValid() ||
		response.Header.Get("Content-Encoding") != "" && response.Header.Get("Content-Encoding") != "identity" {
		return result, guideUploadFailure(invalid)
	}
	var value GuideUploadReceipt
	_, err = contextObject(json.RawMessage(raw), &value,
		[]string{"document_id", "sha256", "byte_count", "status", "replayed"}, nil)
	if err != nil || !sameUUID(value.DocumentID, document) || value.SHA256 != expectedHash || value.ByteCount != size || value.Status == "" {
		return result, guideUploadFailure(invalid)
	}
	if value.Status != "document_stored" && value.Status != "object_confirmed" {
		return result, guideUploadFailure(&Failure{Code: "guide_document_upload_unconfirmed", Status: response.StatusCode, OutcomeUnknown: true})
	}
	// A receipt can confirm the initial prefix even if the caller appended to or
	// rewrote the local file. Re-read the whole bounded original before success.
	// Section readers use independent offsets; an early response cannot race a
	// shared Seek with the HTTP transport's body reader.
	finalHash, hashErr := guideOriginalHash(source, size)
	final, statErr := source.Stat()
	if hashErr != nil || statErr != nil || final.Size() != initial.Size() ||
		!final.ModTime().Equal(initial.ModTime()) || finalHash != expectedHash {
		return result, guideUploadFailure(&Failure{Code: "guide_document_upload_source_changed", Status: response.StatusCode, OutcomeUnknown: true})
	}
	return Result[GuideUploadReceipt]{Raw: json.RawMessage(raw), Value: value}, nil
}

func guideOriginalHash(source *os.File, size int64) (string, error) {
	digest := sha256.New()
	count, err := io.Copy(digest, io.NewSectionReader(source, 0, size+1))
	if err != nil || count != size {
		return "", errors.New("cannot read unchanged original")
	}
	return "sha256:" + hex.EncodeToString(digest.Sum(nil)), nil
}

func guideUploadFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "guide upload outcome unknown; replay only the unchanged selectors, original bytes, media type and idempotency key"
	}
	return err
}
