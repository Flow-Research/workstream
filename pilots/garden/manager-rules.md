{
  "format": "workstream.project_guide_rules.v1",
  "status": "draft_ready",
  "findings": [],
  "submission_artifact_policy": {
    "packaging": "zip",
    "maximum_file_size_bytes": 65536,
    "maximum_package_size_bytes": 65536,
    "maximum_archive_size_bytes": 131072,
    "maximum_archive_entries": 1,
    "allowed_storage_schemes": [
      "artifact"
    ],
    "required_artifacts": [
      "proof.json"
    ],
    "forbidden_artifacts": [],
    "required_evidence": [],
    "attestation_terms": []
  },
  "requirements": [
    {
      "suggestion_id": "garden_proof_structure",
      "statement": "The submitted proof is a bounded, well-formed claim about a Garden pull request and CI run.",
      "stage": "pre_submit",
      "classification_rationale": "File structure and fixed claim fields can be inspected without network access before Submission creation.",
      "check_specification": {
        "evaluation_method": "Parse a bounded UTF-8 proof.json object and validate its required claim format.",
        "inputs": [
          {
            "input_id": "proof",
            "kind": "relative_file",
            "relative_path": "proof.json",
            "purpose": "Supplies the contributor's claims."
          }
        ],
        "check_steps": [
          "Require a root regular proof.json file at most 65536 bytes.",
          "Validate the documented proof schema, full commit SHA and canonical Garden PR and Actions run URLs.",
          "Require successful CI and merged assertions as claims only; do not verify GitHub facts during PRE."
        ],
        "pass_conditions": [
          "All required claim fields have the documented format and no structural error is found."
        ],
        "failure_findings": [
          {
            "code": "harnessy.proof.invalid_json",
            "level": "error",
            "condition": "The root proof is not a valid JSON object.",
            "message": "Provide a UTF-8 JSON object in proof.json."
          },
          {
            "code": "harnessy.proof.missing",
            "level": "error",
            "condition": "The root proof file is absent.",
            "message": "The root proof file is absent. Correct the claim before uploading."
          },
          {
            "code": "harnessy.proof.too_large",
            "level": "error",
            "condition": "The proof exceeds the byte limit.",
            "message": "The proof exceeds the byte limit. Correct the claim before uploading."
          },
          {
            "code": "harnessy.proof.schema",
            "level": "error",
            "condition": "The proof schema is unsupported.",
            "message": "The proof schema is unsupported. Correct the claim before uploading."
          },
          {
            "code": "harnessy.proof.commit_sha",
            "level": "error",
            "condition": "The landed commit SHA has an invalid format.",
            "message": "The landed commit SHA has an invalid format. Correct the claim before uploading."
          },
          {
            "code": "harnessy.proof.ci_conclusion",
            "level": "error",
            "condition": "The claimed CI conclusion is not success.",
            "message": "The claimed CI conclusion is not success. Correct the claim before uploading."
          },
          {
            "code": "harnessy.proof.merged",
            "level": "error",
            "condition": "The merged claim is not true.",
            "message": "The merged claim is not true. Correct the claim before uploading."
          },
          {
            "code": "garden.proof.pr_url",
            "level": "error",
            "condition": "The PR URL does not identify a canonical Garden pull request.",
            "message": "The PR URL does not identify a canonical Garden pull request. Correct the claim before uploading."
          },
          {
            "code": "garden.proof.ci_run_url",
            "level": "error",
            "condition": "The CI URL does not identify a canonical Garden Actions run.",
            "message": "The CI URL does not identify a canonical Garden Actions run. Correct the claim before uploading."
          }
        ],
        "positive_tests": [
          "A well-formed bounded Garden proof reaches Submission intake even though its claims remain unverified until POST."
        ],
        "negative_tests": [
          {
            "name": "malformed_json",
            "scenario": "The root proof is not valid JSON.",
            "expected_verdict": "failed",
            "expected_finding_codes": [
              "harnessy.proof.invalid_json"
            ]
          }
        ],
        "implementation_needs": [
          "A bounded offline project PRE image; no model or forge access."
        ],
        "inability_to_evaluate": [
          {
            "code": "proof_io_unavailable",
            "condition": "The supplied verified material cannot be read because execution infrastructure failed."
          }
        ]
      },
      "evidence_refs": [
        {
          "document": "sha256:e637df3367b4b47510c9c43ef8ba60d40e44db31a45c34bc71017f6b3a35e578",
          "section": "Submit one small ZIP"
        }
      ]
    },
    {
      "suggestion_id": "garden_task_proof",
      "statement": "Independent GitHub facts substantiate the submitted merged and CI-passing Garden change for this exact Workstream task under the explicit test approval count.",
      "stage": "post_submit",
      "classification_rationale": "Verifying remote PR, immutable commit, CI, task association and any configured reviews belongs after immutable Submission creation.",
      "check_specification": {
        "evaluation_method": "Compare submitted claims to scoped GitHub facts and the trusted task identity.",
        "inputs": [
          {
            "input_id": "proof",
            "kind": "relative_file",
            "relative_path": "proof.json",
            "purpose": "Supplies the claims to verify."
          },
          {
            "input_id": "forge_facts",
            "kind": "forge_facts",
            "purpose": "Supplies independently retrieved PR, commit, required CI and any review facts."
          },
          {
            "input_id": "task",
            "kind": "task_context",
            "purpose": "Supplies Workstream's exact task UUID, not a submitted claim."
          }
        ],
        "check_steps": [
          "Require the claimed PR to be merged into Garden dev at the claimed landed commit.",
          "Require successful trusted required checks. For this test, the PM explicitly selects required_independent_approvals=0 in the Garden POST attachment; no independent GitHub review is required. Omission requires one, and positive counts require the corresponding eligible current-head approvals.",
          "Require exactly one canonical Workstream-Task trailer on the immutable PR head commit and compare it with the trusted task UUID.",
          "Reject mismatched URLs, repository, commit, CI or task association and preserve actionable findings."
        ],
        "pass_conditions": [
          "All required independent comparisons pass for the exact task and submitted claims."
        ],
        "failure_findings": [
          {
            "code": "garden.proof.task_mismatch",
            "level": "error",
            "condition": "The PR head trailer identifies another Workstream task.",
            "message": "Use a PR whose PR head identifies this claimed task."
          },
          {
            "code": "garden.proof.task_trailer",
            "level": "error",
            "condition": "The PR head lacks one valid canonical task trailer.",
            "message": "Add one canonical task trailer before final checks and any required review."
          },
          {
            "code": "harnessy.proof.forge.change_url",
            "level": "error",
            "condition": "The claimed PR URL differs from the verified change.",
            "message": "The claimed PR URL differs from the verified change. Resolve the finding before resubmission."
          },
          {
            "code": "harnessy.proof.forge.ci_run",
            "level": "error",
            "condition": "The claimed CI run does not match a required successful check.",
            "message": "The claimed CI run does not match a required successful check. Resolve the finding before resubmission."
          },
          {
            "code": "harnessy.proof.forge.unbound_required_check",
            "level": "error",
            "condition": "A required check has no trusted producer binding.",
            "message": "A required check has no trusted producer binding. Resolve the finding before resubmission."
          },
          {
            "code": "harnessy.proof.forge.producer_mismatch",
            "level": "error",
            "condition": "A check producer differs from the required trusted producer.",
            "message": "A check producer differs from the required trusted producer. Resolve the finding before resubmission."
          },
          {
            "code": "harnessy.proof.forge.protected_path_changed",
            "level": "error",
            "condition": "The change touches a path prohibited by the locked checker configuration.",
            "message": "The change touches a path prohibited by the locked checker configuration. Resolve the finding before resubmission."
          },
          {
            "code": "harnessy.proof.forge.independent_approval_missing",
            "level": "error",
            "condition": "A positive configured independent approval count is not met by eligible human approvals on the current head.",
            "message": "Obtain the eligible current-head approvals required by the positive configured count. This finding does not apply when the count is explicitly zero."
          },
          {
            "code": "harnessy.proof.forge.repository",
            "level": "error",
            "condition": "The change belongs to another repository.",
            "message": "The change belongs to another repository. Resolve the finding before resubmission."
          },
          {
            "code": "harnessy.proof.forge.base_branch",
            "level": "error",
            "condition": "The PR targets another base branch.",
            "message": "The PR targets another base branch. Resolve the finding before resubmission."
          },
          {
            "code": "harnessy.proof.forge.merged",
            "level": "error",
            "condition": "The forge reports that the PR is not merged.",
            "message": "The forge reports that the PR is not merged. Resolve the finding before resubmission."
          },
          {
            "code": "harnessy.proof.forge.landed_commit_sha",
            "level": "error",
            "condition": "The claimed landed commit differs from the verified merge result.",
            "message": "The claimed landed commit differs from the verified merge result. Resolve the finding before resubmission."
          },
          {
            "code": "harnessy.proof.forge.required_check",
            "level": "error",
            "condition": "A required check has not succeeded.",
            "message": "A required check has not succeeded. Resolve the finding before resubmission."
          }
        ],
        "positive_tests": [
          "A merged Garden PR with trusted passing checks, the exact task trailer and no reviews passes when required_independent_approvals is explicitly zero.",
          "The same no-review facts fail the independent-approval requirement when the setting is omitted or positive."
        ],
        "negative_tests": [
          {
            "name": "foreign_task",
            "scenario": "Every required PR, merge and CI condition passes under the explicit zero-approval test configuration, but the immutable head trailer names a different Workstream task.",
            "expected_verdict": "failed",
            "expected_finding_codes": [
              "garden.proof.task_mismatch"
            ]
          }
        ],
        "implementation_needs": [
          "A project POST image with bounded forge-facts capability and no credentials or unrestricted sandbox network."
        ],
        "inability_to_evaluate": [
          {
            "code": "forge_unavailable",
            "condition": "Authorized forge retrieval cannot establish consistent facts due to provider, permission or infrastructure failure."
          }
        ]
      },
      "evidence_refs": [
        {
          "document": "sha256:e637df3367b4b47510c9c43ef8ba60d40e44db31a45c34bc71017f6b3a35e578",
          "section": "What PRE and POST mean"
        }
      ]
    }
  ],
  "setup_notes": [
    "These are PM-authored requirements, not model output or evidence of a successful drill.",
    "The PM must separately approve PRE and POST image bindings and lifecycle policy. No image identity is selected by this document.",
    "This replacement guide uses an explicit Garden POST approval count of zero for the test; omission still requires one. Workstream ReviewPolicy and separate PM approvals remain unchanged."
  ]
}
