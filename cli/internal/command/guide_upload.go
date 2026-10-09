package command

import (
	"io"
	"os"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addGuideUpload(guide *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var path, mediaType, key string
	upload := &cobra.Command{
		Use: "upload PROJECT_ID GUIDE_ID DOCUMENT_ID", Short: "Upload one declared guide original (not approval or activation)", Args: cobra.ExactArgs(3),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			bad := commandError{"invalid_arguments", "--file must be a readable, nonempty regular original of at most 512MiB"}
			info, err := os.Stat(path)
			if err != nil || !info.Mode().IsRegular() || info.Size() <= 0 || info.Size() > api.MaxGuideDocumentBytes {
				return bad
			}
			file, err := os.Open(path)
			if err != nil {
				return bad
			}
			defer file.Close()
			info, err = file.Stat()
			if err != nil || !info.Mode().IsRegular() || info.Size() <= 0 || info.Size() > api.MaxGuideDocumentBytes {
				return bad
			}
			result, err := apiClient.UploadGuideDocument(cmd.Context(), args[0], args[1], args[2], file, info.Size(), mediaType, key)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Guide original storage receipt (not guide approval)", result.Value}})
		},
	}
	upload.Flags().StringVar(&path, "file", "", "Required regular original file; keep its bytes unchanged for manual replay")
	upload.Flags().StringVar(&mediaType, "media-type", "", "Required exact declared PDF, DOCX, PPTX or Markdown media type")
	upload.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID; no automatic retry")
	guide.AddCommand(upload)
}
