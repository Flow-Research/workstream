package api

import (
	"context"
	"strings"
	"testing"
)

func TestOnlyPreparationListsAcceptOutcome(t *testing.T) {
	outcome := "failed"
	project := "019b9ba2-4100-7000-8000-000000000001"
	q := PageQuery{Limit: 10, Outcome: &outcome}
	c := &Client{} // every guard runs before any request
	ctx := context.Background()
	for name, call := range map[string]func() error{
		"my projects":    func() error { _, err := c.MyProjects(ctx, q); return err },
		"my assignments": func() error { _, err := c.MyAssignments(ctx, q); return err },
		"my submissions": func() error { _, err := c.MySubmissions(ctx, q); return err },
		"project submissions": func() error {
			_, err := c.ProjectSubmissions(ctx, project, ProjectWorkQuery{PageQuery: q})
			return err
		},
		"project assignments": func() error {
			_, err := c.ProjectAssignments(ctx, project, ProjectWorkQuery{PageQuery: q})
			return err
		},
		"import batches": func() error {
			_, err := c.ProjectImportBatches(ctx, project, ProjectWorkQuery{PageQuery: q})
			return err
		},
		"guides":          func() error { _, err := c.ProjectGuides(ctx, project, q); return err },
		"policy versions": func() error { _, err := c.ContributionPolicyVersions(ctx, project, q); return err },
	} {
		if err := call(); err == nil {
			t.Errorf("%s accepted --outcome: %v", name, err)
		}
	}
	if _, err := (PageQuery{Limit: 0}).encode(); err == nil || strings.Contains(err.Error(), "outcome") {
		t.Errorf("contributor list error mentions outcome: %v", err)
	}
	query, err := q.encodePreparations()
	if err != nil || query != "limit=10&outcome=failed" {
		t.Fatalf("preparation query %q: %v", query, err)
	}
	invalid := "unknown"
	if _, err := (PageQuery{Limit: 10, Outcome: &invalid}).encodePreparations(); err == nil {
		t.Fatal("accepted an unknown outcome")
	}
}
