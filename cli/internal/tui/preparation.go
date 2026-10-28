package tui

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os"
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"

	tea "charm.land/bubbletea/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
)

func (m *Model) preparationEntry() bool {
	return m.write.mode == writePreparePath || m.write.mode == writePrepareSummary || m.write.mode == writePrepareAttestation
}

func printableASCII(value string) bool {
	for _, b := range []byte(value) {
		if b < 32 || b > 126 {
			return false
		}
	}
	return true
}

func (m *Model) appendPreparationInput(value string) {
	limit := 64 * 1024
	valid := printableASCII(value)
	if m.write.mode == writePreparePath {
		limit = 4096
		valid = utf8.ValidString(value)
		for _, r := range value {
			if !unicode.IsPrint(r) || unicode.Is(unicode.Cf, r) || r == '\u2028' || r == '\u2029' {
				valid = false
			}
		}
	}
	if !valid || len(m.write.input)+len(value) > limit {
		m.write.notice = "Input rejected: use printable text within the displayed limit (ASCII for packet fields); no control characters or multiline paste."
		return
	}
	m.write.input += value
	m.write.notice = ""
}

func (m *Model) preparationKey(key tea.KeyPressMsg) tea.Cmd {
	switch key.String() {
	case "esc":
		m.write = writeState{}
	case "backspace":
		if len(m.write.input) > 0 {
			_, size := utf8.DecodeLastRuneInString(m.write.input)
			m.write.input = m.write.input[:len(m.write.input)-size]
		}
	case "enter":
		value := m.write.input
		if m.write.mode == writePreparePath {
			if value == "" {
				m.write.notice = "Enter one regular ZIP path, at most 4096 UTF-8 bytes."
				return nil
			}
			m.write.packet.path, m.write.mode = value, writePrepareSummary
		} else {
			if strings.TrimSpace(value) != value {
				m.write.notice = "Header-edge whitespace is not supported; edit it explicitly. Text is never trimmed."
				return nil
			}
			if m.write.mode == writePrepareSummary {
				m.write.packet.summary, m.write.mode = value, writePrepareAttestation
			} else {
				m.write.packet.attestation, m.write.mode = value, writeKeyEntry
			}
		}
		m.write.input, m.write.notice = "", ""
		m.viewport.GotoTop()
	default:
		if key.Text != "" {
			m.appendPreparationInput(key.Text)
		} else {
			return m.scroll(key.String())
		}
	}
	return nil
}

type preparationHashResponse struct {
	packet     writePacket
	generation uint64
	digest     string
	bytes      int64
	err        error
}

// Opening and hashing belong to commands; render state never owns a descriptor.
func openPreparationZIP(path string) (*os.File, error) {
	f, err := openPreparationSource(path)
	if err != nil {
		return nil, errors.New("ZIP unavailable")
	}
	info, err := f.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() <= 0 || info.Size() > api.MaxGuideDocumentBytes {
		_ = f.Close()
		return nil, errors.New("ZIP must be a nonempty regular file of at most 512MiB")
	}
	return f, nil
}

func hashPreparationZIP(ctx context.Context, path string) (string, int64, error) {
	if err := ctx.Err(); err != nil {
		return "", 0, err
	}
	f, err := openPreparationZIP(path)
	if err != nil {
		return "", 0, err
	}
	defer f.Close()
	initial, err := f.Stat()
	if err != nil {
		return "", 0, err
	}
	digest := sha256.New()
	buf := make([]byte, 64*1024)
	r := io.NewSectionReader(f, 0, initial.Size()+1)
	var count int64
	for {
		if err := ctx.Err(); err != nil {
			return "", 0, err
		}
		n, err := r.Read(buf)
		count += int64(n)
		if count > initial.Size() {
			return "", 0, errors.New("ZIP changed")
		}
		_, _ = digest.Write(buf[:n])
		if err == io.EOF {
			break
		}
		if err != nil {
			return "", 0, err
		}
	}
	final, err := f.Stat()
	if err != nil || count != initial.Size() || final.Size() != initial.Size() || !final.ModTime().Equal(initial.ModTime()) {
		return "", 0, errors.New("ZIP changed")
	}
	return "sha256:" + hex.EncodeToString(digest.Sum(nil)), count, ctx.Err()
}

func (m *Model) beginPreparationHash() tea.Cmd {
	m.invalidate()
	m.write.mode = writePrepareHash
	p, generation := m.write.packet, m.generation
	ctx, cancel := context.WithCancel(m.ctx)
	m.cancel = cancel
	return func() tea.Msg {
		digest, size, err := hashPreparationZIP(ctx, p.path)
		return preparationHashResponse{packet: p, generation: generation, digest: digest, bytes: size, err: err}
	}
}

func (m *Model) receivePreparationHash(msg preparationHashResponse) {
	if m.write.mode != writePrepareHash || msg.generation != m.generation || msg.packet != m.write.packet {
		return
	}
	if m.cancel != nil {
		m.cancel()
		m.cancel = nil
	}
	if msg.err != nil {
		m.write.mode, m.write.input = writePreparePath, m.write.packet.path
		m.write.notice = "Not sent: ZIP unavailable, changed or cancelled. Choose a nonempty regular file of at most 512MiB."
		return
	}
	m.write.packet.sha256, m.write.packet.bytes = msg.digest, msg.bytes
	m.write.mode = writeConfirm
	m.viewport.GotoTop()
}

func (p writePacket) submissionPacket() api.SubmissionPacket {
	packet := api.SubmissionPacket{Assignment: p.assignment}
	if p.summary != "" {
		value := p.summary
		packet.Summary = &value
	}
	if p.attestation != "" {
		value := p.attestation
		packet.Attestation = &value
	}
	return packet
}

func prepareWrite(ctx context.Context, client Client, p writePacket, generation, sequence uint64) writeResponse {
	result := writeResponse{packet: p, generation: generation, sequence: sequence}
	if ctx.Err() != nil {
		result.notSent = true
		return result
	}
	f, err := openPreparationZIP(p.path)
	if err != nil {
		result.notSent = true
		return result
	}
	defer f.Close()
	receipt, err := client.PrepareSubmission(ctx, p.task, p.key, p.submissionPacket(), nil, f, p.sha256)
	result.value, result.err = receipt.Value, err
	var failure *api.Failure
	// Ordinary errors are validation/hash failures before request dispatch. The
	// shared client marks transport and malformed responses OutcomeUnknown.
	result.notSent = err != nil && !errors.As(err, &failure)
	return result
}

func blockedPreparationFeedback(raw json.RawMessage) []string {
	var details struct {
		Results []json.RawMessage `json:"results"`
	}
	if json.Unmarshal(raw, &details) != nil {
		return nil
	}
	return preparationFeedbackLines(details.Results)
}

func preparationFeedbackLines(results []json.RawMessage) []string {
	lines := api.IntakeFeedbackLines(results)
	for _, raw := range results {
		var check struct {
			Source, Status string
			ID             string `json:"check_id"`
			Failure        string `json:"failure_code"`
		}
		if json.Unmarshal(raw, &check) == nil && check.Source == "workstream_default" && check.Status == "failed" {
			lines = append(lines, "failed "+check.ID+": "+check.Failure)
		}
	}
	return lines
}

func (m *Model) clearPreparationText() {
	if m.write.packet.action != "prepare" {
		return
	}
	p := &m.write.packet
	p.path, p.summary, p.attestation, p.sha256, p.bytes = "", "", "", "", 0
	m.write.input, m.write.keyInput = "", ""
	m.write.preparation, m.write.feedback = nil, nil
}

func (m *Model) preparationNeedsNewAttempt() bool {
	if m.write.packet.action != "prepare" || m.write.outcome != outcomeConfirmed || m.write.preparation == nil || m.write.replayDisabled {
		return false
	}
	switch m.write.preparation.Status {
	case "integrity_mismatch", "missing", "conflict", "stale":
		return true
	}
	return false
}

func packetText(value string) string {
	if value == "" {
		return "(omitted)"
	}
	return strconv.Quote(value)
}

func (m *Model) preparationText() string {
	w, p := m.write, m.write.packet
	d := detailWriter{m: m}
	switch w.mode {
	case writePrepareContext:
		d.heading("Checking initial preparation context")
		d.note("Fresh WorkContext must confirm your in-progress assignment without revision context. No POST was sent.")
	case writePreparePath, writePrepareSummary, writePrepareAttestation:
		label := "ZIP path"
		if w.mode == writePrepareSummary {
			label = "Summary"
		}
		if w.mode == writePrepareAttestation {
			label = "Attestation"
		}
		d.heading(label)
		d.line(label, w.input)
		if w.mode == writePreparePath {
			d.note("One readable, nonempty regular ZIP, at most 512MiB; path limit 4096 UTF-8 bytes, no control characters. No expansion or file execution.")
		} else {
			d.note("Optional exact printable ASCII, at most 64KiB; blank is omitted. No header-edge whitespace. Text is never trimmed.")
		}
		d.note("Enter continues; Esc cancels. q is text; Ctrl+C quits. No POST was sent.")
	case writeKeyEntry:
		d.heading("Caller-owned replay key")
		d.note("Save a UUID and exact ZIP/packet outside this session. No key or recovery inputs are persisted here.")
		d.line("UUID", w.keyInput)
		d.note("Enter hashes the ZIP for review; Esc cancels. No POST was sent.")
	case writePrepareHash:
		d.heading("Hashing ZIP")
		d.line("ZIP path", strconv.Quote(p.path))
		d.note("Local inspection only; Esc cancels. No POST was sent.")
	case writeConfirm, writePending, writeOutcome:
		if w.mode == writeConfirm {
			d.heading("Confirm prepare")
		}
		if w.mode == writePending {
			d.heading("Sending prepare")
		}
		if w.mode == writeOutcome {
			d.heading(m.writeSummary())
		}
		d.line("Actor", p.actor)
		d.line("Project", p.project)
		d.line("Task", p.task)
		d.line("Assignment", p.assignment)
		if !w.replayDisabled {
			d.line("ZIP path", strconv.Quote(p.path))
			d.line("Bytes", strconv.FormatInt(p.bytes, 10))
			d.line("SHA-256", p.sha256)
			d.line("Summary", packetText(p.summary))
			d.line("Attestation", packetText(p.attestation))
			d.line("Predecessor", "(omitted; initial preparation)")
		}
		d.line("Replay key", p.key)
		if w.mode == writeConfirm {
			if w.replay {
				d.note("Exact unchanged replay only. Earlier outcome remains until a validated receipt; no automatic retry.")
			}
			d.note("Save this key and exact inputs outside the session. The workbench cannot verify your copy.")
			if w.acknowledged {
				d.note("Save warning acknowledged. Press y to send one POST; Esc cancels.")
			} else {
				d.note("Press s to acknowledge saving, then y to send one POST. Esc cancels.")
			}
		}
		if w.mode == writePending {
			d.note("One POST is pending. Quit cancels the client request, not possible server effects.")
		}
		if w.mode == writeOutcome {
			d.note(m.clean(w.notice))
			if w.preparation != nil {
				d.line("Preparation status", w.preparation.Status)
				d.line("Put attempt", w.preparation.PutAttemptID)
				if w.preparation.AdmissionID != nil {
					d.line("Ready admission", *w.preparation.AdmissionID)
					d.note("Inert CLI handoff: workstream task submit; supply this Task, Assignment, Ready admission and exact Summary/Attestation with --assignment, --admission, --summary and --attestation (omit blank optional fields). No command is executed here.")
				} else {
					d.note("Not ready: no admission is available for submission.")
					if m.preparationNeedsNewAttempt() {
						d.note("This terminal preparation cannot become ready by changing its replay packet. Esc returns; refresh the task, then a starts a new deliberate preparation with a new saved UUID. Exact replay only observes the prior attempt.")
					} else {
						d.note("Exact replay observes current server state; it does not guarantee storage recovery. If the state persists, use operator support rather than changing the replay packet.")
					}
				}
			}
			for _, line := range w.feedback {
				d.line("Intake feedback", line)
			}
			if m.canReplay() {
				d.note("p reviews explicit same-packet replay; no automatic retry.")
			}
			if w.replayDisabled {
				d.note("Protected preparation text cleared; in-session replay disabled. Recover only with externally saved exact inputs after authority is restored.")
			}
			d.note("r separately refreshes the read; Esc returns. A read cannot prove rollback.")
		}
	}
	d.note("No immutable Submission was requested. Preparation is intake, not acceptance.")
	if w.notice != "" && w.mode != writeOutcome {
		d.note(m.clean(w.notice))
	}
	return d.String()
}
