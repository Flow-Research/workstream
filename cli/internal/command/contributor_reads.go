package command

import (
	"fmt"
	"io"
	"math/big"
	"strings"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

// pageFlags binds the shared page and filter flags of every signed list; unset flags stay nil.
type pageFlags struct {
	limit                                                int
	cursor, project, task, state, status, since, outcome string
}

func (f *pageFlags) query(cmd *cobra.Command) api.PageQuery {
	selected := func(name string, value *string) *string {
		if cmd.Flags().Changed(name) {
			return value
		}
		return nil
	}
	return api.PageQuery{
		Limit: f.limit, Cursor: selected("cursor", &f.cursor), ProjectID: selected("project", &f.project),
		TaskID: selected("task", &f.task), State: selected("state", &f.state), Status: selected("status", &f.status),
		UpdatedSince: selected("updated-since", &f.since), Outcome: selected("outcome", &f.outcome),
	}
}

// bind adds the page flags and the named filters; "name=help" overrides a
// filter's help text where a list stores other values (such as guide status).
func (f *pageFlags) bind(cmd *cobra.Command, limit int, filters ...string) {
	cmd.Flags().IntVar(&f.limit, "limit", limit, "Page size (1–100; keep unchanged when continuing)")
	cmd.Flags().StringVar(&f.cursor, "cursor", "", "Opaque next cursor from the previous page (same filters)")
	for _, filter := range filters {
		name, help, overridden := strings.Cut(filter, "=")
		switch name {
		case "project":
			cmd.Flags().StringVar(&f.project, "project", "", "Only this project (needs your Submitter grant)")
		case "task":
			cmd.Flags().StringVar(&f.task, "task", "", "Only this task")
		case "state":
			cmd.Flags().StringVar(&f.state, "state", "", "active or closed")
		case "status":
			if !overridden {
				help = "evaluation_pending, review_pending, accepted, needs_revision or rejected"
			}
			cmd.Flags().StringVar(&f.status, "status", "", help)
		case "updated-since":
			cmd.Flags().StringVar(&f.since, "updated-since", "", "Only rows changed at or after this RFC 3339 time")
		case "outcome":
			cmd.Flags().StringVar(&f.outcome, "outcome", "", "pending, passed, failed or infrastructure_failed")
		}
	}
}

func count(value *big.Int) string {
	if value == nil {
		return "—"
	}
	return value.String()
}

func addContributorReads(root *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	me := &cobra.Command{Use: "me", Short: "Read your own projects, claimed work, attempts and totals"}
	var projectPage, assignmentPage, submissionPage pageFlags
	projects := &cobra.Command{Use: "projects", Short: "List projects where you hold a grant", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.MyProjects(cmd.Context(), projectPage.query(cmd))
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			for _, p := range result.Value.Items {
				guide := "—"
				if p.ActiveGuide != nil {
					guide = safeText(p.ActiveGuide.GuideID) + " " + safeText(p.ActiveGuide.Version)
				}
				if _, err := fmt.Fprintf(stdout, "Project: %s\nName: %s\nStatus: %s\nAdmin roles: %s\nProject roles: %s\nActive guide: %s\n",
					safeText(p.ProjectID), safeText(p.Name), safeText(p.Status), list(p.AdminRoles), list(p.ProjectRoles), guide); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Next cursor: %s\n", optional(result.Value.Cursor))
			return err
		}}
	projectPage.bind(projects, 50)
	assignments := &cobra.Command{Use: "assignments", Short: "List your claimed tasks with the next action", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.MyAssignments(cmd.Context(), assignmentPage.query(cmd))
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			for _, a := range result.Value.Items {
				if err := writeAssignment(stdout, a); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Next cursor: %s\n", optional(result.Value.Cursor))
			return err
		}}
	assignmentPage.bind(assignments, 50, "project", "state", "updated-since")
	submissions := &cobra.Command{Use: "submissions", Short: "List your attempts and their stored outcomes", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.MySubmissions(cmd.Context(), submissionPage.query(cmd))
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			for _, s := range result.Value.Items {
				if _, err := fmt.Fprintf(stdout,
					"Submission: %s\nProject: %s\nTask: %s\nTitle: %s\nVersion: %s\nStatus: %s\nStatus reason: %s\nSubmitted: %s\nDecided: %s\nFindings: %s blocking, %s warning, %s coverage incomplete\nUpdated: %s\n",
					safeText(s.SubmissionID), safeText(s.ProjectID), safeText(s.TaskID), safeText(s.Title), count(s.Version),
					safeText(s.Status), optional(s.StatusReason), safeText(s.SubmittedAt), optional(s.DecidedAt),
					count(s.FindingCounts.Blocking), count(s.FindingCounts.Warning), count(s.FindingCounts.CoverageIncomplete),
					safeText(s.UpdatedAt)); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Next cursor: %s\n", optional(result.Value.Cursor))
			return err
		}}
	submissionPage.bind(submissions, 50, "project", "task", "status", "updated-since")
	var summaryProject string
	summary := &cobra.Command{Use: "summary", Short: "Count your claims and attempts and total your awards", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			var project *string
			if cmd.Flags().Changed("project") {
				project = &summaryProject
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.MySummary(cmd.Context(), project)
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			v := result.Value
			if _, err := fmt.Fprintf(stdout,
				"Project: %s\nActive assignments: %s\nClosed assignments: %s\nSubmissions: %s evaluation pending, %s review pending, %s accepted, %s needs revision, %s rejected\n",
				optional(v.ProjectID), count(v.Assignments.Active), count(v.Assignments.Closed), count(v.Submissions.EvaluationPending),
				count(v.Submissions.ReviewPending), count(v.Submissions.Accepted), count(v.Submissions.NeedsRevision),
				count(v.Submissions.Rejected)); err != nil {
				return err
			}
			for _, award := range v.AwardTotals {
				if _, err := fmt.Fprintf(stdout, "Award total: %s %s %s\n",
					safeText(award.Instrument), safeText(award.Unit), safeText(award.Quantity)); err != nil {
					return err
				}
			}
			return nil
		}}
	summary.Flags().StringVar(&summaryProject, "project", "", "Only this project (needs your Submitter grant)")
	me.AddCommand(projects, assignments, submissions, summary)
	root.AddCommand(me)
}

func writeAssignment(w io.Writer, a api.ContributorAssignment) error {
	if _, err := fmt.Fprintf(w,
		"Assignment: %s\nProject: %s\nTask: %s\nTitle: %s\nState: %s\nAssignment status: %s\nTask status: %s\nClaimed: %s\nStarted: %s\nReleased: %s\nLocked guide version: %s\nNext action: %s\nUpdated: %s\n",
		safeText(a.AssignmentID), safeText(a.ProjectID), safeText(a.TaskID), safeText(a.Title), safeText(a.State),
		safeText(a.AssignmentStatus), optional(a.TaskStatus), safeText(a.ClaimedAt), optional(a.StartedAt),
		optional(a.ReleasedAt), optional(a.LockedGuideVersion), safeText(a.NextAction), safeText(a.UpdatedAt)); err != nil {
		return err
	}
	if s := a.LatestSubmission; s != nil {
		if _, err := fmt.Fprintf(w, "Latest submission: %s version %s %s\n",
			safeText(s.SubmissionID), count(s.Version), safeText(s.Status)); err != nil {
			return err
		}
	}
	if r := a.Revision; r != nil {
		clock := "clock paused"
		if r.DeadlineAt != nil {
			clock = "deadline " + safeText(*r.DeadlineAt)
		}
		if _, err := fmt.Fprintf(w, "Revision: round %d of %d, %s, %s, %s\n",
			r.NextRevisionRound, r.MaxRevisionRounds, safeText(r.Outcome), safeText(r.Disposition), clock); err != nil {
			return err
		}
	}
	return writeCompensation(w, a.Compensation)
}

func jsonOrError(stdout io.Writer, raw []byte, err error) error {
	if err != nil {
		return err
	}
	return writeJSON(stdout, raw)
}

func addPreparationReads(task *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var page pageFlags
	preparations := &cobra.Command{Use: "preparations TASK_ID", Short: "List your ZIP preparations for one task, newest first", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.Preparations(cmd.Context(), args[0], page.query(cmd))
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			for _, p := range result.Value.Items {
				if err := writePreparation(stdout, p); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Next cursor: %s\n", optional(result.Value.Cursor))
			return err
		}}
	page.bind(preparations, 25)
	task.AddCommand(preparations)
	task.AddCommand(&cobra.Command{Use: "preparation TASK_ID PREPARATION_ID", Short: "Read one of your preparations with its intake findings", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.Preparation(cmd.Context(), args[0], args[1])
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			if err := writePreparation(stdout, result.Value.PreparationSummary); err != nil {
				return err
			}
			_, err = fmt.Fprintf(stdout, "Findings: %d (use --output json for details)\n", len(result.Value.Findings))
			return err
		}})
}

func writePreparation(w io.Writer, p api.PreparationSummary) error {
	findings := "—"
	if c := p.FindingCounts; c != nil {
		findings = count(c.Blocking) + " blocking, " + count(c.Warning) + " warning, " + count(c.CoverageIncomplete) + " coverage incomplete"
	}
	_, err := fmt.Fprintf(w,
		"Preparation: %s\nTask: %s\nAssignment: %s\nOutcome: %s\nState: %s\nStorage status: %s\nInfrastructure failure: %s\nArchive: %s (%s bytes)\nFinding counts: %s\nAdmission: %s\nSubmission: %s\nCreated: %s\nCompleted: %s\n",
		safeText(p.PreparationID), safeText(p.TaskID), safeText(p.AssignmentID), safeText(p.Outcome), safeText(p.State),
		optional(p.StorageStatus), optional(p.InfrastructureFailureCode), safeText(p.ArchiveSHA256), count(p.ArchiveByteCount),
		findings, optional(p.AdmissionID), optional(p.SubmissionID), safeText(p.CreatedAt), optional(p.CompletedAt))
	return err
}
