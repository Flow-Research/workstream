package command

import (
	"encoding/json"
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addTaskContextReads(task *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	task.AddCommand(&cobra.Command{
		Use: "context TASK_ID", Short: "Inspect governing guide, policy identities and server action hints", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.WorkContext(cmd.Context(), args[0])
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			value := result.Value
			fields := []contextField{
				{"Task", value.Task}, {"Project", value.Project}, {"Guide", value.Guide},
				{"Review policy", value.ReviewPolicy}, {"Revision policy", value.RevisionPolicy},
				{"Contribution policy version", value.ContributionPolicyVersionID},
				{"Lifecycle (server hints, not authorization)", value.Lifecycle},
				{"Guide documents", value.GuideDocuments},
			}
			if value.RevisionContext != nil {
				fields = append(fields, contextField{"Revision context", value.RevisionContext})
			}
			return writeTaskContextFields(stdout, fields)
		},
	})
	task.AddCommand(&cobra.Command{
		Use: "requirements TASK_ID", Short: "Inspect locked intake requirements (does not upload a submission)", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.SubmissionRequirements(cmd.Context(), args[0])
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			value := result.Value
			return writeTaskContextFields(stdout, []contextField{
				{"Task", value.TaskID}, {"Project", value.ProjectID}, {"Guide version", value.GuideVersion},
				{"Policy schema version", value.PolicySchemaVersion}, {"Merge algorithm version", value.MergeAlgorithmVersion},
				{"Required artifacts", value.RequiredArtifacts},
				{"Required evidence", value.RequiredEvidence}, {"Forbidden artifacts", value.ForbiddenArtifacts},
				{"Manifest required", value.ManifestRequired},
				{"Artifact hash required", value.ArtifactHashRequired}, {"Artifact hash algorithm", value.ArtifactHashAlgorithm},
				{"Allowed storage schemes", value.AllowedStorageSchemes}, {"Storage reference rules", value.StorageReferenceRules},
				{"Maximum file size bytes", value.MaximumFileSizeBytes}, {"Maximum package size bytes", value.MaximumPackageSizeBytes},
				{"Maximum archive entries", value.MaximumArchiveEntries}, {"Maximum archive size bytes", value.MaximumArchiveSizeBytes},
				{"Packaging", value.Packaging},
			})
		},
	})
	addTaskGuide(task, client, output, stdout)
}

type contextField struct {
	label string
	value any
}

// Compact JSON keeps nested requirements complete without interpreting them.
// Escape terminal controls even when JSON encoders leave Unicode format marks.
func writeTaskContextFields(stdout io.Writer, fields []contextField) error {
	for _, field := range fields {
		encoded, err := json.Marshal(field.value)
		if err != nil {
			return err
		}
		if _, err := fmt.Fprintf(stdout, "%s: %s\n", field.label, safeText(string(encoded))); err != nil {
			return err
		}
	}
	return nil
}
