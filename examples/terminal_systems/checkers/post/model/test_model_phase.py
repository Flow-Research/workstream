"""Known-invalid corrections keep evidence, strict validation and paid-call bounds."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest

from assessment import AssessmentError
from model_phase import run_model_phase
from model_transport import CompletedModelCall, ModelCallUnavailable, ModelSessionError
import test_trial_plan as plan_tests
from trial_plan import (
    MAXIMUM_MODEL_PROMPT_BYTES,
    MAXIMUM_PROCEDURES,
    TrialPlanError,
    build_plan_prompt,
    validate_plan_proposal,
)


class Session:
    def __init__(self, outputs, *, exhausted_at=None):
        self.outputs = iter(outputs)
        self.calls = []
        self.exhausted_at = exhausted_at

    def call(self, prompt, *, required_receipt_handles=()):
        self.calls.append((prompt, required_receipt_handles))
        value = next(self.outputs)
        if isinstance(value, Exception):
            raise value
        return CompletedModelCall(
            len(self.calls) - 1,
            value,
            "sha256:" + "3" * 64,
            len(self.calls) == self.exhausted_at,
        )


class ModelPhaseTests(unittest.TestCase):
    def setUp(self):
        self.case = plan_tests.TrialPlanTests()
        self.case.setUp()
        self.addCleanup(self.case.tearDown)
        self.value = self.case.proposal()
        self.valid = json.dumps(self.value)
        self.prompt = build_plan_prompt(
            self.case.metadata, self.case.material_digest, self.case.evidence
        )

    def validate(self, raw):
        return validate_plan_proposal(
            raw, self.case.material_digest, self.case.evidence
        )

    def bad_outputs(self):
        # Same raw defects observed in the retained live response, using only
        # this public controlled fixture's commands and synthetic identities.
        value = deepcopy(self.value)
        del value["schema_version"]
        value["procedures"][1]["source_quote"] = "absent exact source line"
        item = value["procedures"][3]
        member = json.dumps(item)
        duplicate = (
            member[:-1]
            + "".join(
                ", " + json.dumps(k) + ": " + json.dumps(item[k])
                for k in ("evidence_id", "procedure_id", "purpose", "source_quote")
            )
            + "}"
        )
        raw = json.dumps(value).replace(member, duplicate, 1)
        omitted = deepcopy(self.value)
        del omitted["schema_version"]
        bad_citation = deepcopy(self.value)
        bad_citation["procedures"][1]["source_quote"] = "absent exact source line"
        original_item = self.value["procedures"][3]
        original_member = json.dumps(original_item)
        duplicate_only = json.dumps(self.value).replace(
            original_member,
            original_member[:-1]
            + ", "
            + json.dumps("purpose")
            + ": "
            + json.dumps(original_item["purpose"])
            + "}",
            1,
        )
        return duplicate_only, raw, json.dumps(omitted), json.dumps(bad_citation)

    def test_raw_duplicate_omission_and_bad_citation_correct_only_through_same_validator(
        self,
    ):
        for raw in self.bad_outputs():
            with self.subTest(raw_length=len(raw)):
                with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
                    self.validate(raw)
                session = Session([raw, self.valid])
                proposal, completed = run_model_phase(
                    session, self.prompt, self.validate
                )
                self.assertTrue(proposal.coverage_complete)
                self.assertEqual(completed.call_index, 1)
                self.assertEqual(len(session.calls), 2)
                correction = json.loads(session.calls[1][0])
                self.assertEqual(correction["original_prompt"], self.prompt)
                self.assertEqual(correction["untrusted_prior_output"], raw)
                self.assertEqual(correction["validation_error"], "invalid_output")
                self.assertNotIn("accepted_candidate", correction)

    def test_quoted_recovery_lines_require_a_fresh_integer_output(self):
        # The hosted assessment returned numbered source text for integer spans.
        for field in ("start_line", "end_line"):
            with self.subTest(field=field):
                invalid_value = deepcopy(self.value)
                invalid_value["recovery_applicability"][field] = "1: source text"
                invalid = json.dumps(invalid_value)
                with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
                    self.validate(invalid)
                session = Session([invalid, self.valid])
                proposal, _ = run_model_phase(session, self.prompt, self.validate)
                self.assertTrue(proposal.coverage_complete)
                correction = json.loads(session.calls[1][0])
                self.assertIn(
                    "must be JSON integers", correction["correction_instruction"]
                )
                self.assertEqual(correction["untrusted_prior_output"], invalid)
                self.assertEqual(correction["original_prompt"], self.prompt)
                self.assertEqual(len(session.calls), 2)
                with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
                    run_model_phase(
                        Session([invalid, invalid]), self.prompt, self.validate
                    )

    def test_citation_correction_identifies_the_offending_procedure(self):
        # A closing fence cannot substitute for the source window containing
        # the command. This public fixture preserves bounded correction proof.
        lines = plan_tests.AUTHOR_NOTES.splitlines()
        notes = (
            "\n".join(
                [lines[0], "```sh", "sh solution/incomplete.sh", "```", *lines[2:]]
            )
            + "\n"
        )
        (self.case.root / "AUTHOR_NOTES.md").write_text(notes, encoding="utf-8")
        self.case.material_digest, self.case.evidence = plan_tests.collect_plan_sources(
            self.case.root
        )
        value = self.case.proposal()
        for item, line in zip(value["procedures"][1:], lines[1:], strict=True):
            item["source_quote"] = (
                item["command_text"] if item["purpose"] == "incomplete_repair" else line
            )
        valid = json.dumps(value)
        self.assertTrue(self.validate(valid).coverage_complete)
        value["procedures"][1]["source_quote"] = "```"
        invalid = json.dumps(value)
        prompt = build_plan_prompt(
            self.case.metadata, self.case.material_digest, self.case.evidence
        )
        expected = {
            "reason": "source_quote_or_command_text_not_in_unique_source_lines",
            "procedure_indices": [1],
        }

        class CitationAwareSession(Session):
            def call(self, prompt, *, required_receipt_handles=()):
                if self.calls:
                    correction = json.loads(prompt)
                    feedback = correction.get("validation_feedback")
                    zero_based = (
                        "procedure_indices lists every zero-based position"
                        in correction["correction_instruction"]
                    )
                    self.outputs = iter(
                        [valid if feedback == expected and zero_based else invalid]
                    )
                return super().call(
                    prompt, required_receipt_handles=required_receipt_handles
                )

        session = CitationAwareSession([invalid])
        proposal, completed = run_model_phase(session, prompt, self.validate)
        self.assertTrue(proposal.coverage_complete)
        self.assertEqual(completed.call_index, 1)
        self.assertEqual(len(session.calls), 2)
        correction = json.loads(session.calls[1][0])
        self.assertEqual(correction["validation_error"], "invalid_output")
        self.assertEqual(correction["validation_feedback"], expected)
        self.assertIn(
            "validation_feedback.procedure_indices lists every zero-based position with "
            "a citation failure in the prior procedures array.",
            correction["correction_instruction"],
        )
        self.assertEqual(correction["original_prompt"], prompt)
        self.assertEqual(correction["untrusted_prior_output"], invalid)
        self.assertNotIn("expected_line", correction)

    def test_all_wrapped_quote_failures_are_corrected_in_one_full_response(self):
        value = deepcopy(self.value)
        notes = ["# Reproduction"]
        for index, item in enumerate(value["procedures"][1:], start=1):
            if index <= 3:
                notes.extend(
                    [
                        "Use this documented",
                        "procedure without changing the task.",
                        "```sh",
                        item["command_text"],
                        "```",
                    ]
                )
                item["source_quote"] = item["command_text"]
            else:
                notes.append(item["source_quote"])
        (self.case.root / "AUTHOR_NOTES.md").write_text("\n".join(notes) + "\n")
        self.case.material_digest, self.case.evidence = plan_tests.collect_plan_sources(
            self.case.root
        )
        value["material_digest"] = self.case.material_digest
        valid = json.dumps(value)
        self.assertTrue(self.validate(valid).coverage_complete)
        for item in value["procedures"][1:4]:
            item["source_quote"] = (
                "Use this documented procedure without changing the task.\n"
                "```sh\n" + item["command_text"] + "\n```"
            )
        invalid = json.dumps(value)
        with self.assertRaises(TrialPlanError) as caught:
            self.validate(invalid)
        self.assertEqual(caught.exception.procedure_indices, (1, 2, 3))
        # Reproduces the retained one-correction failure: fixing only the first
        # reported quote leaves two independent citation failures.
        first_only = deepcopy(value)
        first_only["procedures"][1]["source_quote"] = first_only["procedures"][1][
            "command_text"
        ]
        with self.assertRaises(TrialPlanError) as caught:
            self.validate(json.dumps(first_only))
        self.assertEqual(caught.exception.procedure_indices, (2, 3))
        expected = {
            "reason": "source_quote_or_command_text_not_in_unique_source_lines",
            "procedure_indices": [1, 2, 3],
        }

        class CitationAwareSession(Session):
            def call(self, prompt, *, required_receipt_handles=()):
                if self.calls:
                    correction = json.loads(prompt)
                    self.outputs = iter(
                        [
                            valid
                            if correction.get("validation_feedback") == expected
                            and "unique complete command line"
                            in correction["correction_instruction"]
                            else invalid
                        ]
                    )
                return super().call(
                    prompt, required_receipt_handles=required_receipt_handles
                )

        prompt = build_plan_prompt(
            self.case.metadata, self.case.material_digest, self.case.evidence
        )
        session = CitationAwareSession([invalid])
        proposal, completed = run_model_phase(session, prompt, self.validate)
        self.assertEqual(completed.call_index, 1)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(proposal, self.validate(valid))
        correction = json.loads(session.calls[1][0])
        self.assertEqual(correction["validation_feedback"], expected)
        self.assertEqual(correction["untrusted_prior_output"], invalid)
        self.assertEqual(correction["original_prompt"], prompt)
        runtime = plan_tests.build_runtime_trial_plan(
            self.case.metadata, proposal, plan_tests.TrialPlanLimits(100, 16, 32)
        )
        self.assertIsNotNone(runtime)
        self.assertEqual(
            len(
                [
                    step
                    for step in runtime["steps"]
                    if step["slot_kind"].startswith("reference_verify_")
                ]
            ),
            3,
        )

    def test_missing_schema_and_multiple_wrapped_quotes_share_one_correction(self):
        # Synthetic version of the hosted failure: schema omission previously
        # hid both independently diagnosable quotes from the only correction.
        value = deepcopy(self.value)
        notes = ["# Reproduction"]
        for index, item in enumerate(value["procedures"][1:], start=1):
            if index <= 2:
                notes.extend(
                    ["Use this documented", "procedure.", item["command_text"]]
                )
                item["source_quote"] = item["command_text"]
            else:
                notes.append(item["source_quote"])
        (self.case.root / "AUTHOR_NOTES.md").write_text("\n".join(notes) + "\n")
        self.case.material_digest, self.case.evidence = plan_tests.collect_plan_sources(
            self.case.root
        )
        value["material_digest"] = self.case.material_digest
        valid = json.dumps(value)
        for item in value["procedures"][1:3]:
            item["source_quote"] = (
                "Use this documented procedure.\n" + item["command_text"]
            )
        schema_only = json.dumps(value)
        del value["schema_version"]
        invalid = json.dumps(value)
        with self.assertRaises(TrialPlanError) as caught:
            self.validate(invalid)
        self.assertEqual(caught.exception.procedure_indices, (1, 2))
        expected = {
            "reason": "source_quote_or_command_text_not_in_unique_source_lines",
            "procedure_indices": [1, 2],
        }

        class CitationAwareSession(Session):
            def call(self, prompt, *, required_receipt_handles=()):
                if self.calls:
                    correction = json.loads(prompt)
                    self.outputs = iter(
                        [
                            valid
                            if correction.get("validation_feedback") == expected
                            else schema_only
                        ]
                    )
                return super().call(
                    prompt, required_receipt_handles=required_receipt_handles
                )

        prompt = build_plan_prompt(
            self.case.metadata, self.case.material_digest, self.case.evidence
        )
        session = CitationAwareSession([invalid])
        proposal, completed = run_model_phase(session, prompt, self.validate)
        self.assertEqual(proposal, self.validate(valid))
        self.assertEqual(completed.call_index, 1)
        self.assertEqual(len(session.calls), 2)
        correction = json.loads(session.calls[1][0])
        self.assertEqual(correction["validation_feedback"], expected)
        self.assertEqual(correction["original_prompt"], prompt)
        self.assertEqual(correction["untrusted_prior_output"], invalid)
        # Feedback is diagnostic, never authority to accept a partial repair.
        session = Session([invalid, schema_only])
        with self.assertRaises(TrialPlanError) as caught:
            run_model_phase(session, prompt, self.validate)
        self.assertEqual(caught.exception.procedure_indices, (1, 2))
        self.assertEqual(len(session.calls), 2)

    def test_fenced_command_is_resolved_without_model_line_arithmetic(self):
        lines = plan_tests.AUTHOR_NOTES.splitlines()
        notes = (
            "\n".join(
                [
                    *(f"Context {number}" for number in range(100)),
                    "```sh",
                    "sh solution/incomplete.sh",
                    "```",
                    *lines[2:],
                ]
            )
            + "\n"
        )
        (self.case.root / "AUTHOR_NOTES.md").write_text(notes, encoding="utf-8")
        self.case.material_digest, self.case.evidence = plan_tests.collect_plan_sources(
            self.case.root
        )
        value = self.case.proposal()
        for item, line in zip(value["procedures"][1:], lines[1:], strict=True):
            item["source_quote"] = (
                item["command_text"] if item["purpose"] == "incomplete_repair" else line
            )
        prompt = build_plan_prompt(
            self.case.metadata, self.case.material_digest, self.case.evidence
        )
        session = Session([json.dumps(value)])
        proposal, _ = run_model_phase(session, prompt, self.validate)
        self.assertEqual(len(session.calls), 1)
        incomplete = proposal.procedures[1]
        self.assertEqual((incomplete["start_line"], incomplete["end_line"]), (102, 102))
        # The old response citing closing fence 103 remains invalid. This new
        # contract neither accepts nor rewrites the retained provider output.
        obsolete = deepcopy(value)
        for item, normalized in zip(
            obsolete["procedures"], proposal.procedures, strict=True
        ):
            del item["source_quote"]
            item.update(
                start_line=normalized["start_line"], end_line=normalized["end_line"]
            )
        obsolete["procedures"][1].update(start_line=103, end_line=103)
        session = Session([json.dumps(obsolete), json.dumps(obsolete)])
        with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
            run_model_phase(session, prompt, self.validate)
        self.assertEqual(len(session.calls), 2)

    def test_correction_feedback_copies_only_bounded_typed_procedure_indices(self):
        cases = (
            None,
            True,
            1,
            "source text",
            {},
            [],
            (),
            (True,),
            (-1,),
            (MAXIMUM_PROCEDURES,),
            (1.0,),
            ("source text",),
            ({},),
            (1, 1),
            (2, 1),
            tuple(range(MAXIMUM_PROCEDURES + 1)),
            (1,),
            (1, 2, 3),
            tuple(range(MAXIMUM_PROCEDURES)),
        )
        for indices in cases:
            with self.subTest(indices=indices):
                error = TrialPlanError("invalid_output", procedure_indices=indices)
                error.private_detail = "exception attributes must not be serialized"
                session = Session(["invalid", "valid"])

                def validate(raw):
                    if raw == "invalid":
                        raise error
                    return raw

                value, _ = run_model_phase(session, self.prompt, validate)
                self.assertEqual(value, "valid")
                self.assertEqual(len(session.calls), 2)
                correction = json.loads(session.calls[1][0])
                if (
                    type(indices) is tuple
                    and all(type(index) is int for index in indices)
                    and indices in ((1,), (1, 2, 3), tuple(range(MAXIMUM_PROCEDURES)))
                ):
                    self.assertEqual(
                        correction["validation_feedback"],
                        {
                            "reason": "source_quote_or_command_text_not_in_unique_source_lines",
                            "procedure_indices": list(indices),
                        },
                    )
                else:
                    self.assertNotIn("validation_feedback", correction)
                self.assertNotIn(error.private_detail, session.calls[1][0])

    def test_second_invalid_output_is_terminal_with_no_third_call(self):
        raw = self.bad_outputs()[0]
        session = Session([raw, raw, self.valid])
        with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
            run_model_phase(session, self.prompt, self.validate)
        self.assertEqual(len(session.calls), 2)

    def test_provider_unknown_or_transport_failure_never_creates_another_effect(self):
        for failure in (
            ModelCallUnavailable("model_provider_pending"),
            ModelSessionError("implementation_unavailable"),
        ):
            for values, expected_calls in (
                ([failure], 1),
                ([self.bad_outputs()[0], failure], 2),
            ):
                session = Session(values)
                with self.assertRaises(type(failure)):
                    run_model_phase(session, self.prompt, self.validate)
                self.assertEqual(len(session.calls), expected_calls)

    def test_only_typed_exact_invalid_output_is_correctable(self):
        for error in (
            ValueError("invalid_output"),
            TrialPlanError("material_unavailable"),
            AssessmentError("capacity_exceeded"),
        ):
            session = Session([self.valid])

            def invalid(_):
                raise error

            with self.assertRaises(type(error)):
                run_model_phase(session, self.prompt, invalid)
            self.assertEqual(len(session.calls), 1)

    def test_session_exhaustion_blocks_correction_and_latest_completed_is_returned(
        self,
    ):
        session = Session([self.bad_outputs()[0], self.valid], exhausted_at=1)
        with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
            run_model_phase(session, self.prompt, self.validate)
        self.assertEqual(len(session.calls), 1)
        session = Session([self.bad_outputs()[0], self.valid], exhausted_at=2)
        _, completed = run_model_phase(session, self.prompt, self.validate)
        self.assertTrue(completed.session_exhausted)

    def test_full_correction_bound_fails_without_truncation_or_extra_call(self):
        session = Session([self.bad_outputs()[0]])
        prompt = "x" * (MAXIMUM_MODEL_PROMPT_BYTES - 1)
        with self.assertRaisesRegex(AssessmentError, "capacity_exceeded"):
            run_model_phase(session, prompt, self.validate)
        self.assertEqual(len(session.calls), 1)
        session = Session([])
        with self.assertRaisesRegex(AssessmentError, "capacity_exceeded"):
            run_model_phase(
                session, "x" * (MAXIMUM_MODEL_PROMPT_BYTES + 1), self.validate
            )
        self.assertEqual(session.calls, [])

    def test_exact_assessment_receipt_handles_survive_correction(self):
        handles = ("trial_receipt_" + "b" * 32,)
        session = Session(["bad", "valid"])

        def validate(raw):
            if raw == "bad":
                raise AssessmentError("invalid_output")
            return ["valid-work-finding"]

        findings, _ = run_model_phase(
            session, self.prompt, validate, required_receipt_handles=handles
        )
        self.assertEqual(findings, ["valid-work-finding"])
        self.assertEqual([h for _, h in session.calls], [handles, handles])

    def test_valid_failing_assessment_and_valid_coverage_gap_are_not_corrected(self):
        value = deepcopy(self.value)
        value["coverage_complete"] = False
        omitted = value["procedures"].pop()
        value["coverage_gaps"] = [
            {
                "purpose": omitted["purpose"],
                "evidence_id": omitted["evidence_id"],
                "start_line": 6,
                "end_line": 6,
            }
        ]
        session = Session([json.dumps(value)])
        proposal, _ = run_model_phase(session, self.prompt, self.validate)
        self.assertFalse(proposal.coverage_complete)
        self.assertEqual(len(session.calls), 1)
        session = Session(["valid"])
        findings, _ = run_model_phase(session, self.prompt, lambda _: ["work-finding"])
        self.assertEqual(findings, ["work-finding"])
        self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
