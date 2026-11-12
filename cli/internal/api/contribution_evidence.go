package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"mime"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"
)

const maxContributionBytes = 32 * 1024 * 1024
const maxContributionPages = 100
const maxContributionRecords = 100_000
const contributionPageLimit = 1_000

type ContributionFilters struct {
	Project, Type, From, Before string
}

type contributionPage struct {
	exportedAt string
	items      []ContributionRecord
	rawItems   []json.RawMessage
	nextCursor *string
	csvHeader  []byte
	csvData    []byte
}

type ContributionRecord struct {
	ID                 string              `json:"contribution_id"`
	Project            string              `json:"project_id"`
	Task               string              `json:"task_id"`
	Submission         string              `json:"submission_id"`
	Contributor        string              `json:"contributor_id"`
	DisplayName        *string             `json:"contributor_display_name"`
	Type               string              `json:"contribution_type"`
	Review             *string             `json:"source_review_id"`
	Lease              *string             `json:"source_review_lease_id"`
	Acceptance         *string             `json:"source_final_acceptance_id"`
	Assignment         *string             `json:"source_task_assignment_id"`
	ArtifactHash       string              `json:"artifact_hash"`
	Policy             string              `json:"contribution_policy_version_id"`
	PolicyNumber       *big.Int            `json:"policy_version_number"`
	RecordedAt         string              `json:"recorded_at"`
	AcceptedAt         *string             `json:"accepted_at"`
	AcceptanceSource   *string             `json:"acceptance_source"`
	AcceptanceReview   *string             `json:"acceptance_review_id"`
	AcceptanceManifest *string             `json:"acceptance_routing_manifest_id"`
	TaskTitle          string              `json:"task_title"`
	SourceType         string              `json:"source_type"`
	SourceRef          *string             `json:"source_ref"`
	ExternalTask       *string             `json:"external_task_id"`
	Awards             []ContributionAward `json:"awards"`
}

type ContributionAward struct {
	ID         string `json:"award_id"`
	Definition string `json:"award_definition_id"`
	Instrument string `json:"instrument"`
	Unit       string `json:"unit"`
	Quantity   string `json:"quantity"`
}

var contributionRequired = []string{"contribution_id", "project_id", "task_id", "submission_id", "contributor_id", "contribution_type", "artifact_hash", "contribution_policy_version_id", "policy_version_number", "recorded_at", "task_title", "source_type", "awards"}
var contributionNullable = []string{"contributor_display_name", "source_review_id", "source_review_lease_id", "source_final_acceptance_id", "source_task_assignment_id", "accepted_at", "acceptance_source", "acceptance_review_id", "acceptance_routing_manifest_id", "source_ref", "external_task_id"}
var contributionQuantity = regexp.MustCompile(`^[0-9]+(?:\.[0-9]+)?$`)

// The backend owns selection and authority. Normalize time precision to the
// public Python datetime contract before sending and checking the same filters.
func (f *ContributionFilters) query(projectScope, csv bool) (string, string, error) {
	bad := errors.New("select a valid project UUID, contribution type and aware RFC3339 interval")
	if (projectScope && f.Project == "") || (f.Project != "" && (!validUUID(f.Project) || len(f.Project) > 100)) ||
		(f.Type != "" && f.Type != "accepted_submission" && f.Type != "completed_review") {
		return "", "", bad
	}
	for _, value := range []*string{&f.From, &f.Before} {
		if *value != "" {
			t, err := time.Parse(time.RFC3339Nano, *value)
			if err != nil {
				return "", "", bad
			}
			*value = t.UTC().Truncate(time.Microsecond).Format(time.RFC3339Nano)
		}
	}
	if f.From != "" && f.Before != "" {
		start, _ := time.Parse(time.RFC3339Nano, f.From)
		end, _ := time.Parse(time.RFC3339Nano, f.Before)
		if !start.Before(end) {
			return "", "", bad
		}
	}
	path := "/api/v1/actors/me/contributions"
	values := url.Values{"format": {"json"}}
	if projectScope {
		path = "/api/v1/projects/" + url.PathEscape(f.Project) + "/contributions/export"
	} else if f.Project != "" {
		values.Set("project_id", f.Project)
	}
	if csv {
		values.Set("format", "csv")
	}
	for key, value := range map[string]string{"contribution_type": f.Type, "recorded_from": f.From, "recorded_before": f.Before} {
		if value != "" {
			values.Set(key, value)
		}
	}
	return path, values.Encode(), nil
}

func (c *Client) Contributions(
	ctx context.Context, projectScope bool, filters ContributionFilters, destination io.Writer,
) error {
	return c.writeContributions(ctx, projectScope, filters, false, destination)
}

func (c *Client) ContributionCSV(
	ctx context.Context, projectScope bool, filters ContributionFilters, destination io.Writer,
) error {
	return c.writeContributions(ctx, projectScope, filters, true, destination)
}

func (c *Client) writeContributions(
	ctx context.Context, projectScope bool, filters ContributionFilters, csv bool,
	destination io.Writer,
) error {
	if destination == nil {
		return errors.New("contribution export destination is required")
	}
	path, rawQuery, err := filters.query(projectScope, csv)
	if err != nil {
		return err
	}
	query, err := url.ParseQuery(rawQuery)
	if err != nil {
		return errors.New("invalid contribution export query")
	}
	query.Set("limit", "1000")

	seenRecords := make(map[[16]byte]bool)
	seenAwards := make(map[[16]byte]bool)
	seenCursors := make(map[string]bool)
	var firstExportedAt string
	var csvHeader []byte
	var previousTime time.Time
	var previousID [16]byte
	total := 0

	for pageNumber := 0; pageNumber < maxContributionPages; pageNumber++ {
		page, err := c.contributionPage(ctx, path, query.Encode(), filters, csv)
		if err != nil {
			return err
		}
		updatedTotal, valid := advanceContributionTraversal(
			pageNumber, total, len(page.items), page.nextCursor != nil,
		)
		if !valid {
			return &Failure{Code: "invalid_api_response"}
		}
		for _, item := range page.items {
			stamp, stampErr := time.Parse(time.RFC3339Nano, item.RecordedAt)
			id, valid := uuidIdentity(item.ID)
			if stampErr != nil || !valid || seenRecords[id] ||
				(total > 0 && (stamp.Before(previousTime) ||
					(stamp.Equal(previousTime) && bytes.Compare(id[:], previousID[:]) <= 0))) {
				return &Failure{Code: "invalid_api_response"}
			}
			seenRecords[id], previousTime, previousID = true, stamp, id
			for _, award := range item.Awards {
				awardID, valid := uuidIdentity(award.ID)
				if !valid || seenAwards[awardID] {
					return &Failure{Code: "invalid_api_response"}
				}
				seenAwards[awardID] = true
			}
		}
		total = updatedTotal

		if pageNumber == 0 {
			firstExportedAt = page.exportedAt
			if csv {
				csvHeader = bytes.Clone(page.csvHeader)
				if err := writeContributionBytes(destination, csvHeader); err != nil {
					return err
				}
			} else {
				exportedAt, marshalErr := json.Marshal(firstExportedAt)
				if marshalErr != nil {
					return &Failure{Code: "invalid_api_response"}
				}
				if err := writeContributionBytes(destination, append(append(
					[]byte(`{"exported_at":`), exportedAt...), []byte(`,"items":[`)...)); err != nil {
					return err
				}
			}
		} else if csv && !bytes.Equal(page.csvHeader, csvHeader) {
			return &Failure{Code: "invalid_api_response"}
		}

		if csv {
			if err := writeContributionBytes(destination, page.csvData); err != nil {
				return err
			}
		} else {
			for index, item := range page.rawItems {
				if total-len(page.items)+index > 0 {
					if err := writeContributionBytes(destination, []byte(",")); err != nil {
						return err
					}
				}
				if err := writeContributionBytes(destination, item); err != nil {
					return err
				}
			}
		}

		if page.nextCursor == nil {
			if !csv {
				return writeContributionBytes(destination, []byte("]}"))
			}
			return nil
		}
		if pageNumber == maxContributionPages-1 || seenCursors[*page.nextCursor] {
			return &Failure{Code: "invalid_api_response"}
		}
		seenCursors[*page.nextCursor] = true
		query.Set("cursor", *page.nextCursor)
	}
	return &Failure{Code: "invalid_api_response"}
}

func (c *Client) contributionPage(
	ctx context.Context, path, query string, filters ContributionFilters, csv bool,
) (contributionPage, error) {
	if csv {
		return c.contributionCSVPage(ctx, path, query, filters)
	}
	var page contributionPage
	raw, err := c.requestWithResponseLimit(
		ctx, http.MethodGet, path, query, nil, "", http.StatusOK, maxContributionBytes,
	)
	if err != nil {
		return page, err
	}
	var envelope struct {
		ExportedAt string          `json:"exported_at"`
		Items      json.RawMessage `json:"items"`
		NextCursor *string         `json:"next_cursor"`
	}
	fields, err := contextObject(raw, &envelope, []string{"exported_at", "items"}, nil)
	if err != nil || !requiredNullable(fields, "next_cursor") ||
		!validTime(envelope.ExportedAt) || !c.safeMutationResponse(raw) ||
		(envelope.NextCursor != nil && !c.validContributionCursor(*envelope.NextCursor)) ||
		validateContributionRecords(fields["items"], filters) != nil {
		return page, &Failure{Code: "invalid_api_response"}
	}
	if err := json.Unmarshal(fields["items"], &page.items); err != nil || page.items == nil {
		return contributionPage{}, &Failure{Code: "invalid_api_response"}
	}
	if err := json.Unmarshal(fields["items"], &page.rawItems); err != nil || page.rawItems == nil {
		return contributionPage{}, &Failure{Code: "invalid_api_response"}
	}
	page.exportedAt, page.nextCursor = envelope.ExportedAt, envelope.NextCursor
	return page, nil
}

func (c *Client) contributionCSVPage(
	ctx context.Context, path, query string, filters ContributionFilters,
) (contributionPage, error) {
	var page contributionPage
	response, err := c.openRequest(ctx, c.http, http.MethodGet, path, query, nil, "", "text/csv")
	if err != nil {
		return page, err
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, maxContributionBytes+1))
	if err != nil || len(body) > maxContributionBytes {
		return page, &Failure{Code: "invalid_api_response"}
	}
	if response.StatusCode != http.StatusOK {
		return page, c.responseFailure(http.MethodGet, response, body)
	}
	mediaType, params, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	cursors := response.Header.Values("X-Workstream-Next-Cursor")
	if err != nil || mediaType != "text/csv" ||
		(params["charset"] != "" && !strings.EqualFold(params["charset"], "utf-8")) ||
		len(cursors) > 1 {
		return page, &Failure{Code: "invalid_api_response"}
	}
	if len(cursors) == 1 {
		if !c.validContributionCursor(cursors[0]) {
			return page, &Failure{Code: "invalid_api_response"}
		}
		page.nextCursor = &cursors[0]
	}
	items, headerEnd, err := c.decodeContributionCSV(body, filters)
	if err != nil {
		return contributionPage{}, &Failure{Code: "invalid_api_response"}
	}
	page.items = items
	page.csvHeader = body[:headerEnd]
	page.csvData = body[headerEnd:]
	return page, nil
}

func (c *Client) validContributionCursor(value string) bool {
	return value != "" && utf8.ValidString(value) && utf8.RuneCountInString(value) <= 512 &&
		c.safeMetadata(value)
}

func advanceContributionTraversal(
	pageNumber, total, pageItems int, continues bool,
) (int, bool) {
	if pageNumber < 0 || pageNumber >= maxContributionPages || total < 0 || pageItems < 0 ||
		(pageNumber > 0 && pageItems == 0) || pageItems > maxContributionRecords-total ||
		(continues && (pageItems != contributionPageLimit || pageNumber == maxContributionPages-1)) {
		return total, false
	}
	return total + pageItems, true
}

func writeContributionBytes(destination io.Writer, value []byte) error {
	written, err := destination.Write(value)
	if err != nil {
		return err
	}
	if written != len(value) {
		return io.ErrShortWrite
	}
	return nil
}

func validateContributionRecords(raw json.RawMessage, filters ContributionFilters) error {
	bad := errors.New("invalid contribution evidence")
	var records []json.RawMessage
	if err := json.Unmarshal(raw, &records); err != nil || records == nil || len(records) > 1000 {
		return bad
	}
	seen, awards := make(map[[16]byte]bool), make(map[[16]byte]bool)
	var previousTime time.Time
	var previousID [16]byte
	for _, rawRecord := range records {
		var r ContributionRecord
		fields, err := contextObject(rawRecord, &r, contributionRequired, nil)
		if err != nil || !requiredNullable(fields, contributionNullable...) ||
			(filters.Project != "" && !sameUUID(r.Project, filters.Project)) || (filters.Type != "" && r.Type != filters.Type) ||
			r.PolicyNumber == nil || r.PolicyNumber.Sign() <= 0 || !contextPolicyDigest.MatchString(r.ArtifactHash) {
			return bad
		}
		for _, value := range []string{r.ID, r.Project, r.Task, r.Submission, r.Contributor, r.Policy} {
			if !validUUID(value) {
				return bad
			}
		}
		for _, value := range []*string{r.Review, r.Lease, r.Acceptance, r.Assignment, r.AcceptanceReview, r.AcceptanceManifest} {
			if value != nil && !validUUID(*value) {
				return bad
			}
		}
		accepted := r.Type == "accepted_submission"
		if (!accepted && r.Type != "completed_review") || (r.Review != nil) != !accepted || (r.Lease != nil) != !accepted ||
			(r.Acceptance != nil) != accepted || (r.Assignment != nil) != accepted || (r.AcceptedAt != nil) != accepted || (r.AcceptanceSource != nil) != accepted {
			return bad
		}
		if accepted {
			if !validTime(*r.AcceptedAt) || (*r.AcceptanceSource != "human_review" && *r.AcceptanceSource != "task_post_submit_route") ||
				(r.AcceptanceReview != nil) != (*r.AcceptanceSource == "human_review") || (r.AcceptanceManifest != nil) != (*r.AcceptanceSource == "task_post_submit_route") {
				return bad
			}
		} else if r.AcceptanceReview != nil || r.AcceptanceManifest != nil {
			return bad
		}
		stamp, err := time.Parse(time.RFC3339Nano, r.RecordedAt)
		id, _ := uuidIdentity(r.ID)
		from, _ := time.Parse(time.RFC3339Nano, filters.From)
		before, _ := time.Parse(time.RFC3339Nano, filters.Before)
		if err != nil || seen[id] || (len(seen) > 0 && (stamp.Before(previousTime) || (stamp.Equal(previousTime) && bytes.Compare(id[:], previousID[:]) <= 0))) ||
			(filters.From != "" && stamp.Before(from)) || (filters.Before != "" && !stamp.Before(before)) {
			return bad
		}
		seen[id], previousTime, previousID = true, stamp, id
		var rawAwards []json.RawMessage
		if err := json.Unmarshal(fields["awards"], &rawAwards); err != nil || rawAwards == nil || len(rawAwards) > 1 {
			return bad
		}
		instruments := make(map[string]bool)
		for _, rawAward := range rawAwards {
			var a ContributionAward
			_, err := contextObject(rawAward, &a, []string{"award_id", "award_definition_id", "instrument", "unit", "quantity"}, nil)
			awardID, valid := uuidIdentity(a.ID)
			if err != nil || !valid || awards[awardID] || instruments[a.Instrument] || !validUUID(a.Definition) ||
				(a.Instrument != "money" && a.Instrument != "project_points") || !validContributionQuantity(a.Quantity, a.Instrument) {
				return bad
			}
			awards[awardID], instruments[a.Instrument] = true, true
		}
	}
	return nil
}

// Validate the public fixed-point representation, not eligibility or payments.
func validContributionQuantity(value, instrument string) bool {
	if len(value) > 40 || !contributionQuantity.MatchString(value) {
		return false
	}
	parts := strings.Split(value, ".")
	if len(parts) == 2 && (len(parts[1]) > 18 || instrument == "project_points") {
		return false
	}
	number, ok := new(big.Rat).SetString(value)
	maximum, _ := new(big.Rat).SetString("100000000000000000000")
	return ok && number.Sign() > 0 && number.Cmp(maximum) < 0
}
