package command

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/Flow-Research/workstream/cli/internal/download"
	"github.com/spf13/cobra"
)

// addGuideReads adds the Project Manager's read-only guide commands.
func addGuideReads(guide *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var approvedDirectory string
	approved := &cobra.Command{
		Use: "approved PROJECT_ID", Short: "Read or download the active approved contributor guide", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ContributorGuide(cmd.Context(), args[0])
			if err != nil {
				return err
			}
			current := result.Value
			if approvedDirectory != "" {
				root, err := download.OpenRoot(approvedDirectory)
				if err != nil {
					return err
				}
				defer root.Close()
				for _, document := range current.Documents {
					if err := downloadGuide(root, document, func(target io.Writer) error {
						return apiClient.DownloadContributorGuideDocument(cmd.Context(), current.ProjectID, current.GuideID, document, target)
					}); err != nil {
						return err
					}
				}
			}
			if *output == "json" {
				return writeSafeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{
				{"Guide version", current.Version}, {"Guide documents", current.Documents},
			})
		},
	}
	approved.Flags().StringVar(&approvedDirectory, "download", "", "Download verified originals to an existing directory")
	guide.AddCommand(approved)

	var page pageFlags
	list := &cobra.Command{
		Use: "list PROJECT_ID", Short: "List the project's guide versions and their stored status", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ProjectGuides(cmd.Context(), args[0], page.query(cmd))
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			for _, g := range result.Value.Items {
				if _, err := fmt.Fprintf(stdout, "Guide: %s\nVersion: %s\nStatus: %s\nCreated: %s\nEffective: %s\n",
					safeText(g.GuideID), safeText(g.Version), safeText(g.Status), safeText(g.CreatedAt),
					optional(g.EffectiveAt)); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Next cursor: %s\n", optional(result.Value.Cursor))
			return err
		},
	}
	page.bind(list, 50, "status=draft, active or superseded")
	guide.AddCommand(list)
	guide.AddCommand(&cobra.Command{
		Use: "show PROJECT_ID GUIDE_ID", Short: "Read one guide, its declared documents and selected policies", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ProjectGuide(cmd.Context(), args[0], args[1])
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			v := result.Value
			return writeTaskContextFields(stdout, []contextField{
				{"Guide", v.Guide}, {"Documents", v.Documents}, {"Review policy", v.ReviewPolicy},
				{"Revision policy", v.RevisionPolicy}, {"Latest setup run", v.LatestSetupRunID},
				{"Latest compilation", v.LatestCompilationID},
			})
		},
	})
	guide.AddCommand(&cobra.Command{
		Use: "readiness PROJECT_ID GUIDE_ID", Short: "Dry-run activation: ready, or the unmet conditions it evaluates (writes nothing)", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.GuideActivationReadiness(cmd.Context(), args[0], args[1])
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			if _, err := fmt.Fprintf(stdout, "Ready: %t\n", result.Value.Ready); err != nil {
				return err
			}
			for _, c := range result.Value.Unmet {
				if _, err := fmt.Fprintf(stdout, "Unmet: %s %s: %s\n", safeText(c.Code), safeText(c.Reason), safeText(c.Message)); err != nil {
					return err
				}
				for _, m := range c.MissingCapabilities {
					if _, err := fmt.Fprintf(stdout, "Missing capability: %s %s %s\n",
						safeText(m.RequirementID), safeText(m.Stage), safeText(m.Title)); err != nil {
						return err
					}
				}
			}
			return nil
		},
	})
	var directory string
	document := &cobra.Command{
		Use: "document PROJECT_ID GUIDE_ID DOCUMENT_ID", Short: "Download one uploaded guide original, verified against its declared SHA-256", Args: cobra.ExactArgs(3),
		RunE: func(cmd *cobra.Command, args []string) error {
			if !api.ValidUUID(args[2]) {
				return errors.New("DOCUMENT_ID must be a UUID")
			}
			root, err := download.OpenRoot(directory)
			if err != nil {
				return err
			}
			defer root.Close()
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ProjectGuide(cmd.Context(), args[0], args[1])
			if err != nil {
				return err
			}
			var selected *api.ProjectGuideDocument
			for index := range result.Value.Documents {
				if api.SameUUID(result.Value.Documents[index].DocumentID, args[2]) {
					selected = &result.Value.Documents[index]
				}
			}
			if selected == nil {
				return &api.Failure{Code: "guide_document_not_found"}
			}
			if selected.IngestState != "uploaded" {
				return &api.Failure{Code: "guide_document_not_uploaded"}
			}
			name := api.TaskGuideDocument{DocumentID: selected.DocumentID, MediaType: selected.MediaType}.Filename()
			stage, err := root.Stage(name)
			if err != nil {
				return err
			}
			defer stage.Abort()
			if err := apiClient.DownloadProjectGuideDocument(cmd.Context(), args[0], args[1], *selected, stage); err != nil {
				return err
			}
			if err := stage.Seal(); err != nil {
				return err
			}
			if err := stage.Publish(); err != nil {
				return err
			}
			if *output == "json" {
				body, err := json.Marshal(map[string]any{"downloaded": name, "document": selected})
				if err != nil {
					return err
				}
				return writeSafeJSON(stdout, body)
			}
			_, err = fmt.Fprintf(stdout, "Downloaded: %s\n", safeText(name))
			return err
		},
	}
	document.Flags().StringVar(&directory, "download", "", "Required existing directory for the verified original (never overwrite)")
	guide.AddCommand(document)
}
