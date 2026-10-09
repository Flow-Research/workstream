package api

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"strings"
)

// TaskGuideDocument contains only the server's exact locked original projection.
type TaskGuideDocument struct {
	DocumentID    string `json:"document_id"`
	Order         int64  `json:"order"`
	Label         string `json:"label"`
	MediaType     string `json:"media_type"`
	ByteCount     int64  `json:"byte_count"`
	SHA256        string `json:"sha256"`
	ReadReference string `json:"read_reference"`
}

func guideDocumentPath(taskID, documentID string) string {
	return "/api/v1/tasks/" + canonicalUUID(taskID) + "/guide/documents/" + canonicalUUID(documentID) + "/content"
}

func canonicalUUID(value string) string {
	id, _ := uuidIdentity(value)
	return fmt.Sprintf("%x-%x-%x-%x-%x", id[0:4], id[4:6], id[6:8], id[8:10], id[10:16])
}

func (d TaskGuideDocument) Filename() string {
	return canonicalUUID(d.DocumentID) + d.Extension()
}

func (d TaskGuideDocument) Extension() string {
	switch d.MediaType {
	case "application/pdf":
		return ".pdf"
	case "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
		return ".docx"
	case "application/vnd.openxmlformats-officedocument.presentationml.presentation":
		return ".pptx"
	case "text/markdown":
		return ".md"
	default:
		return ""
	}
}

func validateGuideDocuments(raw json.RawMessage, documents []TaskGuideDocument, taskID string, assigned bool) error {
	var entries []json.RawMessage
	if jsonv2.Unmarshal(raw, &entries) != nil || entries == nil || len(entries) != len(documents) || (!assigned && len(entries) != 0) {
		return errors.New("invalid guide documents")
	}
	seen := make(map[string]bool)
	var previous int64 = -1
	for index, entry := range entries {
		d := documents[index]
		if _, err := contextObject(entry, &d, []string{"document_id", "order", "label", "media_type", "byte_count", "sha256", "read_reference"}, nil); err != nil ||
			!validUUID(d.DocumentID) || seen[canonicalUUID(d.DocumentID)] || d.Order <= previous ||
			strings.TrimSpace(d.Label) == "" || d.Extension() == "" || d.ByteCount <= 0 || d.ByteCount > MaxGuideDocumentBytes ||
			!contextPolicyDigest.MatchString(d.SHA256) || d.ReadReference != guideDocumentPath(taskID, d.DocumentID) {
			return errors.New("invalid guide document")
		}
		seen[canonicalUUID(d.DocumentID)] = true
		previous = d.Order
	}
	return nil
}

// DownloadGuideDocument always constructs the same-origin path itself. The
// caller writes privately and publishes only after this verifies all bytes.
func (c *Client) DownloadGuideDocument(ctx context.Context, taskID string, document TaskGuideDocument, target io.Writer) error {
	if !validUUID(taskID) || !validUUID(document.DocumentID) || document.Extension() == "" ||
		document.ByteCount <= 0 || document.ByteCount > MaxGuideDocumentBytes || !contextPolicyDigest.MatchString(document.SHA256) ||
		document.ReadReference != guideDocumentPath(taskID, document.DocumentID) {
		return &Failure{Code: "invalid_api_response"}
	}
	response, err := c.openRequest(ctx, c.guideHTTP, http.MethodGet, guideDocumentPath(taskID, document.DocumentID), "", nil, "", document.MediaType)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		body, err := io.ReadAll(io.LimitReader(response.Body, maxResponseBytes+1))
		if err != nil || len(body) > maxResponseBytes {
			return &Failure{Code: "invalid_api_response", Status: response.StatusCode}
		}
		return c.responseFailure(http.MethodGet, response, body)
	}
	mediaType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || mediaType != document.MediaType || response.Header.Get("Content-Encoding") != "" && response.Header.Get("Content-Encoding") != "identity" ||
		response.ContentLength >= 0 && response.ContentLength != document.ByteCount {
		return &Failure{Code: "guide_document_integrity_mismatch"}
	}
	digest := sha256.New()
	count, err := io.Copy(io.MultiWriter(target, digest), io.LimitReader(response.Body, document.ByteCount+1))
	if err != nil {
		return &Failure{Code: "guide_document_download_failed"}
	}
	if count != document.ByteCount || "sha256:"+hex.EncodeToString(digest.Sum(nil)) != document.SHA256 {
		return &Failure{Code: "guide_document_integrity_mismatch"}
	}
	return nil
}
