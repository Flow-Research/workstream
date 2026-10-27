// Package tui presents contributor observations through the existing public client.
package tui

import (
	"context"
	"strings"
	"time"
	"unicode/utf8"

	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
)

type tab int

const (
	ready tab = iota
	mine
	submissions
)

func (t tab) String() string { return [...]string{"READY", "MINE", "SUBMISSIONS"}[t] }

type row struct {
	id, task, project, title, status string
}

type guideMode int

const (
	guideBrowse guideMode = iota
	guideDestination
	guideConfirm
)

// Model owns one fetched page and one exact detail, never an authority cache.
type Model struct {
	client                                            Client
	ctx                                               context.Context
	stop                                              context.CancelFunc
	cancel                                            context.CancelFunc
	token                                             string
	plain, noColor                                    bool
	backgroundKnown, darkBackground                   bool
	width, height                                     int
	started, closed, blocked, picker, detail, loading bool
	help, handoff, filtering                          bool
	filter, savedFilter                               string
	actor, project, projectName                       string
	tab                                               tab
	section                                           int
	rows                                              []row
	selected, page                                    int
	cursor                                            *string
	pageCursor                                        string
	request                                           request
	generation                                        uint64
	failure                                           string
	observed                                          time.Time
	task                                              *api.ContributorTaskDetail
	context                                           *api.WorkContext
	intake                                            *api.SubmissionRequirements
	submission                                        *api.SubmissionHistory
	findings                                          *api.SubmissionCheckerPage
	findingsCursor, findingsPageCursor                string
	findingsPage                                      int
	guideSelected                                     int
	guideMode                                         guideMode
	guideDirectory, guideNotice                       string
	download                                          *guideDownload
	viewport                                          viewport.Model
	write                                             writeState
}

// New has no I/O; the first adequately sized terminal event starts actor binding.
func New(ctx context.Context, client Client, token string, plain, noColor bool) *Model {
	ctx, stop := context.WithCancel(ctx)
	return &Model{ctx: ctx, stop: stop, client: client, token: token, plain: plain,
		noColor: noColor || plain, picker: true, page: 1, viewport: viewport.New()}
}

func (m *Model) Init() tea.Cmd {
	if m.noColor {
		return nil
	}
	return tea.RequestBackgroundColor
}

// Close cancels outstanding reads after the program has stopped, including errors.
func (m *Model) Close() { m.closed = true; m.invalidate(); m.stop() }

func (m *Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	defer m.reflow()
	if m.closed {
		return m, nil
	}
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = min(max(msg.Width, 1), 300), min(max(msg.Height, 1), 150)
		if !m.started && !m.tooSmall() {
			m.started = true
			return m, m.begin(profileRead)
		}
	case tea.BackgroundColorMsg:
		m.backgroundKnown, m.darkBackground = true, msg.IsDark()
	case response:
		return m, m.receive(msg)
	case writeResponse:
		m.receiveWrite(msg)
		return m, nil
	case tea.PasteMsg:
		m.paste(msg.Content)
		return m, nil
	case tea.KeyPressMsg:
		return m, m.key(msg)
	}
	return m, nil
}

func (m *Model) tooSmall() bool { return m.width < 40 || m.height < 10 }

func (m *Model) invalidate() {
	if m.cancel != nil {
		m.cancel()
		m.cancel = nil
	}
	if m.download != nil {
		m.download.abort()
		m.download = nil
	}
	m.generation++
	m.loading = false
}

func (m *Model) clearDetail() {
	m.detail, m.section = false, 0
	m.task, m.context, m.intake, m.submission, m.findings = nil, nil, nil, nil, nil
	m.findingsCursor, m.findingsPageCursor, m.findingsPage = "", "", 1
	m.guideSelected, m.guideMode, m.guideDirectory, m.guideNotice = 0, guideBrowse, "", ""
	m.handoff = false
	m.viewport.GotoTop()
}

func (m *Model) clearPage() {
	m.rows, m.cursor = nil, nil
	m.pageCursor = ""
	m.selected, m.page = 0, 1
	m.filter, m.savedFilter, m.failure = "", "", ""
	m.filtering = false
	m.observed = time.Time{}
	m.clearDetail()
}

func (m *Model) visible() []row {
	if m.filter == "" {
		return m.rows
	}
	rows := make([]row, 0, len(m.rows))
	for _, row := range m.rows {
		if strings.Contains(strings.ToLower(m.clean(row.title)), strings.ToLower(m.clean(m.filter))) {
			rows = append(rows, row)
		}
	}
	return rows
}

func (m *Model) selectedRow() (row, bool) {
	rows := m.visible()
	if m.selected < 0 || m.selected >= len(rows) {
		return row{}, false
	}
	return rows[m.selected], true
}

func (m *Model) key(key tea.KeyPressMsg) tea.Cmd {
	k := key.String()
	if k == "ctrl+c" || (!m.filtering && m.guideMode != guideDestination && m.write.mode != writeKeyEntry && k == "q") {
		m.closed = true
		m.invalidate()
		m.stop()
		return tea.Quit
	}
	if m.write.mode == writePending {
		return nil
	}
	if m.write.mode == writeKeyEntry || m.write.mode == writeConfirm || m.write.mode == writeOutcome {
		if m.tooSmall() {
			return nil
		}
		return m.writeKey(key)
	}
	if m.filtering {
		switch k {
		case "enter":
			m.filtering = false
		case "esc":
			m.filter, m.filtering = m.savedFilter, false
		case "backspace":
			_, size := utf8.DecodeLastRuneInString(m.filter)
			if size > 0 {
				m.filter = m.filter[:len(m.filter)-size]
			}
		default:
			if key.Text != "" && len(m.filter)+len(key.Text) <= 256 {
				m.filter += key.Text
			}
		}
		m.selected = 0
		return nil
	}
	if m.guideMode == guideDestination {
		switch k {
		case "enter":
			if m.guideDirectory != "" {
				m.guideMode = guideConfirm
				m.viewport.GotoTop()
			}
		case "esc":
			m.guideMode, m.guideDirectory = guideBrowse, ""
		case "backspace":
			_, size := utf8.DecodeLastRuneInString(m.guideDirectory)
			if size > 0 {
				m.guideDirectory = m.guideDirectory[:len(m.guideDirectory)-size]
			}
		default:
			if key.Text != "" && len(m.guideDirectory)+len(key.Text) <= 4096 {
				m.guideDirectory += key.Text
			}
		}
		return nil
	}
	if m.guideMode == guideConfirm {
		if k == "esc" {
			m.guideMode, m.guideDirectory = guideBrowse, ""
			return nil
		}
		if k == "y" {
			if m.tooSmall() {
				return nil
			}
			return m.beginGuideDownload()
		}
		return m.scroll(k)
	}
	if k == "?" {
		m.help, m.handoff = !m.help, false
		m.viewport.GotoTop()
		return nil
	}
	if k == "esc" && (m.help || m.handoff) {
		m.help, m.handoff = false, false
		return nil
	}
	if m.help {
		return m.scroll(k)
	}
	if m.blocked || m.tooSmall() {
		return nil
	}
	if k == "c" {
		m.handoff = !m.handoff
		m.viewport.GotoTop()
		return nil
	}
	if m.handoff {
		return m.scroll(k)
	}
	if k == "g" && m.actor != "" {
		m.invalidate()
		m.clearPage()
		m.picker = true
		m.project, m.projectName = "", ""
		return m.begin(projectsRead)
	}
	if k == "p" && m.canReplay() {
		m.write.mode, m.write.acknowledged, m.write.replay = writeConfirm, false, true
		return nil
	}
	if k == "a" && m.canOpenAction() {
		m.openAction()
		return nil
	}
	if !m.picker && (k == "1" || k == "2" || k == "3") {
		target := tab(int(k[0] - '1'))
		if target != m.tab || m.detail {
			m.invalidate()
			m.clearPage()
			m.tab = target
			return m.begin(pageRead)
		}
		return nil
	}
	if k == "esc" && m.detail {
		if m.tab == submissions && m.section == 1 {
			m.invalidate()
			m.section, m.findings = 0, nil
			m.findingsCursor, m.findingsPageCursor, m.findingsPage = "", "", 1
			m.viewport.GotoTop()
			return nil
		}
		m.invalidate()
		m.clearDetail()
		m.failure = ""
		return nil
	}
	if (k == "tab" || k == "shift+tab") && !m.picker && !m.detail {
		m.invalidate()
		m.clearPage()
		if k == "tab" {
			m.tab = (m.tab + 1) % 3
		} else {
			m.tab = (m.tab + 2) % 3
		}
		return m.begin(pageRead)
	}
	if k == "r" {
		if m.detail {
			m.guideNotice = ""
			if m.tab == submissions && m.section == 1 {
				m.findings, m.findingsCursor, m.findingsPageCursor, m.findingsPage = nil, "", "", 1
				return m.begin(findingsRead)
			}
			m.context, m.intake, m.task, m.submission = nil, nil, nil, nil
			return m.begin(m.detailKind())
		}
		m.clearPage()
		if m.actor == "" {
			return m.begin(profileRead)
		}
		if m.picker {
			return m.begin(projectsRead)
		}
		return m.begin(pageRead)
	}
	if m.loading || m.failure != "" {
		return nil
	}
	if m.detail {
		if (k == "tab" || k == "shift+tab") && m.tab == mine {
			if k == "tab" {
				m.section = (m.section + 1) % 4
			} else {
				m.section = (m.section + 3) % 4
			}
			m.viewport.GotoTop()
			switch m.section {
			case 1:
				return m.begin(contextRead)
			case 2:
				return m.begin(intakeRead)
			case 3:
				return m.begin(contextRead)
			}
		}
		if (k == "tab" || k == "shift+tab") && m.tab == submissions {
			m.invalidate()
			m.section = (m.section + 1) % 2
			m.viewport.GotoTop()
			if m.section == 1 {
				m.findings, m.findingsCursor, m.findingsPageCursor, m.findingsPage = nil, "", "", 1
				return m.begin(findingsRead)
			}
			m.findings = nil
			return nil
		}
		if m.tab == mine && m.section == 3 && m.context != nil {
			switch k {
			case "up":
				m.guideSelected = max(0, m.guideSelected-1)
				m.viewport.GotoTop()
			case "down":
				m.guideSelected = min(max(0, len(m.context.GuideDocuments)-1), m.guideSelected+1)
				m.viewport.GotoTop()
			case "d":
				if len(m.context.GuideDocuments) > 0 {
					m.guideMode, m.guideDirectory, m.guideNotice = guideDestination, "", ""
				}
			default:
				return m.scroll(k)
			}
			return nil
		}
		if m.tab == submissions && m.section == 1 {
			if k == "n" && m.findingsCursor != "" {
				cursor := m.findingsCursor
				m.findings, m.findingsCursor = nil, ""
				m.findingsPage++
				return m.beginCursor(findingsRead, cursor)
			}
			return m.scroll(k)
		}
		return m.scroll(k)
	}
	switch k {
	case "/":
		m.filtering, m.savedFilter = true, m.filter
	case "up":
		m.selected = max(0, m.selected-1)
	case "down":
		m.selected = min(max(0, len(m.visible())-1), m.selected+1)
	case "n":
		if m.cursor != nil {
			cursor := *m.cursor
			m.rows, m.cursor = nil, nil
			m.selected = 0
			m.page++
			m.filter = ""
			if m.picker {
				return m.beginCursor(projectsRead, cursor)
			}
			return m.beginCursor(pageRead, cursor)
		}
	case "enter":
		if selected, ok := m.selectedRow(); ok {
			if m.picker {
				m.project, m.projectName = selected.id, selected.title
				m.picker, m.tab = false, ready
				m.clearPage()
				return m.begin(pageRead)
			}
			m.clearDetail()
			m.detail = true
			return m.begin(m.detailKind())
		}
	}
	return nil
}

func (m *Model) detailKind() readKind {
	if m.tab == submissions {
		if m.section == 1 {
			return findingsRead
		}
		return submissionRead
	}
	switch m.section {
	case 1, 3:
		return contextRead
	case 2:
		return intakeRead
	}
	return taskRead
}

func (m *Model) scroll(key string) tea.Cmd {
	switch key {
	case "down":
		m.viewport.ScrollDown(1)
	case "up":
		m.viewport.ScrollUp(1)
	case "pgdown":
		m.viewport.ScrollDown(max(1, m.viewport.Height()-1))
	case "pgup":
		m.viewport.ScrollUp(max(1, m.viewport.Height()-1))
	}
	return nil
}
