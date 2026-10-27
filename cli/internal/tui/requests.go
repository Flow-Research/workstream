package tui

import (
	"context"
	"errors"
	"fmt"
	"io"
	"strings"
	"sync"
	"time"

	tea "charm.land/bubbletea/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/Flow-Research/workstream/cli/internal/download"
)

// Client is the bounded contributor surface, satisfied directly by api.Client.
type Client interface {
	Profile(context.Context) (api.Result[api.Profile], error)
	MyProjects(context.Context, api.PageQuery) (api.Result[api.ActorProjectPage], error)
	ReadyTasks(context.Context, string, int, *string) (api.Result[api.ReadyTaskPage], error)
	MyAssignments(context.Context, api.PageQuery) (api.Result[api.ContributorAssignmentPage], error)
	MySubmissions(context.Context, api.PageQuery) (api.Result[api.ContributorSubmissionPage], error)
	ContributorTask(context.Context, string) (api.Result[api.ContributorTaskDetail], error)
	WorkContext(context.Context, string) (api.Result[api.WorkContext], error)
	SubmissionRequirements(context.Context, string) (api.Result[api.SubmissionRequirements], error)
	Submission(context.Context, string) (api.Result[api.SubmissionHistory], error)
	SubmissionFindings(context.Context, string, string, int, *string) (api.Result[api.SubmissionFindingsResult], error)
	DownloadGuideDocument(context.Context, string, api.TaskGuideDocument, io.Writer) error
	ClaimTask(context.Context, string, string, *string) (api.Result[api.ClaimedTask], error)
	StartTask(context.Context, string, string, *string) (api.Result[api.MutationTask], error)
}

var _ Client = (*api.Client)(nil)

type readKind int

const (
	profileRead readKind = iota
	projectsRead
	pageRead
	taskRead
	submissionRead
	contextRead
	intakeRead
	findingsRead
	guideDownloadRead
)

// request is an immutable identity carried through a non-cooperative response.
type request struct {
	generation                                                    uint64
	actor, project, resource, task, cursor, document, destination string
	tab                                                           tab
	kind                                                          readKind
	page, section                                                 int
}

type response struct {
	request  request
	value    any
	err      error
	download *guideDownload
}

type guideDownload struct {
	stage *download.Stage
	root  *download.Root
	once  sync.Once
	name  string
}

func (d *guideDownload) abort() {
	if d == nil {
		return
	}
	d.stage.Abort()
	d.once.Do(func() { _ = d.root.Close() })
}

func (d *guideDownload) publish() error {
	if err := d.stage.Publish(); err != nil {
		d.abort()
		return err
	}
	d.once.Do(func() { _ = d.root.Close() })
	return nil
}

func (m *Model) begin(kind readKind) tea.Cmd { return m.beginCursor(kind, "") }

func (m *Model) beginCursor(kind readKind, cursor string) tea.Cmd {
	m.invalidate()
	if kind == projectsRead || kind == pageRead {
		m.pageCursor = cursor
	}
	if kind == findingsRead {
		m.findingsPageCursor = cursor
	}
	m.failure, m.loading = "", true
	m.observed = time.Time{}
	r := request{generation: m.generation, actor: m.actor, project: m.project, tab: m.tab,
		kind: kind, page: m.page, section: m.section, cursor: cursor}
	if selected, ok := m.selectedRow(); ok {
		r.resource, r.task = selected.id, selected.task
	}
	m.request = r
	ctx, cancel := context.WithCancel(m.ctx)
	m.cancel = cancel
	client := m.client
	return func() (message tea.Msg) {
		// Never hand an application panic (which may contain a bearer) to the
		// renderer's diagnostic logger or process-wide panic machinery.
		defer func() {
			if recover() != nil {
				message = response{request: r, err: &api.Failure{Code: "request_failed"}}
			}
		}()
		var value any
		var err error
		var continuation *string
		if r.cursor != "" {
			continuation = &r.cursor
		}
		q := api.PageQuery{Limit: 50, Cursor: continuation}
		switch r.kind {
		case profileRead:
			var result api.Result[api.Profile]
			result, err = client.Profile(ctx)
			value = result.Value
		case projectsRead:
			var result api.Result[api.ActorProjectPage]
			result, err = client.MyProjects(ctx, q)
			value = result.Value
		case pageRead:
			q.ProjectID = &r.project
			switch r.tab {
			case ready:
				var result api.Result[api.ReadyTaskPage]
				result, err = client.ReadyTasks(ctx, r.project, 50, continuation)
				value = result.Value
			case mine:
				state := "active"
				q.State = &state
				var result api.Result[api.ContributorAssignmentPage]
				result, err = client.MyAssignments(ctx, q)
				value = result.Value
			case submissions:
				var result api.Result[api.ContributorSubmissionPage]
				result, err = client.MySubmissions(ctx, q)
				value = result.Value
			}
		case taskRead:
			var result api.Result[api.ContributorTaskDetail]
			result, err = client.ContributorTask(ctx, r.task)
			value = result.Value
		case submissionRead:
			var result api.Result[api.SubmissionHistory]
			result, err = client.Submission(ctx, r.resource)
			value = result.Value
		case contextRead:
			var result api.Result[api.WorkContext]
			result, err = client.WorkContext(ctx, r.task)
			value = result.Value
		case intakeRead:
			var result api.Result[api.SubmissionRequirements]
			result, err = client.SubmissionRequirements(ctx, r.task)
			value = result.Value
		case findingsRead:
			var result api.Result[api.SubmissionFindingsResult]
			result, err = client.SubmissionFindings(ctx, r.resource, "", 50, continuation)
			if result.Value.Page != nil {
				value = *result.Value.Page
			}
		}
		return response{request: r, value: value, err: err}
	}
}

func (m *Model) beginGuideDownload() tea.Cmd {
	if m.context == nil || m.guideSelected < 0 || m.guideSelected >= len(m.context.GuideDocuments) {
		return nil
	}
	document := m.context.GuideDocuments[m.guideSelected]
	m.invalidate()
	root, err := download.OpenRoot(m.guideDirectory)
	if err != nil {
		m.guideMode, m.guideNotice = guideBrowse, "Unavailable: "+m.clean(err.Error())
		return nil
	}
	stage, err := root.Stage(document.Filename())
	if err != nil {
		_ = root.Close()
		m.guideMode, m.guideNotice = guideBrowse, "Unavailable: "+m.clean(err.Error())
		return nil
	}
	work := &guideDownload{stage: stage, root: root, name: document.Filename()}
	m.download = work
	m.guideMode, m.guideNotice, m.failure, m.loading = guideBrowse, "", "", true
	m.observed = time.Time{}
	r := request{generation: m.generation, actor: m.actor, project: m.project, tab: m.tab,
		kind: guideDownloadRead, resource: m.selectedResource(), task: m.context.Task.TaskID,
		document: document.DocumentID, destination: m.guideDirectory, page: m.page, section: m.section}
	m.request = r
	ctx, cancel := context.WithCancel(m.ctx)
	m.cancel = cancel
	client := m.client
	return func() (message tea.Msg) {
		defer func() {
			if recover() != nil {
				work.abort()
				message = response{request: r, err: &api.Failure{Code: "request_failed"}, download: work}
			}
		}()
		err := client.DownloadGuideDocument(ctx, r.task, document, stage)
		if err == nil {
			err = stage.Seal()
		}
		if err != nil || ctx.Err() != nil {
			work.abort()
			if err == nil {
				err = ctx.Err()
			}
		}
		return response{request: r, err: err, download: work}
	}
}

func (m *Model) selectedResource() string {
	selected, _ := m.selectedRow()
	return selected.id
}

func sameID(a, b string) bool {
	return strings.EqualFold(strings.ReplaceAll(a, "-", ""), strings.ReplaceAll(b, "-", ""))
}

func (m *Model) receive(msg response) tea.Cmd {
	if msg.request != m.request || msg.request.generation != m.generation || !m.loading {
		if msg.download != nil {
			msg.download.abort()
		}
		return nil
	}
	m.loading = false
	if m.cancel != nil {
		m.cancel()
		m.cancel = nil
	}
	if msg.err != nil {
		if msg.download != nil {
			msg.download.abort()
			if m.download == msg.download {
				m.download = nil
			}
		}
		m.failed(msg.err, msg.request.kind == profileRead)
		return nil
	}
	bad := func() tea.Cmd { m.failed(&api.Failure{Code: "invalid_api_response"}, false); return nil }
	r := msg.request
	if r.kind == guideDownloadRead {
		if msg.download == nil || m.download != msg.download || r.tab != mine || r.section != 3 || m.context == nil ||
			!sameID(r.resource, m.selectedResource()) || !sameID(r.task, m.context.Task.TaskID) ||
			m.guideSelected < 0 || m.guideSelected >= len(m.context.GuideDocuments) ||
			!sameID(r.document, m.context.GuideDocuments[m.guideSelected].DocumentID) {
			if msg.download != nil {
				msg.download.abort()
			}
			return bad()
		}
		if err := msg.download.publish(); err != nil {
			m.download = nil
			m.guideNotice = "Unavailable: " + m.clean(err.Error())
			return nil
		}
		m.download = nil
		m.guideNotice = "Downloaded: " + m.clean(msg.download.name)
		m.observed = time.Now()
		return nil
	}
	switch value := msg.value.(type) {
	case api.Profile:
		if r.kind != profileRead || value.ActorProfileID == "" {
			return bad()
		}
		m.actor = value.ActorProfileID
		return m.begin(projectsRead)
	case api.ActorProjectPage:
		if r.kind != projectsRead {
			return bad()
		}
		for _, item := range value.Items {
			m.rows = append(m.rows, row{id: item.ProjectID, project: item.ProjectID, title: item.Name, status: item.Status})
		}
		m.cursor = value.Cursor
	case api.ReadyTaskPage:
		if r.kind != pageRead || r.tab != ready || !sameID(value.ProjectID, r.project) {
			return bad()
		}
		for _, item := range value.Items {
			if !sameID(item.ProjectID, r.project) {
				return bad()
			}
			m.rows = append(m.rows, row{id: item.TaskID, task: item.TaskID, project: item.ProjectID, title: item.Title, status: "ready"})
		}
		m.cursor = value.NextCursor
	case api.ContributorAssignmentPage:
		if r.kind != pageRead || r.tab != mine {
			return bad()
		}
		for _, item := range value.Items {
			if !sameID(item.ProjectID, r.project) || item.State != "active" {
				return bad()
			}
			m.rows = append(m.rows, row{id: item.AssignmentID, task: item.TaskID, project: item.ProjectID, title: item.Title, status: item.AssignmentStatus})
		}
		m.cursor = value.Cursor
	case api.ContributorSubmissionPage:
		if r.kind != pageRead || r.tab != submissions {
			return bad()
		}
		for _, item := range value.Items {
			if !sameID(item.ProjectID, r.project) {
				return bad()
			}
			m.rows = append(m.rows, row{id: item.SubmissionID, task: item.TaskID, project: item.ProjectID, title: item.Title, status: item.Status})
		}
		m.cursor = value.Cursor
	case api.ContributorTaskDetail:
		if r.kind != taskRead || !sameID(value.TaskID, r.task) || !sameID(value.ProjectID, r.project) {
			return bad()
		}
		m.task = &value
	case api.SubmissionHistory:
		if r.kind != submissionRead || !sameID(value.ID, r.resource) || !sameID(value.Task, r.task) {
			return bad()
		}
		m.submission = &value
	case api.WorkContext:
		if r.kind != contextRead || !sameID(value.Task.TaskID, r.task) || !sameID(value.Project.ID, r.project) ||
			!sameID(value.Task.ProjectID, r.project) || !sameID(value.Guide.ProjectID, r.project) ||
			(m.task != nil && !sameID(value.ContributionPolicyVersionID, m.task.Compensation.ContributionPolicyVersionID)) ||
			(m.intake != nil && value.Guide.Version != m.intake.GuideVersion) {
			return bad()
		}
		m.context = &value
		m.guideSelected = max(0, min(m.guideSelected, len(value.GuideDocuments)-1))
	case api.SubmissionRequirements:
		if r.kind != intakeRead || !sameID(value.TaskID, r.task) || !sameID(value.ProjectID, r.project) ||
			(m.context != nil && value.GuideVersion != m.context.Guide.Version) {
			return bad()
		}
		m.intake = &value
	case api.SubmissionCheckerPage:
		if r.kind != findingsRead || r.tab != submissions || r.section != 1 || !sameID(r.resource, m.selectedResource()) {
			return bad()
		}
		for _, run := range value.Items {
			if !sameID(run.Submission, r.resource) || !sameID(run.Task, r.task) {
				return bad()
			}
		}
		m.findings = &value
		m.findingsCursor = ""
		if value.Cursor != nil {
			m.findingsCursor = *value.Cursor
		}
	default:
		return bad()
	}
	m.observed = time.Now()
	m.viewport.GotoTop()
	return nil
}

func (m *Model) failed(err error, actorRead bool) {
	m.invalidate()
	m.clearPage()
	m.projectName = ""
	if m.write.mode == writeConfirm || m.write.mode == writeKeyEntry {
		if m.write.outcome == outcomeNone {
			m.write = writeState{}
		} else {
			m.write.mode, m.write.acknowledged, m.write.replay = writeIdle, false, false
		}
	}
	var failure *api.Failure
	if errors.As(err, &failure) {
		if failure.Status == 401 || failure.Status == 403 || failure.Status == 404 {
			m.write.replayDisabled = true
		}
		if failure.Status == 401 || (actorRead && failure.Status == 403) {
			m.blocked = true
			m.actor = ""
			m.project = ""
			m.request = request{}
		}
		label := "Unavailable"
		if failure.Status == 401 || failure.Status == 403 || failure.Status == 404 {
			label = "Denied"
		}
		m.failure = label + ": " + m.clean(failure.Code)
		if failure.Status != 0 {
			m.failure += fmt.Sprintf(" (HTTP %d)", failure.Status)
		}
		if failure.CorrelationID != "" {
			m.failure += " correlation " + m.clean(failure.CorrelationID)
		}
	} else {
		m.failure = "Unavailable: request_failed"
	}
	// No old observation survives a fresh refusal or transport failure.
	m.observed = time.Time{}
}
