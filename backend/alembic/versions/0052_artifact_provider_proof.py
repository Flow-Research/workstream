"""Add immutable native AWS artifact-provider proof and activation custody."""

from alembic import op
from scripts.schema_baseline_sql import split_sql_statements

revision = "0052_artifact_provider_proof"
down_revision = "0051_operational_read_audit"
branch_labels = None
depends_on = None


def _execute_sql(sql: str) -> None:
    """Execute separately parsed SQL commands through the async PostgreSQL driver."""
    for statement in split_sql_statements(sql):
        op.execute(statement)


def upgrade() -> None:
    """Create append-only three-probe activation evidence and exact database guards."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    _execute_sql(_TABLES)
    _execute_sql(_GUARDS)


def downgrade() -> None:
    """Retained provider proof and activation evidence cannot be downgraded."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


_TABLES = r"""
CREATE TABLE public.artifact_provider_probe_results (
 id uuid NOT NULL CONSTRAINT pk_artifact_provider_probe_results PRIMARY KEY,
 probe_type varchar(32) NOT NULL,
 proof_version varchar(32) NOT NULL,
 result varchar(8) NOT NULL,
 release_id varchar(71) NOT NULL,
 namespace_fingerprint varchar(71) NOT NULL,
 aws_partition varchar(20) NOT NULL,
 aws_account_id varchar(12) NOT NULL,
 region varchar(32) NOT NULL,
 runtime_role_arn varchar(700) NOT NULL,
 runtime_trust_policy_sha256 varchar(71) NOT NULL,
 runtime_policy_arn varchar(700) NOT NULL,
 readiness_role_arn varchar(700) NOT NULL,
 readiness_trust_policy_sha256 varchar(71) NOT NULL,
 readiness_policy_arn varchar(700) NOT NULL,
 negative_role_arn varchar(700) NOT NULL,
 negative_trust_policy_sha256 varchar(71) NOT NULL,
 bootstrap_principal_arn varchar(700) NOT NULL,
 expected_principal_arn varchar(700) NOT NULL,
 observed_principal_arn varchar(700),
 bucket_policy_sha256 varchar(71) NOT NULL,
 group_nonce uuid NOT NULL,
 evidence_sha256 varchar(71) NOT NULL,
 error_code varchar(80),
 started_at timestamptz NOT NULL,
 completed_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 CONSTRAINT ck_artifact_provider_probe_results_id_uuid7 CHECK (
  (get_byte(uuid_send(id),6)>>4)=7 AND (get_byte(uuid_send(id),8)&192)=128),
 CONSTRAINT ck_artifact_provider_probe_results_probe_type CHECK (
  probe_type IN ('readiness','runtime_immutability','negative_access')),
 CONSTRAINT ck_artifact_provider_probe_results_result CHECK (result IN ('pass','fail')),
 CONSTRAINT ck_artifact_provider_probe_results_release_id_shape CHECK (
  release_id ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_artifact_provider_probe_results_namespace_fingerprint_shape CHECK (
  namespace_fingerprint ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_artifact_provider_probe_results_bucket_policy_sha256_shape CHECK (
  bucket_policy_sha256 ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_artifact_provider_probe_results_runtime_trust_policy_sha256_shape CHECK (
  runtime_trust_policy_sha256 ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_artifact_provider_probe_results_readiness_trust_policy_sha256_shape CHECK (
  readiness_trust_policy_sha256 ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_artifact_provider_probe_results_negative_trust_policy_sha256_shape CHECK (
  negative_trust_policy_sha256 ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_artifact_provider_probe_results_evidence_sha256_shape CHECK (
  evidence_sha256 ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_artifact_provider_probe_results_account_shape CHECK (
  aws_account_id ~ '^[0-9]{12}$'),
 CONSTRAINT ck_artifact_provider_probe_results_roles_distinct CHECK (
  runtime_role_arn<>readiness_role_arn AND
  runtime_role_arn<>negative_role_arn AND
  readiness_role_arn<>negative_role_arn),
 CONSTRAINT ck_artifact_provider_probe_results_trust_digests_distinct CHECK (
  runtime_trust_policy_sha256<>readiness_trust_policy_sha256 AND
  runtime_trust_policy_sha256<>negative_trust_policy_sha256 AND
  readiness_trust_policy_sha256<>negative_trust_policy_sha256),
 CONSTRAINT ck_artifact_provider_probe_results_completion_order CHECK (
  completed_at>=started_at),
 CONSTRAINT ck_artifact_provider_probe_results_expiry_order CHECK (
  expires_at>completed_at),
 CONSTRAINT ck_artifact_provider_probe_results_result_error CHECK (
  (result='pass' AND error_code IS NULL AND observed_principal_arn IS NOT NULL) OR
  (result='fail' AND error_code IS NOT NULL)),
 CONSTRAINT uq_artifact_provider_probe_group_type UNIQUE (
  probe_type,proof_version,release_id,namespace_fingerprint,
  bucket_policy_sha256,group_nonce)
);
CREATE INDEX ix_artifact_provider_probe_group
 ON public.artifact_provider_probe_results
 (group_nonce,proof_version,release_id,namespace_fingerprint,probe_type,expires_at);

CREATE TABLE public.artifact_provider_activations (
 id uuid NOT NULL CONSTRAINT pk_artifact_provider_activations PRIMARY KEY,
 readiness_result_id uuid NOT NULL,
 runtime_result_id uuid NOT NULL,
 negative_result_id uuid NOT NULL,
 supersedes_activation_id uuid,
 proof_version varchar(32) NOT NULL,
 release_id varchar(71) NOT NULL,
 namespace_fingerprint varchar(71) NOT NULL,
 aws_partition varchar(20) NOT NULL,
 aws_account_id varchar(12) NOT NULL,
 region varchar(32) NOT NULL,
 runtime_role_arn varchar(700) NOT NULL,
 runtime_trust_policy_sha256 varchar(71) NOT NULL,
 runtime_policy_arn varchar(700) NOT NULL,
 readiness_role_arn varchar(700) NOT NULL,
 readiness_trust_policy_sha256 varchar(71) NOT NULL,
 readiness_policy_arn varchar(700) NOT NULL,
 negative_role_arn varchar(700) NOT NULL,
 negative_trust_policy_sha256 varchar(71) NOT NULL,
 bootstrap_principal_arn varchar(700) NOT NULL,
 bucket_policy_sha256 varchar(71) NOT NULL,
 group_nonce uuid NOT NULL,
 activated_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 CONSTRAINT ck_artifact_provider_activations_id_uuid7 CHECK (
  (get_byte(uuid_send(id),6)>>4)=7 AND (get_byte(uuid_send(id),8)&192)=128),
 CONSTRAINT ck_artifact_provider_activations_release_id_shape CHECK (
  release_id ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_artifact_provider_activations_namespace_fingerprint_shape CHECK (
  namespace_fingerprint ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_artifact_provider_activations_bucket_policy_sha256_shape CHECK (
  bucket_policy_sha256 ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_artifact_provider_activations_runtime_trust_policy_sha256_shape CHECK (
  runtime_trust_policy_sha256 ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_artifact_provider_activations_readiness_trust_policy_sha256_shape CHECK (
  readiness_trust_policy_sha256 ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_artifact_provider_activations_negative_trust_policy_sha256_shape CHECK (
  negative_trust_policy_sha256 ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_artifact_provider_activations_account_shape CHECK (
  aws_account_id ~ '^[0-9]{12}$'),
 CONSTRAINT ck_artifact_provider_activations_roles_distinct CHECK (
  runtime_role_arn<>readiness_role_arn AND
  runtime_role_arn<>negative_role_arn AND
  readiness_role_arn<>negative_role_arn),
 CONSTRAINT ck_artifact_provider_activations_trust_digests_distinct CHECK (
  runtime_trust_policy_sha256<>readiness_trust_policy_sha256 AND
  runtime_trust_policy_sha256<>negative_trust_policy_sha256 AND
  readiness_trust_policy_sha256<>negative_trust_policy_sha256),
 CONSTRAINT ck_artifact_provider_activations_expiry_order CHECK (expires_at>activated_at),
 CONSTRAINT fk_artifact_provider_activation_readiness FOREIGN KEY(readiness_result_id)
  REFERENCES public.artifact_provider_probe_results(id) ON DELETE RESTRICT,
 CONSTRAINT fk_artifact_provider_activation_runtime FOREIGN KEY(runtime_result_id)
  REFERENCES public.artifact_provider_probe_results(id) ON DELETE RESTRICT,
 CONSTRAINT fk_artifact_provider_activation_negative FOREIGN KEY(negative_result_id)
  REFERENCES public.artifact_provider_probe_results(id) ON DELETE RESTRICT,
 CONSTRAINT fk_artifact_provider_activation_supersedes FOREIGN KEY(supersedes_activation_id)
  REFERENCES public.artifact_provider_activations(id) ON DELETE RESTRICT,
 CONSTRAINT uq_artifact_activation_readiness UNIQUE(readiness_result_id),
 CONSTRAINT uq_artifact_activation_runtime UNIQUE(runtime_result_id),
 CONSTRAINT uq_artifact_activation_negative UNIQUE(negative_result_id),
 CONSTRAINT uq_artifact_activation_supersedes UNIQUE(supersedes_activation_id),
 CONSTRAINT uq_artifact_provider_activation_group UNIQUE(
  proof_version,release_id,namespace_fingerprint,bucket_policy_sha256,group_nonce)
);
CREATE INDEX ix_artifact_provider_activation_runtime_lookup
 ON public.artifact_provider_activations
 (release_id,namespace_fingerprint,bucket_policy_sha256,expires_at DESC,activated_at DESC,id DESC);
"""


_GUARDS = r"""
CREATE FUNCTION public.guard_artifact_provider_probe_result() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF TG_OP<>'INSERT' THEN
  RAISE EXCEPTION 'artifact provider probe results are immutable' USING ERRCODE='55000';
 END IF;
 IF NEW.proof_version<>'aws-s3-live-v1'
  OR NEW.started_at>clock_timestamp()
  OR NEW.completed_at>clock_timestamp()
  OR NEW.expires_at<>NEW.started_at+interval '15 minutes'
  OR octet_length(NEW.expected_principal_arn) NOT BETWEEN 20 AND 700
  OR (NEW.observed_principal_arn IS NOT NULL AND
      octet_length(NEW.observed_principal_arn) NOT BETWEEN 20 AND 700)
  OR NEW.expected_principal_arn<>(CASE NEW.probe_type
      WHEN 'readiness' THEN NEW.readiness_role_arn
      WHEN 'runtime_immutability' THEN NEW.runtime_role_arn
      WHEN 'negative_access' THEN NEW.negative_role_arn
      ELSE NULL
     END)
 THEN
  RAISE EXCEPTION 'artifact provider probe result is invalid' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER artifact_provider_probe_result_immutable
 BEFORE INSERT OR UPDATE OR DELETE ON public.artifact_provider_probe_results
 FOR EACH ROW EXECUTE FUNCTION public.guard_artifact_provider_probe_result();
CREATE TRIGGER artifact_provider_probe_result_no_truncate
 BEFORE TRUNCATE ON public.artifact_provider_probe_results
 FOR EACH STATEMENT EXECUTE FUNCTION public.guard_artifact_provider_probe_result();

CREATE FUNCTION public.guard_artifact_provider_activation() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE readiness public.artifact_provider_probe_results%ROWTYPE;
 runtime public.artifact_provider_probe_results%ROWTYPE;
 negative public.artifact_provider_probe_results%ROWTYPE;
 predecessor public.artifact_provider_activations%ROWTYPE;
BEGIN
 IF TG_OP<>'INSERT' THEN
  RAISE EXCEPTION 'artifact provider activations are immutable' USING ERRCODE='55000';
 END IF;
 SELECT * INTO readiness FROM public.artifact_provider_probe_results
  WHERE id=NEW.readiness_result_id FOR SHARE;
 SELECT * INTO runtime FROM public.artifact_provider_probe_results
  WHERE id=NEW.runtime_result_id FOR SHARE;
 SELECT * INTO negative FROM public.artifact_provider_probe_results
  WHERE id=NEW.negative_result_id FOR SHARE;
 IF NEW.supersedes_activation_id IS NOT NULL THEN
  SELECT * INTO predecessor FROM public.artifact_provider_activations
   WHERE id=NEW.supersedes_activation_id FOR SHARE;
 END IF;
 IF readiness.id IS NULL OR runtime.id IS NULL OR negative.id IS NULL
  OR readiness.probe_type<>'readiness'
  OR runtime.probe_type<>'runtime_immutability'
  OR negative.probe_type<>'negative_access'
  OR readiness.result<>'pass' OR runtime.result<>'pass' OR negative.result<>'pass'
  OR readiness.expected_principal_arn<>readiness.observed_principal_arn
  OR runtime.expected_principal_arn<>runtime.observed_principal_arn
  OR negative.expected_principal_arn<>negative.observed_principal_arn
  OR runtime.completed_at>readiness.started_at
  OR runtime.completed_at>negative.started_at
  OR ROW(readiness.proof_version,readiness.release_id,readiness.namespace_fingerprint,
         readiness.aws_partition,readiness.aws_account_id,readiness.region,
         readiness.runtime_role_arn,readiness.runtime_trust_policy_sha256,
         readiness.runtime_policy_arn,
         readiness.readiness_role_arn,readiness.readiness_trust_policy_sha256,
         readiness.readiness_policy_arn,
         readiness.negative_role_arn,readiness.negative_trust_policy_sha256,
         readiness.bootstrap_principal_arn,
         readiness.bucket_policy_sha256,readiness.group_nonce)
     IS DISTINCT FROM
     ROW(runtime.proof_version,runtime.release_id,runtime.namespace_fingerprint,
         runtime.aws_partition,runtime.aws_account_id,runtime.region,
         runtime.runtime_role_arn,runtime.runtime_trust_policy_sha256,
         runtime.runtime_policy_arn,
         runtime.readiness_role_arn,runtime.readiness_trust_policy_sha256,
         runtime.readiness_policy_arn,
         runtime.negative_role_arn,runtime.negative_trust_policy_sha256,
         runtime.bootstrap_principal_arn,
         runtime.bucket_policy_sha256,runtime.group_nonce)
  OR ROW(readiness.proof_version,readiness.release_id,readiness.namespace_fingerprint,
         readiness.aws_partition,readiness.aws_account_id,readiness.region,
         readiness.runtime_role_arn,readiness.runtime_trust_policy_sha256,
         readiness.runtime_policy_arn,
         readiness.readiness_role_arn,readiness.readiness_trust_policy_sha256,
         readiness.readiness_policy_arn,
         readiness.negative_role_arn,readiness.negative_trust_policy_sha256,
         readiness.bootstrap_principal_arn,
         readiness.bucket_policy_sha256,readiness.group_nonce)
     IS DISTINCT FROM
     ROW(negative.proof_version,negative.release_id,negative.namespace_fingerprint,
         negative.aws_partition,negative.aws_account_id,negative.region,
         negative.runtime_role_arn,negative.runtime_trust_policy_sha256,
         negative.runtime_policy_arn,
         negative.readiness_role_arn,negative.readiness_trust_policy_sha256,
         negative.readiness_policy_arn,
         negative.negative_role_arn,negative.negative_trust_policy_sha256,
         negative.bootstrap_principal_arn,
         negative.bucket_policy_sha256,negative.group_nonce)
  OR ROW(NEW.proof_version,NEW.release_id,NEW.namespace_fingerprint,
         NEW.aws_partition,NEW.aws_account_id,NEW.region,
         NEW.runtime_role_arn,NEW.runtime_trust_policy_sha256,NEW.runtime_policy_arn,
         NEW.readiness_role_arn,NEW.readiness_trust_policy_sha256,
         NEW.readiness_policy_arn,
         NEW.negative_role_arn,NEW.negative_trust_policy_sha256,
         NEW.bootstrap_principal_arn,
         NEW.bucket_policy_sha256,NEW.group_nonce)
     IS DISTINCT FROM
     ROW(readiness.proof_version,readiness.release_id,readiness.namespace_fingerprint,
         readiness.aws_partition,readiness.aws_account_id,readiness.region,
         readiness.runtime_role_arn,readiness.runtime_trust_policy_sha256,
         readiness.runtime_policy_arn,
         readiness.readiness_role_arn,readiness.readiness_trust_policy_sha256,
         readiness.readiness_policy_arn,
         readiness.negative_role_arn,readiness.negative_trust_policy_sha256,
         readiness.bootstrap_principal_arn,
         readiness.bucket_policy_sha256,readiness.group_nonce)
  OR NEW.activated_at>clock_timestamp()
  OR NEW.expires_at<>least(readiness.expires_at,runtime.expires_at,negative.expires_at)
  OR NEW.expires_at<=clock_timestamp()
  OR (NEW.supersedes_activation_id IS NOT NULL AND (
      predecessor.id IS NULL
      OR predecessor.activated_at>=NEW.activated_at
      OR ROW(predecessor.proof_version,predecessor.release_id,
             predecessor.namespace_fingerprint,predecessor.aws_partition,
             predecessor.aws_account_id,predecessor.region,
             predecessor.runtime_role_arn,predecessor.runtime_trust_policy_sha256,
             predecessor.runtime_policy_arn,
             predecessor.readiness_role_arn,predecessor.readiness_trust_policy_sha256,
             predecessor.readiness_policy_arn,
             predecessor.negative_role_arn,predecessor.negative_trust_policy_sha256,
             predecessor.bootstrap_principal_arn,
             predecessor.bucket_policy_sha256)
         IS DISTINCT FROM
         ROW(NEW.proof_version,NEW.release_id,
             NEW.namespace_fingerprint,NEW.aws_partition,
             NEW.aws_account_id,NEW.region,
             NEW.runtime_role_arn,NEW.runtime_trust_policy_sha256,
             NEW.runtime_policy_arn,
             NEW.readiness_role_arn,NEW.readiness_trust_policy_sha256,
             NEW.readiness_policy_arn,
             NEW.negative_role_arn,NEW.negative_trust_policy_sha256,
             NEW.bootstrap_principal_arn,
             NEW.bucket_policy_sha256)))
 THEN
  RAISE EXCEPTION 'artifact provider activation proof group is invalid' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER artifact_provider_activation_immutable
 BEFORE INSERT OR UPDATE OR DELETE ON public.artifact_provider_activations
 FOR EACH ROW EXECUTE FUNCTION public.guard_artifact_provider_activation();
CREATE TRIGGER artifact_provider_activation_no_truncate
 BEFORE TRUNCATE ON public.artifact_provider_activations
 FOR EACH STATEMENT EXECUTE FUNCTION public.guard_artifact_provider_activation();
"""
