package command

import (
	"fmt"
	"io"
	"os"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func postSubmissionRecovery(code *string) string {
	if code == nil {
		return ""
	}
	message := map[string]string{
		"post_submission_capacity_exceeded":          "POST could not acquire enough checker capacity.",
		"post_submission_deadline_exceeded":          "POST evaluation timed out.",
		"post_submission_material_unavailable":       "POST could not read the retained submission material.",
		"post_submission_implementation_unavailable": "The POST checker runtime is unavailable.",
		"post_submission_invalid_output":             "The POST checker returned an invalid response.",
		"post_submission_delivery_failed":            "The worker could not finish POST processing.",
		"post_submission_outcome_unknown":            "The POST execution outcome is uncertain.",
	}[*code]
	if message == "" {
		return ""
	}
	return message + " Your Submission is retained. Contact an Operator for recovery."
}

func addSubmissionCommands(root, task *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	{
		var assignment, feedback, path, key string
		cmd := &cobra.Command{Use: "submit TASK_ID", Short: "Submit one ZIP for initial work or revision", Args: cobra.ExactArgs(1)}
		cmd.Flags().StringVar(&assignment, "assignment", "", "Required active task-assignment UUID")
		cmd.Flags().StringVar(&feedback, "feedback", "", "Optional project feedback, up to 4096 printable ASCII bytes without leading or trailing whitespace")
		cmd.Flags().StringVar(&path, "file", "", "Required regular ZIP; keep unchanged for explicit replay")
		cmd.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID; never retried automatically")
		cmd.RunE = func(cmd *cobra.Command, args []string) error {
			input := api.SubmissionInput{Assignment: assignment}
			if cmd.Flags().Changed("feedback") {
				input.Feedback = &feedback
			}
			c, err := client()
			if err != nil {
				return err
			}
			bad := commandError{"invalid_arguments", "--file must be a readable, nonempty regular ZIP of at most 500MiB"}
			info, err := os.Stat(path)
			if err != nil || !info.Mode().IsRegular() || info.Size() <= 0 || info.Size() > api.MaxSubmissionZipBytes {
				return bad
			}
			file, err := os.Open(path)
			if err != nil {
				return bad
			}
			defer file.Close()
			result, err := c.SubmitSubmission(cmd.Context(), args[0], key, input, file)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeSafeJSON(stdout, result.Raw)
			}
			receipt := result.Value
			receipt.Feedback = nil // Printed below as readable intake feedback lines.
			if err := writeTaskContextFields(stdout, []contextField{{"Submission accepted for evaluation", receipt}}); err != nil {
				return err
			}
			// Nonblocking intake findings stay visible after admission; they are
			// intake feedback, not a post-submission outcome.
			for _, line := range api.IntakeFeedbackLines(result.Value.Feedback) {
				if _, err := fmt.Fprintln(stdout, "Intake feedback:", safeText(line)); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Initial checks passed. Evaluation is pending. Run workstream task status %s to see the outcome.\n", receipt.AssignmentID)
			return err
		}
		task.AddCommand(cmd)
	}

	{
		var page pageFlags
		status := &cobra.Command{Use: "status ASSIGNMENT_ID", Short: "Read your assignment status and feedback", Args: cobra.ExactArgs(1)}
		page.bind(status, 25)
		status.RunE = func(cmd *cobra.Command, args []string) error {
			if !api.ValidUUID(args[0]) {
				return commandError{"invalid_arguments", "assignment ID must be a UUID"}
			}
			transport, err := client()
			if err != nil {
				return err
			}
			query := page.query(cmd)
			result, err := transport.TaskAssignment(cmd.Context(), args[0], query.Limit, query.Cursor)
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			value := result.Value
			fields := []contextField{
				{"Assignment", value.Assignment.AssignmentID}, {"Task", value.Assignment.TaskID},
				{"Status", value.CurrentStatus},
				{"Reason", optional(value.StatusReason)}, {"Next action", value.NextAction},
				{"Terms", value.Assignment.Compensation}, {"Revision", value.Assignment.Revision},
				{"Latest submitted attempt", value.Assignment.LatestSubmission},
			}
			if value.NextAction == "contact_operator" {
				fields = append(fields, contextField{"Evaluation recovery", postSubmissionRecovery(value.StatusReason)})
			}
			if value.Intake != nil {
				fields = append(fields, contextField{"Intake stage", value.Intake.Stage},
					contextField{"Intake feedback", api.IntakeFeedbackLines(value.Intake.Feedback)})
			}
			if len(value.PostFindings) != 0 {
				fields = append(fields, contextField{"Feedback for submission", optional(value.FeedbackSubmissionID)},
					contextField{"Evaluation findings", value.PostFindings})
			}
			if value.AcceptedEvidence != nil {
				fields = append(fields, contextField{"Accepted evidence", value.AcceptedEvidence})
			}
			if value.NextCursor != nil {
				fields = append(fields, contextField{"Next feedback cursor", *value.NextCursor})
			}
			return writeTaskContextFields(stdout, fields)
		}
		task.AddCommand(status)
	}

	{
		var operation, key string
		progress := &cobra.Command{Use: "submission-operation TASK_ID", Short: "Inspect one submission operation without resubmitting", Args: cobra.ExactArgs(1)}
		progress.Flags().StringVar(&operation, "operation-id", "", "Operation UUID; choose this or --idempotency-key")
		progress.Flags().StringVar(&key, "idempotency-key", "", "Your original caller UUID key; choose this or --operation-id")
		progress.RunE = func(cmd *cobra.Command, args []string) error {
			if cmd.Flags().Changed("operation-id") == cmd.Flags().Changed("idempotency-key") || (operation == "" && key == "") {
				return commandError{"invalid_arguments", "provide exactly one nonempty --operation-id or --idempotency-key"}
			}
			c, err := client()
			if err != nil {
				return err
			}
			result, err := c.SubmissionOperation(cmd.Context(), args[0], operation, key)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeSafeJSON(stdout, result.Raw)
			}
			fields := []contextField{{"Submission operation", result.Value}}
			if result.Value.NextAction == "contact_operator" {
				fields = append(fields, contextField{"Evaluation recovery", postSubmissionRecovery(result.Value.FailureCode)})
			}
			return writeTaskContextFields(stdout, fields)
		}
		task.AddCommand(progress)
	}

	var historyLimit int
	var historyCursor string
	history := &cobra.Command{Use: "submissions TASK_ID", Short: "Read one page of authorized immutable submission history", Args: cobra.ExactArgs(1)}
	history.Flags().IntVar(&historyLimit, "limit", 25, "Page size (1–100)")
	history.Flags().StringVar(&historyCursor, "cursor", "", "Opaque next cursor; no automatic pagination")
	history.RunE = func(cmd *cobra.Command, args []string) error {
		var cursor *string
		if cmd.Flags().Changed("cursor") {
			cursor = &historyCursor
		}
		c, err := client()
		if err != nil {
			return err
		}
		result, err := c.TaskSubmissions(cmd.Context(), args[0], historyLimit, cursor)
		if err != nil {
			return err
		}
		if *output == "json" {
			return writeSafeJSON(stdout, result.Raw)
		}
		return writeTaskContextFields(stdout, []contextField{{"Submission history", result.Value}, {"Revision change summary", "not included in submission history; use workstream task context " + args[0] + " for current task revision context, not historical submission context"}})
	}
	task.AddCommand(history)
	submission := &cobra.Command{Use: "submission", Short: "Read authorized submission history and checker findings"}
	submission.AddCommand(&cobra.Command{Use: "show SUBMISSION_ID", Short: "Read one immutable Submission", Args: cobra.ExactArgs(1), RunE: func(cmd *cobra.Command, args []string) error {
		c, err := client()
		if err != nil {
			return err
		}
		result, err := c.Submission(cmd.Context(), args[0])
		if err != nil {
			return err
		}
		if *output == "json" {
			return writeSafeJSON(stdout, result.Raw)
		}
		return writeTaskContextFields(stdout, []contextField{{"Submission", result.Value}, {"Revision change summary", "not included in this submission response; use workstream task context " + result.Value.Task + " for current task revision context, not historical submission context"}})
	}})
	var run, cursorValue string
	var limit int
	findings := &cobra.Command{Use: "findings SUBMISSION_ID", Short: "Read contributor-visible checker runs or one exact run; not acceptance", Args: cobra.ExactArgs(1)}
	findings.Flags().StringVar(&run, "run", "", "Exact checker-run UUID instead of a page")
	findings.Flags().IntVar(&limit, "limit", 25, "Page size (1–100)")
	findings.Flags().StringVar(&cursorValue, "cursor", "", "Opaque next cursor; no automatic pagination")
	findings.RunE = func(cmd *cobra.Command, args []string) error {
		if cmd.Flags().Changed("run") && (run == "" || cmd.Flags().Changed("limit") || cmd.Flags().Changed("cursor")) {
			return commandError{"invalid_arguments", "--run requires a UUID and cannot be combined with pagination flags"}
		}
		var cursor *string
		if cmd.Flags().Changed("cursor") {
			cursor = &cursorValue
		}
		c, err := client()
		if err != nil {
			return err
		}
		result, err := c.SubmissionFindings(cmd.Context(), args[0], run, limit, cursor)
		if err != nil {
			return err
		}
		if *output == "json" {
			return writeSafeJSON(stdout, result.Raw)
		}
		return writeTaskContextFields(stdout, []contextField{{"Checker evidence (not acceptance)", result.Raw}})
	}
	submission.AddCommand(findings)
	root.AddCommand(submission)
}
