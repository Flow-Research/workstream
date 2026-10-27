package tui

import (
	"context"
	"errors"
	"io"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
)

const (
	actorID      = "10000000-0000-7000-8000-000000000001"
	projectID    = "20000000-0000-7000-8000-000000000001"
	taskID       = "30000000-0000-7000-8000-000000000001"
	submissionID = "40000000-0000-7000-8000-000000000001"
	policyID     = "50000000-0000-7000-8000-000000000001"
	runID        = "60000000-0000-7000-8000-000000000001"
	findingID    = "70000000-0000-7000-8000-000000000001"
)

type fakeClient struct {
	calls                            []string
	profile                          func(context.Context) (api.Result[api.Profile], error)
	projects                         func(context.Context, api.PageQuery) (api.Result[api.ActorProjectPage], error)
	ready                            func(context.Context, string, int, *string) (api.Result[api.ReadyTaskPage], error)
	task                             func(context.Context, string) (api.Result[api.ContributorTaskDetail], error)
	context                          func(context.Context, string) (api.Result[api.WorkContext], error)
	intake                           func(context.Context, string) (api.Result[api.SubmissionRequirements], error)
	findings                         func(context.Context, string, string, int, *string) (api.Result[api.SubmissionFindingsResult], error)
	download                         func(context.Context, string, api.TaskGuideDocument, io.Writer) error
	claim                            func(context.Context, string, string, *string) (api.Result[api.ClaimedTask], error)
	start                            func(context.Context, string, string, *string) (api.Result[api.MutationTask], error)
	assignmentQuery, submissionQuery api.PageQuery
}

func (f *fakeClient) Profile(ctx context.Context) (api.Result[api.Profile], error) {
	f.calls = append(f.calls, "profile")
	if f.profile != nil {
		return f.profile(ctx)
	}
	return api.Result[api.Profile]{Value: api.Profile{ActorProfileID: actorID}}, nil
}
func (f *fakeClient) MyProjects(ctx context.Context, q api.PageQuery) (api.Result[api.ActorProjectPage], error) {
	f.calls = append(f.calls, "projects")
	if f.projects != nil {
		return f.projects(ctx, q)
	}
	return api.Result[api.ActorProjectPage]{Value: api.ActorProjectPage{Items: []api.ActorProject{{ProjectID: projectID, Name: "Project", Status: "active"}}}}, nil
}
func (f *fakeClient) ReadyTasks(ctx context.Context, p string, n int, c *string) (api.Result[api.ReadyTaskPage], error) {
	f.calls = append(f.calls, "ready")
	if f.ready != nil {
		return f.ready(ctx, p, n, c)
	}
	return api.Result[api.ReadyTaskPage]{Value: api.ReadyTaskPage{ProjectID: p, Items: []api.ReadyTaskSummary{{TaskID: taskID, ProjectID: p, Title: "Task title"}}}}, nil
}
func (f *fakeClient) MyAssignments(_ context.Context, q api.PageQuery) (api.Result[api.ContributorAssignmentPage], error) {
	f.calls = append(f.calls, "mine")
	f.assignmentQuery = q
	return api.Result[api.ContributorAssignmentPage]{Value: api.ContributorAssignmentPage{Items: []api.ContributorAssignment{{AssignmentID: actorID, ProjectID: projectID, TaskID: taskID, Title: "Assigned task", State: "active", AssignmentStatus: "active"}}}}, nil
}
func (f *fakeClient) MySubmissions(_ context.Context, q api.PageQuery) (api.Result[api.ContributorSubmissionPage], error) {
	f.calls = append(f.calls, "submissions")
	f.submissionQuery = q
	return api.Result[api.ContributorSubmissionPage]{Value: api.ContributorSubmissionPage{Items: []api.ContributorSubmission{{SubmissionID: submissionID, ProjectID: projectID, TaskID: taskID, Title: "Attempt", Status: "review_pending"}}}}, nil
}
func taskDetail() api.ContributorTaskDetail {
	return api.ContributorTaskDetail{TaskSummary: api.TaskSummary{TaskID: taskID, ProjectID: projectID, Title: "Task title", Status: "ready"}, Description: "Exact instructions", Compensation: api.CompensationTerms{ContributionPolicyVersionID: policyID, AcceptedSubmission: []byte(`"unpaid"`), CompletedReview: []byte(`"unpaid"`)}}
}
func (f *fakeClient) ContributorTask(ctx context.Context, id string) (api.Result[api.ContributorTaskDetail], error) {
	f.calls = append(f.calls, "task")
	if f.task != nil {
		return f.task(ctx, id)
	}
	return api.Result[api.ContributorTaskDetail]{Value: taskDetail()}, nil
}
func (f *fakeClient) WorkContext(ctx context.Context, id string) (api.Result[api.WorkContext], error) {
	f.calls = append(f.calls, "context")
	if f.context != nil {
		return f.context(ctx, id)
	}
	return api.Result[api.WorkContext]{Value: api.WorkContext{Task: taskDetail(), Project: api.ContextProject{ID: projectID}, Guide: api.ContextGuide{ID: actorID, ProjectID: projectID, Version: "locked-v1"}, ContributionPolicyVersionID: policyID}}, nil
}
func (f *fakeClient) SubmissionRequirements(ctx context.Context, id string) (api.Result[api.SubmissionRequirements], error) {
	f.calls = append(f.calls, "intake")
	if f.intake != nil {
		return f.intake(ctx, id)
	}
	return api.Result[api.SubmissionRequirements]{Value: api.SubmissionRequirements{TaskID: taskID, ProjectID: projectID, GuideVersion: "locked-v1"}}, nil
}
func (f *fakeClient) Submission(context.Context, string) (api.Result[api.SubmissionHistory], error) {
	f.calls = append(f.calls, "submission")
	return api.Result[api.SubmissionHistory]{Value: api.SubmissionHistory{ID: submissionID, Task: taskID, Status: "review_pending", Summary: "Stored summary"}}, nil
}
func (f *fakeClient) SubmissionFindings(ctx context.Context, submission, run string, limit int, cursor *string) (api.Result[api.SubmissionFindingsResult], error) {
	f.calls = append(f.calls, "findings")
	if f.findings != nil {
		return f.findings(ctx, submission, run, limit, cursor)
	}
	page := api.SubmissionCheckerPage{Items: []api.SubmissionCheckerRun{{ID: runID, Task: taskID, Submission: submission, Status: "completed", Current: true,
		Results: []api.ContributorFinding{{ID: findingID, Checker: "lint", Status: "passed", Severity: "info"}}}}}
	return api.Result[api.SubmissionFindingsResult]{Value: api.SubmissionFindingsResult{Page: &page}}, nil
}
func (f *fakeClient) DownloadGuideDocument(ctx context.Context, task string, document api.TaskGuideDocument, target io.Writer) error {
	f.calls = append(f.calls, "download")
	if f.download != nil {
		return f.download(ctx, task, document, target)
	}
	_, err := target.Write([]byte("guide"))
	return err
}
func (f *fakeClient) ClaimTask(ctx context.Context, task, key string, reason *string) (api.Result[api.ClaimedTask], error) {
	f.calls = append(f.calls, "claim")
	if f.claim != nil {
		return f.claim(ctx, task, key, reason)
	}
	return api.Result[api.ClaimedTask]{Value: api.ClaimedTask{
		Task:       api.MutationTask{ID: task, ProjectID: projectID, Status: "claimed"},
		Assignment: api.TaskAssignment{TaskID: task, ProjectID: projectID, ContributorID: actorID},
	}}, nil
}
func (f *fakeClient) StartTask(ctx context.Context, task, key string, reason *string) (api.Result[api.MutationTask], error) {
	f.calls = append(f.calls, "start")
	if f.start != nil {
		return f.start(ctx, task, key, reason)
	}
	return api.Result[api.MutationTask]{Value: api.MutationTask{ID: task, ProjectID: projectID, Status: "in_progress"}}, nil
}

func apply(t *testing.T, m *Model, cmd tea.Cmd) {
	t.Helper()
	for n := 0; cmd != nil; n++ {
		if n > 10 {
			t.Fatal("unexpected automatic request loop")
		}
		_, cmd = m.Update(cmd())
	}
}
func press(t *testing.T, m *Model, key string) {
	t.Helper()
	_, cmd := m.Update(keyMessage(key))
	apply(t, m, cmd)
}
func keyMessage(key string) tea.KeyPressMsg {
	switch key {
	case "enter":
		return tea.KeyPressMsg{Code: tea.KeyEnter}
	case "esc":
		return tea.KeyPressMsg{Code: tea.KeyEscape}
	case "tab":
		return tea.KeyPressMsg{Code: tea.KeyTab}
	case "shift+tab":
		return tea.KeyPressMsg{Code: tea.KeyTab, Mod: tea.ModShift}
	case "down":
		return tea.KeyPressMsg{Code: tea.KeyDown}
	case "up":
		return tea.KeyPressMsg{Code: tea.KeyUp}
	case "ctrl+c":
		return tea.KeyPressMsg{Code: 'c', Mod: tea.ModCtrl}
	default:
		r := []rune(key)
		return tea.KeyPressMsg{Code: r[0], Text: key}
	}
}
func boot(t *testing.T, f *fakeClient) *Model {
	t.Helper()
	m := New(context.Background(), f, "secret-token", true, true)
	t.Cleanup(m.Close)
	_, cmd := m.Update(tea.WindowSizeMsg{Width: 80, Height: 24})
	apply(t, m, cmd)
	return m
}

func TestContributorReadNavigation(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	if strings.Join(f.calls, ",") != "profile,projects" {
		t.Fatal(f.calls)
	}
	press(t, m, "enter")
	press(t, m, "enter")
	press(t, m, "tab")
	if m.task == nil || strings.Join(f.calls, ",") != "profile,projects,ready,task" {
		t.Fatal("Ready must not fetch context", f.calls)
	}
	press(t, m, "esc")
	press(t, m, "tab")
	if q := f.assignmentQuery; q.ProjectID == nil || *q.ProjectID != projectID || q.State == nil || *q.State != "active" || q.Limit != 50 {
		t.Fatal(q)
	}
	press(t, m, "enter")
	press(t, m, "tab")
	press(t, m, "tab")
	if m.context == nil || m.intake == nil {
		t.Fatal("missing explicit context/intake")
	}
	press(t, m, "esc")
	press(t, m, "tab")
	press(t, m, "enter")
	if m.submission == nil || f.submissionQuery.ProjectID == nil || f.submissionQuery.State != nil {
		t.Fatal("missing owned attempt")
	}
}

func TestExplicitPaginationAndRefresh(t *testing.T) {
	f := &fakeClient{}
	cursor := "opaque/next?"
	f.ready = func(_ context.Context, p string, n int, c *string) (api.Result[api.ReadyTaskPage], error) {
		if n != 50 {
			t.Fatal(n)
		}
		page := api.ReadyTaskPage{ProjectID: p, Items: []api.ReadyTaskSummary{{TaskID: taskID, ProjectID: p, Title: "Task"}}}
		if c == nil {
			page.NextCursor = &cursor
		} else if *c != cursor {
			t.Fatal(*c)
		}
		return api.Result[api.ReadyTaskPage]{Value: page}, nil
	}
	m := boot(t, f)
	press(t, m, "enter")
	if len(f.calls) != 3 {
		t.Fatal("automatic page traversal", f.calls)
	}
	_, cmd := m.Update(keyMessage("n"))
	_, duplicate := m.Update(keyMessage("n"))
	if duplicate != nil {
		t.Fatal("duplicate dispatch")
	}
	apply(t, m, cmd)
	if len(m.rows) != 1 || m.page != 2 || m.cursor != nil {
		t.Fatal("next must replace one page")
	}
	press(t, m, "r")
	if m.page != 1 || m.cursor == nil {
		t.Fatal("refresh must reset continuation")
	}
}

func TestFilterResizeHelpHandoffNeverRead(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	press(t, m, "enter")
	before := len(f.calls)
	for _, k := range []string{"/", "Task", "enter", "?", "esc", "c", "esc"} {
		press(t, m, k)
	}
	m.Update(tea.WindowSizeMsg{Width: 120, Height: 40})
	if len(f.calls) != before {
		t.Fatal(f.calls)
	}
	if m.filter != "Task" || !strings.Contains(m.View().Content, "local filter") {
		t.Fatal(m.View().Content)
	}
}

func TestDenialPurgesAndQuitCancels(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	press(t, m, "enter")
	press(t, m, "enter")
	f.task = func(context.Context, string) (api.Result[api.ContributorTaskDetail], error) {
		return api.Result[api.ContributorTaskDetail]{}, &api.Failure{Code: "not_found", Status: 404}
	}
	press(t, m, "r")
	if len(m.rows) != 0 || m.task != nil || m.cursor != nil || m.projectName != "" || !strings.Contains(m.failure, "HTTP 404") {
		t.Fatal("denial retained private data")
	}
	if strings.Contains(m.View().Content, "Exact instructions") {
		t.Fatal("denied text visible")
	}
	press(t, m, "g")
	if !m.picker || len(m.rows) != 1 {
		t.Fatal("fresh picker unavailable")
	}
	press(t, m, "ctrl+c")
	if !m.closed || !errors.Is(m.ctx.Err(), context.Canceled) {
		t.Fatal("quit left read context active")
	}
}

func TestSmallTerminalDoesNotStartReads(t *testing.T) {
	f := &fakeClient{}
	m := New(context.Background(), f, "", true, true)
	defer m.Close()
	_, cmd := m.Update(tea.WindowSizeMsg{Width: 30, Height: 8})
	if cmd != nil || len(f.calls) != 0 {
		t.Fatal("small screen requested data")
	}
	press(t, m, "q")
	if !m.closed {
		t.Fatal("small screen cannot quit")
	}
}
