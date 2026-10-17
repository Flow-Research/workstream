package command

import (
	"fmt"
	"io"
	"strings"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

// projectFlags adds the submitter filter to the shared page flags.
type projectFlags struct {
	pageFlags
	submitter string
}

func (f *projectFlags) query(cmd *cobra.Command) api.ProjectWorkQuery {
	q := api.ProjectWorkQuery{PageQuery: f.pageFlags.query(cmd)}
	if cmd.Flags().Changed("submitter") {
		q.SubmitterID = &f.submitter
	}
	return q
}

func taskCounts(counts api.TaskStatusCounts) string {
	parts := make([]string, 0, len(counts))
	for _, status := range []string{"draft", "screening", "ready", "claimed", "in_progress", "submitted",
		"evaluation_pending", "review_pending", "needs_revision", "accepted"} {
		parts = append(parts, count(counts[status])+" "+strings.ReplaceAll(status, "_", " "))
	}
	return strings.Join(parts, ", ")
}

// addManagerReads adds the Project Manager's project-wide work reads under `project`.
func addManagerReads(project *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var submissionPage projectFlags
	var assignmentPage, batchPage pageFlags
	submissions := &cobra.Command{Use: "submissions PROJECT_ID", Short: "List every attempt in a project with its submitter and stored outcome", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ProjectSubmissions(cmd.Context(), args[0], submissionPage.query(cmd))
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			for _, s := range result.Value.Items {
				if _, err := fmt.Fprintf(stdout,
					"Submission: %s\nTask: %s\nTitle: %s\nSubmitter: %s\nVersion: %s\nStatus: %s\nStatus reason: %s\nSubmitted: %s\nDecided: %s\nFindings: %s blocking, %s warning, %s coverage incomplete\nUpdated: %s\n",
					safeText(s.SubmissionID), safeText(s.TaskID), safeText(s.Title), safeText(s.SubmitterActorID), count(s.Version),
					safeText(s.Status), optional(s.StatusReason), safeText(s.SubmittedAt), optional(s.DecidedAt),
					count(s.FindingCounts.Blocking), count(s.FindingCounts.Warning), count(s.FindingCounts.CoverageIncomplete),
					safeText(s.UpdatedAt)); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Next cursor: %s\n", optional(result.Value.Cursor))
			return err
		}}
	submissionPage.bind(submissions, 50, "task", "status", "updated-since")
	submissions.Flags().StringVar(&submissionPage.submitter, "submitter", "", "Only attempts by this actor UUID")
	assignments := &cobra.Command{Use: "assignments PROJECT_ID", Short: "List every claim in a project with its contributor", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ProjectAssignments(cmd.Context(), args[0], api.ProjectWorkQuery{PageQuery: assignmentPage.query(cmd)})
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			for _, a := range result.Value.Items {
				if _, err := fmt.Fprintf(stdout, "Contributor: %s\n", safeText(a.ContributorActorID)); err != nil {
					return err
				}
				if err := writeAssignment(stdout, a.ContributorAssignment); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Next cursor: %s\n", optional(result.Value.Cursor))
			return err
		}}
	assignmentPage.bind(assignments, 50, "state")
	summary := &cobra.Command{Use: "summary PROJECT_ID", Short: "Count a project's tasks, claims and attempts", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ProjectSummary(cmd.Context(), args[0])
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			v := result.Value
			rate := "—"
			if v.AcceptanceRate != nil {
				rate = fmt.Sprintf("%.4f", *v.AcceptanceRate)
			}
			if _, err := fmt.Fprintf(stdout,
				"Project: %s\nTasks: %s\nActive assignments: %s\nClosed assignments: %s\nSubmissions: %s evaluation pending, %s review pending, %s accepted, %s needs revision, %s rejected\nAcceptance rate: %s\nChecker infrastructure failures: %s\n",
				safeText(v.ProjectID), taskCounts(v.Tasks), count(v.Assignments.Active), count(v.Assignments.Closed),
				count(v.Submissions.EvaluationPending), count(v.Submissions.ReviewPending), count(v.Submissions.Accepted),
				count(v.Submissions.NeedsRevision), count(v.Submissions.Rejected), rate,
				count(v.CheckerInfrastructureFailures)); err != nil {
				return err
			}
			if v.AwardTotals == nil {
				_, err = fmt.Fprintln(stdout, "Award totals: not shown (needs Finance Authority on this project)")
				return err
			}
			for _, award := range *v.AwardTotals {
				if _, err := fmt.Fprintf(stdout, "Award total: %s %s %s\n",
					safeText(award.Instrument), safeText(award.Unit), safeText(award.Quantity)); err != nil {
					return err
				}
			}
			return nil
		}}
	batches := &cobra.Command{Use: "import-batches PROJECT_ID", Short: "List a project's task import batches with state and member counts", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ProjectImportBatches(cmd.Context(), args[0], api.ProjectWorkQuery{PageQuery: batchPage.query(cmd)})
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			for _, b := range result.Value.Items {
				if _, err := fmt.Fprintf(stdout,
					"Batch: %s\nSource: %s\nLabel: %s\nFile: %s (%s bytes)\nRows: %s\nState: %s\nCreated: %s\nCommitted: %s\nTasks: %s\n",
					safeText(b.BatchID), safeText(b.SourceID), optional(b.Label), safeText(b.SHA256), count(b.ByteCount),
					count(b.RowCount), safeText(b.State), safeText(b.CreatedAt), optional(b.CommittedAt),
					taskCounts(b.TaskCounts)); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Next cursor: %s\n", optional(result.Value.Cursor))
			return err
		}}
	batchPage.bind(batches, 50)
	project.AddCommand(submissions, assignments, summary, batches)
}
