package command

import (
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addTaskReads(project *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var limit int
	var cursor, status, assignee, importBatch, updatedSince string
	tasks := &cobra.Command{
		Use: "tasks PROJECT_ID", Short: "List one page of tasks under project-manager authority", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			var continuation *string
			if cmd.Flags().Changed("cursor") {
				continuation = &cursor
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			filters := api.TaskFilters{}
			for name, target := range map[string]**string{
				"status": &filters.Status, "assignee": &filters.Assignee,
				"import-batch": &filters.ImportBatch, "updated-since": &filters.UpdatedSince,
			} {
				if cmd.Flags().Changed(name) {
					value, _ := cmd.Flags().GetString(name)
					*target = &value
				}
			}
			result, err := apiClient.Tasks(cmd.Context(), args[0], limit, continuation, filters)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			if _, err := fmt.Fprintf(stdout, "Project: %s\nTasks: %d\n", safeText(result.Value.ProjectID), len(result.Value.Items)); err != nil {
				return err
			}
			for _, task := range result.Value.Items {
				if err := writeTaskSummary(stdout, task); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Next cursor: %s\n", optional(result.Value.NextCursor))
			return err
		},
	}
	tasks.Flags().IntVar(&limit, "limit", 50, "Page size (1–100; keep unchanged when continuing)")
	tasks.Flags().StringVar(&cursor, "cursor", "", "Opaque next cursor from the previous page")
	tasks.Flags().StringVar(&status, "status", "", "Only tasks in this status")
	tasks.Flags().StringVar(&assignee, "assignee", "", "Only tasks currently assigned to this actor UUID")
	tasks.Flags().StringVar(&importBatch, "import-batch", "", "Only members of this native import batch UUID")
	tasks.Flags().StringVar(&updatedSince, "updated-since", "", "Only tasks changed at or after this RFC 3339 time")
	project.AddCommand(tasks)
	task := &cobra.Command{
		Use: "task PROJECT_ID TASK_ID", Short: "Inspect a task under project-manager authority", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.Task(cmd.Context(), args[0], args[1])
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
			if err := writeAssignmentOutcome(stdout, t.LastAssignmentOutcome); err != nil {
				return err
			}
			if t.RevisionContext != nil {
				if err := writeTaskContextFields(stdout, []contextField{{"Revision context", t.RevisionContext}}); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout,
				"Task size: %s\nDescription: %s\nAcceptance criteria: %s\nRejection criteria: %s\nSource type: %s\nSource reference: %s\nSource hash: %s\nImport batch: %s\nExternal task: %s\nCreated by: %s\nAssigned to: %s\n",
				safeText(t.TaskSize), safeText(t.Description), optional(t.AcceptanceCriteria), optional(t.RejectionCriteria), safeText(t.SourceType),
				optional(t.SourceRef), optional(t.SourcePayloadHash), optional(t.ImportBatchID), optional(t.ExternalTaskID), safeText(t.CreatedBy), optional(t.AssignedTo))
			return err
		},
	}
	addManagerTaskWrites(task, client, output, stdout)
	addRevisionRepair(task, client, output, stdout)
	project.AddCommand(task)
}

func writeTaskSummary(w io.Writer, t api.TaskSummary) error {
	minutes := "—"
	if t.EstimatedTimeMinutes != nil {
		minutes = fmt.Sprint(*t.EstimatedTimeMinutes)
	}
	_, err := fmt.Fprintf(w,
		"Task: %s\nProject: %s\nTitle: %s\nStatus: %s\nType: %s\nDifficulty: %s\nSkills: %s\nEstimated minutes: %s\nDeadline: %s\nCreated: %s\nUpdated: %s\n",
		safeText(t.TaskID), safeText(t.ProjectID), safeText(t.Title), safeText(t.Status), optional(t.TaskType), optional(t.Difficulty),
		list(t.SkillTags), minutes, optional(t.DeadlineAt), safeText(t.CreatedAt), safeText(t.UpdatedAt))
	return err
}
