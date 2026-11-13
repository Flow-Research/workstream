"""Commit immutable fulfillment custody with every newly earned award."""

import hashlib

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0072_fulfillment_roots"
down_revision = "0071_selected_task_reward"
branch_labels = None
depends_on = None

_LOCK = int.from_bytes(hashlib.sha256(b"workstream.review.joint_lifecycle_mutation").digest()[:8],
                       "big", signed=True)
_MANIFEST = "sha256:c1e2e0a7109efedcab4d4f13fd82d1efac82a6e18da28c989452423604b06616"
_PREVIOUS_MANIFEST = "sha256:3a6704c3c79c243f5a032f2db9c4f47080716dfef86928f53e0f20b4d6047273"


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.get_bind().execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK})
    phase = op.get_bind().execute(sa.text(
        "SELECT phase FROM public.joint_lifecycle_release_control WHERE singleton FOR UPDATE"
    )).scalar_one()
    op.execute("SELECT id FROM public.authority_control WHERE id=1 FOR UPDATE")
    op.execute("LOCK TABLE public.compensation_awards,public.outbox_events IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().execute(sa.text("SELECT EXISTS(SELECT 1 FROM public.compensation_awards)")).scalar_one():
        raise RuntimeError("fulfillment installation refuses retained awards without original root custody")
    if phase != "disabled":
        raise RuntimeError("fulfillment installation requires the lifecycle disabled")
    op.create_table(
        "compensation_fulfillment_roots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("award_id", sa.Uuid(), sa.ForeignKey("public.compensation_awards.id"), nullable=False, unique=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("public.projects.id"), nullable=False),
        sa.Column("ordinal", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("admission_generation", sa.BigInteger(), nullable=False),
        sa.Column("source_instance_id", sa.Uuid(), nullable=False),
        sa.Column("adapter_binding_id", sa.Uuid(), sa.ForeignKey("public.project_compensation_adapter_bindings.id"), nullable=False),
        sa.Column("route_key", sa.String(120), nullable=False),
        sa.Column("source_final_acceptance_id", sa.Uuid(), sa.ForeignKey("public.final_acceptances.id"), nullable=False),
        sa.Column("source_authorization_decision_id", sa.Uuid(), sa.ForeignKey("public.audit_events.id"), nullable=False),
        sa.Column("source_routing_manifest_id", sa.Uuid(), sa.ForeignKey("public.task_post_submit_routing_manifests.id"), nullable=False),
        sa.Column("source_award_digest", sa.String(71), nullable=False),
        sa.Column("obligation_digest", sa.String(71), nullable=False),
        sa.Column("obligation_body", JSONB(), nullable=False),
        sa.Column("initial_outbox_event_id", sa.Uuid(), sa.ForeignKey("public.outbox_events.event_id"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("clock_timestamp()")),
        sa.CheckConstraint("(get_byte(uuid_send(id),6)>>4)=7 and (get_byte(uuid_send(id),8)&192)=128", name="id_uuid7"),
        sa.CheckConstraint("(get_byte(uuid_send(source_instance_id),6)>>4)=7 and (get_byte(uuid_send(source_instance_id),8)&192)=128", name="source_uuid7"),
        sa.CheckConstraint("ordinal>0 and admission_generation>0", name="positive_custody"),
        sa.CheckConstraint("source_award_digest ~ '^sha256:[0-9a-f]{64}$' and obligation_digest ~ '^sha256:[0-9a-f]{64}$'", name="digests"),
        sa.CheckConstraint("jsonb_typeof(obligation_body)='object'", name="obligation_object"),
        schema="public",
    )
    _envelope()
    _custody()
    _manifest()


def _envelope():
    op.execute("""
CREATE FUNCTION public.compensation_fulfillment_obligation(source_uuid uuid,root_uuid uuid,award_uuid uuid)
RETURNS jsonb LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 WITH facts AS (
  SELECT a.*,c.task_id,c.submission_id,c.source_final_acceptance_id,s.task_size,b.route_key
  FROM public.compensation_awards a
  JOIN public.contribution_records c ON c.id=a.contribution_record_id
    AND c.project_id=a.project_id AND c.contributor_id=a.contributor_id
    AND c.contribution_policy_version_id=a.contribution_policy_version_id
    AND c.contribution_type='accepted_submission'
  JOIN public.submissions s ON s.id=c.submission_id AND s.task_id=c.task_id
    AND s.contribution_policy_version_id=c.contribution_policy_version_id
    AND s.contribution_award_definition_id=a.award_definition_id
  JOIN public.workstream_tasks t ON t.id=c.task_id AND t.project_id=c.project_id
  JOIN public.final_acceptances f ON f.id=c.source_final_acceptance_id
    AND f.project_id=c.project_id AND f.task_id=c.task_id AND f.submission_id=c.submission_id
    AND f.accepted_submitter_id=c.contributor_id
  JOIN public.project_compensation_adapter_bindings b ON b.id=a.adapter_binding_id
    AND b.project_id=a.project_id AND b.instrument_type=a.instrument_type
  WHERE a.id=award_uuid
 ), source AS (
  SELECT facts.*,jsonb_build_object(
   'award_id',id::text,'project_id',project_id::text,
   'contribution_record_id',contribution_record_id::text,'contributor_id',contributor_id::text,
   'contribution_policy_version_id',contribution_policy_version_id::text,
   'award_definition_id',award_definition_id::text,'adapter_binding_id',adapter_binding_id::text,
   'instrument_type',instrument_type,'unit_code',unit_code,
   'quantity',CASE WHEN position('.' IN quantity::text)>0
       THEN rtrim(rtrim(quantity::text,'0'),'.') ELSE quantity::text END,
   'awarded_at',to_char(created_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
   'correlation_id',correlation_id::text) AS body
  FROM facts
 ), envelope AS (
  SELECT body||jsonb_build_object(
   'contract_version',1,'source_instance_id',source_uuid::text,'fulfillment_root_id',root_uuid::text,
   'contribution_type','accepted_submission','task_id',task_id::text,'submission_id',submission_id::text,
   'final_acceptance_id',source_final_acceptance_id::text,'review_id',NULL,
   'task_size',task_size,'route_key',route_key,
   'source_award_digest','sha256:'||encode(sha256(convert_to(
      public.project_guide_projection_canonical_json(body),'UTF8')),'hex')) AS body
  FROM source
 ) SELECT body||jsonb_build_object('obligation_digest','sha256:'||encode(sha256(convert_to(
      public.project_guide_projection_canonical_json(body),'UTF8')),'hex')) FROM envelope;
$$;
    """)


def _custody():
    op.execute("""
CREATE FUNCTION public.compensation_fulfillment_root_is_valid(r public.compensation_fulfillment_roots)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT coalesce(r.obligation_body=public.compensation_fulfillment_obligation(r.source_instance_id,r.id,r.award_id)
  AND r.project_id::text=r.obligation_body->>'project_id'
  AND r.adapter_binding_id::text=r.obligation_body->>'adapter_binding_id'
  AND r.route_key=r.obligation_body->>'route_key'
  AND r.source_final_acceptance_id::text=r.obligation_body->>'final_acceptance_id'
  AND r.source_award_digest=r.obligation_body->>'source_award_digest'
  AND r.obligation_digest=r.obligation_body->>'obligation_digest'
  AND EXISTS(SELECT 1 FROM public.final_acceptances f
    JOIN public.task_post_submit_routing_manifests m ON m.id=f.source_routing_manifest_id
    WHERE f.id=r.source_final_acceptance_id AND f.acceptance_source='task_post_submit_route'
      AND f.source_authorization_decision_id=r.source_authorization_decision_id
      AND f.source_routing_manifest_id=r.source_routing_manifest_id
      AND m.authorization_decision_id=r.source_authorization_decision_id
      AND m.final_acceptance_id=f.id AND m.authorized_lifecycle_generation=r.admission_generation
      AND public.task_routing_receipt_valid(m)),false);
$$;
    """)
    op.execute("""
CREATE FUNCTION public.compensation_fulfillment_payload(r public.compensation_fulfillment_roots)
RETURNS jsonb LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT jsonb_build_object('fulfillment_root_id',r.id::text,'award_id',r.award_id::text,
   'adapter_binding_id',r.adapter_binding_id::text,'admission_generation',r.admission_generation,
   'source_award_digest',r.source_award_digest,'obligation_digest',r.obligation_digest);
$$;
    """)
    op.execute("""
CREATE FUNCTION public.compensation_fulfillment_is_complete(award_uuid uuid)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM public.compensation_fulfillment_roots r
   JOIN public.compensation_awards a ON a.id=r.award_id
   JOIN public.outbox_events e ON e.event_id=r.initial_outbox_event_id
   WHERE r.award_id=award_uuid AND public.compensation_fulfillment_root_is_valid(r)
     AND e.event_type='compensation.obligation.deliver' AND e.event_version=1
     AND e.producer='workstream' AND e.aggregate_type='compensation_fulfillment' AND e.aggregate_id=r.id
     AND e.project_id=r.project_id AND e.correlation_id=a.correlation_id::text
     AND e.causation_event_id IS NULL AND e.not_before_at IS NULL
     AND e.idempotency_key='compensation.fulfillment:'||r.id::text
     AND e.payload::jsonb=public.compensation_fulfillment_payload(r)
     AND e.payload_digest='sha256:'||encode(sha256(convert_to(
       public.project_guide_projection_canonical_json(public.compensation_fulfillment_payload(r)),'UTF8')),'hex'));
$$;
    """)
    unsigned = _LOCK & ((1 << 64) - 1)
    op.execute(f"""
CREATE FUNCTION public.guard_compensation_fulfillment_root() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 PERFORM pg_catalog.pg_export_snapshot();
 IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_locks WHERE locktype='advisory'
   AND pid=pg_backend_pid() AND granted AND mode='ExclusiveLock'
   AND classid={unsigned >> 32}::oid AND objid={unsigned & 0xffffffff}::oid AND objsubid=1)
  OR NOT EXISTS(SELECT 1 FROM public.joint_lifecycle_release_control c
    WHERE c.singleton AND c.generation=NEW.admission_generation
      AND public.joint_lifecycle_new_effects_enabled(c)) THEN
  RAISE EXCEPTION 'fulfillment admission generation unavailable' USING ERRCODE='23514'; END IF;
 IF NEW.ordinal<>(SELECT coalesce(max(ordinal),0)+1 FROM public.compensation_fulfillment_roots)
   OR EXISTS(SELECT 1 FROM public.compensation_fulfillment_roots WHERE source_instance_id<>NEW.source_instance_id) THEN
  RAISE EXCEPTION 'fulfillment ordinal or source differs' USING ERRCODE='23514'; END IF;
 IF NOT public.compensation_fulfillment_root_is_valid(NEW) THEN
  RAISE EXCEPTION 'fulfillment root source differs' USING ERRCODE='23514'; END IF;
 NEW.created_at:=clock_timestamp();
 RETURN NEW;
END $$;
    """)
    op.execute("""
CREATE FUNCTION public.guard_compensation_fulfillment_closure() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE award_uuid uuid;
BEGIN
 IF TG_TABLE_NAME='compensation_awards' THEN award_uuid:=NEW.id;
 ELSIF TG_TABLE_NAME='compensation_fulfillment_roots' THEN award_uuid:=NEW.award_id;
 ELSE
   SELECT award_id INTO award_uuid FROM public.compensation_fulfillment_roots WHERE initial_outbox_event_id=NEW.event_id;
 END IF;
 IF award_uuid IS NULL OR NOT public.compensation_fulfillment_is_complete(award_uuid) THEN
  RAISE EXCEPTION 'compensation fulfillment custody incomplete' USING ERRCODE='23514'; END IF;
 RETURN NULL;
END $$;
    """)
    op.execute("""
CREATE TRIGGER compensation_fulfillment_root_source BEFORE INSERT ON public.compensation_fulfillment_roots
 FOR EACH ROW EXECUTE FUNCTION public.guard_compensation_fulfillment_root();
    """)
    op.execute("""
CREATE TRIGGER compensation_fulfillment_root_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
 ON public.compensation_fulfillment_roots FOR EACH STATEMENT EXECUTE FUNCTION public.reject_artifact_fact_mutation();
    """)
    op.execute("""
CREATE CONSTRAINT TRIGGER compensation_award_fulfillment_closure AFTER INSERT ON public.compensation_awards
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_compensation_fulfillment_closure();
    """)
    op.execute("""
CREATE CONSTRAINT TRIGGER compensation_root_fulfillment_closure AFTER INSERT ON public.compensation_fulfillment_roots
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_compensation_fulfillment_closure();
    """)
    op.execute("""
CREATE CONSTRAINT TRIGGER compensation_event_fulfillment_closure AFTER INSERT ON public.outbox_events
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.event_type='compensation.obligation.deliver')
 EXECUTE FUNCTION public.guard_compensation_fulfillment_closure();
    """)


def _manifest():
    for signature, occurrences in (
        ("public.joint_lifecycle_transition_valid(public.joint_lifecycle_transitions)", 2),
        ("public.joint_lifecycle_new_effects_enabled(public.joint_lifecycle_release_control)", 1),
    ):
        body = op.get_bind().execute(sa.text("SELECT pg_get_functiondef(to_regprocedure(:signature))"),
                                     {"signature": signature}).scalar_one()
        if body.count(_PREVIOUS_MANIFEST) != occurrences or _MANIFEST in body:
            raise RuntimeError("fulfillment lifecycle manifest owner changed")
        op.execute(body.replace(_PREVIOUS_MANIFEST, _MANIFEST))


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
