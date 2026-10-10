package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addGuidePostCorrection(guide *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var input, key string
	correct := &cobra.Command{
		Use: "correct-post PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID", Short: "Request a saved evaluation-policy correction successor (does not dispatch)", Args: cobra.ExactArgs(4),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readGuideInput(input)
			if err != nil {
				return err
			}
			result, err := apiClient.CorrectGuidePostSubmission(cmd.Context(), args[0], args[1], args[2], args[3], body, key)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Saved post-submission correction (not dispatched or activated)", result.Raw}})
		},
	}
	correct.Flags().StringVar(&input, "input", "", "Required public correction JSON file containing inspected target and reason (at most 1MiB)")
	correct.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID; retain with unchanged input for manual replay")
	guide.AddCommand(correct)
}
