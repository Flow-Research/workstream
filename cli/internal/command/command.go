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
			if output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			p := result.Value
			_, err = fmt.Fprintf(stdout,
				"Actor: %s\nStatus: %s\nName: %s\nEmail: %s\nAdmin roles: %s\nProject grants: %s\n",
				safeText(p.ActorProfileID), safeText(p.Status), optional(p.DisplayName), optional(p.ContactEmail),
				list(p.AdminRoles), list(p.ProjectRoleGrants))
			return err
		},
	})

	project := &cobra.Command{Use: "project", Short: "Project-scoped public operations"}
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

func writeFailure(w io.Writer, output string, f api.Failure) {
	if output == "json" {
		_ = json.NewEncoder(w).Encode(struct {
			Error api.Failure `json:"error"`
		}{Error: f})
		return
	}
	_, _ = fmt.Fprintln(w, "Error:", f.Error())
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
