package api

import (
	"context"
	"errors"
	"math/big"
	"net/http"
	"net/url"
)

// GuideCompilationDispatch reports a durable request's current dispatch state.
// It is neither compilation completion nor policy approval or guide activation.
type GuideCompilationDispatch struct {
	OperationID     string   `json:"operation_id"`
	SetupRunID      string   `json:"setup_run_id"`
	SetupGeneration *big.Int `json:"setup_generation"`
	Status          string   `json:"status"`
}

func (c *Client) RequestGuideAssistance(ctx context.Context, project, guide, key string) (Result[GuideCompilationDispatch], error) {
	return c.requestGuideCompilation(ctx, project, guide, key, "setup")
}

func (c *Client) CompileGuideRequirements(ctx context.Context, project, guide, key string) (Result[GuideCompilationDispatch], error) {
	return c.requestGuideCompilation(ctx, project, guide, key, "requirements/compile")
}

func (c *Client) requestGuideCompilation(ctx context.Context, project, guide, key, suffix string) (Result[GuideCompilationDispatch], error) {
	var result Result[GuideCompilationDispatch]
	for _, id := range []string{project, guide, key} {
		if !validUUID(id) || len(id) > 100 {
			return result, errors.New("PROJECT_ID, GUIDE_ID and --idempotency-key must be UUIDs")
		}
	}
	raw, err := c.requestWithKey(ctx, http.MethodPost,
		"/api/v1/projects/"+url.PathEscape(project)+"/guides/"+url.PathEscape(guide)+"/"+suffix,
		"", nil, key, http.StatusAccepted)
	if err != nil {
		return result, guideCompilationFailure(err)
	}
	var value GuideCompilationDispatch
	_, err = contextObject(raw, &value, []string{"operation_id", "setup_run_id", "setup_generation", "status"}, nil)
	if err != nil || !validUUID(value.OperationID) || !validUUID(value.SetupRunID) ||
		value.SetupGeneration == nil || value.SetupGeneration.Sign() < 1 || !c.safeMutationResponse(raw) {
		return result, guideCompilationFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[GuideCompilationDispatch]{Raw: raw, Value: value}, nil
}

func guideCompilationFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "guide compilation request outcome unknown; inspect setup status and manually replay only the unchanged command, project, guide and idempotency key"
	}
	return err
}
