package api

// PendingSubmissionOperation identifies accepted or in-flight work separately from retained submissions.
type PendingSubmissionOperation struct {
	OperationID     string `json:"operation_id"`
	ProcessingStage string `json:"processing_stage"`
}

func validPendingSubmission(value *PendingSubmissionOperation) bool {
	return value == nil || (validUUID(value.OperationID) && oneOf(value.ProcessingStage,
		"receiving", "pre_checking", "finalization_pending", "operationally_stalled"))
}
