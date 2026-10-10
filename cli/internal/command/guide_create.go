package command

import (
	"io"
	"os"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addGuideCreate(project *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var input, key string
	guide := &cobra.Command{Use: "guide", Short: "Public guide setup operations"}
	create := &cobra.Command{
		Use: "create PROJECT_ID", Short: "Declare a draft guide, examples and document upload targets", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readGuideInput(input)
			if err != nil {
				return err
			}
			result, err := apiClient.CreateGuide(cmd.Context(), args[0], body, key)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Guide declaration (documents still need uploading)", result.Value}})
		},
	}
	create.Flags().StringVar(&input, "input", "", "Required regular UTF-8 JSON file containing the public guide declaration (at most 1MiB)")
	create.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID; retain with unchanged input for manual replay")
	guide.AddCommand(create)
	addGuideUpload(guide, client, output, stdout)
	addGuideProposal(guide, client, output, stdout)
	addGuidePostPolicy(guide, client, output, stdout)
	addGuideApproval(guide, client, output, stdout)
	addGuidePostApproval(guide, client, output, stdout)
	guide.AddCommand(&cobra.Command{
		Use: "setup PROJECT_ID GUIDE_ID", Short: "Inspect latest guide setup (does not approve or activate)", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.GuideSetup(cmd.Context(), args[0], args[1])
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Latest setup (not approval or activation)", result.Value}})
		},
	})
	project.AddCommand(guide)
}

func readGuideInput(path string) ([]byte, error) {
	bad := commandError{"invalid_arguments", "--input must be a readable regular JSON file of at most 1MiB"}
	info, err := os.Stat(path)
	if err != nil || !info.Mode().IsRegular() || info.Size() > api.MaxGuideInputBytes {
		return nil, bad
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, bad
	}
	defer file.Close()
	info, err = file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() > api.MaxGuideInputBytes {
		return nil, bad
	}
	body, err := io.ReadAll(io.LimitReader(file, api.MaxGuideInputBytes+1))
	if err != nil || len(body) == 0 || len(body) > api.MaxGuideInputBytes {
		return nil, bad
	}
	return body, nil
}
