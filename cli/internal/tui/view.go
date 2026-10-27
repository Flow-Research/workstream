package tui

import (
	"fmt"
	"strings"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
)

// fitText is for display labels, never exact identities or selectors.
func fitText(value string, width int) string {
	if width < 1 {
		return ""
	}
	if lipgloss.Width(value) <= width {
		return value
	}
	if width <= 3 {
		return strings.Repeat(".", width)
	}
	first, _, _ := strings.Cut(lipgloss.Wrap(value, width-3, ""), "\n")
	return first + "..."
}

func (m *Model) headerText() string {
	header := "WORKSTREAM / Contribute"
	if m.projectName != "" {
		header += " / " + m.clean(m.projectName)
	}
	return fitText(header, m.width)
}

func (m *Model) collectionText() string {
	if m.picker {
		return "Your projects"
	}
	labels := [...]string{"Ready", "Mine", "Submissions"}
	parts := make([]string, 0, len(labels))
	for i, label := range labels {
		if tab(i) == m.tab {
			label = "[" + label + "]"
		}
		parts = append(parts, label)
	}
	if m.width < 60 {
		return strings.Join(parts, " ") + " 1/2/3"
	}
	result := strings.Join(parts, "  ")
	if m.width >= 60 {
		result += "  1/2/3 select"
	}
	return result
}

func (m *Model) sectionText() string {
	if !m.detail || m.help || m.handoff || m.failure != "" || m.guideMode != guideBrowse {
		return ""
	}
	var labels []string
	switch m.tab {
	case mine:
		labels = []string{"Overview", "Context", "Intake", "Guide"}
	case submissions:
		labels = []string{"Overview", "Findings"}
	default:
		labels = []string{"Overview"}
	}
	for i := range labels {
		if i == m.section {
			labels[i] = "[" + labels[i] + "]"
		}
	}
	return strings.Join(labels, "  ")
}

func (m *Model) renderLabels(value string) string {
	styles := m.styles()
	parts := strings.Split(value, "  ")
	for i, part := range parts {
		if strings.HasPrefix(part, "[") {
			parts[i] = styles.focus.Render(part)
		} else {
			parts[i] = styles.secondary.Render(part)
		}
	}
	return strings.Join(parts, "  ")
}

func (m *Model) renderFooter() string {
	footer := m.footerText()
	styles := m.styles()
	for _, action := range []string{"d download", "y download"} {
		if at := strings.Index(footer, action); at >= 0 {
			return styles.secondary.Render(footer[:at]) + styles.action.Render(action) + styles.secondary.Render(footer[at+len(action):])
		}
	}
	return styles.secondary.Render(footer)
}

func (m *Model) footerText() string {
	if m.write.mode == writeKeyEntry {
		return "Enter review  Esc cancel  Ctrl+C quit"
	}
	if m.write.mode == writeConfirm {
		if m.width < 70 {
			return "s saved  y send  up/down inspect\nEsc cancel  q quit"
		}
		return "s saved  y send  arrows/PgUp/PgDn inspect  Esc cancel  q quit"
	}
	if m.write.mode == writePending {
		return "Sending one request...  q quit"
	}
	if m.write.mode == writeOutcome {
		if m.blocked {
			return "up/down inspect  Esc return  q quit"
		}
		if m.canReplay() && m.width < 65 {
			return "p replay  r read  up/down inspect\nEsc return  q quit"
		}
		if m.canReplay() {
			return "p replay  r read  arrows/PgUp/PgDn inspect  Esc return  q quit"
		}
		return "r read  arrows/PgUp/PgDn inspect  Esc return  q quit"
	}
	if m.guideMode == guideDestination {
		return "Enter review  Esc cancel  Ctrl+C quit"
	}
	if m.guideMode == guideConfirm {
		if m.width < 60 {
			return "y download  up/down  Esc cancel  q quit"
		}
		return "y download  arrows/PgUp/PgDn inspect  Esc cancel  q quit"
	}
	if m.filtering {
		return "Enter apply  Esc cancel  Ctrl+C quit"
	}
	if m.help {
		if m.width < 60 {
			return "up/down  ?/Esc close  q quit"
		}
		return "arrows/PgUp/PgDn scroll  ?/Esc close  q quit"
	}
	if m.handoff {
		if m.width < 60 {
			return "up/down  c/Esc close  q quit"
		}
		return "arrows/PgUp/PgDn scroll  c/Esc close  q quit"
	}
	if m.blocked {
		return "? help  q quit"
	}
	if m.failure != "" {
		return "r refresh  g projects  ? help  q quit"
	}
	if m.loading {
		return "Loading...  r refresh  ? help  q quit"
	}
	if m.canOpenAction() {
		if m.width < 60 {
			return "a actions  1/2/3 collections\nEsc back  r refresh  q quit"
		}
		if m.width < 90 {
			return "a actions  1/2/3 collections  Shift+Tab back\nr refresh  Esc back  q quit"
		}
		return "a actions  1 Ready  2 Mine  3 Submissions  Shift+Tab back  r refresh  Esc back  q quit"
	}
	if !m.detail && len(m.visible()) == 0 {
		navigation := "/ filter  r refresh"
		if !m.picker {
			navigation = "Tab collection  " + navigation
		}
		exit := "? help  q quit"
		if m.cursor != nil {
			exit = "n next  " + exit
		}
		return navigation + "\n" + exit
	}
	if m.height < 16 || m.width < 60 {
		if m.detail {
			if m.tab == mine && m.section == 3 {
				if m.context != nil && len(m.context.GuideDocuments) > 0 {
					return "Up/Down doc  PgUp/PgDn scroll\nd download  Tab  Esc back  ?  q quit"
				}
				return "PgUp/PgDn scroll  Tab section\nEsc back  ? help  q quit"
			}
			if m.tab == submissions && m.section == 1 {
				if m.findingsCursor != "" {
					return "Up/Down PgUp/PgDn scroll  Tab\nn next  Esc back  ? help  q quit"
				}
				return "Up/Down PgUp/PgDn scroll  Tab\nEsc back  ? help  q quit"
			}
			if m.tab == mine {
				return "PgUp/PgDn scroll  Tab section\nEsc back  ? help  q quit"
			}
			return "PgUp/PgDn scroll  Esc back\n? help  q quit"
		}
		if m.picker {
			if m.cursor != nil {
				return "Up/Down select  Enter project\n/ filter  n next  ? help  q quit"
			}
			return "Up/Down select  Enter project\n/ filter  ? help  q quit"
		}
		if m.cursor != nil {
			return "Up/Down select  Enter inspect\nTab  / filter  n next  ? help  q quit"
		}
		return "Up/Down select  Enter inspect\nTab collection  / filter  ? help  q quit"
	}
	if m.width >= 110 {
		switch {
		case m.detail && m.tab == mine && m.section == 3 && m.context != nil && len(m.context.GuideDocuments) > 0:
			return "arrows select/scroll  d download  Tab section  Esc back  r refresh  g projects  c CLI  ? help  q quit"
		case m.detail && m.tab == submissions && m.section == 1 && m.findingsCursor != "":
			return "arrows scroll  n next  Tab section  Esc back  r refresh  g projects  c CLI  ? help  q quit"
		case m.detail && m.tab != ready:
			return "arrows scroll  Tab section  Esc back  r refresh  g projects  c CLI  ? help  q quit"
		case m.detail:
			return "arrows scroll  Esc back  r refresh  g projects  c CLI  ? help  q quit"
		case m.picker && m.cursor != nil:
			return "arrows select  Enter project  / filter  n next  r refresh  c CLI  ? help  q quit"
		case m.picker:
			return "arrows select  Enter project  / filter  r refresh  c CLI  ? help  q quit"
		case m.cursor != nil:
			return "arrows select  Enter inspect  Tab collection  n next  / filter  r refresh  g projects  ? help  q quit"
		default:
			return "arrows select  Enter inspect  Tab collection  / filter  r refresh  g projects  ? help  q quit"
		}
	}
	if m.detail && m.tab == mine && m.section == 3 {
		if m.context == nil || len(m.context.GuideDocuments) == 0 {
			return "arrows scroll  Tab section  Esc back\nr refresh  g projects  c CLI  ? help  q quit"
		}
		return "arrows select/scroll  d download  Tab section  Esc back\nr refresh  g project  c CLI  ? help  q quit"
	}
	if m.detail && m.tab == submissions && m.section == 1 {
		if m.findingsCursor == "" {
			return "arrows/PgUp/PgDn scroll  Tab section  Esc back\nr refresh  g projects  c CLI  ? help  q quit"
		}
		return "arrows/PgUp/PgDn scroll  n next  Tab section  Esc back\nr refresh  g project  c CLI  ? help  q quit"
	}
	if m.detail {
		if m.tab == ready {
			return "arrows/PgUp/PgDn scroll  Esc back\nr refresh  g projects  c CLI  ? help  q quit"
		}
		return "arrows/PgUp/PgDn scroll  Tab section  Esc back\nr refresh  g project  c CLI  ? help  q quit"
	}
	if m.picker {
		if m.cursor == nil {
			return "arrows select  Enter project  / filter\nr refresh  c CLI  ? help  q quit"
		}
		return "arrows select  Enter project  / filter  n next\nr refresh  c CLI  ? help  q quit"
	}
	if m.cursor == nil {
		return "arrows select  Enter inspect  Tab collection  / filter\nr refresh  g projects  c CLI  ? help  q quit"
	}
	return "arrows select  Enter inspect  Tab collection  n next  / filter\nr refresh  g project  c CLI  ? help  q quit"
}

func (m *Model) statusText() string {
	if m.detail && m.tab == submissions && m.section == 1 {
		count := 0
		if m.findings != nil {
			count = len(m.findings.Items)
		}
		status := fmt.Sprintf("findings page %d | loaded %d runs", m.findingsPage, count)
		if m.findingsCursor != "" {
			status += " | more available"
		}
		if !m.observed.IsZero() {
			status += " | observed " + m.observed.Format("15:04:05")
		}
		return fitText(status, m.width)
	}
	status := fmt.Sprintf("page %d | loaded %d", m.page, len(m.rows))
	if m.cursor != nil {
		status += " | more available"
	}
	if !m.observed.IsZero() {
		status += " | observed " + m.observed.Format("15:04:05")
	}
	if m.filtering {
		return fitText("Filter fetched page only: "+m.clean(m.filter), m.width) + "\n" + fitText(status, m.width)
	}
	if m.filter != "" {
		return fitText("local filter: "+m.clean(m.filter), m.width) + "\n" + fitText(status, m.width)
	}
	return fitText(status, m.width)
}

func (m *Model) widePanes() bool {
	return m.width >= 100 && m.height >= 24 && !m.plain
}

func (m *Model) leftWidth() int { return min(36, max(30, m.width/3)) }

func padCells(value string, width int) string {
	return value + strings.Repeat(" ", max(0, width-lipgloss.Width(value)))
}

func (m *Model) View() tea.View {
	if m.closed {
		return tea.NewView("")
	}
	if m.tooSmall() {
		guidance := "Resize to at least 40x10. q quit"
		if m.filtering || m.guideMode == guideDestination || m.write.mode == writeKeyEntry {
			guidance = "Resize to at least 40x10. Ctrl+C quit"
		}
		v := tea.NewView(lipgloss.Wrap(guidance, max(1, m.width), ""))
		v.AltScreen = !m.plain
		return v
	}
	styles := m.styles()
	lines := []string{styles.heading.Render(m.headerText()), m.renderLabels(m.collectionText())}
	if section := m.sectionText(); section != "" {
		lines = append(lines, m.renderLabels(section))
	}
	lines = append(lines, styles.divider.Render(m.dividerText()))
	if m.showPanes() {
		leftWidth := m.leftWidth()
		left := m.listLines(leftWidth, m.viewport.Height())
		right := strings.Split(m.viewport.View(), "\n")
		for i := 0; i < m.viewport.Height(); i++ {
			var l, r string
			if i < len(left) {
				l = left[i]
			}
			if i < len(right) {
				r = right[i]
			}
			lines = append(lines, padCells(l, leftWidth)+" "+styles.divider.Render("|")+" "+r)
		}
	} else {
		lines = append(lines, m.viewport.View())
	}
	lines = append(lines, styles.secondary.Render(m.statusText()), m.renderFooter())
	v := tea.NewView(strings.Join(lines, "\n"))
	v.AltScreen = !m.plain
	return v
}

func (m *Model) showPanes() bool {
	return m.widePanes() && m.guideMode == guideBrowse && m.write.mode == writeIdle && !m.help && !m.handoff && m.failure == "" && !m.loading && m.started
}

func (m *Model) dividerText() string {
	unit := "─"
	if m.plain {
		unit = "-"
	}
	return strings.Repeat(unit, m.width)
}

func (m *Model) reflow() {
	if m.width < 1 || m.height < 1 {
		return
	}
	reserved := 1 + 1 + 1 + lipgloss.Height(m.statusText()) + lipgloss.Height(m.footerText())
	if m.sectionText() != "" {
		reserved++
	}
	width := m.width
	if m.showPanes() {
		width -= m.leftWidth() + 3
	}
	m.viewport.SetWidth(width)
	m.viewport.SetHeight(max(1, m.height-reserved))
	m.viewport.SetContent(lipgloss.Wrap(m.body(), width, ""))
}

func (m *Model) body() string {
	if m.write.mode != writeIdle {
		return m.writeText()
	}
	if m.help {
		return "KEYBOARD HELP\n\nNavigate\nArrows select a row/document or scroll detail. 1 Ready, 2 Mine, 3 Submissions select collections. Tab advances and Shift+Tab reverses collections or visible detail sections. Esc returns.\n\nInspect\nEnter reads one exact selected resource. r explicitly refreshes; g opens a fresh project picker. / filters only the loaded page.\n\nActions\na on an inspected Ready task or claimed Mine Overview opens Claim or Start. Enter reviews your externally saved UUID; s acknowledges the save warning and y sends one POST. p explicitly replays the exact prior packet when offered. No automatic retry or chained start.\n\nPages\nn requests exactly one next list or findings page. No polling or project-wide count is implied.\n\nGuide downloads\nd enters a destination for the selected guide original; Enter reviews and y confirms. Esc cancels without downloading.\n\nExit\nc shows inert CLI arguments. q or Ctrl+C quits. ? or Esc closes help.\n\nChecker evidence is not acceptance. A read is not a reservation or authority."
	}
	if m.handoff {
		return m.handoffText()
	}
	if m.failure != "" {
		return m.writeBanner() + m.styles().error.Render(m.failure) + "\nNo retained page or detail is available. A failed read does not change a prior write outcome.\n" + m.failureHelp()
	}
	if m.loading {
		return m.loadingText()
	}
	if !m.started {
		return "Waiting for terminal size..."
	}
	if m.detail {
		return m.writeBanner() + m.detailText()
	}
	if m.widePanes() {
		return m.writeBanner() + m.previewText()
	}
	return m.writeBanner() + m.listText(m.width)
}

func (m *Model) loadingText() string {
	switch m.request.kind {
	case profileRead:
		return "Loading actor profile..."
	case projectsRead:
		return "Loading projects..."
	case pageRead:
		return "Loading " + strings.ToLower(m.tab.String()) + " page..."
	case taskRead:
		return "Loading task overview..."
	case contextRead:
		return "Loading locked context and guide..."
	case intakeRead:
		return "Loading intake requirements..."
	case submissionRead:
		return "Loading submission overview..."
	case findingsRead:
		return "Loading checker findings..."
	case guideDownloadRead:
		return "Downloading selected guide original..."
	}
	return "Loading..."
}

func (m *Model) failureHelp() string {
	if m.blocked {
		return "Session unavailable. Quit and supply a valid bearer through the existing environment.\n? help | q quit"
	}
	return "r explicit refresh | g fresh project picker | ? help | q quit"
}

func (m *Model) previewText() string {
	selected, ok := m.selectedRow()
	if !ok {
		return "No row selected on this loaded page.\nUse / to adjust the local filter."
	}
	return "Selected on this page\n" + m.clean(selected.title) + "\nStatus: " + m.clean(selected.status) + "\nProject ID: " + m.clean(selected.project) + "\n\nEnter to inspect full details.\nA list summary is not full instructions or a reservation."
}

func (m *Model) listText(width int) string {
	return strings.Join(m.listLines(width, max(1, m.viewport.Height())), "\n")
}

func (m *Model) listLines(width, height int) []string {
	rows := m.visible()
	if len(rows) == 0 {
		if m.filter != "" && len(m.rows) > 0 {
			return []string{"No matches on this fetched page.", "Clear / to see loaded rows."}
		}
		return []string{"No rows on this fetched page.", "This is not a project-wide count."}
	}
	first := max(0, m.selected-height+1)
	if first > len(rows)-height {
		first = max(0, len(rows)-height)
	}
	end := min(len(rows), first+height)
	lines := make([]string, 0, end-first)
	for i := first; i < end; i++ {
		mark := "  "
		if i == m.selected {
			mark = "> "
		}
		status := fitText(m.clean(rows[i].status), max(1, width/3))
		available := max(1, width-lipgloss.Width(status)-5)
		title := fitText(m.clean(rows[i].title), available)
		line := mark + title + " [" + status + "]"
		if i == m.selected {
			styles := m.styles()
			marker := styles.focus
			if m.detail {
				marker = styles.secondary
			}
			line = marker.Render(">") + styles.selected.Render(padCells(" "+title+" ["+status+"]", width-1))
		}
		lines = append(lines, line)
	}
	return lines
}
