package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
)

func writePendingSubmission(w io.Writer, pending *api.PendingSubmissionOperation) error {
	if pending == nil {
		return nil
	}
	return writeTaskContextFields(w, []contextField{{"Pending submission operation", pending}})
}
