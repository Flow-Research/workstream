package command

import (
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addContributorTasks(root *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	task := &cobra.Command{Use: "task", Short: "Discover and inspect contributor work"}
	var limit int
	var cursor string
	ready := &cobra.Command{
		Use: "ready PROJECT_ID", Short: "List ready work under your Submitter or Reviewer grant", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			var continuation *string
			if cmd.Flags().Changed("cursor") {
				continuation = &cursor
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ReadyTasks(cmd.Context(), args[0], limit, continuation)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			if _, err := fmt.Fprintf(stdout, "Project: %s\nReady tasks: %d\n", safeText(result.Value.ProjectID), len(result.Value.Items)); err != nil {
				return err
			}
			for _, t := range result.Value.Items {
				minutes := "—"
				if t.EstimatedTimeMinutes != nil {
					minutes = fmt.Sprint(*t.EstimatedTimeMinutes)
				}
				if _, err := fmt.Fprintf(stdout,
					"Task: %s\nProject: %s\nTitle: %s\nType: %s\nDifficulty: %s\nSkills: %s\nEstimated minutes: %s\nCreated: %s\n",
					safeText(t.TaskID), safeText(t.ProjectID), safeText(t.Title), optional(t.TaskType), optional(t.Difficulty),
					list(t.SkillTags), minutes, safeText(t.CreatedAt)); err != nil {
					return err
				}
				if err := writeCompensation(stdout, t.Compensation); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Next cursor: %s\n", optional(result.Value.NextCursor))
			return err
		},
	}
	ready.Flags().IntVar(&limit, "limit", 50, "Page size (1–100; keep unchanged when continuing)")
	ready.Flags().StringVar(&cursor, "cursor", "", "Opaque next cursor from the previous page")
	task.AddCommand(ready)
	task.AddCommand(&cobra.Command{
		Use: "show TASK_ID", Short: "Inspect contributor instructions under current task authority", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ContributorTask(cmd.Context(), args[0])
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			t := result.Value
			if err := writeTaskSummary(stdout, t.TaskSummary); err != nil {
				return err
			}
			if err := writeCompensation(stdout, t.Compensation); err != nil {
				return err
			}
			_, err = fmt.Fprintf(stdout, "Description: %s\nAcceptance criteria: %s\nRejection criteria: %s\n",
				safeText(t.Description), optional(t.AcceptanceCriteria), optional(t.RejectionCriteria))
			return err
		},
	})
	addContributorTaskWrites(task, client, output, stdout)
	addTaskContextReads(task, client, output, stdout)
	root.AddCommand(task)
}

func writeCompensation(w io.Writer, terms api.CompensationTerms) error {
	if _, err := fmt.Fprintf(w, "Contribution policy version: %s\n", safeText(terms.ContributionPolicyVersionID)); err != nil {
		return err
	}
	for _, rule := range []struct {
		label string
		raw   []byte
	}{{"Accepted submission", terms.AcceptedSubmission}, {"Completed review", terms.CompletedReview}} {
		awards, valid := api.CompensationAwards(rule.raw)
		if !valid {
			return fmt.Errorf("invalid compensation terms")
		}
		if awards == nil {
			if _, err := fmt.Fprintf(w, "%s compensation: unpaid\n", rule.label); err != nil {
				return err
			}
			continue
		}
		for _, award := range awards {
			if _, err := fmt.Fprintf(w, "%s compensation: %s %s %s\n", rule.label,
				safeText(award.Instrument), safeText(award.Unit), safeText(award.Quantity)); err != nil {
				return err
			}
		}
	}
	return nil
}
