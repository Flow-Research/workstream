package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addGuidePostPolicy(guide *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	guide.AddCommand(&cobra.Command{
		Use: "post-policy PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID", Short: "Inspect an exact derived evaluation policy (does not approve or activate)", Args: cobra.ExactArgs(4),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.GuidePostPolicy(cmd.Context(), args[0], args[1], args[2], args[3])
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Post-submission policy (not approval or activation)", result.Raw}})
		},
	})
}
