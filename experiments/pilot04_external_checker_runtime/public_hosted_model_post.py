"""One public model POST engineering proof, through the actual hosted workers.

The operator supplies a private JSON file with image_reference,
image_config_digest, image_archive_sha256, proof_state and
historical_uncertain_reference. The existing hosted attachment supplies service
custody and simulated RS256 actors. Run the ordinary hosted journey first to
bootstrap actors/services. An existing proof_state always stops a new run: inspect
the retained project/account instead of creating another paid project. This driver
never calls the proxy or provider directly and never retries an ambiguous effect.
The fixed claim path is node_root/model-post-qualification.json; preserve it and
the same lifetime account for any later full-trial stage.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import time
from uuid import UUID, uuid4
from zipfile import ZipFile, ZipInfo

from experiments.pilot04_external_checker_runtime.public_hosted_attachment import ROOT, require

CHECK = 'solver_brief_and_extension_disclosure'
CEILING = 10_000_000_000
MODEL = 'openai/gpt-5.6-terra'
MODEL_CONTEXT = ROOT / 'pilots/terminal_systems/checkers/post/model'
POST_IMAGE = 'workstream/terminal-systems-post@sha256:94a0a10e81c67deb6d433312d2c40fbca52ec7d27ccc0f714979cf51946794be'
POST_CONFIG = 'sha256:d46fea222c9a91c3cb1425a6c00e73b2bacf9756c6226017db8773cefe6003f7'
POST_ARCHIVE = 'sha256:ff87ecf15599f504f461dbf28868ad98206796c57a733de353747f049b7b80f8'
POST_CONTEXT_TREE = '82d968cf2d919e8ccd938d3780745b2b32bce314'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return 'sha256:' + hashlib.sha256(value).hexdigest()


def specification():
    """Use the actual project handoff and bundled rubric, without copying grading."""
    from app.interfaces.project_agents import CheckSpecification

    handoff = json.loads((MODEL_CONTEXT.parent.parent / 'setup-handoff.json').read_text())
    bundled = json.loads((MODEL_CONTEXT / 'rubrics.json').read_text())
    original = next(item for item in handoff['requirements'] if item['requirement_id'] == CHECK)
    rubric = next(item for item in bundled['requirements'] if item['requirement_id'] == CHECK)
    value = original['check_specification']
    require(all(value[key] == expected for key, expected in rubric['check_specification'].items()),
            'model image rubric differs from retained project handoff')
    proposal = {key: value[key] for key in (
        'inputs', 'check_steps', 'pass_conditions', 'failure_findings',
        'positive_tests', 'negative_tests',
    )}
    proposal.update(
        evaluation_method='Apply the qualitative solver brief and extension disclosure rubric to the submitted materials.',
        implementation_needs=[value['runtime_dependencies'][0]['purpose']],
        inability_to_evaluate=value['infrastructure_failures'],
    )
    return CheckSpecification.model_validate(proposal), original['statement']


def profile_spec(project_id, pricing_id):
    from app.modules.model_usage.api import ProjectModelProfileSpec

    pricing = {'provider': 'openrouter', 'api': 'chat_completions', 'model': MODEL,
               'uncached_input_nanodollars_per_token': 5000,
               'cached_input_nanodollars_per_token': 400,
               'output_nanodollars_per_token': 18000}
    value = ProjectModelProfileSpec.model_validate({
        'project_id': project_id, 'profile_version': 1, 'provider': 'openrouter',
        'api': 'chat_completions', 'model_snapshot': MODEL,
        'settings': {'reasoning_effort': 'low', 'text_verbosity': 'low'},
        'maximum_request_bytes': 262144, 'maximum_output_bytes': 32768,
        'maximum_response_bytes': 200704, 'maximum_input_tokens': 1050000,
        'maximum_output_tokens': 4096, 'maximum_calls': 1,
        'maximum_total_request_bytes': 262144, 'maximum_total_response_bytes': 200704,
        'maximum_total_input_tokens': 1050000, 'maximum_total_output_tokens': 4096,
        'allowed_tools': (), 'maximum_tool_calls': 0, 'maximum_tool_output_bytes': 0,
        'deadline_ms': 180000,
        'pricing': {'pricing_policy_id': pricing_id, 'pricing_policy_version': 1,
                    'pricing_policy_digest': digest(canonical(pricing)),
                    **{key: pricing[key] for key in pricing if key.endswith('_per_token')}},
    })
    require(value.maximum_reservation_nanodollars == 5_323_728_000
            and value.maximum_reservation_nanodollars <= CEILING,
            'model qualification reservation exceeds its authorization')
    return value


def registry_spec(image_digest):
    from app.modules.checkers.api.external import ExternalCheckerRegistrySpec

    def schema(identifier, document):
        return {'schema_id': identifier, 'schema_version': 'v1', 'document': document,
                'schema_sha256': digest(canonical(document))}

    properties = {'check': {'const': CHECK}, 'model_profile_id': {'type': 'string'},
                  'model_profile_version': {'type': 'integer'}, 'model_profile_digest': {'type': 'string'}}
    return ExternalCheckerRegistrySpec.model_validate({
        'capability_id': 'terminal_systems.post.model', 'capability_version': 'hosted-v1',
        'phase': 'post_submit', 'image_digest': image_digest,
        'configuration_schema': schema('terminal_systems.post.hosted_configuration', {
            'type': 'object', 'additionalProperties': False,
            'properties': properties, 'required': sorted(properties)}),
        'input_schema': schema('external_checker_post_submit_input', {'type': 'object'}),
        'output_schema': schema('external_checker_result', {'type': 'object'}),
        'resources': {'cpu_millis': 1000, 'memory_bytes': 256 * 1024 * 1024,
                      'deadline_ms': 600000, 'maximum_output_bytes': 32768},
    })


def fixture_archive():
    """A disclosed tiny authored task; the production rubric judges it for real."""
    files = {
        'task.toml': b"[task]\nname='hosted-model-engineering-proof'\n",
        'instruction.md': (
            '# One-line copy engineering fixture\n\n'
            'This is a synthetic hosted model transport qualification, not a real pilot task. '
            'The starting workspace/seed.txt contains the example line qualified-result. '
            'Implement a repair that copies its exact bytes to workspace/result.txt without changing seed.txt. '
            'Any implementation with this behavior is allowed. The only supported commands are '
            '`sh solution/apply.sh` (the supplied reference) and `sh tests/run.sh` (visible verification), '
            'both run from the package root with POSIX sh, cat, test and cmp. '
            'The reference overwrites result.txt; missing/unreadable input must produce a nonzero exit. '
            'Verification succeeds only if result.txt exists and is byte-identical to seed.txt; otherwise it exits nonzero. '
            'No network, other files, hidden tests, optional metadata extensions or additional grading constraints exist. '
            'AUTHOR_NOTES.md and evidence/results are author disclosures, not solver examples.\n'
        ).encode(),
        'AUTHOR_NOTES.md': b'No metadata extensions. The visible seed is explicitly an example. No runtime execution is claimed by this model-only qualification.\n',
        'workspace/seed.txt': b'qualified-result\n',
        'solution/apply.sh': b'#!/bin/sh\nset -eu\ncat workspace/seed.txt > workspace/result.txt\n',
        'tests/run.sh': b'#!/bin/sh\nset -eu\ntest -f workspace/result.txt\ncmp workspace/seed.txt workspace/result.txt\n',
        'evidence/results': b'Model-only engineering fixture: no execution or trial measurement is claimed.\n',
    }
    output = BytesIO()
    with ZipFile(output, 'w') as archive:
        for name, body in sorted(files.items()):
            item = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.create_system, item.external_attr = 3, 0o100644 << 16
            archive.writestr(item, body)
    return output.getvalue()


def validate_runtime_window(values, settings):
    """Refuse an unrunnable paid rehearsal before creating its durable claim."""
    from app.core.config import Settings
    from app.modules.checkers.api.external_policy import (
        SELECTED_POST_MATERIALIZATION_BUDGET_MS,
        EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS,
    )

    member = registry_spec(POST_IMAGE.rsplit('@', 1)[1]).resources.deadline_ms
    execution = member + EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS
    required = SELECTED_POST_MATERIALIZATION_BUDGET_MS + execution
    artifact_seconds = float(values['WORKSTREAM_ARTIFACT_PREPARATION_TOTAL_DEADLINE_SECONDS'])
    socket_seconds = float(values.get(
        'WORKSTREAM_EXTERNAL_CHECKER_SERVICE_TIMEOUT_SECONDS',
        Settings.model_fields['external_checker_service_timeout_seconds'].default,
    ))
    require(settings.artifact_preparation_total_deadline_seconds == artifact_seconds
            and settings.external_checker_service_timeout_seconds == socket_seconds,
            'model qualification runtime windows differ from inspected hosted roles')
    require(artifact_seconds * 1000 >= required,
            'model qualification exceeds the inspected ART custody window')
    require(socket_seconds * 1000 >= execution,
            'model qualification exceeds the inspected checker socket window')
    return required


def require_completed_effect(ledger):
    require(len(ledger['effects']) == 1 and ledger['effects'][0]['state'] == 'completed'
            and ledger['effects'][0]['provider_response_known']
            and ledger['effects'][0]['request_binding_id'] and ledger['effects'][0]['response_binding_id']
            and ledger['reserved_nanodollars'] == 0,
            'model POST has an incomplete or ambiguous paid effect; stop')


@dataclass
class ModelPostQualification:
    image_reference: str
    image_config_digest: str
    image_archive_sha256: str
    proof_state: Path
    historical_uncertain_reference: str
    descriptor: int = -1

    @classmethod
    def read_and_claim(cls, path, node_root):
        from experiments.hosted_drill_identity.fixture import read_private

        value = json.loads(read_private(path))
        require(set(value) == {'image_reference', 'image_config_digest', 'image_archive_sha256',
                               'proof_state', 'historical_uncertain_reference'}, 'model proof fields differ')
        require(isinstance(value['historical_uncertain_reference'], str)
                and 0 < len(value['historical_uncertain_reference']) <= 256,
                'retain the earlier unresolved charge reference separately')
        value['proof_state'] = Path(value['proof_state'])
        require(value['proof_state'] == node_root / 'model-post-qualification.json',
                'model proof claim must use this deployment\'s single fixed state path')
        result = cls(**value)
        result.claim()
        return result

    def claim(self):
        require(self.proof_state.is_absolute() and self.proof_state.resolve() == self.proof_state,
                'model proof state must be canonical')
        parent = self.proof_state.parent.stat()
        require(stat.S_ISDIR(parent.st_mode) and parent.st_uid == os.getuid()
                and parent.st_mode & 0o077 == 0, 'model proof directory must be private and owned')
        # An existing claim forbids another paid project, including after a crash.
        self.descriptor = os.open(self.proof_state, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.state = {'scope': 'manager-authored engineering model POST; no setup-agent/pilot/full-trial claim',
                      'phase': 'claimed', 'total_authorization_nanodollars': CEILING,
                      'historical_charge': {'reference': self.historical_uncertain_reference, 'status': 'unresolved_separate'},
                      'operation_keys': {key: str(uuid4()) for key in ('profile', 'budget', 'registry')}}
        self.checkpoint()
        directory = os.open(self.proof_state.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def checkpoint(self, **fields):
        self.state.update(fields)
        os.lseek(self.descriptor, 0, os.SEEK_SET)
        data = canonical(self.state) + b'\n'
        offset = 0
        while offset < len(data):
            count = os.write(self.descriptor, data[offset:])
            require(count > 0, 'model proof state write failed')
            offset += count
        os.ftruncate(self.descriptor, len(data))
        os.fsync(self.descriptor)

    def close(self):
        if self.descriptor >= 0:
            os.close(self.descriptor)
            self.descriptor = -1

    def verify_cache(self, attachment):
        from experiments.pilot04_external_checker_runtime.public_hosted_attachment import _command

        require((self.image_reference, self.image_config_digest, self.image_archive_sha256)
                == (POST_IMAGE, POST_CONFIG, POST_ARCHIVE), 'model POST qualification image identity differs')
        context_tree = _command(['git', 'rev-parse', 'HEAD:pilots/terminal_systems/checkers/post/model']).decode().strip()
        require(context_tree == POST_CONTEXT_TREE, 'production model image context changed after qualification')
        repository, image = self.image_reference.rsplit('@', 1)
        require(repository == 'workstream/terminal-systems-post', 'qualification requires the production project image')
        binding = json.loads((attachment.node_root / 'node-binding.json').read_text())
        matches = [item for item in binding['node_config']['cache'] if item['repository'] == repository
                   and item['platform_manifest_digest'] == image and item['config_image_id'] == self.image_config_digest
                   and item['smol']['archive_sha256'] == self.image_archive_sha256]
        require(len(matches) == 1, 'model POST image is absent or substituted in native cache')
        require(attachment.values['WORKSTREAM_MODEL_PROXY_ENABLED'] == 'true'
                and 'model-proxy' in attachment.custody, 'actual hosted model proxy is required')
        specification()
        self.checkpoint(image_reference=self.image_reference, image_config_digest=self.image_config_digest,
                        image_archive_sha256=self.image_archive_sha256,
                        image_context_tree=context_tree,
                        rubric_sha256=digest((MODEL_CONTEXT / 'rubrics.json').read_bytes()))

    async def bind_project(self, client, project_id, attachment):
        from app.core.identifiers import new_record_id
        from app.modules.model_usage.api import ProjectModelProfile, ProjectModelBudgetConfigurationSpec
        from experiments.pilot04_external_checker_runtime.public_probe_support import _json

        require('project_id' not in self.state, 'this qualification already owns one project')
        self.checkpoint(phase='project_created', project_id=project_id)
        token = attachment.token_for_label('operator')
        root = f'/api/v1/operations/projects/{project_id}'
        profile = profile_spec(UUID(project_id), new_record_id())
        published = await _json(client, 'POST', root + '/model-profiles', token, 201,
                                headers={'Idempotency-Key': self.state['operation_keys']['profile']},
                                json=profile.model_dump(mode='json'))
        self.profile = ProjectModelProfile.model_validate_json(canonical(published))
        require(self.profile.spec == profile, 'published model profile differs')
        budget = ProjectModelBudgetConfigurationSpec(project_id=UUID(project_id), configuration_version=1,
                    authorized_total_nanodollars=CEILING, externally_reconciled_prior_spend_nanodollars=0,
                    lifetime_limit_nanodollars=CEILING)
        receipt = await _json(client, 'POST', root + '/model-budget-configurations', token, 201,
                             headers={'Idempotency-Key': self.state['operation_keys']['budget']},
                             json=budget.model_dump(mode='json'))
        require(receipt['spec'] == budget.model_dump(mode='json'), 'published model budget differs')
        require(receipt['lifetime_reserved_nanodollars'] == receipt['lifetime_settled_nanodollars'] == 0,
                'new qualification project already has model spend or reservations')
        spec = registry_spec(self.image_reference.rsplit('@', 1)[1])
        registry = await _json(client, 'POST', '/api/v1/operations/external-checker-registry', token, 201,
                               headers={'Idempotency-Key': self.state['operation_keys']['registry']},
                               json=spec.model_dump(mode='json'))
        require(registry['entry_digest'] == spec.spec_digest, 'published model registry differs')
        self.registry = registry
        self.checkpoint(phase='authority_published', profile=published, budget=receipt, registry=registry,
                        maximum_run_reservation_nanodollars=profile.maximum_reservation_nanodollars)

    def guide_bytes(self):
        _, statement = specification()
        return ('# Hosted model POST engineering qualification\n\n'
                'This manager-authored guide describes only the Terminal Systems '
                f'`{CHECK}` model rubric. It does not claim setup inference, a real pilot or runtime trials.\n\n'
                + statement + '\n').encode()

    def rules(self, original, count):
        from experiments.pilot04_external_checker_runtime.public_hosted_attachment import manager_rules

        require(count == 0, 'model qualification must not propose a PRE check')
        body = json.loads(manager_rules(original, 0))
        spec, statement = specification()
        body['requirements'] = [{'suggestion_id': 'suggested.solver_brief_and_extension_disclosure',
            'statement': statement, 'stage': 'post_submit',
            'classification_rationale': 'The rubric evaluates the submitted task after intake.',
            'evidence_refs': body['findings'][0]['evidence_refs'], 'check_specification': spec.model_dump(mode='json')}]

        return canonical(body)

    def approval_attachments(self):
        """Select the exact published model image and profile as the human manager."""
        from app.modules.checkers.api.external_policy import ExternalCheckerImageAttachment

        require(hasattr(self, 'registry') and hasattr(self, 'profile'),
                'model image and profile must be published before approval')
        configuration = {'check': CHECK, **self.profile.selector.model_dump(mode='json')}
        # The selector DTO uses profile_* names; image configuration reserves model_profile_* names.
        configuration = {('model_' + key if key.startswith('profile_') else key): value
                         for key, value in configuration.items()}
        entry = ExternalCheckerImageAttachment.model_validate({
            'requirement_id': CHECK,
            'registry_entry_id': self.registry['registry_entry_id'],
            'registry_entry_digest': self.registry['entry_digest'],
            'configuration': configuration,
        })
        return {'pre_submit_attachments': [],
                'post_submit_attachments': [entry.model_dump(mode='json')]}


async def account_snapshot(factory, project_id):
    from sqlalchemy import or_, select
    from app.modules.model_usage.models import (
        ModelUsageBudgetAccount, ModelUsageEffect, CheckerModelUsageSlot, SetupModelUsageSlot,
    )

    async with factory() as session:
        account = await session.get(ModelUsageBudgetAccount, project_id)
        effects = (await session.scalars(select(ModelUsageEffect)
            .outerjoin(CheckerModelUsageSlot, CheckerModelUsageSlot.id == ModelUsageEffect.checker_slot_id)
            .outerjoin(SetupModelUsageSlot, SetupModelUsageSlot.id == ModelUsageEffect.setup_slot_id)
            .where(or_(CheckerModelUsageSlot.project_id == project_id, SetupModelUsageSlot.project_id == project_id))
            .order_by(ModelUsageEffect.id))).all()
        require(account is not None, 'model qualification account is absent')
        settled, reserved = account.lifetime_settled_nanodollars, account.lifetime_reserved_nanodollars
        require(0 <= settled and 0 <= reserved and settled + reserved <= CEILING,
                'model qualification lifetime ledger exceeds authorization')
        return {'settled_nanodollars': settled, 'reserved_nanodollars': reserved,
                'billing_scope': 'conservative ledger charge at pinned rates; not a provider invoice',
                'provider_invoice_qualified': False,
                'configuration_id': account.current_configuration_id,
                'effects': [{'effect_id': item.id, 'state': item.state,
                             'settled_nanodollars': item.settled_nanodollars,
                             'reserved_nanodollars': item.reserved_nanodollars,
                             'provider_response_known': item.provider_response_id is not None,
                             'request_binding_id': item.request_binding_id, 'response_binding_id': item.response_binding_id,
                             'request_sha256': item.request_sha256, 'checker_slot_id': item.checker_slot_id}
                            for item in effects]}


def model_grant_snapshot(grant, calls):
    """Retain the exact immutable grant/call facts before a public recovery."""
    require(len(calls) == 1 and calls[0].call_index == 0,
            'model qualification grant has an unexpected call set')
    call = calls[0]
    return {'grant_id': grant.id, 'checker_run_id': grant.checker_run_id,
            'registry_entry_id': str(grant.registry_entry_id),
            'capability_hash_sha256': digest(grant.token_hash.encode()),
            'external_request_digest': grant.external_request_digest,
            'execution_facts_sha256': digest(canonical(grant.execution_facts)),
            'paid_slot_sha256': digest(canonical(grant.paid_slot)),
            'authorization_evidence_id': grant.authorization_evidence_id,
            'issued_at': grant.issued_at.isoformat(), 'expires_at': grant.expires_at.isoformat(),
            'effect_id': call.attempt_id, 'request_sha256': call.request_sha256,
            'bound_at': call.bound_at.isoformat(), 'call_index': call.call_index}


async def paid_custody(factory, project_id, run_id, submission_id, member, qualification):
    from sqlalchemy import select
    from app.modules.model_usage.models import (
        CheckerModelInvocationGrant, CheckerModelInvocationGrantCall, CheckerModelUsageSlot,
    )
    from app.modules.checkers.models import CheckerRun
    from app.modules.checkers.execution_repository import stored_request

    async with factory() as session:
        grants = (await session.scalars(select(CheckerModelInvocationGrant).where(
            CheckerModelInvocationGrant.project_id == project_id))).all()
        slots = (await session.scalars(select(CheckerModelUsageSlot).where(
            CheckerModelUsageSlot.project_id == project_id))).all()
        retained = qualification.state.get('prior_model_grant')
        expected_grants = 1 if retained is None else 2
        require(len(grants) == expected_grants and len(slots) == 1,
                'model qualification has unexpected grant/paid-slot count')
        current = [grant for grant in grants if grant.checker_run_id == str(run_id)]
        require(len(current) == 1, 'model qualification has no unique current grant')
        grant, slot = current[0], slots[0]
        calls = (await session.scalars(select(CheckerModelInvocationGrantCall).where(
            CheckerModelInvocationGrantCall.grant_id == grant.id))).all()
        require(len(calls) == 1 and calls[0].call_index == 0
                and grant.checker_run_id == str(run_id) and grant.external_request_digest == member.request_digest
                and str(grant.registry_entry_id) == qualification.registry['registry_entry_id']
                and slot.submission_id == submission_id and slot.requirement_id == CHECK
                and slot.profile_id == str(qualification.profile.profile_id)
                and slot.profile_digest == qualification.profile.profile_digest
                and slot.registry_entry_digest == qualification.registry['entry_digest'],
                'model grant and paid slot do not bind this exact selected POST')
        if retained is not None:
            prior = next(item for item in grants if item.id != grant.id)
            prior_calls = (await session.scalars(select(CheckerModelInvocationGrantCall).where(
                CheckerModelInvocationGrantCall.grant_id == prior.id))).all()
            require(model_grant_snapshot(prior, prior_calls) == retained,
                    'retained predecessor grant or call changed')
            previous_run = await session.get(CheckerRun, prior.checker_run_id)
            current_run = await session.get(CheckerRun, str(run_id))
            require(previous_run is not None and current_run is not None
                    and previous_run.status == 'infrastructure_failed'
                    and previous_run.project_id == current_run.project_id == project_id
                    and previous_run.submission_id == current_run.submission_id == submission_id
                    and current_run.supersedes_checker_run_id == previous_run.id
                    and stored_request(previous_run).policy == stored_request(current_run).policy
                    and prior.registry_entry_id == grant.registry_entry_id
                    and prior_calls[0].attempt_id == calls[0].attempt_id
                    and prior_calls[0].request_sha256 == calls[0].request_sha256
                    == slot.first_request_sha256,
                    'model recovery changed lineage, policy or its single paid effect')
        receipt = {'grant_id': grant.id, 'checker_run_id': grant.checker_run_id,
                'external_request_digest': grant.external_request_digest,
                'slot_id': slot.id, 'call_index': calls[0].call_index,
                'effect_id': calls[0].attempt_id, 'request_sha256': calls[0].request_sha256,
                'submission_id': slot.submission_id, 'profile_id': slot.profile_id}
        if retained is not None:
            receipt['prior_model_grant'] = retained
        return receipt


async def run_model_post(attachment, client, factory, qualification):
    from app.modules.tasks.models import SubmissionDispatch
    from experiments.pilot04_external_checker_runtime.public_probe_support import (
        _public_project, _started_public_task,
    )
    from experiments.pilot04_external_checker_runtime.run_public_journey_probe import _submit

    qualification.verify_cache(attachment)
    await attachment.transition('live')
    project, contributor, manager_token, contributor_token = await _public_project(
        client, factory, attachment, human_review_required=False, pre_requirements=0)
    project_id = str(project.project_id)
    task, assignment = await _started_public_task(client, project_id=project_id,
        manager_token=manager_token, contributor_token=contributor_token, source_ref='hosted-model-engineering-proof')
    archive = fixture_archive()
    qualification.checkpoint(phase='task_started', task_id=task, assignment_id=assignment,
                            archive_sha256=digest(archive), guide_setup=project.evidence)
    summary = 'Synthetic model-only hosted qualification.'
    attestation = 'rights_confirmed; no confidential data or credentials.'
    saved = await _submit(client, factory, task_id=task, assignment_id=assignment,
        contributor_token=contributor_token, archive=archive, summary=summary,
        attestation=attestation, predecessor_id=None,
        hosted=True)
    qualification.checkpoint(phase='submission_created', submission=saved)
    async with factory() as session:
        dispatch = await session.get(SubmissionDispatch, saved['submission_id'])
        require(dispatch is not None, 'model POST submission lacks durable dispatch')
        event_id, run_id = dispatch.evaluation_event_id, dispatch.evaluation_attempt_id
    return await observe_model_post(
        attachment, client, factory, qualification, project=project, contributor=contributor,
        task=task, assignment=assignment, archive=archive, summary=summary,
        attestation=attestation, saved=saved, event_id=event_id, run_id=run_id,
    )


async def observe_model_post(attachment, client, factory, qualification, *, project,
                             contributor, task, assignment, archive, summary, attestation,
                             saved, event_id, run_id):
    """Qualify one exact public dispatch; this never creates or retries a run."""
    import asyncio
    from app.core.config import get_settings
    from app.modules.checkers.execution_repository import stored_request, stored_result
    from app.modules.checkers.api.external_policy import (
        selected_post_submit_execution_budget_ms,
        SELECTED_POST_HANDLER_PRELUDE_MARGIN_MS,
        SELECTED_POST_FINALIZATION_MARGIN_MS,
    )
    from app.modules.checkers.models import CheckerRun
    from app.modules.outbox.models import OutboxEvent
    from experiments.pilot04_external_checker_runtime.public_probe_support import (
        _json, _wait_outbox_acknowledged, _fixture_hashes,
    )
    from experiments.pilot04_external_checker_runtime.run_public_journey_probe import (
        _outbox_snapshot, _project_effects_snapshot, _assert_outcome, _assert_revision,
    )

    project_id = str(project.project_id)
    async with factory() as session:
        run = await session.get(CheckerRun, run_id)
        require(run is not None and str(run.project_id) == project_id
                and str(run.task_id) == str(task)
                and str(run.submission_id) == saved['submission_id'],
                'observed model dispatch differs from the retained project and Submission')
        budget = selected_post_submit_execution_budget_ms(
            stored_request(run).policy,
            artifact_deadline_ms=int(get_settings().artifact_preparation_total_deadline_seconds * 1000),
        )
        require(budget == validate_runtime_window(attachment.values, get_settings()),
                'locked model qualification execution budget differs')
    deadline = time.monotonic() + (
        budget + SELECTED_POST_HANDLER_PRELUDE_MARGIN_MS + SELECTED_POST_FINALIZATION_MARGIN_MS
    ) / 1000
    while time.monotonic() < deadline:
        async with factory() as session:
            run = await session.get(CheckerRun, run_id)
            state = run.status
        if state in {'completed', 'infrastructure_failed'}:
            break
        await asyncio.sleep(.5)
    else:
        raise RuntimeError('model POST observation deadline reached; stop without another dispatch')
    await _wait_outbox_acknowledged(factory, event_id, project.project_id)
    ledger = await account_snapshot(factory, project_id)
    qualification.checkpoint(phase='post_observed', ledger=ledger)
    require_completed_effect(ledger)
    async with factory() as session:
        run = await session.get(CheckerRun, run_id)
        require(run.status == 'completed' and run.completion_event_id is not None,
                'model POST did not retain a completed grader outcome')
        result = stored_result(run)
        members = result.execution.external_members if result.execution else []
        require(len(members) == 1 and members[0].requirement_id == CHECK
                and members[0].result.outcome == 'completed', 'model POST has no exact production member result')
        member = members[0]
        require(str(member.registry_entry_id) == qualification.registry['registry_entry_id']
                and member.registry_entry_digest == qualification.registry['entry_digest']
                and (member.isolation.repository + '@' + member.isolation.platform_manifest_digest) == POST_IMAGE
                and member.isolation.config_image_id == POST_CONFIG
                and (member.isolation.runtime, member.isolation.isolation_mode) == ('smolvm', 'smol-microvm'),
                'model POST did not execute the exact approved native project image')
        completion = run.completion_event_id
        verdict, recommendation = members[0].result.verdict, run.routing_recommendation
        require(verdict in {'passed', 'failed'}, 'model judgment has no supported work verdict')
    await _wait_outbox_acknowledged(factory, completion, project.project_id)
    custody = await paid_custody(factory, project_id, run_id, saved['submission_id'], members[0], qualification)
    effect_id = ledger['effects'][0]['effect_id']
    require(custody['effect_id'] == effect_id and custody['slot_id'] == ledger['effects'][0]['checker_slot_id']
            and custody['request_sha256'] == ledger['effects'][0]['request_sha256'],
            'retained model call differs from the exact effect')
    inspection = await _json(client, 'GET', f'/api/v1/operations/projects/{project_id}/model-usage/effects/{effect_id}',
                             attachment.token_for_label('operator'), 200)
    require(inspection['owner_kind'] == 'checker' and inspection['owner']['submission_id'] == saved['submission_id']
            and inspection['state'] == 'completed' and inspection['request_evidence']
            and inspection['response_evidence'] and inspection['usage'], 'public effect inspection lost paid custody')
    from app.modules.model_usage.api import ModelCallUsage, model_usage_cost
    usage = ModelCallUsage.model_validate_json(canonical(inspection['usage']))
    charge = model_usage_cost(qualification.profile.spec, usage)
    require(inspection['settled_nanodollars'] == ledger['settled_nanodollars'] == charge
            and inspection['budget_configuration_id'] == ledger['configuration_id']
            == qualification.state['budget']['configuration_id']
            and inspection['owner']['profile_id'] == str(qualification.profile.profile_id)
            and inspection['owner']['requirement_id'] == CHECK,
            'public model accounting differs from the exact profile or lifetime ledger')
    expected = 'accepted' if verdict == 'passed' else 'needs_revision'
    require(recommendation == ('allow_review' if verdict == 'passed' else 'needs_revision'),
            'selected POST recommendation differs from actual model verdict')
    if verdict == 'passed':
        governed = await _assert_outcome(factory, guide_source=project, project_id=project.project_id,
            task_id=task, submission_id=saved['submission_id'], initial_submission_id=saved['submission_id'],
            contributor_id=contributor.actor_profile_id, human_review_required=False, expected_awards=0,
            expected_submissions=1, expected_inputs={saved['submission_id']: _fixture_hashes(archive)})
    else:
        await _assert_revision(factory, project_id=project.project_id, task_id=task,
                               submission_id=saved['submission_id'], attempt_id=str(run_id))
        governed = {'task_status': expected, 'acceptance_qualified': False}
    async with factory() as session:
        governed_before = await _project_effects_snapshot(session, project.project_id)
        event = await session.get(OutboxEvent, completion)
        require(event.delivery_state == 'acknowledged', 'model completion was not acknowledged')
    before = {str(identifier): await _outbox_snapshot(factory, identifier) for identifier in (event_id, completion)}
    replay = await _json(client, 'POST', f'/api/v1/tasks/{task}/submissions',
        attachment.token_for_label('contributor'), 201,
        json={'assignment_id': assignment, 'admission_id': saved['admission_id'],
              'predecessor_submission_id': None, 'summary': summary, 'contributor_attestation': attestation})
    require(replay == saved, 'completed public Submission replay changed its receipt')
    duplicate_tasks = []
    for identifier in (event_id, completion):
        duplicate = await attachment.deliver_duplicate(identifier, project_id)
        require(duplicate['result'] == {'status': 'delivery_unavailable'},
                'duplicate model delivery result differs')
        duplicate_tasks.append({'event_id': str(identifier), 'task_id': duplicate['task_id']})
    require(await account_snapshot(factory, project_id) == ledger
            and {str(identifier): await _outbox_snapshot(factory, identifier) for identifier in (event_id, completion)} == before
            and await paid_custody(factory, project_id, run_id, saved['submission_id'], members[0], qualification) == custody,
            'duplicate changed model usage, slots, grants or OUTBOX custody')
    async with factory() as session:
        require(await _project_effects_snapshot(session, project.project_id) == governed_before,
                'duplicate changed governed model outcome')
    outcome = {'model_enabled_post_qualification': True, 'full_trial_qualification': False,
               'acceptance_qualified': verdict == 'passed', 'actual_verdict': verdict,
               'task_status': expected, 'project_id': project_id, 'submission': saved,
               'checker_run_id': str(run_id), 'completion_event_id': str(completion),
               'duplicate_deliveries': duplicate_tasks, 'ledger': ledger, 'effect_inspection': inspection,
               'paid_custody': custody, 'governed_outcome': governed}
    qualification.checkpoint(phase='completed', outcome=outcome)
    return outcome
