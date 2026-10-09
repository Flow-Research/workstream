package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addGuideApproval(guide *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var input, key string
	approve := &cobra.Command{
		Use: "approve-pre PROJECT_ID GUIDE_ID COMPILATION_ID", Short: "Approve the exact pre-submission proposal (not activation)", Args: cobra.ExactArgs(3),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readGuideInput(input)
			if err != nil {
				return err
			}
			result, err := apiClient.ApproveGuidePreSubmission(cmd.Context(), args[0], args[1], args[2], body, key)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Pre-submission approval (not post-policy approval or guide activation)", result.Raw}})
		},
	}
	approve.Flags().StringVar(&input, "input", "", "Required public approval JSON file (at most 1MiB); acknowledge warnings deliberately")
	approve.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID; retain with unchanged input for manual replay")
	guide.AddCommand(approve)
}
