package command

import (
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addOperatorTasks(operations *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	task := &cobra.Command{Use: "task", Short: "System Operator task inspection"}
	var limit int
	var cursor string
	list := &cobra.Command{
		Use: "list PROJECT_ID", Short: "List one status-only task page with current system Operator authority", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			var continuation *string
			if cmd.Flags().Changed("cursor") {
				continuation = &cursor
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.OperationalTasks(cmd.Context(), args[0], limit, continuation)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeSafeJSON(stdout, result.Raw)
			}
			if _, err := fmt.Fprintf(stdout, "Project: %s\nOperator tasks: %d\n", safeText(result.Value.ProjectID), len(result.Value.Items)); err != nil {
				return err
			}
			for _, item := range result.Value.Items {
				if _, err := fmt.Fprintf(stdout, "Task: %s\nProject: %s\nStatus: %s\nCreated: %s\nUpdated: %s\n",
					safeText(item.TaskID), safeText(item.ProjectID), safeText(item.Status), safeText(item.CreatedAt), safeText(item.UpdatedAt)); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Next cursor (observation, not authority): %s\n", optional(result.Value.NextCursor))
			return err
		},
	}
	list.Flags().IntVar(&limit, "limit", 50, "Page size (1–100; keep unchanged when continuing)")
	list.Flags().StringVar(&cursor, "cursor", "", "Opaque continuation from this exact project page")
	task.AddCommand(list)
	task.AddCommand(&cobra.Command{
		Use: "locked-context PROJECT_ID TASK_ID", Short: "Inspect only exact locked policy references", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.OperationalTaskLockedContext(cmd.Context(), args[0], args[1])
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeSafeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Operator locked context (references only)", result.Raw}})
		},
	})
	operations.AddCommand(task)
}
