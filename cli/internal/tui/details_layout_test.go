package tui

import (
	"math/big"
	"strings"
	"testing"

	"charm.land/bubbles/v2/viewport"
	"github.com/Flow-Research/workstream/cli/internal/api"
)

func orderOf(t *testing.T, rendered string, labels ...string) {
	t.Helper()
	last := -1
	for _, label := range labels {
		at := strings.Index(rendered, label)
		if at < 0 || at <= last {
			t.Fatalf("missing or out-of-order %q in:\n%s", label, rendered)
		}
		last = at
	}
}

func TestProsePreservesParagraphsAfterBearerSuppression(t *testing.T) {
	m := &Model{token: "bearer\r\nsecret"}
	rendered := m.prose("First\r\n\r\nbearer\r\nsecret\nLast\x1b]52;c;secret\a\u202e\u009b\t")
	if !strings.HasPrefix(rendered, "First\n\n[redacted]\nLast") {
		t.Fatal(rendered)
	}
	for _, unsafe := range []string{"bearer", "\r", "\x1b", "\a", "\u202e", "\u009b", "\t"} {
		if strings.Contains(rendered, unsafe) {
			t.Fatalf("unsafe %q in %q", unsafe, rendered)
		}
	}
	if !strings.Contains(rendered, "\\u001B") || !strings.Contains(rendered, "\\u202E") {
		t.Fatal(rendered)
	}
	if got := m.clean("a\nb"); got != "a\\u000Ab" {
		t.Fatalf("metadata sanitizer changed: %q", got)
	}
}

func TestTaskOverviewPrioritizesFullProseAndExactTerms(t *testing.T) {
	accept, reject := "Accepted line\n\nSecond paragraph", "Rejected line\nNext line"
	task := taskDetail()
	task.Title = "A complete contributor title"
	task.Description = "Do the work\n\nThen submit exact artifact"
	task.AcceptanceCriteria, task.RejectionCriteria = &accept, &reject
	task.SkillTags = []string{"Go", "writing"}
	task.Compensation.AcceptedSubmission = []byte(`[{"instrument":"money","unit":"USD","quantity":"0.100000000000000001"}]`)
	task.Compensation.CompletedReview = []byte(`"unpaid"`)
	m := &Model{task: &task, noColor: true}
	rendered := m.detailText()
	orderOf(t, rendered, "A complete contributor title", "Stored status: ready", "Skills: Go, writing", "Instructions", "Do the work\n\nThen submit exact artifact", "Acceptance criteria", "Accepted line\n\nSecond paragraph", "Rejection criteria", "Contribution terms", "Accepted submission terms: money / USD / 0.100000000000000001", "Completed review terms: unpaid", "References", "Task: "+taskID)
	for _, want := range []string{"Project: " + projectID, "Contribution policy version: " + policyID, "potential earned terms, not acceptance or fulfillment"} {
		if !strings.Contains(rendered, want) {
			t.Fatal(want, rendered)
		}
	}
}

func TestGuideConfirmationReplacesDocumentListAndNamesExactTarget(t *testing.T) {
	hash := "sha256:" + strings.Repeat("a", 64)
	doc := api.TaskGuideDocument{DocumentID: actorID, Order: 9, Label: "Read me", MediaType: "text/markdown", ByteCount: 128, SHA256: hash}
	context := guideContext(doc)
	m := &Model{context: &context, section: 3, guideMode: guideConfirm, guideDirectory: "/tmp/selected", noColor: true}
	rendered := m.detailText()
	orderOf(t, rendered, "Confirm download", "Label: Read me", "Document: "+actorID, "Task: "+taskID, "Download directory: /tmp/selected", "Filename: "+doc.Filename(), "Expected bytes: 128", "Expected SHA-256: "+hash)
	if strings.Contains(rendered, "Guide originals") || strings.Contains(rendered, "verified and saved") {
		t.Fatal(rendered)
	}
	m.guideMode, m.guideNotice = guideBrowse, "Unavailable: transfer failed"
	if strings.Contains(m.detailText(), "verified and saved") {
		t.Fatal(m.detailText())
	}
}

func TestGuideBrowseKeepsServerOrderAndSelectedExactMetadata(t *testing.T) {
	firstHash := "sha256:" + strings.Repeat("a", 64)
	secondHash := "sha256:" + strings.Repeat("b", 64)
	first := api.TaskGuideDocument{DocumentID: actorID, Order: 2, Label: "First", MediaType: "text/markdown", ByteCount: 1024, SHA256: firstHash}
	second := api.TaskGuideDocument{DocumentID: policyID, Order: 7, Label: "Second", MediaType: "application/pdf", ByteCount: 2048, SHA256: secondHash}
	context := guideContext(first, second)
	m := &Model{context: &context, section: 3, noColor: true}
	rendered := m.detailText()
	orderOf(t, rendered, "Selected original", "Document ID: "+actorID, "Order: 2", firstHash, "Guide originals", "> 1. First · text/markdown · 1.0 KiB", "  2. Second · application/pdf · 2.0 KiB")
	if strings.Contains(rendered, secondHash) {
		t.Fatal("unselected original crowded selected detail", rendered)
	}
	m.guideSelected = 1
	rendered = m.detailText()
	orderOf(t, rendered, "Document ID: "+policyID, "Order: 7", secondHash, "Guide originals", "  1. First", "> 2. Second")
	for _, want := range []string{"Task: " + taskID, "Project: " + projectID, "Guide: " + actorID, "Locked guide version: locked-v1"} {
		if !strings.Contains(rendered, want) {
			t.Fatal(want, rendered)
		}
	}
}

func TestGuidePlainModeUsesASCIIChromeWithoutChangingUnicodeContent(t *testing.T) {
	doc := api.TaskGuideDocument{DocumentID: actorID, Order: 1, Label: "Café 指南", MediaType: "text/markdown", ByteCount: 1024}
	context := guideContext(doc)
	m := &Model{context: &context, section: 3, plain: true, noColor: true,
		started: true, detail: true, tab: mine, width: 80, height: 24, viewport: viewport.New()}
	m.reflow()
	rendered := m.View().Content
	if !strings.Contains(rendered, "> 1. Café 指南 | text/markdown | 1.0 KiB") || strings.Contains(rendered, " · ") || strings.Contains(rendered, "\x1b") {
		t.Fatal(rendered)
	}
}

func TestContextRetainsExactLockedPolicyAndRevisionReferences(t *testing.T) {
	reviewHash := "sha256:" + strings.Repeat("a", 64)
	revisionHash := "sha256:" + strings.Repeat("b", 64)
	preparationHash := "sha256:" + strings.Repeat("c", 64)
	predecessor, deadline := policyID, "2026-10-27T10:00:00Z"
	context := guideContext()
	context.ReviewPolicy = api.ContextPolicy{PolicyID: runID, Generation: 17, PolicyHash: reviewHash}
	context.RevisionPolicy = api.ContextPolicy{PolicyID: findingID, Generation: 23, PolicyHash: revisionHash}
	context.Lifecycle.NextActions = []string{}
	context.RevisionContext = &api.RevisionContext{
		PreparationID: actorID, PreparationSHA256: preparationHash,
		PredecessorPreparationID: &predecessor, SourceSubmissionID: submissionID,
		SourceRoutingManifestID: taskID, Sequence: 4, NextRevisionRound: 2,
		MaxRevisionRounds: 3, RequestedAt: "2026-10-26T10:00:00Z",
		DeadlineAt: &deadline, ClockState: "running", Outcome: "prepared",
		Disposition: "needs_revision", Prior: api.RevisionSnapshot{GuideID: actorID},
		Target:  &api.RevisionSnapshot{GuideID: policyID},
		Changes: []api.RevisionChange{{Component: "guide", Before: "v1", After: "v2"}},
	}
	m := &Model{context: &context, section: 1, noColor: true}
	rendered := m.detailText()
	orderOf(t, rendered, "Assignment", "Task: "+taskID, "Project: "+projectID, "Assigned to current actor: true", "Observed action hints (not authority): ", "Locked rules", "Revision context")
	for _, exact := range []string{
		"Guide: " + actorID, "Locked guide version: locked-v1",
		"Review policy: " + runID, "Review policy generation: 17", "Review policy hash: " + reviewHash,
		"Revision policy: " + findingID, "Revision policy generation: 23", "Revision policy hash: " + revisionHash,
		"Contribution policy version: " + policyID,
		"Revision preparation: " + actorID, "Revision preparation digest: " + preparationHash,
		"Revision source Submission: " + submissionID, "Revision source routing manifest: " + taskID,
		"Predecessor preparation: " + policyID, "Revision sequence: 4", "Next revision round: 2",
		"Maximum revision rounds: 3", "Revision requested: 2026-10-26T10:00:00Z",
		"Revision outcome: prepared", "Revision disposition: needs_revision", "Revision clock: running",
		"Revision deadline: " + deadline, "Prior guide: " + actorID, "Target guide: " + policyID,
		"Changed component: guide", "Before: v1", "After: v2",
	} {
		if !strings.Contains(rendered, exact) {
			t.Fatalf("missing exact %q in:\n%s", exact, rendered)
		}
	}
}

func TestIntakeDisplaysConstraintsWithoutValidationClaim(t *testing.T) {
	desc, reason, fix := "Expected artifact", "Secrets forbidden", "Remove credentials"
	value := api.SubmissionRequirements{
		TaskID: taskID, ProjectID: projectID, GuideVersion: "locked-v1",
		RequiredPacketFields: []string{"summary"},
		RequiredArtifacts:    []api.ArtifactRequirement{{Key: "source", Path: "src/**", Required: true, HashRequired: true, Description: &desc}},
		RequiredEvidence:     []api.EvidenceRequirement{{Key: "test", Label: "Tests", Required: true, HashRequired: false}},
		ForbiddenArtifacts:   []api.ForbiddenArtifact{{Pattern: "*.key", Reason: &reason, WorkerFacingFix: &fix}},
		AttestationTerms:     []string{"original work"}, ManifestRequired: true, ArtifactHashRequired: true,
		ArtifactHashAlgorithm: "sha256", AllowedStorageSchemes: []string{"s3"},
		StorageReferenceRules: api.StorageReferenceRules{AllowedURIPrefixes: []string{"s3://bucket/"}},
		MaximumFileSizeBytes:  big.NewInt(4294967297), Packaging: api.PackagingRequirements{PackageRequired: true, AllowedPackageFormats: []string{"zip"}},
	}
	m := &Model{intake: &value, section: 2, noColor: true}
	rendered := m.detailText()
	orderOf(t, rendered, "Required packet fields", "Field: summary", "Required artifacts", "Artifact: source", "Required evidence", "Evidence: test", "Forbidden artifacts", "Forbidden pattern: *.key", "Attestations", "Attestation term: original work", "Package and storage constraints", "Maximum file bytes: 4294967297", "References")
	for _, want := range []string{"Hash required: true", "Path (text only): src/**", "Reason\nSecrets forbidden", "Suggested fix\nRemove credentials", "Package required: true", "Allowed package formats: zip", "Policy schema version"} {
		if want == "Policy schema version" {
			if strings.Contains(rendered, want) {
				t.Fatal(rendered)
			}
			continue
		}
		if !strings.Contains(rendered, want) {
			t.Fatal(want, rendered)
		}
	}
}

func TestSubmissionAndFindingsSeparateOutcomeFromEvidence(t *testing.T) {
	reason := "coverage_incomplete"
	submission := api.SubmissionHistory{ID: submissionID, Task: taskID, Status: "needs_revision", StatusReason: &reason, Summary: "My full summary", Version: big.NewInt(12), FindingCounts: api.SubmissionFindingCounts{Blocking: big.NewInt(2), Warning: big.NewInt(1)}, Evidence: []api.SubmissionEvidence{{ID: actorID, Type: "artifact", Label: "source", Size: big.NewInt(9007199254740993)}}}
	m := &Model{submission: &submission, tab: submissions, noColor: true}
	rendered := m.detailText()
	orderOf(t, rendered, "My full summary", "Stored outcome: needs_revision", "Reason: coverage_incomplete", "Blocking findings: 2", "Version: 12", "Evidence label: source", "Size: 9007199254740993", "References", "Submission: "+submissionID)
	page := api.SubmissionCheckerPage{Items: []api.SubmissionCheckerRun{{ID: runID, Submission: submissionID, Task: taskID, Status: "completed", Current: false, Results: []api.ContributorFinding{{ID: findingID, Severity: "high", Status: "failed", Checker: "lint", Message: &reason}}}}}
	m.section, m.findings = 1, &page
	rendered = m.detailText()
	orderOf(t, rendered, "Historical checker run", "Run status: completed", "Run: "+runID, "Severity: high", "Finding status: failed", "Checker: lint", "Message\ncoverage_incomplete", "Finding: "+findingID, "stored submission outcome determines disposition")
	page.Items[0].Results = nil
	if !strings.Contains(m.detailText(), "does not establish a pass") {
		t.Fatal(m.detailText())
	}
}
