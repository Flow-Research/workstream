package tui

import (
	"encoding/json"
	"fmt"
	"image/color"
	"math/big"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
)

// These are presentation fixtures, not evidence of a live backend journey.
func renderFixture(t *testing.T, screen string) (*Model, *fakeClient) {
	t.Helper()
	f := &fakeClient{}
	m := boot(t, f)
	m.projectName = "Aster Research / fixture project"
	m.observed = time.Date(2026, 10, 26, 14, 2, 18, 0, time.UTC)
	if screen == "projects" {
		m.rows[0].title = m.projectName
		return m, f
	}
	press(t, m, "enter")
	m.projectName = "Aster Research / fixture project"
	m.rows[0].title = "Assess evidence for the coastal flood warning study"
	if screen == "ready" {
		return m, f
	}
	if screen == "empty" {
		m.rows = nil
		return m, f
	}
	if screen == "filter-miss" {
		m.filter = "unmatched fixture"
		return m, f
	}
	if screen == "denied" {
		m.failed(&api.Failure{Status: 403, Code: "permission_denied"}, false)
		return m, f
	}
	if screen == "help" {
		m.help = true
		return m, f
	}
	press(t, m, "tab")
	press(t, m, "enter")
	m.task.Title = "Assess the coastal flood warning study and document where its evidence supports the published conclusions"
	m.task.Status = "in_progress"
	m.task.Description = "Read the supplied field report and produce an evidence matrix linking each major conclusion to its source. Keep direct observations separate from assumptions.\n\nFor every conclusion, cite the section and page, explain the strength of the evidence, and note any material limitation. Preserve uncertainty: absence of evidence is not evidence of absence.\n\nDeliver evidence-matrix.csv and a concise methodology.md in one ZIP. Include enough context for another contributor to reproduce your assessment."
	accept := "Every conclusion has a traceable citation or an explicit evidence gap. The matrix and methodology agree; no unsupported certainty is introduced."
	reject := "Missing source references, invented evidence, or claims that cannot be traced to the supplied report."
	m.task.AcceptanceCriteria, m.task.RejectionCriteria = &accept, &reject
	m.task.SkillTags = []string{"evidence synthesis", "research"}
	m.rows[0].title, m.rows[0].status = m.task.Title, "active"
	m.task.Compensation.AcceptedSubmission = []byte(`[{"instrument":"money","unit":"USD","quantity":"40.000000000000000001"}]`)
	if screen == "mine" {
		return m, f
	}
	if screen == "intake" {
		m.section = 2
		description := "One row per conclusion, with source section, page and evidence strength."
		m.intake = &api.SubmissionRequirements{TaskID: taskID, ProjectID: projectID, GuideVersion: "research-guide",
			RequiredArtifacts:       []api.ArtifactRequirement{{Key: "matrix", Path: "evidence-matrix.csv", Required: true, HashRequired: true, Description: &description}, {Key: "methodology", Path: "methodology.md", Required: true, HashRequired: true}},
			RequiredEvidence:        []api.EvidenceRequirement{{Key: "sources", Label: "Source citation index", Required: true, HashRequired: true}},
			MaximumPackageSizeBytes: big.NewInt(10485760), Packaging: api.PackagingRequirements{PackageRequired: true, AllowedPackageFormats: []string{"zip"}}}
		return m, f
	}
	if screen == "guide-confirmation" {
		m.section = 3
		context := guideContext(api.TaskGuideDocument{DocumentID: actorID, Label: "Research instructions", Order: 0, MediaType: "text/markdown", ByteCount: 12480, SHA256: "sha256:" + strings.Repeat("abcdef01", 8)})
		m.context, m.guideMode, m.guideDirectory = &context, guideConfirm, "/work/aster/locked-guide"
		return m, f
	}
	m.tab, m.section = submissions, 0
	summary := "Evidence matrix and methodology for the coastal flood warning study"
	m.submission = &api.SubmissionHistory{ID: submissionID, Task: taskID, Version: big.NewInt(1), Status: "review_pending", Summary: &summary, SubmittedAt: "2026-10-26T13:58:02Z", FindingCounts: api.SubmissionFindingCounts{Blocking: big.NewInt(0), Warning: big.NewInt(1), CoverageIncomplete: big.NewInt(0)}, Evidence: []api.SubmissionEvidence{{ID: findingID, Type: "document", Label: "Methodology and citation matrix", Size: big.NewInt(18520)}}}
	if screen == "submission" {
		return m, f
	}
	m.section, m.findingsPage = 1, 1
	message, fix, checkID, path := "The citation for conclusion 4 does not identify a page.", "Add the exact page reference or explain why the source is not paginated.", "citation-location", "evidence-matrix.csv"
	line := int64(5)
	m.findings = &api.SubmissionCheckerPage{Items: []api.SubmissionCheckerRun{{ID: runID, Task: taskID, Submission: submissionID, Status: "completed", Current: true, Version: big.NewInt(1), Attempt: big.NewInt(1), CreatedAt: "2026-10-26T13:58:05Z", Results: []api.ContributorFinding{{ID: findingID, Checker: "citation-checker", CheckID: &checkID, Status: "warning", Severity: "warning", Path: &path, Line: &line, Message: &message, Fix: &fix}}}}}
	return m, f
}

func TestRepresentativeRenderBoundsAndPureReflow(t *testing.T) {
	for _, screen := range []string{"projects", "ready", "mine", "intake", "guide-confirmation", "submission", "findings", "empty", "filter-miss", "denied", "help"} {
		for _, mode := range []string{"dark", "light", "no-color", "plain"} {
			for _, size := range [][2]int{{120, 40}, {100, 24}, {80, 24}, {60, 24}, {59, 24}, {40, 24}, {40, 10}} {
				name := fmt.Sprintf("%s-%s-%dx%d", screen, mode, size[0], size[1])
				t.Run(name, func(t *testing.T) {
					m, f := renderFixture(t, screen)
					m.plain, m.noColor = mode == "plain", mode == "plain" || mode == "no-color"
					background := color.RGBA{R: 16, G: 25, B: 35, A: 255}
					if mode == "light" {
						background = color.RGBA{R: 255, G: 255, B: 255, A: 255}
					}
					m.Update(tea.BackgroundColorMsg{Color: background})
					before, selected, section, generation := len(f.calls), m.selectedResource(), m.section, m.generation
					_, cmd := m.Update(tea.WindowSizeMsg{Width: size[0], Height: size[1]})
					if cmd != nil || len(f.calls) != before || m.selectedResource() != selected || m.section != section || m.generation != generation {
						t.Fatal("presentation reflow changed request or exact navigation state")
					}
					content := m.View().Content
					if lipgloss.Height(content) > size[1] {
						t.Fatalf("height exceeds terminal: %d\n%s", lipgloss.Height(content), content)
					}
					for _, line := range strings.Split(content, "\n") {
						if lipgloss.Width(line) > size[0] {
							t.Fatalf("width exceeds terminal: %q", line)
						}
					}
					if m.noColor && strings.Contains(content, "\x1b") {
						t.Fatal("no-color output contains ANSI")
					}
					if !strings.Contains(content, "quit") {
						t.Fatal("quit control is not visible")
					}
					if screen == "denied" && (strings.Contains(content, "Assess evidence") || strings.Contains(content, taskID)) {
						t.Fatal("denial retained protected content")
					}
					if directory := os.Getenv("WORKSTREAM_TUI_RENDER_DIR"); directory != "" {
						data, err := json.MarshalIndent(map[string]any{"kind": "fixture terminal render; not live backend proof", "screen": screen, "mode": mode, "columns": size[0], "rows": size[1], "content": content}, "", "  ")
						if err != nil {
							t.Fatal(err)
						}
						if err := os.MkdirAll(directory, 0700); err != nil {
							t.Fatal(err)
						}
						if err := os.WriteFile(filepath.Join(directory, name+".json"), data, 0600); err != nil {
							t.Fatal(err)
						}
					}
				})
			}
		}
	}
}
