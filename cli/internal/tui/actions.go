package tui

import (
	"context"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"

	tea "charm.land/bubbletea/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
)

type writeMode int

const (
	writeIdle writeMode = iota
	writeKeyEntry
	writeConfirm
	writePending
	writeOutcome
)

type writeOutcomeKind int

const (
	outcomeNone writeOutcomeKind = iota
	outcomeConfirmed
	outcomeDenied
	outcomeUnknown
)

type writePacket struct {
	action, actor, project, task, key string
}

type writeState struct {
	mode           writeMode
	packet         writePacket
	outcome        writeOutcomeKind
	keyInput       string
	notice         string
	acknowledged   bool
	replay         bool
	replayDisabled bool
	sequence       uint64
}

type writeResponse struct {
	packet     writePacket
	generation uint64
	sequence   uint64
	value      any
	err        error
}

var replayUUID = regexp.MustCompile(`(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)
var replayUUIDCharacters = regexp.MustCompile(`(?i)^[0-9a-f-]+$`)

func (m *Model) paste(value string) {
	if m.closed || m.tooSmall() || m.write.mode != writeKeyEntry {
		return
	}
	if len(value) == 0 || len(m.write.keyInput)+len(value) > 100 || !replayUUIDCharacters.MatchString(value) {
		m.write.notice = "Paste one UUID without spaces or control characters. No action was sent."
		return
	}
	m.write.keyInput += value
	m.write.notice = ""
}

func (m *Model) actionName() string {
	if m.tab == ready && m.task != nil && m.task.Status == "ready" {
		return "Claim"
	}
	if m.tab == mine && m.section == 0 && m.task != nil && m.task.Status == "claimed" {
		return "Start"
	}
	return ""
}

func (m *Model) canOpenAction() bool {
	selected, ok := m.selectedRow()
	return m.detail && !m.loading && m.failure == "" && m.section == 0 &&
		m.write.outcome != outcomeUnknown && m.actionName() != "" && ok &&
		!(m.write.outcome == outcomeConfirmed && sameID(m.write.packet.task, m.task.TaskID) && m.write.packet.action == strings.ToLower(m.actionName())) &&
		sameID(selected.task, m.task.TaskID) && sameID(selected.project, m.task.ProjectID) &&
		sameID(m.project, m.task.ProjectID) && m.actor != ""
}

func (m *Model) openAction() {
	action := strings.ToLower(m.actionName())
	m.write = writeState{mode: writeKeyEntry, packet: writePacket{
		action: action, actor: m.actor, project: m.project, task: m.task.TaskID,
	}}
	m.viewport.GotoTop()
}

func (m *Model) canReplay() bool {
	return !m.closed && !m.blocked && !m.loading && !m.write.replayDisabled && m.write.packet.key != "" &&
		(m.write.outcome == outcomeUnknown || m.write.outcome == outcomeConfirmed)
}

func (m *Model) writeKey(key tea.KeyPressMsg) tea.Cmd {
	k := key.String()
	switch m.write.mode {
	case writeKeyEntry:
		switch k {
		case "esc":
			m.write = writeState{}
		case "enter":
			if replayUUID.MatchString(m.write.keyInput) {
				m.write.packet.key = m.write.keyInput
				m.write.keyInput, m.write.notice = "", ""
				m.write.mode = writeConfirm
			} else {
				m.write.notice = "Enter a caller-owned UUID saved outside this session."
			}
		case "backspace":
			_, size := utf8.DecodeLastRuneInString(m.write.keyInput)
			if size > 0 {
				m.write.keyInput = m.write.keyInput[:len(m.write.keyInput)-size]
			}
		default:
			if key.Text != "" && len(m.write.keyInput)+len(key.Text) <= 100 {
				m.write.keyInput += key.Text
			}
		}
	case writeConfirm:
		switch k {
		case "esc":
			if m.write.replay {
				m.write.mode = writeOutcome
				m.write.replay = false
			} else {
				m.write = writeState{}
			}
		case "s":
			m.write.acknowledged = true
		case "y":
			if m.write.acknowledged && !m.tooSmall() {
				return m.beginWrite()
			}
		default:
			return m.scroll(k)
		}
	case writeOutcome:
		switch k {
		case "p":
			if m.canReplay() {
				m.write.mode, m.write.acknowledged, m.write.replay = writeConfirm, false, true
			}
		case "r":
			if !m.blocked {
				m.write.mode = writeIdle
				if m.detail {
					m.task, m.context, m.intake, m.submission = nil, nil, nil, nil
					return m.begin(m.detailKind())
				}
				m.clearPage()
				return m.begin(pageRead)
			}
		case "esc":
			m.write.mode = writeIdle
		default:
			return m.scroll(k)
		}
	}
	return nil
}

func (m *Model) beginWrite() tea.Cmd {
	packet := m.write.packet
	if m.closed || m.ctx.Err() != nil || m.blocked || m.write.replayDisabled || m.loading || m.tooSmall() ||
		m.write.mode != writeConfirm || !m.write.acknowledged ||
		(packet.action != "claim" && packet.action != "start") ||
		!replayUUID.MatchString(packet.key) || !sameID(packet.actor, m.actor) {
		if m.write.mode == writeConfirm {
			m.write.mode, m.write.acknowledged, m.write.replay = writeOutcome, false, false
			m.write.notice = "Not sent: confirmation expired after read or session state changed. No POST was dispatched."
		}
		return nil
	}
	m.invalidate()
	m.write.mode, m.write.sequence = writePending, m.write.sequence+1
	m.write.notice = ""
	generation, sequence := m.generation, m.write.sequence
	ctx, cancel := context.WithCancel(m.ctx)
	m.cancel = cancel
	client := m.client
	return func() (message tea.Msg) {
		if ctx.Err() != nil {
			return writeResponse{packet: packet, generation: generation, sequence: sequence,
				err: &api.Failure{Code: "request_failed", OutcomeUnknown: true}}
		}
		defer func() {
			if recover() != nil {
				message = writeResponse{packet: packet, generation: generation, sequence: sequence,
					err: &api.Failure{Code: "request_failed", OutcomeUnknown: true}}
			}
		}()
		var value any
		var err error
		if packet.action == "claim" {
			var result api.Result[api.ClaimedTask]
			result, err = client.ClaimTask(ctx, packet.task, packet.key, nil)
			value = result.Value
		} else {
			var result api.Result[api.MutationTask]
			result, err = client.StartTask(ctx, packet.task, packet.key, nil)
			value = result.Value
		}
		return writeResponse{packet: packet, generation: generation, sequence: sequence, value: value, err: err}
	}
}

func (m *Model) receiveWrite(msg writeResponse) {
	if m.write.mode != writePending || msg.packet != m.write.packet ||
		msg.generation != m.generation || msg.sequence != m.write.sequence {
		return
	}
	if m.cancel != nil {
		m.cancel()
		m.cancel = nil
	}
	m.write.mode = writeOutcome
	m.write.acknowledged = false
	packet := msg.packet
	if msg.err == nil {
		valid := false
		switch v := msg.value.(type) {
		case api.ClaimedTask:
			valid = packet.action == "claim" && sameID(v.Task.ID, packet.task) &&
				sameID(v.Task.ProjectID, packet.project) && v.Task.Status == "claimed" &&
				sameID(v.Assignment.TaskID, packet.task) && sameID(v.Assignment.ProjectID, packet.project) &&
				sameID(v.Assignment.ContributorID, packet.actor)
		case api.MutationTask:
			valid = packet.action == "start" && sameID(v.ID, packet.task) &&
				sameID(v.ProjectID, packet.project) && v.Status == "in_progress"
		}
		if valid {
			m.write.outcome, m.write.notice = outcomeConfirmed, "Validated receipt. A later read is a separate observation."
			m.observed = time.Now()
			m.viewport.GotoTop()
			return
		}
		msg.err = &api.Failure{Code: "invalid_api_response", OutcomeUnknown: true}
	}
	var failure *api.Failure
	knownDenial := errors.As(msg.err, &failure) && !failure.OutcomeUnknown && failure.Status >= 400 && failure.Status < 500
	if knownDenial {
		if m.write.outcome == outcomeNone {
			m.write.outcome = outcomeDenied
		}
		m.write.notice = "Request denied: " + m.clean(failure.Code) + fmt.Sprintf(" (HTTP %d).", failure.Status)
		if m.write.outcome == outcomeUnknown {
			m.write.notice += " Earlier outcome remains unknown."
		}
		if m.write.outcome == outcomeConfirmed {
			m.write.notice += " Earlier validated receipt remains confirmed."
		}
	} else {
		if m.write.outcome == outcomeConfirmed {
			m.write.notice = "Replay response unknown; earlier validated receipt remains confirmed."
		} else {
			m.write.outcome = outcomeUnknown
			m.write.notice = "Outcome unknown: response was not validated. Do not use a new key for this action."
		}
	}
	if errors.As(msg.err, &failure) && (failure.Status == 401 || failure.Status == 403 || failure.Status == 404) {
		m.clearPage()
		m.projectName = ""
		m.write.replayDisabled = true
		if failure.Status == 401 {
			m.blocked = true
			m.actor, m.project = "", ""
		}
	}
	m.viewport.GotoTop()
}

func (m *Model) writeText() string {
	w := m.write
	p := w.packet
	d := detailWriter{m: m}
	switch w.mode {
	case writeKeyEntry:
		d.heading("Caller-owned replay key")
		d.note("Save a UUID outside this session before continuing. This workbench does not generate or persist a recovery key.")
		d.line("Action", strings.Title(p.action))
		d.line("Task", p.task)
		d.line("UUID", w.keyInput)
		d.note("Enter reviews; Esc cancels. No write has been sent.")
	case writeConfirm:
		d.heading("Confirm " + p.action)
		d.line("Action", strings.Title(p.action))
		d.line("Actor", p.actor)
		d.line("Project", p.project)
		d.line("Task", p.task)
		d.line("Replay key", p.key)
		if m.task != nil && sameID(m.task.TaskID, p.task) && sameID(m.task.ProjectID, p.project) {
			d.line("Contribution policy version", m.task.Compensation.ContributionPolicyVersionID)
			for _, term := range []struct {
				label string
				raw   []byte
			}{{"Accepted submission terms", m.task.Compensation.AcceptedSubmission}, {"Completed review terms", m.task.Compensation.CompletedReview}} {
				awards, ok := api.CompensationAwards(term.raw)
				if !ok {
					d.line(term.label, "unavailable")
				} else if len(awards) == 0 {
					d.line(term.label, "unpaid")
				} else {
					for _, award := range awards {
						d.line(term.label, award.Instrument+" / "+award.Unit+" / "+award.Quantity)
					}
				}
			}
		} else {
			d.note("Locked terms are not retained here; inspect fresh task detail before relying on them.")
		}
		if w.replay {
			if w.outcome == outcomeUnknown {
				d.note("Replay uses the exact prior action, actor, project, task and key. Earlier uncertainty remains until a validated receipt.")
			} else {
				d.note("Replay uses the exact prior action, actor, project, task and key. The prior validated receipt remains confirmed.")
			}
		}
		d.note("Save this key outside the session. The workbench cannot verify your copy.")
		if w.acknowledged {
			d.note("Save warning acknowledged. Press y to send one POST; Esc cancels.")
		} else {
			d.note("Press s to acknowledge saving, then y to send one POST. Esc cancels.")
		}
	case writePending:
		d.heading("Sending " + p.action)
		d.line("Task", p.task)
		d.line("Replay key", p.key)
		d.note("One POST is pending. Quit cancels the client request, not possible server effects.")
	case writeOutcome:
		d.note(m.writeSummary())
		d.line("Action", p.action)
		d.line("Actor", p.actor)
		d.line("Project", p.project)
		d.line("Task", p.task)
		d.line("Replay key", p.key)
		d.note(m.clean(w.notice))
		d.note(m.clean("Recovery CLI arguments: workstream task " + p.action + " " + p.task + " --idempotency-key " + p.key))
		if m.canReplay() {
			d.note("p reviews explicit same-packet replay; no automatic retry.")
		}
		if m.blocked {
			d.note("Session unavailable; replay and reads are disabled here. Quit and use the externally saved key for recovery.")
		} else {
			d.note("r separately refreshes the read; Esc returns. A read cannot prove rollback.")
		}
	}
	if w.notice != "" && w.mode == writeKeyEntry {
		d.note(m.clean(w.notice))
	}
	return d.String()
}

func (m *Model) writeSummary() string {
	switch m.write.outcome {
	case outcomeNone:
		return "Not sent"
	case outcomeConfirmed:
		if m.write.packet.action == "claim" {
			return "Claim confirmed"
		}
		return "Start confirmed"
	case outcomeDenied:
		return "Request denied"
	case outcomeUnknown:
		return "Outcome unknown"
	}
	return ""
}

func (m *Model) writeBanner() string {
	if m.write.outcome != outcomeConfirmed && m.write.outcome != outcomeUnknown {
		return ""
	}
	p := m.write.packet
	guidance := "p reviews its exact packet."
	if !m.canReplay() {
		guidance = "In-session replay unavailable; use saved inputs with the CLI after authority is restored."
	}
	return "Prior operation: " + m.writeSummary() + " | task " + m.clean(p.task) +
		" | project " + m.clean(p.project) + ". " + guidance + "\n\n"
}
