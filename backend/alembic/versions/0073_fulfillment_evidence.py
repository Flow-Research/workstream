"""Retain original-bound immutable fulfillment receipts and linked exceptions."""

import hashlib

from alembic import op
import sqlalchemy as sa

revision = "0073_fulfillment_evidence"
down_revision = "0072_fulfillment_roots"
branch_labels = None
depends_on = None

_LOCK = int.from_bytes(hashlib.sha256(b"workstream.review.joint_lifecycle_mutation").digest()[:8],
                       "big", signed=True)


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.get_bind().execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK})
    phase = op.get_bind().execute(sa.text(
        "SELECT phase FROM public.joint_lifecycle_release_control WHERE singleton FOR UPDATE"
    )).scalar_one()
    op.execute("SELECT id FROM public.authority_control WHERE id=1 FOR UPDATE")
    if phase != "disabled":
        raise RuntimeError("fulfillment evidence installation requires the lifecycle disabled")
    op.execute("LOCK TABLE public.compensation_fulfillment_roots, "
               "public.project_compensation_adapter_bindings,public.audit_events IN ACCESS EXCLUSIVE MODE")
    _audit_vocabulary()
    _schema()
    _resource()
    _body_validation()
    _insertion()
    _closure()



def _audit_vocabulary():
    """Extend only the three exact action pairs and four closed resource types."""
    actions = (
        "compensation.fulfillment.report",
        "compensation.fulfillment.exception.report",
        "compensation.fulfillment.source.read",
    )
    resources = (
        "compensation_fulfillment_report", "compensation_fulfillment_exception",
        "compensation_fulfillment_evidence", "compensation_fulfillment_report_lookup",
    )
    pair_anchor = (
        "(((action_id)::text = 'contribution.read_self'::text) AND "
        "((permission_id)::text = 'contribution.read_self'::text))"
    )
    replacements = {
        "ck_audit_events_authorization_action_evidence": (
            pair_anchor,
            "".join(f" OR (((action_id)::text = '{action}'::text) AND "
                    f"((permission_id)::text = '{action}'::text))" for action in actions),
            2, actions,
        ),
        "ck_audit_events_authority_registries": (
            "('outbox.dispatch'::character varying)::text",
            "".join(f", ('{action}'::character varying)::text" for action in actions),
            1, actions,
        ),
        "ck_audit_events_authority_privacy_bounds": (
            "('outbox_event'::character varying)::text",
            "".join(f", ('{resource}'::character varying)::text" for resource in resources),
            1, resources,
        ),
    }
    for name, (anchor, addition, count, tokens) in replacements.items():
        definition = op.get_bind().execute(sa.text(
            "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
            "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
        ), {"name": name}).scalar_one()
        if definition.count(anchor) != count or any(token in definition for token in tokens):
            raise RuntimeError("fulfillment audit constraint shape changed: " + name)
        op.execute(f"ALTER TABLE public.audit_events DROP CONSTRAINT {name}")
        op.execute(f"ALTER TABLE public.audit_events ADD CONSTRAINT {name} "
                   + definition.replace(anchor, anchor + addition))


def _schema():
    op.execute(r"""
CREATE TABLE public.compensation_fulfillment_receipts (
	id UUID NOT NULL,
	fulfillment_root_id UUID NOT NULL,
	award_id UUID NOT NULL,
	project_id UUID NOT NULL,
	source_instance_id UUID NOT NULL,
	adapter_binding_id UUID NOT NULL,
	external_event_id UUID NOT NULL,
	evidence_ordinal BIGINT NOT NULL,
	recording_lifecycle_generation BIGINT NOT NULL,
	reported_status VARCHAR(16) NOT NULL,
	report_body JSONB NOT NULL,
	report_digest VARCHAR(71) NOT NULL,
	reporter_actor_id UUID NOT NULL,
	reporter_identity_link_id UUID NOT NULL,
	authorization_decision_id UUID NOT NULL,
	authorization_resource_digest VARCHAR(71) NOT NULL,
	received_at TIMESTAMP WITH TIME ZONE NOT NULL,
	CONSTRAINT pk_compensation_fulfillment_receipts PRIMARY KEY (id),
	CONSTRAINT ck_compensation_fulfillment_receipts_id_uuid7 CHECK ((get_byte(uuid_send(id),6)>>4)=7 and (get_byte(uuid_send(id),8)&192)=128),
	CONSTRAINT ck_compensation_fulfillment_receipts_event_uuid7 CHECK ((get_byte(uuid_send(external_event_id),6)>>4)=7 and (get_byte(uuid_send(external_event_id),8)&192)=128),
	CONSTRAINT ck_compensation_fulfillment_receipts_positive_custody CHECK (evidence_ordinal>0 and recording_lifecycle_generation>0),
	CONSTRAINT ck_compensation_fulfillment_receipts_digests CHECK (report_digest ~ '^sha256:[0-9a-f]{64}$' and authorization_resource_digest ~ '^sha256:[0-9a-f]{64}$'),
	CONSTRAINT ck_compensation_fulfillment_receipts_reported_status CHECK (reported_status in ('failed','fulfilled')),
	CONSTRAINT ck_compensation_fulfillment_receipts_report_object CHECK (jsonb_typeof(report_body)='object'),
	CONSTRAINT uq_fulfillment_receipt_binding_event UNIQUE (adapter_binding_id, external_event_id),
	CONSTRAINT uq_fulfillment_receipt_root_ordinal UNIQUE (fulfillment_root_id, evidence_ordinal),
	CONSTRAINT fk_compensation_fulfillment_receipts_fulfillment_root_i_cd6e FOREIGN KEY(fulfillment_root_id) REFERENCES compensation_fulfillment_roots (id),
	CONSTRAINT fk_compensation_fulfillment_receipts_award_id_compensat_6b88 FOREIGN KEY(award_id) REFERENCES compensation_awards (id),
	CONSTRAINT fk_compensation_fulfillment_receipts_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id),
	CONSTRAINT fk_compensation_fulfillment_receipts_adapter_binding_id_b094 FOREIGN KEY(adapter_binding_id) REFERENCES project_compensation_adapter_bindings (id),
	CONSTRAINT fk_compensation_fulfillment_receipts_reporter_actor_id__9be6 FOREIGN KEY(reporter_actor_id) REFERENCES actor_profiles (id),
	CONSTRAINT fk_compensation_fulfillment_receipts_reporter_identity__6ca2 FOREIGN KEY(reporter_identity_link_id) REFERENCES actor_identity_links (id),
	CONSTRAINT fk_compensation_fulfillment_receipts_authorization_deci_10e8 FOREIGN KEY(authorization_decision_id) REFERENCES audit_events (id)
);
    """)
    op.execute(r"""
CREATE UNIQUE INDEX uq_fulfillment_receipt_fulfilled_award ON public.compensation_fulfillment_receipts (award_id) WHERE reported_status='fulfilled';
    """)
    op.execute(r"""
CREATE TABLE public.compensation_fulfillment_exceptions (
	id UUID NOT NULL,
	fulfillment_root_id UUID NOT NULL,
	award_id UUID NOT NULL,
	project_id UUID NOT NULL,
	source_instance_id UUID NOT NULL,
	adapter_binding_id UUID NOT NULL,
	exception_event_id UUID NOT NULL,
	original_receipt_id UUID NOT NULL,
	original_fulfillment_event_id UUID NOT NULL,
	evidence_ordinal BIGINT NOT NULL,
	recording_lifecycle_generation BIGINT NOT NULL,
	kind VARCHAR(32) NOT NULL,
	exception_body JSONB NOT NULL,
	exception_digest VARCHAR(71) NOT NULL,
	reporter_actor_id UUID NOT NULL,
	reporter_identity_link_id UUID NOT NULL,
	authorization_decision_id UUID NOT NULL,
	authorization_resource_digest VARCHAR(71) NOT NULL,
	received_at TIMESTAMP WITH TIME ZONE NOT NULL,
	CONSTRAINT pk_compensation_fulfillment_exceptions PRIMARY KEY (id),
	CONSTRAINT ck_compensation_fulfillment_exceptions_id_uuid7 CHECK ((get_byte(uuid_send(id),6)>>4)=7 and (get_byte(uuid_send(id),8)&192)=128),
	CONSTRAINT ck_compensation_fulfillment_exceptions_event_uuid7 CHECK ((get_byte(uuid_send(exception_event_id),6)>>4)=7 and (get_byte(uuid_send(exception_event_id),8)&192)=128),
	CONSTRAINT ck_compensation_fulfillment_exceptions_positive_custody CHECK (evidence_ordinal>0 and recording_lifecycle_generation>0),
	CONSTRAINT ck_compensation_fulfillment_exceptions_digests CHECK (exception_digest ~ '^sha256:[0-9a-f]{64}$' and authorization_resource_digest ~ '^sha256:[0-9a-f]{64}$'),
	CONSTRAINT ck_compensation_fulfillment_exceptions_kind CHECK (kind in ('provider_reversal','provider_status_conflict')),
	CONSTRAINT ck_compensation_fulfillment_exceptions_exception_object CHECK (jsonb_typeof(exception_body)='object'),
	CONSTRAINT uq_fulfillment_exception_binding_event UNIQUE (adapter_binding_id, exception_event_id),
	CONSTRAINT uq_fulfillment_exception_root_ordinal UNIQUE (fulfillment_root_id, evidence_ordinal),
	CONSTRAINT fk_compensation_fulfillment_exceptions_fulfillment_root_afa9 FOREIGN KEY(fulfillment_root_id) REFERENCES compensation_fulfillment_roots (id),
	CONSTRAINT fk_compensation_fulfillment_exceptions_award_id_compens_532f FOREIGN KEY(award_id) REFERENCES compensation_awards (id),
	CONSTRAINT fk_compensation_fulfillment_exceptions_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id),
	CONSTRAINT fk_compensation_fulfillment_exceptions_adapter_binding__3173 FOREIGN KEY(adapter_binding_id) REFERENCES project_compensation_adapter_bindings (id),
	CONSTRAINT fk_compensation_fulfillment_exceptions_original_receipt_0d2a FOREIGN KEY(original_receipt_id) REFERENCES compensation_fulfillment_receipts (id),
	CONSTRAINT fk_compensation_fulfillment_exceptions_reporter_actor_i_a26e FOREIGN KEY(reporter_actor_id) REFERENCES actor_profiles (id),
	CONSTRAINT fk_compensation_fulfillment_exceptions_reporter_identit_77e6 FOREIGN KEY(reporter_identity_link_id) REFERENCES actor_identity_links (id),
	CONSTRAINT fk_compensation_fulfillment_exceptions_authorization_de_446d FOREIGN KEY(authorization_decision_id) REFERENCES audit_events (id)
);
    """)


def _resource():
    op.execute(r"""
CREATE FUNCTION public.compensation_fulfillment_evidence_resource(
 e jsonb,r public.compensation_fulfillment_roots,is_exception boolean)
RETURNS jsonb LANGUAGE plpgsql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE facts jsonb; event_id text; resource_type text;
BEGIN
 facts:=jsonb_build_object(
  'source_instance_id',r.source_instance_id::text,'fulfillment_root_id',r.id::text,
  'award_id',r.award_id::text,'project_id',r.project_id::text,
  'adapter_binding_id',r.adapter_binding_id::text,'binding_actor_id',e->>'reporter_actor_id',
  'reporter_actor_id',e->>'reporter_actor_id',
  'reporter_identity_link_id',e->>'reporter_identity_link_id',
  'source_award_digest',r.source_award_digest,'obligation_digest',r.obligation_digest,
  'admission_generation',r.admission_generation,
  'recording_lifecycle_generation',e->'recording_lifecycle_generation');
 IF is_exception THEN
  event_id:=e->>'exception_event_id'; resource_type:='compensation_fulfillment_exception';
  facts:=facts||jsonb_build_object('exception_event_id',event_id,
    'exception_digest',e->>'exception_digest',
    'original_fulfillment_event_id',e->>'original_fulfillment_event_id');
 ELSE
  event_id:=e->>'external_event_id'; resource_type:='compensation_fulfillment_report';
  facts:=facts||jsonb_build_object('external_event_id',event_id,'report_digest',e->>'report_digest');
 END IF;
 RETURN jsonb_build_object('resource_type',resource_type,'resource_id',event_id,
   'scope_project_id',r.project_id::text,'facts',facts);
END $$;
    """)
    op.execute(r"""
CREATE FUNCTION public.compensation_fulfillment_evidence_resource_digest(context jsonb)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT 'sha256:'||encode(sha256(convert_to(public.project_guide_projection_canonical_json(
  jsonb_build_object('domain','workstream.authorization.compensation_fulfillment.v0.1',
                    'resource',context)),'UTF8')),'hex');
$$;
    """)
    op.execute(r"""
CREATE FUNCTION public.compensation_new_fulfillment_allow_valid(
 e jsonb,r public.compensation_fulfillment_roots,is_exception boolean)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 WITH expected AS (
  SELECT public.compensation_fulfillment_evidence_resource(e,r,is_exception) AS context,
   CASE WHEN is_exception THEN 'compensation.fulfillment.exception.report'
        ELSE 'compensation.fulfillment.report' END AS action
 ), bound AS (
  SELECT *,public.compensation_fulfillment_evidence_resource_digest(context) AS digest FROM expected
 ) SELECT EXISTS(SELECT 1 FROM public.audit_events a CROSS JOIN bound b
   WHERE a.id=(e->>'authorization_decision_id')::uuid
    AND a.xmin=pg_current_xact_id()::xid
    AND a.entity_type='authorization_decision' AND a.entity_id=a.id
    AND a.event_domain='authority' AND a.event_type='SensitiveAuthorizationAllowed'
    AND a.actor_ref_kind='actor_profile' AND a.actor_id=e->>'reporter_actor_id'
    AND a.action_id=b.action AND a.permission_id=b.action
    AND a.project_id=r.project_id AND a.resource_type=b.context->>'resource_type'
    AND a.resource_id=b.context->>'resource_id'
    AND a.target_ref_kind='project' AND a.target_ref_id=r.project_id::text
    AND a.denial_code IS NULL AND a.matched_grant_id IS NULL
    AND a.idempotency_reference IS NULL AND a.request_id IS NOT NULL AND a.correlation_id IS NOT NULL
    AND e->>'authorization_resource_digest'=b.digest
    AND a.after_facts::jsonb=jsonb_build_object('allowed',true,'resource_context_digest',b.digest));
$$;
    """)


def _body_validation():
    op.execute(r"""
CREATE FUNCTION public.compensation_fulfillment_event_time(value text)
RETURNS timestamptz LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE parsed timestamptz;
BEGIN
 IF value IS NULL OR value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$'
 THEN RETURN NULL; END IF;
 parsed:=value::timestamptz;
 IF to_char(parsed AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')<>value
 THEN RETURN NULL; END IF;
 RETURN parsed;
EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN RETURN NULL;
END $$;
    """)
    op.execute(r"""
CREATE FUNCTION public.compensation_fulfillment_report_valid(
 body jsonb,obligation jsonb,received_at timestamptz)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE reported timestamptz; awarded timestamptz; fulfilled timestamptz; keys text[];
BEGIN
 IF body IS NULL OR jsonb_typeof(body)<>'object' THEN RETURN false; END IF;
 SELECT array_agg(key ORDER BY key) INTO keys FROM jsonb_object_keys(body) AS k(key);
 IF keys<>ARRAY['adapter_binding_id','award_id','contract_version','correlation_id','external_event_id',
   'external_reference','failure_code','fulfilled_at','fulfilled_quantity','fulfillment_root_id',
   'instrument_type','project_id','reported_at','reported_status','route_key','source_instance_id','unit_code']
 THEN RETURN false; END IF;
 IF NOT coalesce(body @> jsonb_build_object(
   'contract_version',1,'source_instance_id',obligation->>'source_instance_id',
   'fulfillment_root_id',obligation->>'fulfillment_root_id','award_id',obligation->>'award_id',
   'project_id',obligation->>'project_id','adapter_binding_id',obligation->>'adapter_binding_id',
   'route_key',obligation->>'route_key','instrument_type',obligation->>'instrument_type',
   'unit_code',obligation->>'unit_code','correlation_id',obligation->>'correlation_id')
   AND body->>'contract_version'='1',false) THEN RETURN false; END IF;
 reported:=public.compensation_fulfillment_event_time(body->>'reported_at');
 awarded:=public.compensation_fulfillment_event_time(obligation->>'awarded_at');
 IF reported IS NULL OR awarded IS NULL OR received_at IS NULL
   OR reported<awarded-interval '300 seconds' OR reported>received_at+interval '300 seconds'
 THEN RETURN false; END IF;
 IF body->>'reported_status'='failed' THEN
  RETURN coalesce(body->'fulfilled_quantity'='null'::jsonb AND body->'fulfilled_at'='null'::jsonb
   AND body->'external_reference'='null'::jsonb AND body->>'failure_code'=ANY(ARRAY[
    'ADAPTER_REJECTED','DESTINATION_UNAVAILABLE','PROVIDER_UNAVAILABLE','PROVIDER_TIMEOUT',
    'UNKNOWN_PROVIDER_FAILURE']),false);
 ELSIF body->>'reported_status'='fulfilled' THEN
  fulfilled:=public.compensation_fulfillment_event_time(body->>'fulfilled_at');
  RETURN coalesce(body->'fulfilled_quantity'=obligation->'quantity'
   AND body->'failure_code'='null'::jsonb AND jsonb_typeof(body->'external_reference')='string'
   AND body->>'external_reference' ~ '^[A-Za-z0-9._:-]{1,128}$'
   AND fulfilled IS NOT NULL AND fulfilled>=awarded-interval '300 seconds'
   AND fulfilled<=received_at+interval '300 seconds' AND reported>=fulfilled-interval '300 seconds',false);
 END IF;
 RETURN false;
END $$;
    """)
    op.execute(r"""
CREATE FUNCTION public.compensation_fulfillment_exception_valid(
 body jsonb,obligation jsonb,original public.compensation_fulfillment_receipts,received_at timestamptz)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE reported timestamptz; observed timestamptz; fulfilled timestamptz; keys text[];
BEGIN
 IF body IS NULL OR jsonb_typeof(body)<>'object' THEN RETURN false; END IF;
 SELECT array_agg(key ORDER BY key) INTO keys FROM jsonb_object_keys(body) AS k(key);
 IF keys<>ARRAY['adapter_binding_id','award_id','contract_version','correlation_id','exception_event_id',
  'fulfillment_root_id','kind','observed_at','original_fulfillment_event_id','project_id',
  'reported_at','route_key','source_instance_id'] THEN RETURN false; END IF;
 IF original.reported_status<>'fulfilled' OR NOT coalesce(body @> jsonb_build_object(
   'contract_version',1,'source_instance_id',obligation->>'source_instance_id',
   'fulfillment_root_id',obligation->>'fulfillment_root_id','award_id',obligation->>'award_id',
   'project_id',obligation->>'project_id','adapter_binding_id',obligation->>'adapter_binding_id',
   'route_key',obligation->>'route_key','correlation_id',obligation->>'correlation_id',
   'original_fulfillment_event_id',original.external_event_id::text)
   AND body->>'contract_version'='1',false) THEN RETURN false; END IF;
 reported:=public.compensation_fulfillment_event_time(body->>'reported_at');
 observed:=public.compensation_fulfillment_event_time(body->>'observed_at');
 fulfilled:=public.compensation_fulfillment_event_time(original.report_body->>'fulfilled_at');
 RETURN coalesce(body->>'kind'=ANY(ARRAY['provider_reversal','provider_status_conflict'])
   AND reported IS NOT NULL AND observed IS NOT NULL AND fulfilled IS NOT NULL
   AND observed>=fulfilled-interval '300 seconds' AND observed<=received_at+interval '300 seconds'
   AND reported>=observed-interval '300 seconds' AND reported<=received_at+interval '300 seconds',false);
END $$;
    """)


def _insertion():
    unsigned = _LOCK & ((1 << 64) - 1)
    op.execute(f"""
CREATE FUNCTION public.guard_compensation_fulfillment_evidence() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE r public.compensation_fulfillment_roots; original public.compensation_fulfillment_receipts;
 c public.joint_lifecycle_release_control; body jsonb; e jsonb; digest text;
 is_exception boolean:=TG_TABLE_NAME='compensation_fulfillment_exceptions'; next_ordinal bigint;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN
  RAISE EXCEPTION 'fulfillment evidence requires read committed'
   USING ERRCODE='23514',CONSTRAINT='fulfillment_evidence_read_committed'; END IF;
 PERFORM pg_catalog.pg_export_snapshot();
 IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_locks WHERE locktype='advisory'
   AND pid=pg_backend_pid() AND granted AND mode='ExclusiveLock'
   AND classid={unsigned >> 32}::oid AND objid={unsigned & 0xffffffff}::oid AND objsubid=1)
 THEN RAISE EXCEPTION 'fulfillment evidence requires current lifecycle custody'
   USING ERRCODE='23514',CONSTRAINT='fulfillment_evidence_lifecycle'; END IF;
 SELECT * INTO c FROM public.joint_lifecycle_release_control WHERE singleton FOR UPDATE;
 IF NOT FOUND OR c.generation<>NEW.recording_lifecycle_generation
   OR c.fulfillment_source_instance_id IS DISTINCT FROM NEW.source_instance_id
 THEN RAISE EXCEPTION 'fulfillment evidence lifecycle or source differs'
   USING ERRCODE='23514',CONSTRAINT='fulfillment_evidence_lifecycle'; END IF;
 PERFORM 1 FROM public.actor_profiles WHERE id=NEW.reporter_actor_id AND actor_kind='service'
   AND service_identity='workstream.compensation.adapter' AND status='active' FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'fulfillment evidence reporter unavailable'
   USING ERRCODE='23514',CONSTRAINT='fulfillment_evidence_reporter'; END IF;
 PERFORM 1 FROM public.actor_identity_links WHERE id=NEW.reporter_identity_link_id
   AND actor_profile_id=NEW.reporter_actor_id AND status='active' AND subject_kind='service' FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'fulfillment evidence reporter link unavailable'
   USING ERRCODE='23514',CONSTRAINT='fulfillment_evidence_reporter'; END IF;
 PERFORM 1 FROM public.project_compensation_adapter_bindings WHERE id=NEW.adapter_binding_id
   AND project_id=NEW.project_id AND adapter_actor_id=NEW.reporter_actor_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'fulfillment evidence original binding differs'
   USING ERRCODE='23514',CONSTRAINT='fulfillment_evidence_source'; END IF;
 SELECT * INTO r FROM public.compensation_fulfillment_roots WHERE id=NEW.fulfillment_root_id
   AND award_id=NEW.award_id AND project_id=NEW.project_id AND source_instance_id=NEW.source_instance_id
   AND adapter_binding_id=NEW.adapter_binding_id FOR UPDATE;
 IF NOT FOUND OR NOT public.compensation_fulfillment_root_is_valid(r)
 THEN RAISE EXCEPTION 'fulfillment evidence immutable source differs'
   USING ERRCODE='23514',CONSTRAINT='fulfillment_evidence_source'; END IF;
 e:=to_jsonb(NEW);
 IF NOT public.compensation_new_fulfillment_allow_valid(e,r,is_exception)
 THEN RAISE EXCEPTION 'fulfillment evidence exact authority differs'
   USING ERRCODE='23514',CONSTRAINT='fulfillment_evidence_authority'; END IF;
 NEW.received_at:=clock_timestamp();
 IF is_exception THEN
  SELECT * INTO original FROM public.compensation_fulfillment_receipts
   WHERE id=NEW.original_receipt_id AND external_event_id=NEW.original_fulfillment_event_id
    AND fulfillment_root_id=r.id AND award_id=r.award_id AND project_id=r.project_id
    AND adapter_binding_id=r.adapter_binding_id AND reported_status='fulfilled';
  IF NOT FOUND THEN RAISE EXCEPTION 'fulfillment exception requires its actual success'
    USING ERRCODE='23514',CONSTRAINT='fulfillment_exception_parent'; END IF;
  body:=NEW.exception_body; digest:=NEW.exception_digest;
  IF NOT public.compensation_fulfillment_exception_valid(body,r.obligation_body,original,NEW.received_at)
    OR body->>'exception_event_id' IS DISTINCT FROM NEW.exception_event_id::text
    OR body->>'kind' IS DISTINCT FROM NEW.kind
  THEN RAISE EXCEPTION 'fulfillment exception body differs'
    USING ERRCODE='23514',CONSTRAINT='fulfillment_exception_body'; END IF;
 ELSE
  body:=NEW.report_body; digest:=NEW.report_digest;
  IF NOT public.compensation_fulfillment_report_valid(body,r.obligation_body,NEW.received_at)
    OR body->>'external_event_id' IS DISTINCT FROM NEW.external_event_id::text
    OR body->>'reported_status' IS DISTINCT FROM NEW.reported_status
  THEN RAISE EXCEPTION 'fulfillment report body differs'
    USING ERRCODE='23514',CONSTRAINT='fulfillment_report_body'; END IF;
 END IF;
 IF digest IS DISTINCT FROM 'sha256:'||encode(sha256(convert_to(
   public.project_guide_projection_canonical_json(body),'UTF8')),'hex')
 THEN RAISE EXCEPTION 'fulfillment evidence body digest differs'
   USING ERRCODE='23514',CONSTRAINT='fulfillment_evidence_body_digest'; END IF;
 SELECT coalesce(max(n),0)+1 INTO next_ordinal FROM (
   SELECT evidence_ordinal AS n FROM public.compensation_fulfillment_receipts WHERE fulfillment_root_id=r.id
   UNION ALL
   SELECT evidence_ordinal AS n FROM public.compensation_fulfillment_exceptions WHERE fulfillment_root_id=r.id
 ) AS evidence;
 NEW.evidence_ordinal:=next_ordinal;
 RETURN NEW;
END $$;
    """)


def _closure():
    op.execute(r"""
CREATE FUNCTION public.guard_compensation_fulfillment_allow_closure() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF NEW.event_domain<>'authority' OR NEW.event_type<>'SensitiveAuthorizationAllowed' THEN RETURN NULL; END IF;
 IF NEW.action_id='compensation.fulfillment.report' THEN
  IF NOT EXISTS(SELECT 1 FROM public.compensation_fulfillment_receipts e
    JOIN public.compensation_fulfillment_roots r ON r.id=e.fulfillment_root_id
    WHERE e.authorization_decision_id=NEW.id
      AND public.compensation_new_fulfillment_allow_valid(to_jsonb(e),r,false))
  THEN RAISE EXCEPTION 'fulfillment report allow lacks immutable receipt'
    USING ERRCODE='23514',CONSTRAINT='fulfillment_report_allow_closure'; END IF;
 ELSIF NEW.action_id='compensation.fulfillment.exception.report' THEN
  IF NOT EXISTS(SELECT 1 FROM public.compensation_fulfillment_exceptions e
    JOIN public.compensation_fulfillment_roots r ON r.id=e.fulfillment_root_id
    WHERE e.authorization_decision_id=NEW.id
      AND public.compensation_new_fulfillment_allow_valid(to_jsonb(e),r,true))
  THEN RAISE EXCEPTION 'fulfillment exception allow lacks immutable evidence'
    USING ERRCODE='23514',CONSTRAINT='fulfillment_exception_allow_closure'; END IF;
 END IF;
 RETURN NULL;
END $$;
    """)
    op.execute(r"""
CREATE TRIGGER compensation_fulfillment_receipt_source BEFORE INSERT
 ON public.compensation_fulfillment_receipts FOR EACH ROW
 EXECUTE FUNCTION public.guard_compensation_fulfillment_evidence();
    """)
    op.execute(r"""
CREATE TRIGGER compensation_fulfillment_exception_source BEFORE INSERT
 ON public.compensation_fulfillment_exceptions FOR EACH ROW
 EXECUTE FUNCTION public.guard_compensation_fulfillment_evidence();
    """)
    op.execute(r"""
CREATE TRIGGER compensation_fulfillment_receipt_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
 ON public.compensation_fulfillment_receipts FOR EACH STATEMENT
 EXECUTE FUNCTION public.reject_artifact_fact_mutation();
    """)
    op.execute(r"""
CREATE TRIGGER compensation_fulfillment_exception_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
 ON public.compensation_fulfillment_exceptions FOR EACH STATEMENT
 EXECUTE FUNCTION public.reject_artifact_fact_mutation();
    """)
    op.execute(r"""
CREATE CONSTRAINT TRIGGER compensation_fulfillment_allow_closure AFTER INSERT ON public.audit_events
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
 EXECUTE FUNCTION public.guard_compensation_fulfillment_allow_closure();
    """)


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
