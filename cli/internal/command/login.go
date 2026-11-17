package command

import (
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/login"
	"github.com/spf13/cobra"
)

func addLoginCommands(root *cobra.Command, stdout, stderr io.Writer, getenv environment) {
	var issuerURL, apiURL string
	signIn := &cobra.Command{Use: "login", Short: "Sign in to Flow Identity using your browser", Args: cobra.NoArgs, RunE: func(cmd *cobra.Command, _ []string) error {
		store, err := login.DefaultStore()
		if err != nil {
			return commandError{"login_unavailable", err.Error()}
		}
		if err = login.NewClient().Login(cmd.Context(), store, issuerURL, apiURL, stderr, login.OpenBrowser); err != nil {
			return commandError{"login_failed", err.Error()}
		}
		return nil
	}}
	signIn.Flags().StringVar(&issuerURL, "issuer", login.DefaultIssuer, "Trusted Flow Identity issuer")
	signIn.Flags().StringVar(&apiURL, "api-url", login.DefaultAPI, "Workstream API origin bound to this login")
	root.AddCommand(signIn)
	root.AddCommand(&cobra.Command{Use: "logout", Short: "Remove saved login and close its refresh session", Args: cobra.NoArgs, RunE: func(cmd *cobra.Command, _ []string) error {
		store, err := login.DefaultStore()
		if err != nil {
			return commandError{"logout_failed", err.Error()}
		}
		if err = login.NewClient().Logout(cmd.Context(), store); err != nil {
			return commandError{"logout_failed", err.Error()}
		}
		fmt.Fprintln(stderr, "Signed out. Already-issued access tokens remain valid until expiry.")
		return nil
	}})
	auth := &cobra.Command{Use: "auth", Short: "Manage your Workstream API credential"}
	auth.AddCommand(&cobra.Command{Use: "token", Short: "Print your current API access token (keep this output private)", Args: cobra.NoArgs, RunE: func(cmd *cobra.Command, _ []string) error {
		store, err := login.DefaultStore()
		if err != nil {
			return commandError{"login_unavailable", err.Error()}
		}
		_, token, err := login.NewClient().Credential(cmd.Context(), store, getenv("WORKSTREAM_API_URL"))
		if err != nil {
			return commandError{"login_required", err.Error()}
		}
		_, err = fmt.Fprintln(stdout, token)
		return err
	}})
	root.AddCommand(auth)
}
