"""Evidence oracle for the public guide drill."""


def verify_source_commitment(source, attempt, *, examples, examples_hash, source_hash,
                             source_id, original_sha256s, accesses, manager_authored):
    """Check persisted input lineage and original-read custody, never generated prose."""
    if (source["task_examples"] != examples
            or source["task_examples_hash"] != examples_hash
            or source["manifest_json"]["task_examples_hash"] != examples_hash
            or source["manifest_json"]["task_examples_count"] != len(examples)
            or source["bundle_hash"] != source_hash):
        raise AssertionError("guide/example/source commitment differs")
    if (attempt["status"] != "compilation_persisted"
            or attempt["source_snapshot_hash"] != source_hash
            or str(attempt["source_snapshot_id"]) != source_id
            or attempt["canonical_input_hash"] != attempt["compiled_input_hash"]):
        raise AssertionError("worker input lineage differs")
    if manager_authored and (
        attempt["runtime_key"] != "manager_authored" or attempt["model_provider"] != "none"
        or attempt["setup_model_slots"] != 0
    ):
        raise AssertionError("manager-authored guide used model assistance")
    read_digests = {
        access["sha256"]
        for access in accesses
        if str(access["source_snapshot_id"]) == source_id
        and access["manifest_sha256"] == attempt["guide_material_hash"]
        and access["access_method"] == "trusted_parser" and access["operation"] == "read"
    }
    if read_digests != set(original_sha256s):
        raise AssertionError("worker original-read custody is missing")
