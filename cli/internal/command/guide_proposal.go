package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addGuideProposal(guide *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	guide.AddCommand(&cobra.Command{
		Use: "proposal PROJECT_ID GUIDE_ID COMPILATION_ID", Short: "Inspect an exact finalized proposal (does not approve or activate)", Args: cobra.ExactArgs(3),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.GuideProposal(cmd.Context(), args[0], args[1], args[2])
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Guide proposal (not approval or activation)", result.Raw}})
		},
	})
}
