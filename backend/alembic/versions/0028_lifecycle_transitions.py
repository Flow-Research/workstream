"""Extend the shared singleton with exact Operator-authorized transition custody."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0028_lifecycle_transitions"
down_revision = "0027_markdown_guide_media"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    _audit_contract()
    op.create_table(
        "joint_lifecycle_transitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("singleton_id", sa.Uuid(), sa.ForeignKey("public.joint_lifecycle_release_control.id"), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("previous_phase", sa.String(16), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("facts_json", JSONB(), nullable=False),
        sa.Column("resource_context_digest", sa.String(71), nullable=False),
        sa.Column("authorization_decision_event_id", sa.Uuid(), sa.ForeignKey("public.audit_events.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        sa.UniqueConstraint("operation_id"),
        sa.UniqueConstraint("singleton_id", "generation"),
        sa.UniqueConstraint("authorization_decision_event_id"),
        sa.CheckConstraint("generation > 0", name="generation_positive"),
        schema="public",
    )
    op.add_column("joint_lifecycle_release_control", sa.Column("transition_id", sa.Uuid()), schema="public")
    op.create_foreign_key(
        "fk_joint_lifecycle_release_control_transition_id", "joint_lifecycle_release_control",
        "joint_lifecycle_transitions", ["transition_id"], ["id"], deferrable=True, initially="DEFERRED",
        source_schema="public", referent_schema="public",
    )
    op.execute("DROP TRIGGER joint_lifecycle_genesis_immutable ON public.joint_lifecycle_release_control")
    op.execute("DROP TRIGGER joint_lifecycle_genesis_no_truncate ON public.joint_lifecycle_release_control")
    op.execute("DROP FUNCTION public.guard_joint_lifecycle_genesis()")
    _functions()
    op.execute("""
CREATE TRIGGER joint_lifecycle_history_time BEFORE INSERT
ON public.joint_lifecycle_transitions FOR EACH ROW
EXECUTE FUNCTION public.stamp_joint_lifecycle_history_time()
""")
    op.execute("""
CREATE TRIGGER joint_lifecycle_control_change BEFORE INSERT OR UPDATE OR DELETE
ON public.joint_lifecycle_release_control FOR EACH ROW
EXECUTE FUNCTION public.guard_joint_lifecycle_control_change()
""")
    op.execute("""
CREATE TRIGGER joint_lifecycle_history_immutable BEFORE UPDATE OR DELETE
ON public.joint_lifecycle_transitions FOR EACH ROW
EXECUTE FUNCTION public.deny_joint_lifecycle_mutation()
""")
    for table in ("joint_lifecycle_release_control", "joint_lifecycle_transitions"):
        op.execute(f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON public.{table} "
                   "FOR EACH STATEMENT EXECUTE FUNCTION public.deny_joint_lifecycle_mutation()")
    op.execute("""
CREATE CONSTRAINT TRIGGER joint_lifecycle_history_closure AFTER INSERT
ON public.joint_lifecycle_transitions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION public.guard_joint_lifecycle_history_closure()
""")
    op.execute("""
CREATE CONSTRAINT TRIGGER joint_lifecycle_control_closure AFTER UPDATE
ON public.joint_lifecycle_release_control DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION public.guard_joint_lifecycle_control_closure()
""")
    op.execute("""
CREATE CONSTRAINT TRIGGER joint_lifecycle_authority_closure AFTER INSERT
ON public.audit_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
WHEN (NEW.action_id='review.lifecycle.activation.manage' AND NEW.event_type='SensitiveAuthorizationAllowed')
EXECUTE FUNCTION public.guard_joint_lifecycle_authority_closure()
""")


def _audit_contract():
    op.execute("LOCK TABLE public.audit_events IN ACCESS EXCLUSIVE MODE")
    name = "ck_audit_events_authorization_action_evidence"
    definition = _definition(name)
    anchor = "(((action_id)::text = 'project.task.create'::text) AND ((permission_id)::text = 'project.task.manage'::text))"
    addition = "(((action_id)::text = 'review.lifecycle.activation.manage'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text))"
    if definition.count(anchor) != 2:
        raise RuntimeError("lifecycle audit action anchor changed")
    _replace(name, definition.replace(anchor, anchor + " OR " + addition))
    name = "ck_audit_events_authority_privacy_bounds"
    definition = _definition(name)
    # Add only one UUID resource/target kind; retain every existing privacy bound.
    resource_start = definition.index("resource_type IS NULL")
    target_start = definition.index("target_ref_kind IS NULL")
    for start in sorted((resource_start, target_start), reverse=True):
        index = definition.index("ARRAY[", start) + len("ARRAY[")
        definition = definition[:index] + "('joint_lifecycle_control'::character varying)::text, " + definition[index:]
    _replace(name, definition)


def _definition(name):
    return op.get_bind().execute(sa.text(
        "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
        "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
    ), {"name": name}).scalar_one()


def _replace(name, definition):
    op.execute(f"ALTER TABLE public.audit_events DROP CONSTRAINT {name}")
    op.execute(f"ALTER TABLE public.audit_events ADD CONSTRAINT {name} {definition}")


def _functions():
    op.execute("""
CREATE FUNCTION public.stamp_joint_lifecycle_history_time() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 NEW.created_at := pg_catalog.clock_timestamp();
 RETURN NEW;
END;
$$
""")
    op.execute("""
CREATE FUNCTION public.deny_joint_lifecycle_mutation() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN RAISE EXCEPTION 'joint lifecycle custody is immutable' USING ERRCODE='23514'; END;
$$
""")
    op.execute("""
CREATE FUNCTION public.joint_lifecycle_transition_valid(t public.joint_lifecycle_transitions)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT coalesce(
  t.generation>0 AND t.generation=(t.facts_json->'command'->>'expected_generation')::bigint+1
  AND t.operation_id::text=t.facts_json->'command'->>'operation_id'
  AND t.singleton_id::text=t.facts_json->'command'->>'singleton_id'
  AND t.previous_phase=t.facts_json->'command'->>'current_phase'
  AND t.phase=t.facts_json->'command'->>'target_phase'
  AND (t.previous_phase,t.phase) IN (('disabled','shadow'),('shadow','live'),('shadow','disabled'),('live','draining'),('draining','disabled'))
  AND t.created_at < (t.facts_json->'command'->>'deadline')::timestamptz
  AND t.facts_json->'command'->>'reviewed_manifest_digest'='sha256:f7385c3930e0a3fc60a55e4a35c67b00c1bd3056ffa89a1e09ecae4b736c3ab4'
  AND (t.phase<>'live' OR NOT EXISTS (SELECT 1 FROM public.final_acceptances))
  AND t.facts_json->>'observations_digest'='sha256:' || pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
    public.project_guide_projection_canonical_json(pg_catalog.jsonb_build_object(
      'singleton_id',t.singleton_id::text,'generation',t.generation-1,'phase',t.previous_phase,
      'retained_pre_authority_acceptance',EXISTS(SELECT 1 FROM public.final_acceptances),
      'manifest','sha256:f7385c3930e0a3fc60a55e4a35c67b00c1bd3056ffa89a1e09ecae4b736c3ab4')), 'UTF8')), 'hex')
  AND t.resource_context_digest='sha256:' || pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
    public.project_guide_projection_canonical_json(pg_catalog.jsonb_build_object('resource_context',
      pg_catalog.jsonb_build_object('action_id','review.lifecycle.activation.manage',
        'resource_type','joint_lifecycle_control','resource_id',t.singleton_id::text,'facts',t.facts_json))), 'UTF8')), 'hex')
  AND EXISTS (
    SELECT 1 FROM public.audit_events a
    JOIN public.admin_role_grants g ON g.id::text=a.matched_grant_id
    JOIN public.actor_profiles p ON p.id::text=a.actor_id
    JOIN public.actor_identity_links l ON l.actor_profile_id=p.id
    WHERE a.id=t.authorization_decision_event_id
      AND a.event_domain='authority' AND a.event_type='SensitiveAuthorizationAllowed'
      AND a.actor_ref_kind='actor_profile' AND p.actor_kind='human' AND p.status='active'
      AND p.id::text=t.facts_json->'command'->>'actor_profile_id'
      AND l.id::text=t.facts_json->'command'->>'identity_link_id' AND l.status='active'
      AND g.target_actor_profile_id=p.id AND g.role='operator' AND g.status='active'
      AND g.scope_type='system' AND g.scope_project_id IS NULL
      AND a.action_id='review.lifecycle.activation.manage' AND a.permission_id='operations.reconcile.run'
      AND a.request_id IS NOT NULL AND a.correlation_id=t.operation_id
      AND a.project_id IS NULL AND a.resource_type='joint_lifecycle_control' AND a.resource_id=t.singleton_id::text
      AND a.target_ref_kind='joint_lifecycle_control' AND a.target_ref_id=t.singleton_id::text
      AND a.denial_code IS NULL AND a.after_facts::jsonb=pg_catalog.jsonb_build_object(
        'allowed',true,'resource_context_digest',t.resource_context_digest)
  ),false)
$$
""")
    op.execute("""
CREATE FUNCTION public.guard_joint_lifecycle_authority_closure() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF NOT EXISTS (
  SELECT 1 FROM public.joint_lifecycle_transitions t WHERE t.authorization_decision_event_id=NEW.id
   AND public.joint_lifecycle_transition_valid(t)
 ) THEN RAISE EXCEPTION 'joint lifecycle authority closure invalid' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END;
$$
""")
    op.execute("""
CREATE FUNCTION public.guard_joint_lifecycle_control_change() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF TG_OP<>'UPDATE' THEN
  RAISE EXCEPTION 'joint lifecycle custody is immutable' USING ERRCODE='23514';
 END IF;
 IF NEW.id IS DISTINCT FROM OLD.id OR NEW.singleton IS DISTINCT FROM OLD.singleton
  OR NEW.created_at IS DISTINCT FROM OLD.created_at OR NEW.generation<>OLD.generation+1
  OR NEW.transition_id IS NULL OR NOT EXISTS (
   SELECT 1 FROM public.joint_lifecycle_transitions t WHERE t.id=NEW.transition_id
    AND t.singleton_id=OLD.id AND t.generation=NEW.generation
    AND t.phase=NEW.phase AND t.previous_phase=OLD.phase
    AND public.joint_lifecycle_transition_valid(t)
  ) THEN RAISE EXCEPTION 'joint lifecycle transition custody invalid' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END;
$$
""")
    op.execute("""
CREATE FUNCTION public.guard_joint_lifecycle_history_closure() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF NOT public.joint_lifecycle_transition_valid(NEW) OR NOT EXISTS (
  SELECT 1 FROM public.joint_lifecycle_release_control c
  WHERE c.id=NEW.singleton_id AND c.transition_id=NEW.id AND c.generation=NEW.generation AND c.phase=NEW.phase
 ) THEN RAISE EXCEPTION 'joint lifecycle history closure invalid' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END;
$$
""")
    op.execute("""
CREATE FUNCTION public.guard_joint_lifecycle_control_closure() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF NOT EXISTS (
  SELECT 1 FROM public.joint_lifecycle_transitions t JOIN public.joint_lifecycle_release_control c ON c.transition_id=t.id
  WHERE c.id=NEW.id AND c.generation=NEW.generation AND c.phase=NEW.phase
    AND t.singleton_id=c.id AND t.generation=c.generation AND t.phase=c.phase
    AND public.joint_lifecycle_transition_valid(t)
 ) THEN RAISE EXCEPTION 'joint lifecycle controller closure invalid' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END;
$$
""")


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
