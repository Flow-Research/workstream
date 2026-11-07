package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addGuideDispatch(guide *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	for _, assistance := range []bool{true, false} {
		var key string
		name, description := "compile-requirements", "Explicitly compile uploaded manager requirements without model inference"
		if assistance {
			name, description = "assist", "Explicitly request configured model assistance for the uploaded guide"
		}
		command := &cobra.Command{
			Use: name + " PROJECT_ID GUIDE_ID", Short: description, Args: cobra.ExactArgs(2),
			RunE: func(cmd *cobra.Command, args []string) error {
				apiClient, err := client()
				if err != nil {
					return err
				}
				var result api.Result[api.GuideCompilationDispatch]
				if assistance {
					result, err = apiClient.RequestGuideAssistance(cmd.Context(), args[0], args[1], key)
				} else {
					result, err = apiClient.CompileGuideRequirements(cmd.Context(), args[0], args[1], key)
				}
				if err != nil {
					return err
				}
				if *output == "json" {
					return writeJSON(stdout, result.Raw)
				}
				return writeTaskContextFields(stdout, []contextField{{"Compilation request dispatch status (not completion, approval or activation)", result.Value}})
			},
		}
		command.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID; retain with the exact command, project and guide for manual replay")
		guide.AddCommand(command)
	}
}
