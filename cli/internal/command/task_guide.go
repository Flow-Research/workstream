package command

import (
	"encoding/json"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/Flow-Research/workstream/cli/internal/download"
	"github.com/spf13/cobra"
)

func addTaskGuide(task *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var directory string
	cmd := &cobra.Command{
		Use: "guide TASK_ID", Short: "Read or download the task's exact guide before or after claiming", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.WorkContext(cmd.Context(), args[0])
			if err != nil {
				return err
			}
			if directory != "" {
				root, err := download.OpenRoot(directory)
				if err != nil {
					return err
				}
				defer root.Close()
				for _, document := range result.Value.GuideDocuments {
					if err := downloadGuide(root, document, func(target io.Writer) error {
						return apiClient.DownloadGuideDocument(cmd.Context(), result.Value.Task.TaskID, document, target)
					}); err != nil {
						return err
					}
				}
			}
			if *output == "json" {
				body, err := json.Marshal(api.ApprovedContributorGuide{
					ProjectID: result.Value.Project.ID, GuideID: result.Value.Guide.ID,
					Version: result.Value.Guide.Version, Documents: result.Value.GuideDocuments,
				})
				if err != nil {
					return err
				}
				return writeSafeJSON(stdout, body)
			}
			return writeTaskContextFields(stdout, []contextField{
				{"Guide version", result.Value.Guide.Version}, {"Guide documents", result.Value.GuideDocuments},
			})
		},
	}
	cmd.Flags().StringVar(&directory, "download", "", "Download verified originals into an existing directory (never overwrite)")
	task.AddCommand(cmd)
}

func downloadGuide(root *download.Root, document api.TaskGuideDocument, write func(io.Writer) error) error {
	name := document.Filename()
	stage, err := root.Stage(name)
	if err != nil {
		return err
	}
	defer stage.Abort()
	if err := write(stage); err != nil {
		return err
	}
	if err := stage.Seal(); err != nil {
		return err
	}
	return stage.Publish()
}
