package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addGuidePostApproval(guide *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var input, key string
	approve := &cobra.Command{
		Use: "approve-post PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID", Short: "Approve the exact post-submission policy (not guide activation)", Args: cobra.ExactArgs(4),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readGuideInput(input)
			if err != nil {
				return err
			}
			result, err := apiClient.ApproveGuidePostSubmission(cmd.Context(), args[0], args[1], args[2], args[3], body, key)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Post-submission policy approval (not guide activation)", result.Raw}})
		},
	}
	approve.Flags().StringVar(&input, "input", "", "Required public approval JSON file containing the inspected target (at most 1MiB)")
	approve.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID; retain with unchanged input for manual replay")
	guide.AddCommand(approve)
}
