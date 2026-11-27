package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addPostSubmitDeliveryOperations(operations *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	delivery := &cobra.Command{Use: "delivery", Short: "Observe and explicitly reconcile uncertain post-submit deliveries"}
	var limit int
	var cursor string
	list := &cobra.Command{
		Use: "list PROJECT_ID", Short: "List one project page of exact UNKNOWN deliveries; observation is not write authority", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.PostSubmitDeliveries(cmd.Context(), args[0], limit, cursor)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeSafeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Post-submit delivery sources (not reconciliation authority)", result.Raw}})
		},
	}
	list.Flags().IntVar(&limit, "limit", 50, "Page size, 1..100")
	list.Flags().StringVar(&cursor, "cursor", "", "Opaque continuation from this exact project page")
	delivery.AddCommand(list)

	var reason, key string
	var abandonUnknown bool
	reconcile := &cobra.Command{
		Use: "reconcile PROJECT_ID EVENT_ID", Short: "Request one governed reconciliation child for an exact UNKNOWN event", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			if !cmd.Flags().Changed("reason") || !api.ValidPostSubmitDeliveryReason(reason) || key == "" {
				return commandError{"invalid_arguments", "--reason (1..500 characters, no surrounding whitespace or ASCII controls) and --idempotency-key are required"}
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ReconcilePostSubmitDelivery(cmd.Context(), args[0], args[1], reason, key, abandonUnknown)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeSafeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Post-submit delivery reconciliation receipt (not acceptance)", result.Raw}})
		},
	}
	reconcile.Flags().BoolVar(&abandonUnknown, "abandon-unknown", false, "Supersede the expired unresolved attempt and request another evaluation")
	reconcile.Flags().StringVar(&reason, "reason", "", "Required operator explanation, 1..500 characters")
	reconcile.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID; reuse unchanged only for manual replay")
	delivery.AddCommand(reconcile)
	operations.AddCommand(delivery)
}
