package tui

import (
	"context"
	"errors"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
)

const replayKey = "80000000-0000-7000-8000-000000000001"

func readyDetail(t *testing.T, f *fakeClient) *Model {
	t.Helper()
	m := boot(t, f)
	press(t, m, "enter")
	press(t, m, "enter")
	if !m.canOpenAction() {
		t.Fatal("fresh ready detail did not offer Claim")
	}
	return m
}

func confirmClaim(t *testing.T, m *Model) {
	t.Helper()
	press(t, m, "a")
	if m.write.mode != writeKeyEntry || !strings.Contains(m.View().Content, "Save a UUID outside this session") {
		t.Fatal("action did not explain caller-owned recovery key")
	}
	press(t, m, replayKey)
	press(t, m, "enter")
	if m.write.mode != writeConfirm || !strings.Contains(m.View().Content, "Confirm claim") ||
		!strings.Contains(m.View().Content, "Actor: "+actorID) ||
		!strings.Contains(m.View().Content, "Project: "+projectID) ||
		!strings.Contains(m.View().Content, "Contribution policy version: "+policyID) {
		t.Fatal("exact confirmation not visible", m.View().Content)
	}
}

func TestClaimRequiresVisibleAcknowledgedConfirmation(t *testing.T) {
	f := &fakeClient{}
	m := readyDetail(t, f)
	confirmClaim(t, m)
	before := len(f.calls)
	for _, key := range []string{"y", "1", "2", "3", "tab", "r", "a", "enter"} {
		_, cmd := m.Update(keyMessage(key))
		if cmd != nil || len(f.calls) != before {
			t.Fatalf("%q dispatched before save acknowledgment", key)
		}
	}
	m.Update(tea.WindowSizeMsg{Width: 30, Height: 8})
	press(t, m, "s")
	press(t, m, "y")
	if m.write.acknowledged || len(f.calls) != before {
		t.Fatal("hidden confirmation changed or dispatched")
	}
	m.Update(tea.WindowSizeMsg{Width: 80, Height: 24})
	press(t, m, "s")
	press(t, m, "y")
	if m.write.outcome != outcomeConfirmed || strings.Count(strings.Join(f.calls, ","), "claim") != 1 {
		t.Fatal("deliberate confirmation did not send exactly one POST", f.calls)
	}
	if !strings.Contains(m.View().Content, "Claim confirmed") {
		t.Fatal(m.View().Content)
	}
}

func TestBracketedPasteIsOnlyKeyEntryTextNeverConfirmation(t *testing.T) {
	f := &fakeClient{}
	m := readyDetail(t, f)
	press(t, m, "a")
	_, cmd := m.Update(tea.PasteMsg{Content: replayKey + "\ny"})
	if cmd != nil || m.write.keyInput != "" || !strings.Contains(m.View().Content, "Paste one UUID") {
		t.Fatal("multiline paste was accepted or dispatched")
	}
	m.Update(tea.PasteMsg{Content: replayKey})
	if m.write.keyInput != replayKey || m.write.mode != writeKeyEntry {
		t.Fatal("UUID paste was not inserted as text")
	}
	press(t, m, "enter")
	before := len(f.calls)
	m.Update(tea.PasteMsg{Content: "sy"})
	if m.write.acknowledged || len(f.calls) != before {
		t.Fatal("confirmation paste became commands")
	}
	press(t, m, "y")
	if len(f.calls) != before {
		t.Fatal("pasted acknowledgment dispatched write")
	}
	press(t, m, "s")
	m.Update(tea.PasteMsg{Content: "y"})
	if len(f.calls) != before {
		t.Fatal("pasted confirmation dispatched write")
	}
	press(t, m, "y")
	if strings.Count(strings.Join(f.calls, ","), "claim") != 1 {
		t.Fatal("manual y did not dispatch exactly once")
	}
}

func TestWritePendingConsumesNavigationAndLateResultIsBound(t *testing.T) {
	f := &fakeClient{}
	m := readyDetail(t, f)
	confirmClaim(t, m)
	press(t, m, "s")
	_, cmd := m.Update(keyMessage("y"))
	if cmd == nil || m.write.mode != writePending {
		t.Fatal("write did not enter pending state")
	}
	before := len(f.calls)
	for _, key := range []string{"y", "1", "2", "3", "tab", "shift+tab", "r", "g", "a", "p", "esc", "enter"} {
		_, duplicate := m.Update(keyMessage(key))
		if duplicate != nil || m.tab != ready || m.write.mode != writePending || len(f.calls) != before {
			t.Fatalf("%q moved or duplicated pending write", key)
		}
	}
	// A valid typed receipt substituted from another project is never success.
	f.claim = func(context.Context, string, string, *string) (api.Result[api.ClaimedTask], error) {
		return api.Result[api.ClaimedTask]{Value: api.ClaimedTask{
			Task:       api.MutationTask{ID: taskID, ProjectID: actorID, Status: "claimed"},
			Assignment: api.TaskAssignment{TaskID: taskID, ProjectID: actorID, ContributorID: actorID},
		}}, nil
	}
	apply(t, m, cmd)
	if m.write.outcome != outcomeUnknown || !strings.Contains(m.View().Content, "Outcome unknown") {
		t.Fatal("substituted project was accepted", m.View().Content)
	}
}

func TestClaimActorSubstitutionAndDeniedReplayKeepUncertainty(t *testing.T) {
	f := &fakeClient{}
	m := readyDetail(t, f)
	confirmClaim(t, m)
	f.claim = func(_ context.Context, task, key string, reason *string) (api.Result[api.ClaimedTask], error) {
		if key != replayKey || reason != nil {
			t.Fatal("wire packet changed", key, reason)
		}
		if strings.Count(strings.Join(f.calls, ","), "claim") == 1 {
			return api.Result[api.ClaimedTask]{Value: api.ClaimedTask{
				Task:       api.MutationTask{ID: task, ProjectID: projectID, Status: "claimed"},
				Assignment: api.TaskAssignment{TaskID: task, ProjectID: projectID, ContributorID: projectID},
			}}, nil
		}
		return api.Result[api.ClaimedTask]{}, &api.Failure{Code: "state_conflict", Status: 409}
	}
	press(t, m, "s")
	press(t, m, "y")
	if m.write.outcome != outcomeUnknown {
		t.Fatal("wrong contributor accepted")
	}
	for _, key := range []string{"y", "enter", "r"} {
		if key != "r" {
			press(t, m, key)
		}
	}
	if strings.Count(strings.Join(f.calls, ","), "claim") != 1 {
		t.Fatal("automatic retry")
	}
	press(t, m, "p")
	if m.write.mode != writeConfirm || !m.write.replay || m.write.packet.key != replayKey {
		t.Fatal("exact replay not offered")
	}
	press(t, m, "y")
	if strings.Count(strings.Join(f.calls, ","), "claim") != 1 {
		t.Fatal("replay skipped save acknowledgment")
	}
	press(t, m, "s")
	press(t, m, "y")
	if m.write.outcome != outcomeUnknown || !strings.Contains(m.View().Content, "Earlier outcome remains unknown") {
		t.Fatal("denial retroactively erased uncertainty", m.View().Content)
	}
}

func TestConfirmedWriteSurvivesFailedReadAndExplicitReplay(t *testing.T) {
	f := &fakeClient{}
	m := readyDetail(t, f)
	confirmClaim(t, m)
	press(t, m, "s")
	press(t, m, "y")
	if m.write.outcome != outcomeConfirmed {
		t.Fatal("no validated receipt")
	}
	press(t, m, "p")
	if m.write.mode != writeConfirm || !m.write.replay {
		t.Fatal("confirmed same-key replay unavailable")
	}
	press(t, m, "s")
	press(t, m, "y")
	if strings.Count(strings.Join(f.calls, ","), "claim") != 2 || m.write.outcome != outcomeConfirmed {
		t.Fatal("confirmed replay failed", f.calls)
	}
	f.task = func(context.Context, string) (api.Result[api.ContributorTaskDetail], error) {
		return api.Result[api.ContributorTaskDetail]{}, &api.Failure{Code: "not_found", Status: 404}
	}
	press(t, m, "r")
	if m.task != nil || m.write.outcome != outcomeConfirmed || !strings.Contains(m.View().Content, "Prior operation: Claim confirmed | task "+taskID) || strings.Contains(m.View().Content, "Exact instructions") {
		t.Fatal("failed read erased receipt or retained protected text", m.View().Content)
	}
}

func TestDelayedReadSessionDenialCannotDispatchReplay(t *testing.T) {
	f := &fakeClient{}
	m := readyDetail(t, f)
	confirmClaim(t, m)
	press(t, m, "s")
	press(t, m, "y")
	if m.write.outcome != outcomeConfirmed {
		t.Fatal("fixture needs a validated receipt")
	}
	_, delayedRead := m.Update(keyMessage("r"))
	if delayedRead == nil || !m.loading {
		t.Fatal("fixture needs pending read")
	}
	press(t, m, "p")
	f.task = func(context.Context, string) (api.Result[api.ContributorTaskDetail], error) {
		return api.Result[api.ContributorTaskDetail]{}, &api.Failure{Code: "session_unavailable", Status: 401}
	}
	apply(t, m, delayedRead)
	before := strings.Count(strings.Join(f.calls, ","), "claim")
	press(t, m, "s")
	press(t, m, "y")
	if after := strings.Count(strings.Join(f.calls, ","), "claim"); after != before || !m.blocked || m.task != nil || m.write.outcome != outcomeConfirmed || m.write.mode == writeConfirm ||
		!strings.Contains(m.View().Content, "Denied: session_unavailable") || !strings.Contains(m.View().Content, "Prior operation: Claim confirmed") {
		t.Fatalf("delayed read denial dispatched stale replay: claims %d -> %d, blocked=%v, outcome=%v", before, after, m.blocked, m.write.outcome)
	}
	// Even a stale caller of the owner operation cannot bypass the session guard.
	m.write.mode, m.write.acknowledged = writeConfirm, true
	if cmd := m.beginWrite(); cmd != nil || strings.Count(strings.Join(f.calls, ","), "claim") != before {
		t.Fatal("dispatch boundary ignored denied session")
	}
}

func TestTransientReadFailureDoesNotDisableExplicitReplay(t *testing.T) {
	f := &fakeClient{}
	m := readyDetail(t, f)
	confirmClaim(t, m)
	press(t, m, "s")
	press(t, m, "y")
	f.task = func(context.Context, string) (api.Result[api.ContributorTaskDetail], error) {
		return api.Result[api.ContributorTaskDetail]{}, errors.New("temporary transport failure")
	}
	press(t, m, "r")
	if !m.canReplay() || m.write.outcome != outcomeConfirmed {
		t.Fatal("transient read failure disabled exact replay")
	}
	press(t, m, "p")
	if m.write.mode != writeConfirm || m.write.packet.key != replayKey {
		t.Fatal("transient failure lost packet")
	}
}

func TestPriorReceiptIsBoundWhileBrowsingDifferentProject(t *testing.T) {
	otherProject := "20000000-0000-7000-8000-000000000002"
	f := &fakeClient{projects: func(context.Context, api.PageQuery) (api.Result[api.ActorProjectPage], error) {
		return api.Result[api.ActorProjectPage]{Value: api.ActorProjectPage{Items: []api.ActorProject{
			{ProjectID: projectID, Name: "Original", Status: "active"},
			{ProjectID: otherProject, Name: "Other", Status: "active"},
		}}}, nil
	}}
	m := readyDetail(t, f)
	confirmClaim(t, m)
	press(t, m, "s")
	press(t, m, "y")
	press(t, m, "esc")
	press(t, m, "g")
	press(t, m, "down")
	press(t, m, "enter")
	if m.project != otherProject || !strings.Contains(m.body(), "Prior operation: Claim confirmed | task "+taskID+" | project "+projectID) {
		t.Fatal("prior receipt attributed to new project", m.View().Content)
	}
	press(t, m, "p")
	if m.write.mode != writeConfirm || m.write.packet.project != projectID || m.write.packet.key != replayKey {
		t.Fatal("navigation changed recovery packet")
	}
}

func TestUnknownSessionFailureClearsProtectedContentAndDisablesReplay(t *testing.T) {
	f := &fakeClient{}
	m := readyDetail(t, f)
	confirmClaim(t, m)
	f.claim = func(context.Context, string, string, *string) (api.Result[api.ClaimedTask], error) {
		return api.Result[api.ClaimedTask]{}, &api.Failure{Code: "session_unavailable", Status: 401, OutcomeUnknown: true}
	}
	press(t, m, "s")
	press(t, m, "y")
	if m.task != nil || !m.blocked || m.canReplay() || strings.Contains(m.View().Content, "Exact instructions") || strings.Contains(m.View().Content, "Accepted submission terms") {
		t.Fatal("session failure retained protected content or replay", m.View().Content)
	}
	press(t, m, "p")
	if m.write.mode != writeOutcome {
		t.Fatal("blocked replay entered confirmation")
	}
}

func TestDirectCollectionsReverseTabAndTextEntryIsolation(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	press(t, m, "enter")
	press(t, m, "3")
	if m.tab != submissions {
		t.Fatal("3 did not select submissions")
	}
	press(t, m, "shift+tab")
	if m.tab != mine {
		t.Fatal("reverse Tab did not select Mine")
	}
	press(t, m, "1")
	if m.tab != ready {
		t.Fatal("1 did not select Ready")
	}
	press(t, m, "/")
	press(t, m, "2")
	if m.tab != ready || m.filter != "2" {
		t.Fatal("text entry intercepted direct navigation")
	}
	press(t, m, "esc")
	press(t, m, "r")
	press(t, m, "enter")
	press(t, m, "a")
	press(t, m, "3")
	if m.tab != ready || m.write.keyInput != "3" {
		t.Fatal("key entry intercepted direct navigation")
	}
	press(t, m, "esc")
	press(t, m, "c")
	press(t, m, "2")
	if m.tab != ready {
		t.Fatal("handoff intercepted direct navigation")
	}
}

func TestDirectSameCollectionReturnsFromDetailToList(t *testing.T) {
	for _, tc := range []struct {
		key  string
		tab  tab
		read string
	}{
		{"1", ready, "ready"}, {"2", mine, "mine"}, {"3", submissions, "submissions"},
	} {
		t.Run(tc.read, func(t *testing.T) {
			f := &fakeClient{}
			m := boot(t, f)
			press(t, m, "enter")
			press(t, m, tc.key)
			press(t, m, "enter")
			if !m.detail || m.tab != tc.tab {
				t.Fatal("fixture did not inspect target collection")
			}
			before := strings.Count(strings.Join(f.calls, ","), tc.read)
			press(t, m, tc.key)
			if m.detail || m.tab != tc.tab || strings.Count(strings.Join(f.calls, ","), tc.read) != before+1 {
				t.Fatal("same collection shortcut did not return to fresh list", f.calls)
			}
			press(t, m, tc.key)
			if strings.Count(strings.Join(f.calls, ","), tc.read) != before+1 {
				t.Fatal("same collection list key re-read", f.calls)
			}
		})
	}
}

func TestWriteTransportErrorIsUnknown(t *testing.T) {
	f := &fakeClient{claim: func(context.Context, string, string, *string) (api.Result[api.ClaimedTask], error) {
		return api.Result[api.ClaimedTask]{}, errors.New("transport unavailable")
	}}
	m := readyDetail(t, f)
	confirmClaim(t, m)
	press(t, m, "s")
	press(t, m, "y")
	if m.write.outcome != outcomeUnknown {
		t.Fatal("transport error treated as denial")
	}
}

func TestMineStartUsesClaimedDetailNotActiveAssignmentRow(t *testing.T) {
	f := &fakeClient{task: func(context.Context, string) (api.Result[api.ContributorTaskDetail], error) {
		v := taskDetail()
		v.Status = "claimed"
		return api.Result[api.ContributorTaskDetail]{Value: v}, nil
	}}
	m := boot(t, f)
	press(t, m, "enter")
	press(t, m, "2")
	if m.rows[0].status != "active" {
		t.Fatal("fixture does not distinguish assignment and task status")
	}
	if m.canOpenAction() {
		t.Fatal("assignment row alone offered Start")
	}
	press(t, m, "enter")
	if !m.canOpenAction() || m.actionName() != "Start" {
		t.Fatal("claimed detail did not offer Start")
	}
	press(t, m, "a")
	press(t, m, replayKey)
	press(t, m, "enter")
	if !strings.Contains(m.View().Content, "Confirm start") {
		t.Fatal("Start confirmation absent")
	}
	press(t, m, "s")
	press(t, m, "y")
	if m.write.outcome != outcomeConfirmed || !strings.Contains(m.View().Content, "Start confirmed") || strings.Count(strings.Join(f.calls, ","), "start") != 1 {
		t.Fatal("Start was not an independent confirmed write", f.calls)
	}
}
