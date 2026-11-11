package command

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"unicode"
	"unicode/utf16"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

type environment func(string) string

type commandError struct {
	code    string
	message string
}

func (e commandError) Error() string { return e.message }

// Run owns the CLI's stable output and exit status. Cobra never prints raw
// arguments or transport errors, which might otherwise contain credentials.
func Run(args []string, stdout, stderr io.Writer, getenv environment, version string) int {
	var output string
	root := &cobra.Command{
		Use:           "workstream",
		Short:         "Work with the public Workstream API",
		SilenceUsage:  true,
		SilenceErrors: true,
		Version:       version,
	}
	root.SetOut(stdout)
	root.SetErr(stderr)
	root.SetArgs(args)
	root.SetFlagErrorFunc(func(_ *cobra.Command, _ error) error {
		return commandError{"invalid_arguments", "invalid flags; run workstream --help"}
	})
	root.PersistentFlags().StringVarP(&output, "output", "o", "text", "Output format: text or json")

	client := func() (*api.Client, error) {
		if output != "text" && output != "json" {
			return nil, commandError{"invalid_output", "--output must be text or json"}
		}
		value, err := api.New(getenv("WORKSTREAM_API_URL"), getenv("WORKSTREAM_TOKEN"))
		if err != nil {
			return nil, commandError{"invalid_configuration", err.Error()}
		}
		return value, nil
	}

	root.AddCommand(&cobra.Command{
		Use:   "whoami",
		Short: "Show the caller's canonical actor profile",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.Profile(cmd.Context())
			if err != nil {
				return err
			}
			return writeProfile(stdout, output, result)
		},
	})

	profile := &cobra.Command{Use: "profile", Short: "Caller-owned profile operations"}
	var displayName string
	var clearDisplayName bool
	update := &cobra.Command{
		Use:   "update",
		Short: "Set or clear your human display name",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			fields := api.ProfileUpdate{ClearDisplayName: clearDisplayName}
			if cmd.Flags().Changed("display-name") {
				fields.DisplayName = &displayName
			}
			if (fields.DisplayName != nil && clearDisplayName) ||
				(fields.DisplayName == nil && !clearDisplayName) {
				return commandError{"invalid_arguments", "select profile fields; do not set and clear the same field"}
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.UpdateProfile(cmd.Context(), fields)
			if err != nil {
				return err
			}
			return writeProfile(stdout, output, result)
		},
	}
	update.Flags().StringVar(&displayName, "display-name", "", "Set your display name")
	update.Flags().BoolVar(&clearDisplayName, "clear-display-name", false, "Clear your display name")
	profile.AddCommand(update)
	root.AddCommand(profile)
	addAdminInspection(root, client, &output, stdout)

	project := &cobra.Command{Use: "project", Short: "Public project operations"}
	addProjectCatalogue(project, client, &output, stdout)
	addTaskReads(project, client, &output, stdout)
	addTaskBatch(project, client, &output, stdout)
	addProjectCreate(project, client, &output, stdout)
	addProjectRoleMutations(project, client, &output, stdout)
	addContributionPolicyReads(project, client, &output, stdout)
	addManagerReads(project, client, &output, stdout)
	addManagerTaskEvidence(project, client, &output, stdout)
	addProjectPreparationReads(project, client, &output, stdout)
	addContributionEvidence(root, project, client, &output, stdout)
	addGuideCreate(project, client, &output, stdout)
	project.AddCommand(&cobra.Command{
		Use:   "show PROJECT_ID",
		Short: "Inspect the project fields your current authority permits",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.Project(cmd.Context(), args[0])
			if err != nil {
				return err
			}
			return writeProject(stdout, output, result)
		},
	})
	project.AddCommand(&cobra.Command{
		Use:   "access PROJECT_ID",
		Short: "Show your current authority for one project",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.AuthorizationContext(cmd.Context(), args[0])
			if err != nil {
				return err
			}
			if output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			p := result.Value
			if _, err := fmt.Fprintf(stdout,
				"Project: %s\nActor: %s\nStatus: %s\nAdmin roles: %s\nProject roles: %s\nEffective actions (%d):\n",
				safeText(p.ProjectID), safeText(p.ActorProfileID), safeText(p.Status), list(p.AdminRoles), list(p.ProjectRoles),
				len(p.EffectiveActionIDs)); err != nil {
				return err
			}
			for _, action := range p.EffectiveActionIDs {
				if _, err := fmt.Fprintf(stdout, "  %s\n", safeText(action)); err != nil {
					return err
				}
			}
			return nil
		},
	})
	root.AddCommand(project)
	addTaskAudit(root, client, &output, stdout)
	operations := &cobra.Command{Use: "operations", Short: "Explicit system Operator operations"}
	addCheckerOperations(operations, client, &output, stdout)
	addPostSubmitDeliveryOperations(operations, client, &output, stdout)
	addOperatorTasks(operations, client, &output, stdout)
	addArtifactOperator(operations, client, &output, stdout)
	root.AddCommand(operations)
	addContributorTasks(root, client, &output, stdout)
	addContributorReads(root, client, &output, stdout)
	addTUI(root, client, &output, stdout, getenv)

	err := root.ExecuteContext(context.Background())
	if err == nil {
		return 0
	}
	var failure *api.Failure
	var usage commandError
	switch {
	case errors.As(err, &failure):
		writeFailure(stderr, output, *failure)
		return 1
	case errors.As(err, &usage):
		writeFailure(stderr, output, api.Failure{Code: usage.code})
		if output != "json" {
			fmt.Fprintln(stderr, usage.message)
		}
		if usage.code == "file_io_error" {
			return 1
		}
		return 2
	default:
		writeFailure(stderr, output, api.Failure{Code: "invalid_arguments"})
		return 2
	}
}

func writeJSON(w io.Writer, raw json.RawMessage) error {
	_, err := fmt.Fprintln(w, string(bytes.TrimSpace(raw)))
	return err
}

func writeSafeJSON(w io.Writer, raw json.RawMessage) error {
	// Preserve JSON values while keeping literal controls, format marks and
	// Unicode line/paragraph separators out of terminals. JSON already
	// escapes C0 controls inside strings.
	var safe strings.Builder
	for _, r := range string(bytes.TrimSpace(raw)) {
		if r >= 0x7f && (unicode.IsControl(r) || unicode.Is(unicode.Cf, r) || r == '\u2028' || r == '\u2029') {
			if r <= 0xffff {
				fmt.Fprintf(&safe, "\\u%04x", r)
			} else {
				hi, lo := utf16.EncodeRune(r)
				fmt.Fprintf(&safe, "\\u%04x\\u%04x", hi, lo)
			}
		} else {
			safe.WriteRune(r)
		}
	}
	_, err := fmt.Fprintln(w, safe.String())
	return err
}

func writeProfile(w io.Writer, output string, result api.Result[api.Profile]) error {
	if output == "json" {
		return writeJSON(w, result.Raw)
	}
	p := result.Value
	_, err := fmt.Fprintf(w,
		"Actor: %s\nStatus: %s\nName: %s\nEmail: %s\nAdmin roles: %s\nProject grants: %s\n",
		safeText(p.ActorProfileID), safeText(p.Status), optional(p.DisplayName), optional(p.ContactEmail),
		list(p.AdminRoles), list(p.ProjectRoleGrants))
	return err
}

func writeFailure(w io.Writer, output string, f api.Failure) {
	if output == "json" {
		raw, err := json.Marshal(struct {
			Error api.Failure `json:"error"`
		}{Error: f})
		if err == nil {
			_ = writeSafeJSON(w, raw)
		}
		return
	}
	_, _ = fmt.Fprintln(w, "Error:", f.Error())
	if len(f.Details) != 0 {
		_, _ = fmt.Fprintln(w, "Intake findings:", safeText(string(f.Details)))
	}
}

func optional(value *string) string {
	if value == nil || *value == "" {
		return "—"
	}
	return safeText(*value)
}

func list(values []string) string {
	if len(values) == 0 {
		return "none"
	}
	safe := make([]string, len(values))
	for i, value := range values {
		safe[i] = safeText(value)
	}
	return strings.Join(safe, ", ")
}

func safeText(value string) string {
	var out strings.Builder
	for _, r := range value {
		if !unicode.IsPrint(r) || unicode.Is(unicode.Cf, r) {
			fmt.Fprintf(&out, "\\u%04X", r)
		} else {
			out.WriteRune(r)
		}
	}
	return out.String()
}
