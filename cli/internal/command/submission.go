package command

import (
	"fmt"
	"io"
	"os"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addSubmissionCommands(root, task *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	{
		var assignment, predecessor, summary, attestation, path, key string
		var revisionPreparationID, revisionPreparationSHA256 string
		name, description := "submit", "Upload one ZIP for initial checks and durable evaluation acceptance"
		cmd := &cobra.Command{Use: name + " TASK_ID", Short: description, Args: cobra.ExactArgs(1)}
		cmd.Flags().StringVar(&assignment, "assignment", "", "Required active task-assignment UUID")
		cmd.Flags().StringVar(&predecessor, "predecessor", "", "Predecessor Submission UUID when required by the task")
		cmd.Flags().StringVar(&summary, "summary", "", "Exact printable ASCII packet summary; preserve for same-key replay")
		cmd.Flags().StringVar(&attestation, "attestation", "", "Exact printable ASCII contributor attestation")
		cmd.Flags().StringVar(&path, "file", "", "Required regular ZIP; keep unchanged for explicit replay")
		cmd.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID; never retried automatically")
		cmd.Flags().StringVar(&revisionPreparationID, "revision-preparation-id", "", "Exact preparation UUID from task context; required with --predecessor")
		cmd.Flags().StringVar(&revisionPreparationSHA256, "revision-preparation-sha256", "", "Exact preparation digest from task context; required with --predecessor")
		cmd.RunE = func(cmd *cobra.Command, args []string) error {
			var acknowledgement *api.RevisionAcknowledgement
			{
				hasID := cmd.Flags().Changed("revision-preparation-id")
				hasSHA := cmd.Flags().Changed("revision-preparation-sha256")
				if cmd.Flags().Changed("predecessor") != (hasID && hasSHA) || hasID != hasSHA {
					return commandError{"invalid_arguments", "revision preparation ID and sha256 are both required with --predecessor and forbidden for initial submission"}
				}
				if hasID {
					acknowledgement = &api.RevisionAcknowledgement{
						PreparationID: revisionPreparationID, PreparationSHA256: revisionPreparationSHA256,
					}
				}
			}
			packet := api.SubmissionPacket{Assignment: assignment}
			if cmd.Flags().Changed("predecessor") {
				packet.Predecessor = &predecessor
			}
			if cmd.Flags().Changed("summary") {
				packet.Summary = &summary
			}
			if cmd.Flags().Changed("attestation") {
				packet.Attestation = &attestation
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
			result, err := c.SubmitSubmission(cmd.Context(), args[0], key, packet, acknowledgement, file)
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
			_, err = fmt.Fprintln(stdout, "Initial checks passed. Evaluation is pending; use the operation ID or the same idempotency key to observe progress.")
			return err
		}
		task.AddCommand(cmd)
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
