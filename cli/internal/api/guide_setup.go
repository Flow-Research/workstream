package api

import (
	"context"
	"errors"
	"math/big"
	"net/http"
	"net/url"
)

// GuideSetup is a current diagnostic projection, not an approval or activation.
type GuideSetup struct {
	ID                               string   `json:"id"`
	ProjectID                        string   `json:"project_id"`
	GuideID                          string   `json:"guide_id"`
	GuideVersion                     string   `json:"guide_version"`
	SourceSnapshotID                 string   `json:"source_snapshot_id"`
	SetupGeneration                  *big.Int `json:"setup_generation"`
	FinalizedCompilationID           *string  `json:"finalized_compilation_id"`
	CorrectionOperationID            *string  `json:"correction_operation_id"`
	PredecessorCompilationID         *string  `json:"predecessor_compilation_id"`
	CeleryTaskID                     *string  `json:"celery_task_id"`
	DocumentsReadyAt                 *string  `json:"documents_ready_at"`
	Status                           string   `json:"status"`
	CurrentStep                      string   `json:"current_step"`
	OutputSufficiencyReportID        *string  `json:"output_sufficiency_report_id"`
	OutputSubmissionArtifactPolicyID *string  `json:"output_submission_artifact_policy_id"`
	ErrorCode                        *string  `json:"error_code"`
	ErrorArtifactIncidentID          *string  `json:"error_artifact_incident_id"`
	ErrorSummary                     *string  `json:"error_summary"`
	CreatedBy                        string   `json:"created_by"`
	CreatedAt                        string   `json:"created_at"`
	UpdatedAt                        string   `json:"updated_at"`
	StartedAt                        *string  `json:"started_at"`
	FinishedAt                       *string  `json:"finished_at"`
}

func (c *Client) GuideSetup(ctx context.Context, project, guide string) (Result[GuideSetup], error) {
	var result Result[GuideSetup]
	if !validUUID(project) || len(project) > 100 || !validUUID(guide) || len(guide) > 100 {
		return result, errors.New("PROJECT_ID and GUIDE_ID must be UUIDs")
	}
	raw, err := c.request(ctx, http.MethodGet,
		"/api/v1/projects/"+url.PathEscape(project)+"/guides/"+url.PathEscape(guide)+"/setup-runs/latest", "", nil)
	if err != nil {
		return result, err
	}
	var value GuideSetup
	fields, err := contextObject(raw, &value, []string{
		"id", "project_id", "guide_id", "guide_version", "source_snapshot_id", "setup_generation",
		"status", "current_step", "created_by", "created_at", "updated_at",
	}, nil)
	if err != nil || !sameUUID(value.ProjectID, project) || !sameUUID(value.GuideID, guide) ||
		!validUUID(value.ID) || !validUUID(value.SourceSnapshotID) || !validUUID(value.CreatedBy) ||
		!validTime(value.CreatedAt) || !validTime(value.UpdatedAt) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	// These public nullable fields are required; only the three lineage UUIDs
	// default to null when omitted. Do not infer a state machine from diagnostics.
	for _, name := range []string{
		"celery_task_id", "documents_ready_at", "output_sufficiency_report_id",
		"output_submission_artifact_policy_id", "error_code", "error_artifact_incident_id",
		"error_summary", "started_at", "finished_at",
	} {
		if _, present := fields[name]; !present {
			return result, &Failure{Code: "invalid_api_response"}
		}
	}
	for _, identity := range []*string{
		value.FinalizedCompilationID, value.CorrectionOperationID, value.PredecessorCompilationID,
		value.OutputSufficiencyReportID, value.OutputSubmissionArtifactPolicyID, value.ErrorArtifactIncidentID,
	} {
		if identity != nil && !validUUID(*identity) {
			return result, &Failure{Code: "invalid_api_response"}
		}
	}
	for _, timestamp := range []*string{value.DocumentsReadyAt, value.StartedAt, value.FinishedAt} {
		if timestamp != nil && !validTime(*timestamp) {
			return result, &Failure{Code: "invalid_api_response"}
		}
	}
	return Result[GuideSetup]{Raw: raw, Value: value}, nil
}
