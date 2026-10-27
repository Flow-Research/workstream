package tui

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
)

const preparationAssignmentID = "90000000-0000-7000-8000-000000000001"

func preparationDetail(t *testing.T, f *fakeClient) *Model {
	t.Helper()
	f.task = func(context.Context, string) (api.Result[api.ContributorTaskDetail], error) {
		v := taskDetail()
		v.Status = "in_progress"
		return api.Result[api.ContributorTaskDetail]{Value: v}, nil
	}
	if f.context == nil {
		f.context = func(context.Context, string) (api.Result[api.WorkContext], error) {
			v, _ := f.task(context.Background(), taskID)
			return api.Result[api.WorkContext]{Value: api.WorkContext{
				Task: v.Value, Project: api.ContextProject{ID: projectID}, Guide: api.ContextGuide{ProjectID: projectID},
				ContributionPolicyVersionID: policyID, Lifecycle: api.ContextLifecycle{AssignedToCurrentActor: true},
			}}, nil
		}
	}
	m := boot(t, f)
	press(t, m, "enter")
	press(t, m, "2")
	// Keep actor and assignment distinct so accidental actor-as-assignment
	// substitution cannot satisfy the preparation wire assertion.
	m.rows[0].id = preparationAssignmentID
	press(t, m, "enter")
	if !m.canOpenAction() || m.actionName() != "Prepare" {
		t.Fatal("initial Mine task did not offer preparation")
	}
	return m
}

func preparationFile(t *testing.T) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "bundle.zip")
	if err := os.WriteFile(path, []byte("ZIP bytes for testing"), 0600); err != nil {
		t.Fatal(err)
	}
	return path
}

func confirmPreparation(t *testing.T, m *Model, path, summary, attestation string) {
	t.Helper()
	press(t, m, "a")
	for _, text := range []string{path, summary, attestation, replayKey} {
		if text != "" {
			m.Update(tea.PasteMsg{Content: text})
		}
		press(t, m, "enter")
	}
	if m.write.mode != writeConfirm || m.write.packet.sha256 == "" {
		t.Fatal("preparation did not reach exact hashed review", m.body())
	}
}

func TestPreparationStagesExactPacketAndOnePOST(t *testing.T) {
	f := &fakeClient{}
	m := preparationDetail(t, f)
	path := preparationFile(t)
	var retained *os.File
	f.prepare = func(_ context.Context, task, key string, packet api.SubmissionPacket, ack *api.RevisionAcknowledgement, source *os.File, digest string) (api.Result[api.PreparationReceipt], error) {
		retained = source
		data, _ := io.ReadAll(source)
		if task != taskID || key != replayKey || packet.Assignment != preparationAssignmentID || packet.Predecessor != nil || ack != nil ||
			packet.Summary == nil || *packet.Summary != "literal q summary" || packet.Attestation == nil || *packet.Attestation != "Exact q attestation" ||
			string(data) != "ZIP bytes for testing" || digest != m.write.packet.sha256 {
			t.Fatal("packet or reviewed fingerprint changed", packet, digest)
		}
		return api.Result[api.PreparationReceipt]{Value: api.PreparationReceipt{PutAttemptID: runID, AdmissionID: new(submissionID), Status: "ready", Feedback: []json.RawMessage{json.RawMessage(`{"source":"workstream_default","status":"warning","warning_code":"archive_warning"}`)}}}, nil
	}
	confirmPreparation(t, m, path, "literal q summary", "Exact q attestation")
	if strings.Count(strings.Join(f.calls, ","), "context") != 1 {
		t.Fatal("preparation did not freshly read context")
	}
	before := len(f.calls)
	for _, k := range []string{"y", "enter", "a", "1", "2", "3", "tab", "r"} {
		press(t, m, k)
		if len(f.calls) != before {
			t.Fatal("implicit POST from", k)
		}
	}
	m.Update(tea.PasteMsg{Content: "sy"})
	if m.write.acknowledged {
		t.Fatal("paste acknowledged save")
	}
	press(t, m, "s")
	_, cmd := m.Update(keyMessage("y"))
	for _, k := range []string{"y", "p", "r", "esc", "2", "tab"} {
		if _, duplicate := m.Update(keyMessage(k)); duplicate != nil {
			t.Fatal("pending duplicate", k)
		}
	}
	apply(t, m, cmd)
	if m.write.outcome != outcomeConfirmed || m.write.preparation == nil || strings.Count(strings.Join(f.calls, ","), "prepare") != 1 ||
		!strings.Contains(m.body(), "Preparation ready") || !strings.Contains(m.body(), "archive_warning") || !strings.Contains(m.body(), "No immutable Submission was requested") {
		t.Fatal("validated preparation receipt missing", m.body())
	}
	if _, err := retained.Stat(); err == nil {
		t.Fatal("command retained an open file")
	}
}

func TestPreparationRejectsUnassignedAndRevisionContext(t *testing.T) {
	for _, revision := range []bool{false, true} {
		f := &fakeClient{context: func(context.Context, string) (api.Result[api.WorkContext], error) {
			v := taskDetail()
			v.Status = "in_progress"
			value := api.WorkContext{Task: v, Project: api.ContextProject{ID: projectID}, Guide: api.ContextGuide{ProjectID: projectID}, ContributionPolicyVersionID: policyID}
			if revision {
				value.Lifecycle.AssignedToCurrentActor = true
				value.RevisionContext = &api.RevisionContext{}
			}
			return api.Result[api.WorkContext]{Value: value}, nil
		}}
		m := preparationDetail(t, f)
		press(t, m, "a")
		if m.write.mode != writeIdle || !strings.Contains(m.failure, "without revision context") || strings.Contains(strings.Join(f.calls, ","), "prepare") {
			t.Fatal("unsafe initial context entered form", m.failure)
		}
	}
}

func TestPreparationTextPasteAndCancellationBoundaries(t *testing.T) {
	f := &fakeClient{}
	m := preparationDetail(t, f)
	press(t, m, "a")
	for _, mode := range []writeMode{writePreparePath, writePrepareSummary, writePrepareAttestation} {
		m.write.mode, m.write.input = mode, ""
		press(t, m, "q")
		m.Update(tea.PasteMsg{Content: " literal sy"})
		if m.closed || m.write.input != "q literal sy" {
			t.Fatal("field shortcuts executed", mode)
		}
		for _, hostile := range []string{"\ny", "\x1b[31m", "é", "\x00", strings.Repeat("a", 64*1024+1)} {
			if mode == writePreparePath && hostile == "é" {
				continue
			}
			m.Update(tea.PasteMsg{Content: hostile})
			if m.write.input != "q literal sy" || m.write.notice == "" {
				t.Fatal("hostile/oversize paste was accepted")
			}
		}
	}
	m.write.mode, m.write.input = writePrepareSummary, " edge "
	press(t, m, "enter")
	if m.write.mode != writePrepareSummary || m.write.input != " edge " {
		t.Fatal("text silently trimmed")
	}
	press(t, m, "esc")
	path := preparationFile(t)
	press(t, m, "a")
	for _, value := range []string{path, "", ""} {
		if value != "" {
			m.Update(tea.PasteMsg{Content: value})
		}
		press(t, m, "enter")
	}
	press(t, m, "q")
	if m.closed || m.write.keyInput != "q" {
		t.Fatal("q quit key entry")
	}
	m.write.keyInput = replayKey
	_, hash := m.Update(keyMessage("enter"))
	if hash == nil || m.write.mode != writePrepareHash {
		t.Fatal("hash was not asynchronous")
	}
	press(t, m, "esc")
	apply(t, m, hash)
	if m.write.mode != writeIdle || strings.Contains(strings.Join(f.calls, ","), "prepare") {
		t.Fatal("cancelled hash restored confirmation")
	}
	confirmPreparation(t, m, path, "", "")
	press(t, m, "s")
	_, send := m.Update(keyMessage("y"))
	m.cancel()
	apply(t, m, send)
	if m.write.outcome != outcomeNone || strings.Contains(strings.Join(f.calls, ","), "prepare") || !strings.Contains(m.write.notice, "No POST") {
		t.Fatal("cancelled-before-dispatch reached client")
	}
}

func TestPreparationUnicodePathPreservesBytesAndRuneBackspace(t *testing.T) {
	f := &fakeClient{}
	m := preparationDetail(t, f)
	path := filepath.Join(t.TempDir(), "贡献-e\u0301.zip")
	if err := os.WriteFile(path, []byte("ZIP bytes"), 0600); err != nil {
		t.Fatal(err)
	}
	press(t, m, "a")
	m.Update(tea.PasteMsg{Content: "贡献"})
	m.Update(tea.KeyPressMsg{Code: tea.KeyBackspace})
	if m.write.input != "贡" {
		t.Fatal("path backspace split a UTF-8 rune", m.write.input)
	}
	press(t, m, "esc")
	confirmPreparation(t, m, path, "", "")
	if m.write.packet.path != path || !strings.Contains(m.body(), "贡献-e\u0301.zip") {
		t.Fatal("Unicode path was normalized or rejected", m.body())
	}
}

func TestPreparationUnknownReplayKeepsOriginalFingerprintAndUncertainty(t *testing.T) {
	f := &fakeClient{}
	m := preparationDetail(t, f)
	path := preparationFile(t)
	confirmPreparation(t, m, path, "original", "")
	original := m.write.packet
	f.prepare = func(context.Context, string, string, api.SubmissionPacket, *api.RevisionAcknowledgement, *os.File, string) (api.Result[api.PreparationReceipt], error) {
		return api.Result[api.PreparationReceipt]{}, &api.Failure{Code: "request_failed", OutcomeUnknown: true}
	}
	press(t, m, "s")
	press(t, m, "y")
	press(t, m, "esc")
	press(t, m, "a")
	if m.write.packet != original || m.write.mode != writeIdle || m.canOpenAction() {
		t.Fatal("unknown result allowed replacement")
	}
	f.prepare = func(_ context.Context, _, _ string, _ api.SubmissionPacket, _ *api.RevisionAcknowledgement, _ *os.File, digest string) (api.Result[api.PreparationReceipt], error) {
		if digest != original.sha256 {
			t.Fatal("replay rehashed/rebound changed source")
		}
		return api.Result[api.PreparationReceipt]{}, errors.New("local changed-file guard")
	}
	press(t, m, "p")
	press(t, m, "s")
	press(t, m, "y")
	if m.write.outcome != outcomeUnknown || m.write.packet != original || !strings.Contains(m.write.notice, "Earlier outcome remains unknown") {
		t.Fatal("local refusal erased uncertainty", m.write.notice)
	}
}

func TestPreparationFailedIntakeAllowsCorrectedOperationAndNonreadyIsNotReady(t *testing.T) {
	f := &fakeClient{prepare: func(context.Context, string, string, api.SubmissionPacket, *api.RevisionAcknowledgement, *os.File, string) (api.Result[api.PreparationReceipt], error) {
		return api.Result[api.PreparationReceipt]{}, &api.Failure{Status: 422, Code: "pre_submission_checker_failed", Details: json.RawMessage(`{"status":"failed","eligible_to_submit":false,"results":[{"source":"workstream_default","status":"failed","check_id":"manifest","failure_code":"manifest_missing","finding_count":1}]}`)}
	}}
	m := preparationDetail(t, f)
	confirmPreparation(t, m, preparationFile(t), "", "")
	press(t, m, "s")
	press(t, m, "y")
	if m.write.outcome != outcomeDenied || !strings.Contains(m.body(), "manifest_missing") || m.canReplay() {
		t.Fatal("failed intake was not canonical blocking feedback", m.body())
	}
	press(t, m, "esc")
	press(t, m, "a")
	if m.write.mode != writePreparePath || m.write.outcome != outcomeNone {
		t.Fatal("known failed intake blocked corrected operation")
	}
	press(t, m, "esc")
	f.prepare = func(context.Context, string, string, api.SubmissionPacket, *api.RevisionAcknowledgement, *os.File, string) (api.Result[api.PreparationReceipt], error) {
		return api.Result[api.PreparationReceipt]{Value: api.PreparationReceipt{PutAttemptID: runID, Status: "stored_pending_verification", Feedback: []json.RawMessage{}}}, nil
	}
	confirmPreparation(t, m, preparationFile(t), "", "")
	press(t, m, "s")
	press(t, m, "y")
	if !strings.Contains(m.body(), "Preparation confirmed; not ready") || strings.Contains(m.body(), "Ready admission:") || !m.canReplay() {
		t.Fatal("nonready receipt exposed admission", m.body())
	}
}

func TestPreparationTerminalReceiptAllowsNewOperationButNotUnknownReplacement(t *testing.T) {
	for _, status := range []string{"integrity_mismatch", "missing", "conflict", "stale"} {
		t.Run(status, func(t *testing.T) {
			f := &fakeClient{prepare: func(context.Context, string, string, api.SubmissionPacket, *api.RevisionAcknowledgement, *os.File, string) (api.Result[api.PreparationReceipt], error) {
				return api.Result[api.PreparationReceipt]{Value: api.PreparationReceipt{PutAttemptID: runID, Status: status, Feedback: []json.RawMessage{}}}, nil
			}}
			m := preparationDetail(t, f)
			confirmPreparation(t, m, preparationFile(t), "", "")
			press(t, m, "s")
			press(t, m, "y")
			if !strings.Contains(m.body(), "new saved UUID") {
				t.Fatal("terminal receipt lacked recovery guidance")
			}
			press(t, m, "esc")
			if !m.canOpenAction() {
				t.Fatal("terminal receipt trapped user in observation-only replay")
			}
			m.write.outcome = outcomeUnknown
			if m.canOpenAction() || m.preparationNeedsNewAttempt() {
				t.Fatal("terminal status erased later uncertainty")
			}
			m.write.outcome = outcomeConfirmed
			press(t, m, "a")
			if m.write.mode != writePreparePath || m.write.packet.key != "" {
				t.Fatal("new operation did not require fresh deliberate inputs")
			}
		})
	}
}

func TestPreparationAuthFailureClearsProtectedTextAndRejectsLateResponse(t *testing.T) {
	f := &fakeClient{}
	m := preparationDetail(t, f)
	confirmPreparation(t, m, preparationFile(t), "private summary", "private attestation")
	press(t, m, "s")
	_, send := m.Update(keyMessage("y"))
	late := send().(writeResponse)
	denial := late
	denial.value, denial.err = nil, &api.Failure{Status: 403, Code: "permission_denied"}
	m.Update(denial)
	m.Update(late)
	if m.write.preparation != nil || m.write.packet.path != "" || m.write.packet.summary != "" || m.write.packet.sha256 != "" || m.canReplay() ||
		strings.Contains(m.body(), "private summary") || !strings.Contains(m.body(), "Protected preparation text cleared") {
		t.Fatal("late receipt restored protected preparation", m.body())
	}
	// A current delayed read denial after opening replay must expire confirmation
	// just as it does for Claim/Start; it cannot leave a y-dispatch path behind.
	m = preparationDetail(t, &fakeClient{})
	confirmPreparation(t, m, preparationFile(t), "private summary", "")
	m.failed(&api.Failure{Status: 401, Code: "session_unavailable"}, false)
	press(t, m, "s")
	press(t, m, "y")
	if !m.blocked || m.write.mode == writePending || m.write.packet.summary != "" {
		t.Fatal("delayed 401 left preparation writable")
	}
}

func TestPreparationConfirmedReceiptClearingDoesNotInventNotReady(t *testing.T) {
	for _, status := range []int{401, 403, 404} {
		f := &fakeClient{}
		m := preparationDetail(t, f)
		confirmPreparation(t, m, preparationFile(t), "private summary", "private attestation")
		press(t, m, "s")
		press(t, m, "y")
		if m.write.preparation == nil || m.write.preparation.Status != "ready" {
			t.Fatal("fixture lacks prior ready receipt")
		}
		f.prepare = func(context.Context, string, string, api.SubmissionPacket, *api.RevisionAcknowledgement, *os.File, string) (api.Result[api.PreparationReceipt], error) {
			return api.Result[api.PreparationReceipt]{}, &api.Failure{Status: status, Code: "permission_denied"}
		}
		press(t, m, "p")
		press(t, m, "s")
		press(t, m, "y")
		if m.write.outcome != outcomeConfirmed || m.write.preparation != nil || m.canReplay() || strings.Contains(m.body(), "not ready") ||
			!strings.Contains(m.body(), "Preparation receipt confirmed; protected details cleared") || strings.Contains(m.body(), "private summary") {
			t.Fatal("cleared receipt invented a non-ready storage outcome", status, m.body())
		}
	}
}

func TestPreparationConfirmationResponsiveScrollableExactReview(t *testing.T) {
	for _, size := range [][2]int{{120, 40}, {80, 24}, {40, 10}} {
		m := preparationDetail(t, &fakeClient{})
		confirmPreparation(t, m, preparationFile(t), strings.Repeat("long-summary-", 30), "literal q")
		m.Update(tea.WindowSizeMsg{Width: size[0], Height: size[1]})
		var seen strings.Builder
		for i := 0; i < 140; i++ {
			seen.WriteString(m.View().Content)
			m.scroll("down")
		}
		for _, want := range []string{"Confirm prepare", "Actor:", "Assignment:", "SHA-256:", "Summary:", "Attestation:", "Replay key:", "s saved", "y send", "q quit"} {
			if !strings.Contains(seen.String(), want) {
				t.Fatalf("%dx%d inaccessible %q", size[0], size[1], want)
			}
		}
		if m.write.acknowledged || m.write.outcome != outcomeNone {
			t.Fatal("scroll/resize dispatched")
		}
	}
}
