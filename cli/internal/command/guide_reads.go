package command

import (
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

// addGuideReads adds the Project Manager's read-only guide commands.
func addGuideReads(guide *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
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
			info, err := os.Lstat(directory)
			if directory == "" || err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
				return errors.New("--download must be an existing real directory")
			}
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
			root, err := os.OpenRoot(directory)
			if err != nil {
				return errors.New("cannot open download directory")
			}
			defer root.Close()
			name := api.TaskGuideDocument{DocumentID: selected.DocumentID, MediaType: selected.MediaType}.Filename()
			if err := publishVerifiedDownload(root, name, func(target io.Writer) error {
				return apiClient.DownloadProjectGuideDocument(cmd.Context(), args[0], args[1], *selected, target)
			}); err != nil {
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

// publishVerifiedDownload writes privately, then links the name only after
// write reports every byte verified; it never replaces an existing file.
func publishVerifiedDownload(root *os.Root, name string, write func(io.Writer) error) error {
	if _, err := root.Lstat(name); !os.IsNotExist(err) {
		return errors.New("download target already exists or is inaccessible")
	}
	temporary := ".workstream-guide-" + rand.Text()
	file, err := root.OpenFile(temporary, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return errors.New("cannot create private guide download")
	}
	defer root.Remove(temporary)
	defer file.Close()
	if err := write(file); err != nil {
		return err
	}
	if err := file.Sync(); err != nil {
		return errors.New("cannot persist guide download")
	}
	if err := file.Close(); err != nil {
		return errors.New("cannot close guide download")
	}
	if err := root.Link(temporary, name); err != nil {
		return errors.New("cannot publish guide download without overwrite")
	}
	return nil
}
