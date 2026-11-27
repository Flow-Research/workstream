"""Observe real submission custody through the public Operator CLI only."""


def inspect_submission_custody(client, tokens, project_id, task_id, submission_id):
    token = tokens["operator"]

    def read(*arguments):
        return client.call(token, "operations", "artifact", *arguments)

    bindings = read("bindings", "submission", submission_id)
    if bindings["next_cursor"] is not None or len(bindings["items"]) != 1:
        raise AssertionError("expected one immutable submission bundle binding")
    binding = bindings["items"][0]
    for field, expected in {
        "project_id": project_id,
        "resource_type": "submission",
        "resource_id": submission_id,
        "logical_role": "submission_bundle_original",
    }.items():
        if binding[field] != expected:
            raise AssertionError("artifact binding differs from submitted work")
    replicas = read("replicas", binding["content_id"])
    if replicas["next_cursor"] is not None or len(replicas["items"]) != 1:
        raise AssertionError("expected one replica in the isolated provider")
    replica = replicas["items"][0]
    if replica["content_id"] != binding["content_id"]:
        raise AssertionError("replica substituted submission content")
    receipts = read("receipts", replica["id"])
    # This route excludes nulls, including an exhausted page's next_cursor.
    if receipts.get("next_cursor") is not None:
        raise AssertionError("isolated custody receipts unexpectedly exceed one page")
    if (
        replica["verification_state"] != "verified"
        or replica["availability_state"] != "available"
        or replica["integrity_state"] != "valid"
    ):
        raise AssertionError("accepted source replica lacks retained verified custody")
    # Source-first T5 retains the sealed source itself. It does not synthesize
    # the retired put/verification job lineage for the same provider version.
    if any(item["receipt_type"] == "verification" for item in receipts["items"]):
        raise AssertionError("source-first binding invented old verifier lineage")
    read("audit-events", "artifact_binding", binding["id"])
    read("admission-usage", project_id, "--task-id", task_id)
    read("readiness")
    denied = client.call(
        tokens["bob"],
        "operations",
        "artifact",
        "bindings",
        "submission",
        submission_id,
        expected_exit=1,
    )
    if denied["error"].get("status") != 404:
        raise AssertionError("non-Operator can inspect submission custody")
    # No retry is appropriate for this successful upload. The independent
    # signed API test uses a genuinely exhausted job to prove that mutation.
