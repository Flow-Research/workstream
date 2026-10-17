package command

import (
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addContributionPolicyReads(project *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	policy := &cobra.Command{Use: "contribution-policy", Short: "Inspect and manage contribution policies through public Finance authority"}
	policy.AddCommand(&cobra.Command{
		Use: "current PROJECT_ID", Short: "Discover the current published and open draft selectors", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.CurrentContributionPolicy(cmd.Context(), args[0])
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Current selectors (not authority)", result.Raw}})
		},
	})
	var version string
	show := &cobra.Command{
		Use: "show PROJECT_ID POLICY_ID", Short: "Inspect the backend-selected version or an explicit historical version", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			var selected *string
			if cmd.Flags().Changed("version") {
				selected = &version
			}
			result, err := apiClient.ContributionPolicy(cmd.Context(), args[0], args[1], selected)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Contribution policy (not authority or readiness)", result.Raw}})
		},
	}
	show.Flags().StringVar(&version, "version", "", "Optional exact version UUID; omitted means backend selection, not auto-discovery")
	policy.AddCommand(show)
	var page pageFlags
	list := &cobra.Command{
		Use: "list PROJECT_ID", Short: "List every stored policy version with its draft, published or retired status, oldest first", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ContributionPolicyVersions(cmd.Context(), args[0], page.query(cmd))
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			for _, v := range result.Value.Items {
				if _, err := fmt.Fprintf(stdout, "Policy: %s (%s)\nVersion: %s #%s %s\nCreated: %s\nPublished: %s\nRetired: %s\nRules: %d\n",
					safeText(v.ContributionPolicyID), safeText(v.PolicyStatus), safeText(v.ContributionPolicyVersionID),
					count(v.VersionNumber), safeText(v.VersionStatus), safeText(v.CreatedAt), optional(v.PublishedAt),
					optional(v.RetiredAt), len(v.Rules)); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Next cursor: %s\n", optional(result.Value.Cursor))
			return err
		},
	}
	page.bind(list, 50)
	policy.AddCommand(list)
	addContributionPolicyMutations(policy, client, output, stdout)
	project.AddCommand(policy)
}
