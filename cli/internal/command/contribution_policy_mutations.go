package command

import (
	"encoding/json"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addContributionPolicyMutations(policy *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	for _, action := range []string{"create", "update", "publish", "retire"} {
		var input, key string
		use, count := action+" PROJECT_ID POLICY_ID VERSION_ID", 3
		if action == "create" {
			use, count = "create PROJECT_ID", 1
		}
		cmd := &cobra.Command{
			Use: use, Short: action + " an explicitly selected contribution policy under current project policy authority", Args: cobra.ExactArgs(count),
			RunE: func(cmd *cobra.Command, args []string) error {
				apiClient, err := client()
				if err != nil {
					return err
				}
				body := json.RawMessage(`{}`)
				if action == "create" || action == "update" {
					body, err = readJSONInput(input)
					if err != nil {
						return err
					}
				}
				policyID, version := "", ""
				if action != "create" {
					policyID, version = args[1], args[2]
				}
				result, err := apiClient.MutateContributionPolicy(cmd.Context(), action, args[0], policyID, version, body, key)
				if err != nil {
					return err
				}
				if *output == "json" {
					return writeJSON(stdout, result.Raw)
				}
				return writeTaskContextFields(stdout, []contextField{{"Contribution policy event (not guide activation or payment)", result.Raw}})
			},
		}
		if action == "create" || action == "update" {
			cmd.Flags().StringVar(&input, "input", "", "Required public JSON file (at most 1MiB); create name or complete replacement rules")
		}
		cmd.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID for unchanged manual replay")
		policy.AddCommand(cmd)
	}
}
