package tui

import (
	"fmt"
	"math/big"
	"strings"

	"github.com/Flow-Research/workstream/cli/internal/api"
)

func number(v *big.Int) string {
	if v == nil {
		return "not supplied"
	}
	return v.String()
}

func humanBytes(value int64) string {
	if value < 1024 {
		return fmt.Sprintf("%d B", value)
	}
	for _, unit := range []struct {
		bytes int64
		name  string
	}{{1024 * 1024 * 1024, "GiB"}, {1024 * 1024, "MiB"}, {1024, "KiB"}} {
		if value >= unit.bytes {
			return fmt.Sprintf("%.1f %s", float64(value)/float64(unit.bytes), unit.name)
		}
	}
	return fmt.Sprintf("%d B", value)
}

type detailWriter struct {
	m   *Model
	out strings.Builder
}

func (d *detailWriter) heading(label string) {
	if d.out.Len() > 0 {
		d.out.WriteByte('\n')
	}
	d.out.WriteString(d.m.styles().heading.Render(label))
	d.out.WriteByte('\n')
}

func (d *detailWriter) line(label, value string) {
	d.out.WriteString(label + ": " + d.m.clean(value) + "\n")
}

func (d *detailWriter) optional(label string, value *string) {
	if value != nil {
		d.line(label, *value)
	}
}

func (d *detailWriter) prose(label, value string) {
	d.out.WriteString(label + "\n" + d.m.prose(value) + "\n")
}

func (d *detailWriter) optionalProse(label string, value *string) {
	if value != nil {
		d.prose(label, *value)
	}
}

func (d *detailWriter) note(value string) { d.out.WriteString(value + "\n") }
func (d *detailWriter) String() string    { return strings.TrimRight(d.out.String(), "\n") }

func (m *Model) detailText() string {
	if m.tab == submissions && m.section == 1 && m.findings != nil {
		return m.findingsText()
	}
	if m.submission != nil {
		return m.submissionText()
	}
	if m.section == 3 && m.context != nil {
		return m.guideText()
	}
	if m.section == 1 && m.context != nil {
		return m.contextText()
	}
	if m.section == 2 && m.intake != nil {
		return m.intakeText()
	}
	if m.task != nil {
		return m.taskText()
	}
	return "No detail loaded."
}

func (m *Model) taskText() string {
	v := m.task
	d := detailWriter{m: m}
	d.heading(m.clean(v.Title))
	d.line("Stored status", v.Status)
	if len(v.SkillTags) > 0 {
		d.line("Skills", strings.Join(v.SkillTags, ", "))
	}
	d.heading("Instructions")
	d.note(m.prose(v.Description))
	if v.AcceptanceCriteria != nil {
		d.heading("Acceptance criteria")
		d.note(m.prose(*v.AcceptanceCriteria))
	}
	if v.RejectionCriteria != nil {
		d.heading("Rejection criteria")
		d.note(m.prose(*v.RejectionCriteria))
	}
	d.heading("Contribution terms")
	for _, terms := range []struct {
		label string
		raw   []byte
	}{{"Accepted submission terms", v.Compensation.AcceptedSubmission}, {"Completed review terms", v.Compensation.CompletedReview}} {
		awards, ok := api.CompensationAwards(terms.raw)
		if !ok {
			d.line(terms.label, "unavailable")
			continue
		}
		if len(awards) == 0 {
			d.line(terms.label, "unpaid")
		}
		for _, award := range awards {
			d.line(terms.label, award.Instrument+" / "+award.Unit+" / "+award.Quantity)
		}
	}
	d.note("Terms are potential earned terms, not acceptance or fulfillment.")
	if m.canOpenAction() {
		d.note("a actions opens the deliberate " + m.actionName() + " flow; server authorization is checked again on write.")
	}
	d.heading("References")
	d.line("Task", v.TaskID)
	d.line("Project", v.ProjectID)
	d.line("Contribution policy version", v.Compensation.ContributionPolicyVersionID)
	return d.String()
}

func (m *Model) contextText() string {
	v := m.context
	d := detailWriter{m: m}
	d.heading("Assignment")
	d.line("Task", v.Task.TaskID)
	d.line("Project", v.Project.ID)
	d.line("Assigned to current actor", fmt.Sprint(v.Lifecycle.AssignedToCurrentActor))
	d.line("Observed action hints (not authority)", strings.Join(v.Lifecycle.NextActions, ", "))
	d.heading("Locked rules")
	d.line("Guide", v.Guide.ID)
	d.line("Locked guide version", v.Guide.Version)
	d.line("Review policy", v.ReviewPolicy.PolicyID)
	d.line("Review policy generation", fmt.Sprint(v.ReviewPolicy.Generation))
	d.line("Review policy hash", v.ReviewPolicy.PolicyHash)
	d.line("Revision policy", v.RevisionPolicy.PolicyID)
	d.line("Revision policy generation", fmt.Sprint(v.RevisionPolicy.Generation))
	d.line("Revision policy hash", v.RevisionPolicy.PolicyHash)
	d.line("Contribution policy version", v.ContributionPolicyVersionID)
	d.heading("Guide originals (server metadata; bytes not downloaded)")
	if len(v.GuideDocuments) == 0 {
		d.note("No assigned guide documents.")
	}
	for _, original := range v.GuideDocuments {
		d.line("Document label", original.Label)
		d.line("Document ID", original.DocumentID)
		d.line("Order", fmt.Sprint(original.Order))
		d.line("Media type", original.MediaType)
		d.line("Bytes", fmt.Sprint(original.ByteCount))
		d.line("SHA-256 (server metadata; bytes not downloaded)", original.SHA256)
		d.line("Read reference (server metadata; not opened)", original.ReadReference)
	}
	if v.RevisionContext != nil {
		d.heading("Revision context")
		r := v.RevisionContext
		d.line("Revision preparation", r.PreparationID)
		d.line("Revision preparation digest", r.PreparationSHA256)
		d.line("Revision source Submission", r.SourceSubmissionID)
		d.line("Revision source routing manifest", r.SourceRoutingManifestID)
		d.optional("Predecessor preparation", r.PredecessorPreparationID)
		d.line("Revision sequence", fmt.Sprint(r.Sequence))
		d.line("Next revision round", fmt.Sprint(r.NextRevisionRound))
		d.line("Maximum revision rounds", fmt.Sprint(r.MaxRevisionRounds))
		d.line("Revision requested", r.RequestedAt)
		d.line("Revision outcome", r.Outcome)
		d.line("Revision disposition", r.Disposition)
		d.line("Revision clock", r.ClockState)
		d.optional("Revision deadline", r.DeadlineAt)
		if r.RemainingMicroseconds != nil {
			d.line("Remaining microseconds", fmt.Sprint(*r.RemainingMicroseconds))
		}
		d.optionalProse("Direction", r.Direction)
		d.line("Prior guide", r.Prior.GuideID)
		if r.Target != nil {
			d.line("Target guide", r.Target.GuideID)
		}
		for _, change := range r.Changes {
			d.line("Changed component", change.Component)
			d.line("Before", change.Before)
			d.line("After", change.After)
		}
	}
	return d.String()
}

func (m *Model) intakeText() string {
	v := m.intake
	d := detailWriter{m: m}
	d.heading("Required packet fields")
	if len(v.RequiredPacketFields) == 0 {
		d.note("None listed.")
	} else {
		for _, field := range v.RequiredPacketFields {
			d.line("Field", field)
		}
	}
	d.heading("Required artifacts")
	if len(v.RequiredArtifacts) == 0 {
		d.note("None listed.")
	}
	for _, a := range v.RequiredArtifacts {
		d.line("Artifact", a.Key)
		d.line("Path (text only)", a.Path)
		d.line("Required", fmt.Sprint(a.Required))
		d.line("Hash required", fmt.Sprint(a.HashRequired))
		d.optionalProse("Description", a.Description)
	}
	d.heading("Required evidence")
	if len(v.RequiredEvidence) == 0 {
		d.note("None listed.")
	}
	for _, e := range v.RequiredEvidence {
		d.line("Evidence", e.Key)
		d.line("Label", e.Label)
		d.line("Required", fmt.Sprint(e.Required))
		d.line("Hash required", fmt.Sprint(e.HashRequired))
		d.optionalProse("Description", e.Description)
	}
	d.heading("Forbidden artifacts")
	if len(v.ForbiddenArtifacts) == 0 {
		d.note("None listed.")
	}
	for _, a := range v.ForbiddenArtifacts {
		d.line("Forbidden pattern", a.Pattern)
		d.optionalProse("Reason", a.Reason)
		d.optionalProse("Suggested fix", a.WorkerFacingFix)
		d.optional("Severity", a.Severity)
	}
	d.heading("Attestations")
	if len(v.AttestationTerms) == 0 {
		d.note("None listed.")
	}
	for _, term := range v.AttestationTerms {
		d.line("Attestation term", term)
	}
	d.heading("Package and storage constraints")
	d.line("Manifest required", fmt.Sprint(v.ManifestRequired))
	d.line("Artifact hash required", fmt.Sprint(v.ArtifactHashRequired))
	d.line("Hash algorithm", v.ArtifactHashAlgorithm)
	d.line("Allowed storage schemes", strings.Join(v.AllowedStorageSchemes, ", "))
	d.line("Allowed URI prefixes (text only)", strings.Join(v.StorageReferenceRules.AllowedURIPrefixes, ", "))
	d.line("Storage credentials allowed", fmt.Sprint(v.StorageReferenceRules.CredentialsAllowed))
	d.line("Storage query strings allowed", fmt.Sprint(v.StorageReferenceRules.QueryStringsAllowed))
	d.line("Storage fragments allowed", fmt.Sprint(v.StorageReferenceRules.FragmentsAllowed))
	d.line("Storage path traversal allowed", fmt.Sprint(v.StorageReferenceRules.PathTraversalAllowed))
	d.line("Maximum file bytes", number(v.MaximumFileSizeBytes))
	d.line("Maximum package bytes", number(v.MaximumPackageSizeBytes))
	d.line("Maximum archive bytes", number(v.MaximumArchiveSizeBytes))
	d.line("Maximum archive entries", number(v.MaximumArchiveEntries))
	d.line("Package required", fmt.Sprint(v.Packaging.PackageRequired))
	d.line("Allowed package formats", strings.Join(v.Packaging.AllowedPackageFormats, ", "))
	d.heading("References")
	d.line("Task", v.TaskID)
	d.line("Project", v.ProjectID)
	d.line("Locked guide version", v.GuideVersion)
	d.optional("Policy schema version", v.PolicySchemaVersion)
	d.optional("Merge algorithm version", v.MergeAlgorithmVersion)
	d.note("Intake requirements are not a preparation or Submission. No package is uploaded.")
	return d.String()
}

func (m *Model) guideText() string {
	v := m.context
	d := detailWriter{m: m}
	if m.guideMode == guideDestination {
		d.heading("Download destination")
		if m.guideSelected >= 0 && m.guideSelected < len(v.GuideDocuments) {
			d.line("Document", v.GuideDocuments[m.guideSelected].DocumentID)
			d.line("Label", v.GuideDocuments[m.guideSelected].Label)
		}
		d.line("Download directory", m.guideDirectory)
		d.note("Enter confirms this existing directory; no directory is created.")
		return d.String()
	}
	if m.guideMode == guideConfirm && m.guideSelected >= 0 && m.guideSelected < len(v.GuideDocuments) {
		original := v.GuideDocuments[m.guideSelected]
		d.heading("Confirm download")
		d.line("Label", original.Label)
		d.line("Document", original.DocumentID)
		d.line("Task", v.Task.TaskID)
		d.line("Download directory", m.guideDirectory)
		d.line("Filename", original.Filename())
		d.line("Expected bytes", fmt.Sprint(original.ByteCount))
		d.line("Expected SHA-256", original.SHA256)
		d.note("y downloads and verifies bytes before saving | esc cancels")
		return d.String()
	}
	if m.guideNotice != "" {
		if strings.HasPrefix(m.guideNotice, "Downloaded: ") {
			d.note(m.clean(m.guideNotice) + " (verified and saved)")
		} else {
			d.note(m.clean(m.guideNotice))
		}
	}
	if len(v.GuideDocuments) > 0 && m.guideSelected >= 0 && m.guideSelected < len(v.GuideDocuments) {
		original := v.GuideDocuments[m.guideSelected]
		d.heading("Selected original (server metadata; bytes not downloaded)")
		d.line("Label", original.Label)
		d.line("Document ID", original.DocumentID)
		d.line("Order", fmt.Sprint(original.Order))
		d.line("Media type", original.MediaType)
		d.line("Bytes (server metadata; bytes not downloaded)", fmt.Sprint(original.ByteCount))
		d.line("SHA-256 (server metadata; bytes not downloaded)", original.SHA256)
		d.line("Read reference (server metadata; not opened)", original.ReadReference)
	}
	d.heading("Guide originals (server metadata; bytes not downloaded)")
	if len(v.GuideDocuments) == 0 {
		d.note("No assigned guide documents.")
	}
	separator := " · "
	if m.plain {
		separator = " | "
	}
	for index, original := range v.GuideDocuments {
		mark := "  "
		if index == m.guideSelected {
			mark = "> "
		}
		d.note(mark + fmt.Sprint(index+1) + ". " + m.clean(original.Label) + separator + m.clean(original.MediaType) + separator + humanBytes(original.ByteCount))
	}
	d.heading("References")
	d.line("Task", v.Task.TaskID)
	d.line("Project", v.Project.ID)
	d.line("Guide", v.Guide.ID)
	d.line("Locked guide version", v.Guide.Version)
	d.note("Guide metadata is not verified downloaded bytes.")
	return d.String()
}

func (m *Model) submissionText() string {
	v := m.submission
	d := detailWriter{m: m}
	title := v.Summary
	if strings.TrimSpace(title) == "" {
		title = "Submission"
	}
	d.heading(m.prose(title))
	d.heading("Stored outcome")
	d.line("Stored outcome", v.Status)
	d.optional("Reason", v.StatusReason)
	d.heading("Finding counts")
	d.line("Blocking findings", number(v.FindingCounts.Blocking))
	d.line("Warning findings", number(v.FindingCounts.Warning))
	d.line("Coverage incomplete", number(v.FindingCounts.CoverageIncomplete))
	d.heading("Attempt")
	d.line("Version", number(v.Version))
	d.optional("Predecessor", v.Predecessor)
	d.heading("Timing")
	d.line("Submitted", v.SubmittedAt)
	d.optional("Locked", v.LockedAt)
	d.optional("Decided", v.DecidedAt)
	d.heading("Evidence")
	if len(v.Evidence) == 0 {
		d.note("No evidence items listed.")
	}
	for _, e := range v.Evidence {
		d.line("Evidence label", e.Label)
		d.line("Type", e.Type)
		d.line("Size", number(e.Size))
		d.line("Evidence ID", e.ID)
	}
	d.heading("References")
	d.line("Submission", v.ID)
	d.line("Task", v.Task)
	d.note("Tab opens contributor-visible checker findings. Stored observations do not predict acceptance or fulfillment.")
	return d.String()
}

func (m *Model) findingsText() string {
	d := detailWriter{m: m}
	if len(m.findings.Items) == 0 {
		d.heading("Checker runs")
		d.note("No checker runs on this fetched page. This is not a passing result.")
	}
	for _, run := range m.findings.Items {
		label := "Historical checker run"
		if run.Current {
			label = "Current checker run"
		}
		d.heading(label)
		d.line("Run status", run.Status)
		d.line("Current", fmt.Sprint(run.Current))
		d.line("Attempt", number(run.Attempt))
		d.line("Submission version", number(run.Version))
		d.line("Created", run.CreatedAt)
		if run.CompletedAt == nil {
			d.line("Completed", "not supplied")
		} else {
			d.line("Completed", *run.CompletedAt)
		}
		d.line("Run", run.ID)
		d.line("Submission", run.Submission)
		d.line("Task", run.Task)
		if run.Predecessor == nil {
			d.line("Predecessor run", "not supplied")
		} else {
			d.line("Predecessor run", *run.Predecessor)
		}
		if len(run.Results) == 0 {
			d.note("No findings in this run; this does not establish a pass.")
		}
		for _, finding := range run.Results {
			d.note("")
			d.line("Severity", finding.Severity)
			d.line("Finding status", finding.Status)
			d.line("Checker", finding.Checker)
			if finding.CheckID == nil {
				d.line("Check ID", "not supplied")
			} else {
				d.line("Check ID", *finding.CheckID)
			}
			if finding.Message == nil {
				d.line("Message", "not supplied")
			} else {
				d.prose("Message", *finding.Message)
			}
			if finding.Path == nil {
				d.line("Path", "not supplied")
			} else {
				d.line("Path", *finding.Path)
			}
			if finding.Line == nil {
				d.line("Line", "not supplied")
			} else {
				d.line("Line", fmt.Sprint(*finding.Line))
			}
			if finding.Fix == nil {
				d.line("Suggested fix", "not supplied")
			} else {
				d.prose("Suggested fix", *finding.Fix)
			}
			d.line("Finding", finding.ID)
		}
	}
	d.note("Checker findings are evidence; the stored submission outcome determines disposition.")
	return d.String()
}
