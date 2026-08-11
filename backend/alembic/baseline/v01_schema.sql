
CREATE FUNCTION public.authority_event_facts_are_safe(event_name text, before_state json, after_state json, envelope_project_id text) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    AS $$
        begin
          if not (event_name='AuthorityInvalidationRequested'
                  and before_state is not null
                  and after_state is not null
                  and coalesce(before_state::jsonb ? 'future_obligation', false)
                  and coalesce(after_state::jsonb ? 'future_obligation', false))
             and ((before_state is not null and not authority_facts_are_safe(before_state))
               or (after_state is not null and not authority_facts_are_safe(after_state))) then
            return false;
          end if;
          case event_name
            when 'ActorProfileProvisioned' then return before_state is null and after_state::jsonb =
              '{"status":"active","subject_kind":"human","provisioning_method":"automatic_first_access"}'::jsonb;
            when 'ServiceActorProvisioned' then return before_state is null and after_state::jsonb =
              '{"status":"active","subject_kind":"service","provisioning_method":"manual_service_provisioning"}'::jsonb;
            when 'ActorIdentityLinked' then return before_state is null and after_state::jsonb in (
              '{"status":"active","subject_kind":"human"}'::jsonb,
              '{"status":"active","subject_kind":"service"}'::jsonb);
            when 'ActorIdentityLinkRevoked' then return before_state::jsonb='{"status":"active"}'::jsonb and after_state::jsonb='{"status":"revoked"}'::jsonb;
            when 'ActorIdentityLinkReactivated' then return before_state::jsonb='{"status":"revoked"}'::jsonb and after_state::jsonb='{"status":"active"}'::jsonb;
            when 'ActorProfileSuspended' then return before_state::jsonb='{"status":"active"}'::jsonb and after_state::jsonb='{"status":"suspended"}'::jsonb;
            when 'ActorProfileReactivated' then return before_state::jsonb='{"status":"suspended"}'::jsonb and after_state::jsonb='{"status":"active"}'::jsonb;
            when 'ActorProfileDeactivated' then return before_state::jsonb in ('{"status":"active"}'::jsonb,'{"status":"suspended"}'::jsonb) and after_state::jsonb='{"status":"deactivated"}'::jsonb;
            when 'InitialAccessAdministratorBootstrapped' then return before_state is null and authority_grant_facts_are_safe(after_state,array['access_administrator'],'active',true,null);
            when 'AdminRoleGrantIssued' then return before_state is null and authority_grant_facts_are_safe(after_state,array['access_administrator','operator','project_manager','finance_authority','audit_authority'],'active',true,envelope_project_id);
            when 'ProjectRoleGrantIssued' then return before_state is null and authority_grant_facts_are_safe(after_state,array['submitter','reviewer','adjudicator'],'active',true,envelope_project_id);
            when 'AdminRoleGrantRevoked','ProjectRoleGrantRevoked' then
              return authority_grant_facts_are_safe(before_state,
                case when event_name='AdminRoleGrantRevoked' then array['access_administrator','operator','project_manager','finance_authority','audit_authority'] else array['submitter','reviewer','adjudicator'] end,
                'active',true,envelope_project_id)
                and authority_grant_facts_are_safe(after_state,
                case when event_name='AdminRoleGrantRevoked' then array['access_administrator','operator','project_manager','finance_authority','audit_authority'] else array['submitter','reviewer','adjudicator'] end,
                'revoked',false,envelope_project_id)
                and before_state->>'role'=after_state->>'role'
                and before_state->>'scope_type'=after_state->>'scope_type'
                and coalesce(before_state->>'scope_id','')=coalesce(after_state->>'scope_id','');
            when 'ProjectRoleQualificationSnapshotCaptured' then return before_state is null and after_state::jsonb='{"status":"captured"}'::jsonb;
            when 'AdminRoleGrantIssueDenied','LastAccessAdministratorOperationDenied' then return before_state is null and after_state is null;
            when 'SensitiveAuthorizationAllowed' then
              return before_state is null and (
                after_state::jsonb = '{"allowed": true}'::jsonb or (
                  after_state::jsonb->'allowed' = 'true'::jsonb
                  and after_state::jsonb ? 'resource_context_digest'
                  and (select count(*) from json_each(after_state)) = 2
                )
              );
            when 'SensitiveAuthorizationDenied' then
              return before_state is null and (
                after_state::jsonb = '{"allowed": false}'::jsonb or (
                  after_state::jsonb->'allowed' = 'false'::jsonb
                  and after_state::jsonb ? 'resource_context_digest'
                  and (select count(*) from json_each(after_state)) = 2
                )
              );
            when 'AuthorityInvalidationRequested' then return
              (before_state::jsonb = '{"effective": true}'::jsonb
                and after_state::jsonb = '{"effective": false}'::jsonb)
              or (before_state::jsonb = '{"effective": false}'::jsonb
                and after_state::jsonb = '{"effective": true}'::jsonb)
              or (
                jsonb_typeof(before_state::jsonb)='object'
                and jsonb_typeof(after_state::jsonb)='object'
                and (select count(*) from jsonb_object_keys(before_state::jsonb))=5
                and (select count(*) from jsonb_object_keys(after_state::jsonb))=5
                and before_state::jsonb ?& array['effective','role','scope_type','scope_id','future_obligation']
                and after_state::jsonb ?& array['effective','role','scope_type','scope_id','future_obligation']
                and before_state::jsonb->'effective'='true'::jsonb
                and after_state::jsonb->'effective'='false'::jsonb
                and jsonb_typeof(before_state::jsonb->'role')='string'
                and jsonb_typeof(before_state::jsonb->'scope_type')='string'
                and jsonb_typeof(before_state::jsonb->'scope_id')='string'
                and jsonb_typeof(before_state::jsonb->'future_obligation')='string'
                and (before_state::jsonb - 'effective')=(after_state::jsonb - 'effective')
                and before_state::jsonb->>'scope_type'='project'
                and before_state::jsonb->>'scope_id'=envelope_project_id
                and ((before_state::jsonb->>'role'='submitter' and before_state::jsonb->>'future_obligation'='auth13_assignment')
                  or (before_state::jsonb->>'role'='reviewer' and before_state::jsonb->>'future_obligation'='rev_reviewer_obligation')
                  or (before_state::jsonb->>'role'='adjudicator' and before_state::jsonb->>'future_obligation'='none'))
              );
            else return false;
          end case;
        end $$;
CREATE FUNCTION public.authority_facts_are_safe(facts json) RETURNS boolean
    LANGUAGE sql IMMUTABLE STRICT
    AS $_$
          select json_typeof(facts) = 'object'
            and (select count(*) = count(distinct key) and count(*) <= 8 from json_each(facts))
            and not exists (
              select 1 from json_each(facts) item
              where item.key not in (
                'status', 'subject_kind', 'provisioning_method', 'role',
                'scope_type', 'scope_id', 'effective', 'allowed',
                'resource_context_digest'
              )
              or case item.key
                when 'status' then item.value #>> '{}' not in (
                  'active', 'suspended', 'deactivated', 'revoked', 'captured'
                )
                when 'subject_kind' then item.value #>> '{}' not in ('human', 'service')
                when 'provisioning_method' then item.value #>> '{}' not in (
                  'automatic_first_access', 'manual_service_provisioning'
                )
                when 'role' then item.value #>> '{}' not in (
                  'access_administrator', 'operator', 'project_manager',
                  'finance_authority', 'audit_authority', 'submitter', 'reviewer', 'both'
                )
                when 'scope_type' then item.value #>> '{}' not in ('system', 'project')
                when 'scope_id' then (item.value #>> '{}') !~
                  '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                when 'effective' then json_typeof(item.value) <> 'boolean'
                when 'allowed' then json_typeof(item.value) <> 'boolean'
                when 'resource_context_digest' then (item.value #>> '{}') !~
                  '^sha256:[0-9a-f]{64}$'
                else true
              end
            )
        $_$;
CREATE FUNCTION public.authority_grant_facts_are_safe(facts json, roles text[], expected_status text, expected_effective boolean, envelope_project_id text) RETURNS boolean
    LANGUAGE sql IMMUTABLE
    AS $$
          select authority_facts_are_safe(facts)
            and facts->>'role' = any(roles)
            and facts->>'status' = expected_status
            and (facts->>'effective')::boolean = expected_effective
            and (
              (
                facts->>'scope_type' = 'system'
                and envelope_project_id is null
                and not facts::jsonb ? 'scope_id'
                and facts->>'role' not in ('submitter', 'reviewer', 'both')
                and (select count(*) from json_each(facts)) = 4
              ) or (
                facts->>'scope_type' = 'project'
                and envelope_project_id is not null
                and facts->>'scope_id' = envelope_project_id
                and facts->>'role' not in ('access_administrator', 'operator')
                and (select count(*) from json_each(facts)) = 5
              )
            )
        $$;
CREATE FUNCTION public.enforce_compensation_binding_lifecycle() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'compensation_binding_updates_deferred';
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_actor_identity_link_history() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op='DELETE' then raise exception 'actor identity links are immutable history' using errcode='55000'; end if;
          if (new.id,new.actor_profile_id,new.issuer,new.subject,new.subject_kind,new.linked_by,new.linked_at)
             is distinct from (old.id,old.actor_profile_id,old.issuer,old.subject,old.subject_kind,old.linked_by,old.linked_at) then
            raise exception 'actor identity link anchor is immutable' using errcode='55000';
          end if;
          if new.status=old.status and
             (new.revoked_by,new.revoked_at,new.revoked_reason,new.reactivated_by,new.reactivated_at,new.reactivation_reason)
             is distinct from
             (old.revoked_by,old.revoked_at,old.revoked_reason,old.reactivated_by,old.reactivated_at,old.reactivation_reason) then
            raise exception 'identity link attribution requires a transition' using errcode='23514';
          end if;
          if old.status='active' and new.status='revoked' and
             (new.reactivated_by,new.reactivated_at,new.reactivation_reason) is distinct from
             (old.reactivated_by,old.reactivated_at,old.reactivation_reason) then
            raise exception 'invalid identity link revocation attribution' using errcode='23514';
          end if;
          if old.status='revoked' and new.status='active' and
             ((new.revoked_by,new.revoked_at,new.revoked_reason) is distinct from (null,null,null)
              or (new.reactivated_by,new.reactivated_at,new.reactivation_reason) is not distinct from (null,null,null)
              or (new.reactivated_by,new.reactivated_at,new.reactivation_reason) is not distinct from
                 (old.reactivated_by,old.reactivated_at,old.reactivation_reason)) then
            raise exception 'invalid identity link reactivation attribution' using errcode='23514';
          end if;
          if new.status <> old.status and not (
             (old.status='active' and new.status='revoked') or
             (old.status='revoked' and new.status='active')) then
            raise exception 'invalid identity link lifecycle transition' using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_actor_profile_history() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op='DELETE' then raise exception 'actor profiles are immutable history' using errcode='55000'; end if;
          if (new.id,new.actor_kind,new.provisioning_method,new.created_by,new.created_at)
             is distinct from (old.id,old.actor_kind,old.provisioning_method,old.created_by,old.created_at) then
            raise exception 'actor profile identity is immutable' using errcode='55000';
          end if;
          if old.status='deactivated' and new.status <> 'deactivated' then
            raise exception 'deactivated actor is terminal' using errcode='23514';
          end if;
          if new.status = old.status and
             (new.suspended_by,new.suspended_at,new.suspension_reason,new.reactivated_by,new.reactivated_at,new.reactivation_reason,
              new.deactivated_by,new.deactivated_at,new.deactivation_reason) is distinct from
             (old.suspended_by,old.suspended_at,old.suspension_reason,old.reactivated_by,old.reactivated_at,old.reactivation_reason,
              old.deactivated_by,old.deactivated_at,old.deactivation_reason) then
            raise exception 'actor lifecycle attribution requires a transition' using errcode='23514';
          end if;
          if old.status='active' and new.status='suspended' and
             (new.reactivated_by,new.reactivated_at,new.reactivation_reason,new.deactivated_by,new.deactivated_at,new.deactivation_reason)
             is distinct from
             (old.reactivated_by,old.reactivated_at,old.reactivation_reason,old.deactivated_by,old.deactivated_at,old.deactivation_reason) then
            raise exception 'invalid actor suspension attribution' using errcode='23514';
          end if;
          if old.status='suspended' and new.status='active' and
             ((new.suspended_by,new.suspended_at,new.suspension_reason) is distinct from (null,null,null)
              or (new.reactivated_by,new.reactivated_at,new.reactivation_reason) is not distinct from (null,null,null)
              or (new.reactivated_by,new.reactivated_at,new.reactivation_reason) is not distinct from
                 (old.reactivated_by,old.reactivated_at,old.reactivation_reason)
              or (new.deactivated_by,new.deactivated_at,new.deactivation_reason) is distinct from
                 (old.deactivated_by,old.deactivated_at,old.deactivation_reason)) then
            raise exception 'invalid actor reactivation attribution' using errcode='23514';
          end if;
          if new.status='deactivated' and old.status in ('active','suspended') and
             (new.suspended_by,new.suspended_at,new.suspension_reason,new.reactivated_by,new.reactivated_at,new.reactivation_reason)
             is distinct from
             (old.suspended_by,old.suspended_at,old.suspension_reason,old.reactivated_by,old.reactivated_at,old.reactivation_reason) then
            raise exception 'invalid actor deactivation attribution' using errcode='23514';
          end if;
          if new.status <> old.status and not (
             (old.status='active' and new.status in ('suspended','deactivated')) or
             (old.status='suspended' and new.status in ('active','deactivated'))) then
            raise exception 'invalid actor lifecycle transition' using errcode='23514';
          end if;
          new.updated_at = statement_timestamp(); return new;
        end $$;
CREATE FUNCTION public.guard_admin_role_grant() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare target_kind text; authorizer admin_role_grants%rowtype;
                bootstrap_done boolean;
        begin
          if tg_op='DELETE' then raise exception 'admin role grants are immutable' using errcode='55000'; end if;
          if tg_op='INSERT' then
            select actor_kind into target_kind from actor_profiles where id=new.target_actor_profile_id;
            if target_kind is distinct from 'human' then raise exception 'admin role target must be human' using errcode='23514'; end if;
            new.granted_at := clock_timestamp();
            if new.granted_by_system_principal is not null then
              if new.role <> 'access_administrator' or new.scope_type <> 'system' then raise exception 'invalid bootstrap grant' using errcode='23514'; end if;
              select bootstrap_completed into bootstrap_done from authority_control where id=1 for update;
              if bootstrap_done is distinct from false
                 or exists(select 1 from admin_role_grants where granted_by_system_principal='workstream:system:bootstrap') then
                raise exception 'bootstrap already completed' using errcode='23514';
              end if;
            else
              select * into authorizer from admin_role_grants where id=new.granted_by_admin_role_grant_id;
              if not found or authorizer.target_actor_profile_id <> new.granted_by_actor_profile_id
                 or authorizer.role <> 'access_administrator' or authorizer.scope_type <> 'system'
                 or authorizer.status <> 'active' then raise exception 'invalid admin grant attribution' using errcode='23514'; end if;
            end if;
            return new;
          end if;
          if old.status <> 'active' or old.version <> 1 or new.status <> 'revoked' or new.version <> 2
             or (new.id,new.target_actor_profile_id,new.role,new.scope_type,new.scope_project_id,
                 new.granted_by_actor_profile_id,new.granted_by_system_principal,
                 new.granted_by_admin_role_grant_id,new.grant_reason,new.granted_at)
                is distinct from
                (old.id,old.target_actor_profile_id,old.role,old.scope_type,old.scope_project_id,
                 old.granted_by_actor_profile_id,old.granted_by_system_principal,
                 old.granted_by_admin_role_grant_id,old.grant_reason,old.granted_at) then
            raise exception 'invalid admin role grant transition' using errcode='23514';
          end if;
          select * into authorizer from admin_role_grants where id=new.revoked_by_admin_role_grant_id;
          if not found or authorizer.target_actor_profile_id <> new.revoked_by_actor_profile_id
             or authorizer.role <> 'access_administrator' or authorizer.scope_type <> 'system'
             or authorizer.status <> 'active' then raise exception 'invalid admin revoke attribution' using errcode='23514'; end if;
          new.revoked_at := clock_timestamp(); return new;
        end $$;
CREATE FUNCTION public.guard_artifact_receipt_producer_reference() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare request_type text;
        begin
          select producer_request_type into request_type
          from artifact_put_attempts where id = new.put_attempt_id;
          if request_type is null
             or (request_type = 'guide' and not (
                 new.guide_source_item_id is not null and new.checker_run_id is null
                 and new.logical_role is null))
             or (request_type = 'checker_output' and not (
                 new.guide_source_item_id is null and new.checker_run_id is not null
                 and octet_length(new.logical_role) between 1 and 100))
             or (request_type = 'submission_bundle' and not (
                 new.guide_source_item_id is null and new.checker_run_id is null
                 and new.logical_role is null))
          then
            raise exception 'artifact receipt producer reference mismatch'
              using errcode='23514';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_authority_control() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op in ('INSERT','DELETE') then raise exception 'authority control is immutable' using errcode='55000'; end if;
          if old.id <> 1 or old.bootstrap_completed or old.version <> 0
             or new.id <> 1 or not new.bootstrap_completed or new.version <> 1
             or new.bootstrap_grant_id is null or new.created_at is distinct from old.created_at then
            raise exception 'invalid authority control transition' using errcode='23514';
          end if;
          new.updated_at := clock_timestamp(); return new;
        end $$;
CREATE FUNCTION public.guard_authority_idempotency_record() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
declare success_count integer; invalidation_count integer; success_id text;
        qualification_row audit_events%rowtype; success_row audit_events%rowtype;
        grant_row project_role_grants%rowtype;
        snapshot_row project_role_qualification_snapshots%rowtype;
begin
  if tg_op = 'INSERT' then
    if new.status <> 'pending' then raise exception 'idempotency must begin pending' using errcode='23514'; end if;
    new.created_at := statement_timestamp(); new.committed_at := null; return new;
  elsif tg_op = 'DELETE' then
    raise exception 'authority idempotency records are immutable' using errcode='55000';
  end if;
  if old.status <> 'pending' or new.status <> 'committed'
     or (new.id,new.idempotency_key,new.actor_ref_kind,new.actor_ref,new.operation,
         new.request_digest,new.created_at) is distinct from
        (old.id,old.idempotency_key,old.actor_ref_kind,old.actor_ref,old.operation,
         old.request_digest,old.created_at) then
    raise exception 'invalid authority idempotency transition' using errcode='23514';
  end if;
  select count(*), min(id) into success_count, success_id from audit_events
  where event_domain='authority' and idempotency_reference=new.id
    and event_type <> 'AuthorityInvalidationRequested';
  select count(*) into invalidation_count from audit_events
  where event_domain='authority' and idempotency_reference=new.id
    and event_type='AuthorityInvalidationRequested';
  if new.operation='project_role_grant.issue' then
    if success_count <> 2 or invalidation_count <> 0
       or (select count(*) from audit_events where idempotency_reference=new.id
             and event_type='ProjectRoleQualificationSnapshotCaptured') <> 1
       or (select count(*) from audit_events where idempotency_reference=new.id
             and event_type='ProjectRoleGrantIssued') <> 1 then
      raise exception 'project role issue evidence pair required' using errcode='23514';
    end if;
    select * into qualification_row from audit_events where idempotency_reference=new.id
      and event_type='ProjectRoleQualificationSnapshotCaptured';
    select * into success_row from audit_events where idempotency_reference=new.id
      and event_type='ProjectRoleGrantIssued';
    select * into grant_row from project_role_grants where id=success_row.resource_id::uuid;
    select * into snapshot_row from project_role_qualification_snapshots
      where id=qualification_row.resource_id::uuid;
    if not found or grant_row.id is null or snapshot_row.id is null
       or grant_row.qualification_snapshot_id <> snapshot_row.id
       or grant_row.project_id <> snapshot_row.project_id
       or grant_row.actor_profile_id <> snapshot_row.actor_profile_id
       or grant_row.role <> snapshot_row.requested_role
       or qualification_row.project_id is distinct from grant_row.project_id
       or success_row.project_id is distinct from grant_row.project_id
       or qualification_row.target_actor_ref is distinct from grant_row.actor_profile_id
       or success_row.target_actor_ref is distinct from grant_row.actor_profile_id
       or qualification_row.request_id is distinct from success_row.request_id
       or qualification_row.correlation_id is distinct from success_row.correlation_id
       or qualification_row.actor_ref_kind is distinct from success_row.actor_ref_kind
       or qualification_row.actor_id is distinct from success_row.actor_id
       or qualification_row.permission_id is distinct from success_row.permission_id
       or qualification_row.matched_grant_id is distinct from success_row.matched_grant_id then
      raise exception 'project role issue evidence mismatch' using errcode='23514';
    end if;
  else
    if success_count <> 1 or invalidation_count <> 1 then
      raise exception 'authority evidence pair required' using errcode='23514';
    end if;
    select * into success_row from audit_events where id=success_id;
  end if;
  if success_row.resource_type <> new.response_resource_type
     or success_row.resource_id <> new.response_resource_id::text then
    raise exception 'authority response does not match evidence' using errcode='23514';
  end if;
  new.committed_at := statement_timestamp(); return new;
end $$;
CREATE FUNCTION public.guard_contribution_policy_children() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare old_parent_status text;
        declare new_parent_status text;
        begin
          if tg_op in ('UPDATE','DELETE') then
            select status into old_parent_status from contribution_policy_versions
            where id=old.contribution_policy_version_id for update;
          end if;
          if tg_op in ('INSERT','UPDATE') then
            select status into new_parent_status from contribution_policy_versions
            where id=new.contribution_policy_version_id for update;
          end if;
          if old_parent_status in ('published','retired')
             or new_parent_status in ('published','retired') then
            raise exception 'published contribution policy rules and definitions are immutable'
              using errcode='55000';
          end if;
          return case when tg_op='DELETE' then old else new end;
        end;
        $$;
CREATE FUNCTION public.guard_contribution_policy_version_content() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op='DELETE' and old.status in ('published','retired') then
            raise exception 'published contribution policy versions are immutable'
              using errcode='55000';
          end if;
          if tg_op='UPDATE' and old.status='retired' then
            raise exception 'retired contribution policy versions are immutable'
              using errcode='55000';
          end if;
          if tg_op='UPDATE' and old.status='published' and not (
            new.status='retired'
            and new.id=old.id
            and new.contribution_policy_id=old.contribution_policy_id
            and new.project_id=old.project_id
            and new.version_number=old.version_number
            and new.created_by=old.created_by
            and new.created_at=old.created_at
            and new.published_by=old.published_by
            and new.published_at=old.published_at
            and new.retired_by is not null
            and new.retired_at is not null
          ) then
            raise exception 'published contribution policy version content is immutable'
              using errcode='55000';
          end if;
          return case when tg_op='DELETE' then old else new end;
        end;
        $$;
CREATE FUNCTION public.guard_guide_lineage_and_lifecycle() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          if (new.id,new.project_id,new.version)
             is distinct from (old.id,old.project_id,old.version) then
            raise exception 'guide identity and lineage are immutable' using errcode='23514';
          end if;
          if (new.status,new.approved_by,new.effective_at,new.superseded_at)
             is distinct from (old.status,old.approved_by,old.effective_at,old.superseded_at) then
            raise exception 'guide lifecycle mutation requires activation authority'
              using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_guide_mutation_idempotency() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          if tg_op='INSERT' then
            if new.status<>'pending' then raise exception 'guide mutation must begin pending' using errcode='23514'; end if;
            return new;
          elsif tg_op='DELETE' then
            raise exception 'guide mutation custody is immutable' using errcode='55000';
          end if;
          if new is not distinct from old then return new; end if;
          if old.status<>'pending' or new.status<>'committed'
             or (new.id,new.actor_profile_id,new.identity_link_id,new.action_id,new.idempotency_key,
                 new.request_digest,new.resource_context_digest,new.operation_id,new.project_id,new.resource_id,
                 new.operation_generation,new.created_at)
                is distinct from
                (old.id,old.actor_profile_id,old.identity_link_id,old.action_id,old.idempotency_key,
                 old.request_digest,old.resource_context_digest,old.operation_id,old.project_id,old.resource_id,
                 old.operation_generation,old.created_at) then
            raise exception 'invalid guide mutation custody transition' using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_iso_4217_currency_codes() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'ISO 4217 currency-code registry is migration-owned and immutable'
            using errcode='55000';
        end;
        $$;
CREATE FUNCTION public.guard_outbox_event() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare event_time timestamptz;
        begin
          if tg_op = 'TRUNCATE' then
            raise exception 'outbox events cannot be truncated' using errcode='55000';
          elsif tg_op = 'DELETE' then
            raise exception 'outbox events cannot be deleted' using errcode='55000';
          elsif tg_op = 'INSERT' then
            event_time := statement_timestamp();
            new.producer := 'workstream';
            new.occurred_at := event_time;
            new.delivery_state := 'pending';
            new.attempt_count := 0;
            new.next_attempt_at := event_time;
            new.claim_owner := null;
            new.claim_generation := 0;
            new.claimed_at := null;
            new.claim_expires_at := null;
            new.last_attempt_at := null;
            new.last_error_code := null;
            new.finalized_at := null;
            new.archived_at := null;
            return new;
          end if;
          if (new.event_id, new.event_type, new.event_version, new.producer,
              new.aggregate_type, new.aggregate_id, new.project_id,
              new.correlation_id, new.causation_event_id, new.idempotency_key,
              new.payload, new.payload_digest, new.occurred_at)
             is distinct from
             (old.event_id, old.event_type, old.event_version, old.producer,
              old.aggregate_type, old.aggregate_id, old.project_id,
              old.correlation_id, old.causation_event_id, old.idempotency_key,
              old.payload, old.payload_digest, old.occurred_at) then
            raise exception 'outbox event envelope is immutable' using errcode='55000';
          end if;
          if new.attempt_count < old.attempt_count
             or new.claim_generation < old.claim_generation
             or new.attempt_count <> new.claim_generation then
            raise exception 'outbox counters cannot regress' using errcode='23514';
          end if;
          if old.archived_at is not null and
             (new.delivery_state, new.attempt_count, new.next_attempt_at,
              new.claim_owner, new.claim_generation, new.claimed_at,
              new.claim_expires_at, new.last_attempt_at, new.last_error_code,
              new.finalized_at, new.archived_at)
             is distinct from
             (old.delivery_state, old.attempt_count, old.next_attempt_at,
              old.claim_owner, old.claim_generation, old.claimed_at,
              old.claim_expires_at, old.last_attempt_at, old.last_error_code,
              old.finalized_at, old.archived_at) then
            raise exception 'archived outbox event is closed' using errcode='55000';
          end if;
          if old.delivery_state in ('pending', 'retryable')
             and new.delivery_state = 'claimed' then
            if new.attempt_count <> old.attempt_count + 1
               or new.claim_generation <> old.claim_generation + 1
               or new.last_error_code is distinct from old.last_error_code then
              raise exception 'outbox claim generation must increment once' using errcode='23514';
            end if;
          elsif old.delivery_state = 'claimed'
                and new.delivery_state in ('retryable','acknowledged','dead_letter','cancelled') then
            if new.attempt_count <> old.attempt_count
               or new.claim_generation <> old.claim_generation
               or new.last_attempt_at is distinct from old.last_attempt_at then
              raise exception 'outbox outcome cannot change claim generation' using errcode='23514';
            end if;
          elsif old.delivery_state = 'dead_letter'
                and new.delivery_state = 'retryable' and old.archived_at is null then
            if new.attempt_count <> old.attempt_count
               or new.claim_generation <> old.claim_generation
               or new.last_attempt_at is distinct from old.last_attempt_at
               or new.last_error_code is distinct from old.last_error_code then
              raise exception 'outbox requeue cannot change claim generation' using errcode='23514';
            end if;
          elsif old.delivery_state in ('pending','retryable')
                and new.delivery_state = 'cancelled' then
            if new.attempt_count <> old.attempt_count
               or new.claim_generation <> old.claim_generation
               or new.last_attempt_at is distinct from old.last_attempt_at
               or new.last_error_code is distinct from old.last_error_code then
              raise exception 'outbox cancellation cannot change claim generation' using errcode='23514';
            end if;
          elsif old.delivery_state in ('pending','retryable')
                and new.delivery_state = old.delivery_state then
            if (new.attempt_count, new.claim_owner, new.claim_generation,
                new.claimed_at, new.claim_expires_at, new.last_attempt_at,
                new.last_error_code, new.finalized_at, new.archived_at)
               is distinct from
               (old.attempt_count, old.claim_owner, old.claim_generation,
                old.claimed_at, old.claim_expires_at, old.last_attempt_at,
                old.last_error_code, old.finalized_at, old.archived_at) then
              raise exception 'outbox eligibility update changed unrelated state' using errcode='23514';
            end if;
          elsif old.delivery_state in ('acknowledged','dead_letter','cancelled')
                and new.delivery_state = old.delivery_state then
            if (new.attempt_count, new.next_attempt_at, new.claim_owner,
                new.claim_generation, new.claimed_at, new.claim_expires_at,
                new.last_attempt_at, new.last_error_code, new.finalized_at)
               is distinct from
               (old.attempt_count, old.next_attempt_at, old.claim_owner,
                old.claim_generation, old.claimed_at, old.claim_expires_at,
                old.last_attempt_at, old.last_error_code, old.finalized_at)
               or (old.archived_at is not null and new.archived_at is distinct from old.archived_at)
               or (old.archived_at is null and new.archived_at is null) then
              raise exception 'terminal outbox event permits archival only' using errcode='23514';
            end if;
          else
            raise exception 'illegal outbox delivery transition' using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_policy_mutation_replay() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op='INSERT' then
            if new.status<>'pending' then
              raise exception 'policy mutation must begin pending' using errcode='23514';
            end if;
            return new;
          elsif tg_op='DELETE' then
            raise exception 'policy mutation replay is immutable' using errcode='55000';
          elsif new is not distinct from old then
            return new;
          elsif old.status='pending' and new.status='committed'
             and (new.id,new.actor_profile_id,new.identity_link_id,new.action_id,
                  new.idempotency_key,new.request_digest,new.policy_hash,
                  new.resource_context_digest,
                  new.operation_id,new.project_id,new.guide_id,new.policy_id,
                  new.policy_generation,new.created_at)
                 is not distinct from
                 (old.id,old.actor_profile_id,old.identity_link_id,old.action_id,
                  old.idempotency_key,old.request_digest,old.policy_hash,
                  old.resource_context_digest,
                  old.operation_id,old.project_id,old.guide_id,old.policy_id,
                  old.policy_generation,old.created_at) then
            return new;
          end if;
          raise exception 'policy mutation replay is immutable' using errcode='23514';
        end $$;
CREATE FUNCTION public.guard_pre_submit_evidence_result_membership() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare parent_created_at timestamptz; expected_count integer; current_count integer;
        begin
          select created_at, result_count into parent_created_at, expected_count
            from pre_submit_evidence_sets where id=new.evidence_set_id for key share;
          select count(*) into current_count from pre_submit_evidence_results
            where evidence_set_id=new.evidence_set_id;
          if parent_created_at is null
             or parent_created_at <> transaction_timestamp()
             or current_count >= expected_count then
            raise exception 'pre-submit evidence result membership is closed'
              using errcode='55000';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_pre_submit_evidence_results_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'pre_submit_evidence_results rows are immutable' using errcode='55000';
        end;
        $$;
CREATE FUNCTION public.guard_pre_submit_evidence_set_creation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if new.created_at is distinct from transaction_timestamp() then
            raise exception 'pre-submit evidence creation timestamp is invalid'
              using errcode='55000';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_pre_submit_evidence_sets_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'pre_submit_evidence_sets rows are immutable' using errcode='55000';
        end;
        $$;
CREATE FUNCTION public.guard_project_compensation_units() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op in ('UPDATE','DELETE') then
            raise exception 'project compensation-unit lifecycle behavior is deferred'
              using errcode='55000';
          end if;
          if new.status <> 'active' then
            raise exception 'project compensation units must begin active'
              using errcode='23514';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_project_create_idempotency() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op = 'INSERT' then
            if new.status <> 'pending' or new.committed_at is not null then
              raise exception 'project create reservation must begin pending' using errcode='23514';
            end if;
            return new;
          elsif tg_op = 'DELETE' then
            raise exception 'project create reservations are immutable' using errcode='55000';
          end if;
          if new is not distinct from old then
            return new;
          end if;
          if old.status <> 'pending' or new.status <> 'committed'
             or (new.id, new.actor_profile_id, new.identity_link_id, new.action_id,
                 new.idempotency_key, new.request_digest, new.operation_id,
                 new.project_id, new.operation_generation, new.created_at)
                is distinct from
                (old.id, old.actor_profile_id, old.identity_link_id, old.action_id,
                 old.idempotency_key, old.request_digest, old.operation_id,
                 old.project_id, old.operation_generation, old.created_at) then
            raise exception 'invalid project create reservation transition' using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_project_guide_compilation_attempt_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if row(new.project_id,new.guide_id,new.guide_version,new.source_snapshot_id,
            new.source_snapshot_hash,new.setup_run_id,new.setup_generation,
            new.canonical_input_hash,new.guide_material_hash,new.pre_catalogue_id,
            new.pre_catalogue_version,new.pre_catalogue_schema_version,
            new.pre_catalogue_manifest_hash,new.post_catalogue_id,new.post_catalogue_version,
            new.post_catalogue_schema_version,new.post_catalogue_manifest_hash,
            new.agent_identity,new.agent_version,new.instruction_version,
            new.provider_idempotency_key)
          is distinct from row(old.project_id,old.guide_id,old.guide_version,old.source_snapshot_id,
            old.source_snapshot_hash,old.setup_run_id,old.setup_generation,
            old.canonical_input_hash,old.guide_material_hash,old.pre_catalogue_id,
            old.pre_catalogue_version,old.pre_catalogue_schema_version,
            old.pre_catalogue_manifest_hash,old.post_catalogue_id,old.post_catalogue_version,
            old.post_catalogue_schema_version,old.post_catalogue_manifest_hash,
            old.agent_identity,old.agent_version,old.instruction_version,
            old.provider_idempotency_key) then raise exception 'compilation attempt identity is immutable'; end if;
          if old.status in ('compilation_persisted','compilation_invalid_terminal') then raise exception 'terminal compilation attempt is immutable'; end if;
          if new.reserved_at is distinct from old.reserved_at then
            raise exception 'compilation reservation timestamp is immutable';
          end if;
          if new.provider_uncertain_at is distinct from old.provider_uncertain_at and
            not (old.status='compilation_reserved' and new.status='compilation_provider_uncertain') then
            raise exception 'provider uncertainty timestamp is immutable';
          end if;
          if new.accepted_at is distinct from old.accepted_at and
            not (old.status in ('compilation_reserved','compilation_provider_uncertain') and new.status='provider_result_accepted') then
            raise exception 'accepted timestamp is immutable';
          end if;
          if new.terminal_at is distinct from old.terminal_at and
            not (old.status in ('compilation_reserved','compilation_provider_uncertain') and new.status='compilation_invalid_terminal') then
            raise exception 'terminal timestamp is immutable';
          end if;
          if row(new.persisted_at,new.persisted_compilation_id) is distinct from
            row(old.persisted_at,old.persisted_compilation_id) and
            not (old.status='provider_result_accepted' and new.status='compilation_persisted') then
            raise exception 'persisted custody is immutable';
          end if;
          if old.status='provider_result_accepted' and row(new.canonical_result::jsonb,new.result_hash,new.component_hashes::jsonb,new.accepted_at)
            is distinct from row(old.canonical_result::jsonb,old.result_hash,old.component_hashes::jsonb,old.accepted_at) then
            raise exception 'accepted compilation result is immutable';
          end if;
          if not ((old.status='compilation_reserved' and new.status in ('compilation_provider_uncertain','provider_result_accepted','compilation_invalid_terminal')) or
                  (old.status='compilation_provider_uncertain' and new.status in ('provider_result_accepted','compilation_invalid_terminal')) or
                  (old.status='provider_result_accepted' and new.status='compilation_persisted')) then
            raise exception 'invalid compilation attempt transition';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_project_guide_compilation_insert() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare predecessor_generation bigint;
        declare source_attempt project_guide_compilation_attempts%rowtype;
        begin
          select * into source_attempt from project_guide_compilation_attempts
            where id=new.attempt_id for update;
          if source_attempt.id is null or source_attempt.status <> 'provider_result_accepted' or
            row(new.project_id,new.guide_id,new.guide_version,new.source_snapshot_id,
              new.source_snapshot_hash,new.setup_run_id,new.setup_generation,
              new.canonical_input_hash,new.guide_material_hash,
              new.pre_catalogue_manifest_hash,new.post_catalogue_manifest_hash,
              new.agent_identity,new.agent_version,new.instruction_version,
              new.canonical_result::jsonb,new.result_hash,new.component_hashes::jsonb)
            is distinct from
            row(source_attempt.project_id,source_attempt.guide_id,
              source_attempt.guide_version,source_attempt.source_snapshot_id,
              source_attempt.source_snapshot_hash,source_attempt.setup_run_id,
              source_attempt.setup_generation,source_attempt.canonical_input_hash,
              source_attempt.guide_material_hash,source_attempt.pre_catalogue_manifest_hash,
              source_attempt.post_catalogue_manifest_hash,source_attempt.agent_identity,
              source_attempt.agent_version,source_attempt.instruction_version,
              source_attempt.canonical_result::jsonb,source_attempt.result_hash,
              source_attempt.component_hashes::jsonb) then
            raise exception 'compilation does not match its accepted attempt';
          end if;
          if not exists(
            select 1 from audit_events event
            join actor_profiles profile on profile.id=new.created_by_actor_profile_id
            join actor_identity_links link on link.id=new.created_via_identity_link_id
              and link.actor_profile_id=profile.id
            where event.id=new.authorization_decision_event_id
              and event.event_domain='authority'
              and event.event_type='SensitiveAuthorizationAllowed'
              and event.denial_code is null
              and event.actor_id=new.created_by_actor_profile_id
              and event.permission_id='project.guide_compilation.execute'
              and event.action_id='project.guide_compilation.execute'
              and event.project_id=new.project_id
              and event.resource_type='project_guide_compilation_attempt'
              and event.resource_id=new.attempt_id::text
              and event.after_facts->>'allowed'='true'
              and event.after_facts->>'resource_context_digest'=
                new.authorization_resource_context_digest
              and profile.actor_kind='service' and profile.status='active'
              and profile.service_identity='workstream.project.setup'
              and link.subject_kind='service' and link.status='active'
              and link.issuer='workstream-internal'
              and link.subject='workstream.project.setup'
          ) then
            raise exception 'compilation authorization evidence is invalid';
          end if;
          if new.supersedes_compilation_id is null then return new; end if;
          select setup_generation into predecessor_generation
            from project_guide_compilations
            where id=new.supersedes_compilation_id
              and project_id=new.project_id and guide_id=new.guide_id;
          if predecessor_generation is null or predecessor_generation >= new.setup_generation then
            raise exception 'compilation generation must strictly advance';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_project_guide_policy_selection() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          if old.status in ('active','superseded') and (
            new.selected_review_policy_id is distinct from old.selected_review_policy_id or
            new.selected_review_policy_generation is distinct from
              old.selected_review_policy_generation or
            new.selected_review_policy_hash is distinct from old.selected_review_policy_hash or
            new.selected_revision_policy_id is distinct from old.selected_revision_policy_id or
            new.selected_revision_policy_generation is distinct from
              old.selected_revision_policy_generation or
            new.selected_revision_policy_hash is distinct from old.selected_revision_policy_hash
          ) then
            raise exception 'active guide policy selection is immutable' using errcode='55000';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_project_role_grant_history() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op='INSERT' then new.granted_at := clock_timestamp(); return new; end if;
          if tg_op='DELETE' then raise exception 'project-role grants are immutable history' using errcode='55000'; end if;
          if (new.id,new.project_id,new.actor_profile_id,new.role,new.grant_method,
              new.qualification_snapshot_id,new.granted_by_actor_profile_id,
              new.granted_by_admin_role_grant_id,new.grant_reason,new.granted_at)
             is distinct from
             (old.id,old.project_id,old.actor_profile_id,old.role,old.grant_method,
              old.qualification_snapshot_id,old.granted_by_actor_profile_id,
              old.granted_by_admin_role_grant_id,old.grant_reason,old.granted_at)
             or old.status<>'active' or old.version<>1 or new.status<>'revoked' or new.version<>2
             or new.revoked_by_actor_profile_id is null or new.revoked_by_admin_role_grant_id is null
             or new.revoked_reason is null then
            raise exception 'invalid project-role grant history transition' using errcode='23514';
          end if;
          new.revoked_at := clock_timestamp();
          return new;
        end $$;
CREATE FUNCTION public.guard_project_role_snapshot_history() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op='INSERT' then new.captured_at := clock_timestamp(); return new; end if;
          raise exception 'project-role qualification snapshots are immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.guard_review_admission_record() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          task_project text;
          checker_row checker_runs%rowtype;
        begin
          if tg_op='DELETE' then
            raise exception 'review admission records cannot be deleted' using errcode='55000';
          end if;
          if tg_op='INSERT' and new.status <> 'pending' then
            raise exception 'review admission must begin pending' using errcode='23514';
          end if;
          if tg_op='INSERT' then
            new.created_at := statement_timestamp();
          end if;
          if tg_op='UPDATE' then
            if (new.id,new.idempotency_key,new.operation_id,new.request_digest,new.project_id,
                new.task_id,new.submission_id,new.submission_version,
                new.admitting_checker_run_id,new.created_at)
               is distinct from
               (old.id,old.idempotency_key,old.operation_id,old.request_digest,old.project_id,
                old.task_id,old.submission_id,old.submission_version,
                old.admitting_checker_run_id,old.created_at) then
              raise exception 'review admission identity is immutable' using errcode='55000';
            end if;
            if old.status <> 'pending' or new.status <> 'committed' then
              raise exception 'invalid review admission transition' using errcode='23514';
            end if;
          end if;
          select project_id into task_project from workstream_tasks where id=new.task_id;
          if task_project is null or task_project <> new.project_id then
            raise exception 'review admission task project mismatch' using errcode='23514';
          end if;
          select * into checker_row from checker_runs where id=new.admitting_checker_run_id;
          if not found or checker_row.task_id <> new.task_id
             or checker_row.submission_id <> new.submission_id
             or checker_row.submission_version <> new.submission_version then
            raise exception 'review admission checker lineage mismatch' using errcode='23514';
          end if;
          if new.status='committed' and (
             checker_row.status <> 'completed'
             or checker_row.routing_recommendation <> 'allow_review'
             or checker_row.is_current_for_submission is not true) then
            raise exception 'review admission checker is not admissible' using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_review_lease() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          actor_type text;
          policy_status text;
        begin
          if tg_op='DELETE' then
            raise exception 'review leases cannot be deleted' using errcode='55000';
          end if;
          if tg_op='INSERT' then
            if new.status <> 'active' then
              raise exception 'review lease must begin active' using errcode='23514';
            end if;
            new.claimed_at := statement_timestamp();
            new.closed_at := null;
            new.close_reason := null;
          else
            if old.status <> 'active' then
              raise exception 'terminal review leases are immutable' using errcode='55000';
            end if;
            if (new.id,new.review_queue_entry_id,new.project_id,new.task_id,new.submission_id,
                new.submission_version,new.reviewer_id,
                new.reviewer_contribution_policy_version_id,new.attempt_generation,
                new.claimed_at,new.expires_at)
               is distinct from
               (old.id,old.review_queue_entry_id,old.project_id,old.task_id,old.submission_id,
                old.submission_version,old.reviewer_id,
                old.reviewer_contribution_policy_version_id,old.attempt_generation,
                old.claimed_at,old.expires_at) then
              raise exception 'review lease identity is immutable' using errcode='55000';
            end if;
            if new.status='active' then
              raise exception 'review lease update must close attempt' using errcode='23514';
            end if;
          end if;
          select actor_kind into actor_type from actor_profiles where id=new.reviewer_id;
          if actor_type is distinct from 'human' then
            raise exception 'review lease reviewer must be human' using errcode='23514';
          end if;
          if tg_op='INSERT' then
            select status into policy_status from contribution_policy_versions
             where id=new.reviewer_contribution_policy_version_id and project_id=new.project_id;
            if policy_status is distinct from 'published' then
              raise exception 'review lease policy version must be published' using errcode='23514';
            end if;
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_review_policies_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'review_policies rows are immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.guard_review_queue_entry() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          task_project text;
          checker_row checker_runs%rowtype;
        begin
          if tg_op='DELETE' then
            raise exception 'review queue entries cannot be deleted' using errcode='55000';
          end if;
          if tg_op='INSERT' then
            if new.queue_state <> 'pending' then
              raise exception 'review queue must begin pending' using errcode='23514';
            end if;
            new.first_queued_at := statement_timestamp();
            new.available_since := new.first_queued_at;
            new.routing_generation := 1;
            new.lifecycle_generation := 1;
            new.created_at := new.first_queued_at;
          end if;
          if tg_op='UPDATE' then
            if (new.id,new.project_id,new.task_id,new.submission_id,new.submission_version,
                new.admitting_checker_run_id,new.first_queued_at,new.created_at)
               is distinct from
               (old.id,old.project_id,old.task_id,old.submission_id,old.submission_version,
                old.admitting_checker_run_id,old.first_queued_at,old.created_at) then
              raise exception 'review queue identity is immutable' using errcode='55000';
            end if;
            if old.queue_state='closed' and new.queue_state <> 'closed' then
              raise exception 'closed review queue entries cannot reopen' using errcode='23514';
            end if;
            if new.routing_generation < old.routing_generation
               or new.lifecycle_generation < old.lifecycle_generation then
              raise exception 'review queue generations cannot decrease' using errcode='23514';
            end if;
          end if;
          if new.preferred_reviewer_id is not null and not exists(
            select 1 from actor_profiles where id=new.preferred_reviewer_id and actor_kind='human'
          ) then
            raise exception 'preferred reviewer must be human' using errcode='23514';
          end if;
          if tg_op='UPDATE' then return new; end if;
          select project_id into task_project from workstream_tasks where id=new.task_id;
          if task_project is null or task_project <> new.project_id then
            raise exception 'review queue task project mismatch' using errcode='23514';
          end if;
          select * into checker_row from checker_runs where id=new.admitting_checker_run_id;
          if not found or checker_row.task_id <> new.task_id
             or checker_row.submission_id <> new.submission_id
             or checker_row.submission_version <> new.submission_version then
            raise exception 'review queue checker lineage mismatch' using errcode='23514';
          end if;
          if checker_row.status <> 'completed' or checker_row.routing_recommendation <> 'allow_review'
             or checker_row.is_current_for_submission is not true then
            raise exception 'review queue checker is not admissible' using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_revision_policies_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'revision_policies rows are immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.guard_service_identity_migration_evidence() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          raise exception 'service identity migration evidence is immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.guard_submission_bundle_admission_delete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin raise exception 'submission bundle admissions cannot be removed' using errcode='55000'; end; $$;
CREATE FUNCTION public.guard_submission_bundle_admission_lineage() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if row(old.durable_intent_id, old.pre_submit_evidence_set_id, old.put_attempt_id,
                 old.artifact_content_id, old.verified_replica_id, old.verification_receipt_id,
                 old.put_operation_receipt_id, old.put_observation_receipt_id,
                 old.actor_profile_id, old.identity_link_id, old.project_id, old.task_id,
                 old.assignment_id, old.predecessor_submission_id,
                 old.predecessor_submission_version,
                 old.locked_policy_context_hash,
                 old.semantic_manifest_id, old.semantic_manifest_sha256, old.archive_sha256,
                 old.archive_byte_count, old.ready_at, old.created_at)
             is distinct from
             row(new.durable_intent_id, new.pre_submit_evidence_set_id, new.put_attempt_id,
                 new.artifact_content_id, new.verified_replica_id, new.verification_receipt_id,
                 new.put_operation_receipt_id, new.put_observation_receipt_id,
                 new.actor_profile_id, new.identity_link_id, new.project_id, new.task_id,
                 new.assignment_id, new.predecessor_submission_id,
                 new.predecessor_submission_version,
                 new.locked_policy_context_hash,
                 new.semantic_manifest_id, new.semantic_manifest_sha256, new.archive_sha256,
                 new.archive_byte_count, new.ready_at, new.created_at)
          then
            raise exception 'submission bundle admission lineage is immutable' using errcode='55000';
          end if;
          if old.status <> 'ready' or new.status not in ('consumed','stale') then
            raise exception 'invalid submission bundle admission transition' using errcode='23514';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_submission_bundle_admission_verified_lineage() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare matches integer;
        begin
          select count(*) into matches
          from submission_bundle_durable_intents intent
          join pre_submit_evidence_sets evidence
            on evidence.id=intent.pre_submit_evidence_set_id
          join artifact_put_attempts attempt on attempt.id=intent.put_attempt_id
          join artifact_replicas replica on replica.id=attempt.replica_id
          join artifact_contents content on content.id=replica.content_id
          join artifact_verification_jobs job
            on job.originating_put_attempt_id=attempt.id and job.replica_id=replica.id
          join artifact_verification_receipts verification
            on verification.verification_job_id=job.id
          where intent.id=new.durable_intent_id
            and evidence.id=new.pre_submit_evidence_set_id
            and attempt.id=new.put_attempt_id
            and content.id=new.artifact_content_id
            and replica.id=new.verified_replica_id
            and verification.id=new.verification_receipt_id
            and attempt.producer_request_type='submission_bundle'
            and attempt.producer_type='actor_profile'
            and attempt.producer_ref=evidence.actor_profile_id
            and attempt.project_id=evidence.project_id
            and attempt.task_id=evidence.task_id
            and attempt.media_type='application/zip'
            and content.media_type='application/zip'
            and attempt.status='object_confirmed'
            and evidence.terminal_status='passed' and evidence.eligible
            and replica.verification_state='verified'
            and replica.availability_state='available'
            and replica.integrity_state='valid'
            and verification.outcome='verified'
            and verification.execution_generation=job.execution_generation
            and verification.observed_sha256=attempt.sha256
            and verification.observed_sha256=content.sha256
            and verification.observed_sha256=evidence.archive_sha256
            and verification.observed_byte_count=attempt.byte_count
            and verification.observed_byte_count=content.byte_count
            and verification.observed_byte_count=evidence.archive_byte_count
            and new.actor_profile_id=evidence.actor_profile_id
            and new.identity_link_id=evidence.identity_link_id
            and new.project_id=evidence.project_id and new.task_id=evidence.task_id
            and new.assignment_id=evidence.assignment_id
            and new.predecessor_submission_id is not distinct from evidence.predecessor_submission_id
            and new.predecessor_submission_version is not distinct from evidence.predecessor_submission_version
            and new.locked_policy_context_hash=evidence.locked_policy_context_hash
            and new.semantic_manifest_id=evidence.semantic_manifest_id
            and new.semantic_manifest_sha256=evidence.semantic_manifest_sha256
            and new.archive_sha256=evidence.archive_sha256
            and new.archive_byte_count=evidence.archive_byte_count
            and ((new.put_operation_receipt_id is not null and exists (
                  select 1 from artifact_operation_receipts receipt
                  where receipt.id=new.put_operation_receipt_id
                    and receipt.put_attempt_id=attempt.id and receipt.replica_id=replica.id
                    and receipt.outcome='stored_pending_verification'))
              or (new.put_observation_receipt_id is not null and exists (
                  select 1 from artifact_put_observation_receipts observation
                  where observation.id=new.put_observation_receipt_id
                    and observation.put_attempt_id=attempt.id
                    and observation.outcome='observed_confirmed'
                    and observation.observed_sha256=attempt.sha256
                    and observation.observed_byte_count=attempt.byte_count)));
          if matches <> 1 then
            raise exception 'submission bundle admission verified lineage mismatch'
              using errcode='23514';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_submission_bundle_durable_intent_put_attempt() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare request_type text;
        begin
          select producer_request_type into request_type
          from artifact_put_attempts
          where id = new.put_attempt_id
          for share;
          if request_type is distinct from 'submission_bundle' then
            raise exception 'submission bundle durable intent requires submission_bundle put attempt'
              using errcode='23514';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_submission_bundle_durable_intents_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'submission_bundle_durable_intents rows are immutable'
            using errcode='55000';
        end;
        $$;
CREATE FUNCTION public.project_role_availability_is_safe(value jsonb) RETURNS boolean
    LANGUAGE sql IMMUTABLE STRICT
    AS $$
          select jsonb_typeof(value)='object' and
            (select count(*)=3 from jsonb_object_keys(value)) and
            value ?& array['availability','reference_ids','unavailable_reason'] and
            project_role_reference_array_is_safe(value->'reference_ids',false) and (
              (value->>'availability'='available' and jsonb_array_length(value->'reference_ids')>0
                and value->'unavailable_reason'='null'::jsonb) or
              (value->>'availability'='unavailable' and jsonb_array_length(value->'reference_ids')=0
                and value->>'unavailable_reason' in ('not_collected','source_unavailable','no_record'))
            )
        $$;
CREATE FUNCTION public.project_role_reason_is_safe(value text) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE STRICT
    AS $$
        declare point integer; index integer;
        begin
          if octet_length(value) not between 1 and 500 or value <> btrim(value, (E' \t\n\r\f\013'||chr(28)||chr(29)||chr(30)||chr(31)||chr(133)||chr(160)||chr(5760)||chr(8192)||chr(8193)||chr(8194)||chr(8195)||chr(8196)||chr(8197)||chr(8198)||chr(8199)||chr(8200)||chr(8201)||chr(8202)||chr(8232)||chr(8233)||chr(8239)||chr(8287)||chr(12288))) then return false; end if;
          for index in 1..char_length(value) loop
            point := ascii(substr(value,index,1));
            if point between 0 and 31 or point between 127 and 159
               or point in (173,1536,1537,1538,1539,1757,1807,6068,6069,6070,6071,6072,6073,6158,8203,8204,8205,8206,8207,8234,8235,8236,8237,8238,8288,8289,8290,8291,8292,8293,8294,8295,8296,8297,8298,8299,8300,8301,8302,8303,65279) then
              return false;
            end if;
          end loop;
          return true;
        end $$;
CREATE FUNCTION public.project_role_reference_array_is_safe(value jsonb, uuid_only boolean) RETURNS boolean
    LANGUAGE sql IMMUTABLE STRICT
    AS $_$
          select jsonb_typeof(value)='array' and jsonb_array_length(value)<=20
            and not exists (
              select 1 from jsonb_array_elements(value) item
              where jsonb_typeof(item)<>'string' or
                case when uuid_only then not (item #>> '{}') ~
                  '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                else not project_role_reference_token_is_safe(item #>> '{}') end
            )
        $_$;
CREATE FUNCTION public.project_role_reference_token_is_safe(value text) RETURNS boolean
    LANGUAGE sql IMMUTABLE STRICT
    AS $_$
          select value ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$' and strpos(value, '://')=0
        $_$;
CREATE FUNCTION public.protect_submission_policy_approval_provenance() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if old.approval_action_id is not null and
             (new.approved_by_actor_profile_id,new.approved_via_identity_link_id,
              new.approved_by_admin_role_grant_id,new.approval_scope_type,
              new.approval_scope_project_id,new.approval_action_id,
              new.approval_decision_event_id)
             is distinct from
             (old.approved_by_actor_profile_id,old.approved_via_identity_link_id,
              old.approved_by_admin_role_grant_id,old.approval_scope_type,
              old.approval_scope_project_id,old.approval_action_id,
              old.approval_decision_event_id) then
            raise exception 'submission-policy approval provenance is immutable'
              using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.protect_submission_policy_creation_provenance() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if old.creation_action_id is not null and
             (new.created_by_actor_profile_id,new.created_via_identity_link_id,
              new.created_by_admin_role_grant_id,new.created_by_service_identity,
              new.creation_scope_type,new.creation_scope_project_id,
              new.creation_action_id,new.creation_decision_event_id)
             is distinct from
             (old.created_by_actor_profile_id,old.created_via_identity_link_id,
              old.created_by_admin_role_grant_id,old.created_by_service_identity,
              old.creation_scope_type,old.creation_scope_project_id,
              old.creation_action_id,old.creation_decision_event_id) then
            raise exception 'submission-policy creation provenance is immutable'
              using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.protect_submission_policy_output_provenance() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if old.creation_action_id is not null and
             (new.created_by_actor_profile_id,new.created_via_identity_link_id,
              new.created_by_admin_role_grant_id,new.creation_scope_type,
              new.creation_scope_project_id,new.creation_action_id,
              new.creation_decision_event_id)
             is distinct from
             (old.created_by_actor_profile_id,old.created_via_identity_link_id,
              old.created_by_admin_role_grant_id,old.creation_scope_type,
              old.creation_scope_project_id,old.creation_action_id,
              old.creation_decision_event_id) then
            raise exception 'submission-policy output provenance is immutable'
              using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.reject_admin_role_grant_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
             begin raise exception 'admin role grants are immutable' using errcode='55000'; end $$;
CREATE FUNCTION public.reject_artifact_fact_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
            raise exception '% rows are immutable', tg_table_name;
        end;
        $$;
CREATE FUNCTION public.reject_audit_event_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'audit events are append-only' using errcode = '55000';
        end
        $$;
CREATE FUNCTION public.reject_authority_control_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
             begin raise exception 'authority control is immutable' using errcode='55000'; end $$;
CREATE FUNCTION public.reject_authority_idempotency_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          raise exception 'authority idempotency records are immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.reject_contribution_policy_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'contribution policy persistence cannot be truncated'
            using errcode='55000';
        end;
        $$;
CREATE FUNCTION public.reject_guide_mutation_idempotency_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          raise exception 'guide mutation custody is immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.reject_guide_source_snapshot_item_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          raise exception 'guide source snapshot items are immutable' using errcode='23514';
        end $$;
CREATE FUNCTION public.reject_pending_authority_idempotency() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          if exists(select 1 from authority_idempotency_records where id=new.id and status='pending') then
            raise exception 'pending authority idempotency cannot commit' using errcode='23514';
          end if; return null;
        end $$;
CREATE FUNCTION public.reject_policy_mutation_replay_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          raise exception 'policy mutation replay is immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.reject_project_create_idempotency_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          raise exception 'project create reservations are immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.reject_project_guide_compilation_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin raise exception 'compilation custody is append-only'; end $$;
CREATE FUNCTION public.reject_project_role_history_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin raise exception 'project-role history cannot be truncated' using errcode='55000'; end $$;
CREATE FUNCTION public.reject_review_lease_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'review leases cannot be truncated' using errcode='55000';
        end $$;
CREATE FUNCTION public.reject_review_queue_foundation_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'review queue foundation cannot be truncated' using errcode='55000';
        end $$;
CREATE FUNCTION public.reject_submission_policy_replay_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op = 'DELETE' then
            raise exception 'submission-policy replay rows cannot be deleted';
          end if;
          if old.status = 'reserved' and new.status = 'pending'
             and old.service_identity = 'workstream.project.setup'
             and old.action_id = 'project.submission_artifact_policy.derive'
             and (new.id,new.actor_profile_id,new.identity_link_id,new.service_identity,
                  new.action_id,new.idempotency_key,new.operation_id,new.project_id,
                  new.guide_id,new.source_snapshot_id,new.policy_id,new.setup_run_id,
                  new.setup_generation,new.setup_task_id,new.correlation_id,new.created_at,
                  new.response_json::text,new.committed_policy_id,new.committed_effective_policy_id,
                  new.committed_pre_submit_policy_id,new.committed_at)
                 is not distinct from
                 (old.id,old.actor_profile_id,old.identity_link_id,old.service_identity,
                  old.action_id,old.idempotency_key,old.operation_id,old.project_id,
                  old.guide_id,old.source_snapshot_id,old.policy_id,old.setup_run_id,
                  old.setup_generation,old.setup_task_id,old.correlation_id,old.created_at,
                  old.response_json::text,old.committed_policy_id,old.committed_effective_policy_id,
                  old.committed_pre_submit_policy_id,old.committed_at)
          then
            return new;
          end if;
          if old.status <> 'pending' or new.status <> 'committed'
             or (new.id,new.actor_profile_id,new.identity_link_id,new.service_identity,
                 new.action_id,new.idempotency_key,new.request_digest,
                 new.resource_context_digest,new.resource_context_json::text,new.operation_id,
                 new.project_id,new.guide_id,new.source_snapshot_id,new.policy_id,
                 new.setup_run_id,new.setup_generation,new.setup_task_id,
                 new.correlation_id,new.created_at)
                is distinct from
                (old.id,old.actor_profile_id,old.identity_link_id,old.service_identity,
                 old.action_id,old.idempotency_key,old.request_digest,
                 old.resource_context_digest,old.resource_context_json::text,old.operation_id,
                 old.project_id,old.guide_id,old.source_snapshot_id,old.policy_id,
                 old.setup_run_id,old.setup_generation,old.setup_task_id,
                 old.correlation_id,old.created_at)
          then
            raise exception 'invalid submission-policy replay mutation';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.reject_submission_policy_replay_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          raise exception 'submission-policy replay rows cannot be truncated';
        end $$;
CREATE FUNCTION public.reject_sufficiency_replay_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op = 'DELETE' then
            raise exception 'guide sufficiency replay rows are append-only';
          end if;
          if old.status = 'committed' or new.status <> 'committed'
             or (new.id,new.actor_profile_id,new.identity_link_id,new.action_id,
                 new.idempotency_key,new.request_digest,
                 new.resource_context_digest,
                 new.operation_id,new.project_id,new.guide_id,new.source_snapshot_id,
                 new.setup_run_id,new.setup_generation,new.created_at)
                is distinct from
                (old.id,old.actor_profile_id,old.identity_link_id,old.action_id,
                 old.idempotency_key,old.request_digest,
                 old.resource_context_digest,
                 old.operation_id,old.project_id,old.guide_id,old.source_snapshot_id,
                 old.setup_run_id,old.setup_generation,old.created_at)
          then
            raise exception 'invalid guide sufficiency replay mutation';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.reject_sufficiency_replay_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'guide sufficiency replay rows are append-only';
        end $$;
CREATE FUNCTION public.require_human_actor_profile_reference() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare referenced_id text; referenced_kind text;
        begin
          if tg_nargs <> 1 or tg_argv[0] is null
             or not (to_jsonb(new) ? tg_argv[0]) then
            raise exception 'human actor reference trigger is misconfigured'
              using errcode='55000';
          end if;
          referenced_id := to_jsonb(new) ->> tg_argv[0];
          if referenced_id is null then return new; end if;
          select profile.actor_kind into referenced_kind
          from public.actor_profiles profile where profile.id=referenced_id;
          if not found then return new; end if;
          if referenced_kind <> 'human' then
            raise exception 'actor reference must identify a human profile'
              using errcode='23514', constraint='require_human_actor_profile_reference';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.set_authority_audit_database_time() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if new.event_domain = 'authority' then
            if new.invalidation_cause_event_id is not null and not exists (
              select 1 from audit_events
              where id = new.invalidation_cause_event_id and event_domain = 'authority'
            ) then
              raise exception 'invalid authority invalidation cause' using errcode = '23503';
            end if;
            new.occurred_at = statement_timestamp();
          else
            new.occurred_at = null;
          end if;
          return new;
        end
        $$;
CREATE FUNCTION public.validate_artifact_binding_history() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare predecessor artifact_bindings%rowtype;
        begin
            if new.scope_version = 1 then
                return new;
            end if;
            select * into predecessor
              from artifact_bindings where id = new.supersedes_binding_id;
            if not found
               or predecessor.project_id != new.project_id
               or predecessor.resource_type != new.resource_type
               or predecessor.resource_id != new.resource_id
               or predecessor.logical_role != new.logical_role
               or predecessor.scope_version + 1 != new.scope_version then
                raise exception 'artifact binding predecessor is invalid';
            end if;
            return new;
        end;
        $$;
CREATE FUNCTION public.validate_artifact_recovery_attempt() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          source_row artifact_verification_jobs%rowtype;
          retry_row artifact_verification_jobs%rowtype;
          expected_parent text;
        begin
          if tg_op = 'DELETE' then
            raise exception 'artifact recovery attempts are append-only' using errcode='55000';
          end if;
          if tg_op = 'UPDATE' and (
            to_jsonb(new) - array['status','terminal_result_code','terminal_audit_event_id',
              'terminal_at','cas_version','updated_at']
            is distinct from
            to_jsonb(old) - array['status','terminal_result_code','terminal_audit_event_id',
              'terminal_at','cas_version','updated_at']
          ) then
            raise exception 'artifact recovery identity is immutable' using errcode='55000';
          end if;
          select * into source_row from artifact_verification_jobs
            where id=new.source_verification_job_id;
          select * into retry_row from artifact_verification_jobs
            where id=new.retry_verification_job_id;
          if source_row.id is null or retry_row.id is null
             or source_row.status <> 'provider_unavailable'
             or source_row.terminal_result_code <> 'provider_unavailable'
             or source_row.terminal_at is null or source_row.next_run_at is not null
             or source_row.executor_id is not null
             or source_row.attempt_count < source_row.maximum_attempts
             or retry_row.parent_verification_job_id <> source_row.id
             or retry_row.originating_put_attempt_id <> source_row.originating_put_attempt_id
             or retry_row.replica_id <> source_row.replica_id then
            raise exception 'invalid artifact recovery verification lineage' using errcode='23514';
          end if;
          if (tg_op = 'INSERT' and (retry_row.status <> 'pending' or retry_row.attempt_count <> 0))
             or (tg_op = 'UPDATE' and (
               retry_row.status <> new.terminal_result_code or retry_row.terminal_at is null
             )) then
            raise exception 'invalid artifact recovery retry state' using errcode='23514';
          end if;
          select id into expected_parent from artifact_recovery_attempts
            where retry_verification_job_id=source_row.id;
          if new.parent_recovery_attempt_id is distinct from expected_parent then
            raise exception 'invalid artifact recovery parent chain' using errcode='23514';
          end if;
          if not exists (
            select 1 from audit_events where id=new.initiation_audit_event_id
              and entity_type='artifact_recovery_attempt' and entity_id=new.id
              and event_type='ArtifactRecoveryInitiated'
          ) then
            raise exception 'invalid artifact recovery initiation audit' using errcode='23514';
          end if;
          if new.terminal_audit_event_id is not null and not exists (
            select 1 from audit_events where id=new.terminal_audit_event_id
              and entity_type='artifact_recovery_attempt' and entity_id=new.id
              and event_type='ArtifactRecoveryCompleted'
          ) then
            raise exception 'invalid artifact recovery terminal audit' using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.validate_artifact_verification_lineage() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if (
            old.parent_verification_job_id is not null
            or exists(
              select 1 from artifact_recovery_attempts
              where source_verification_job_id = old.id
                 or retry_verification_job_id = old.id
            )
          ) and (
            old.originating_put_attempt_id is distinct from new.originating_put_attempt_id
            or old.replica_id is distinct from new.replica_id
            or old.parent_verification_job_id is distinct from new.parent_verification_job_id
          ) then
            raise exception 'artifact verification lineage is immutable' using errcode='55000';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.validate_bootstrap_authority_state() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare control authority_control%rowtype;
                bootstrap_count bigint;
                referenced_bootstrap boolean;
        begin
          select * into control from authority_control where id=1;
          if not found then
            raise exception 'bootstrap grant/control invariant violated' using errcode='23514';
          end if;
          select count(*) into bootstrap_count from admin_role_grants
          where granted_by_system_principal='workstream:system:bootstrap';
          referenced_bootstrap := exists(
            select 1 from admin_role_grants
            where id=control.bootstrap_grant_id
              and granted_by_system_principal='workstream:system:bootstrap'
          );
          if (not control.bootstrap_completed and
              (control.bootstrap_grant_id is not null or control.version <> 0 or bootstrap_count <> 0))
             or (control.bootstrap_completed and
              (control.bootstrap_grant_id is null or control.version <> 1
               or bootstrap_count <> 1 or not referenced_bootstrap)) then
            raise exception 'bootstrap grant/control invariant violated' using errcode='23514';
          end if;
          return null;
        end $$;
CREATE FUNCTION public.validate_canonical_actor_link() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare profile_row actor_profiles%rowtype; link_count integer;
        begin
          if tg_table_name='actor_profiles' then
            select count(*) into link_count from actor_identity_links where actor_profile_id=new.id;
            if link_count <> 1 then raise exception 'actor profile requires exactly one identity link' using errcode='23514'; end if;
            if not exists(select 1 from actor_identity_links where actor_profile_id=new.id and subject_kind=new.actor_kind) then
              raise exception 'actor and identity kind mismatch' using errcode='23514';
            end if;
          else
            select * into profile_row from actor_profiles where id=new.actor_profile_id;
            if not found or profile_row.actor_kind <> new.subject_kind then
              raise exception 'actor and identity kind mismatch' using errcode='23514';
            end if;
          end if; return new;
        end $$;
CREATE FUNCTION public.validate_contribution_policy_graph() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if exists (
            select 1 from contribution_policy_versions v
            where v.status in ('published','retired') and (
              (select count(*) from contribution_rules r
               where r.contribution_policy_version_id=v.id
                 and r.contribution_type='accepted_submission') <> 1
              or
              (select count(*) from contribution_rules r
               where r.contribution_policy_version_id=v.id
                 and r.contribution_type='completed_review') <> 1
              or exists (
                select 1 from contribution_rules r
                where r.contribution_policy_version_id=v.id and (
                  (r.compensation_mode='unpaid' and
                    (select count(*) from contribution_award_definitions d
                     where d.contribution_rule_id=r.id) <> 0)
                  or
                  (r.compensation_mode='compensated' and
                    (select count(*) from contribution_award_definitions d
                     where d.contribution_rule_id=r.id) not between 1 and 2)
                )
              )
            )
          ) then
            raise exception 'published contribution policy graph is incomplete'
              using errcode='23514';
          end if;
          if exists (
            select 1 from contribution_policies p
            left join contribution_policy_versions v
              on v.id=p.current_published_version_id
             and v.contribution_policy_id=p.id
             and v.project_id=p.project_id
            where p.status='active' and (v.id is null or v.status <> 'published')
          ) then
            raise exception 'active contribution policy selector is invalid'
              using errcode='23514';
          end if;
          return null;
        end;
        $$;
CREATE FUNCTION public.validate_guide_mutation_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare reservation guide_mutation_idempotency_records%rowtype;
                evidence audit_events%rowtype;
                actor_id text; link_id text; grant_id uuid; action_value text;
                scope_type text; scope_project text; decision_id text;
                product_project text; product_resource text; product_generation integer;
        begin
          if tg_table_name='guide_mutation_idempotency_records' then
            select * into reservation from guide_mutation_idempotency_records where id=new.id;
            if reservation.status<>'committed' then
              raise exception 'pending guide mutation custody cannot commit' using errcode='23514';
            end if;
            if reservation.action_id in ('project.guide.create','project.guide.update') then
              select last_mutated_by_actor_profile_id,last_mutated_via_identity_link_id,
                     last_mutated_by_admin_role_grant_id,last_mutation_action_id,
                     last_mutation_scope_type,last_mutation_scope_project_id,
                     last_authorization_decision_event_id,project_id,id,mutation_generation
                into actor_id,link_id,grant_id,action_value,scope_type,scope_project,
                     decision_id,product_project,product_resource,product_generation
                from project_guides where id=reservation.resource_id;
            else
              select created_by_actor_profile_id,created_via_identity_link_id,
                     created_by_admin_role_grant_id,creation_action_id,
                     creation_scope_type,creation_scope_project_id,
                     authorization_decision_event_id,project_id,id,creation_generation
                into actor_id,link_id,grant_id,action_value,scope_type,scope_project,
                     decision_id,product_project,product_resource,product_generation
                from guide_source_snapshots where id=reservation.resource_id;
            end if;
          elsif tg_table_name='project_guides' then
            if tg_op='UPDATE'
               and (new.content_markdown is distinct from old.content_markdown
                    or new.change_summary is distinct from old.change_summary)
               and (new.mutation_generation is not distinct from old.mutation_generation
                    or new.last_authorization_decision_event_id
                       is not distinct from old.last_authorization_decision_event_id) then
              raise exception 'guide content mutation requires fresh custody' using errcode='23514';
            end if;
            if new.mutation_generation is null then
              if tg_op='INSERT' then
                raise exception 'new guides require mutation authority' using errcode='23514';
              end if;
              return null;
            end if;
            actor_id:=new.last_mutated_by_actor_profile_id;
            link_id:=new.last_mutated_via_identity_link_id;
            grant_id:=new.last_mutated_by_admin_role_grant_id;
            action_value:=new.last_mutation_action_id;
            scope_type:=new.last_mutation_scope_type;
            scope_project:=new.last_mutation_scope_project_id;
            decision_id:=new.last_authorization_decision_event_id;
            product_project:=new.project_id; product_resource:=new.id;
            product_generation:=new.mutation_generation;
            select * into reservation from guide_mutation_idempotency_records
              where resource_id=new.id and action_id=new.last_mutation_action_id
                and operation_generation=new.mutation_generation and status='committed';
          elsif tg_table_name='guide_source_snapshots' then
            if tg_op='UPDATE'
               and (new.project_id,new.guide_id,new.guide_version,
                    new.manifest_schema_version,new.manifest_json::jsonb,new.bundle_hash,new.captured_by)
                   is distinct from
                   (old.project_id,old.guide_id,old.guide_version,
                    old.manifest_schema_version,old.manifest_json::jsonb,old.bundle_hash,old.captured_by) then
              raise exception 'guide source snapshot content is immutable' using errcode='23514';
            end if;
            if new.creation_generation is null then
              raise exception 'new source snapshots require creation authority' using errcode='23514';
            end if;
            actor_id:=new.created_by_actor_profile_id;
            link_id:=new.created_via_identity_link_id;
            grant_id:=new.created_by_admin_role_grant_id;
            action_value:=new.creation_action_id;
            scope_type:=new.creation_scope_type;
            scope_project:=new.creation_scope_project_id;
            decision_id:=new.authorization_decision_event_id;
            product_project:=new.project_id; product_resource:=new.id;
            product_generation:=new.creation_generation;
            select * into reservation from guide_mutation_idempotency_records
              where resource_id=new.id and action_id='project.guide_source_snapshot.create'
                and operation_generation=new.creation_generation and status='committed';
          else
            if new.authorization_action_id is null then return null; end if;
            actor_id:=new.authorized_by_actor_profile_id;
            link_id:=new.authorized_via_identity_link_id;
            grant_id:=new.authorized_by_admin_role_grant_id;
            action_value:=new.authorization_action_id;
            scope_type:=new.authorization_scope_type;
            scope_project:=new.authorization_scope_project_id;
            decision_id:=new.authorization_decision_event_id;
            product_project:=new.project_id; product_resource:=new.source_snapshot_id;
            select * into reservation from guide_mutation_idempotency_records
              where setup_run_id=new.id and action_id='project.guide_source_snapshot.create'
                and status='committed';
            product_generation:=reservation.operation_generation;
          end if;
          if reservation.id is null or product_resource is null
             or reservation.actor_profile_id is distinct from actor_id
             or reservation.identity_link_id is distinct from link_id
             or reservation.action_id is distinct from action_value
             or reservation.project_id is distinct from product_project
             or reservation.resource_id is distinct from product_resource
             or reservation.operation_generation is distinct from product_generation
             or scope_type not in ('system','project')
             or (scope_type='project' and scope_project is distinct from product_project)
             or (scope_type='system' and scope_project is not null) then
            raise exception 'guide mutation custody mismatch' using errcode='23514';
          end if;
          select * into evidence from audit_events where id=decision_id;
          if evidence.id is null
             or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind is distinct from 'actor_profile'
             or evidence.actor_id is distinct from actor_id
             or evidence.matched_grant_id is distinct from grant_id::text
             or evidence.permission_id is distinct from 'project.guide.manage'
             or evidence.action_id is distinct from action_value
             or evidence.resource_type is distinct from 'project'
             or evidence.resource_id is distinct from product_project
             or evidence.target_ref_kind is distinct from 'project'
             or evidence.target_ref_id is distinct from product_project
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or evidence.after_facts->>'resource_context_digest'
                is distinct from reservation.resource_context_digest then
            raise exception 'guide mutation evidence mismatch' using errcode='23514';
          end if;
          return null;
        end $$;
CREATE FUNCTION public.validate_guide_source_snapshot_items() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare expected jsonb; actual jsonb; reservation guide_mutation_idempotency_records%rowtype;
        begin
          select snapshot.manifest_json::jsonb->'items' into expected
            from guide_source_snapshots snapshot where snapshot.id=new.source_snapshot_id;
          if expected is null then
            raise exception 'guide source snapshot item parent is unavailable' using errcode='23514';
          end if;
          select coalesce(jsonb_agg(jsonb_build_object(
                   'item_id',id,'item_order',item_order,'source_kind',source_kind,
                   'source_label',source_label,'ingestion_adapter',ingestion_adapter,
                   'media_type',media_type) order by item_order),'[]'::jsonb)
            into actual from guide_source_snapshot_items
            where source_snapshot_id=new.source_snapshot_id;
          if actual is distinct from expected then
            raise exception 'guide source snapshot items do not match manifest' using errcode='23514';
          end if;
          select r.* into reservation from guide_mutation_idempotency_records r
            join guide_source_snapshots s on s.id=r.resource_id
            where s.id=new.source_snapshot_id
              and r.action_id='project.guide_source_snapshot.create'
              and r.operation_generation=s.creation_generation and r.status='committed';
          if reservation.id is null then
            raise exception 'guide source snapshot item custody mismatch' using errcode='23514';
          end if;
          return null;
        end $$;
CREATE FUNCTION public.validate_linked_authority_event() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare record_row authority_idempotency_records%rowtype;
                cause_row audit_events%rowtype; expected_permission text;
                expected_resource text; expected_invalidation_resource text;
                expected_invalidation_id text; valid_success boolean;
        begin
          if new.event_domain <> 'authority' then return new; end if;
          valid_success := new.event_type in (
            'ServiceActorProvisioned','AdminRoleGrantIssued','AdminRoleGrantRevoked',
            'ProjectRoleQualificationSnapshotCaptured','ProjectRoleGrantIssued','ProjectRoleGrantRevoked',
            'ActorProfileSuspended','ActorProfileReactivated','ActorProfileDeactivated',
            'ActorIdentityLinkRevoked','ActorIdentityLinkReactivated');
          if not valid_success and new.event_type <> 'AuthorityInvalidationRequested' then
            if new.idempotency_reference is not null then
              raise exception 'invalid authority idempotency event' using errcode='23514';
            end if; return new;
          end if;
          if new.idempotency_reference is null then
            raise exception 'authority event requires idempotency reference' using errcode='23514';
          end if;
          select * into record_row from authority_idempotency_records
          where id=new.idempotency_reference and actor_ref_kind=new.actor_ref_kind and actor_ref=new.actor_id;
          if not found then raise exception 'invalid authority idempotency reference' using errcode='23503'; end if;
          if record_row.status <> 'pending' then raise exception 'committed authority idempotency is closed' using errcode='23514'; end if;
          expected_permission := case record_row.operation
            when 'service_actor.create' then 'actor.service.provision'
            when 'admin_role_grant.issue' then 'admin_role.grant'
            when 'admin_role_grant.revoke' then 'admin_role.revoke'
            when 'project_role_grant.issue' then 'project.role_grant.manage'
            when 'project_role_grant.revoke' then 'project.role_grant.manage'
            when 'actor_profile.suspend' then 'actor.profile.suspend'
            when 'actor_profile.reactivate' then 'actor.profile.reactivate'
            when 'actor_profile.deactivate' then 'actor.profile.deactivate'
            when 'actor_identity_link.revoke' then 'actor.identity_link.revoke'
            when 'actor_identity_link.reactivate' then 'actor.identity_link.reactivate' end;
          expected_resource := case
            when record_row.operation='service_actor.create' or record_row.operation like 'actor_profile.%' then 'actor_profile'
            when record_row.operation like 'admin_role_grant.%' then 'admin_role_grant'
            when record_row.operation like 'project_role_grant.%' then 'project_role_grant'
            else 'actor_identity_link' end;
          if new.permission_id <> expected_permission or new.resource_id is null then
            raise exception 'authority event does not match operation' using errcode='23514';
          end if;
          if new.event_type='ProjectRoleQualificationSnapshotCaptured' then
            if record_row.operation <> 'project_role_grant.issue'
               or new.resource_type <> 'qualification_snapshot'
               or new.entity_type <> 'qualification_snapshot'
               or new.entity_id <> new.resource_id
               or new.target_ref_kind is distinct from 'qualification_snapshot'
               or new.target_ref_id is distinct from new.resource_id
               or new.invalidation_cause_event_id is not null
               or new.invalidation_target_kind is not null
               or new.invalidation_target_ref is not null
               or exists(select 1 from audit_events where idempotency_reference=record_row.id) then
              raise exception 'invalid project role qualification evidence' using errcode='23514';
            end if;
          elsif record_row.operation='project_role_grant.issue'
                and new.event_type='ProjectRoleGrantIssued' then
            select * into cause_row from audit_events
            where idempotency_reference=record_row.id
              and event_type='ProjectRoleQualificationSnapshotCaptured';
            if not found
               or (select count(*) from audit_events where idempotency_reference=record_row.id) <> 1
               or cause_row.request_id is distinct from new.request_id
               or cause_row.correlation_id is distinct from new.correlation_id
               or cause_row.actor_ref_kind is distinct from new.actor_ref_kind
               or cause_row.actor_id is distinct from new.actor_id
               or cause_row.permission_id is distinct from new.permission_id
               or cause_row.project_id is distinct from new.project_id
               or cause_row.target_actor_ref_kind is distinct from new.target_actor_ref_kind
               or cause_row.target_actor_ref is distinct from new.target_actor_ref
               or cause_row.matched_grant_id is distinct from new.matched_grant_id
               or new.resource_type <> 'project_role_grant'
               or new.entity_type <> 'project_role_grant'
               or new.entity_id <> new.resource_id
               or new.target_ref_kind is distinct from 'project_role_grant'
               or new.target_ref_id is distinct from new.resource_id
               or new.invalidation_cause_event_id is not null
               or new.invalidation_target_kind is not null
               or new.invalidation_target_ref is not null then
              raise exception 'invalid project role issue evidence' using errcode='23514';
            end if;
          elsif record_row.operation='project_role_grant.revoke'
                and new.event_type='AuthorityInvalidationRequested' then
            select * into cause_row from audit_events where id=new.invalidation_cause_event_id;
            if not found or cause_row.event_type <> 'ProjectRoleGrantRevoked'
               or cause_row.idempotency_reference is distinct from record_row.id
               or cause_row.actor_ref_kind is distinct from new.actor_ref_kind
               or cause_row.actor_id is distinct from new.actor_id
               or cause_row.permission_id is distinct from new.permission_id
               or cause_row.request_id is distinct from new.request_id
               or cause_row.correlation_id is distinct from new.correlation_id
               or cause_row.project_id is distinct from new.project_id
               or cause_row.target_actor_ref_kind is distinct from 'actor_profile'
               or cause_row.target_actor_ref_kind is distinct from new.target_actor_ref_kind
               or cause_row.target_actor_ref is distinct from new.target_actor_ref
               or cause_row.resource_type <> 'project_role_grant'
               or cause_row.target_ref_kind <> 'project_role_grant'
               or cause_row.target_ref_id is distinct from cause_row.resource_id
               or new.resource_type <> 'project_role_grant'
               or new.resource_id is distinct from cause_row.resource_id
               or new.target_ref_kind is distinct from 'project_role_grant'
               or new.target_ref_id is distinct from cause_row.resource_id
               or new.invalidation_target_kind <> 'project_role_grant'
               or new.invalidation_target_ref is distinct from cause_row.resource_id
               or new.entity_type <> 'authority_invalidation' or new.entity_id <> new.id
               or new.before_facts::jsonb->>'effective' <> 'true'
               or new.after_facts::jsonb->>'effective' <> 'false'
               or new.before_facts::jsonb->>'role' not in ('submitter','reviewer','adjudicator')
               or new.before_facts::jsonb->>'role' is distinct from new.after_facts::jsonb->>'role'
               or new.before_facts::jsonb->>'scope_type' <> 'project'
               or new.before_facts::jsonb->>'scope_id' is distinct from new.project_id
               or new.before_facts::jsonb->>'scope_id' is distinct from new.after_facts::jsonb->>'scope_id'
               or new.before_facts::jsonb->>'future_obligation' is distinct from new.after_facts::jsonb->>'future_obligation'
               or (new.before_facts::jsonb->>'role'='submitter' and new.before_facts::jsonb->>'future_obligation'<>'auth13_assignment')
               or (new.before_facts::jsonb->>'role'='reviewer' and new.before_facts::jsonb->>'future_obligation'<>'rev_reviewer_obligation')
               or (new.before_facts::jsonb->>'role'='adjudicator' and new.before_facts::jsonb->>'future_obligation'<>'none') then
              raise exception 'invalid project role revoke invalidation' using errcode='23514';
            end if;
          elsif record_row.operation='project_role_grant.issue'
                and new.event_type='AuthorityInvalidationRequested' then
            raise exception 'project role issue forbids invalidation' using errcode='23514';
          elsif new.event_type='AuthorityInvalidationRequested' then
            select * into cause_row from audit_events where id=new.invalidation_cause_event_id;
            expected_invalidation_resource := case when record_row.operation in ('admin_role_grant.issue','admin_role_grant.revoke','actor_identity_link.revoke','actor_identity_link.reactivate') then 'actor_profile' else expected_resource end;
            expected_invalidation_id := case when record_row.operation in ('admin_role_grant.issue','admin_role_grant.revoke','actor_identity_link.revoke','actor_identity_link.reactivate') then cause_row.target_actor_ref else cause_row.resource_id end;
            if not found or cause_row.idempotency_reference is distinct from record_row.id
               or cause_row.actor_ref_kind is distinct from new.actor_ref_kind
               or cause_row.actor_id is distinct from new.actor_id
               or cause_row.permission_id is distinct from new.permission_id
               or cause_row.resource_type is distinct from expected_resource
               or new.resource_type is distinct from expected_invalidation_resource
               or new.resource_id is distinct from expected_invalidation_id
               or new.invalidation_target_kind is distinct from expected_invalidation_resource
               or new.invalidation_target_ref is distinct from expected_invalidation_id
               or cause_row.target_ref_kind is distinct from cause_row.resource_type
               or cause_row.target_ref_id is distinct from cause_row.resource_id
               or cause_row.request_id is distinct from new.request_id
               or cause_row.correlation_id is distinct from new.correlation_id
               or cause_row.project_id is distinct from new.project_id
               or new.entity_type <> 'authority_invalidation' or new.entity_id <> new.id
               or (record_row.operation in ('admin_role_grant.issue','admin_role_grant.revoke','actor_identity_link.revoke','actor_identity_link.reactivate') and (cause_row.target_actor_ref_kind <> 'actor_profile' or cause_row.target_actor_ref is null))
               or (record_row.operation in ('admin_role_grant.issue','actor_profile.reactivate','actor_identity_link.reactivate') and
                   (new.before_facts::jsonb <> '{"effective": false}'::jsonb or new.after_facts::jsonb <> '{"effective": true}'::jsonb))
               or (record_row.operation not in ('admin_role_grant.issue','actor_profile.reactivate','actor_identity_link.reactivate') and
                   (new.before_facts::jsonb <> '{"effective": true}'::jsonb or new.after_facts::jsonb <> '{"effective": false}'::jsonb))
               or not (
                 (record_row.operation='service_actor.create' and cause_row.event_type='ServiceActorProvisioned') or
                 (record_row.operation='admin_role_grant.issue' and cause_row.event_type='AdminRoleGrantIssued') or
                 (record_row.operation='admin_role_grant.revoke' and cause_row.event_type='AdminRoleGrantRevoked') or
                 (record_row.operation='project_role_grant.issue' and cause_row.event_type in ('ProjectRoleGrantIssued')) or
                 (record_row.operation='project_role_grant.revoke' and cause_row.event_type='ProjectRoleGrantRevoked') or
                 (record_row.operation='actor_profile.suspend' and cause_row.event_type='ActorProfileSuspended') or
                 (record_row.operation='actor_profile.reactivate' and cause_row.event_type='ActorProfileReactivated') or
                 (record_row.operation='actor_profile.deactivate' and cause_row.event_type='ActorProfileDeactivated') or
                 (record_row.operation='actor_identity_link.revoke' and cause_row.event_type='ActorIdentityLinkRevoked') or
                 (record_row.operation='actor_identity_link.reactivate' and cause_row.event_type='ActorIdentityLinkReactivated')) then
              raise exception 'invalid linked authority cause' using errcode='23514';
            end if;
          else
            if new.resource_type <> expected_resource or new.entity_type <> expected_resource
               or new.entity_id <> new.resource_id or new.target_ref_kind is distinct from expected_resource
               or new.target_ref_id is distinct from new.resource_id
               or new.invalidation_cause_event_id is not null
               or new.invalidation_target_kind is not null or new.invalidation_target_ref is not null
               or not (
                 (record_row.operation='service_actor.create' and new.event_type='ServiceActorProvisioned') or
                 (record_row.operation='admin_role_grant.issue' and new.event_type='AdminRoleGrantIssued') or
                 (record_row.operation='admin_role_grant.revoke' and new.event_type='AdminRoleGrantRevoked') or
                 (record_row.operation='project_role_grant.issue' and new.event_type in ('ProjectRoleGrantIssued')) or
                 (record_row.operation='project_role_grant.revoke' and new.event_type='ProjectRoleGrantRevoked') or
                 (record_row.operation='actor_profile.suspend' and new.event_type='ActorProfileSuspended') or
                 (record_row.operation='actor_profile.reactivate' and new.event_type='ActorProfileReactivated') or
                 (record_row.operation='actor_profile.deactivate' and new.event_type='ActorProfileDeactivated') or
                 (record_row.operation='actor_identity_link.revoke' and new.event_type='ActorIdentityLinkRevoked') or
                 (record_row.operation='actor_identity_link.reactivate' and new.event_type='ActorIdentityLinkReactivated')) then
              raise exception 'authority success event does not match operation' using errcode='23514';
            end if;
          end if; return new;
        end $$;
CREATE FUNCTION public.validate_policy_mutation_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare reservation policy_mutation_idempotency_records%rowtype;
                evidence audit_events%rowtype;
                actor_id text; link_id text; grant_id uuid; action_value text;
                scope_type text; scope_project text; decision_id text;
                product_project text; product_guide text; product_id text;
                product_generation integer;
                product_hash text; predecessor_id text; predecessor_hash text;
                selector_id text; selector_generation integer; selector_hash text;
                predecessor_valid boolean;
        begin
          if tg_table_name='policy_mutation_idempotency_records' then
            select * into reservation from policy_mutation_idempotency_records where id=new.id;
            if reservation.status<>'committed' then
              raise exception 'pending policy mutation custody cannot commit' using errcode='23514';
            end if;
            if reservation.action_id='project.review_policy.update' then
              select created_by_actor_profile_id,created_via_identity_link_id,
                     created_by_admin_role_grant_id,creation_action_id,
                     creation_scope_type,creation_scope_project_id,
                     authorization_decision_event_id,p.project_id,g.id,p.id,
                     p.policy_generation,p.policy_hash,p.supersedes_policy_id,
                     p.predecessor_policy_hash,g.selected_review_policy_id,
                     g.selected_review_policy_generation,g.selected_review_policy_hash
                into actor_id,link_id,grant_id,action_value,scope_type,scope_project,
                     decision_id,product_project,product_guide,product_id,product_generation,
                     product_hash,predecessor_id,predecessor_hash,selector_id,
                     selector_generation,selector_hash
                from review_policies p join project_guides g
                  on g.project_id=p.project_id and g.version=p.guide_version
                where p.id=reservation.policy_id and g.id=reservation.guide_id;
            else
              select created_by_actor_profile_id,created_via_identity_link_id,
                     created_by_admin_role_grant_id,creation_action_id,
                     creation_scope_type,creation_scope_project_id,
                     authorization_decision_event_id,p.project_id,g.id,p.id,
                     p.policy_generation,p.policy_hash,p.supersedes_policy_id,
                     p.predecessor_policy_hash,g.selected_revision_policy_id,
                     g.selected_revision_policy_generation,g.selected_revision_policy_hash
                into actor_id,link_id,grant_id,action_value,scope_type,scope_project,
                     decision_id,product_project,product_guide,product_id,product_generation,
                     product_hash,predecessor_id,predecessor_hash,selector_id,
                     selector_generation,selector_hash
                from revision_policies p join project_guides g
                  on g.project_id=p.project_id and g.version=p.guide_version
                where p.id=reservation.policy_id and g.id=reservation.guide_id;
            end if;
          else
            actor_id:=new.created_by_actor_profile_id;
            link_id:=new.created_via_identity_link_id;
            grant_id:=new.created_by_admin_role_grant_id;
            action_value:=new.creation_action_id;
            scope_type:=new.creation_scope_type;
            scope_project:=new.creation_scope_project_id;
            decision_id:=new.authorization_decision_event_id;
            product_project:=new.project_id; product_id:=new.id;
            product_generation:=new.policy_generation; product_hash:=new.policy_hash;
            predecessor_id:=new.supersedes_policy_id;
            predecessor_hash:=new.predecessor_policy_hash;
            if tg_table_name='review_policies' then
              select g.id,g.selected_review_policy_id,g.selected_review_policy_generation,
                     g.selected_review_policy_hash
                into product_guide,selector_id,selector_generation,selector_hash
                from project_guides g
                where g.project_id=new.project_id and g.version=new.guide_version;
            else
              select g.id,g.selected_revision_policy_id,g.selected_revision_policy_generation,
                     g.selected_revision_policy_hash
                into product_guide,selector_id,selector_generation,selector_hash
                from project_guides g
                where g.project_id=new.project_id and g.version=new.guide_version;
            end if;
            select r.* into reservation from policy_mutation_idempotency_records r
              where r.policy_id=new.id and r.action_id=new.creation_action_id
                and r.policy_generation=new.policy_generation and r.status='committed';
          end if;
          if reservation.id is null or product_id is null
             or reservation.actor_profile_id is distinct from actor_id
             or reservation.identity_link_id is distinct from link_id
             or reservation.action_id is distinct from action_value
             or reservation.project_id is distinct from product_project
             or reservation.guide_id is distinct from product_guide
             or reservation.policy_id is distinct from product_id
             or reservation.policy_generation is distinct from product_generation
             or reservation.policy_hash is distinct from product_hash
             or selector_id is distinct from product_id
             or selector_generation is distinct from product_generation
             or selector_hash is distinct from product_hash
             or scope_type not in ('system','project')
             or (scope_type='project' and scope_project is distinct from product_project)
             or (scope_type='system' and scope_project is not null) then
            raise exception 'policy mutation custody mismatch' using errcode='23514';
          end if;
          if product_generation=1 then
            predecessor_valid:=predecessor_id is null and predecessor_hash is null;
          elsif reservation.action_id='project.review_policy.update' then
            select exists(select 1 from review_policies prior
              where prior.id=predecessor_id and prior.project_id=product_project
                and prior.guide_version=(select version from project_guides where id=product_guide)
                and prior.policy_generation=product_generation-1
                and prior.policy_hash=predecessor_hash) into predecessor_valid;
          else
            select exists(select 1 from revision_policies prior
              where prior.id=predecessor_id and prior.project_id=product_project
                and prior.guide_version=(select version from project_guides where id=product_guide)
                and prior.policy_generation=product_generation-1
                and prior.policy_hash=predecessor_hash) into predecessor_valid;
          end if;
          if predecessor_valid is not true then
            raise exception 'policy mutation lineage mismatch' using errcode='23514';
          end if;
          select * into evidence from audit_events where id=decision_id;
          if evidence.id is null or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind is distinct from 'actor_profile'
             or evidence.actor_id is distinct from actor_id
             or evidence.matched_grant_id is distinct from grant_id::text
             or evidence.permission_id is distinct from 'project.review_policy.manage'
             or evidence.action_id is distinct from action_value
             or evidence.resource_type is distinct from 'project'
             or evidence.resource_id is distinct from product_project
             or evidence.target_ref_kind is distinct from 'project'
             or evidence.target_ref_id is distinct from product_project
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or evidence.after_facts->>'resource_context_digest'
                is distinct from reservation.resource_context_digest then
            raise exception 'policy mutation evidence mismatch' using errcode='23514';
          end if;
          return null;
        end $$;
CREATE FUNCTION public.validate_project_create_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
        declare project_row projects%rowtype; reservation project_create_idempotency_records%rowtype;
                evidence audit_events%rowtype;
        begin
          if tg_table_name = 'projects' then
            if tg_op = 'INSERT' and new.creation_action_id is null then
              raise exception 'new projects require creation authority' using errcode='23514';
            end if;
            if new.creation_action_id is null then return null; end if;
            project_row := new;
            select * into reservation from project_create_idempotency_records
              where project_id=project_row.id and status='committed';
          else
            select * into reservation from project_create_idempotency_records
              where id=new.id;
            if reservation.status <> 'committed' then
              raise exception 'pending project create reservation cannot commit' using errcode='23514';
            end if;
            select * into project_row from projects where id=reservation.project_id;
          end if;
          if project_row.id is null or reservation.id is null
             or project_row.created_by_actor_profile_id
                is distinct from reservation.actor_profile_id
             or project_row.created_via_identity_link_id
                is distinct from reservation.identity_link_id
             or project_row.creation_action_id is distinct from reservation.action_id then
            raise exception 'project create custody mismatch' using errcode='23514';
          end if;
          select * into evidence from audit_events
            where id=project_row.authorization_decision_event_id;
          if evidence.id is null
             or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind is distinct from 'actor_profile'
             or evidence.actor_id is distinct from project_row.created_by_actor_profile_id
             or evidence.matched_grant_id
                is distinct from project_row.created_by_admin_role_grant_id::text
             or evidence.permission_id is distinct from 'project.create'
             or evidence.action_id is distinct from 'project.create'
             or evidence.resource_type is distinct from 'project_create_operation'
             or evidence.resource_id is distinct from reservation.operation_id::text
             or evidence.target_ref_kind is distinct from 'project'
             or evidence.target_ref_id is distinct from project_row.id
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or coalesce(
                  evidence.after_facts->>'resource_context_digest'
                    !~ '^sha256:[0-9a-f]{64}$',
                  true
                ) then
            raise exception 'project create evidence mismatch' using errcode='23514';
          end if;
          return null;
        end $_$;
CREATE FUNCTION public.validate_review_active_lease() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          queue_row review_queue_entries%rowtype;
          active_count integer;
        begin
          if tg_table_name='review_queue_entries' then
            queue_row := new;
          else
            select * into queue_row from review_queue_entries
             where id=coalesce(new.review_queue_entry_id,old.review_queue_entry_id);
          end if;
          if not found and tg_table_name='review_leases' then
            raise exception 'review lease queue is missing' using errcode='23514';
          end if;
          select count(*) into active_count from review_leases
           where review_queue_entry_id=queue_row.id and status='active';
          if queue_row.queue_state='leased' then
            if queue_row.active_lease_id is null or active_count <> 1 or not exists(
              select 1 from review_leases where id=queue_row.active_lease_id
               and review_queue_entry_id=queue_row.id and status='active'
            ) then
              raise exception 'leased queue must identify its active lease' using errcode='23514';
            end if;
          elsif queue_row.active_lease_id is not null or active_count <> 0 then
            raise exception 'non-leased queue cannot retain an active lease' using errcode='23514';
          end if;
          return null;
        end $$;
CREATE FUNCTION public.validate_submission_policy_authority_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare reservation submission_policy_mutation_idempotency_records%rowtype;
                evidence audit_events%rowtype;
                actor_id varchar; link_id varchar; grant_id uuid; service_id varchar;
                action_value varchar; decision_id varchar; product_project varchar;
                product_id varchar; approval_outputs_valid boolean;
        begin
          if tg_table_name='submission_policy_mutation_idempotency_records' then
            if new.status='pending' then return null; end if;
            reservation:=new;
            select project_id,id,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then approved_by_actor_profile_id else created_by_actor_profile_id end,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then approved_via_identity_link_id else created_via_identity_link_id end,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then approved_by_admin_role_grant_id
                        else created_by_admin_role_grant_id end,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then null else created_by_service_identity end,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then approval_action_id else creation_action_id end,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then approval_decision_event_id else creation_decision_event_id end
              into product_project,product_id,actor_id,link_id,grant_id,service_id,
                   action_value,decision_id
              from submission_artifact_policies where id=reservation.committed_policy_id;
            if reservation.action_id='project.submission_artifact_policy.approve' then
              select exists(
                select 1
                  from submission_artifact_policies s
                  join effective_project_submission_artifact_policies e
                    on e.id=reservation.committed_effective_policy_id
                   and e.submission_artifact_policy_id=s.id
                   and e.submission_artifact_policy_hash=s.policy_hash
                  join pre_submit_checker_policies p
                    on p.id=reservation.committed_pre_submit_policy_id
                   and p.project_id=e.project_id
                  where s.id=reservation.committed_policy_id
                    and s.id=reservation.policy_id
                    and s.guide_id=reservation.guide_id
                    and s.source_snapshot_id=reservation.source_snapshot_id
                    and s.guide_version=reservation.resource_context_json->>'guide_version'
                    and s.policy_hash=reservation.resource_context_json->>'policy_digest'
                    and e.effective_policy_hash=
                        reservation.resource_context_json->>'effective_output_digest'
                    and p.compiled_bundle_hash=
                        reservation.resource_context_json->>'compiled_pre_submit_output_digest'
                    and e.project_id=reservation.project_id
                    and e.guide_id=s.guide_id and p.guide_id=s.guide_id
                    and e.guide_version=s.guide_version
                    and p.guide_version=s.guide_version
                    and e.source_snapshot_id=s.source_snapshot_id
                    and p.source_snapshot_id=s.source_snapshot_id
                    and e.source_snapshot_hash=s.source_snapshot_hash
                    and p.source_snapshot_hash=s.source_snapshot_hash
                    and e.submission_artifact_policy_id=reservation.committed_policy_id
                    and p.effective_policy_id=e.id
                    and p.effective_policy_hash=e.effective_policy_hash
                    and e.created_by_actor_profile_id=reservation.actor_profile_id
                    and p.created_by_actor_profile_id=reservation.actor_profile_id
                    and e.created_via_identity_link_id=reservation.identity_link_id
                    and p.created_via_identity_link_id=reservation.identity_link_id
                    and e.created_by_admin_role_grant_id=grant_id
                    and p.created_by_admin_role_grant_id=grant_id
                    and e.creation_scope_project_id=reservation.project_id
                    and p.creation_scope_project_id=reservation.project_id
                    and e.creation_action_id=reservation.action_id
                    and p.creation_action_id=reservation.action_id
                    and e.creation_decision_event_id=decision_id
                    and p.creation_decision_event_id=decision_id
              ) into approval_outputs_valid;
              if approval_outputs_valid is not true then
                raise exception 'submission-policy approval output custody mismatch'
                  using errcode='23514';
              end if;
            end if;
          elsif tg_table_name='submission_artifact_policies' then
            if new.creation_action_id is null and new.approval_action_id is null then
              if new.created_by_actor_profile_id is not null
                 or new.created_via_identity_link_id is not null
                 or new.created_by_admin_role_grant_id is not null
                 or new.created_by_service_identity is not null
                 or new.creation_scope_type is not null
                 or new.creation_scope_project_id is not null
                 or new.creation_decision_event_id is not null
                 or new.approved_by_actor_profile_id is not null
                 or new.approved_via_identity_link_id is not null
                 or new.approved_by_admin_role_grant_id is not null
                 or new.approval_scope_type is not null
                 or new.approval_scope_project_id is not null
                 or new.approval_decision_event_id is not null then
                raise exception 'partial submission-policy provenance'
                  using errcode='23514';
              end if;
              return null;
            end if;
            if new.approval_action_id is not null then
              select * into reservation from submission_policy_mutation_idempotency_records
                where committed_policy_id=new.id and action_id=new.approval_action_id
                  and status='committed';
              actor_id:=new.approved_by_actor_profile_id;
              link_id:=new.approved_via_identity_link_id;
              grant_id:=new.approved_by_admin_role_grant_id;
              service_id:=null; action_value:=new.approval_action_id;
              decision_id:=new.approval_decision_event_id;
            else
              select * into reservation from submission_policy_mutation_idempotency_records
                where committed_policy_id=new.id and action_id=new.creation_action_id
                  and status='committed';
              actor_id:=new.created_by_actor_profile_id;
              link_id:=new.created_via_identity_link_id;
              grant_id:=new.created_by_admin_role_grant_id;
              service_id:=new.created_by_service_identity;
              action_value:=new.creation_action_id;
              decision_id:=new.creation_decision_event_id;
            end if;
            product_project:=new.project_id; product_id:=new.id;
          elsif tg_table_name='effective_project_submission_artifact_policies' then
            if new.creation_action_id is null then
              if new.created_by_actor_profile_id is not null
                 or new.created_via_identity_link_id is not null
                 or new.created_by_admin_role_grant_id is not null
                 or new.creation_scope_type is not null
                 or new.creation_scope_project_id is not null
                 or new.creation_decision_event_id is not null then
                raise exception 'partial effective-policy provenance'
                  using errcode='23514';
              end if;
              return null;
            end if;
            select * into reservation from submission_policy_mutation_idempotency_records
              where committed_effective_policy_id=new.id and status='committed';
            actor_id:=new.created_by_actor_profile_id;
            link_id:=new.created_via_identity_link_id;
            grant_id:=new.created_by_admin_role_grant_id;
            service_id:=null; action_value:=new.creation_action_id;
            decision_id:=new.creation_decision_event_id;
            product_project:=new.project_id; product_id:=reservation.committed_policy_id;
          else
            if new.creation_action_id is null then
              if new.created_by_actor_profile_id is not null
                 or new.created_via_identity_link_id is not null
                 or new.created_by_admin_role_grant_id is not null
                 or new.creation_scope_type is not null
                 or new.creation_scope_project_id is not null
                 or new.creation_decision_event_id is not null then
                raise exception 'partial pre-submit-policy provenance'
                  using errcode='23514';
              end if;
              return null;
            end if;
            select * into reservation from submission_policy_mutation_idempotency_records
              where committed_pre_submit_policy_id=new.id and status='committed';
            actor_id:=new.created_by_actor_profile_id;
            link_id:=new.created_via_identity_link_id;
            grant_id:=new.created_by_admin_role_grant_id;
            service_id:=null; action_value:=new.creation_action_id;
            decision_id:=new.creation_decision_event_id;
            product_project:=new.project_id; product_id:=reservation.committed_policy_id;
          end if;
          if reservation.id is null or product_id is null
             or reservation.actor_profile_id is distinct from actor_id
             or reservation.identity_link_id is distinct from link_id
             or reservation.action_id is distinct from action_value
             or reservation.project_id is distinct from product_project
             or reservation.committed_policy_id is distinct from product_id
             or reservation.service_identity is distinct from service_id then
            raise exception 'submission-policy mutation custody mismatch' using errcode='23514';
          end if;
          select * into evidence from audit_events where id=decision_id;
          if evidence.id is null or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind is distinct from 'actor_profile'
             or evidence.actor_id is distinct from actor_id
             or evidence.matched_grant_id is distinct from grant_id::text
             or evidence.permission_id is distinct from 'project.effective_policy.manage'
             or evidence.action_id is distinct from action_value
             or evidence.resource_type
                is distinct from 'project_submission_artifact_policy_mutation'
             or evidence.resource_id is distinct from product_id
             or evidence.project_id is distinct from reservation.project_id
             or evidence.target_ref_kind is distinct from 'project'
             or evidence.target_ref_id is distinct from reservation.project_id
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or evidence.after_facts->>'resource_context_digest'
                is distinct from reservation.resource_context_digest then
            raise exception 'submission-policy authorization evidence mismatch'
              using errcode='23514';
          end if;
          return null;
        end $$;
CREATE FUNCTION public.validate_submission_policy_creation_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare reservation submission_policy_mutation_idempotency_records%rowtype;
                evidence audit_events%rowtype;
        begin
          if new.creation_action_id is null then
            if new.created_by_actor_profile_id is not null
               or new.created_via_identity_link_id is not null
               or new.created_by_admin_role_grant_id is not null
               or new.created_by_service_identity is not null
               or new.creation_scope_type is not null
               or new.creation_scope_project_id is not null
               or new.creation_decision_event_id is not null then
              raise exception 'partial submission-policy creation provenance'
                using errcode='23514';
            end if;
            return null;
          end if;
          select * into reservation from submission_policy_mutation_idempotency_records
            where committed_policy_id=new.id and action_id=new.creation_action_id
              and status='committed';
          if reservation.id is null
             or reservation.actor_profile_id
                is distinct from new.created_by_actor_profile_id
             or reservation.identity_link_id
                is distinct from new.created_via_identity_link_id
             or reservation.service_identity
                is distinct from new.created_by_service_identity
             or reservation.project_id is distinct from new.project_id
             or reservation.policy_id is distinct from new.id
             or reservation.guide_id is distinct from new.guide_id
             or reservation.source_snapshot_id is distinct from new.source_snapshot_id
             or reservation.resource_context_json->>'guide_version'
                is distinct from new.guide_version then
            raise exception 'submission-policy creation custody mismatch' using errcode='23514';
          end if;
          select * into evidence from audit_events where id=new.creation_decision_event_id;
          if evidence.id is null or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind is distinct from 'actor_profile'
             or evidence.actor_id is distinct from new.created_by_actor_profile_id
             or evidence.matched_grant_id
                is distinct from new.created_by_admin_role_grant_id::text
             or evidence.permission_id is distinct from 'project.effective_policy.manage'
             or evidence.action_id is distinct from new.creation_action_id
             or evidence.resource_type
                is distinct from 'project_submission_artifact_policy_mutation'
             or evidence.resource_id is distinct from new.id
             or evidence.project_id is distinct from reservation.project_id
             or evidence.target_ref_kind is distinct from 'project'
             or evidence.target_ref_id is distinct from reservation.project_id
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or evidence.after_facts->>'resource_context_digest'
                is distinct from reservation.resource_context_digest then
            raise exception 'submission-policy creation evidence mismatch'
              using errcode='23514';
          end if;
          return null;
        end $$;
CREATE TABLE public.actor_identity_links (
    id character varying(36) NOT NULL,
    actor_profile_id character varying(36) NOT NULL,
    issuer character varying(200) NOT NULL,
    subject character varying(200) NOT NULL,
    subject_kind character varying(16) NOT NULL,
    status character varying(16) NOT NULL,
    linked_by character varying(120) NOT NULL,
    linked_at timestamp with time zone DEFAULT now() NOT NULL,
    last_verified_at timestamp with time zone,
    revoked_by character varying(120),
    revoked_at timestamp with time zone,
    revoked_reason character varying(500),
    reactivated_by character varying(120),
    reactivated_at timestamp with time zone,
    reactivation_reason character varying(500),
    CONSTRAINT ck_actor_identity_links_human_verified CHECK ((((subject_kind)::text = 'service'::text) OR (last_verified_at IS NOT NULL))),
    CONSTRAINT ck_actor_identity_links_id_uuid CHECK (((id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)),
    CONSTRAINT ck_actor_identity_links_issuer CHECK (((length(btrim((issuer)::text)) >= 1) AND (length(btrim((issuer)::text)) <= 200))),
    CONSTRAINT ck_actor_identity_links_lifecycle_reason_bounds CHECK ((((revoked_reason IS NULL) OR (((revoked_reason)::text = btrim((revoked_reason)::text, (((((((((((((((((((((((' 	
'::text || chr(28)) || chr(29)) || chr(30)) || chr(31)) || chr(133)) || chr(160)) || chr(5760)) || chr(8192)) || chr(8193)) || chr(8194)) || chr(8195)) || chr(8196)) || chr(8197)) || chr(8198)) || chr(8199)) || chr(8200)) || chr(8201)) || chr(8202)) || chr(8232)) || chr(8233)) || chr(8239)) || chr(8287)) || chr(12288)))) AND ((octet_length((revoked_reason)::text) >= 1) AND (octet_length((revoked_reason)::text) <= 500)))) AND ((reactivation_reason IS NULL) OR (((reactivation_reason)::text = btrim((reactivation_reason)::text, (((((((((((((((((((((((' 	
'::text || chr(28)) || chr(29)) || chr(30)) || chr(31)) || chr(133)) || chr(160)) || chr(5760)) || chr(8192)) || chr(8193)) || chr(8194)) || chr(8195)) || chr(8196)) || chr(8197)) || chr(8198)) || chr(8199)) || chr(8200)) || chr(8201)) || chr(8202)) || chr(8232)) || chr(8233)) || chr(8239)) || chr(8287)) || chr(12288)))) AND ((octet_length((reactivation_reason)::text) >= 1) AND (octet_length((reactivation_reason)::text) <= 500)))))),
    CONSTRAINT ck_actor_identity_links_reactivation_fields CHECK ((((reactivated_by IS NULL) AND (reactivated_at IS NULL) AND (reactivation_reason IS NULL)) OR ((reactivated_by IS NOT NULL) AND (reactivated_at IS NOT NULL) AND (reactivation_reason IS NOT NULL)))),
    CONSTRAINT ck_actor_identity_links_revocation_fields CHECK (((((status)::text = 'active'::text) AND (revoked_by IS NULL) AND (revoked_at IS NULL) AND (revoked_reason IS NULL)) OR (((status)::text = 'revoked'::text) AND (revoked_by IS NOT NULL) AND (revoked_at IS NOT NULL) AND (revoked_reason IS NOT NULL)))),
    CONSTRAINT ck_actor_identity_links_status CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'revoked'::character varying])::text[]))),
    CONSTRAINT ck_actor_identity_links_subject CHECK (((length(btrim((subject)::text)) >= 1) AND (length(btrim((subject)::text)) <= 200))),
    CONSTRAINT ck_actor_identity_links_subject_kind CHECK (((subject_kind)::text = ANY ((ARRAY['human'::character varying, 'service'::character varying])::text[])))
);
CREATE TABLE public.actor_profile_migration_state (
    id integer NOT NULL,
    schema_version integer NOT NULL,
    classified_count integer NOT NULL,
    source_row_set_sha256 character varying(64) NOT NULL,
    manifest_sha256 character varying(64),
    envelope_sha256 character varying(64),
    migrated_at timestamp with time zone DEFAULT now() NOT NULL,
    service_identity_mapped_count integer NOT NULL,
    service_identity_source_row_set_sha256 character varying(64) NOT NULL,
    service_identity_manifest_sha256 character varying(64),
    service_identity_envelope_sha256 character varying(64),
    service_identity_database_binding character varying(76) NOT NULL,
    CONSTRAINT ck_actor_profile_migration_state_evidence CHECK ((((classified_count = 0) AND (manifest_sha256 IS NULL) AND (envelope_sha256 IS NULL)) OR ((classified_count > 0) AND (manifest_sha256 IS NOT NULL) AND (envelope_sha256 IS NOT NULL)))),
    CONSTRAINT ck_actor_profile_migration_state_service_identity_evidence CHECK ((((service_identity_mapped_count >= 0) AND (service_identity_mapped_count <= 7)) AND ((service_identity_source_row_set_sha256)::text ~ '^[0-9a-f]{64}$'::text) AND ((service_identity_database_binding)::text ~ '^postgres-v1:[0-9a-f]{64}$'::text) AND (((service_identity_mapped_count = 0) AND (service_identity_manifest_sha256 IS NULL) AND (service_identity_envelope_sha256 IS NULL)) OR (((service_identity_mapped_count >= 1) AND (service_identity_mapped_count <= 7)) AND ((service_identity_manifest_sha256)::text ~ '^[0-9a-f]{64}$'::text) AND ((service_identity_envelope_sha256)::text ~ '^[0-9a-f]{64}$'::text))))),
    CONSTRAINT ck_actor_profile_migration_state_singleton CHECK (((id = 1) AND (schema_version = 1) AND (classified_count >= 0)))
);
CREATE SEQUENCE public.actor_profile_migration_state_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.actor_profile_migration_state_id_seq OWNED BY public.actor_profile_migration_state.id;
CREATE TABLE public.actor_profiles (
    id character varying(36) NOT NULL,
    actor_kind character varying(16) NOT NULL,
    status character varying(16) NOT NULL,
    provisioning_method character varying(32) NOT NULL,
    display_name character varying(200),
    contact_email character varying(320),
    created_by character varying(120) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone,
    suspended_by character varying(120),
    suspended_at timestamp with time zone,
    suspension_reason character varying(500),
    deactivated_by character varying(120),
    deactivated_at timestamp with time zone,
    deactivation_reason character varying(500),
    service_identity character varying(80),
    reactivated_by character varying(120),
    reactivated_at timestamp with time zone,
    reactivation_reason character varying(500),
    CONSTRAINT ck_actor_profiles_actor_kind CHECK (((actor_kind)::text = ANY ((ARRAY['human'::character varying, 'service'::character varying])::text[]))),
    CONSTRAINT ck_actor_profiles_id_uuid CHECK (((id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)),
    CONSTRAINT ck_actor_profiles_kind_provisioning CHECK (((((actor_kind)::text = 'human'::text) AND ((provisioning_method)::text = 'automatic_first_access'::text)) OR (((actor_kind)::text = 'service'::text) AND ((provisioning_method)::text = 'manual_service_provisioning'::text)))),
    CONSTRAINT ck_actor_profiles_kind_service_identity CHECK (((((actor_kind)::text = 'human'::text) AND (service_identity IS NULL)) OR (((actor_kind)::text = 'service'::text) AND ((service_identity)::text = ANY ((ARRAY['workstream.artifact.verifier'::character varying, 'workstream.artifact.put_resolver'::character varying, 'workstream.artifact.scheduler'::character varying, 'workstream.artifact.binding'::character varying, 'workstream.artifact.guide_reader'::character varying, 'workstream.artifact.materializer'::character varying, 'workstream.artifact.checker_output'::character varying, 'workstream.project.setup'::character varying, 'workstream.review.preference_expiry'::character varying, 'workstream.review.lease_expiry'::character varying, 'workstream.review.authority_invalidation_reconciliation'::character varying, 'workstream.review.reconciliation'::character varying, 'workstream.review.artifact_reference_reconciliation'::character varying, 'workstream.review.projection'::character varying])::text[]))))),
    CONSTRAINT ck_actor_profiles_lifecycle_fields CHECK (((((status)::text = 'active'::text) AND (suspended_by IS NULL) AND (suspended_at IS NULL) AND (suspension_reason IS NULL) AND (deactivated_by IS NULL) AND (deactivated_at IS NULL) AND (deactivation_reason IS NULL)) OR (((status)::text = 'suspended'::text) AND (suspended_by IS NOT NULL) AND (suspended_at IS NOT NULL) AND (suspension_reason IS NOT NULL) AND (deactivated_by IS NULL) AND (deactivated_at IS NULL) AND (deactivation_reason IS NULL)) OR (((status)::text = 'deactivated'::text) AND (deactivated_by IS NOT NULL) AND (deactivated_at IS NOT NULL) AND (deactivation_reason IS NOT NULL)))),
    CONSTRAINT ck_actor_profiles_lifecycle_reason_bounds CHECK ((((suspension_reason IS NULL) OR (((suspension_reason)::text = btrim((suspension_reason)::text, (((((((((((((((((((((((' 	
'::text || chr(28)) || chr(29)) || chr(30)) || chr(31)) || chr(133)) || chr(160)) || chr(5760)) || chr(8192)) || chr(8193)) || chr(8194)) || chr(8195)) || chr(8196)) || chr(8197)) || chr(8198)) || chr(8199)) || chr(8200)) || chr(8201)) || chr(8202)) || chr(8232)) || chr(8233)) || chr(8239)) || chr(8287)) || chr(12288)))) AND ((octet_length((suspension_reason)::text) >= 1) AND (octet_length((suspension_reason)::text) <= 500)))) AND ((reactivation_reason IS NULL) OR (((reactivation_reason)::text = btrim((reactivation_reason)::text, (((((((((((((((((((((((' 	
'::text || chr(28)) || chr(29)) || chr(30)) || chr(31)) || chr(133)) || chr(160)) || chr(5760)) || chr(8192)) || chr(8193)) || chr(8194)) || chr(8195)) || chr(8196)) || chr(8197)) || chr(8198)) || chr(8199)) || chr(8200)) || chr(8201)) || chr(8202)) || chr(8232)) || chr(8233)) || chr(8239)) || chr(8287)) || chr(12288)))) AND ((octet_length((reactivation_reason)::text) >= 1) AND (octet_length((reactivation_reason)::text) <= 500)))) AND ((deactivation_reason IS NULL) OR (((deactivation_reason)::text = btrim((deactivation_reason)::text, (((((((((((((((((((((((' 	
'::text || chr(28)) || chr(29)) || chr(30)) || chr(31)) || chr(133)) || chr(160)) || chr(5760)) || chr(8192)) || chr(8193)) || chr(8194)) || chr(8195)) || chr(8196)) || chr(8197)) || chr(8198)) || chr(8199)) || chr(8200)) || chr(8201)) || chr(8202)) || chr(8232)) || chr(8233)) || chr(8239)) || chr(8287)) || chr(12288)))) AND ((octet_length((deactivation_reason)::text) >= 1) AND (octet_length((deactivation_reason)::text) <= 500)))))),
    CONSTRAINT ck_actor_profiles_provisioning_method CHECK (((provisioning_method)::text = ANY ((ARRAY['automatic_first_access'::character varying, 'manual_service_provisioning'::character varying])::text[]))),
    CONSTRAINT ck_actor_profiles_reactivation_fields CHECK ((((reactivated_by IS NULL) AND (reactivated_at IS NULL) AND (reactivation_reason IS NULL)) OR ((reactivated_by IS NOT NULL) AND (reactivated_at IS NOT NULL) AND (reactivation_reason IS NOT NULL)))),
    CONSTRAINT ck_actor_profiles_status CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'suspended'::character varying, 'deactivated'::character varying])::text[])))
);
CREATE TABLE public.admin_role_grants (
    id uuid NOT NULL,
    target_actor_profile_id character varying(36) NOT NULL,
    role character varying(40) NOT NULL,
    scope_type character varying(16) NOT NULL,
    scope_project_id character varying(36),
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    version smallint DEFAULT '1'::smallint NOT NULL,
    granted_by_actor_profile_id character varying(36),
    granted_by_system_principal character varying(100),
    granted_by_admin_role_grant_id uuid,
    grant_reason text NOT NULL,
    granted_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    revoked_by_actor_profile_id character varying(36),
    revoked_by_admin_role_grant_id uuid,
    revoked_reason text,
    revoked_at timestamp with time zone,
    CONSTRAINT ck_admin_role_grants_grant_attribution CHECK (((((granted_by_system_principal)::text = 'workstream:system:bootstrap'::text) AND (granted_by_actor_profile_id IS NULL) AND (granted_by_admin_role_grant_id IS NULL)) OR ((granted_by_system_principal IS NULL) AND (granted_by_actor_profile_id IS NOT NULL) AND (granted_by_admin_role_grant_id IS NOT NULL)))),
    CONSTRAINT ck_admin_role_grants_grant_reason CHECK (((octet_length(grant_reason) >= 1) AND (octet_length(grant_reason) <= 500))),
    CONSTRAINT ck_admin_role_grants_lifecycle CHECK (((((status)::text = 'active'::text) AND (version = 1) AND (revoked_by_actor_profile_id IS NULL) AND (revoked_by_admin_role_grant_id IS NULL) AND (revoked_reason IS NULL) AND (revoked_at IS NULL)) OR (((status)::text = 'revoked'::text) AND (version = 2) AND (revoked_by_actor_profile_id IS NOT NULL) AND (revoked_by_admin_role_grant_id IS NOT NULL) AND (revoked_reason IS NOT NULL) AND ((octet_length(revoked_reason) >= 1) AND (octet_length(revoked_reason) <= 500)) AND (revoked_at IS NOT NULL)))),
    CONSTRAINT ck_admin_role_grants_role CHECK (((role)::text = ANY ((ARRAY['access_administrator'::character varying, 'operator'::character varying, 'project_manager'::character varying, 'finance_authority'::character varying, 'audit_authority'::character varying])::text[]))),
    CONSTRAINT ck_admin_role_grants_role_scope CHECK (((((scope_type)::text = 'system'::text) AND (scope_project_id IS NULL)) OR (((scope_type)::text = 'project'::text) AND (scope_project_id IS NOT NULL) AND ((role)::text <> ALL ((ARRAY['access_administrator'::character varying, 'operator'::character varying])::text[]))))),
    CONSTRAINT ck_admin_role_grants_scope_type CHECK (((scope_type)::text = ANY ((ARRAY['system'::character varying, 'project'::character varying])::text[])))
);
CREATE TABLE public.api_rate_control_counters (
    control_scope character varying(32) NOT NULL,
    key_digest bytea NOT NULL,
    window_started_at timestamp with time zone NOT NULL,
    window_expires_at timestamp with time zone NOT NULL,
    request_count bigint NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_api_rate_control_counters_digest_length CHECK ((octet_length(key_digest) = 32)),
    CONSTRAINT ck_api_rate_control_counters_request_count CHECK (((request_count >= 1) AND (request_count <= '9223372036854775807'::bigint))),
    CONSTRAINT ck_api_rate_control_counters_scope_token CHECK (((control_scope)::text = ANY ((ARRAY['first_access'::character varying, 'admin_mutation'::character varying, 'authorization_read'::character varying])::text[]))),
    CONSTRAINT ck_api_rate_control_counters_window_order CHECK ((window_started_at < window_expires_at))
);
CREATE TABLE public.artifact_admission_charges (
    id character varying(36) NOT NULL,
    scope_type character varying(20) NOT NULL,
    scope_id character varying(120) NOT NULL,
    sha256 character varying(71) NOT NULL,
    byte_count bigint NOT NULL,
    producer_type character varying(30) NOT NULL,
    producer_ref character varying(120) NOT NULL,
    creating_operation_identity character varying(71) NOT NULL,
    state character varying(20) DEFAULT 'provisional'::character varying NOT NULL,
    cas_version bigint DEFAULT '0'::bigint NOT NULL,
    reserved_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    released_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_artifact_admission_charges_byte_count_nonnegative CHECK ((byte_count >= 0)),
    CONSTRAINT ck_artifact_admission_charges_cas_nonnegative CHECK ((cas_version >= 0)),
    CONSTRAINT ck_artifact_admission_charges_completed_timestamp CHECK ((((state)::text = 'completed'::text) = (completed_at IS NOT NULL))),
    CONSTRAINT ck_artifact_admission_charges_operation_identity_shape CHECK (((creating_operation_identity)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_admission_charges_producer_type CHECK (((producer_type)::text = ANY ((ARRAY['actor_profile'::character varying, 'service_identity'::character varying])::text[]))),
    CONSTRAINT ck_artifact_admission_charges_released_timestamp CHECK ((((state)::text = 'released'::text) = (released_at IS NOT NULL))),
    CONSTRAINT ck_artifact_admission_charges_sha256_shape CHECK (((sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_admission_charges_state CHECK (((state)::text = ANY ((ARRAY['provisional'::character varying, 'completed'::character varying, 'released'::character varying])::text[])))
);
CREATE TABLE public.artifact_admission_scopes (
    scope_type character varying(20) NOT NULL,
    scope_id character varying(120) NOT NULL,
    limit_bytes bigint NOT NULL,
    counted_bytes bigint DEFAULT '0'::bigint NOT NULL,
    cas_version bigint DEFAULT '0'::bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_artifact_admission_scopes_cas_nonnegative CHECK ((cas_version >= 0)),
    CONSTRAINT ck_artifact_admission_scopes_counted_bytes_within_limit CHECK (((counted_bytes >= 0) AND (counted_bytes <= limit_bytes))),
    CONSTRAINT ck_artifact_admission_scopes_limit_positive CHECK ((limit_bytes > 0)),
    CONSTRAINT ck_artifact_admission_scopes_scope_id_bounds CHECK (((octet_length((scope_id)::text) >= 1) AND (octet_length((scope_id)::text) <= 120))),
    CONSTRAINT ck_artifact_admission_scopes_scope_type CHECK (((scope_type)::text = ANY ((ARRAY['deployment'::character varying, 'project'::character varying, 'producer'::character varying, 'task'::character varying])::text[])))
);
CREATE TABLE public.artifact_bindings (
    id character varying(36) NOT NULL,
    content_id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    resource_type character varying(80) NOT NULL,
    resource_id character varying(100) NOT NULL,
    logical_role character varying(100) NOT NULL,
    scope_version integer NOT NULL,
    actor_id character varying(100) NOT NULL,
    attribution_type character varying(30) NOT NULL,
    supersedes_binding_id character varying(36),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_artifact_bindings_scope_version_positive CHECK ((scope_version > 0)),
    CONSTRAINT ck_artifact_bindings_scope_version_predecessor CHECK ((((scope_version = 1) AND (supersedes_binding_id IS NULL)) OR ((scope_version > 1) AND (supersedes_binding_id IS NOT NULL))))
);
CREATE TABLE public.artifact_contents (
    id character varying(36) NOT NULL,
    sha256 character varying(71) NOT NULL,
    byte_count integer NOT NULL,
    media_type character varying(200),
    normalized_display_name character varying(500),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_artifact_contents_byte_count_nonnegative CHECK ((byte_count >= 0)),
    CONSTRAINT ck_artifact_contents_sha256_shape CHECK (((sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text))
);
CREATE TABLE public.artifact_operation_receipts (
    id character varying(36) NOT NULL,
    replica_id character varying(36) NOT NULL,
    operation character varying(30) NOT NULL,
    idempotency_key character varying(200) NOT NULL,
    request_digest character varying(71) NOT NULL,
    provider_object_ref character varying(1024) NOT NULL,
    replayed boolean NOT NULL,
    outcome character varying(30) NOT NULL,
    attempt_number integer NOT NULL,
    correlation_id character varying(100) NOT NULL,
    details json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    contract_version integer DEFAULT 1 NOT NULL,
    put_attempt_id character varying(36) NOT NULL,
    guide_source_item_id character varying(36),
    checker_run_id character varying(36),
    logical_role character varying(100),
    CONSTRAINT ck_artifact_operation_receipts_attempt_positive CHECK ((attempt_number > 0)),
    CONSTRAINT ck_artifact_operation_receipts_contract_producer_reference CHECK (((contract_version = 2) AND (put_attempt_id IS NOT NULL) AND (((guide_source_item_id IS NOT NULL) AND (checker_run_id IS NULL) AND (logical_role IS NULL)) OR ((guide_source_item_id IS NULL) AND (checker_run_id IS NOT NULL) AND ((octet_length((logical_role)::text) >= 1) AND (octet_length((logical_role)::text) <= 100))) OR ((guide_source_item_id IS NULL) AND (checker_run_id IS NULL) AND (logical_role IS NULL))))),
    CONSTRAINT ck_artifact_operation_receipts_operation CHECK (((operation)::text = 'put'::text)),
    CONSTRAINT ck_artifact_operation_receipts_outcome CHECK (((outcome)::text = 'stored_pending_verification'::text)),
    CONSTRAINT ck_artifact_operation_receipts_request_digest_shape CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text))
);
CREATE TABLE public.artifact_put_attempt_charges (
    attempt_id character varying(36) NOT NULL,
    charge_id character varying(36) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.artifact_put_attempts (
    id character varying(36) NOT NULL,
    producer_request_type character varying(30) NOT NULL,
    producer_type character varying(30) NOT NULL,
    producer_ref character varying(120) NOT NULL,
    project_id character varying(36) NOT NULL,
    task_id character varying(36),
    guide_source_item_id character varying(36),
    checker_run_id character varying(36),
    logical_role character varying(100),
    sha256 character varying(71) NOT NULL,
    byte_count bigint NOT NULL,
    media_type character varying(255) NOT NULL,
    storage_namespace_id character varying(20) NOT NULL,
    namespace_fingerprint character varying(71) NOT NULL,
    canonical_target character varying(1024) NOT NULL,
    operation_identity character varying(71) NOT NULL,
    request_digest character varying(71) NOT NULL,
    status character varying(40) DEFAULT 'prepared'::character varying NOT NULL,
    next_run_at timestamp with time zone,
    executor_id character varying(36),
    lease_expires_at timestamp with time zone,
    execution_generation bigint DEFAULT '0'::bigint NOT NULL,
    terminal_result_code character varying(100),
    replica_id character varying(36),
    receipt_id character varying(36),
    cas_version bigint DEFAULT '0'::bigint NOT NULL,
    prepared_at timestamp with time zone DEFAULT now() NOT NULL,
    terminal_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    execution_mode character varying(20),
    observation_count bigint DEFAULT '0'::bigint NOT NULL,
    maximum_observations bigint DEFAULT '5'::bigint NOT NULL,
    CONSTRAINT ck_artifact_put_attempts_byte_count_nonnegative CHECK ((byte_count >= 0)),
    CONSTRAINT ck_artifact_put_attempts_canonical_target_shape CHECK (((canonical_target)::text ~ '^sha256/[0-9a-f]{2}/[0-9a-f]{62}$'::text)),
    CONSTRAINT ck_artifact_put_attempts_execution_mode CHECK (((execution_mode IS NULL) OR ((execution_mode)::text = ANY ((ARRAY['caller_put'::character varying, 'observation'::character varying])::text[])))),
    CONSTRAINT ck_artifact_put_attempts_executor_lease_pair CHECK (((executor_id IS NULL) = (lease_expires_at IS NULL))),
    CONSTRAINT ck_artifact_put_attempts_inflight_fence CHECK ((((status)::text = 'put_in_flight'::text) = (executor_id IS NOT NULL))),
    CONSTRAINT ck_artifact_put_attempts_observation_counts CHECK (((observation_count >= 0) AND (maximum_observations > 0))),
    CONSTRAINT ck_artifact_put_attempts_operation_identity_shape CHECK (((operation_identity)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_put_attempts_prepared_execution_inactive CHECK ((((status)::text <> 'prepared'::text) OR ((next_run_at IS NULL) AND (executor_id IS NULL) AND (lease_expires_at IS NULL) AND (execution_generation = 0) AND (terminal_result_code IS NULL) AND (terminal_at IS NULL) AND (replica_id IS NULL) AND (receipt_id IS NULL)))),
    CONSTRAINT ck_artifact_put_attempts_producer_identity CHECK (((((producer_request_type)::text = 'guide'::text) AND ((producer_type)::text = 'actor_profile'::text) AND ((producer_ref)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'::text)) OR (((producer_request_type)::text = 'checker_output'::text) AND ((producer_type)::text = 'service_identity'::text) AND ((producer_ref)::text = 'workstream.artifact.checker_output'::text)) OR (((producer_request_type)::text = 'submission_bundle'::text) AND ((producer_type)::text = 'actor_profile'::text) AND ((producer_ref)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'::text)))),
    CONSTRAINT ck_artifact_put_attempts_producer_reference CHECK (((((producer_request_type)::text = 'guide'::text) AND (guide_source_item_id IS NOT NULL) AND (checker_run_id IS NULL) AND (task_id IS NULL) AND (logical_role IS NULL)) OR (((producer_request_type)::text = 'checker_output'::text) AND (guide_source_item_id IS NULL) AND (checker_run_id IS NOT NULL) AND (task_id IS NOT NULL) AND ((octet_length((logical_role)::text) >= 1) AND (octet_length((logical_role)::text) <= 100))) OR (((producer_request_type)::text = 'submission_bundle'::text) AND (guide_source_item_id IS NULL) AND (checker_run_id IS NULL) AND (task_id IS NOT NULL) AND (logical_role IS NULL)))),
    CONSTRAINT ck_artifact_put_attempts_producer_request_type CHECK (((producer_request_type)::text = ANY ((ARRAY['guide'::character varying, 'checker_output'::character varying, 'submission_bundle'::character varying])::text[]))),
    CONSTRAINT ck_artifact_put_attempts_producer_type CHECK (((producer_type)::text = ANY ((ARRAY['actor_profile'::character varying, 'service_identity'::character varying])::text[]))),
    CONSTRAINT ck_artifact_put_attempts_request_digest_shape CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_put_attempts_sha256_shape CHECK (((sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_put_attempts_status CHECK (((status)::text = ANY ((ARRAY['prepared'::character varying, 'put_in_flight'::character varying, 'acknowledgement_unknown'::character varying, 'object_confirmed'::character varying, 'absent_replay_required'::character varying, 'integrity_mismatch'::character varying, 'provider_unavailable'::character varying, 'conflict'::character varying])::text[]))),
    CONSTRAINT ck_artifact_put_attempts_unavailable_exhausted CHECK ((((status)::text <> 'provider_unavailable'::text) OR ((observation_count >= maximum_observations) AND (next_run_at IS NULL) AND (terminal_at IS NOT NULL)))),
    CONSTRAINT ck_artifact_put_attempts_versions_nonnegative CHECK (((execution_generation >= 0) AND (cas_version >= 0)))
);
CREATE TABLE public.artifact_put_observation_receipts (
    id character varying(36) NOT NULL,
    put_attempt_id character varying(36) NOT NULL,
    execution_generation bigint NOT NULL,
    outcome character varying(40) NOT NULL,
    expected_sha256 character varying(71) NOT NULL,
    expected_byte_count bigint NOT NULL,
    observed_sha256 character varying(71),
    observed_byte_count bigint,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT ck_artifact_put_observation_receipts_expected_sha256 CHECK (((expected_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_put_observation_receipts_expected_size CHECK ((expected_byte_count >= 0)),
    CONSTRAINT ck_artifact_put_observation_receipts_observed_facts CHECK ((((outcome)::text = ANY ((ARRAY['observed_confirmed'::character varying, 'observed_integrity_mismatch'::character varying])::text[])) = ((observed_sha256 IS NOT NULL) AND (observed_byte_count IS NOT NULL)))),
    CONSTRAINT ck_artifact_put_observation_receipts_observed_sha256 CHECK (((observed_sha256 IS NULL) OR ((observed_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_artifact_put_observation_receipts_observed_size CHECK (((observed_byte_count IS NULL) OR (observed_byte_count >= 0))),
    CONSTRAINT ck_artifact_put_observation_receipts_outcome CHECK (((outcome)::text = ANY ((ARRAY['observed_confirmed'::character varying, 'observed_missing'::character varying, 'observed_integrity_mismatch'::character varying, 'conflict'::character varying])::text[])))
);
CREATE TABLE public.artifact_recovery_attempts (
    id character varying(36) NOT NULL,
    requester_actor_profile_id character varying(36) NOT NULL,
    requester_identity_link_id character varying(36) NOT NULL,
    authorization_request_id character varying(36) NOT NULL,
    authorization_correlation_id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    task_id character varying(36),
    submission_id character varying(36),
    source_verification_job_id character varying(36) NOT NULL,
    retry_verification_job_id character varying(36) NOT NULL,
    parent_recovery_attempt_id character varying(36),
    recovery_class character varying(40) NOT NULL,
    reason character varying(1000) NOT NULL,
    client_idempotency_key character varying(200) NOT NULL,
    request_digest character varying(71) NOT NULL,
    status character varying(20) DEFAULT 'requested'::character varying NOT NULL,
    terminal_result_code character varying(40),
    initiation_audit_event_id character varying(36) NOT NULL,
    terminal_audit_event_id character varying(36),
    cas_version bigint DEFAULT '0'::bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    terminal_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT ck_artifact_recovery_attempts_cas_nonnegative CHECK ((cas_version >= 0)),
    CONSTRAINT ck_artifact_recovery_attempts_distinct_jobs CHECK (((source_verification_job_id)::text <> (retry_verification_job_id)::text)),
    CONSTRAINT ck_artifact_recovery_attempts_recovery_class CHECK (((recovery_class)::text = 'provider_observation'::text)),
    CONSTRAINT ck_artifact_recovery_attempts_request_digest CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_recovery_attempts_status CHECK (((status)::text = ANY ((ARRAY['requested'::character varying, 'succeeded'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT ck_artifact_recovery_attempts_terminal_result CHECK (((((status)::text = 'succeeded'::text) AND ((terminal_result_code)::text = 'verified'::text)) OR (((status)::text = 'failed'::text) AND ((terminal_result_code)::text = ANY ((ARRAY['provider_unavailable'::character varying, 'missing'::character varying, 'integrity_mismatch'::character varying, 'conflict'::character varying])::text[]))) OR ((status)::text = 'requested'::text))),
    CONSTRAINT ck_artifact_recovery_attempts_terminal_shape CHECK (((((status)::text = 'requested'::text) AND (terminal_result_code IS NULL) AND (terminal_at IS NULL) AND (terminal_audit_event_id IS NULL)) OR (((status)::text = ANY ((ARRAY['succeeded'::character varying, 'failed'::character varying])::text[])) AND (terminal_result_code IS NOT NULL) AND (terminal_at IS NOT NULL) AND (terminal_audit_event_id IS NOT NULL))))
);
CREATE TABLE public.artifact_replicas (
    id character varying(36) NOT NULL,
    content_id character varying(36) NOT NULL,
    adapter character varying(50) NOT NULL,
    provider_object_ref character varying(1024) NOT NULL,
    verification_state character varying(30) NOT NULL,
    availability_state character varying(30) NOT NULL,
    integrity_state character varying(30) NOT NULL,
    last_reconciled_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    storage_namespace_id character varying(20) NOT NULL,
    namespace_fingerprint character varying(71) NOT NULL,
    provider_profile character varying(100) NOT NULL,
    CONSTRAINT ck_artifact_replicas_availability_state CHECK (((availability_state)::text = ANY ((ARRAY['unknown'::character varying, 'available'::character varying, 'unavailable'::character varying])::text[]))),
    CONSTRAINT ck_artifact_replicas_fingerprint_shape CHECK (((namespace_fingerprint)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_replicas_integrity_state CHECK (((integrity_state)::text = ANY ((ARRAY['unknown'::character varying, 'valid'::character varying, 'invalid'::character varying])::text[]))),
    CONSTRAINT ck_artifact_replicas_verification_state CHECK (((verification_state)::text = ANY ((ARRAY['pending'::character varying, 'verified'::character varying, 'missing'::character varying, 'integrity_mismatch'::character varying])::text[])))
);
CREATE TABLE public.artifact_storage_namespaces (
    id character varying(20) NOT NULL,
    backend character varying(50) NOT NULL,
    adapter character varying(50) NOT NULL,
    provider_profile character varying(100) NOT NULL,
    namespace_descriptor json NOT NULL,
    namespace_fingerprint character varying(71) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_artifact_storage_namespaces_fingerprint_shape CHECK (((namespace_fingerprint)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_storage_namespaces_singleton_id CHECK (((id)::text = 'primary'::text))
);
CREATE TABLE public.artifact_verification_jobs (
    id character varying(36) NOT NULL,
    originating_put_attempt_id character varying(36) NOT NULL,
    replica_id character varying(36) NOT NULL,
    status character varying(40) DEFAULT 'pending'::character varying NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    maximum_attempts integer NOT NULL,
    next_run_at timestamp with time zone,
    executor_id character varying(36),
    lease_expires_at timestamp with time zone,
    execution_generation bigint DEFAULT '0'::bigint NOT NULL,
    cas_version bigint DEFAULT '0'::bigint NOT NULL,
    terminal_result_code character varying(100),
    terminal_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    parent_verification_job_id character varying(36),
    CONSTRAINT ck_artifact_verification_jobs_attempts CHECK (((attempt_count >= 0) AND (maximum_attempts > 0))),
    CONSTRAINT ck_artifact_verification_jobs_fence_pair CHECK (((executor_id IS NULL) = (lease_expires_at IS NULL))),
    CONSTRAINT ck_artifact_verification_jobs_running_fence CHECK ((((status)::text = 'running'::text) = (executor_id IS NOT NULL))),
    CONSTRAINT ck_artifact_verification_jobs_status CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'running'::character varying, 'verified'::character varying, 'missing'::character varying, 'integrity_mismatch'::character varying, 'provider_unavailable'::character varying, 'conflict'::character varying])::text[]))),
    CONSTRAINT ck_artifact_verification_jobs_unavailable_retryability CHECK ((((status)::text <> 'provider_unavailable'::text) OR (((next_run_at IS NOT NULL) AND (terminal_at IS NULL) AND (attempt_count < maximum_attempts)) OR ((next_run_at IS NULL) AND (terminal_at IS NOT NULL) AND (attempt_count >= maximum_attempts))))),
    CONSTRAINT ck_artifact_verification_jobs_versions CHECK (((execution_generation >= 0) AND (cas_version >= 0)))
);
CREATE TABLE public.artifact_verification_receipts (
    id character varying(36) NOT NULL,
    verification_job_id character varying(36) NOT NULL,
    execution_generation bigint NOT NULL,
    outcome character varying(40) NOT NULL,
    observed_sha256 character varying(71),
    observed_byte_count bigint,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT ck_artifact_verification_receipts_observed_facts CHECK ((((outcome)::text = ANY ((ARRAY['verified'::character varying, 'integrity_mismatch'::character varying])::text[])) = ((observed_sha256 IS NOT NULL) AND (observed_byte_count IS NOT NULL)))),
    CONSTRAINT ck_artifact_verification_receipts_observed_sha256 CHECK (((observed_sha256 IS NULL) OR ((observed_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_artifact_verification_receipts_observed_size CHECK (((observed_byte_count IS NULL) OR (observed_byte_count >= 0))),
    CONSTRAINT ck_artifact_verification_receipts_outcome CHECK (((outcome)::text = ANY ((ARRAY['verified'::character varying, 'missing'::character varying, 'integrity_mismatch'::character varying, 'conflict'::character varying])::text[])))
);
CREATE TABLE public.audit_events (
    id character varying(36) NOT NULL,
    entity_type character varying(80) NOT NULL,
    entity_id character varying(36) NOT NULL,
    event_type character varying(100) NOT NULL,
    from_status character varying(30),
    to_status character varying(30),
    actor_id character varying(100) NOT NULL,
    external_subject character varying(200),
    external_issuer character varying(200),
    actor_roles json NOT NULL,
    claim_snapshot json NOT NULL,
    auth_source character varying(30) NOT NULL,
    is_dev_auth boolean NOT NULL,
    reason text,
    event_payload json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    event_domain character varying(24) DEFAULT 'legacy_lifecycle'::character varying NOT NULL,
    event_version integer,
    occurred_at timestamp with time zone,
    actor_ref_kind character varying(32),
    request_id uuid,
    correlation_id uuid,
    target_actor_ref_kind character varying(32),
    target_actor_ref character varying(100),
    matched_grant_id character varying(100),
    permission_id character varying(120),
    project_id character varying(36),
    resource_type character varying(80),
    resource_id character varying(100),
    target_ref_kind character varying(32),
    target_ref_id character varying(100),
    denial_code character varying(80),
    idempotency_reference uuid,
    invalidation_cause_event_id character varying(36),
    invalidation_target_kind character varying(32),
    invalidation_target_ref character varying(100),
    before_facts json,
    after_facts json,
    action_id character varying(160),
    CONSTRAINT ck_audit_events_authority_privacy_bounds CHECK ((((event_domain)::text <> 'authority'::text) OR (((id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text) AND ((entity_type)::text = ANY (ARRAY[('actor_profile'::character varying)::text, ('actor_identity_link'::character varying)::text, ('admin_role_grant'::character varying)::text, ('qualification_snapshot'::character varying)::text, ('project_role_grant'::character varying)::text, ('authorization_decision'::character varying)::text, ('authority_invalidation'::character varying)::text])) AND ((entity_id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text) AND ((((actor_ref_kind)::text = ANY (ARRAY[('legacy_actor'::character varying)::text, ('actor_profile'::character varying)::text])) AND ((actor_id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)) OR (((actor_ref_kind)::text = 'system_principal'::text) AND ((actor_id)::text = 'workstream:system:bootstrap'::text))) AND ((target_actor_ref IS NULL) OR (((target_actor_ref_kind)::text = 'actor_profile'::text) AND ((target_actor_ref)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text))) AND ((matched_grant_id IS NULL) OR ((matched_grant_id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)) AND ((project_id IS NULL) OR ((project_id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)) AND ((resource_type IS NULL) OR ((resource_type)::text = ANY (ARRAY[('actor_profile'::character varying)::text, ('actor_identity_link'::character varying)::text, ('admin_role_grant'::character varying)::text, ('project'::character varying)::text, ('qualification_snapshot'::character varying)::text, ('project_role_grant'::character varying)::text, ('task'::character varying)::text, ('submission'::character varying)::text, ('review'::character varying)::text, ('contribution'::character varying)::text, ('compensation_award'::character varying)::text, ('compensation_delivery'::character varying)::text, ('operations'::character varying)::text, ('audit_event'::character varying)::text, ('project_create_operation'::character varying)::text, ('project_submission_artifact_policy_mutation'::character varying)::text, ('project_guide_compilation_attempt'::character varying)::text, ('project_guide_compilation_request'::character varying)::text]))) AND ((resource_id IS NULL) OR ((resource_id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)) AND ((target_ref_kind IS NULL) OR (((target_ref_kind)::text = ANY (ARRAY[('actor_profile'::character varying)::text, ('actor_identity_link'::character varying)::text, ('admin_role_grant'::character varying)::text, ('qualification_snapshot'::character varying)::text, ('project_role_grant'::character varying)::text, ('project'::character varying)::text])) AND ((target_ref_id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)) OR (((target_ref_kind)::text = 'permission_registry'::text) AND ((target_ref_id)::text = ANY (ARRAY[('actor.profile.read_self'::character varying)::text, ('actor.profile.update_self'::character varying)::text, ('actor.profile.read_any'::character varying)::text, ('actor.profile.suspend'::character varying)::text, ('actor.profile.reactivate'::character varying)::text, ('actor.profile.deactivate'::character varying)::text, ('actor.identity_link.read'::character varying)::text, ('actor.identity_link.revoke'::character varying)::text, ('actor.identity_link.reactivate'::character varying)::text, ('actor.service.provision'::character varying)::text, ('admin_role.read'::character varying)::text, ('admin_role.grant'::character varying)::text, ('admin_role.revoke'::character varying)::text, ('project.create'::character varying)::text, ('project.read'::character varying)::text, ('project.update'::character varying)::text, ('project.archive'::character varying)::text, ('project.guide.manage'::character varying)::text, ('project.effective_policy.manage'::character varying)::text, ('project.task.manage'::character varying)::text, ('project.review_policy.manage'::character varying)::text, ('project.role_grant.read'::character varying)::text, ('project.role_grant.manage'::character varying)::text, ('project.setup_diagnostic.read'::character varying)::text, ('project.effective_policy.read'::character varying)::text, ('task.queue.read'::character varying)::text, ('task.claim'::character varying)::text, ('submission.create'::character varying)::text, ('submission.read_own'::character varying)::text, ('submission.read_for_review'::character varying)::text, ('review.queue.read'::character varying)::text, ('review.queue.inspect'::character varying)::text, ('review.claim'::character varying)::text, ('review.release'::character varying)::text, ('review.decline_preference'::character varying)::text, ('review.decision'::character varying)::text, ('review.lease.force_release'::character varying)::text, ('review.chain.read'::character varying)::text, ('contribution.read_self'::character varying)::text, ('contribution.read_project'::character varying)::text, ('compensation.policy.manage'::character varying)::text, ('compensation.adapter_binding.manage'::character varying)::text, ('compensation.award.read'::character varying)::text, ('compensation.delivery.reconcile'::character varying)::text, ('operations.status.read'::character varying)::text, ('operations.timer.run'::character varying)::text, ('operations.reconcile.run'::character varying)::text, ('operations.outbox.retry'::character varying)::text, ('operations.projection.rebuild'::character varying)::text, ('audit.read'::character varying)::text, ('audit.export'::character varying)::text, ('operations.task.start_override'::character varying)::text, ('operations.submission_gate.repair'::character varying)::text, ('operations.checker.retry'::character varying)::text, ('artifact.binding.read'::character varying)::text, ('artifact.replica.read'::character varying)::text, ('artifact.receipt.read'::character varying)::text, ('artifact.verification_job.read'::character varying)::text, ('artifact.verification_job.retry'::character varying)::text, ('artifact.recovery_attempt.read'::character varying)::text, ('artifact.audit.read'::character varying)::text, ('artifact.guide_source.ingest'::character varying)::text, ('artifact.binding.create'::character varying)::text, ('artifact.review_packet.materialize'::character varying)::text, ('artifact.verification.execute'::character varying)::text, ('artifact.pending_work.scan'::character varying)::text, ('artifact.put_attempt.resolve'::character varying)::text, ('artifact.guide_source.read'::character varying)::text, ('artifact.checker_input.materialize'::character varying)::text, ('artifact.checker_output.write'::character varying)::text, ('review.queue.override'::character varying)::text, ('project.guide_compilation.request'::character varying)::text, ('project.guide_compilation.execute'::character varying)::text])))) AND ((invalidation_target_kind IS NULL) OR (((invalidation_target_kind)::text = ANY (ARRAY[('actor_profile'::character varying)::text, ('actor_identity_link'::character varying)::text, ('admin_role_grant'::character varying)::text, ('qualification_snapshot'::character varying)::text, ('project_role_grant'::character varying)::text])) AND ((invalidation_target_ref)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)) OR (((invalidation_target_kind)::text = 'permission_registry'::text) AND ((invalidation_target_ref)::text = ANY (ARRAY[('actor.profile.read_self'::character varying)::text, ('actor.profile.update_self'::character varying)::text, ('actor.profile.read_any'::character varying)::text, ('actor.profile.suspend'::character varying)::text, ('actor.profile.reactivate'::character varying)::text, ('actor.profile.deactivate'::character varying)::text, ('actor.identity_link.read'::character varying)::text, ('actor.identity_link.revoke'::character varying)::text, ('actor.identity_link.reactivate'::character varying)::text, ('actor.service.provision'::character varying)::text, ('admin_role.read'::character varying)::text, ('admin_role.grant'::character varying)::text, ('admin_role.revoke'::character varying)::text, ('project.create'::character varying)::text, ('project.read'::character varying)::text, ('project.update'::character varying)::text, ('project.archive'::character varying)::text, ('project.guide.manage'::character varying)::text, ('project.effective_policy.manage'::character varying)::text, ('project.task.manage'::character varying)::text, ('project.review_policy.manage'::character varying)::text, ('project.role_grant.read'::character varying)::text, ('project.role_grant.manage'::character varying)::text, ('project.setup_diagnostic.read'::character varying)::text, ('project.effective_policy.read'::character varying)::text, ('task.queue.read'::character varying)::text, ('task.claim'::character varying)::text, ('submission.create'::character varying)::text, ('submission.read_own'::character varying)::text, ('submission.read_for_review'::character varying)::text, ('review.queue.read'::character varying)::text, ('review.queue.inspect'::character varying)::text, ('review.claim'::character varying)::text, ('review.release'::character varying)::text, ('review.decline_preference'::character varying)::text, ('review.decision'::character varying)::text, ('review.lease.force_release'::character varying)::text, ('review.chain.read'::character varying)::text, ('contribution.read_self'::character varying)::text, ('contribution.read_project'::character varying)::text, ('compensation.policy.manage'::character varying)::text, ('compensation.adapter_binding.manage'::character varying)::text, ('compensation.award.read'::character varying)::text, ('compensation.delivery.reconcile'::character varying)::text, ('operations.status.read'::character varying)::text, ('operations.timer.run'::character varying)::text, ('operations.reconcile.run'::character varying)::text, ('operations.outbox.retry'::character varying)::text, ('operations.projection.rebuild'::character varying)::text, ('audit.read'::character varying)::text, ('audit.export'::character varying)::text, ('operations.task.start_override'::character varying)::text, ('operations.submission_gate.repair'::character varying)::text, ('operations.checker.retry'::character varying)::text, ('artifact.binding.read'::character varying)::text, ('artifact.replica.read'::character varying)::text, ('artifact.receipt.read'::character varying)::text, ('artifact.verification_job.read'::character varying)::text, ('artifact.verification_job.retry'::character varying)::text, ('artifact.recovery_attempt.read'::character varying)::text, ('artifact.audit.read'::character varying)::text, ('artifact.guide_source.ingest'::character varying)::text, ('artifact.binding.create'::character varying)::text, ('artifact.review_packet.materialize'::character varying)::text, ('artifact.verification.execute'::character varying)::text, ('artifact.pending_work.scan'::character varying)::text, ('artifact.put_attempt.resolve'::character varying)::text, ('artifact.guide_source.read'::character varying)::text, ('artifact.checker_input.materialize'::character varying)::text, ('artifact.checker_output.write'::character varying)::text, ('review.queue.override'::character varying)::text, ('project.guide_compilation.request'::character varying)::text, ('project.guide_compilation.execute'::character varying)::text])))) AND (((entity_type)::text <> ALL (ARRAY[('authorization_decision'::character varying)::text, ('authority_invalidation'::character varying)::text])) OR ((entity_id)::text = (id)::text)) AND (((resource_type)::text <> 'project'::text) OR (resource_id IS NULL) OR ((project_id IS NOT NULL) AND ((resource_id)::text = (project_id)::text)))))),
    CONSTRAINT ck_audit_events_authority_registries CHECK ((((event_domain)::text <> 'authority'::text) OR ((reason IS NOT NULL) AND ((((event_type)::text = 'ActorProfileProvisioned'::text) AND (reason = 'automatic_first_access'::text)) OR (((event_type)::text = 'ServiceActorProvisioned'::text) AND (reason = 'manual_service_provisioning'::text)) OR (((event_type)::text = 'ActorIdentityLinked'::text) AND (reason = 'identity_lifecycle_change'::text)) OR (((event_type)::text = 'ActorIdentityLinkRevoked'::text) AND (reason = 'identity_lifecycle_change'::text)) OR (((event_type)::text = 'ActorIdentityLinkReactivated'::text) AND (reason = 'identity_lifecycle_change'::text)) OR (((event_type)::text = 'ActorProfileSuspended'::text) AND (reason = ANY (ARRAY['security_response'::text, 'administrative_correction'::text]))) OR (((event_type)::text = 'ActorProfileReactivated'::text) AND (reason = 'administrative_correction'::text)) OR (((event_type)::text = 'ActorProfileDeactivated'::text) AND (reason = ANY (ARRAY['security_response'::text, 'administrative_correction'::text]))) OR (((event_type)::text = 'InitialAccessAdministratorBootstrapped'::text) AND (reason = 'initial_access_bootstrap'::text)) OR (((event_type)::text = 'AdminRoleGrantIssued'::text) AND (reason = 'authority_assignment'::text)) OR (((event_type)::text = 'AdminRoleGrantRevoked'::text) AND (reason = 'authority_revocation'::text)) OR (((event_type)::text = 'AdminRoleGrantIssueDenied'::text) AND (reason = 'authorization_policy_denial'::text)) OR (((event_type)::text = 'LastAccessAdministratorOperationDenied'::text) AND (reason = 'authorization_policy_denial'::text)) OR (((event_type)::text = 'ProjectRoleQualificationSnapshotCaptured'::text) AND (reason = 'qualification_evidence_captured'::text)) OR (((event_type)::text = 'ProjectRoleGrantIssued'::text) AND (reason = 'authority_assignment'::text)) OR (((event_type)::text = 'ProjectRoleGrantRevoked'::text) AND (reason = 'authority_revocation'::text)) OR (((event_type)::text = 'SensitiveAuthorizationAllowed'::text) AND (reason = 'authorization_evaluation'::text)) OR (((event_type)::text = 'SensitiveAuthorizationDenied'::text) AND (reason = 'authorization_evaluation'::text)) OR (((event_type)::text = 'AuthorityInvalidationRequested'::text) AND (reason = 'authority_state_changed'::text))) AND ((permission_id IS NULL) OR ((permission_id)::text = ANY (ARRAY[('actor.profile.read_self'::character varying)::text, ('actor.profile.update_self'::character varying)::text, ('actor.profile.read_any'::character varying)::text, ('actor.profile.suspend'::character varying)::text, ('actor.profile.reactivate'::character varying)::text, ('actor.profile.deactivate'::character varying)::text, ('actor.identity_link.read'::character varying)::text, ('actor.identity_link.revoke'::character varying)::text, ('actor.identity_link.reactivate'::character varying)::text, ('actor.service.provision'::character varying)::text, ('admin_role.read'::character varying)::text, ('admin_role.grant'::character varying)::text, ('admin_role.revoke'::character varying)::text, ('project.create'::character varying)::text, ('project.read'::character varying)::text, ('project.update'::character varying)::text, ('project.archive'::character varying)::text, ('project.guide.manage'::character varying)::text, ('project.effective_policy.manage'::character varying)::text, ('project.task.manage'::character varying)::text, ('project.review_policy.manage'::character varying)::text, ('project.role_grant.read'::character varying)::text, ('project.role_grant.manage'::character varying)::text, ('project.setup_diagnostic.read'::character varying)::text, ('project.effective_policy.read'::character varying)::text, ('task.queue.read'::character varying)::text, ('task.claim'::character varying)::text, ('submission.create'::character varying)::text, ('submission.read_own'::character varying)::text, ('submission.read_for_review'::character varying)::text, ('review.queue.read'::character varying)::text, ('review.queue.inspect'::character varying)::text, ('review.claim'::character varying)::text, ('review.release'::character varying)::text, ('review.decline_preference'::character varying)::text, ('review.decision'::character varying)::text, ('review.lease.force_release'::character varying)::text, ('review.chain.read'::character varying)::text, ('contribution.read_self'::character varying)::text, ('contribution.read_project'::character varying)::text, ('compensation.policy.manage'::character varying)::text, ('compensation.adapter_binding.manage'::character varying)::text, ('compensation.award.read'::character varying)::text, ('compensation.delivery.reconcile'::character varying)::text, ('operations.status.read'::character varying)::text, ('operations.timer.run'::character varying)::text, ('operations.reconcile.run'::character varying)::text, ('operations.outbox.retry'::character varying)::text, ('operations.projection.rebuild'::character varying)::text, ('audit.read'::character varying)::text, ('audit.export'::character varying)::text, ('operations.task.start_override'::character varying)::text, ('operations.submission_gate.repair'::character varying)::text, ('operations.checker.retry'::character varying)::text, ('artifact.binding.read'::character varying)::text, ('artifact.replica.read'::character varying)::text, ('artifact.receipt.read'::character varying)::text, ('artifact.verification_job.read'::character varying)::text, ('artifact.verification_job.retry'::character varying)::text, ('artifact.recovery_attempt.read'::character varying)::text, ('artifact.audit.read'::character varying)::text, ('artifact.guide_source.ingest'::character varying)::text, ('artifact.binding.create'::character varying)::text, ('artifact.review_packet.materialize'::character varying)::text, ('artifact.verification.execute'::character varying)::text, ('artifact.pending_work.scan'::character varying)::text, ('artifact.put_attempt.resolve'::character varying)::text, ('artifact.guide_source.read'::character varying)::text, ('artifact.checker_input.materialize'::character varying)::text, ('artifact.checker_output.write'::character varying)::text, ('review.queue.override'::character varying)::text, ('project.guide_compilation.execute'::character varying)::text, ('project.guide_compilation.request'::character varying)::text]))) AND ((denial_code IS NULL) OR ((denial_code)::text = ANY (ARRAY[('required_scope_missing'::character varying)::text, ('unsupported_subject_kind'::character varying)::text, ('service_actor_not_provisioned'::character varying)::text, ('identity_link_revoked'::character varying)::text, ('actor_suspended'::character varying)::text, ('actor_deactivated'::character varying)::text, ('permission_not_granted'::character varying)::text, ('scope_not_authorized'::character varying)::text, ('self_grant_forbidden'::character varying)::text, ('self_role_revoke_forbidden'::character varying)::text, ('resource_guard_denied'::character varying)::text, ('actor_not_found'::character varying)::text, ('grant_not_found'::character varying)::text, ('resource_not_found'::character varying)::text, ('actor_already_suspended'::character varying)::text, ('actor_not_suspended'::character varying)::text, ('actor_deactivated_terminal'::character varying)::text, ('last_access_administrator'::character varying)::text, ('admin_role_grant_exists'::character varying)::text, ('project_role_grant_exists'::character varying)::text, ('identity_link_conflict'::character varying)::text, ('project_role_grant_already_revoked'::character varying)::text, ('project_role_grant_replay_state_changed'::character varying)::text, ('identity_link_already_revoked'::character varying)::text, ('identity_link_not_revoked'::character varying)::text, ('resource_project_mismatch'::character varying)::text, ('idempotency_mismatch'::character varying)::text, ('invalid_role_scope'::character varying)::text, ('invalid_project_role'::character varying)::text, ('qualification_snapshot_invalid'::character varying)::text])))))),
    CONSTRAINT ck_audit_events_authority_tokens CHECK ((((event_domain)::text <> 'authority'::text) OR ((event_type)::text = ANY ((ARRAY['ActorProfileProvisioned'::character varying, 'ServiceActorProvisioned'::character varying, 'ActorIdentityLinked'::character varying, 'ActorIdentityLinkRevoked'::character varying, 'ActorIdentityLinkReactivated'::character varying, 'ActorProfileSuspended'::character varying, 'ActorProfileReactivated'::character varying, 'ActorProfileDeactivated'::character varying, 'InitialAccessAdministratorBootstrapped'::character varying, 'AdminRoleGrantIssued'::character varying, 'AdminRoleGrantRevoked'::character varying, 'AdminRoleGrantIssueDenied'::character varying, 'LastAccessAdministratorOperationDenied'::character varying, 'ProjectRoleQualificationSnapshotCaptured'::character varying, 'ProjectRoleGrantIssued'::character varying, 'ProjectRoleGrantReplaced'::character varying, 'ProjectRoleGrantRevoked'::character varying, 'SensitiveAuthorizationAllowed'::character varying, 'SensitiveAuthorizationDenied'::character varying, 'AuthorityInvalidationRequested'::character varying])::text[])))),
    CONSTRAINT ck_audit_events_authorization_action_evidence CHECK (((((event_domain)::text = 'legacy_lifecycle'::text) AND (action_id IS NULL)) OR (((event_domain)::text = 'authority'::text) AND ((action_id IS NULL) OR (((event_type)::text = ANY (ARRAY[('SensitiveAuthorizationAllowed'::character varying)::text, ('SensitiveAuthorizationDenied'::character varying)::text])) AND (permission_id IS NOT NULL) AND ((((action_id)::text = 'actor.profile.read_self'::text) AND ((permission_id)::text = 'actor.profile.read_self'::text)) OR (((action_id)::text = 'actor.profile.update_self'::text) AND ((permission_id)::text = 'actor.profile.update_self'::text)) OR (((action_id)::text = 'operations.task.start_override'::text) AND ((permission_id)::text = 'operations.task.start_override'::text)) OR (((action_id)::text = 'operations.submission_gate.repair'::text) AND ((permission_id)::text = 'operations.submission_gate.repair'::text)) OR (((action_id)::text = 'operations.checker.retry'::text) AND ((permission_id)::text = 'operations.checker.retry'::text)) OR (((action_id)::text = 'submission.create'::text) AND ((permission_id)::text = 'submission.create'::text)) OR (((action_id)::text = 'review.queue.read'::text) AND ((permission_id)::text = 'review.queue.read'::text)) OR (((action_id)::text = 'review.queue.inspect'::text) AND ((permission_id)::text = 'review.queue.inspect'::text)) OR (((action_id)::text = 'review.claim'::text) AND ((permission_id)::text = 'review.claim'::text)) OR (((action_id)::text = 'review.release'::text) AND ((permission_id)::text = 'review.release'::text)) OR (((action_id)::text = 'review.decline_preference'::text) AND ((permission_id)::text = 'review.decline_preference'::text)) OR (((action_id)::text = 'review.preference_expiry.run'::text) AND ((permission_id)::text = 'operations.timer.run'::text)) OR (((action_id)::text = 'review.lease_expiry.run'::text) AND ((permission_id)::text = 'operations.timer.run'::text)) OR (((action_id)::text = 'review.context.read'::text) AND ((permission_id)::text = 'submission.read_for_review'::text)) OR (((action_id)::text = 'review.chain.read'::text) AND ((permission_id)::text = 'review.chain.read'::text)) OR (((action_id)::text = 'review.finding_evidence.ingest'::text) AND ((permission_id)::text = 'review.decision'::text)) OR (((action_id)::text = 'review.decision'::text) AND ((permission_id)::text = 'review.decision'::text)) OR (((action_id)::text = 'review.finding_response_evidence.ingest'::text) AND ((permission_id)::text = 'submission.create'::text)) OR (((action_id)::text = 'review.lease.force_release'::text) AND ((permission_id)::text = 'review.lease.force_release'::text)) OR (((action_id)::text = 'review.queue.routing.override'::text) AND ((permission_id)::text = 'review.queue.override'::text)) OR (((action_id)::text = 'review.queue.routing.correct'::text) AND ((permission_id)::text = 'review.queue.override'::text)) OR (((action_id)::text = 'review.queue.close'::text) AND ((permission_id)::text = 'review.queue.override'::text)) OR (((action_id)::text = 'review.reconcile.run'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'review.artifact_reference.reconcile'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'review.projection.rebuild'::text) AND ((permission_id)::text = 'operations.projection.rebuild'::text)) OR (((action_id)::text = 'review.revision_context.repair'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'review.revision_obligation.close'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'review.revision_context.legacy_close'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'review.lifecycle.activation.manage'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'artifact.binding.read'::text) AND ((permission_id)::text = 'artifact.binding.read'::text)) OR (((action_id)::text = 'artifact.replica.read'::text) AND ((permission_id)::text = 'artifact.replica.read'::text)) OR (((action_id)::text = 'artifact.receipt.read'::text) AND ((permission_id)::text = 'artifact.receipt.read'::text)) OR (((action_id)::text = 'artifact.verification_job.read'::text) AND ((permission_id)::text = 'artifact.verification_job.read'::text)) OR (((action_id)::text = 'artifact.verification_job.retry'::text) AND ((permission_id)::text = 'artifact.verification_job.retry'::text)) OR (((action_id)::text = 'artifact.recovery_attempt.read'::text) AND ((permission_id)::text = 'artifact.recovery_attempt.read'::text)) OR (((action_id)::text = 'artifact.audit.read'::text) AND ((permission_id)::text = 'artifact.audit.read'::text)) OR (((action_id)::text = 'operations.artifact_storage_admission.read'::text) AND ((permission_id)::text = 'operations.status.read'::text)) OR (((action_id)::text = 'artifact.guide_source.ingest'::text) AND ((permission_id)::text = 'artifact.guide_source.ingest'::text)) OR (((action_id)::text = 'artifact.submission_bundle.prepare'::text) AND ((permission_id)::text = 'submission.create'::text)) OR (((action_id)::text = 'artifact.review_packet.materialize'::text) AND ((permission_id)::text = 'artifact.review_packet.materialize'::text)) OR (((action_id)::text = 'artifact.review_evidence.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.guide_source.read'::text) AND ((permission_id)::text = 'artifact.guide_source.read'::text)) OR (((action_id)::text = 'artifact.guide_source.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.submission.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.checker_output.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.verification.execute'::text) AND ((permission_id)::text = 'artifact.verification.execute'::text)) OR (((action_id)::text = 'artifact.pending_work.scan'::text) AND ((permission_id)::text = 'artifact.pending_work.scan'::text)) OR (((action_id)::text = 'artifact.put_attempt.resolve'::text) AND ((permission_id)::text = 'artifact.put_attempt.resolve'::text)) OR (((action_id)::text = 'artifact.pre_submit.checker_input.materialize'::text) AND ((permission_id)::text = 'artifact.checker_input.materialize'::text)) OR (((action_id)::text = 'artifact.post_submit.checker_input.materialize'::text) AND ((permission_id)::text = 'artifact.checker_input.materialize'::text)) OR (((action_id)::text = 'artifact.checker_output.write'::text) AND ((permission_id)::text = 'artifact.checker_output.write'::text)) OR (((action_id)::text = 'authorization.permission_catalogue.read'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'authorization.admin_role_definitions.read'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'admin_role_grant.list'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'actor.admin_role_grant_history.read'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'admin_role_grant.issue'::text) AND ((permission_id)::text = 'admin_role.grant'::text)) OR (((action_id)::text = 'admin_role_grant.revoke'::text) AND ((permission_id)::text = 'admin_role.revoke'::text)) OR (((action_id)::text = 'admin_role_grant.bootstrap'::text) AND ((permission_id)::text = 'admin_role.grant'::text)) OR (((action_id)::text = 'actor.profile.read'::text) AND ((permission_id)::text = 'actor.profile.read_any'::text)) OR (((action_id)::text = 'actor.profile.suspend'::text) AND ((permission_id)::text = 'actor.profile.suspend'::text)) OR (((action_id)::text = 'actor.profile.reactivate'::text) AND ((permission_id)::text = 'actor.profile.reactivate'::text)) OR (((action_id)::text = 'actor.profile.deactivate'::text) AND ((permission_id)::text = 'actor.profile.deactivate'::text)) OR (((action_id)::text = 'actor.identity_link.read'::text) AND ((permission_id)::text = 'actor.identity_link.read'::text)) OR (((action_id)::text = 'actor.identity_link.revoke'::text) AND ((permission_id)::text = 'actor.identity_link.revoke'::text)) OR (((action_id)::text = 'actor.identity_link.reactivate'::text) AND ((permission_id)::text = 'actor.identity_link.reactivate'::text)) OR (((action_id)::text = 'actor.service.provision'::text) AND ((permission_id)::text = 'actor.service.provision'::text)) OR (((action_id)::text = 'project.contributor_candidate.list'::text) AND ((permission_id)::text = 'project.role_grant.manage'::text)) OR (((action_id)::text = 'project_role_grant.list'::text) AND ((permission_id)::text = 'project.role_grant.read'::text)) OR (((action_id)::text = 'project_role_grant.read'::text) AND ((permission_id)::text = 'project.role_grant.read'::text)) OR (((action_id)::text = 'project_role_grant.issue'::text) AND ((permission_id)::text = 'project.role_grant.manage'::text)) OR (((action_id)::text = 'project_role_grant.revoke'::text) AND ((permission_id)::text = 'project.role_grant.manage'::text)) OR (((action_id)::text = 'project.read'::text) AND ((permission_id)::text = 'project.read'::text)) OR (((action_id)::text = 'actor.authorization_context.read'::text) AND ((permission_id)::text = 'actor.profile.read_self'::text)) OR (((action_id)::text = 'project.setup_run.read'::text) AND ((permission_id)::text = 'project.setup_diagnostic.read'::text)) OR (((action_id)::text = 'project.guide_sufficiency_report.list'::text) AND ((permission_id)::text = 'project.setup_diagnostic.read'::text)) OR (((action_id)::text = 'project.guide_sufficiency_report.read'::text) AND ((permission_id)::text = 'project.setup_diagnostic.read'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.list'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy_setup.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.effective_submission_artifact_policy.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.pre_submit_checker_policy.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.active_guide.read'::text) AND ((permission_id)::text = 'project.read'::text)) OR (((action_id)::text = 'project.create'::text) AND ((permission_id)::text = 'project.create'::text)) OR (((action_id)::text = 'project.guide.create'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide.update'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide_source_snapshot.create'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.review_policy.update'::text) AND ((permission_id)::text = 'project.review_policy.manage'::text)) OR (((action_id)::text = 'project.revision_policy.update'::text) AND ((permission_id)::text = 'project.review_policy.manage'::text)) OR (((action_id)::text = 'project.guide_sufficiency_report.create'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide_sufficiency.run'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide_compilation.execute'::text) AND ((permission_id)::text = 'project.guide_compilation.execute'::text)) OR (((action_id)::text = 'project.guide_compilation.request'::text) AND ((permission_id)::text = 'project.guide_compilation.request'::text)) OR (((action_id)::text = 'project.guide_sufficiency.warnings.acknowledge'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.create'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.derive'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.update'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.approve'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy.approve'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy.correction.request'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy.derive'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.setup_run.update'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide.activate'::text) AND ((permission_id)::text = 'project.guide.manage'::text))))) AND ((permission_id IS NULL) OR ((permission_id)::text <> ALL (ARRAY[('operations.task.start_override'::character varying)::text, ('operations.submission_gate.repair'::character varying)::text, ('operations.checker.retry'::character varying)::text, ('artifact.binding.read'::character varying)::text, ('artifact.replica.read'::character varying)::text, ('artifact.receipt.read'::character varying)::text, ('artifact.verification_job.read'::character varying)::text, ('artifact.verification_job.retry'::character varying)::text, ('artifact.recovery_attempt.read'::character varying)::text, ('artifact.audit.read'::character varying)::text, ('artifact.guide_source.ingest'::character varying)::text, ('artifact.binding.create'::character varying)::text, ('artifact.review_packet.materialize'::character varying)::text, ('artifact.verification.execute'::character varying)::text, ('artifact.pending_work.scan'::character varying)::text, ('artifact.put_attempt.resolve'::character varying)::text, ('artifact.guide_source.read'::character varying)::text, ('artifact.checker_input.materialize'::character varying)::text, ('artifact.checker_output.write'::character varying)::text, ('review.queue.override'::character varying)::text, ('project.setup_diagnostic.read'::character varying)::text, ('project.effective_policy.read'::character varying)::text, ('project.guide_compilation.request'::character varying)::text, ('project.guide_compilation.execute'::character varying)::text])) OR ((action_id IS NOT NULL) AND ((((action_id)::text = 'actor.profile.read_self'::text) AND ((permission_id)::text = 'actor.profile.read_self'::text)) OR (((action_id)::text = 'actor.profile.update_self'::text) AND ((permission_id)::text = 'actor.profile.update_self'::text)) OR (((action_id)::text = 'operations.task.start_override'::text) AND ((permission_id)::text = 'operations.task.start_override'::text)) OR (((action_id)::text = 'operations.submission_gate.repair'::text) AND ((permission_id)::text = 'operations.submission_gate.repair'::text)) OR (((action_id)::text = 'operations.checker.retry'::text) AND ((permission_id)::text = 'operations.checker.retry'::text)) OR (((action_id)::text = 'submission.create'::text) AND ((permission_id)::text = 'submission.create'::text)) OR (((action_id)::text = 'review.queue.read'::text) AND ((permission_id)::text = 'review.queue.read'::text)) OR (((action_id)::text = 'review.queue.inspect'::text) AND ((permission_id)::text = 'review.queue.inspect'::text)) OR (((action_id)::text = 'review.claim'::text) AND ((permission_id)::text = 'review.claim'::text)) OR (((action_id)::text = 'review.release'::text) AND ((permission_id)::text = 'review.release'::text)) OR (((action_id)::text = 'review.decline_preference'::text) AND ((permission_id)::text = 'review.decline_preference'::text)) OR (((action_id)::text = 'review.preference_expiry.run'::text) AND ((permission_id)::text = 'operations.timer.run'::text)) OR (((action_id)::text = 'review.lease_expiry.run'::text) AND ((permission_id)::text = 'operations.timer.run'::text)) OR (((action_id)::text = 'review.context.read'::text) AND ((permission_id)::text = 'submission.read_for_review'::text)) OR (((action_id)::text = 'review.chain.read'::text) AND ((permission_id)::text = 'review.chain.read'::text)) OR (((action_id)::text = 'review.finding_evidence.ingest'::text) AND ((permission_id)::text = 'review.decision'::text)) OR (((action_id)::text = 'review.decision'::text) AND ((permission_id)::text = 'review.decision'::text)) OR (((action_id)::text = 'review.finding_response_evidence.ingest'::text) AND ((permission_id)::text = 'submission.create'::text)) OR (((action_id)::text = 'review.lease.force_release'::text) AND ((permission_id)::text = 'review.lease.force_release'::text)) OR (((action_id)::text = 'review.queue.routing.override'::text) AND ((permission_id)::text = 'review.queue.override'::text)) OR (((action_id)::text = 'review.queue.routing.correct'::text) AND ((permission_id)::text = 'review.queue.override'::text)) OR (((action_id)::text = 'review.queue.close'::text) AND ((permission_id)::text = 'review.queue.override'::text)) OR (((action_id)::text = 'review.reconcile.run'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'review.artifact_reference.reconcile'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'review.projection.rebuild'::text) AND ((permission_id)::text = 'operations.projection.rebuild'::text)) OR (((action_id)::text = 'review.revision_context.repair'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'review.revision_obligation.close'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'review.revision_context.legacy_close'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'review.lifecycle.activation.manage'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'artifact.binding.read'::text) AND ((permission_id)::text = 'artifact.binding.read'::text)) OR (((action_id)::text = 'artifact.replica.read'::text) AND ((permission_id)::text = 'artifact.replica.read'::text)) OR (((action_id)::text = 'artifact.receipt.read'::text) AND ((permission_id)::text = 'artifact.receipt.read'::text)) OR (((action_id)::text = 'artifact.verification_job.read'::text) AND ((permission_id)::text = 'artifact.verification_job.read'::text)) OR (((action_id)::text = 'artifact.verification_job.retry'::text) AND ((permission_id)::text = 'artifact.verification_job.retry'::text)) OR (((action_id)::text = 'artifact.recovery_attempt.read'::text) AND ((permission_id)::text = 'artifact.recovery_attempt.read'::text)) OR (((action_id)::text = 'artifact.audit.read'::text) AND ((permission_id)::text = 'artifact.audit.read'::text)) OR (((action_id)::text = 'operations.artifact_storage_admission.read'::text) AND ((permission_id)::text = 'operations.status.read'::text)) OR (((action_id)::text = 'artifact.guide_source.ingest'::text) AND ((permission_id)::text = 'artifact.guide_source.ingest'::text)) OR (((action_id)::text = 'artifact.submission_bundle.prepare'::text) AND ((permission_id)::text = 'submission.create'::text)) OR (((action_id)::text = 'artifact.review_packet.materialize'::text) AND ((permission_id)::text = 'artifact.review_packet.materialize'::text)) OR (((action_id)::text = 'artifact.review_evidence.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.guide_source.read'::text) AND ((permission_id)::text = 'artifact.guide_source.read'::text)) OR (((action_id)::text = 'artifact.guide_source.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.submission.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.checker_output.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.verification.execute'::text) AND ((permission_id)::text = 'artifact.verification.execute'::text)) OR (((action_id)::text = 'artifact.pending_work.scan'::text) AND ((permission_id)::text = 'artifact.pending_work.scan'::text)) OR (((action_id)::text = 'artifact.put_attempt.resolve'::text) AND ((permission_id)::text = 'artifact.put_attempt.resolve'::text)) OR (((action_id)::text = 'artifact.pre_submit.checker_input.materialize'::text) AND ((permission_id)::text = 'artifact.checker_input.materialize'::text)) OR (((action_id)::text = 'artifact.post_submit.checker_input.materialize'::text) AND ((permission_id)::text = 'artifact.checker_input.materialize'::text)) OR (((action_id)::text = 'artifact.checker_output.write'::text) AND ((permission_id)::text = 'artifact.checker_output.write'::text)) OR (((action_id)::text = 'authorization.permission_catalogue.read'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'authorization.admin_role_definitions.read'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'admin_role_grant.list'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'actor.admin_role_grant_history.read'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'admin_role_grant.issue'::text) AND ((permission_id)::text = 'admin_role.grant'::text)) OR (((action_id)::text = 'admin_role_grant.revoke'::text) AND ((permission_id)::text = 'admin_role.revoke'::text)) OR (((action_id)::text = 'admin_role_grant.bootstrap'::text) AND ((permission_id)::text = 'admin_role.grant'::text)) OR (((action_id)::text = 'actor.profile.read'::text) AND ((permission_id)::text = 'actor.profile.read_any'::text)) OR (((action_id)::text = 'actor.profile.suspend'::text) AND ((permission_id)::text = 'actor.profile.suspend'::text)) OR (((action_id)::text = 'actor.profile.reactivate'::text) AND ((permission_id)::text = 'actor.profile.reactivate'::text)) OR (((action_id)::text = 'actor.profile.deactivate'::text) AND ((permission_id)::text = 'actor.profile.deactivate'::text)) OR (((action_id)::text = 'actor.identity_link.read'::text) AND ((permission_id)::text = 'actor.identity_link.read'::text)) OR (((action_id)::text = 'actor.identity_link.revoke'::text) AND ((permission_id)::text = 'actor.identity_link.revoke'::text)) OR (((action_id)::text = 'actor.identity_link.reactivate'::text) AND ((permission_id)::text = 'actor.identity_link.reactivate'::text)) OR (((action_id)::text = 'actor.service.provision'::text) AND ((permission_id)::text = 'actor.service.provision'::text)) OR (((action_id)::text = 'project.contributor_candidate.list'::text) AND ((permission_id)::text = 'project.role_grant.manage'::text)) OR (((action_id)::text = 'project_role_grant.list'::text) AND ((permission_id)::text = 'project.role_grant.read'::text)) OR (((action_id)::text = 'project_role_grant.read'::text) AND ((permission_id)::text = 'project.role_grant.read'::text)) OR (((action_id)::text = 'project_role_grant.issue'::text) AND ((permission_id)::text = 'project.role_grant.manage'::text)) OR (((action_id)::text = 'project_role_grant.revoke'::text) AND ((permission_id)::text = 'project.role_grant.manage'::text)) OR (((action_id)::text = 'project.read'::text) AND ((permission_id)::text = 'project.read'::text)) OR (((action_id)::text = 'actor.authorization_context.read'::text) AND ((permission_id)::text = 'actor.profile.read_self'::text)) OR (((action_id)::text = 'project.setup_run.read'::text) AND ((permission_id)::text = 'project.setup_diagnostic.read'::text)) OR (((action_id)::text = 'project.guide_sufficiency_report.list'::text) AND ((permission_id)::text = 'project.setup_diagnostic.read'::text)) OR (((action_id)::text = 'project.guide_sufficiency_report.read'::text) AND ((permission_id)::text = 'project.setup_diagnostic.read'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.list'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy_setup.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.effective_submission_artifact_policy.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.pre_submit_checker_policy.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.active_guide.read'::text) AND ((permission_id)::text = 'project.read'::text)) OR (((action_id)::text = 'project.create'::text) AND ((permission_id)::text = 'project.create'::text)) OR (((action_id)::text = 'project.guide.create'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide.update'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide_source_snapshot.create'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.review_policy.update'::text) AND ((permission_id)::text = 'project.review_policy.manage'::text)) OR (((action_id)::text = 'project.revision_policy.update'::text) AND ((permission_id)::text = 'project.review_policy.manage'::text)) OR (((action_id)::text = 'project.guide_sufficiency_report.create'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide_sufficiency.run'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide_compilation.execute'::text) AND ((permission_id)::text = 'project.guide_compilation.execute'::text)) OR (((action_id)::text = 'project.guide_compilation.request'::text) AND ((permission_id)::text = 'project.guide_compilation.request'::text)) OR (((action_id)::text = 'project.guide_sufficiency.warnings.acknowledge'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.create'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.derive'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.update'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.approve'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy.approve'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy.correction.request'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy.derive'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.setup_run.update'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide.activate'::text) AND ((permission_id)::text = 'project.guide.manage'::text)))))))),
    CONSTRAINT ck_audit_events_domain_shape CHECK (((((event_domain)::text = 'legacy_lifecycle'::text) AND (event_version IS NULL) AND (occurred_at IS NULL) AND (actor_ref_kind IS NULL) AND (request_id IS NULL) AND (correlation_id IS NULL) AND (target_actor_ref_kind IS NULL) AND (target_actor_ref IS NULL) AND (matched_grant_id IS NULL) AND (permission_id IS NULL) AND (project_id IS NULL) AND (resource_type IS NULL) AND (resource_id IS NULL) AND (target_ref_kind IS NULL) AND (target_ref_id IS NULL) AND (denial_code IS NULL) AND (idempotency_reference IS NULL) AND (invalidation_cause_event_id IS NULL) AND (invalidation_target_kind IS NULL) AND (invalidation_target_ref IS NULL) AND (before_facts IS NULL) AND (after_facts IS NULL) AND (external_subject IS NOT NULL) AND (external_issuer IS NOT NULL)) OR (((event_domain)::text = 'authority'::text) AND (event_version = 1) AND (occurred_at IS NOT NULL) AND ((actor_ref_kind)::text = ANY ((ARRAY['legacy_actor'::character varying, 'actor_profile'::character varying, 'system_principal'::character varying])::text[])) AND (request_id IS NOT NULL) AND (correlation_id IS NOT NULL) AND (from_status IS NULL) AND (to_status IS NULL) AND (reason IS NOT NULL) AND (external_subject IS NULL) AND (external_issuer IS NULL) AND ((actor_roles)::jsonb = '[]'::jsonb) AND ((claim_snapshot)::jsonb = '{}'::jsonb) AND ((auth_source)::text = 'local_authority'::text) AND (is_dev_auth = false) AND ((event_payload)::jsonb = '{}'::jsonb)))),
    CONSTRAINT ck_audit_events_fact_bounds CHECK ((((event_domain)::text <> 'authority'::text) OR (((before_facts IS NULL) OR (octet_length((before_facts)::text) <= 4096)) AND ((after_facts IS NULL) OR (octet_length((after_facts)::text) <= 4096)) AND COALESCE(public.authority_event_facts_are_safe((event_type)::text, before_facts, after_facts, (project_id)::text), false)))),
    CONSTRAINT ck_audit_events_foundation_shapes CHECK ((((event_domain)::text <> 'authority'::text) OR ((event_type)::text <> ALL ((ARRAY['SensitiveAuthorizationAllowed'::character varying, 'SensitiveAuthorizationDenied'::character varying, 'AuthorityInvalidationRequested'::character varying, 'AdminRoleGrantIssueDenied'::character varying, 'LastAccessAdministratorOperationDenied'::character varying])::text[])) OR (((event_type)::text = ANY ((ARRAY['AdminRoleGrantIssueDenied'::character varying, 'LastAccessAdministratorOperationDenied'::character varying])::text[])) AND (denial_code IS NOT NULL)) OR (((event_type)::text = 'SensitiveAuthorizationAllowed'::text) AND (permission_id IS NOT NULL) AND (denial_code IS NULL) AND (invalidation_cause_event_id IS NULL) AND (invalidation_target_kind IS NULL)) OR (((event_type)::text = 'SensitiveAuthorizationDenied'::text) AND (permission_id IS NOT NULL) AND (denial_code IS NOT NULL) AND (invalidation_cause_event_id IS NULL) AND (invalidation_target_kind IS NULL) AND (idempotency_reference IS NULL)) OR (((event_type)::text = 'AuthorityInvalidationRequested'::text) AND (invalidation_cause_event_id IS NOT NULL) AND (invalidation_target_kind IS NOT NULL) AND (denial_code IS NULL)))),
    CONSTRAINT ck_audit_events_reference_pairs CHECK ((((target_actor_ref_kind IS NULL) = (target_actor_ref IS NULL)) AND ((resource_type IS NOT NULL) OR (resource_id IS NULL)) AND ((target_ref_kind IS NULL) = (target_ref_id IS NULL)) AND ((invalidation_target_kind IS NULL) = (invalidation_target_ref IS NULL)) AND ((invalidation_cause_event_id IS NULL) OR ((invalidation_cause_event_id)::text <> (id)::text))))
);
CREATE TABLE public.authority_control (
    id smallint NOT NULL,
    bootstrap_completed boolean DEFAULT false NOT NULL,
    bootstrap_grant_id uuid,
    version smallint DEFAULT '0'::smallint NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ck_authority_control_bootstrap_state CHECK ((((bootstrap_completed = false) AND (bootstrap_grant_id IS NULL) AND (version = 0)) OR ((bootstrap_completed = true) AND (bootstrap_grant_id IS NOT NULL) AND (version = 1)))),
    CONSTRAINT ck_authority_control_singleton CHECK ((id = 1))
);
CREATE SEQUENCE public.authority_control_id_seq
    AS smallint
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.authority_control_id_seq OWNED BY public.authority_control.id;
CREATE TABLE public.authority_idempotency_records (
    id uuid NOT NULL,
    idempotency_key uuid NOT NULL,
    actor_ref_kind character varying(32) NOT NULL,
    actor_ref character varying(100) NOT NULL,
    operation character varying(48) NOT NULL,
    request_digest character varying(71) NOT NULL,
    status character varying(16) NOT NULL,
    response_resource_type character varying(32),
    response_resource_id uuid,
    response_resource_version bigint,
    response_http_status smallint,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    committed_at timestamp with time zone,
    CONSTRAINT ck_authority_idempotency_records_actor_kind CHECK (((actor_ref_kind)::text = ANY ((ARRAY['legacy_actor'::character varying, 'actor_profile'::character varying, 'system_principal'::character varying])::text[]))),
    CONSTRAINT ck_authority_idempotency_records_actor_reference CHECK (((((actor_ref_kind)::text = 'system_principal'::text) AND ((actor_ref)::text = 'workstream:system:bootstrap'::text)) OR (((actor_ref_kind)::text <> 'system_principal'::text) AND ((actor_ref)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)))),
    CONSTRAINT ck_authority_idempotency_records_operation CHECK (((operation)::text = ANY ((ARRAY['service_actor.create'::character varying, 'admin_role_grant.issue'::character varying, 'admin_role_grant.revoke'::character varying, 'project_role_grant.issue'::character varying, 'project_role_grant.revoke'::character varying, 'actor_profile.suspend'::character varying, 'actor_profile.reactivate'::character varying, 'actor_profile.deactivate'::character varying, 'actor_identity_link.revoke'::character varying, 'actor_identity_link.reactivate'::character varying])::text[]))),
    CONSTRAINT ck_authority_idempotency_records_request_digest CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_authority_idempotency_records_response_status CHECK (((response_http_status IS NULL) OR ((((operation)::text = ANY ((ARRAY['service_actor.create'::character varying, 'admin_role_grant.issue'::character varying, 'project_role_grant.issue'::character varying])::text[])) AND (response_http_status = 201)) OR (((operation)::text <> ALL ((ARRAY['service_actor.create'::character varying, 'admin_role_grant.issue'::character varying, 'project_role_grant.issue'::character varying])::text[])) AND (response_http_status = 200))))),
    CONSTRAINT ck_authority_idempotency_records_response_type CHECK (((((operation)::text = 'service_actor.create'::text) AND ((response_resource_type IS NULL) OR ((response_resource_type)::text = 'actor_profile'::text))) OR (((operation)::text ~~ 'admin_role_grant.%'::text) AND ((response_resource_type IS NULL) OR ((response_resource_type)::text = 'admin_role_grant'::text))) OR (((operation)::text ~~ 'project_role_grant.%'::text) AND ((response_resource_type IS NULL) OR ((response_resource_type)::text = 'project_role_grant'::text))) OR (((operation)::text ~~ 'actor_profile.%'::text) AND ((response_resource_type IS NULL) OR ((response_resource_type)::text = 'actor_profile'::text))) OR (((operation)::text ~~ 'actor_identity_link.%'::text) AND ((response_resource_type IS NULL) OR ((response_resource_type)::text = 'actor_identity_link'::text))))),
    CONSTRAINT ck_authority_idempotency_records_response_version CHECK (((response_resource_version IS NULL) OR (response_resource_version > 0))),
    CONSTRAINT ck_authority_idempotency_records_state_shape CHECK (((((status)::text = 'pending'::text) AND (response_resource_type IS NULL) AND (response_resource_id IS NULL) AND (response_resource_version IS NULL) AND (response_http_status IS NULL) AND (committed_at IS NULL)) OR (((status)::text = 'committed'::text) AND (response_resource_type IS NOT NULL) AND (response_resource_id IS NOT NULL) AND (response_http_status IS NOT NULL) AND (committed_at IS NOT NULL)))),
    CONSTRAINT ck_authority_idempotency_records_status CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'committed'::character varying])::text[])))
);
CREATE TABLE public.checker_policies (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_version character varying(50) NOT NULL,
    required_checkers json NOT NULL,
    warning_checkers json NOT NULL,
    blocking_severities json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    policy_hash character varying(71),
    policy_body json,
    guide_id character varying(36) NOT NULL,
    source_snapshot_id character varying(36) NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    effective_policy_id character varying(36) NOT NULL,
    effective_policy_hash character varying(71) NOT NULL,
    pre_submit_checker_policy_id character varying(36) NOT NULL,
    pre_submit_checker_bundle_hash character varying(71) NOT NULL,
    lifecycle_status character varying(30) NOT NULL,
    approved_by_role character varying(50),
    approved_by_actor character varying(100),
    approved_at timestamp with time zone,
    created_by character varying(100) NOT NULL,
    supersedes_policy_id character varying(36),
    superseded_at timestamp with time zone,
    superseded_by_role character varying(50),
    superseded_by_actor character varying(100),
    supersession_kind character varying(50),
    supersession_reason text,
    CONSTRAINT ck_checker_policies_approval_provenance CHECK ((((lifecycle_status)::text <> 'approved'::text) OR (((approved_by_role)::text = ANY ((ARRAY['admin'::character varying, 'project_manager'::character varying])::text[])) AND (approved_by_actor IS NOT NULL) AND (approved_at IS NOT NULL)))),
    CONSTRAINT ck_checker_policies_correction_provenance CHECK ((((lifecycle_status)::text <> 'superseded'::text) OR ((superseded_at IS NOT NULL) AND ((superseded_by_role)::text = ANY ((ARRAY['admin'::character varying, 'project_manager'::character varying])::text[])) AND (superseded_by_actor IS NOT NULL) AND ((supersession_kind)::text = ANY ((ARRAY['correction_requested'::character varying, 'upstream_policy_changed'::character varying])::text[])) AND (supersession_reason IS NOT NULL) AND (length(btrim(supersession_reason)) > 0)))),
    CONSTRAINT ck_checker_policies_lifecycle_status CHECK (((lifecycle_status)::text = ANY ((ARRAY['compiled'::character varying, 'approved'::character varying, 'superseded'::character varying])::text[]))),
    CONSTRAINT ck_checker_policies_policy_hash_shape CHECK (((policy_hash IS NULL) OR ((policy_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text)))
);
CREATE TABLE public.checker_results (
    id character varying(36) NOT NULL,
    checker_run_id character varying(36) NOT NULL,
    task_id character varying(36) NOT NULL,
    submission_id character varying(36) NOT NULL,
    checker_name character varying(100) NOT NULL,
    status character varying(30) NOT NULL,
    severity character varying(30) NOT NULL,
    blocks_review boolean NOT NULL,
    message text NOT NULL,
    worker_message text,
    worker_suggested_fix text,
    worker_evidence_refs json NOT NULL,
    worker_visible boolean NOT NULL,
    metadata json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.checker_runs (
    id character varying(36) NOT NULL,
    task_id character varying(36) NOT NULL,
    submission_id character varying(36) NOT NULL,
    submission_version integer NOT NULL,
    trigger_source character varying(50) NOT NULL,
    status character varying(30) NOT NULL,
    routing_recommendation character varying(50) NOT NULL,
    outcome_source character varying(50) NOT NULL,
    triggered_by character varying(100) NOT NULL,
    triggered_by_subject character varying(200) NOT NULL,
    triggered_by_issuer character varying(200) NOT NULL,
    trigger_auth_source character varying(30) NOT NULL,
    trigger_reason text,
    audit_event_id character varying(36),
    attempt_number integer NOT NULL,
    supersedes_checker_run_id character varying(36),
    is_current_for_submission boolean NOT NULL,
    locked_guide_version character varying(50) NOT NULL,
    locked_payment_policy_version character varying(50) NOT NULL,
    package_hash character varying(128) NOT NULL,
    artifact_hash_manifest json NOT NULL,
    artifact_manifest_hash character varying(128) NOT NULL,
    passed_count integer NOT NULL,
    warning_count integer NOT NULL,
    failed_count integer NOT NULL,
    blocking_count integer NOT NULL,
    queued_at timestamp with time zone DEFAULT now() NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    failure_code character varying(100),
    failure_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    locked_post_submit_checker_policy_id character varying(36),
    locked_post_submit_checker_policy_version character varying(50),
    locked_post_submit_checker_policy_hash character varying(71),
    locked_post_submit_checker_policy_body json,
    locked_review_policy_id character varying(36) NOT NULL,
    locked_review_policy_generation integer NOT NULL,
    locked_review_policy_hash character varying(71) NOT NULL,
    locked_revision_policy_id character varying(36) NOT NULL,
    locked_revision_policy_generation integer NOT NULL,
    locked_revision_policy_hash character varying(71) NOT NULL,
    CONSTRAINT ck_checker_runs_post_submit_policy_lock_complete CHECK (((locked_post_submit_checker_policy_id IS NOT NULL) AND (locked_post_submit_checker_policy_version IS NOT NULL) AND (locked_post_submit_checker_policy_hash IS NOT NULL) AND (locked_post_submit_checker_policy_body IS NOT NULL)))
);
CREATE TABLE public.contribution_award_definitions (
    id uuid NOT NULL,
    contribution_rule_id uuid NOT NULL,
    contribution_policy_version_id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    contribution_type character varying(32) NOT NULL,
    instrument_type character varying(32) NOT NULL,
    unit_code character varying(32) NOT NULL,
    quantity numeric NOT NULL,
    adapter_binding_id uuid NOT NULL,
    CONSTRAINT ck_contribution_award_definitions_contribution_type CHECK (((contribution_type)::text = ANY ((ARRAY['accepted_submission'::character varying, 'completed_review'::character varying])::text[]))),
    CONSTRAINT ck_contribution_award_definitions_instrument_type CHECK (((instrument_type)::text = ANY ((ARRAY['money'::character varying, 'project_points'::character varying])::text[]))),
    CONSTRAINT ck_contribution_award_definitions_project_points_whole CHECK ((((instrument_type)::text <> 'project_points'::text) OR (scale(quantity) = 0))),
    CONSTRAINT ck_contribution_award_definitions_quantity_exact_bounds CHECK (((quantity > (0)::numeric) AND (quantity < '100000000000000000000'::numeric) AND ((scale(quantity) >= 0) AND (scale(quantity) <= 18))))
);
CREATE TABLE public.contribution_policies (
    id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    name character varying(200) NOT NULL,
    status character varying(16) DEFAULT 'draft'::character varying NOT NULL,
    current_published_version_id uuid,
    created_by character varying(36) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    retired_by character varying(36),
    retired_at timestamp with time zone,
    CONSTRAINT ck_contribution_policies_lifecycle_shape CHECK (((((status)::text = 'draft'::text) AND (current_published_version_id IS NULL) AND (retired_by IS NULL) AND (retired_at IS NULL)) OR (((status)::text = 'active'::text) AND (current_published_version_id IS NOT NULL) AND (retired_by IS NULL) AND (retired_at IS NULL)) OR (((status)::text = 'retired'::text) AND (current_published_version_id IS NOT NULL) AND (retired_by IS NOT NULL) AND (retired_at IS NOT NULL)))),
    CONSTRAINT ck_contribution_policies_name CHECK (((char_length(btrim((name)::text)) >= 1) AND (char_length(btrim((name)::text)) <= 200))),
    CONSTRAINT ck_contribution_policies_retirement_timestamp CHECK (((retired_at IS NULL) OR (retired_at >= created_at))),
    CONSTRAINT ck_contribution_policies_status CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'active'::character varying, 'retired'::character varying])::text[])))
);
CREATE TABLE public.contribution_policy_versions (
    id uuid NOT NULL,
    contribution_policy_id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    version_number integer NOT NULL,
    status character varying(16) DEFAULT 'draft'::character varying NOT NULL,
    created_by character varying(36) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    published_by character varying(36),
    published_at timestamp with time zone,
    retired_by character varying(36),
    retired_at timestamp with time zone,
    CONSTRAINT ck_contribution_policy_versions_lifecycle_shape CHECK (((((status)::text = 'draft'::text) AND (published_by IS NULL) AND (published_at IS NULL) AND (retired_by IS NULL) AND (retired_at IS NULL)) OR (((status)::text = 'published'::text) AND (published_by IS NOT NULL) AND (published_at IS NOT NULL) AND (retired_by IS NULL) AND (retired_at IS NULL)) OR (((status)::text = 'retired'::text) AND (published_by IS NOT NULL) AND (published_at IS NOT NULL) AND (retired_by IS NOT NULL) AND (retired_at IS NOT NULL)))),
    CONSTRAINT ck_contribution_policy_versions_lifecycle_timestamps CHECK ((((published_at IS NULL) OR (published_at >= created_at)) AND ((retired_at IS NULL) OR (retired_at >= published_at)))),
    CONSTRAINT ck_contribution_policy_versions_status CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'published'::character varying, 'retired'::character varying])::text[]))),
    CONSTRAINT ck_contribution_policy_versions_version_number_positive CHECK ((version_number > 0))
);
CREATE TABLE public.contribution_rules (
    id uuid NOT NULL,
    contribution_policy_version_id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    contribution_type character varying(32) NOT NULL,
    compensation_mode character varying(16) NOT NULL,
    CONSTRAINT ck_contribution_rules_compensation_mode CHECK (((compensation_mode)::text = ANY ((ARRAY['unpaid'::character varying, 'compensated'::character varying])::text[]))),
    CONSTRAINT ck_contribution_rules_contribution_type CHECK (((contribution_type)::text = ANY ((ARRAY['accepted_submission'::character varying, 'completed_review'::character varying])::text[])))
);
CREATE TABLE public.effective_project_submission_artifact_policies (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_id character varying(36) NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id character varying(36) NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    submission_artifact_policy_id character varying(36) NOT NULL,
    submission_artifact_policy_hash character varying(71) NOT NULL,
    lifecycle_status character varying(30) NOT NULL,
    merge_algorithm_version character varying(50) NOT NULL,
    effective_policy json NOT NULL,
    effective_policy_hash character varying(71) NOT NULL,
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    supersedes_effective_policy_id character varying(36),
    superseded_at timestamp with time zone,
    created_by_actor_profile_id character varying(36),
    created_via_identity_link_id character varying(36),
    created_by_admin_role_grant_id uuid,
    creation_scope_type character varying(16),
    creation_scope_project_id character varying(36),
    creation_action_id character varying(160),
    creation_decision_event_id character varying(36),
    CONSTRAINT ck_effective_project_submission_artifact_policies_ck_ef_7be7 CHECK (((lifecycle_status)::text = ANY ((ARRAY['approved'::character varying, 'superseded'::character varying])::text[]))),
    CONSTRAINT ck_effective_project_submission_artifact_policies_ck_ef_bd4e CHECK ((((created_by_actor_profile_id IS NULL) AND (created_via_identity_link_id IS NULL) AND (created_by_admin_role_grant_id IS NULL) AND (creation_scope_type IS NULL) AND (creation_scope_project_id IS NULL) AND (creation_action_id IS NULL) AND (creation_decision_event_id IS NULL)) OR ((created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (created_by_admin_role_grant_id IS NOT NULL) AND (creation_scope_type IS NOT NULL) AND (creation_action_id IS NOT NULL) AND ((creation_scope_type)::text = ANY ((ARRAY['system'::character varying, 'project'::character varying])::text[])) AND (creation_scope_project_id IS NOT NULL) AND ((creation_scope_project_id)::text = (project_id)::text) AND ((creation_action_id)::text = 'project.submission_artifact_policy.approve'::text) AND (creation_decision_event_id IS NOT NULL))))
);
CREATE TABLE public.evidence_items (
    id character varying(36) NOT NULL,
    submission_id character varying(36) NOT NULL,
    type character varying(50) NOT NULL,
    label character varying(200) NOT NULL,
    uri character varying(1000),
    hash character varying(128),
    size_bytes integer,
    locked_at timestamp with time zone,
    metadata json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.guide_mutation_idempotency_records (
    id uuid NOT NULL,
    actor_profile_id character varying(36) NOT NULL,
    identity_link_id character varying(36) NOT NULL,
    action_id character varying(160) NOT NULL,
    idempotency_key uuid NOT NULL,
    request_digest character varying(71) NOT NULL,
    resource_context_digest character varying(71) NOT NULL,
    operation_id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    resource_id character varying(36) NOT NULL,
    operation_generation integer NOT NULL,
    status character varying(16) NOT NULL,
    response_json json,
    setup_run_id character varying(36),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    committed_at timestamp with time zone,
    CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_6506 CHECK ((operation_generation > 0)),
    CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_9402 CHECK (((((status)::text = 'pending'::text) AND (response_json IS NULL) AND (committed_at IS NULL) AND (setup_run_id IS NULL)) OR (((status)::text = 'committed'::text) AND (response_json IS NOT NULL) AND (committed_at IS NOT NULL)))),
    CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_action CHECK (((action_id)::text = ANY ((ARRAY['project.guide.create'::character varying, 'project.guide.update'::character varying, 'project.guide_source_snapshot.create'::character varying])::text[]))),
    CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_b397 CHECK (((resource_context_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_e32d CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_status CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'committed'::character varying])::text[])))
);
CREATE TABLE public.guide_source_artifact_bindings (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_id character varying(36) NOT NULL,
    source_snapshot_id character varying(36) NOT NULL,
    source_item_id character varying(36) NOT NULL,
    project_setup_run_id character varying(36) NOT NULL,
    setup_generation bigint NOT NULL,
    content_id character varying(36) NOT NULL,
    verified_replica_id character varying(36) NOT NULL,
    logical_role character varying(100) NOT NULL,
    supersedes_binding_id character varying(36),
    created_by_service character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_artifact_bindings_ck_guide_bindings_gen_b5fe CHECK ((setup_generation > 0)),
    CONSTRAINT ck_guide_source_artifact_bindings_ck_guide_bindings_role CHECK (((logical_role)::text = 'guide_source_original'::text))
);
CREATE TABLE public.guide_source_artifact_incidents (
    id character varying(36) NOT NULL,
    binding_id character varying(36) NOT NULL,
    content_id character varying(36) NOT NULL,
    verified_replica_id character varying(36) NOT NULL,
    setup_generation bigint NOT NULL,
    code character varying(40) NOT NULL,
    observed_sha256 character varying(71),
    observed_byte_count bigint,
    bounded_facts json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_artifact_incidents_ck_guide_incidents_code CHECK (((code)::text = ANY ((ARRAY['missing'::character varying, 'changed'::character varying, 'truncated'::character varying, 'unavailable'::character varying, 'stale'::character varying, 'conflict'::character varying])::text[]))),
    CONSTRAINT ck_guide_source_artifact_incidents_ck_guide_source_arti_621b CHECK (((observed_sha256 IS NULL) OR ((observed_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_guide_source_artifact_incidents_ck_guide_source_arti_92fa CHECK (((observed_byte_count IS NULL) OR (observed_byte_count >= 0)))
);
CREATE TABLE public.guide_source_artifact_ingests (
    id character varying(36) NOT NULL,
    source_item_id character varying(36) NOT NULL,
    actor_profile_id character varying(36) NOT NULL,
    sha256 character varying(71) NOT NULL,
    byte_count bigint NOT NULL,
    media_type character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_artifact_ingests_ck_guide_source_artifa_2958 CHECK ((byte_count >= 0)),
    CONSTRAINT ck_guide_source_artifact_ingests_ck_guide_source_artifa_64cb CHECK (((sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text))
);
CREATE TABLE public.guide_source_extracted_contents (
    id character varying(36) NOT NULL,
    content_id character varying(36) NOT NULL,
    detected_format character varying(40) NOT NULL,
    extractor_name character varying(100) NOT NULL,
    extractor_version character varying(40) NOT NULL,
    policy_version character varying(80) NOT NULL,
    source_sha256 character varying(71) NOT NULL,
    source_byte_count bigint NOT NULL,
    status character varying(40) NOT NULL,
    output_sha256 character varying(71) NOT NULL,
    canonical_output text NOT NULL,
    omission_facts json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_extracted_contents_ck_guide_extracted_c_1b91 CHECK (((output_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_guide_source_extracted_contents_ck_guide_extracted_c_54b5 CHECK ((octet_length(canonical_output) <= 4194304)),
    CONSTRAINT ck_guide_source_extracted_contents_ck_guide_extracted_c_988f CHECK (((source_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_guide_source_extracted_contents_ck_guide_extracted_c_a759 CHECK (((status)::text = 'extracted'::text)),
    CONSTRAINT ck_guide_source_extracted_contents_ck_guide_extracted_c_fb79 CHECK ((source_byte_count >= 0))
);
CREATE TABLE public.guide_source_extraction_attempts (
    id character varying(36) NOT NULL,
    binding_id character varying(36) NOT NULL,
    content_id character varying(36) NOT NULL,
    classification_id character varying(36) NOT NULL,
    setup_generation bigint NOT NULL,
    detected_format character varying(40) NOT NULL,
    extractor_name character varying(100) NOT NULL,
    extractor_version character varying(40) NOT NULL,
    policy_version character varying(80) NOT NULL,
    attempt_number bigint NOT NULL,
    status character varying(40) NOT NULL,
    error_code character varying(80),
    bounded_facts json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_extraction_attempts_ck_guide_extraction_3927 CHECK ((attempt_number > 0)),
    CONSTRAINT ck_guide_source_extraction_attempts_ck_guide_extraction_940d CHECK ((((status)::text = 'extracted'::text) = (error_code IS NULL))),
    CONSTRAINT ck_guide_source_extraction_attempts_ck_guide_extraction_ff6d CHECK (((status)::text = ANY ((ARRAY['extracted'::character varying, 'unsupported'::character varying, 'ambiguous'::character varying, 'malformed'::character varying, 'limit_exceeded'::character varying, 'parser_failure'::character varying, 'cancelled'::character varying, 'artifact_incident'::character varying])::text[])))
);
CREATE TABLE public.guide_source_extraction_retry_budgets (
    binding_id character varying(36) NOT NULL,
    content_id character varying(36) NOT NULL,
    classification_id character varying(36) NOT NULL,
    setup_generation bigint NOT NULL,
    policy_version character varying(80) NOT NULL,
    claimed_slots integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_extraction_retry_budgets_ck_guide_extra_99c3 CHECK (((claimed_slots >= 1) AND (claimed_slots <= 2)))
);
CREATE TABLE public.guide_source_extraction_usages (
    id character varying(36) NOT NULL,
    extracted_content_id character varying(36) NOT NULL,
    extraction_attempt_id character varying(36) NOT NULL,
    attempt_status character varying(40) NOT NULL,
    binding_id character varying(36) NOT NULL,
    content_id character varying(36) NOT NULL,
    source_item_id character varying(36) NOT NULL,
    project_setup_run_id character varying(36) NOT NULL,
    setup_generation bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_extraction_usages_ck_guide_extraction_u_a2fd CHECK (((attempt_status)::text = 'extracted'::text))
);
CREATE TABLE public.guide_source_format_classifications (
    id character varying(36) NOT NULL,
    binding_id character varying(36) NOT NULL,
    content_id character varying(36) NOT NULL,
    verified_replica_id character varying(36) NOT NULL,
    setup_generation bigint NOT NULL,
    sha256 character varying(71) NOT NULL,
    byte_count bigint NOT NULL,
    media_type character varying(255) NOT NULL,
    detected_format character varying(40) NOT NULL,
    status character varying(40) NOT NULL,
    detector_name character varying(100) NOT NULL,
    detector_version character varying(40) NOT NULL,
    classification_facts json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_format_classifications_ck_guide_classif_8737 CHECK (((status)::text = ANY ((ARRAY['classified'::character varying, 'unsupported'::character varying, 'ambiguous'::character varying, 'malformed'::character varying, 'limit_exceeded'::character varying])::text[]))),
    CONSTRAINT ck_guide_source_format_classifications_ck_guide_source__0dd2 CHECK (((sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_guide_source_format_classifications_ck_guide_source__7235 CHECK ((byte_count >= 0))
);
CREATE TABLE public.guide_source_snapshot_items (
    id character varying(36) NOT NULL,
    source_snapshot_id character varying(36) NOT NULL,
    item_order integer NOT NULL,
    source_kind character varying(50) NOT NULL,
    source_label text NOT NULL,
    ingestion_adapter character varying(100) NOT NULL,
    media_type character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.guide_source_snapshots (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_id character varying(36) NOT NULL,
    guide_version character varying(50) NOT NULL,
    manifest_schema_version character varying(50) NOT NULL,
    manifest_json json NOT NULL,
    bundle_hash character varying(71) NOT NULL,
    captured_by character varying(100) NOT NULL,
    captured_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by_actor_profile_id character varying(36),
    created_via_identity_link_id character varying(36),
    created_by_admin_role_grant_id uuid,
    creation_scope_type character varying(16),
    creation_scope_project_id character varying(36),
    creation_action_id character varying(160),
    authorization_decision_event_id character varying(36),
    creation_generation integer,
    CONSTRAINT ck_guide_source_snapshots_source_snapshot_creation_auth_2f3e CHECK ((((creation_generation IS NULL) AND (created_by_actor_profile_id IS NULL) AND (created_via_identity_link_id IS NULL) AND (created_by_admin_role_grant_id IS NULL) AND (creation_scope_type IS NULL) AND (creation_scope_project_id IS NULL) AND (creation_action_id IS NULL) AND (authorization_decision_event_id IS NULL)) OR ((creation_generation > 0) AND (created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (created_by_admin_role_grant_id IS NOT NULL) AND ((creation_scope_type)::text = ANY ((ARRAY['system'::character varying, 'project'::character varying])::text[])) AND ((((creation_scope_type)::text = 'system'::text) AND (creation_scope_project_id IS NULL)) OR (((creation_scope_type)::text = 'project'::text) AND ((creation_scope_project_id)::text = (project_id)::text))) AND ((creation_action_id)::text = 'project.guide_source_snapshot.create'::text) AND (authorization_decision_event_id IS NOT NULL))))
);
CREATE TABLE public.guide_sufficiency_mutation_idempotency_records (
    id uuid NOT NULL,
    actor_profile_id character varying(36) NOT NULL,
    identity_link_id character varying(36) NOT NULL,
    action_id character varying(160) NOT NULL,
    idempotency_key uuid NOT NULL,
    request_digest character varying(71) NOT NULL,
    resource_context_digest character varying(71) NOT NULL,
    operation_id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_id character varying(36) NOT NULL,
    source_snapshot_id character varying(36) NOT NULL,
    report_id character varying(36),
    setup_run_id character varying(36),
    setup_generation bigint NOT NULL,
    status character varying(16) NOT NULL,
    response_json json,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    committed_at timestamp with time zone,
    CONSTRAINT ck_guide_sufficiency_mutation_idempotency_records_ck_su_1033 CHECK ((setup_generation > 0)),
    CONSTRAINT ck_guide_sufficiency_mutation_idempotency_records_ck_su_177a CHECK ((((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((resource_context_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_guide_sufficiency_mutation_idempotency_records_ck_su_6651 CHECK (((action_id)::text = ANY ((ARRAY['project.guide_sufficiency_report.create'::character varying, 'project.guide_sufficiency.run'::character varying, 'project.guide_sufficiency.warnings.acknowledge'::character varying])::text[]))),
    CONSTRAINT ck_guide_sufficiency_mutation_idempotency_records_ck_su_87dd CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'committed'::character varying])::text[]))),
    CONSTRAINT ck_guide_sufficiency_mutation_idempotency_records_ck_su_e7f6 CHECK (((((status)::text = 'pending'::text) AND (response_json IS NULL) AND (committed_at IS NULL)) OR (((status)::text = 'committed'::text) AND (response_json IS NOT NULL) AND (committed_at IS NOT NULL) AND ((((action_id)::text = 'project.guide_sufficiency.run'::text) AND ((setup_run_id IS NOT NULL) OR (report_id IS NOT NULL))) OR (((action_id)::text <> 'project.guide_sufficiency.run'::text) AND (report_id IS NOT NULL))))))
);
CREATE TABLE public.guide_sufficiency_report_source_usages (
    id character varying(36) NOT NULL,
    report_id character varying(36) NOT NULL,
    item_order integer NOT NULL,
    source_item_id character varying(36) NOT NULL,
    binding_id character varying(36) NOT NULL,
    content_id character varying(36) NOT NULL,
    extraction_usage_id character varying(36) NOT NULL,
    extraction_attempt_id character varying(36) NOT NULL,
    extracted_content_id character varying(36) NOT NULL,
    project_setup_run_id character varying(36) NOT NULL,
    setup_generation bigint NOT NULL,
    canonical_output_sha256 character varying(71) NOT NULL,
    CONSTRAINT ck_guide_sufficiency_report_source_usages_ck_sufficienc_2983 CHECK ((setup_generation > 0)),
    CONSTRAINT ck_guide_sufficiency_report_source_usages_ck_sufficienc_8148 CHECK (((canonical_output_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_guide_sufficiency_report_source_usages_ck_sufficienc_eb12 CHECK ((item_order >= 0))
);
CREATE TABLE public.guide_sufficiency_reports (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_id character varying(36) NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id character varying(36) NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    status character varying(30) NOT NULL,
    findings json NOT NULL,
    summary text,
    agent_name character varying(100),
    agent_version character varying(50),
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    warnings_acknowledged_by_role character varying(50),
    warnings_acknowledged_by_actor character varying(100),
    warnings_acknowledged_at timestamp with time zone,
    acknowledgement_note text,
    project_setup_run_id character varying(36),
    setup_generation bigint,
    agent_material_sha256 character varying(71),
    agent_material_byte_count bigint,
    created_by_actor_profile_id character varying(36),
    created_via_identity_link_id character varying(36),
    created_by_admin_role_grant_id uuid,
    created_by_service_identity character varying(160),
    creation_scope_type character varying(16),
    creation_scope_project_id character varying(36),
    creation_action_id character varying(160),
    authorization_decision_event_id character varying(36),
    warnings_acknowledged_by_actor_profile_id character varying(36),
    warnings_acknowledged_via_identity_link_id character varying(36),
    warnings_acknowledged_by_admin_role_grant_id uuid,
    warning_acknowledgement_scope_type character varying(16),
    warning_acknowledgement_scope_project_id character varying(36),
    warning_acknowledgement_action_id character varying(160),
    warning_acknowledgement_decision_event_id character varying(36),
    CONSTRAINT ck_guide_sufficiency_ack_authority_shape CHECK ((((warnings_acknowledged_by_actor_profile_id IS NULL) AND (warnings_acknowledged_via_identity_link_id IS NULL) AND (warnings_acknowledged_by_admin_role_grant_id IS NULL) AND (warning_acknowledgement_scope_type IS NULL) AND (warning_acknowledgement_scope_project_id IS NULL) AND (warning_acknowledgement_action_id IS NULL) AND (warning_acknowledgement_decision_event_id IS NULL)) OR ((warnings_acknowledged_by_actor_profile_id IS NOT NULL) AND (warnings_acknowledged_via_identity_link_id IS NOT NULL) AND (warnings_acknowledged_by_admin_role_grant_id IS NOT NULL) AND ((warning_acknowledgement_scope_type)::text = ANY ((ARRAY['system'::character varying, 'project'::character varying])::text[])) AND (warning_acknowledgement_scope_project_id IS NOT NULL) AND ((warning_acknowledgement_action_id)::text = 'project.guide_sufficiency.warnings.acknowledge'::text) AND (warning_acknowledgement_decision_event_id IS NOT NULL)))),
    CONSTRAINT ck_guide_sufficiency_creation_authority_shape CHECK ((((created_by_actor_profile_id IS NULL) AND (created_via_identity_link_id IS NULL) AND (created_by_admin_role_grant_id IS NULL) AND (created_by_service_identity IS NULL) AND (creation_scope_type IS NULL) AND (creation_scope_project_id IS NULL) AND (creation_action_id IS NULL) AND (authorization_decision_event_id IS NULL)) OR ((created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (creation_scope_project_id IS NOT NULL) AND ((creation_action_id)::text = ANY ((ARRAY['project.guide_sufficiency_report.create'::character varying, 'project.guide_sufficiency.run'::character varying])::text[])) AND (authorization_decision_event_id IS NOT NULL) AND (((created_by_admin_role_grant_id IS NOT NULL) AND (created_by_service_identity IS NULL) AND ((creation_scope_type)::text = ANY ((ARRAY['system'::character varying, 'project'::character varying])::text[]))) OR ((created_by_admin_role_grant_id IS NULL) AND ((created_by_service_identity)::text = 'workstream.project.setup'::text) AND ((creation_scope_type)::text = 'service'::text) AND ((creation_action_id)::text = 'project.guide_sufficiency.run'::text) AND (project_setup_run_id IS NOT NULL) AND (setup_generation IS NOT NULL) AND (agent_material_sha256 IS NOT NULL) AND (agent_material_byte_count IS NOT NULL)))))),
    CONSTRAINT ck_guide_sufficiency_reports_ck_guide_sufficiency_repor_31bb CHECK (((agent_material_byte_count IS NULL) OR (agent_material_byte_count >= 0))),
    CONSTRAINT ck_guide_sufficiency_reports_ck_guide_sufficiency_repor_3e43 CHECK (((setup_generation IS NULL) OR (setup_generation > 0))),
    CONSTRAINT ck_guide_sufficiency_reports_ck_guide_sufficiency_repor_4640 CHECK ((((project_setup_run_id IS NULL) AND (setup_generation IS NULL) AND (agent_material_sha256 IS NULL) AND (agent_material_byte_count IS NULL)) OR ((project_setup_run_id IS NOT NULL) AND (setup_generation IS NOT NULL) AND (agent_material_sha256 IS NOT NULL) AND (agent_material_byte_count IS NOT NULL)))),
    CONSTRAINT ck_guide_sufficiency_reports_ck_guide_sufficiency_repor_841c CHECK (((status)::text = ANY ((ARRAY['passed'::character varying, 'blocked'::character varying, 'passed_with_warnings'::character varying])::text[]))),
    CONSTRAINT ck_guide_sufficiency_reports_ck_guide_sufficiency_repor_b3ec CHECK (((agent_material_sha256 IS NULL) OR ((agent_material_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)))
);
CREATE TABLE public.iso_4217_currency_codes (
    code character varying(3) NOT NULL,
    CONSTRAINT ck_iso_4217_currency_codes_code CHECK (((code)::text ~ '^[A-Z]{3}$'::text))
);
CREATE TABLE public.legacy_actor_identities (
    actor_id character varying(100) NOT NULL,
    external_subject character varying(200) NOT NULL,
    external_issuer character varying(200) NOT NULL,
    display_name character varying(200),
    email character varying(320),
    last_seen_roles json NOT NULL,
    last_claim_snapshot json NOT NULL,
    auth_source character varying(50) NOT NULL,
    is_dev_auth boolean NOT NULL,
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.legacy_workflow_eligibility (
    id character varying(36) NOT NULL,
    actor_id character varying(100) NOT NULL,
    profile_type character varying(50) NOT NULL,
    status character varying(30) NOT NULL,
    skill_tags json NOT NULL,
    scope_type character varying(50) NOT NULL,
    scope_id character varying(100) NOT NULL,
    profile_metadata json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_legacy_workflow_eligibility_profile_type CHECK (((profile_type)::text = ANY ((ARRAY['worker'::character varying, 'reviewer'::character varying, 'admin'::character varying, 'project_manager'::character varying, 'project_owner'::character varying])::text[]))),
    CONSTRAINT ck_legacy_workflow_eligibility_status CHECK (((status)::text = ANY ((ARRAY['observed'::character varying, 'active'::character varying, 'disabled'::character varying])::text[])))
);
CREATE TABLE public.outbox_events (
    event_id uuid NOT NULL,
    event_type character varying(128) NOT NULL,
    event_version smallint NOT NULL,
    producer character varying(32) DEFAULT 'workstream'::character varying NOT NULL,
    aggregate_type character varying(64) NOT NULL,
    aggregate_id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    correlation_id character varying(200) NOT NULL,
    causation_event_id uuid,
    idempotency_key character varying(200) NOT NULL,
    payload jsonb NOT NULL,
    payload_digest character varying(71) NOT NULL,
    occurred_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    delivery_state character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    next_attempt_at timestamp with time zone DEFAULT statement_timestamp(),
    claim_owner character varying(120),
    claim_generation bigint DEFAULT '0'::bigint NOT NULL,
    claimed_at timestamp with time zone,
    claim_expires_at timestamp with time zone,
    last_attempt_at timestamp with time zone,
    last_error_code character varying(80),
    finalized_at timestamp with time zone,
    archived_at timestamp with time zone,
    CONSTRAINT ck_outbox_events_aggregate_type CHECK (((aggregate_type)::text ~ '^[a-z][a-z0-9_]{0,63}$'::text)),
    CONSTRAINT ck_outbox_events_claim_owner CHECK (((claim_owner IS NULL) OR ((claim_owner)::text ~ '^[A-Za-z0-9._:-]{1,120}$'::text))),
    CONSTRAINT ck_outbox_events_correlation_id CHECK (((correlation_id)::text ~ '^[A-Za-z0-9._:-]{1,200}$'::text)),
    CONSTRAINT ck_outbox_events_delivery_counters CHECK (((attempt_count >= 0) AND (claim_generation >= 0) AND (attempt_count = claim_generation))),
    CONSTRAINT ck_outbox_events_delivery_state CHECK (((delivery_state)::text = ANY ((ARRAY['pending'::character varying, 'claimed'::character varying, 'retryable'::character varying, 'acknowledged'::character varying, 'dead_letter'::character varying, 'cancelled'::character varying])::text[]))),
    CONSTRAINT ck_outbox_events_delivery_state_shape CHECK (((((delivery_state)::text = 'pending'::text) AND (attempt_count = 0) AND (next_attempt_at IS NOT NULL) AND (claim_owner IS NULL) AND (claimed_at IS NULL) AND (claim_expires_at IS NULL) AND (last_attempt_at IS NULL) AND (last_error_code IS NULL) AND (finalized_at IS NULL) AND (archived_at IS NULL)) OR (((delivery_state)::text = 'claimed'::text) AND (attempt_count > 0) AND (next_attempt_at IS NULL) AND (claim_owner IS NOT NULL) AND (claimed_at IS NOT NULL) AND (claim_expires_at IS NOT NULL) AND (last_attempt_at = claimed_at) AND (finalized_at IS NULL) AND (archived_at IS NULL)) OR (((delivery_state)::text = 'retryable'::text) AND (attempt_count > 0) AND (next_attempt_at IS NOT NULL) AND (claim_owner IS NULL) AND (claimed_at IS NULL) AND (claim_expires_at IS NULL) AND (last_attempt_at IS NOT NULL) AND (last_error_code IS NOT NULL) AND (finalized_at IS NULL) AND (archived_at IS NULL)) OR (((delivery_state)::text = 'acknowledged'::text) AND (attempt_count > 0) AND (next_attempt_at IS NULL) AND (claim_owner IS NULL) AND (claimed_at IS NULL) AND (claim_expires_at IS NULL) AND (last_attempt_at IS NOT NULL) AND (finalized_at IS NOT NULL)) OR (((delivery_state)::text = 'dead_letter'::text) AND (attempt_count > 0) AND (next_attempt_at IS NULL) AND (claim_owner IS NULL) AND (claimed_at IS NULL) AND (claim_expires_at IS NULL) AND (last_attempt_at IS NOT NULL) AND (last_error_code IS NOT NULL) AND (finalized_at IS NOT NULL)) OR (((delivery_state)::text = 'cancelled'::text) AND (next_attempt_at IS NULL) AND (claim_owner IS NULL) AND (claimed_at IS NULL) AND (claim_expires_at IS NULL) AND (finalized_at IS NOT NULL) AND (((attempt_count = 0) AND (last_attempt_at IS NULL) AND (last_error_code IS NULL)) OR ((attempt_count > 0) AND (last_attempt_at IS NOT NULL)))))),
    CONSTRAINT ck_outbox_events_delivery_timestamps CHECK ((((next_attempt_at IS NULL) OR (next_attempt_at >= occurred_at)) AND ((claimed_at IS NULL) OR (claimed_at >= occurred_at)) AND ((last_attempt_at IS NULL) OR (last_attempt_at >= occurred_at)) AND ((claim_expires_at IS NULL) OR (claim_expires_at > claimed_at)) AND ((finalized_at IS NULL) OR (finalized_at >= occurred_at)) AND ((finalized_at IS NULL) OR (last_attempt_at IS NULL) OR (finalized_at >= last_attempt_at)) AND ((archived_at IS NULL) OR (archived_at >= finalized_at)))),
    CONSTRAINT ck_outbox_events_error_code CHECK (((last_error_code IS NULL) OR ((last_error_code)::text ~ '^[A-Z][A-Z0-9_]{0,79}$'::text))),
    CONSTRAINT ck_outbox_events_event_type CHECK (((event_type)::text ~ '^[A-Za-z][A-Za-z0-9._:-]{0,127}$'::text)),
    CONSTRAINT ck_outbox_events_event_version CHECK (((event_version >= 1) AND (event_version <= 32767))),
    CONSTRAINT ck_outbox_events_idempotency_key CHECK (((idempotency_key)::text ~ '^[A-Za-z0-9._:-]{1,200}$'::text)),
    CONSTRAINT ck_outbox_events_payload_digest CHECK (((payload_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_outbox_events_payload_shape CHECK (((jsonb_typeof(payload) = 'object'::text) AND (octet_length((payload)::text) <= 262144))),
    CONSTRAINT ck_outbox_events_producer CHECK (((producer)::text = 'workstream'::text)),
    CONSTRAINT ck_outbox_events_project_id CHECK (((project_id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text))
);
CREATE TABLE public.payment_policies (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_version character varying(50) NOT NULL,
    base_amount numeric(12,2),
    currency character varying(20),
    payout_type character varying(50),
    revision_payment_rule text,
    rejection_payment_rule text,
    accepted_payment_rule text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.policy_mutation_idempotency_records (
    id uuid NOT NULL,
    actor_profile_id character varying(36) NOT NULL,
    identity_link_id character varying(36) NOT NULL,
    action_id character varying(160) NOT NULL,
    idempotency_key uuid NOT NULL,
    request_digest character varying(71) NOT NULL,
    policy_hash character varying(71) NOT NULL,
    resource_context_digest character varying(71) NOT NULL,
    operation_id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_id character varying(36) NOT NULL,
    policy_id character varying(36) NOT NULL,
    policy_generation integer NOT NULL,
    status character varying(16) NOT NULL,
    response_json json,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    committed_at timestamp with time zone,
    CONSTRAINT ck_policy_mutation_idempotency_records_ck_policy_mutati_26aa CHECK (((((status)::text = 'pending'::text) AND (response_json IS NULL) AND (committed_at IS NULL)) OR (((status)::text = 'committed'::text) AND (response_json IS NOT NULL) AND (committed_at IS NOT NULL)))),
    CONSTRAINT ck_policy_mutation_idempotency_records_ck_policy_mutati_595e CHECK ((((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((policy_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((resource_context_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_policy_mutation_idempotency_records_ck_policy_mutati_7f7f CHECK (((action_id)::text = ANY ((ARRAY['project.review_policy.update'::character varying, 'project.revision_policy.update'::character varying])::text[]))),
    CONSTRAINT ck_policy_mutation_idempotency_records_ck_policy_mutati_8b22 CHECK ((policy_generation > 0)),
    CONSTRAINT ck_policy_mutation_idempotency_records_ck_policy_mutati_dc05 CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'committed'::character varying])::text[])))
);
CREATE TABLE public.pre_submit_checker_policies (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_id character varying(36) NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id character varying(36) NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    effective_policy_id character varying(36) NOT NULL,
    effective_policy_hash character varying(71) NOT NULL,
    lifecycle_status character varying(30) NOT NULL,
    compiler_version character varying(50),
    compiled_bundle json,
    compiled_bundle_hash character varying(71),
    checker_names json NOT NULL,
    checker_configs json NOT NULL,
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    supersedes_pre_submit_checker_policy_id character varying(36),
    superseded_at timestamp with time zone,
    created_by_actor_profile_id character varying(36),
    created_via_identity_link_id character varying(36),
    created_by_admin_role_grant_id uuid,
    creation_scope_type character varying(16),
    creation_scope_project_id character varying(36),
    creation_action_id character varying(160),
    creation_decision_event_id character varying(36),
    CONSTRAINT ck_pre_submit_checker_policies_ck_pre_submit_checker_po_5010 CHECK ((((lifecycle_status)::text <> 'compiled'::text) OR ((compiler_version IS NOT NULL) AND (compiled_bundle IS NOT NULL) AND (compiled_bundle_hash IS NOT NULL) AND ((compiled_bundle_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text)))),
    CONSTRAINT ck_pre_submit_checker_policies_ck_pre_submit_checker_po_a935 CHECK (((lifecycle_status)::text = ANY ((ARRAY['pending_compilation'::character varying, 'compiled'::character varying, 'superseded'::character varying])::text[]))),
    CONSTRAINT ck_pre_submit_checker_policies_ck_pre_submit_policy_aut_90fc CHECK ((((created_by_actor_profile_id IS NULL) AND (created_via_identity_link_id IS NULL) AND (created_by_admin_role_grant_id IS NULL) AND (creation_scope_type IS NULL) AND (creation_scope_project_id IS NULL) AND (creation_action_id IS NULL) AND (creation_decision_event_id IS NULL)) OR ((created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (created_by_admin_role_grant_id IS NOT NULL) AND (creation_scope_type IS NOT NULL) AND (creation_action_id IS NOT NULL) AND ((creation_scope_type)::text = ANY ((ARRAY['system'::character varying, 'project'::character varying])::text[])) AND (creation_scope_project_id IS NOT NULL) AND ((creation_scope_project_id)::text = (project_id)::text) AND ((creation_action_id)::text = 'project.submission_artifact_policy.approve'::text) AND (creation_decision_event_id IS NOT NULL))))
);
CREATE TABLE public.pre_submit_evidence_results (
    id character varying(36) NOT NULL,
    evidence_set_id character varying(36) NOT NULL,
    result_order integer NOT NULL,
    schema_version character varying(80) NOT NULL,
    dispatch_authority character varying(160) NOT NULL,
    definition_id character varying(160) NOT NULL,
    definition_version character varying(40) NOT NULL,
    public_name character varying(160) NOT NULL,
    source character varying(160) NOT NULL,
    phase character varying(40) NOT NULL,
    classification character varying(40) NOT NULL,
    severity character varying(16) NOT NULL,
    status character varying(40) NOT NULL,
    failure_code character varying(160),
    message_code character varying(160) NOT NULL,
    effective_plan_sha256 character varying(71) NOT NULL,
    rule_instance_id character varying(71),
    locked_policy_sha256 character varying(71) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_cla_b0de CHECK (((classification)::text = ANY ((ARRAY['mandatory_security'::character varying, 'mandatory_integrity'::character varying, 'mandatory_accountability'::character varying, 'advisory'::character varying])::text[]))),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_cla_f04e CHECK (((((classification)::text = 'advisory'::text) AND ((severity)::text = 'warning'::text)) OR (((classification)::text <> 'advisory'::text) AND ((severity)::text = 'blocking'::text)))),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_order CHECK ((result_order >= 0)),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_phase CHECK (((phase)::text = ANY ((ARRAY['custody'::character varying, 'identity'::character varying, 'materialization'::character varying, 'default_policy'::character varying, 'project_policy'::character varying])::text[]))),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_plan_sha256 CHECK (((effective_plan_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_pol_cef4 CHECK (((locked_policy_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_rul_321f CHECK (((((phase)::text = 'project_policy'::text) AND (rule_instance_id IS NOT NULL) AND ((rule_instance_id)::text ~ '^sha256:[0-9a-f]{64}$'::text)) OR (((phase)::text <> 'project_policy'::text) AND (rule_instance_id IS NULL)))),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_severity CHECK (((severity)::text = ANY ((ARRAY['blocking'::character varying, 'warning'::character varying])::text[]))),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_status CHECK (((status)::text = ANY ((ARRAY['passed'::character varying, 'warning'::character varying, 'advisory_disabled'::character varying, 'dependency_not_run'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT ck_pre_submit_evidence_results_result_failure_shape CHECK (((((status)::text = 'failed'::text) AND (failure_code IS NOT NULL)) OR (((status)::text <> 'failed'::text) AND (failure_code IS NULL))))
);
CREATE TABLE public.pre_submit_evidence_sets (
    id character varying(36) NOT NULL,
    operation_identity character varying(71) NOT NULL,
    actor_profile_id character varying(36) NOT NULL,
    identity_link_id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    task_id character varying(36) NOT NULL,
    assignment_id character varying(36) NOT NULL,
    predecessor_submission_id character varying(36),
    predecessor_submission_version integer,
    prepared_generation_id character varying(36) NOT NULL,
    archive_sha256 character varying(71) NOT NULL,
    archive_byte_count bigint NOT NULL,
    semantic_manifest_id character varying(36) NOT NULL,
    semantic_manifest_sha256 character varying(71) NOT NULL,
    guide_id character varying(36) NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id character varying(36) NOT NULL,
    source_snapshot_sha256 character varying(71) NOT NULL,
    locked_guide_sha256 character varying(71) NOT NULL,
    effective_policy_id character varying(36) NOT NULL,
    locked_artifact_policy_sha256 character varying(71) NOT NULL,
    pre_submit_policy_id character varying(36) NOT NULL,
    locked_checker_policy_sha256 character varying(71) NOT NULL,
    effective_plan_sha256 character varying(71) NOT NULL,
    catalogue_id character varying(160) NOT NULL,
    catalogue_version character varying(40) NOT NULL,
    catalogue_manifest_sha256 character varying(71) NOT NULL,
    storage_scheme character varying(16) NOT NULL,
    terminal_status character varying(16) NOT NULL,
    eligible boolean NOT NULL,
    result_count integer NOT NULL,
    result_manifest_sha256 character varying(71) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    locked_policy_context_hash character varying(71) NOT NULL,
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_arch_8e95 CHECK (((archive_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_archive_size CHECK ((archive_byte_count >= 0)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_arti_16f8 CHECK (((locked_artifact_policy_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_cata_ffcb CHECK (((catalogue_manifest_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_chec_765d CHECK (((locked_checker_policy_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_guide_sha256 CHECK (((locked_guide_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_mani_7268 CHECK (((semantic_manifest_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_oper_f617 CHECK (((operation_identity)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_plan_sha256 CHECK (((effective_plan_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_pred_bd87 CHECK ((((predecessor_submission_id IS NULL) AND (predecessor_submission_version IS NULL)) OR ((predecessor_submission_id IS NOT NULL) AND (predecessor_submission_version IS NOT NULL)))),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_resu_0b46 CHECK (((result_manifest_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_result_count CHECK ((result_count > 0)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_sour_982b CHECK (((source_snapshot_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_stat_1ae6 CHECK (((((terminal_status)::text = 'passed'::text) AND eligible) OR (((terminal_status)::text = 'blocked'::text) AND (NOT eligible)))),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_stor_022c CHECK (((storage_scheme)::text = ANY ((ARRAY['local'::character varying, 's3'::character varying])::text[]))),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_term_a512 CHECK (((terminal_status)::text = ANY ((ARRAY['passed'::character varying, 'blocked'::character varying])::text[]))),
    CONSTRAINT ck_pre_submit_evidence_sets_policy_context_sha256 CHECK (((locked_policy_context_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text))
);
CREATE TABLE public.project_compensation_adapter_bindings (
    id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    instrument_type character varying(32) NOT NULL,
    adapter_actor_id character varying(36) NOT NULL,
    route_key character varying(120) NOT NULL,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    binding_lifecycle_version integer DEFAULT 1 NOT NULL,
    created_by character varying(36) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    suspended_by character varying(36),
    suspended_at timestamp with time zone,
    retired_by character varying(36),
    retired_at timestamp with time zone,
    CONSTRAINT ck_project_compensation_adapter_bindings_ck_project_com_1870 CHECK ((binding_lifecycle_version > 0)),
    CONSTRAINT ck_project_compensation_adapter_bindings_ck_project_com_3372 CHECK (((instrument_type)::text = ANY ((ARRAY['money'::character varying, 'project_points'::character varying])::text[]))),
    CONSTRAINT ck_project_compensation_adapter_bindings_ck_project_com_6958 CHECK (((route_key)::text ~ '^[A-Za-z][A-Za-z0-9._:-]{0,119}$'::text)),
    CONSTRAINT ck_project_compensation_adapter_bindings_ck_project_com_95ba CHECK ((((status)::text = 'active'::text) AND (binding_lifecycle_version = 1) AND (suspended_by IS NULL) AND (suspended_at IS NULL) AND (retired_by IS NULL) AND (retired_at IS NULL))),
    CONSTRAINT ck_project_compensation_adapter_bindings_ck_project_com_ade1 CHECK ((((suspended_at IS NULL) OR (suspended_at >= created_at)) AND ((retired_at IS NULL) OR (retired_at >= created_at)) AND ((retired_at IS NULL) OR (suspended_at IS NULL) OR (retired_at >= suspended_at)))),
    CONSTRAINT ck_project_compensation_adapter_bindings_ck_project_com_da73 CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'suspended'::character varying, 'retired'::character varying])::text[]))),
    CONSTRAINT ck_project_compensation_adapter_bindings_ck_project_com_f32d CHECK (((route_key)::text !~~ '%..%'::text))
);
CREATE TABLE public.project_compensation_units (
    project_id character varying(36) NOT NULL,
    instrument_type character varying(32) NOT NULL,
    unit_code character varying(32) NOT NULL,
    iso_currency_code character varying(3),
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    created_by character varying(36) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    retired_by character varying(36),
    retired_at timestamp with time zone,
    CONSTRAINT ck_project_compensation_units_instrument_type CHECK (((instrument_type)::text = ANY ((ARRAY['money'::character varying, 'project_points'::character varying])::text[]))),
    CONSTRAINT ck_project_compensation_units_lifecycle_shape CHECK (((((status)::text = 'active'::text) AND (retired_by IS NULL) AND (retired_at IS NULL)) OR (((status)::text = 'retired'::text) AND (retired_by IS NOT NULL) AND (retired_at IS NOT NULL)))),
    CONSTRAINT ck_project_compensation_units_retirement_time CHECK (((retired_at IS NULL) OR (retired_at >= created_at))),
    CONSTRAINT ck_project_compensation_units_status CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'retired'::character varying])::text[]))),
    CONSTRAINT ck_project_compensation_units_unit_identity CHECK (((((instrument_type)::text = 'money'::text) AND (iso_currency_code IS NOT NULL) AND ((unit_code)::text = (iso_currency_code)::text)) OR (((instrument_type)::text = 'project_points'::text) AND (iso_currency_code IS NULL) AND ((unit_code)::text ~ '^[A-Za-z][A-Za-z0-9._:-]{0,31}$'::text))))
);
CREATE TABLE public.project_create_idempotency_records (
    id uuid NOT NULL,
    actor_profile_id character varying(36) NOT NULL,
    identity_link_id character varying(36) NOT NULL,
    action_id character varying(160) NOT NULL,
    idempotency_key uuid NOT NULL,
    request_digest character varying(71) NOT NULL,
    operation_id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    operation_generation integer NOT NULL,
    status character varying(16) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    committed_at timestamp with time zone,
    CONSTRAINT ck_project_create_idempotency_records_ck_project_create_0a41 CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_project_create_idempotency_records_ck_project_create_100d CHECK ((operation_generation = 1)),
    CONSTRAINT ck_project_create_idempotency_records_ck_project_create_3aa0 CHECK (((((status)::text = 'pending'::text) AND (committed_at IS NULL)) OR (((status)::text = 'committed'::text) AND (committed_at IS NOT NULL)))),
    CONSTRAINT ck_project_create_idempotency_records_ck_project_create_action CHECK (((action_id)::text = 'project.create'::text)),
    CONSTRAINT ck_project_create_idempotency_records_ck_project_create_status CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'committed'::character varying])::text[])))
);
CREATE TABLE public.project_guide_compilation_attempts (
    id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_id character varying(36) NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id character varying(36) NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    setup_run_id character varying(36) NOT NULL,
    setup_generation bigint NOT NULL,
    canonical_input_hash character varying(71) NOT NULL,
    guide_material_hash character varying(71) NOT NULL,
    pre_catalogue_id character varying(160) NOT NULL,
    pre_catalogue_version character varying(100) NOT NULL,
    pre_catalogue_schema_version character varying(160) NOT NULL,
    pre_catalogue_manifest_hash character varying(71) NOT NULL,
    post_catalogue_id character varying(160) NOT NULL,
    post_catalogue_version character varying(100) NOT NULL,
    post_catalogue_schema_version character varying(160) NOT NULL,
    post_catalogue_manifest_hash character varying(71) NOT NULL,
    agent_identity character varying(100) NOT NULL,
    agent_version character varying(100) NOT NULL,
    instruction_version character varying(100) NOT NULL,
    provider_idempotency_key uuid NOT NULL,
    status character varying(32) NOT NULL,
    canonical_result json,
    result_hash character varying(71),
    component_hashes json,
    failure_code character varying(100),
    persisted_compilation_id uuid,
    reserved_at timestamp with time zone DEFAULT now() NOT NULL,
    provider_uncertain_at timestamp with time zone,
    accepted_at timestamp with time zone,
    terminal_at timestamp with time zone,
    persisted_at timestamp with time zone,
    CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_00d8 CHECK ((((source_snapshot_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((canonical_input_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((guide_material_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((pre_catalogue_manifest_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((post_catalogue_manifest_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_31c4 CHECK (((component_hashes IS NULL) OR ((json_typeof(component_hashes) = 'object'::text) AND ((component_hashes)::jsonb = jsonb_build_object('sufficiency_hash', (component_hashes ->> 'sufficiency_hash'::text), 'artifact_policy_hash', (component_hashes ->> 'artifact_policy_hash'::text), 'requirement_inventory_hash', (component_hashes ->> 'requirement_inventory_hash'::text), 'pre_submit_hash', (component_hashes ->> 'pre_submit_hash'::text), 'post_submit_hash', (component_hashes ->> 'post_submit_hash'::text), 'capability_suggestions_hash', (component_hashes ->> 'capability_suggestions_hash'::text), 'setup_notes_hash', (component_hashes ->> 'setup_notes_hash'::text))) AND COALESCE(((component_hashes ->> 'sufficiency_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'artifact_policy_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'requirement_inventory_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'pre_submit_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'post_submit_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'capability_suggestions_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'setup_notes_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false)))),
    CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_444c CHECK (((((status)::text = 'compilation_reserved'::text) AND (provider_uncertain_at IS NULL) AND (accepted_at IS NULL) AND (terminal_at IS NULL) AND (persisted_at IS NULL) AND (canonical_result IS NULL) AND (result_hash IS NULL) AND (component_hashes IS NULL) AND (failure_code IS NULL) AND (persisted_compilation_id IS NULL)) OR (((status)::text = 'compilation_provider_uncertain'::text) AND (provider_uncertain_at IS NOT NULL) AND (accepted_at IS NULL) AND (terminal_at IS NULL) AND (persisted_at IS NULL) AND (canonical_result IS NULL) AND (result_hash IS NULL) AND (component_hashes IS NULL) AND (failure_code IS NULL) AND (persisted_compilation_id IS NULL)) OR (((status)::text = 'provider_result_accepted'::text) AND (accepted_at IS NOT NULL) AND (terminal_at IS NULL) AND (persisted_at IS NULL) AND (canonical_result IS NOT NULL) AND (result_hash IS NOT NULL) AND (component_hashes IS NOT NULL) AND (failure_code IS NULL) AND (persisted_compilation_id IS NULL)) OR (((status)::text = 'compilation_persisted'::text) AND (accepted_at IS NOT NULL) AND (persisted_at IS NOT NULL) AND (terminal_at IS NULL) AND (canonical_result IS NOT NULL) AND (result_hash IS NOT NULL) AND (component_hashes IS NOT NULL) AND (failure_code IS NULL) AND (persisted_compilation_id IS NOT NULL)) OR (((status)::text = 'compilation_invalid_terminal'::text) AND (terminal_at IS NOT NULL) AND (accepted_at IS NULL) AND (persisted_at IS NULL) AND (canonical_result IS NULL) AND (result_hash IS NULL) AND (component_hashes IS NULL) AND (persisted_compilation_id IS NULL) AND ((failure_code)::text = ANY ((ARRAY['schema_invalid'::character varying, 'unsafe_text'::character varying, 'hash_mismatch'::character varying, 'context_mismatch'::character varying])::text[]))))),
    CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_513e CHECK ((setup_generation > 0)),
    CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_6057 CHECK (((canonical_result IS NULL) OR (octet_length((canonical_result)::text) <= 4194304))),
    CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_6609 CHECK (((result_hash IS NULL) OR ((result_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_6c82 CHECK (((status)::text = ANY ((ARRAY['compilation_reserved'::character varying, 'compilation_provider_uncertain'::character varying, 'provider_result_accepted'::character varying, 'compilation_invalid_terminal'::character varying, 'compilation_persisted'::character varying])::text[])))
);
CREATE TABLE public.project_guide_compilations (
    id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_id character varying(36) NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id character varying(36) NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    setup_run_id character varying(36) NOT NULL,
    setup_generation bigint NOT NULL,
    canonical_input_hash character varying(71) NOT NULL,
    guide_material_hash character varying(71) NOT NULL,
    pre_catalogue_manifest_hash character varying(71) NOT NULL,
    post_catalogue_manifest_hash character varying(71) NOT NULL,
    agent_identity character varying(100) NOT NULL,
    agent_version character varying(100) NOT NULL,
    instruction_version character varying(100) NOT NULL,
    canonical_result json NOT NULL,
    result_hash character varying(71) NOT NULL,
    component_hashes json NOT NULL,
    supersedes_compilation_id uuid,
    created_by_actor_profile_id character varying(36) NOT NULL,
    created_via_identity_link_id character varying(36) NOT NULL,
    created_by_service_identity character varying(160) NOT NULL,
    creation_action_id character varying(160) NOT NULL,
    authorization_decision_event_id character varying(36) NOT NULL,
    authorization_resource_context_digest character varying(71) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_project_guide_compilations_ck_project_guide_compilat_8a51 CHECK (((setup_generation > 0) AND ((created_by_service_identity)::text = 'workstream.project.setup'::text) AND ((creation_action_id)::text = 'project.guide_compilation.execute'::text))),
    CONSTRAINT ck_project_guide_compilations_ck_project_guide_compilat_9cd9 CHECK ((((source_snapshot_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((canonical_input_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((guide_material_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((pre_catalogue_manifest_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((post_catalogue_manifest_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((result_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_project_guide_compilations_ck_project_guide_compilat_d554 CHECK (((authorization_resource_context_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_project_guide_compilations_ck_project_guide_compilat_dafe CHECK (((octet_length((canonical_result)::text) <= 4194304) AND (json_typeof(component_hashes) = 'object'::text) AND ((component_hashes)::jsonb = jsonb_build_object('sufficiency_hash', (component_hashes ->> 'sufficiency_hash'::text), 'artifact_policy_hash', (component_hashes ->> 'artifact_policy_hash'::text), 'requirement_inventory_hash', (component_hashes ->> 'requirement_inventory_hash'::text), 'pre_submit_hash', (component_hashes ->> 'pre_submit_hash'::text), 'post_submit_hash', (component_hashes ->> 'post_submit_hash'::text), 'capability_suggestions_hash', (component_hashes ->> 'capability_suggestions_hash'::text), 'setup_notes_hash', (component_hashes ->> 'setup_notes_hash'::text))) AND COALESCE(((component_hashes ->> 'sufficiency_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'artifact_policy_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'requirement_inventory_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'pre_submit_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'post_submit_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'capability_suggestions_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'setup_notes_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false)))
);
CREATE TABLE public.project_guides (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    version character varying(50) NOT NULL,
    status character varying(30) NOT NULL,
    content_markdown text NOT NULL,
    approved_by character varying(100),
    effective_at timestamp with time zone,
    change_summary text,
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    superseded_at timestamp with time zone,
    last_mutated_by_actor_profile_id character varying(36),
    last_mutated_via_identity_link_id character varying(36),
    last_mutated_by_admin_role_grant_id uuid,
    last_mutation_scope_type character varying(16),
    last_mutation_scope_project_id character varying(36),
    last_mutation_action_id character varying(160),
    last_authorization_decision_event_id character varying(36),
    mutation_generation integer,
    selected_review_policy_id character varying(36),
    selected_review_policy_hash character varying(71),
    selected_revision_policy_id character varying(36),
    selected_revision_policy_hash character varying(71),
    selected_review_policy_generation integer,
    selected_revision_policy_generation integer,
    CONSTRAINT ck_project_guides_active_policy_selection_required CHECK ((((status)::text <> ALL ((ARRAY['active'::character varying, 'superseded'::character varying])::text[])) OR ((selected_review_policy_id IS NOT NULL) AND (selected_review_policy_generation IS NOT NULL) AND (selected_review_policy_hash IS NOT NULL) AND (selected_revision_policy_id IS NOT NULL) AND (selected_revision_policy_generation IS NOT NULL) AND (selected_revision_policy_hash IS NOT NULL)))),
    CONSTRAINT ck_project_guides_guide_mutation_authority_shape CHECK ((((mutation_generation IS NULL) AND (last_mutated_by_actor_profile_id IS NULL) AND (last_mutated_via_identity_link_id IS NULL) AND (last_mutated_by_admin_role_grant_id IS NULL) AND (last_mutation_scope_type IS NULL) AND (last_mutation_scope_project_id IS NULL) AND (last_mutation_action_id IS NULL) AND (last_authorization_decision_event_id IS NULL)) OR ((mutation_generation > 0) AND (last_mutated_by_actor_profile_id IS NOT NULL) AND (last_mutated_via_identity_link_id IS NOT NULL) AND (last_mutated_by_admin_role_grant_id IS NOT NULL) AND ((last_mutation_scope_type)::text = ANY ((ARRAY['system'::character varying, 'project'::character varying])::text[])) AND ((((last_mutation_scope_type)::text = 'system'::text) AND (last_mutation_scope_project_id IS NULL)) OR (((last_mutation_scope_type)::text = 'project'::text) AND ((last_mutation_scope_project_id)::text = (project_id)::text))) AND ((last_mutation_action_id)::text = ANY ((ARRAY['project.guide.create'::character varying, 'project.guide.update'::character varying, 'project.guide_source_snapshot.create'::character varying])::text[])) AND (last_authorization_decision_event_id IS NOT NULL)))),
    CONSTRAINT ck_project_guides_policy_selection_shape CHECK (((((selected_review_policy_id IS NULL) AND (selected_review_policy_generation IS NULL) AND (selected_review_policy_hash IS NULL)) OR ((selected_review_policy_id IS NOT NULL) AND (selected_review_policy_generation IS NOT NULL) AND (selected_review_policy_hash IS NOT NULL))) AND (((selected_revision_policy_id IS NULL) AND (selected_revision_policy_generation IS NULL) AND (selected_revision_policy_hash IS NULL)) OR ((selected_revision_policy_id IS NOT NULL) AND (selected_revision_policy_generation IS NOT NULL) AND (selected_revision_policy_hash IS NOT NULL)))))
);
CREATE TABLE public.project_role_grants (
    id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    actor_profile_id character varying(36) NOT NULL,
    role character varying(24) NOT NULL,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    version smallint DEFAULT '1'::smallint NOT NULL,
    grant_method character varying(16) DEFAULT 'manual'::character varying NOT NULL,
    qualification_snapshot_id uuid NOT NULL,
    granted_by_actor_profile_id character varying(36) NOT NULL,
    granted_by_admin_role_grant_id uuid NOT NULL,
    grant_reason text NOT NULL,
    granted_at timestamp with time zone DEFAULT now() NOT NULL,
    revoked_by_actor_profile_id character varying(36),
    revoked_by_admin_role_grant_id uuid,
    revoked_reason text,
    revoked_at timestamp with time zone,
    CONSTRAINT ck_project_role_grants_grant_method CHECK (((grant_method)::text = 'manual'::text)),
    CONSTRAINT ck_project_role_grants_lifecycle CHECK (((((status)::text = 'active'::text) AND (version = 1) AND (revoked_by_actor_profile_id IS NULL) AND (revoked_by_admin_role_grant_id IS NULL) AND (revoked_reason IS NULL) AND (revoked_at IS NULL)) OR (((status)::text = 'revoked'::text) AND (version = 2) AND (revoked_by_actor_profile_id IS NOT NULL) AND (revoked_by_admin_role_grant_id IS NOT NULL) AND (revoked_reason IS NOT NULL) AND (revoked_at IS NOT NULL)))),
    CONSTRAINT ck_project_role_grants_reason CHECK ((public.project_role_reason_is_safe(grant_reason) AND ((revoked_reason IS NULL) OR public.project_role_reason_is_safe(revoked_reason)))),
    CONSTRAINT ck_project_role_grants_role CHECK (((role)::text = ANY ((ARRAY['submitter'::character varying, 'reviewer'::character varying, 'adjudicator'::character varying])::text[])))
);
CREATE TABLE public.project_role_qualification_snapshots (
    id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    actor_profile_id character varying(36) NOT NULL,
    requested_role character varying(24) NOT NULL,
    skills_snapshot jsonb NOT NULL,
    reputation_snapshot jsonb NOT NULL,
    prior_project_work_refs jsonb NOT NULL,
    external_expertise_refs jsonb NOT NULL,
    captured_by_actor_profile_id character varying(36) NOT NULL,
    captured_by_admin_role_grant_id uuid NOT NULL,
    captured_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_project_role_qualification_snapshots_availability CHECK ((public.project_role_availability_is_safe(skills_snapshot) AND public.project_role_availability_is_safe(reputation_snapshot))),
    CONSTRAINT ck_project_role_qualification_snapshots_external_expertise_refs CHECK (public.project_role_reference_array_is_safe(external_expertise_refs, false)),
    CONSTRAINT ck_project_role_qualification_snapshots_prior_work_refs CHECK (public.project_role_reference_array_is_safe(prior_project_work_refs, true)),
    CONSTRAINT ck_project_role_qualification_snapshots_role CHECK (((requested_role)::text = ANY ((ARRAY['submitter'::character varying, 'reviewer'::character varying, 'adjudicator'::character varying])::text[])))
);
CREATE TABLE public.project_setup_runs (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_id character varying(36) NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id character varying(36) NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    celery_task_id character varying(155),
    status character varying(50) NOT NULL,
    current_step character varying(100) NOT NULL,
    output_sufficiency_report_id character varying(36),
    output_submission_artifact_policy_id character varying(36),
    error_code character varying(100),
    error_summary text,
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    output_post_submit_checker_policy_id character varying(36),
    post_submit_derivation_summary json,
    setup_generation bigint NOT NULL,
    authorized_by_actor_profile_id character varying(36),
    authorized_via_identity_link_id character varying(36),
    authorized_by_admin_role_grant_id uuid,
    authorization_scope_type character varying(16),
    authorization_scope_project_id character varying(36),
    authorization_action_id character varying(160),
    authorization_decision_event_id character varying(36),
    error_artifact_incident_id character varying(36),
    continuation_verification_job_id character varying(36),
    continuation_started_at timestamp with time zone,
    CONSTRAINT ck_project_setup_runs_ck_project_setup_runs_generation_positive CHECK ((setup_generation > 0)),
    CONSTRAINT ck_project_setup_runs_ck_project_setup_runs_status CHECK (((status)::text = ANY ((ARRAY['queued'::character varying, 'dispatch_pending'::character varying, 'enqueue_failed'::character varying, 'enqueue_identity_mismatch'::character varying, 'running_sufficiency_agent'::character varying, 'sufficiency_blocked'::character varying, 'running_policy_derivation_agent'::character varying, 'policy_draft_ready'::character varying, 'running_post_submit_derivation_agent'::character varying, 'post_submit_setup_blocked'::character varying, 'post_submit_policy_compiled'::character varying, 'setup_blocked'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT ck_project_setup_runs_setup_run_authority_shape CHECK ((((authorized_by_actor_profile_id IS NULL) AND (authorized_via_identity_link_id IS NULL) AND (authorized_by_admin_role_grant_id IS NULL) AND (authorization_scope_type IS NULL) AND (authorization_scope_project_id IS NULL) AND (authorization_action_id IS NULL) AND (authorization_decision_event_id IS NULL)) OR ((authorized_by_actor_profile_id IS NOT NULL) AND (authorized_via_identity_link_id IS NOT NULL) AND (authorized_by_admin_role_grant_id IS NOT NULL) AND ((authorization_scope_type)::text = ANY ((ARRAY['system'::character varying, 'project'::character varying])::text[])) AND ((((authorization_scope_type)::text = 'system'::text) AND (authorization_scope_project_id IS NULL)) OR (((authorization_scope_type)::text = 'project'::text) AND ((authorization_scope_project_id)::text = (project_id)::text))) AND ((authorization_action_id)::text = 'project.guide_source_snapshot.create'::text) AND (authorization_decision_event_id IS NOT NULL))))
);
CREATE TABLE public.projects (
    id character varying(36) NOT NULL,
    name character varying(200) NOT NULL,
    slug character varying(120) NOT NULL,
    description text,
    status character varying(30) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by_actor_profile_id character varying(36),
    created_via_identity_link_id character varying(36),
    created_by_admin_role_grant_id uuid,
    creation_scope_type character varying(16),
    creation_action_id character varying(160),
    authorization_decision_event_id character varying(36),
    CONSTRAINT ck_projects_creation_authority_shape CHECK ((((created_by_actor_profile_id IS NULL) AND (created_via_identity_link_id IS NULL) AND (created_by_admin_role_grant_id IS NULL) AND (creation_scope_type IS NULL) AND (creation_action_id IS NULL) AND (authorization_decision_event_id IS NULL)) OR ((created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (created_by_admin_role_grant_id IS NOT NULL) AND ((creation_scope_type)::text = 'system'::text) AND ((creation_action_id)::text = 'project.create'::text) AND (authorization_decision_event_id IS NOT NULL))))
);
CREATE TABLE public.review_admission_idempotency_records (
    id uuid NOT NULL,
    idempotency_key uuid NOT NULL,
    operation_id uuid NOT NULL,
    request_digest character varying(71) NOT NULL,
    project_id character varying(36) NOT NULL,
    task_id character varying(36) NOT NULL,
    submission_id character varying(36) NOT NULL,
    submission_version integer NOT NULL,
    admitting_checker_run_id character varying(36) NOT NULL,
    status character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    review_queue_entry_id uuid,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    committed_at timestamp with time zone,
    CONSTRAINT ck_review_admission_idempotency_records_ck_review_admis_2b6d CHECK ((submission_version > 0)),
    CONSTRAINT ck_review_admission_idempotency_records_ck_review_admis_4cd5 CHECK (((((status)::text = 'pending'::text) AND (review_queue_entry_id IS NULL) AND (committed_at IS NULL)) OR (((status)::text = 'committed'::text) AND (review_queue_entry_id IS NOT NULL) AND (committed_at IS NOT NULL)))),
    CONSTRAINT ck_review_admission_idempotency_records_ck_review_admis_88bf CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_review_admission_idempotency_records_ck_review_admis_b8b8 CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'committed'::character varying])::text[])))
);
CREATE TABLE public.review_leases (
    id uuid NOT NULL,
    review_queue_entry_id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    task_id character varying(36) NOT NULL,
    submission_id character varying(36) NOT NULL,
    submission_version integer NOT NULL,
    reviewer_id character varying(36) NOT NULL,
    reviewer_contribution_policy_version_id uuid NOT NULL,
    attempt_generation integer NOT NULL,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    claimed_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    closed_at timestamp with time zone,
    close_reason character varying(32),
    CONSTRAINT ck_review_leases_attempt_generation_positive CHECK ((attempt_generation > 0)),
    CONSTRAINT ck_review_leases_closure_after_claim CHECK (((closed_at IS NULL) OR (closed_at >= claimed_at))),
    CONSTRAINT ck_review_leases_expiry_after_claim CHECK ((expires_at > claimed_at)),
    CONSTRAINT ck_review_leases_lifecycle_shape CHECK (((((status)::text = 'active'::text) AND (closed_at IS NULL) AND (close_reason IS NULL)) OR (((status)::text = 'consumed'::text) AND (closed_at IS NOT NULL) AND ((close_reason)::text = 'review_recorded'::text)) OR (((status)::text = 'released'::text) AND (closed_at IS NOT NULL) AND ((close_reason)::text = 'manual_release'::text)) OR (((status)::text = 'expired'::text) AND (closed_at IS NOT NULL) AND ((close_reason)::text = 'lease_expired'::text)) OR (((status)::text = 'revoked'::text) AND (closed_at IS NOT NULL) AND ((close_reason)::text = ANY ((ARRAY['grant_revoked'::character varying, 'admin_override'::character varying])::text[]))))),
    CONSTRAINT ck_review_leases_status CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'consumed'::character varying, 'released'::character varying, 'expired'::character varying, 'revoked'::character varying])::text[])))
);
CREATE TABLE public.review_policies (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_version character varying(50) NOT NULL,
    requires_second_review boolean NOT NULL,
    allowed_decisions json NOT NULL,
    minimum_finding_fields json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    policy_generation integer NOT NULL,
    policy_hash character varying(71) NOT NULL,
    semantics_status character varying(24) NOT NULL,
    supersedes_policy_id character varying(36),
    review_preference_window_seconds integer,
    review_lease_duration_seconds integer,
    max_active_review_leases_per_reviewer integer,
    self_review_allowed boolean,
    reject_policy character varying(32),
    finding_evidence_requirement character varying(32),
    predecessor_policy_hash character varying(71),
    created_by_actor_profile_id character varying(36),
    created_via_identity_link_id character varying(36),
    created_by_admin_role_grant_id uuid,
    creation_scope_type character varying(16),
    creation_scope_project_id character varying(36),
    creation_action_id character varying(160),
    authorization_decision_event_id character varying(36),
    CONSTRAINT ck_review_policies_review_policy_authority_shape CHECK ((((semantics_status)::text = 'legacy_incomplete'::text) OR ((created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (created_by_admin_role_grant_id IS NOT NULL) AND ((creation_scope_type)::text = ANY ((ARRAY['system'::character varying, 'project'::character varying])::text[])) AND ((creation_action_id)::text = 'project.review_policy.update'::text) AND (authorization_decision_event_id IS NOT NULL)))),
    CONSTRAINT ck_review_policies_review_policy_identity_shape CHECK (((policy_generation > 0) AND ((policy_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((semantics_status)::text = ANY ((ARRAY['complete'::character varying, 'legacy_incomplete'::character varying])::text[])))),
    CONSTRAINT ck_review_policies_review_policy_predecessor_shape CHECK ((((supersedes_policy_id IS NULL) AND (predecessor_policy_hash IS NULL) AND (policy_generation = 1)) OR ((supersedes_policy_id IS NOT NULL) AND ((predecessor_policy_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND (policy_generation > 1)) OR ((semantics_status)::text = 'legacy_incomplete'::text))),
    CONSTRAINT ck_review_policies_review_policy_semantics_shape CHECK ((((semantics_status)::text = 'legacy_incomplete'::text) OR ((review_preference_window_seconds > 0) AND (review_lease_duration_seconds > 0) AND (max_active_review_leases_per_reviewer = 1) AND (self_review_allowed = false) AND ((reject_policy)::text = 'close_task'::text) AND ((finding_evidence_requirement)::text = ANY ((ARRAY['optional'::character varying, 'required_for_blocking'::character varying, 'required_for_all'::character varying])::text[])))))
);
CREATE TABLE public.review_queue_entries (
    id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    task_id character varying(36) NOT NULL,
    submission_id character varying(36) NOT NULL,
    submission_version integer NOT NULL,
    admitting_checker_run_id character varying(36) NOT NULL,
    queue_state character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    routing_mode character varying(16) NOT NULL,
    routing_reason character varying(32) NOT NULL,
    first_queued_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    available_since timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    preferred_reviewer_id character varying(36),
    preference_expires_at timestamp with time zone,
    closed_at timestamp with time zone,
    closed_reason character varying(32),
    routing_generation integer DEFAULT 1 NOT NULL,
    lifecycle_generation integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    active_lease_id uuid,
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_availab_d484 CHECK ((available_since >= first_queued_at)),
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_generat_38b7 CHECK (((routing_generation > 0) AND (lifecycle_generation > 0))),
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_lifecycle_shape CHECK (((((queue_state)::text = 'pending'::text) AND (active_lease_id IS NULL) AND (closed_at IS NULL) AND (closed_reason IS NULL)) OR (((queue_state)::text = 'leased'::text) AND (active_lease_id IS NOT NULL) AND (closed_at IS NULL) AND (closed_reason IS NULL)) OR (((queue_state)::text = 'closed'::text) AND (active_lease_id IS NULL) AND (closed_at IS NOT NULL) AND ((closed_reason)::text = ANY ((ARRAY['review_recorded'::character varying, 'task_closed'::character varying, 'admin_cancelled'::character varying])::text[])) AND (closed_at >= first_queued_at)))),
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_queue_state CHECK (((queue_state)::text = ANY ((ARRAY['pending'::character varying, 'leased'::character varying, 'closed'::character varying])::text[]))),
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_routing_mode CHECK (((routing_mode)::text = ANY ((ARRAY['open'::character varying, 'preferred'::character varying])::text[]))),
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_routing_reason CHECK (((routing_reason)::text = ANY ((ARRAY['first_submission'::character varying, 'revision_return'::character varying, 'admin_assignment'::character varying])::text[]))),
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_routing_shape CHECK (((((routing_mode)::text = 'open'::text) AND (preferred_reviewer_id IS NULL) AND (preference_expires_at IS NULL)) OR (((routing_mode)::text = 'preferred'::text) AND (preferred_reviewer_id IS NOT NULL) AND (preference_expires_at IS NOT NULL) AND (preference_expires_at > first_queued_at)))),
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_submiss_2f6b CHECK ((submission_version > 0))
);
CREATE TABLE public.revision_policies (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_version character varying(50) NOT NULL,
    max_revision_rounds integer NOT NULL,
    revision_deadline_hours integer NOT NULL,
    allowed_resubmission_states json NOT NULL,
    reviewer_reassignment_rule text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    policy_generation integer NOT NULL,
    policy_hash character varying(71) NOT NULL,
    semantics_status character varying(24) NOT NULL,
    supersedes_policy_id character varying(36),
    predecessor_policy_hash character varying(71),
    created_by_actor_profile_id character varying(36),
    created_via_identity_link_id character varying(36),
    created_by_admin_role_grant_id uuid,
    creation_scope_type character varying(16),
    creation_scope_project_id character varying(36),
    creation_action_id character varying(160),
    authorization_decision_event_id character varying(36),
    CONSTRAINT ck_revision_policies_revision_policy_authority_shape CHECK ((((semantics_status)::text = 'legacy_incomplete'::text) OR ((created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (created_by_admin_role_grant_id IS NOT NULL) AND ((creation_scope_type)::text = ANY ((ARRAY['system'::character varying, 'project'::character varying])::text[])) AND ((creation_action_id)::text = 'project.revision_policy.update'::text) AND (authorization_decision_event_id IS NOT NULL)))),
    CONSTRAINT ck_revision_policies_revision_policy_identity_shape CHECK (((policy_generation > 0) AND ((policy_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((semantics_status)::text = ANY ((ARRAY['complete'::character varying, 'legacy_incomplete'::character varying])::text[])))),
    CONSTRAINT ck_revision_policies_revision_policy_predecessor_shape CHECK ((((supersedes_policy_id IS NULL) AND (predecessor_policy_hash IS NULL) AND (policy_generation = 1)) OR ((supersedes_policy_id IS NOT NULL) AND ((predecessor_policy_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND (policy_generation > 1)) OR ((semantics_status)::text = 'legacy_incomplete'::text))),
    CONSTRAINT ck_revision_policies_revision_policy_semantics_shape CHECK ((((semantics_status)::text = 'legacy_incomplete'::text) OR ((max_revision_rounds > 0) AND (revision_deadline_hours > 0))))
);
CREATE TABLE public.submission_artifact_policies (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_id character varying(36) NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id character varying(36) NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    policy_version character varying(50) NOT NULL,
    lifecycle_status character varying(30) NOT NULL,
    policy_body json NOT NULL,
    policy_hash character varying(71) NOT NULL,
    derivation_source character varying(100) NOT NULL,
    source_material_refs json NOT NULL,
    derivation_agent_name character varying(100),
    derivation_agent_version character varying(50),
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    approved_by_role character varying(50),
    approved_by_actor character varying(100),
    approved_at timestamp with time zone,
    supersedes_policy_id character varying(36),
    superseded_at timestamp with time zone,
    change_summary text,
    created_by_actor_profile_id character varying(36),
    created_via_identity_link_id character varying(36),
    created_by_admin_role_grant_id uuid,
    created_by_service_identity character varying(160),
    creation_scope_type character varying(16),
    creation_scope_project_id character varying(36),
    creation_action_id character varying(160),
    creation_decision_event_id character varying(36),
    approved_by_actor_profile_id character varying(36),
    approved_via_identity_link_id character varying(36),
    approved_by_admin_role_grant_id uuid,
    approval_scope_type character varying(16),
    approval_scope_project_id character varying(36),
    approval_action_id character varying(160),
    approval_decision_event_id character varying(36),
    CONSTRAINT ck_submission_artifact_policies_ck_submission_artifact__20ca CHECK (((lifecycle_status)::text = ANY ((ARRAY['draft'::character varying, 'approved'::character varying, 'superseded'::character varying])::text[]))),
    CONSTRAINT ck_submission_artifact_policies_ck_submission_artifact__52ca CHECK ((((lifecycle_status)::text <> 'approved'::text) OR (((approved_by_role)::text = ANY ((ARRAY['admin'::character varying, 'project_manager'::character varying])::text[])) AND (approved_by_actor IS NOT NULL) AND (approved_at IS NOT NULL)))),
    CONSTRAINT ck_submission_artifact_policies_ck_submission_policy_ap_0e4d CHECK ((((approved_by_actor_profile_id IS NULL) AND (approved_via_identity_link_id IS NULL) AND (approved_by_admin_role_grant_id IS NULL) AND (approval_scope_type IS NULL) AND (approval_scope_project_id IS NULL) AND (approval_action_id IS NULL) AND (approval_decision_event_id IS NULL)) OR ((approved_by_actor_profile_id IS NOT NULL) AND (approved_via_identity_link_id IS NOT NULL) AND (approved_by_admin_role_grant_id IS NOT NULL) AND (approval_scope_type IS NOT NULL) AND (approval_action_id IS NOT NULL) AND ((approval_scope_type)::text = ANY ((ARRAY['system'::character varying, 'project'::character varying])::text[])) AND (approval_scope_project_id IS NOT NULL) AND ((approval_scope_project_id)::text = (project_id)::text) AND ((approval_action_id)::text = 'project.submission_artifact_policy.approve'::text) AND (approval_decision_event_id IS NOT NULL)))),
    CONSTRAINT ck_submission_artifact_policies_ck_submission_policy_cr_0629 CHECK ((((created_by_actor_profile_id IS NULL) AND (created_via_identity_link_id IS NULL) AND (created_by_admin_role_grant_id IS NULL) AND (created_by_service_identity IS NULL) AND (creation_scope_type IS NULL) AND (creation_scope_project_id IS NULL) AND (creation_action_id IS NULL) AND (creation_decision_event_id IS NULL)) OR ((created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (creation_scope_type IS NOT NULL) AND (creation_action_id IS NOT NULL) AND (creation_scope_project_id IS NOT NULL) AND ((creation_scope_project_id)::text = (project_id)::text) AND (creation_decision_event_id IS NOT NULL) AND ((creation_action_id)::text = ANY ((ARRAY['project.submission_artifact_policy.create'::character varying, 'project.submission_artifact_policy.derive'::character varying, 'project.submission_artifact_policy.update'::character varying])::text[])) AND (((created_by_admin_role_grant_id IS NOT NULL) AND (created_by_service_identity IS NULL) AND ((creation_scope_type)::text = ANY ((ARRAY['system'::character varying, 'project'::character varying])::text[]))) OR ((created_by_admin_role_grant_id IS NULL) AND (created_by_service_identity IS NOT NULL) AND ((created_by_service_identity)::text = 'workstream.project.setup'::text) AND ((creation_scope_type)::text = 'service'::text) AND ((creation_action_id)::text = 'project.submission_artifact_policy.derive'::text))))))
);
CREATE TABLE public.submission_bundle_admissions (
    id character varying(36) NOT NULL,
    durable_intent_id character varying(36) NOT NULL,
    pre_submit_evidence_set_id character varying(36) NOT NULL,
    put_attempt_id character varying(36) NOT NULL,
    artifact_content_id character varying(36) NOT NULL,
    verified_replica_id character varying(36) NOT NULL,
    verification_receipt_id character varying(36) NOT NULL,
    put_operation_receipt_id character varying(36),
    put_observation_receipt_id character varying(36),
    actor_profile_id character varying(36) NOT NULL,
    identity_link_id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    task_id character varying(36) NOT NULL,
    assignment_id character varying(36) NOT NULL,
    predecessor_submission_id character varying(36),
    predecessor_submission_version integer,
    locked_policy_context_hash character varying(71) NOT NULL,
    semantic_manifest_id character varying(36) NOT NULL,
    semantic_manifest_sha256 character varying(71) NOT NULL,
    archive_sha256 character varying(71) NOT NULL,
    archive_byte_count bigint NOT NULL,
    status character varying(16) DEFAULT 'ready'::character varying NOT NULL,
    ready_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    consumed_by_submission_id character varying(36),
    stale_at timestamp with time zone,
    stale_reason character varying(500),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_submission_bundle_admissions_archive_sha256 CHECK (((archive_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_submission_bundle_admissions_archive_size CHECK ((archive_byte_count >= 0)),
    CONSTRAINT ck_submission_bundle_admissions_manifest_sha256 CHECK (((semantic_manifest_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_submission_bundle_admissions_policy_context_hash CHECK (((locked_policy_context_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_submission_bundle_admissions_predecessor_shape CHECK (((predecessor_submission_id IS NULL) = (predecessor_submission_version IS NULL))),
    CONSTRAINT ck_submission_bundle_admissions_status CHECK (((status)::text = ANY ((ARRAY['ready'::character varying, 'consumed'::character varying, 'stale'::character varying])::text[]))),
    CONSTRAINT ck_submission_bundle_admissions_terminal_shape CHECK (((((status)::text = 'ready'::text) AND (consumed_at IS NULL) AND (consumed_by_submission_id IS NULL) AND (stale_at IS NULL) AND (stale_reason IS NULL)) OR (((status)::text = 'consumed'::text) AND (consumed_at IS NOT NULL) AND (consumed_by_submission_id IS NOT NULL) AND (stale_at IS NULL) AND (stale_reason IS NULL)) OR (((status)::text = 'stale'::text) AND (consumed_at IS NULL) AND (consumed_by_submission_id IS NULL) AND (stale_at IS NOT NULL) AND ((octet_length((stale_reason)::text) >= 1) AND (octet_length((stale_reason)::text) <= 500))))),
    CONSTRAINT ck_submission_bundle_admissions_write_receipt_shape CHECK (((((put_operation_receipt_id IS NOT NULL))::integer + ((put_observation_receipt_id IS NOT NULL))::integer) = 1))
);
CREATE TABLE public.submission_bundle_durable_intents (
    id character varying(36) NOT NULL,
    pre_submit_evidence_set_id character varying(36) NOT NULL,
    put_attempt_id character varying(36) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.submission_policy_mutation_idempotency_records (
    id uuid NOT NULL,
    actor_profile_id character varying(36) NOT NULL,
    identity_link_id character varying(36) NOT NULL,
    service_identity character varying(160),
    action_id character varying(160) NOT NULL,
    idempotency_key uuid,
    request_digest character varying(71) NOT NULL,
    resource_context_digest character varying(71) NOT NULL,
    resource_context_json json NOT NULL,
    operation_id uuid NOT NULL,
    project_id character varying(36) NOT NULL,
    guide_id character varying(36) NOT NULL,
    source_snapshot_id character varying(36) NOT NULL,
    policy_id character varying(36) NOT NULL,
    setup_run_id character varying(36),
    setup_generation bigint NOT NULL,
    setup_task_id uuid,
    correlation_id uuid,
    status character varying(16) NOT NULL,
    response_json json,
    committed_policy_id character varying(36),
    committed_effective_policy_id character varying(36),
    committed_pre_submit_policy_id character varying(36),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    committed_at timestamp with time zone,
    CONSTRAINT ck_submission_policy_mutation_idempotency_records_ck_su_0119 CHECK ((((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((resource_context_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_submission_policy_mutation_idempotency_records_ck_su_0dbe CHECK (((action_id)::text = ANY ((ARRAY['project.submission_artifact_policy.create'::character varying, 'project.submission_artifact_policy.derive'::character varying, 'project.submission_artifact_policy.update'::character varying, 'project.submission_artifact_policy.approve'::character varying])::text[]))),
    CONSTRAINT ck_submission_policy_mutation_idempotency_records_ck_su_2b53 CHECK ((setup_generation > 0)),
    CONSTRAINT ck_submission_policy_mutation_idempotency_records_ck_su_58d4 CHECK (((((status)::text = ANY ((ARRAY['reserved'::character varying, 'pending'::character varying])::text[])) AND (response_json IS NULL) AND (committed_at IS NULL) AND (committed_policy_id IS NULL) AND (committed_effective_policy_id IS NULL) AND (committed_pre_submit_policy_id IS NULL)) OR (((status)::text = 'committed'::text) AND (response_json IS NOT NULL) AND (committed_at IS NOT NULL) AND (committed_policy_id IS NOT NULL) AND ((((action_id)::text = 'project.submission_artifact_policy.approve'::text) AND (committed_effective_policy_id IS NOT NULL) AND (committed_pre_submit_policy_id IS NOT NULL)) OR (((action_id)::text <> 'project.submission_artifact_policy.approve'::text) AND (committed_effective_policy_id IS NULL) AND (committed_pre_submit_policy_id IS NULL)))))),
    CONSTRAINT ck_submission_policy_mutation_idempotency_records_ck_su_a824 CHECK (((status)::text = ANY ((ARRAY['reserved'::character varying, 'pending'::character varying, 'committed'::character varying])::text[]))),
    CONSTRAINT ck_submission_policy_mutation_idempotency_records_ck_su_b357 CHECK ((((service_identity IS NULL) AND (idempotency_key IS NOT NULL) AND (setup_run_id IS NULL) AND (setup_task_id IS NULL) AND (correlation_id IS NULL)) OR ((service_identity IS NOT NULL) AND ((service_identity)::text = 'workstream.project.setup'::text) AND (idempotency_key IS NULL) AND ((action_id)::text = 'project.submission_artifact_policy.derive'::text) AND (setup_run_id IS NOT NULL) AND (setup_task_id IS NOT NULL) AND (correlation_id IS NOT NULL))))
);
CREATE TABLE public.submissions (
    id character varying(36) NOT NULL,
    task_id character varying(36) NOT NULL,
    contributor_id character varying(36) NOT NULL,
    version integer NOT NULL,
    status character varying(30) NOT NULL,
    summary text NOT NULL,
    package_uri character varying(1000),
    package_hash character varying(128) NOT NULL,
    artifact_hash_manifest json NOT NULL,
    worker_attestation text NOT NULL,
    locked_guide_version character varying(50) NOT NULL,
    locked_payment_policy_version character varying(50) NOT NULL,
    submitted_at timestamp with time zone DEFAULT now() NOT NULL,
    locked_at timestamp with time zone,
    supersedes_submission_id character varying(36),
    locked_guide_source_snapshot_id character varying(36),
    locked_guide_source_snapshot_hash character varying(71),
    locked_effective_project_submission_artifact_policy_id character varying(36),
    locked_effective_project_submission_artifact_policy_hash character varying(71),
    locked_pre_submit_checker_policy_id character varying(36),
    locked_pre_submit_checker_bundle_hash character varying(71),
    locked_post_submit_checker_policy_id character varying(36),
    locked_post_submit_checker_policy_version character varying(50),
    locked_post_submit_checker_policy_hash character varying(71),
    locked_post_submit_checker_policy_body json,
    locked_review_policy_id character varying(36) NOT NULL,
    locked_review_policy_generation integer NOT NULL,
    locked_review_policy_hash character varying(71) NOT NULL,
    locked_revision_policy_id character varying(36) NOT NULL,
    locked_revision_policy_generation integer NOT NULL,
    locked_revision_policy_hash character varying(71) NOT NULL,
    CONSTRAINT ck_submissions_post_submit_policy_lock_complete CHECK (((locked_post_submit_checker_policy_id IS NOT NULL) AND (locked_post_submit_checker_policy_version IS NOT NULL) AND (locked_post_submit_checker_policy_hash IS NOT NULL) AND (locked_post_submit_checker_policy_body IS NOT NULL)))
);
CREATE TABLE public.task_assignments (
    id character varying(36) NOT NULL,
    task_id character varying(36) NOT NULL,
    contributor_id character varying(36) NOT NULL,
    assigned_by character varying(100) NOT NULL,
    assigned_at timestamp with time zone DEFAULT now() NOT NULL,
    accepted_at timestamp with time zone,
    released_at timestamp with time zone,
    status character varying(30) NOT NULL
);
CREATE TABLE public.workstream_tasks (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    locked_guide_version character varying(50),
    locked_payment_policy_version character varying(50),
    source_type character varying(50) NOT NULL,
    source_ref character varying(500),
    source_payload_hash character varying(128),
    import_batch_id character varying(100),
    external_task_id character varying(200),
    title character varying(300) NOT NULL,
    description text NOT NULL,
    task_type character varying(100),
    difficulty character varying(50),
    skill_tags json NOT NULL,
    estimated_time_minutes integer,
    base_amount numeric(12,2),
    currency character varying(20),
    payout_type character varying(50),
    status character varying(30) NOT NULL,
    acceptance_criteria text,
    rejection_criteria text,
    deadline_at timestamp with time zone,
    created_by character varying(100) NOT NULL,
    assigned_to character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    locked_guide_source_snapshot_id character varying(36),
    locked_guide_source_snapshot_hash character varying(71),
    locked_effective_project_submission_artifact_policy_id character varying(36),
    locked_effective_project_submission_artifact_policy_hash character varying(71),
    locked_pre_submit_checker_policy_id character varying(36),
    locked_pre_submit_checker_bundle_hash character varying(71),
    locked_post_submit_checker_policy_id character varying(36),
    locked_post_submit_checker_policy_version character varying(50),
    locked_post_submit_checker_policy_hash character varying(71),
    locked_post_submit_checker_policy_body json,
    locked_review_policy_id character varying(36),
    locked_review_policy_generation integer,
    locked_review_policy_hash character varying(71),
    locked_revision_policy_id character varying(36),
    locked_revision_policy_generation integer,
    locked_revision_policy_hash character varying(71),
    CONSTRAINT ck_workstream_tasks_post_submit_policy_lock_complete CHECK ((((status)::text = 'draft'::text) OR ((locked_post_submit_checker_policy_id IS NOT NULL) AND (locked_post_submit_checker_policy_version IS NOT NULL) AND (locked_post_submit_checker_policy_hash IS NOT NULL) AND (locked_post_submit_checker_policy_body IS NOT NULL)))),
    CONSTRAINT ck_workstream_tasks_review_revision_policy_lock_required CHECK ((((status)::text = 'draft'::text) OR ((locked_review_policy_id IS NOT NULL) AND (locked_review_policy_generation IS NOT NULL) AND (locked_review_policy_hash IS NOT NULL) AND (locked_revision_policy_id IS NOT NULL) AND (locked_revision_policy_generation IS NOT NULL) AND (locked_revision_policy_hash IS NOT NULL)))),
    CONSTRAINT ck_workstream_tasks_review_revision_policy_lock_shape CHECK ((((locked_review_policy_id IS NULL) AND (locked_review_policy_generation IS NULL) AND (locked_review_policy_hash IS NULL) AND (locked_revision_policy_id IS NULL) AND (locked_revision_policy_generation IS NULL) AND (locked_revision_policy_hash IS NULL)) OR ((locked_review_policy_id IS NOT NULL) AND (locked_review_policy_generation IS NOT NULL) AND (locked_review_policy_hash IS NOT NULL) AND (locked_revision_policy_id IS NOT NULL) AND (locked_revision_policy_generation IS NOT NULL) AND (locked_revision_policy_hash IS NOT NULL))))
);
ALTER TABLE ONLY public.actor_profile_migration_state ALTER COLUMN id SET DEFAULT nextval('public.actor_profile_migration_state_id_seq'::regclass);
ALTER TABLE ONLY public.authority_control ALTER COLUMN id SET DEFAULT nextval('public.authority_control_id_seq'::regclass);
ALTER TABLE ONLY public.project_role_qualification_snapshots
    ADD CONSTRAINT grant_reference UNIQUE (id, actor_profile_id, project_id, requested_role);
ALTER TABLE ONLY public.actor_identity_links
    ADD CONSTRAINT pk_actor_identity_links PRIMARY KEY (id);
ALTER TABLE ONLY public.actor_profile_migration_state
    ADD CONSTRAINT pk_actor_profile_migration_state PRIMARY KEY (id);
ALTER TABLE ONLY public.actor_profiles
    ADD CONSTRAINT pk_actor_profiles PRIMARY KEY (id);
ALTER TABLE ONLY public.admin_role_grants
    ADD CONSTRAINT pk_admin_role_grants PRIMARY KEY (id);
ALTER TABLE ONLY public.api_rate_control_counters
    ADD CONSTRAINT pk_api_rate_control_counters PRIMARY KEY (control_scope, key_digest);
ALTER TABLE ONLY public.artifact_admission_charges
    ADD CONSTRAINT pk_artifact_admission_charges PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_admission_scopes
    ADD CONSTRAINT pk_artifact_admission_scopes PRIMARY KEY (scope_type, scope_id);
ALTER TABLE ONLY public.artifact_bindings
    ADD CONSTRAINT pk_artifact_bindings PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_contents
    ADD CONSTRAINT pk_artifact_contents PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_operation_receipts
    ADD CONSTRAINT pk_artifact_operation_receipts PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_put_attempt_charges
    ADD CONSTRAINT pk_artifact_put_attempt_charges PRIMARY KEY (attempt_id, charge_id);
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT pk_artifact_put_attempts PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_put_observation_receipts
    ADD CONSTRAINT pk_artifact_put_observation_receipts PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT pk_artifact_recovery_attempts PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_replicas
    ADD CONSTRAINT pk_artifact_replicas PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_storage_namespaces
    ADD CONSTRAINT pk_artifact_storage_namespaces PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_verification_jobs
    ADD CONSTRAINT pk_artifact_verification_jobs PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_verification_receipts
    ADD CONSTRAINT pk_artifact_verification_receipts PRIMARY KEY (id);
ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT pk_audit_events PRIMARY KEY (id);
ALTER TABLE ONLY public.authority_control
    ADD CONSTRAINT pk_authority_control PRIMARY KEY (id);
ALTER TABLE ONLY public.authority_idempotency_records
    ADD CONSTRAINT pk_authority_idempotency_records PRIMARY KEY (id);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT pk_checker_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.checker_results
    ADD CONSTRAINT pk_checker_results PRIMARY KEY (id);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT pk_checker_runs PRIMARY KEY (id);
ALTER TABLE ONLY public.contribution_award_definitions
    ADD CONSTRAINT pk_contribution_award_definitions PRIMARY KEY (id);
ALTER TABLE ONLY public.contribution_policies
    ADD CONSTRAINT pk_contribution_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT pk_contribution_policy_versions PRIMARY KEY (id);
ALTER TABLE ONLY public.contribution_rules
    ADD CONSTRAINT pk_contribution_rules PRIMARY KEY (id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT pk_effective_project_submission_artifact_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.evidence_items
    ADD CONSTRAINT pk_evidence_items PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_mutation_idempotency_records
    ADD CONSTRAINT pk_guide_mutation_idempotency_records PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT pk_guide_source_artifact_bindings PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_artifact_incidents
    ADD CONSTRAINT pk_guide_source_artifact_incidents PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_artifact_ingests
    ADD CONSTRAINT pk_guide_source_artifact_ingests PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_extracted_contents
    ADD CONSTRAINT pk_guide_source_extracted_contents PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_extraction_attempts
    ADD CONSTRAINT pk_guide_source_extraction_attempts PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_extraction_retry_budgets
    ADD CONSTRAINT pk_guide_source_extraction_retry_budgets PRIMARY KEY (binding_id);
ALTER TABLE ONLY public.guide_source_extraction_usages
    ADD CONSTRAINT pk_guide_source_extraction_usages PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_format_classifications
    ADD CONSTRAINT pk_guide_source_format_classifications PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_snapshot_items
    ADD CONSTRAINT pk_guide_source_snapshot_items PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT pk_guide_source_snapshots PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT pk_guide_sufficiency_mutation_idempotency_records PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_sufficiency_report_source_usages
    ADD CONSTRAINT pk_guide_sufficiency_report_source_usages PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT pk_guide_sufficiency_reports PRIMARY KEY (id);
ALTER TABLE ONLY public.iso_4217_currency_codes
    ADD CONSTRAINT pk_iso_4217_currency_codes PRIMARY KEY (code);
ALTER TABLE ONLY public.legacy_actor_identities
    ADD CONSTRAINT pk_legacy_actor_identities PRIMARY KEY (actor_id);
ALTER TABLE ONLY public.legacy_workflow_eligibility
    ADD CONSTRAINT pk_legacy_workflow_eligibility PRIMARY KEY (id);
ALTER TABLE ONLY public.outbox_events
    ADD CONSTRAINT pk_outbox_events PRIMARY KEY (event_id);
ALTER TABLE ONLY public.payment_policies
    ADD CONSTRAINT pk_payment_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.policy_mutation_idempotency_records
    ADD CONSTRAINT pk_policy_mutation_idempotency_records PRIMARY KEY (id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT pk_pre_submit_checker_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.pre_submit_evidence_results
    ADD CONSTRAINT pk_pre_submit_evidence_results PRIMARY KEY (id);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT pk_pre_submit_evidence_sets PRIMARY KEY (id);
ALTER TABLE ONLY public.project_compensation_adapter_bindings
    ADD CONSTRAINT pk_project_compensation_adapter_bindings PRIMARY KEY (id);
ALTER TABLE ONLY public.project_compensation_units
    ADD CONSTRAINT pk_project_compensation_units PRIMARY KEY (project_id, instrument_type, unit_code);
ALTER TABLE ONLY public.project_create_idempotency_records
    ADD CONSTRAINT pk_project_create_idempotency_records PRIMARY KEY (id);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT pk_project_guide_compilation_attempts PRIMARY KEY (id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT pk_project_guide_compilations PRIMARY KEY (id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT pk_project_guides PRIMARY KEY (id);
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT pk_project_role_grants PRIMARY KEY (id);
ALTER TABLE ONLY public.project_role_qualification_snapshots
    ADD CONSTRAINT pk_project_role_qualification_snapshots PRIMARY KEY (id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT pk_project_setup_runs PRIMARY KEY (id);
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT pk_projects PRIMARY KEY (id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT pk_review_admission_idempotency_records PRIMARY KEY (id);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT pk_review_leases PRIMARY KEY (id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT pk_review_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT pk_review_queue_entries PRIMARY KEY (id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT pk_revision_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT pk_submission_artifact_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT pk_submission_bundle_admissions PRIMARY KEY (id);
ALTER TABLE ONLY public.submission_bundle_durable_intents
    ADD CONSTRAINT pk_submission_bundle_durable_intents PRIMARY KEY (id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT pk_submission_policy_mutation_idempotency_records PRIMARY KEY (id);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT pk_submissions PRIMARY KEY (id);
ALTER TABLE ONLY public.task_assignments
    ADD CONSTRAINT pk_task_assignments PRIMARY KEY (id);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT pk_workstream_tasks PRIMARY KEY (id);
ALTER TABLE ONLY public.actor_profiles
    ADD CONSTRAINT service_identity UNIQUE (service_identity);
ALTER TABLE ONLY public.actor_identity_links
    ADD CONSTRAINT uq_actor_identity_links_actor_profile UNIQUE (actor_profile_id);
ALTER TABLE ONLY public.actor_identity_links
    ADD CONSTRAINT uq_actor_identity_links_external_identity UNIQUE (issuer, subject);
ALTER TABLE ONLY public.actor_identity_links
    ADD CONSTRAINT uq_actor_identity_links_id_profile UNIQUE (id, actor_profile_id);
ALTER TABLE ONLY public.artifact_admission_charges
    ADD CONSTRAINT uq_artifact_admission_charge_scope_content UNIQUE (scope_type, scope_id, sha256, byte_count);
ALTER TABLE ONLY public.artifact_bindings
    ADD CONSTRAINT uq_artifact_binding_scope_version UNIQUE (project_id, resource_type, resource_id, logical_role, scope_version);
ALTER TABLE ONLY public.artifact_bindings
    ADD CONSTRAINT uq_artifact_binding_supersedes UNIQUE (supersedes_binding_id);
ALTER TABLE ONLY public.artifact_contents
    ADD CONSTRAINT uq_artifact_content_digest_size UNIQUE (sha256, byte_count);
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT uq_artifact_put_attempt_operation UNIQUE (operation_identity);
ALTER TABLE ONLY public.artifact_put_observation_receipts
    ADD CONSTRAINT uq_artifact_put_observation_fence UNIQUE (put_attempt_id, execution_generation);
ALTER TABLE ONLY public.artifact_operation_receipts
    ADD CONSTRAINT uq_artifact_receipt_put_attempt UNIQUE (put_attempt_id);
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT uq_artifact_recovery_idempotency UNIQUE (requester_actor_profile_id, source_verification_job_id, recovery_class, client_idempotency_key);
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT uq_artifact_recovery_retry_job UNIQUE (retry_verification_job_id);
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT uq_artifact_recovery_source_job UNIQUE (source_verification_job_id);
ALTER TABLE ONLY public.artifact_replicas
    ADD CONSTRAINT uq_artifact_replica_provider_object UNIQUE (storage_namespace_id, provider_object_ref);
ALTER TABLE ONLY public.artifact_replicas
    ADD CONSTRAINT uq_artifact_replicas_id_content UNIQUE (id, content_id);
ALTER TABLE ONLY public.artifact_storage_namespaces
    ADD CONSTRAINT uq_artifact_storage_namespace_fingerprint UNIQUE (namespace_fingerprint);
ALTER TABLE ONLY public.artifact_storage_namespaces
    ADD CONSTRAINT uq_artifact_storage_namespace_id_fingerprint UNIQUE (id, namespace_fingerprint);
ALTER TABLE ONLY public.artifact_verification_receipts
    ADD CONSTRAINT uq_artifact_verification_fence UNIQUE (verification_job_id, execution_generation);
ALTER TABLE ONLY public.artifact_verification_jobs
    ADD CONSTRAINT uq_artifact_verification_parent UNIQUE (parent_verification_job_id);
ALTER TABLE ONLY public.authority_idempotency_records
    ADD CONSTRAINT uq_authority_idempotency_records_actor_reference UNIQUE (id, actor_ref_kind, actor_ref);
ALTER TABLE ONLY public.authority_idempotency_records
    ADD CONSTRAINT uq_authority_idempotency_records_replay_namespace UNIQUE (actor_ref_kind, actor_ref, operation, idempotency_key);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT uq_checker_policies_id_version_hash UNIQUE (id, guide_version, policy_hash);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT uq_checker_runs_submission_attempt UNIQUE (submission_id, attempt_number);
ALTER TABLE ONLY public.project_compensation_adapter_bindings
    ADD CONSTRAINT uq_compensation_binding_ownership UNIQUE (id, project_id, instrument_type);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT uq_compilation_attempt_provider_key UNIQUE (provider_idempotency_key);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT uq_compilation_attempt_setup_generation UNIQUE (setup_run_id, setup_generation);
ALTER TABLE ONLY public.contribution_award_definitions
    ADD CONSTRAINT uq_contribution_award_definition_instrument UNIQUE (contribution_rule_id, instrument_type);
ALTER TABLE ONLY public.contribution_policies
    ADD CONSTRAINT uq_contribution_policy_ownership UNIQUE (id, project_id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT uq_contribution_policy_version_number UNIQUE (contribution_policy_id, version_number);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT uq_contribution_policy_version_ownership UNIQUE (id, contribution_policy_id, project_id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT uq_contribution_policy_version_project UNIQUE (id, project_id);
ALTER TABLE ONLY public.contribution_rules
    ADD CONSTRAINT uq_contribution_rule_ownership UNIQUE (id, contribution_policy_version_id, project_id, contribution_type);
ALTER TABLE ONLY public.contribution_rules
    ADD CONSTRAINT uq_contribution_rule_type UNIQUE (contribution_policy_version_id, contribution_type);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT uq_effective_project_submission_artifact_policies_id_hash UNIQUE (id, effective_policy_hash);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT uq_guide_bindings_exact_read UNIQUE (id, content_id, verified_replica_id, setup_generation);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT uq_guide_bindings_extraction_attempt_lineage UNIQUE (id, content_id, setup_generation);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT uq_guide_bindings_extraction_lineage UNIQUE (id, content_id, source_item_id, project_setup_run_id, setup_generation);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT uq_guide_bindings_item_generation UNIQUE (source_item_id, setup_generation);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT uq_guide_bindings_supersedes UNIQUE (supersedes_binding_id);
ALTER TABLE ONLY public.guide_source_format_classifications
    ADD CONSTRAINT uq_guide_classifications_binding UNIQUE (binding_id);
ALTER TABLE ONLY public.guide_source_format_classifications
    ADD CONSTRAINT uq_guide_classifications_extraction_lineage UNIQUE (id, binding_id, content_id, setup_generation);
ALTER TABLE ONLY public.guide_source_extracted_contents
    ADD CONSTRAINT uq_guide_extracted_contents_exact_usage UNIQUE (id, content_id);
ALTER TABLE ONLY public.guide_source_extracted_contents
    ADD CONSTRAINT uq_guide_extracted_contents_identity UNIQUE (content_id, detected_format, extractor_name, extractor_version, policy_version);
ALTER TABLE ONLY public.guide_source_extraction_attempts
    ADD CONSTRAINT uq_guide_extraction_attempts UNIQUE (binding_id, policy_version, attempt_number);
ALTER TABLE ONLY public.guide_source_extraction_attempts
    ADD CONSTRAINT uq_guide_extraction_attempts_exact_usage UNIQUE (id, binding_id, content_id, setup_generation, status);
ALTER TABLE ONLY public.guide_source_extraction_usages
    ADD CONSTRAINT uq_guide_extraction_usages UNIQUE (binding_id, extracted_content_id);
ALTER TABLE ONLY public.guide_source_extraction_usages
    ADD CONSTRAINT uq_guide_extraction_usages_exact_provenance UNIQUE (id, source_item_id, binding_id, content_id, extraction_attempt_id, extracted_content_id, project_setup_run_id, setup_generation);
ALTER TABLE ONLY public.guide_mutation_idempotency_records
    ADD CONSTRAINT uq_guide_mutation_operation_identity UNIQUE (operation_id);
ALTER TABLE ONLY public.guide_mutation_idempotency_records
    ADD CONSTRAINT uq_guide_mutation_replay_namespace UNIQUE (actor_profile_id, action_id, idempotency_key);
ALTER TABLE ONLY public.guide_source_artifact_ingests
    ADD CONSTRAINT uq_guide_source_artifact_ingests_source_item_id UNIQUE (source_item_id);
ALTER TABLE ONLY public.guide_source_snapshot_items
    ADD CONSTRAINT uq_guide_source_snapshot_items_exact_lineage UNIQUE (id, source_snapshot_id);
ALTER TABLE ONLY public.guide_source_snapshot_items
    ADD CONSTRAINT uq_guide_source_snapshot_items_snapshot_order UNIQUE (source_snapshot_id, item_order);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT uq_guide_source_snapshots_exact_lineage UNIQUE (id, project_id, guide_id);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT uq_guide_source_snapshots_id_hash UNIQUE (id, bundle_hash);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT uq_guide_source_snapshots_project_version_hash UNIQUE (project_id, guide_version, bundle_hash);
ALTER TABLE ONLY public.legacy_actor_identities
    ADD CONSTRAINT uq_legacy_actor_identities_external_identity UNIQUE (external_issuer, external_subject);
ALTER TABLE ONLY public.legacy_workflow_eligibility
    ADD CONSTRAINT uq_legacy_workflow_eligibility_actor_type_scope UNIQUE (actor_id, profile_type, scope_type, scope_id);
ALTER TABLE ONLY public.outbox_events
    ADD CONSTRAINT uq_outbox_events_idempotency_key UNIQUE (idempotency_key);
ALTER TABLE ONLY public.payment_policies
    ADD CONSTRAINT uq_payment_policies_project_version UNIQUE (project_id, guide_version);
ALTER TABLE ONLY public.policy_mutation_idempotency_records
    ADD CONSTRAINT uq_policy_mutation_operation_identity UNIQUE (operation_id);
ALTER TABLE ONLY public.policy_mutation_idempotency_records
    ADD CONSTRAINT uq_policy_mutation_replay_namespace UNIQUE (actor_profile_id, action_id, idempotency_key);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT uq_pre_submit_checker_policies_id_compiled_bundle_hash UNIQUE (id, compiled_bundle_hash);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT uq_pre_submit_evidence_operation UNIQUE (operation_identity);
ALTER TABLE ONLY public.pre_submit_evidence_results
    ADD CONSTRAINT uq_pre_submit_result_definition UNIQUE (evidence_set_id, definition_id);
ALTER TABLE ONLY public.pre_submit_evidence_results
    ADD CONSTRAINT uq_pre_submit_result_order UNIQUE (evidence_set_id, result_order);
ALTER TABLE ONLY public.project_create_idempotency_records
    ADD CONSTRAINT uq_project_create_operation_identity UNIQUE (operation_id);
ALTER TABLE ONLY public.project_create_idempotency_records
    ADD CONSTRAINT uq_project_create_project_identity UNIQUE (project_id);
ALTER TABLE ONLY public.project_create_idempotency_records
    ADD CONSTRAINT uq_project_create_replay_namespace UNIQUE (actor_profile_id, action_id, idempotency_key);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT uq_project_guide_compilation_attempt UNIQUE (attempt_id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT uq_project_guide_compilation_id_attempt UNIQUE (id, attempt_id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT uq_project_guide_compilation_predecessor UNIQUE (supersedes_compilation_id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT uq_project_guide_compilation_scope UNIQUE (id, project_id, guide_id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT uq_project_guides_id_project_version UNIQUE (id, project_id, version);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT uq_project_guides_project_version UNIQUE (project_id, version);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT uq_project_setup_runs_exact_generation UNIQUE (id, project_id, guide_id, source_snapshot_id, setup_generation);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT uq_project_setup_runs_guide_generation UNIQUE (guide_id, setup_generation);
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT uq_projects_slug UNIQUE (slug);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT uq_review_admission_checker_run UNIQUE (admitting_checker_run_id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT uq_review_admission_operation UNIQUE (operation_id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT uq_review_admission_replay_key UNIQUE (idempotency_key);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT uq_review_lease_attempt UNIQUE (review_queue_entry_id, attempt_generation);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT uq_review_lease_queue_identity UNIQUE (review_queue_entry_id, id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT uq_review_policies_project_version_generation UNIQUE (project_id, guide_version, policy_generation);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT uq_review_policy_lineage UNIQUE (id, policy_generation, policy_hash);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT uq_review_policy_scoped_lineage UNIQUE (project_id, guide_version, id, policy_generation, policy_hash);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT uq_review_queue_admission_identity UNIQUE (id, project_id, task_id, submission_id, submission_version, admitting_checker_run_id);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT uq_review_queue_lease_lineage UNIQUE (id, project_id, task_id, submission_id, submission_version);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT uq_review_queue_submission UNIQUE (submission_id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT uq_revision_policies_project_version_generation UNIQUE (project_id, guide_version, policy_generation);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT uq_revision_policy_lineage UNIQUE (id, policy_generation, policy_hash);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT uq_revision_policy_scoped_lineage UNIQUE (project_id, guide_version, id, policy_generation, policy_hash);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT uq_submission_artifact_policies_id_hash UNIQUE (id, policy_hash);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT uq_submission_artifact_policies_project_version_policy UNIQUE (project_id, guide_version, policy_version);
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT uq_submission_bundle_admission_evidence UNIQUE (pre_submit_evidence_set_id);
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT uq_submission_bundle_admission_intent UNIQUE (durable_intent_id);
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT uq_submission_bundle_admission_verification UNIQUE (verification_receipt_id);
ALTER TABLE ONLY public.submission_bundle_durable_intents
    ADD CONSTRAINT uq_submission_bundle_intent_evidence UNIQUE (pre_submit_evidence_set_id);
ALTER TABLE ONLY public.submission_bundle_durable_intents
    ADD CONSTRAINT uq_submission_bundle_intent_put_attempt UNIQUE (put_attempt_id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT uq_submission_policy_operation_identity UNIQUE (operation_id);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT uq_submissions_id_locked_post_submit_policy_hash UNIQUE (id, locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT uq_submissions_id_task_version UNIQUE (id, task_id, version);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT uq_submissions_id_version UNIQUE (id, version);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT uq_submissions_task_version UNIQUE (task_id, version);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT uq_sufficiency_mutation_operation_identity UNIQUE (operation_id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT uq_sufficiency_mutation_replay_namespace UNIQUE (actor_profile_id, idempotency_key);
ALTER TABLE ONLY public.guide_sufficiency_report_source_usages
    ADD CONSTRAINT uq_sufficiency_report_extraction_usage UNIQUE (report_id, extraction_usage_id);
ALTER TABLE ONLY public.guide_sufficiency_report_source_usages
    ADD CONSTRAINT uq_sufficiency_report_item_order UNIQUE (report_id, item_order);
ALTER TABLE ONLY public.task_assignments
    ADD CONSTRAINT uq_task_assignments_id_task_contributor UNIQUE (id, task_id, contributor_id);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_effective_policy_hash UNIQUE (id, locked_effective_project_submission_artifact_policy_id, locked_effective_project_submission_artifact_policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_guide UNIQUE (id, locked_guide_version);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_payment_policy UNIQUE (id, locked_payment_policy_version);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_post_submit_policy_hash UNIQUE (id, locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_pre_submit_checker_hash UNIQUE (id, locked_pre_submit_checker_policy_id, locked_pre_submit_checker_bundle_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_review_policy UNIQUE (id, locked_review_policy_id, locked_review_policy_generation, locked_review_policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_revision_policy UNIQUE (id, locked_revision_policy_id, locked_revision_policy_generation, locked_revision_policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_source_snapshot_hash UNIQUE (id, locked_guide_source_snapshot_id, locked_guide_source_snapshot_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_project UNIQUE (id, project_id);
CREATE INDEX ix_actor_identity_links_issuer_subject_status ON public.actor_identity_links USING btree (issuer, subject, status);
CREATE INDEX ix_actor_profiles_last_seen_at ON public.actor_profiles USING btree (last_seen_at);
CREATE INDEX ix_actor_profiles_status_actor_kind ON public.actor_profiles USING btree (status, actor_kind);
CREATE INDEX ix_admin_role_grants_effective_candidate ON public.admin_role_grants USING btree (target_actor_profile_id, status, scope_type, scope_project_id);
CREATE INDEX ix_admin_role_grants_final_access_admin ON public.admin_role_grants USING btree (role, status) WHERE (((role)::text = 'access_administrator'::text) AND ((status)::text = 'active'::text) AND ((scope_type)::text = 'system'::text));
CREATE INDEX ix_admin_role_grants_history ON public.admin_role_grants USING btree (target_actor_profile_id, granted_at, id);
CREATE INDEX ix_api_rate_control_counters_window_expires_at ON public.api_rate_control_counters USING btree (window_expires_at);
CREATE INDEX ix_artifact_bindings_content_id ON public.artifact_bindings USING btree (content_id);
CREATE INDEX ix_artifact_bindings_project_id ON public.artifact_bindings USING btree (project_id);
CREATE INDEX ix_artifact_bindings_scope ON public.artifact_bindings USING btree (project_id, resource_type, resource_id, logical_role, scope_version DESC);
CREATE INDEX ix_artifact_bindings_supersedes_binding_id ON public.artifact_bindings USING btree (supersedes_binding_id);
CREATE INDEX ix_artifact_contents_sha256 ON public.artifact_contents USING btree (sha256);
CREATE INDEX ix_artifact_operation_receipts_put_attempt_id ON public.artifact_operation_receipts USING btree (put_attempt_id);
CREATE INDEX ix_artifact_operation_receipts_replica_id ON public.artifact_operation_receipts USING btree (replica_id);
CREATE INDEX ix_artifact_put_attempts_checker_run_id ON public.artifact_put_attempts USING btree (checker_run_id);
CREATE INDEX ix_artifact_put_attempts_guide_source_item_id ON public.artifact_put_attempts USING btree (guide_source_item_id);
CREATE INDEX ix_artifact_put_attempts_next_run_at ON public.artifact_put_attempts USING btree (next_run_at);
CREATE INDEX ix_artifact_put_attempts_project_id ON public.artifact_put_attempts USING btree (project_id);
CREATE INDEX ix_artifact_put_attempts_receipt_id ON public.artifact_put_attempts USING btree (receipt_id);
CREATE INDEX ix_artifact_put_attempts_replica_id ON public.artifact_put_attempts USING btree (replica_id);
CREATE INDEX ix_artifact_put_attempts_status ON public.artifact_put_attempts USING btree (status);
CREATE INDEX ix_artifact_put_attempts_task_id ON public.artifact_put_attempts USING btree (task_id);
CREATE INDEX ix_artifact_put_observation_receipts_put_attempt_id ON public.artifact_put_observation_receipts USING btree (put_attempt_id);
CREATE INDEX ix_artifact_recovery_attempts_parent_recovery_attempt_id ON public.artifact_recovery_attempts USING btree (parent_recovery_attempt_id);
CREATE INDEX ix_artifact_recovery_attempts_project_id ON public.artifact_recovery_attempts USING btree (project_id);
CREATE INDEX ix_artifact_recovery_attempts_requester_actor_profile_id ON public.artifact_recovery_attempts USING btree (requester_actor_profile_id);
CREATE INDEX ix_artifact_recovery_attempts_submission_id ON public.artifact_recovery_attempts USING btree (submission_id);
CREATE INDEX ix_artifact_recovery_attempts_task_id ON public.artifact_recovery_attempts USING btree (task_id);
CREATE INDEX ix_artifact_replicas_content_id ON public.artifact_replicas USING btree (content_id);
CREATE INDEX ix_artifact_replicas_storage_namespace_id ON public.artifact_replicas USING btree (storage_namespace_id);
CREATE INDEX ix_artifact_verification_jobs_next_run_at ON public.artifact_verification_jobs USING btree (next_run_at);
CREATE INDEX ix_artifact_verification_jobs_originating_put_attempt_id ON public.artifact_verification_jobs USING btree (originating_put_attempt_id);
CREATE INDEX ix_artifact_verification_jobs_parent_verification_job_id ON public.artifact_verification_jobs USING btree (parent_verification_job_id);
CREATE INDEX ix_artifact_verification_jobs_replica_id ON public.artifact_verification_jobs USING btree (replica_id);
CREATE INDEX ix_artifact_verification_jobs_status ON public.artifact_verification_jobs USING btree (status);
CREATE INDEX ix_artifact_verification_receipts_verification_job_id ON public.artifact_verification_receipts USING btree (verification_job_id);
CREATE INDEX ix_audit_events_actor_id ON public.audit_events USING btree (actor_id);
CREATE INDEX ix_audit_events_actor_ref ON public.audit_events USING btree (actor_ref_kind, actor_id);
CREATE INDEX ix_audit_events_correlation_id ON public.audit_events USING btree (correlation_id);
CREATE INDEX ix_audit_events_entity_id ON public.audit_events USING btree (entity_id);
CREATE INDEX ix_audit_events_entity_type ON public.audit_events USING btree (entity_type);
CREATE INDEX ix_audit_events_event_type ON public.audit_events USING btree (event_type);
CREATE INDEX ix_audit_events_occurred_at ON public.audit_events USING btree (occurred_at);
CREATE INDEX ix_audit_events_project_id ON public.audit_events USING btree (project_id);
CREATE INDEX ix_audit_events_request_id ON public.audit_events USING btree (request_id);
CREATE INDEX ix_checker_policies_effective_policy_hash ON public.checker_policies USING btree (effective_policy_hash);
CREATE INDEX ix_checker_policies_effective_policy_id ON public.checker_policies USING btree (effective_policy_id);
CREATE INDEX ix_checker_policies_guide_id ON public.checker_policies USING btree (guide_id);
CREATE INDEX ix_checker_policies_pre_submit_checker_bundle_hash ON public.checker_policies USING btree (pre_submit_checker_bundle_hash);
CREATE INDEX ix_checker_policies_pre_submit_checker_policy_id ON public.checker_policies USING btree (pre_submit_checker_policy_id);
CREATE INDEX ix_checker_policies_project_id ON public.checker_policies USING btree (project_id);
CREATE INDEX ix_checker_policies_source_snapshot_id ON public.checker_policies USING btree (source_snapshot_id);
CREATE INDEX ix_checker_policies_supersedes_policy_id ON public.checker_policies USING btree (supersedes_policy_id);
CREATE INDEX ix_checker_results_checker_name ON public.checker_results USING btree (checker_name);
CREATE INDEX ix_checker_results_checker_run_id ON public.checker_results USING btree (checker_run_id);
CREATE INDEX ix_checker_results_submission_id ON public.checker_results USING btree (submission_id);
CREATE INDEX ix_checker_results_task_id ON public.checker_results USING btree (task_id);
CREATE INDEX ix_checker_results_worker_visible ON public.checker_results USING btree (worker_visible);
CREATE INDEX ix_checker_runs_audit_event_id ON public.checker_runs USING btree (audit_event_id);
CREATE INDEX ix_checker_runs_locked_post_submit_policy_hash ON public.checker_runs USING btree (locked_post_submit_checker_policy_hash);
CREATE INDEX ix_checker_runs_routing_recommendation ON public.checker_runs USING btree (routing_recommendation);
CREATE INDEX ix_checker_runs_status ON public.checker_runs USING btree (status);
CREATE INDEX ix_checker_runs_submission_id ON public.checker_runs USING btree (submission_id);
CREATE INDEX ix_checker_runs_supersedes_checker_run_id ON public.checker_runs USING btree (supersedes_checker_run_id);
CREATE INDEX ix_checker_runs_task_id ON public.checker_runs USING btree (task_id);
CREATE INDEX ix_compensation_binding_adapter_actor ON public.project_compensation_adapter_bindings USING btree (adapter_actor_id, status, id);
CREATE INDEX ix_effective_psap_effective_hash ON public.effective_project_submission_artifact_policies USING btree (effective_policy_hash);
CREATE INDEX ix_effective_psap_guide ON public.effective_project_submission_artifact_policies USING btree (guide_id);
CREATE INDEX ix_effective_psap_lifecycle ON public.effective_project_submission_artifact_policies USING btree (lifecycle_status);
CREATE INDEX ix_effective_psap_project ON public.effective_project_submission_artifact_policies USING btree (project_id);
CREATE INDEX ix_effective_psap_source_snapshot ON public.effective_project_submission_artifact_policies USING btree (source_snapshot_id);
CREATE INDEX ix_effective_psap_submission_policy ON public.effective_project_submission_artifact_policies USING btree (submission_artifact_policy_id);
CREATE INDEX ix_evidence_items_submission_id ON public.evidence_items USING btree (submission_id);
CREATE INDEX ix_evidence_items_type ON public.evidence_items USING btree (type);
CREATE INDEX ix_guide_source_artifact_bindings_content_id ON public.guide_source_artifact_bindings USING btree (content_id);
CREATE INDEX ix_guide_source_artifact_bindings_guide_id ON public.guide_source_artifact_bindings USING btree (guide_id);
CREATE INDEX ix_guide_source_artifact_bindings_project_id ON public.guide_source_artifact_bindings USING btree (project_id);
CREATE INDEX ix_guide_source_artifact_bindings_project_setup_run_id ON public.guide_source_artifact_bindings USING btree (project_setup_run_id);
CREATE INDEX ix_guide_source_artifact_bindings_source_item_id ON public.guide_source_artifact_bindings USING btree (source_item_id);
CREATE INDEX ix_guide_source_artifact_bindings_source_snapshot_id ON public.guide_source_artifact_bindings USING btree (source_snapshot_id);
CREATE INDEX ix_guide_source_artifact_bindings_supersedes_binding_id ON public.guide_source_artifact_bindings USING btree (supersedes_binding_id);
CREATE INDEX ix_guide_source_artifact_bindings_verified_replica_id ON public.guide_source_artifact_bindings USING btree (verified_replica_id);
CREATE INDEX ix_guide_source_artifact_incidents_binding_id ON public.guide_source_artifact_incidents USING btree (binding_id);
CREATE INDEX ix_guide_source_artifact_incidents_content_id ON public.guide_source_artifact_incidents USING btree (content_id);
CREATE INDEX ix_guide_source_artifact_incidents_verified_replica_id ON public.guide_source_artifact_incidents USING btree (verified_replica_id);
CREATE INDEX ix_guide_source_artifact_ingests_actor_profile_id ON public.guide_source_artifact_ingests USING btree (actor_profile_id);
CREATE UNIQUE INDEX ix_guide_source_artifact_ingests_source_item_id ON public.guide_source_artifact_ingests USING btree (source_item_id);
CREATE INDEX ix_guide_source_extracted_contents_content_id ON public.guide_source_extracted_contents USING btree (content_id);
CREATE INDEX ix_guide_source_extraction_attempts_binding_id ON public.guide_source_extraction_attempts USING btree (binding_id);
CREATE INDEX ix_guide_source_extraction_attempts_content_id ON public.guide_source_extraction_attempts USING btree (content_id);
CREATE INDEX ix_guide_source_extraction_usages_binding_id ON public.guide_source_extraction_usages USING btree (binding_id);
CREATE INDEX ix_guide_source_extraction_usages_content_id ON public.guide_source_extraction_usages USING btree (content_id);
CREATE INDEX ix_guide_source_extraction_usages_extracted_content_id ON public.guide_source_extraction_usages USING btree (extracted_content_id);
CREATE INDEX ix_guide_source_extraction_usages_project_setup_run_id ON public.guide_source_extraction_usages USING btree (project_setup_run_id);
CREATE INDEX ix_guide_source_extraction_usages_source_item_id ON public.guide_source_extraction_usages USING btree (source_item_id);
CREATE INDEX ix_guide_source_format_classifications_binding_id ON public.guide_source_format_classifications USING btree (binding_id);
CREATE INDEX ix_guide_source_format_classifications_content_id ON public.guide_source_format_classifications USING btree (content_id);
CREATE INDEX ix_guide_source_format_classifications_verified_replica_id ON public.guide_source_format_classifications USING btree (verified_replica_id);
CREATE INDEX ix_guide_source_snapshot_items_source_snapshot_id ON public.guide_source_snapshot_items USING btree (source_snapshot_id);
CREATE INDEX ix_guide_source_snapshots_bundle_hash ON public.guide_source_snapshots USING btree (bundle_hash);
CREATE INDEX ix_guide_source_snapshots_guide_id ON public.guide_source_snapshots USING btree (guide_id);
CREATE INDEX ix_guide_source_snapshots_project_id ON public.guide_source_snapshots USING btree (project_id);
CREATE INDEX ix_guide_sufficiency_reports_guide_id ON public.guide_sufficiency_reports USING btree (guide_id);
CREATE INDEX ix_guide_sufficiency_reports_project_id ON public.guide_sufficiency_reports USING btree (project_id);
CREATE INDEX ix_guide_sufficiency_reports_project_setup_run_id ON public.guide_sufficiency_reports USING btree (project_setup_run_id);
CREATE INDEX ix_guide_sufficiency_reports_source_snapshot_id ON public.guide_sufficiency_reports USING btree (source_snapshot_id);
CREATE INDEX ix_guide_sufficiency_reports_status ON public.guide_sufficiency_reports USING btree (status);
CREATE INDEX ix_legacy_workflow_eligibility_actor_id ON public.legacy_workflow_eligibility USING btree (actor_id);
CREATE INDEX ix_legacy_workflow_eligibility_profile_type ON public.legacy_workflow_eligibility USING btree (profile_type);
CREATE INDEX ix_legacy_workflow_eligibility_status ON public.legacy_workflow_eligibility USING btree (status);
CREATE INDEX ix_outbox_events_aggregate ON public.outbox_events USING btree (aggregate_type, aggregate_id, occurred_at, event_id);
CREATE INDEX ix_outbox_events_eligible ON public.outbox_events USING btree (event_type, delivery_state, next_attempt_at, occurred_at, event_id) WHERE ((delivery_state)::text = ANY ((ARRAY['pending'::character varying, 'retryable'::character varying])::text[]));
CREATE INDEX ix_outbox_events_expired_claims ON public.outbox_events USING btree (claim_expires_at, event_id) WHERE ((delivery_state)::text = 'claimed'::text);
CREATE INDEX ix_outbox_events_project_drain ON public.outbox_events USING btree (project_id, delivery_state, occurred_at, event_id);
CREATE INDEX ix_outbox_events_retention ON public.outbox_events USING btree (finalized_at, event_id) WHERE (((delivery_state)::text = ANY ((ARRAY['acknowledged'::character varying, 'dead_letter'::character varying, 'cancelled'::character varying])::text[])) AND (archived_at IS NULL));
CREATE INDEX ix_payment_policies_project_id ON public.payment_policies USING btree (project_id);
CREATE INDEX ix_policy_mutation_custody_lookup ON public.policy_mutation_idempotency_records USING btree (policy_id, action_id, policy_generation, status);
CREATE INDEX ix_pre_submit_checker_compiled_hash ON public.pre_submit_checker_policies USING btree (compiled_bundle_hash);
CREATE INDEX ix_pre_submit_checker_effective ON public.pre_submit_checker_policies USING btree (effective_policy_id);
CREATE INDEX ix_pre_submit_checker_effective_hash ON public.pre_submit_checker_policies USING btree (effective_policy_hash);
CREATE INDEX ix_pre_submit_checker_guide ON public.pre_submit_checker_policies USING btree (guide_id);
CREATE INDEX ix_pre_submit_checker_lifecycle ON public.pre_submit_checker_policies USING btree (lifecycle_status);
CREATE INDEX ix_pre_submit_checker_project ON public.pre_submit_checker_policies USING btree (project_id);
CREATE INDEX ix_pre_submit_checker_source_snapshot ON public.pre_submit_checker_policies USING btree (source_snapshot_id);
CREATE INDEX ix_pre_submit_evidence_results_evidence_set_id ON public.pre_submit_evidence_results USING btree (evidence_set_id);
CREATE INDEX ix_pre_submit_evidence_sets_actor_profile_id ON public.pre_submit_evidence_sets USING btree (actor_profile_id);
CREATE INDEX ix_pre_submit_evidence_sets_project_id ON public.pre_submit_evidence_sets USING btree (project_id);
CREATE INDEX ix_pre_submit_evidence_sets_task_id ON public.pre_submit_evidence_sets USING btree (task_id);
CREATE INDEX ix_project_guide_compilation_attempts_guide_id ON public.project_guide_compilation_attempts USING btree (guide_id);
CREATE INDEX ix_project_guide_compilation_attempts_project_id ON public.project_guide_compilation_attempts USING btree (project_id);
CREATE INDEX ix_project_guide_compilation_attempts_setup_run_id ON public.project_guide_compilation_attempts USING btree (setup_run_id);
CREATE INDEX ix_project_guide_compilation_attempts_source_snapshot_id ON public.project_guide_compilation_attempts USING btree (source_snapshot_id);
CREATE INDEX ix_project_guide_compilations_guide_id ON public.project_guide_compilations USING btree (guide_id);
CREATE INDEX ix_project_guide_compilations_project_id ON public.project_guide_compilations USING btree (project_id);
CREATE INDEX ix_project_guide_compilations_setup_run_id ON public.project_guide_compilations USING btree (setup_run_id);
CREATE INDEX ix_project_guide_compilations_source_snapshot_id ON public.project_guide_compilations USING btree (source_snapshot_id);
CREATE INDEX ix_project_guides_project_id ON public.project_guides USING btree (project_id);
CREATE INDEX ix_project_guides_status ON public.project_guides USING btree (status);
CREATE INDEX ix_project_role_grants_actor_role_status ON public.project_role_grants USING btree (actor_profile_id, role, status);
CREATE INDEX ix_project_role_grants_project_actor_role_status ON public.project_role_grants USING btree (project_id, actor_profile_id, role, status);
CREATE INDEX ix_project_role_qualification_snapshots_history ON public.project_role_qualification_snapshots USING btree (project_id, actor_profile_id, requested_role, captured_at);
CREATE INDEX ix_project_setup_runs_celery_task_id ON public.project_setup_runs USING btree (celery_task_id);
CREATE INDEX ix_project_setup_runs_continuation_verification_job_id ON public.project_setup_runs USING btree (continuation_verification_job_id);
CREATE INDEX ix_project_setup_runs_error_artifact_incident_id ON public.project_setup_runs USING btree (error_artifact_incident_id);
CREATE INDEX ix_project_setup_runs_guide_id ON public.project_setup_runs USING btree (guide_id);
CREATE INDEX ix_project_setup_runs_output_post_submit_checker_policy_id ON public.project_setup_runs USING btree (output_post_submit_checker_policy_id);
CREATE INDEX ix_project_setup_runs_output_submission_artifact_policy_id ON public.project_setup_runs USING btree (output_submission_artifact_policy_id);
CREATE INDEX ix_project_setup_runs_output_sufficiency_report_id ON public.project_setup_runs USING btree (output_sufficiency_report_id);
CREATE INDEX ix_project_setup_runs_project_id ON public.project_setup_runs USING btree (project_id);
CREATE INDEX ix_project_setup_runs_source_snapshot_id ON public.project_setup_runs USING btree (source_snapshot_id);
CREATE INDEX ix_project_setup_runs_status ON public.project_setup_runs USING btree (status);
CREATE INDEX ix_projects_slug ON public.projects USING btree (slug);
CREATE INDEX ix_projects_status ON public.projects USING btree (status);
CREATE INDEX ix_review_admission_submission ON public.review_admission_idempotency_records USING btree (submission_id, status, created_at, id);
CREATE INDEX ix_review_lease_expiry ON public.review_leases USING btree (status, expires_at, id);
CREATE INDEX ix_review_policies_project_id ON public.review_policies USING btree (project_id);
CREATE INDEX ix_review_queue_preference ON public.review_queue_entries USING btree (preferred_reviewer_id, queue_state, preference_expires_at, id);
CREATE INDEX ix_review_queue_selection ON public.review_queue_entries USING btree (project_id, queue_state, routing_mode, first_queued_at, id);
CREATE INDEX ix_revision_policies_project_id ON public.revision_policies USING btree (project_id);
CREATE INDEX ix_submission_artifact_policies_guide_id ON public.submission_artifact_policies USING btree (guide_id);
CREATE INDEX ix_submission_artifact_policies_lifecycle_status ON public.submission_artifact_policies USING btree (lifecycle_status);
CREATE INDEX ix_submission_artifact_policies_policy_hash ON public.submission_artifact_policies USING btree (policy_hash);
CREATE INDEX ix_submission_artifact_policies_project_id ON public.submission_artifact_policies USING btree (project_id);
CREATE INDEX ix_submission_artifact_policies_source_snapshot_id ON public.submission_artifact_policies USING btree (source_snapshot_id);
CREATE INDEX ix_submission_bundle_admissions_actor_profile_id ON public.submission_bundle_admissions USING btree (actor_profile_id);
CREATE INDEX ix_submission_bundle_admissions_artifact_content_id ON public.submission_bundle_admissions USING btree (artifact_content_id);
CREATE INDEX ix_submission_bundle_admissions_pre_submit_evidence_set_id ON public.submission_bundle_admissions USING btree (pre_submit_evidence_set_id);
CREATE INDEX ix_submission_bundle_admissions_project_id ON public.submission_bundle_admissions USING btree (project_id);
CREATE INDEX ix_submission_bundle_admissions_status ON public.submission_bundle_admissions USING btree (status);
CREATE INDEX ix_submission_bundle_admissions_task_id ON public.submission_bundle_admissions USING btree (task_id);
CREATE INDEX ix_submission_bundle_durable_intents_pre_submit_evidence_set_id ON public.submission_bundle_durable_intents USING btree (pre_submit_evidence_set_id);
CREATE INDEX ix_submission_bundle_durable_intents_put_attempt_id ON public.submission_bundle_durable_intents USING btree (put_attempt_id);
CREATE INDEX ix_submissions_contributor_id ON public.submissions USING btree (contributor_id);
CREATE INDEX ix_submissions_locked_effective_policy_hash ON public.submissions USING btree (locked_effective_project_submission_artifact_policy_hash);
CREATE INDEX ix_submissions_locked_post_submit_policy_hash ON public.submissions USING btree (locked_post_submit_checker_policy_hash);
CREATE INDEX ix_submissions_locked_pre_submit_checker_hash ON public.submissions USING btree (locked_pre_submit_checker_bundle_hash);
CREATE INDEX ix_submissions_locked_source_snapshot ON public.submissions USING btree (locked_guide_source_snapshot_id);
CREATE INDEX ix_submissions_status ON public.submissions USING btree (status);
CREATE INDEX ix_submissions_supersedes_submission_id ON public.submissions USING btree (supersedes_submission_id);
CREATE INDEX ix_submissions_task_id ON public.submissions USING btree (task_id);
CREATE INDEX ix_sufficiency_report_source_usage_report_id ON public.guide_sufficiency_report_source_usages USING btree (report_id);
CREATE INDEX ix_task_assignments_contributor_id ON public.task_assignments USING btree (contributor_id);
CREATE INDEX ix_task_assignments_status ON public.task_assignments USING btree (status);
CREATE INDEX ix_task_assignments_task_id ON public.task_assignments USING btree (task_id);
CREATE INDEX ix_workstream_tasks_assigned_to ON public.workstream_tasks USING btree (assigned_to);
CREATE INDEX ix_workstream_tasks_locked_effective_policy_hash ON public.workstream_tasks USING btree (locked_effective_project_submission_artifact_policy_hash);
CREATE INDEX ix_workstream_tasks_locked_post_submit_policy_hash ON public.workstream_tasks USING btree (locked_post_submit_checker_policy_hash);
CREATE INDEX ix_workstream_tasks_locked_pre_submit_checker_hash ON public.workstream_tasks USING btree (locked_pre_submit_checker_bundle_hash);
CREATE INDEX ix_workstream_tasks_locked_source_snapshot ON public.workstream_tasks USING btree (locked_guide_source_snapshot_id);
CREATE INDEX ix_workstream_tasks_project_id ON public.workstream_tasks USING btree (project_id);
CREATE INDEX ix_workstream_tasks_status ON public.workstream_tasks USING btree (status);
CREATE UNIQUE INDEX uq_admin_role_grants_active_project ON public.admin_role_grants USING btree (target_actor_profile_id, role, scope_project_id) WHERE (((status)::text = 'active'::text) AND ((scope_type)::text = 'project'::text));
CREATE UNIQUE INDEX uq_admin_role_grants_active_system ON public.admin_role_grants USING btree (target_actor_profile_id, role) WHERE (((status)::text = 'active'::text) AND ((scope_type)::text = 'system'::text));
CREATE UNIQUE INDEX uq_artifact_verification_initial_origin ON public.artifact_verification_jobs USING btree (originating_put_attempt_id) WHERE (parent_verification_job_id IS NULL);
CREATE UNIQUE INDEX uq_checker_policies_current_project_version ON public.checker_policies USING btree (project_id, guide_version) WHERE ((lifecycle_status)::text = ANY ((ARRAY['compiled'::character varying, 'approved'::character varying])::text[]));
CREATE UNIQUE INDEX uq_checker_runs_current_per_submission ON public.checker_runs USING btree (submission_id) WHERE (is_current_for_submission = true);
CREATE UNIQUE INDEX uq_compensation_binding_active_project_instrument ON public.project_compensation_adapter_bindings USING btree (project_id, instrument_type) WHERE ((status)::text = 'active'::text);
CREATE UNIQUE INDEX uq_contribution_policy_active_project ON public.contribution_policies USING btree (project_id) WHERE ((status)::text = 'active'::text);
CREATE UNIQUE INDEX uq_guide_sufficiency_reports_diagnostic_snapshot ON public.guide_sufficiency_reports USING btree (source_snapshot_id) WHERE (project_setup_run_id IS NULL);
CREATE UNIQUE INDEX uq_guide_sufficiency_reports_verified_snapshot ON public.guide_sufficiency_reports USING btree (source_snapshot_id) WHERE (project_setup_run_id IS NOT NULL);
CREATE UNIQUE INDEX uq_project_guide_compilation_root ON public.project_guide_compilations USING btree (project_id, guide_id) WHERE (supersedes_compilation_id IS NULL);
CREATE UNIQUE INDEX uq_project_guides_one_active_per_project ON public.project_guides USING btree (project_id) WHERE ((status)::text = 'active'::text);
CREATE UNIQUE INDEX uq_project_role_grants_active_exact_role ON public.project_role_grants USING btree (project_id, actor_profile_id, role) WHERE ((status)::text = 'active'::text);
CREATE UNIQUE INDEX uq_review_lease_active_queue ON public.review_leases USING btree (review_queue_entry_id) WHERE ((status)::text = 'active'::text);
CREATE UNIQUE INDEX uq_review_lease_active_reviewer ON public.review_leases USING btree (reviewer_id) WHERE ((status)::text = 'active'::text);
CREATE UNIQUE INDEX uq_submission_bundle_admission_consumer ON public.submission_bundle_admissions USING btree (consumed_by_submission_id) WHERE (consumed_by_submission_id IS NOT NULL);
CREATE UNIQUE INDEX uq_submission_policy_committed_policy_action ON public.submission_policy_mutation_idempotency_records USING btree (committed_policy_id, action_id) WHERE ((status)::text = 'committed'::text);
CREATE UNIQUE INDEX uq_submission_policy_human_replay_namespace ON public.submission_policy_mutation_idempotency_records USING btree (actor_profile_id, idempotency_key) WHERE (service_identity IS NULL);
CREATE UNIQUE INDEX uq_submission_policy_service_replay_namespace ON public.submission_policy_mutation_idempotency_records USING btree (actor_profile_id, setup_run_id, setup_generation, setup_task_id, correlation_id, action_id) WHERE (service_identity IS NOT NULL);
CREATE UNIQUE INDEX uq_task_assignments_one_active_per_task ON public.task_assignments USING btree (task_id) WHERE ((status)::text = 'active'::text);
CREATE TRIGGER actor_identity_link_history_guard BEFORE DELETE OR UPDATE ON public.actor_identity_links FOR EACH ROW EXECUTE FUNCTION public.guard_actor_identity_link_history();
CREATE CONSTRAINT TRIGGER actor_identity_link_profile_guard AFTER INSERT OR UPDATE ON public.actor_identity_links DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_canonical_actor_link();
CREATE TRIGGER actor_profile_history_guard BEFORE DELETE OR UPDATE ON public.actor_profiles FOR EACH ROW EXECUTE FUNCTION public.guard_actor_profile_history();
CREATE CONSTRAINT TRIGGER actor_profile_link_guard AFTER INSERT OR UPDATE ON public.actor_profiles DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_canonical_actor_link();
CREATE CONSTRAINT TRIGGER admin_role_grants_bootstrap_invariant AFTER INSERT OR DELETE OR UPDATE ON public.admin_role_grants DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_bootstrap_authority_state();
CREATE TRIGGER admin_role_grants_guard BEFORE INSERT OR DELETE OR UPDATE ON public.admin_role_grants FOR EACH ROW EXECUTE FUNCTION public.guard_admin_role_grant();
CREATE TRIGGER admin_role_grants_reject_truncate BEFORE TRUNCATE ON public.admin_role_grants FOR EACH STATEMENT EXECUTE FUNCTION public.reject_admin_role_grant_truncate();
CREATE TRIGGER artifact_receipt_producer_reference BEFORE INSERT OR UPDATE OF put_attempt_id, guide_source_item_id, checker_run_id, logical_role ON public.artifact_operation_receipts FOR EACH ROW EXECUTE FUNCTION public.guard_artifact_receipt_producer_reference();
CREATE TRIGGER artifact_recovery_attempt_custody BEFORE INSERT OR DELETE OR UPDATE ON public.artifact_recovery_attempts FOR EACH ROW EXECUTE FUNCTION public.validate_artifact_recovery_attempt();
CREATE TRIGGER artifact_verification_lineage_custody BEFORE UPDATE ON public.artifact_verification_jobs FOR EACH ROW EXECUTE FUNCTION public.validate_artifact_verification_lineage();
CREATE TRIGGER audit_events_reject_truncate BEFORE TRUNCATE ON public.audit_events FOR EACH STATEMENT EXECUTE FUNCTION public.reject_audit_event_mutation();
CREATE TRIGGER audit_events_reject_update_delete BEFORE DELETE OR UPDATE ON public.audit_events FOR EACH ROW EXECUTE FUNCTION public.reject_audit_event_mutation();
CREATE TRIGGER audit_events_set_authority_time BEFORE INSERT ON public.audit_events FOR EACH ROW EXECUTE FUNCTION public.set_authority_audit_database_time();
CREATE TRIGGER audit_events_validate_idempotency BEFORE INSERT ON public.audit_events FOR EACH ROW EXECUTE FUNCTION public.validate_linked_authority_event();
CREATE CONSTRAINT TRIGGER authority_control_bootstrap_invariant AFTER INSERT OR DELETE OR UPDATE ON public.authority_control DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_bootstrap_authority_state();
CREATE TRIGGER authority_control_guard BEFORE INSERT OR DELETE OR UPDATE ON public.authority_control FOR EACH ROW EXECUTE FUNCTION public.guard_authority_control();
CREATE TRIGGER authority_control_reject_truncate BEFORE TRUNCATE ON public.authority_control FOR EACH STATEMENT EXECUTE FUNCTION public.reject_authority_control_truncate();
CREATE TRIGGER authority_idempotency_guard BEFORE INSERT OR DELETE OR UPDATE ON public.authority_idempotency_records FOR EACH ROW EXECUTE FUNCTION public.guard_authority_idempotency_record();
CREATE CONSTRAINT TRIGGER authority_idempotency_pending_guard AFTER INSERT OR UPDATE ON public.authority_idempotency_records DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.reject_pending_authority_idempotency();
CREATE TRIGGER authority_idempotency_reject_truncate BEFORE TRUNCATE ON public.authority_idempotency_records FOR EACH STATEMENT EXECUTE FUNCTION public.reject_authority_idempotency_truncate();
CREATE TRIGGER contribution_award_definitions_content_guard BEFORE INSERT OR DELETE OR UPDATE ON public.contribution_award_definitions FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_policy_children();
CREATE CONSTRAINT TRIGGER contribution_award_definitions_graph_guard AFTER INSERT OR DELETE OR UPDATE ON public.contribution_award_definitions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_contribution_policy_graph();
CREATE TRIGGER contribution_award_definitions_reject_truncate BEFORE TRUNCATE ON public.contribution_award_definitions FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_policy_truncate();
CREATE CONSTRAINT TRIGGER contribution_policies_graph_guard AFTER INSERT OR DELETE OR UPDATE ON public.contribution_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_contribution_policy_graph();
CREATE TRIGGER contribution_policies_reject_truncate BEFORE TRUNCATE ON public.contribution_policies FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_policy_truncate();
CREATE TRIGGER contribution_policy_versions_content_guard BEFORE DELETE OR UPDATE ON public.contribution_policy_versions FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_policy_version_content();
CREATE CONSTRAINT TRIGGER contribution_policy_versions_graph_guard AFTER INSERT OR DELETE OR UPDATE ON public.contribution_policy_versions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_contribution_policy_graph();
CREATE TRIGGER contribution_policy_versions_reject_truncate BEFORE TRUNCATE ON public.contribution_policy_versions FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_policy_truncate();
CREATE TRIGGER contribution_rules_content_guard BEFORE INSERT OR DELETE OR UPDATE ON public.contribution_rules FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_policy_children();
CREATE CONSTRAINT TRIGGER contribution_rules_graph_guard AFTER INSERT OR DELETE OR UPDATE ON public.contribution_rules DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_contribution_policy_graph();
CREATE TRIGGER contribution_rules_reject_truncate BEFORE TRUNCATE ON public.contribution_rules FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_policy_truncate();
CREATE CONSTRAINT TRIGGER effective_submission_policy_custody AFTER INSERT OR UPDATE ON public.effective_project_submission_artifact_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_submission_policy_authority_custody();
CREATE TRIGGER effective_submission_policy_provenance_immutable BEFORE UPDATE ON public.effective_project_submission_artifact_policies FOR EACH ROW EXECUTE FUNCTION public.protect_submission_policy_output_provenance();
CREATE TRIGGER guide_lineage_lifecycle_guard BEFORE UPDATE ON public.project_guides FOR EACH ROW EXECUTE FUNCTION public.guard_guide_lineage_and_lifecycle();
CREATE TRIGGER guide_mutation_idempotency_guard BEFORE INSERT OR DELETE OR UPDATE ON public.guide_mutation_idempotency_records FOR EACH ROW EXECUTE FUNCTION public.guard_guide_mutation_idempotency();
CREATE TRIGGER guide_mutation_idempotency_reject_truncate BEFORE TRUNCATE ON public.guide_mutation_idempotency_records FOR EACH STATEMENT EXECUTE FUNCTION public.reject_guide_mutation_idempotency_truncate();
CREATE CONSTRAINT TRIGGER guide_mutation_product_custody AFTER INSERT OR UPDATE ON public.project_guides DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_guide_mutation_custody();
CREATE CONSTRAINT TRIGGER guide_mutation_reservation_custody AFTER INSERT OR UPDATE ON public.guide_mutation_idempotency_records DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_guide_mutation_custody();
CREATE CONSTRAINT TRIGGER guide_source_snapshot_items_custody AFTER INSERT ON public.guide_source_snapshot_items DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_guide_source_snapshot_items();
CREATE TRIGGER guide_source_snapshot_items_immutable BEFORE DELETE OR UPDATE OR TRUNCATE ON public.guide_source_snapshot_items FOR EACH STATEMENT EXECUTE FUNCTION public.reject_guide_source_snapshot_item_mutation();
CREATE TRIGGER iso_4217_currency_codes_immutable BEFORE INSERT OR DELETE OR UPDATE ON public.iso_4217_currency_codes FOR EACH ROW EXECUTE FUNCTION public.guard_iso_4217_currency_codes();
CREATE TRIGGER iso_4217_currency_codes_reject_truncate BEFORE TRUNCATE ON public.iso_4217_currency_codes FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_policy_truncate();
CREATE TRIGGER outbox_events_custody BEFORE INSERT OR DELETE OR UPDATE ON public.outbox_events FOR EACH ROW EXECUTE FUNCTION public.guard_outbox_event();
CREATE TRIGGER outbox_events_reject_truncate BEFORE TRUNCATE ON public.outbox_events FOR EACH STATEMENT EXECUTE FUNCTION public.guard_outbox_event();
CREATE CONSTRAINT TRIGGER policy_mutation_replay_custody AFTER INSERT OR UPDATE ON public.policy_mutation_idempotency_records DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_policy_mutation_custody();
CREATE TRIGGER policy_mutation_replay_immutable BEFORE INSERT OR DELETE OR UPDATE ON public.policy_mutation_idempotency_records FOR EACH ROW EXECUTE FUNCTION public.guard_policy_mutation_replay();
CREATE TRIGGER policy_mutation_replay_reject_truncate BEFORE TRUNCATE ON public.policy_mutation_idempotency_records FOR EACH STATEMENT EXECUTE FUNCTION public.reject_policy_mutation_replay_truncate();
CREATE TRIGGER pre_submit_evidence_results_immutable BEFORE DELETE OR UPDATE ON public.pre_submit_evidence_results FOR EACH ROW EXECUTE FUNCTION public.guard_pre_submit_evidence_results_immutable();
CREATE TRIGGER pre_submit_evidence_results_membership BEFORE INSERT ON public.pre_submit_evidence_results FOR EACH ROW EXECUTE FUNCTION public.guard_pre_submit_evidence_result_membership();
CREATE TRIGGER pre_submit_evidence_results_no_truncate BEFORE TRUNCATE ON public.pre_submit_evidence_results FOR EACH STATEMENT EXECUTE FUNCTION public.guard_pre_submit_evidence_results_immutable();
CREATE TRIGGER pre_submit_evidence_sets_creation BEFORE INSERT ON public.pre_submit_evidence_sets FOR EACH ROW EXECUTE FUNCTION public.guard_pre_submit_evidence_set_creation();
CREATE TRIGGER pre_submit_evidence_sets_immutable BEFORE DELETE OR UPDATE ON public.pre_submit_evidence_sets FOR EACH ROW EXECUTE FUNCTION public.guard_pre_submit_evidence_sets_immutable();
CREATE TRIGGER pre_submit_evidence_sets_no_truncate BEFORE TRUNCATE ON public.pre_submit_evidence_sets FOR EACH STATEMENT EXECUTE FUNCTION public.guard_pre_submit_evidence_sets_immutable();
CREATE CONSTRAINT TRIGGER pre_submit_policy_custody AFTER INSERT OR UPDATE ON public.pre_submit_checker_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_submission_policy_authority_custody();
CREATE TRIGGER pre_submit_policy_provenance_immutable BEFORE UPDATE ON public.pre_submit_checker_policies FOR EACH ROW EXECUTE FUNCTION public.protect_submission_policy_output_provenance();
CREATE TRIGGER project_compensation_binding_update_guard BEFORE UPDATE ON public.project_compensation_adapter_bindings FOR EACH ROW EXECUTE FUNCTION public.enforce_compensation_binding_lifecycle();
CREATE TRIGGER project_compensation_units_lifecycle_guard BEFORE INSERT OR DELETE OR UPDATE ON public.project_compensation_units FOR EACH ROW EXECUTE FUNCTION public.guard_project_compensation_units();
CREATE TRIGGER project_compensation_units_reject_truncate BEFORE TRUNCATE ON public.project_compensation_units FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_policy_truncate();
CREATE TRIGGER project_create_idempotency_guard BEFORE INSERT OR DELETE OR UPDATE ON public.project_create_idempotency_records FOR EACH ROW EXECUTE FUNCTION public.guard_project_create_idempotency();
CREATE TRIGGER project_create_idempotency_reject_truncate BEFORE TRUNCATE ON public.project_create_idempotency_records FOR EACH STATEMENT EXECUTE FUNCTION public.reject_project_create_idempotency_truncate();
CREATE CONSTRAINT TRIGGER project_create_reservation_custody AFTER INSERT OR UPDATE ON public.project_create_idempotency_records DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_project_create_custody();
CREATE CONSTRAINT TRIGGER project_creation_custody AFTER INSERT OR UPDATE OF created_by_actor_profile_id, created_via_identity_link_id, created_by_admin_role_grant_id, creation_scope_type, creation_action_id, authorization_decision_event_id ON public.projects DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_project_create_custody();
CREATE TRIGGER project_guides_policy_selection_immutable BEFORE UPDATE ON public.project_guides FOR EACH ROW EXECUTE FUNCTION public.guard_project_guide_policy_selection();
CREATE TRIGGER review_admission_idempotency_records_reject_truncate BEFORE TRUNCATE ON public.review_admission_idempotency_records FOR EACH STATEMENT EXECUTE FUNCTION public.reject_review_queue_foundation_truncate();
CREATE TRIGGER review_admission_records_guard BEFORE INSERT OR DELETE OR UPDATE ON public.review_admission_idempotency_records FOR EACH ROW EXECUTE FUNCTION public.guard_review_admission_record();
CREATE CONSTRAINT TRIGGER review_leases_active_lease_guard AFTER INSERT OR UPDATE ON public.review_leases DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_review_active_lease();
CREATE TRIGGER review_leases_guard BEFORE INSERT OR DELETE OR UPDATE ON public.review_leases FOR EACH ROW EXECUTE FUNCTION public.guard_review_lease();
CREATE TRIGGER review_leases_reject_truncate BEFORE TRUNCATE ON public.review_leases FOR EACH STATEMENT EXECUTE FUNCTION public.reject_review_lease_truncate();
CREATE TRIGGER review_policies_immutable BEFORE DELETE OR UPDATE ON public.review_policies FOR EACH ROW EXECUTE FUNCTION public.guard_review_policies_immutable();
CREATE TRIGGER review_policies_reject_truncate BEFORE TRUNCATE ON public.review_policies FOR EACH STATEMENT EXECUTE FUNCTION public.guard_review_policies_immutable();
CREATE CONSTRAINT TRIGGER review_policy_mutation_custody AFTER INSERT OR UPDATE ON public.review_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_policy_mutation_custody();
CREATE CONSTRAINT TRIGGER review_queue_entries_active_lease_guard AFTER INSERT OR UPDATE ON public.review_queue_entries DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_review_active_lease();
CREATE TRIGGER review_queue_entries_guard BEFORE INSERT OR DELETE OR UPDATE ON public.review_queue_entries FOR EACH ROW EXECUTE FUNCTION public.guard_review_queue_entry();
CREATE TRIGGER review_queue_entries_reject_truncate BEFORE TRUNCATE ON public.review_queue_entries FOR EACH STATEMENT EXECUTE FUNCTION public.reject_review_queue_foundation_truncate();
CREATE TRIGGER revision_policies_immutable BEFORE DELETE OR UPDATE ON public.revision_policies FOR EACH ROW EXECUTE FUNCTION public.guard_revision_policies_immutable();
CREATE TRIGGER revision_policies_reject_truncate BEFORE TRUNCATE ON public.revision_policies FOR EACH STATEMENT EXECUTE FUNCTION public.guard_revision_policies_immutable();
CREATE CONSTRAINT TRIGGER revision_policy_mutation_custody AFTER INSERT OR UPDATE ON public.revision_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_policy_mutation_custody();
CREATE TRIGGER service_identity_migration_evidence_row_guard BEFORE DELETE OR UPDATE ON public.actor_profile_migration_state FOR EACH ROW EXECUTE FUNCTION public.guard_service_identity_migration_evidence();
CREATE TRIGGER service_identity_migration_evidence_truncate_guard BEFORE TRUNCATE ON public.actor_profile_migration_state FOR EACH STATEMENT EXECUTE FUNCTION public.guard_service_identity_migration_evidence();
CREATE CONSTRAINT TRIGGER source_setup_run_custody AFTER INSERT OR UPDATE ON public.project_setup_runs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_guide_mutation_custody();
CREATE CONSTRAINT TRIGGER source_snapshot_product_custody AFTER INSERT OR UPDATE ON public.guide_source_snapshots DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_guide_mutation_custody();
CREATE TRIGGER submission_bundle_admission_delete BEFORE DELETE OR TRUNCATE ON public.submission_bundle_admissions FOR EACH STATEMENT EXECUTE FUNCTION public.guard_submission_bundle_admission_delete();
CREATE TRIGGER submission_bundle_admission_lineage BEFORE UPDATE ON public.submission_bundle_admissions FOR EACH ROW EXECUTE FUNCTION public.guard_submission_bundle_admission_lineage();
CREATE TRIGGER submission_bundle_admission_verified_lineage BEFORE INSERT ON public.submission_bundle_admissions FOR EACH ROW EXECUTE FUNCTION public.guard_submission_bundle_admission_verified_lineage();
CREATE TRIGGER submission_bundle_durable_intent_put_attempt BEFORE INSERT ON public.submission_bundle_durable_intents FOR EACH ROW EXECUTE FUNCTION public.guard_submission_bundle_durable_intent_put_attempt();
CREATE TRIGGER submission_bundle_durable_intents_immutable BEFORE DELETE OR UPDATE ON public.submission_bundle_durable_intents FOR EACH ROW EXECUTE FUNCTION public.guard_submission_bundle_durable_intents_immutable();
CREATE TRIGGER submission_bundle_durable_intents_no_truncate BEFORE TRUNCATE ON public.submission_bundle_durable_intents FOR EACH STATEMENT EXECUTE FUNCTION public.guard_submission_bundle_durable_intents_immutable();
CREATE TRIGGER submission_policy_approval_provenance_immutable BEFORE UPDATE ON public.submission_artifact_policies FOR EACH ROW EXECUTE FUNCTION public.protect_submission_policy_approval_provenance();
CREATE CONSTRAINT TRIGGER submission_policy_creation_custody AFTER INSERT OR UPDATE ON public.submission_artifact_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_submission_policy_creation_custody();
CREATE TRIGGER submission_policy_creation_provenance_immutable BEFORE UPDATE ON public.submission_artifact_policies FOR EACH ROW EXECUTE FUNCTION public.protect_submission_policy_creation_provenance();
CREATE CONSTRAINT TRIGGER submission_policy_product_custody AFTER INSERT OR UPDATE ON public.submission_artifact_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_submission_policy_authority_custody();
CREATE CONSTRAINT TRIGGER submission_policy_replay_custody AFTER INSERT OR UPDATE ON public.submission_policy_mutation_idempotency_records DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (((new.status)::text = 'committed'::text)) EXECUTE FUNCTION public.validate_submission_policy_authority_custody();
CREATE TRIGGER submissions_contributor_human BEFORE INSERT OR UPDATE OF contributor_id ON public.submissions FOR EACH ROW EXECUTE FUNCTION public.require_human_actor_profile_reference('contributor_id');
CREATE TRIGGER task_assignments_contributor_human BEFORE INSERT OR UPDATE OF contributor_id ON public.task_assignments FOR EACH ROW EXECUTE FUNCTION public.require_human_actor_profile_reference('contributor_id');
CREATE CONSTRAINT TRIGGER trg_artifact_binding_history AFTER INSERT ON public.artifact_bindings DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION public.validate_artifact_binding_history();
CREATE TRIGGER trg_artifact_bindings_immutable BEFORE DELETE OR UPDATE ON public.artifact_bindings FOR EACH ROW EXECUTE FUNCTION public.reject_artifact_fact_mutation();
CREATE TRIGGER trg_artifact_contents_immutable BEFORE DELETE OR UPDATE ON public.artifact_contents FOR EACH ROW EXECUTE FUNCTION public.reject_artifact_fact_mutation();
CREATE TRIGGER trg_artifact_operation_receipts_immutable BEFORE DELETE OR UPDATE ON public.artifact_operation_receipts FOR EACH ROW EXECUTE FUNCTION public.reject_artifact_fact_mutation();
CREATE TRIGGER trg_artifact_put_observation_receipts_immutable BEFORE DELETE OR UPDATE ON public.artifact_put_observation_receipts FOR EACH ROW EXECUTE FUNCTION public.reject_artifact_fact_mutation();
CREATE TRIGGER trg_artifact_storage_namespaces_immutable BEFORE DELETE OR UPDATE ON public.artifact_storage_namespaces FOR EACH ROW EXECUTE FUNCTION public.reject_artifact_fact_mutation();
CREATE TRIGGER trg_artifact_verification_receipts_immutable BEFORE DELETE OR UPDATE ON public.artifact_verification_receipts FOR EACH ROW EXECUTE FUNCTION public.reject_artifact_fact_mutation();
CREATE TRIGGER trg_compilation_attempt_delete BEFORE DELETE OR TRUNCATE ON public.project_guide_compilation_attempts FOR EACH STATEMENT EXECUTE FUNCTION public.reject_project_guide_compilation_mutation();
CREATE TRIGGER trg_compilation_attempt_update BEFORE UPDATE ON public.project_guide_compilation_attempts FOR EACH ROW EXECUTE FUNCTION public.guard_project_guide_compilation_attempt_update();
CREATE TRIGGER trg_compilation_insert BEFORE INSERT ON public.project_guide_compilations FOR EACH ROW EXECUTE FUNCTION public.guard_project_guide_compilation_insert();
CREATE TRIGGER trg_compilation_mutation BEFORE DELETE OR UPDATE OR TRUNCATE ON public.project_guide_compilations FOR EACH STATEMENT EXECUTE FUNCTION public.reject_project_guide_compilation_mutation();
CREATE TRIGGER trg_project_role_grants_history BEFORE INSERT OR DELETE OR UPDATE ON public.project_role_grants FOR EACH ROW EXECUTE FUNCTION public.guard_project_role_grant_history();
CREATE TRIGGER trg_project_role_grants_reject_truncate BEFORE TRUNCATE ON public.project_role_grants FOR EACH STATEMENT EXECUTE FUNCTION public.reject_project_role_history_truncate();
CREATE TRIGGER trg_project_role_qualification_snapshots_immutable BEFORE INSERT OR DELETE OR UPDATE ON public.project_role_qualification_snapshots FOR EACH ROW EXECUTE FUNCTION public.guard_project_role_snapshot_history();
CREATE TRIGGER trg_project_role_snapshots_reject_truncate BEFORE TRUNCATE ON public.project_role_qualification_snapshots FOR EACH STATEMENT EXECUTE FUNCTION public.reject_project_role_history_truncate();
CREATE TRIGGER trg_submission_policy_replay_immutable BEFORE DELETE OR UPDATE ON public.submission_policy_mutation_idempotency_records FOR EACH ROW EXECUTE FUNCTION public.reject_submission_policy_replay_mutation();
CREATE TRIGGER trg_submission_policy_replay_no_truncate BEFORE TRUNCATE ON public.submission_policy_mutation_idempotency_records FOR EACH STATEMENT EXECUTE FUNCTION public.reject_submission_policy_replay_truncate();
CREATE TRIGGER trg_sufficiency_replay_immutable BEFORE DELETE OR UPDATE ON public.guide_sufficiency_mutation_idempotency_records FOR EACH ROW EXECUTE FUNCTION public.reject_sufficiency_replay_mutation();
CREATE TRIGGER trg_sufficiency_replay_no_truncate BEFORE TRUNCATE ON public.guide_sufficiency_mutation_idempotency_records FOR EACH STATEMENT EXECUTE FUNCTION public.reject_sufficiency_replay_truncate();
ALTER TABLE ONLY public.actor_identity_links
    ADD CONSTRAINT fk_actor_identity_links_actor_profile_id_actor_profiles FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.admin_role_grants
    ADD CONSTRAINT fk_admin_role_grants_granted_by_actor_profile_id_actor_profiles FOREIGN KEY (granted_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.admin_role_grants
    ADD CONSTRAINT fk_admin_role_grants_granted_by_admin_role_grant_id_adm_81e0 FOREIGN KEY (granted_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.admin_role_grants
    ADD CONSTRAINT fk_admin_role_grants_revoked_by_actor_profile_id_actor_profiles FOREIGN KEY (revoked_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.admin_role_grants
    ADD CONSTRAINT fk_admin_role_grants_revoked_by_admin_role_grant_id_adm_78b5 FOREIGN KEY (revoked_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.admin_role_grants
    ADD CONSTRAINT fk_admin_role_grants_scope_project_id_projects FOREIGN KEY (scope_project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.admin_role_grants
    ADD CONSTRAINT fk_admin_role_grants_target_actor_profile_id_actor_profiles FOREIGN KEY (target_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.artifact_admission_charges
    ADD CONSTRAINT fk_artifact_admission_charges_scope FOREIGN KEY (scope_type, scope_id) REFERENCES public.artifact_admission_scopes(scope_type, scope_id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_bindings
    ADD CONSTRAINT fk_artifact_bindings_content_id_artifact_contents FOREIGN KEY (content_id) REFERENCES public.artifact_contents(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_bindings
    ADD CONSTRAINT fk_artifact_bindings_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_bindings
    ADD CONSTRAINT fk_artifact_bindings_supersedes_binding_id_artifact_bindings FOREIGN KEY (supersedes_binding_id) REFERENCES public.artifact_bindings(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_operation_receipts
    ADD CONSTRAINT fk_artifact_operation_receipts_replica_id_artifact_replicas FOREIGN KEY (replica_id) REFERENCES public.artifact_replicas(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempt_charges
    ADD CONSTRAINT fk_artifact_put_attempt_charges_attempt_id_artifact_put_b25d FOREIGN KEY (attempt_id) REFERENCES public.artifact_put_attempts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempt_charges
    ADD CONSTRAINT fk_artifact_put_attempt_charges_charge_id_artifact_admi_85a9 FOREIGN KEY (charge_id) REFERENCES public.artifact_admission_charges(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT fk_artifact_put_attempts_checker_run_id_checker_runs FOREIGN KEY (checker_run_id) REFERENCES public.checker_runs(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT fk_artifact_put_attempts_guide_source_item_id_guide_sou_e48c FOREIGN KEY (guide_source_item_id) REFERENCES public.guide_source_snapshot_items(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT fk_artifact_put_attempts_namespace_fingerprint FOREIGN KEY (storage_namespace_id, namespace_fingerprint) REFERENCES public.artifact_storage_namespaces(id, namespace_fingerprint) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT fk_artifact_put_attempts_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT fk_artifact_put_attempts_receipt_id_artifact_operation_receipts FOREIGN KEY (receipt_id) REFERENCES public.artifact_operation_receipts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT fk_artifact_put_attempts_replica_id_artifact_replicas FOREIGN KEY (replica_id) REFERENCES public.artifact_replicas(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT fk_artifact_put_attempts_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_observation_receipts
    ADD CONSTRAINT fk_artifact_put_observation_receipts_put_attempt_id_art_237d FOREIGN KEY (put_attempt_id) REFERENCES public.artifact_put_attempts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_operation_receipts
    ADD CONSTRAINT fk_artifact_receipt_checker_run FOREIGN KEY (checker_run_id) REFERENCES public.checker_runs(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_operation_receipts
    ADD CONSTRAINT fk_artifact_receipt_guide_item FOREIGN KEY (guide_source_item_id) REFERENCES public.guide_source_snapshot_items(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_operation_receipts
    ADD CONSTRAINT fk_artifact_receipt_put_attempt FOREIGN KEY (put_attempt_id) REFERENCES public.artifact_put_attempts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_initiation_audit_event_id_2af7 FOREIGN KEY (initiation_audit_event_id) REFERENCES public.audit_events(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_parent_recovery_attempt_i_130d FOREIGN KEY (parent_recovery_attempt_id) REFERENCES public.artifact_recovery_attempts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_requester_actor_profile_i_77f5 FOREIGN KEY (requester_actor_profile_id) REFERENCES public.actor_profiles(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_requester_identity_link_i_3619 FOREIGN KEY (requester_identity_link_id) REFERENCES public.actor_identity_links(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_retry_verification_job_id_b330 FOREIGN KEY (retry_verification_job_id) REFERENCES public.artifact_verification_jobs(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_source_verification_job_i_5eac FOREIGN KEY (source_verification_job_id) REFERENCES public.artifact_verification_jobs(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_submission_id_submissions FOREIGN KEY (submission_id) REFERENCES public.submissions(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_terminal_audit_event_id_a_47ab FOREIGN KEY (terminal_audit_event_id) REFERENCES public.audit_events(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_replicas
    ADD CONSTRAINT fk_artifact_replicas_content_id_artifact_contents FOREIGN KEY (content_id) REFERENCES public.artifact_contents(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_replicas
    ADD CONSTRAINT fk_artifact_replicas_storage_namespace_id_artifact_stor_d6cc FOREIGN KEY (storage_namespace_id) REFERENCES public.artifact_storage_namespaces(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_verification_jobs
    ADD CONSTRAINT fk_artifact_verification_jobs_originating_put_attempt_i_3260 FOREIGN KEY (originating_put_attempt_id) REFERENCES public.artifact_put_attempts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_verification_jobs
    ADD CONSTRAINT fk_artifact_verification_jobs_replica_id_artifact_replicas FOREIGN KEY (replica_id) REFERENCES public.artifact_replicas(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_verification_jobs
    ADD CONSTRAINT fk_artifact_verification_parent FOREIGN KEY (parent_verification_job_id) REFERENCES public.artifact_verification_jobs(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_verification_receipts
    ADD CONSTRAINT fk_artifact_verification_receipts_verification_job_id_a_dabf FOREIGN KEY (verification_job_id) REFERENCES public.artifact_verification_jobs(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT fk_audit_events_authority_idempotency FOREIGN KEY (idempotency_reference, actor_ref_kind, actor_id) REFERENCES public.authority_idempotency_records(id, actor_ref_kind, actor_ref) NOT VALID;
ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT fk_audit_events_invalidation_cause FOREIGN KEY (invalidation_cause_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.authority_control
    ADD CONSTRAINT fk_authority_control_bootstrap_grant_id_admin_role_grants FOREIGN KEY (bootstrap_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT fk_checker_policies_effective_policy_hash FOREIGN KEY (effective_policy_id, effective_policy_hash) REFERENCES public.effective_project_submission_artifact_policies(id, effective_policy_hash);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT fk_checker_policies_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT fk_checker_policies_pre_submit_checker_hash FOREIGN KEY (pre_submit_checker_policy_id, pre_submit_checker_bundle_hash) REFERENCES public.pre_submit_checker_policies(id, compiled_bundle_hash);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT fk_checker_policies_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT fk_checker_policies_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT fk_checker_policies_source_snapshot_hash FOREIGN KEY (source_snapshot_id, source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT fk_checker_policies_supersedes_policy_id FOREIGN KEY (supersedes_policy_id) REFERENCES public.checker_policies(id);
ALTER TABLE ONLY public.checker_results
    ADD CONSTRAINT fk_checker_results_checker_run_id_checker_runs FOREIGN KEY (checker_run_id) REFERENCES public.checker_runs(id);
ALTER TABLE ONLY public.checker_results
    ADD CONSTRAINT fk_checker_results_submission_id_submissions FOREIGN KEY (submission_id) REFERENCES public.submissions(id);
ALTER TABLE ONLY public.checker_results
    ADD CONSTRAINT fk_checker_results_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_audit_event_id_audit_events FOREIGN KEY (audit_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_locked_post_submit_policy_hash FOREIGN KEY (locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash) REFERENCES public.checker_policies(id, guide_version, policy_hash);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_submission_id_submissions FOREIGN KEY (submission_id) REFERENCES public.submissions(id);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_submission_locked_post_submit_policy_hash FOREIGN KEY (submission_id, locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash) REFERENCES public.submissions(id, locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_submission_version FOREIGN KEY (submission_id, task_id, submission_version) REFERENCES public.submissions(id, task_id, version);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_supersedes_checker_run_id_checker_runs FOREIGN KEY (supersedes_checker_run_id) REFERENCES public.checker_runs(id);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_task_locked_guide FOREIGN KEY (task_id, locked_guide_version) REFERENCES public.workstream_tasks(id, locked_guide_version);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_task_locked_payment_policy FOREIGN KEY (task_id, locked_payment_policy_version) REFERENCES public.workstream_tasks(id, locked_payment_policy_version);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_task_locked_review_policy FOREIGN KEY (task_id, locked_review_policy_id, locked_review_policy_generation, locked_review_policy_hash) REFERENCES public.workstream_tasks(id, locked_review_policy_id, locked_review_policy_generation, locked_review_policy_hash);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_task_locked_revision_policy FOREIGN KEY (task_id, locked_revision_policy_id, locked_revision_policy_generation, locked_revision_policy_hash) REFERENCES public.workstream_tasks(id, locked_revision_policy_id, locked_revision_policy_generation, locked_revision_policy_hash);
ALTER TABLE ONLY public.project_compensation_adapter_bindings
    ADD CONSTRAINT fk_compensation_binding_adapter_actor FOREIGN KEY (adapter_actor_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_compensation_adapter_bindings
    ADD CONSTRAINT fk_compensation_binding_created_by FOREIGN KEY (created_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_compensation_adapter_bindings
    ADD CONSTRAINT fk_compensation_binding_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_compensation_adapter_bindings
    ADD CONSTRAINT fk_compensation_binding_retired_by FOREIGN KEY (retired_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_compensation_adapter_bindings
    ADD CONSTRAINT fk_compensation_binding_suspended_by FOREIGN KEY (suspended_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT fk_compilation_attempt_exact_persisted_compilation FOREIGN KEY (persisted_compilation_id, id) REFERENCES public.project_guide_compilations(id, attempt_id);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT fk_compilation_attempt_exact_setup FOREIGN KEY (setup_run_id, project_id, guide_id, source_snapshot_id, setup_generation) REFERENCES public.project_setup_runs(id, project_id, guide_id, source_snapshot_id, setup_generation);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT fk_compilation_attempt_snapshot_hash FOREIGN KEY (source_snapshot_id, source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.contribution_award_definitions
    ADD CONSTRAINT fk_contribution_award_definition_binding FOREIGN KEY (adapter_binding_id, project_id, instrument_type) REFERENCES public.project_compensation_adapter_bindings(id, project_id, instrument_type);
ALTER TABLE ONLY public.contribution_award_definitions
    ADD CONSTRAINT fk_contribution_award_definition_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.contribution_award_definitions
    ADD CONSTRAINT fk_contribution_award_definition_rule FOREIGN KEY (contribution_rule_id, contribution_policy_version_id, project_id, contribution_type) REFERENCES public.contribution_rules(id, contribution_policy_version_id, project_id, contribution_type);
ALTER TABLE ONLY public.contribution_award_definitions
    ADD CONSTRAINT fk_contribution_award_definition_unit FOREIGN KEY (project_id, instrument_type, unit_code) REFERENCES public.project_compensation_units(project_id, instrument_type, unit_code);
ALTER TABLE ONLY public.contribution_policies
    ADD CONSTRAINT fk_contribution_policy_created_by FOREIGN KEY (created_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.contribution_policies
    ADD CONSTRAINT fk_contribution_policy_current_version FOREIGN KEY (current_published_version_id, id, project_id) REFERENCES public.contribution_policy_versions(id, contribution_policy_id, project_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE ONLY public.contribution_policies
    ADD CONSTRAINT fk_contribution_policy_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.contribution_policies
    ADD CONSTRAINT fk_contribution_policy_retired_by FOREIGN KEY (retired_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT fk_contribution_policy_version_created_by FOREIGN KEY (created_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT fk_contribution_policy_version_policy FOREIGN KEY (contribution_policy_id, project_id) REFERENCES public.contribution_policies(id, project_id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT fk_contribution_policy_version_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT fk_contribution_policy_version_published_by FOREIGN KEY (published_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT fk_contribution_policy_version_retired_by FOREIGN KEY (retired_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.contribution_rules
    ADD CONSTRAINT fk_contribution_rule_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.contribution_rules
    ADD CONSTRAINT fk_contribution_rule_version FOREIGN KEY (contribution_policy_version_id, project_id) REFERENCES public.contribution_policy_versions(id, project_id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_policy_creation_actor FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_policy_creation_decision FOREIGN KEY (creation_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_policy_creation_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_policy_creation_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_policy_creation_project FOREIGN KEY (creation_scope_project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_project_submission_artifact_policies_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_psap_guide FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_psap_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_psap_source_snapshot_hash FOREIGN KEY (source_snapshot_id, source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_psap_submission_policy_hash FOREIGN KEY (submission_artifact_policy_id, submission_artifact_policy_hash) REFERENCES public.submission_artifact_policies(id, policy_hash);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_psap_supersedes FOREIGN KEY (supersedes_effective_policy_id) REFERENCES public.effective_project_submission_artifact_policies(id);
ALTER TABLE ONLY public.evidence_items
    ADD CONSTRAINT fk_evidence_items_submission_id_submissions FOREIGN KEY (submission_id) REFERENCES public.submissions(id);
ALTER TABLE ONLY public.guide_source_snapshot_items
    ADD CONSTRAINT fk_gssi_source_snapshot FOREIGN KEY (source_snapshot_id) REFERENCES public.guide_source_snapshots(id);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT fk_guide_bindings_exact_item FOREIGN KEY (source_item_id, source_snapshot_id) REFERENCES public.guide_source_snapshot_items(id, source_snapshot_id);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT fk_guide_bindings_exact_setup_generation FOREIGN KEY (project_setup_run_id, project_id, guide_id, source_snapshot_id, setup_generation) REFERENCES public.project_setup_runs(id, project_id, guide_id, source_snapshot_id, setup_generation);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT fk_guide_bindings_exact_snapshot FOREIGN KEY (source_snapshot_id, project_id, guide_id) REFERENCES public.guide_source_snapshots(id, project_id, guide_id);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT fk_guide_bindings_verified_replica_content FOREIGN KEY (verified_replica_id, content_id) REFERENCES public.artifact_replicas(id, content_id);
ALTER TABLE ONLY public.guide_source_format_classifications
    ADD CONSTRAINT fk_guide_classifications_exact_binding FOREIGN KEY (binding_id, content_id, verified_replica_id, setup_generation) REFERENCES public.guide_source_artifact_bindings(id, content_id, verified_replica_id, setup_generation);
ALTER TABLE ONLY public.guide_source_extraction_attempts
    ADD CONSTRAINT fk_guide_extraction_attempts_exact_binding FOREIGN KEY (binding_id, content_id, setup_generation) REFERENCES public.guide_source_artifact_bindings(id, content_id, setup_generation);
ALTER TABLE ONLY public.guide_source_extraction_attempts
    ADD CONSTRAINT fk_guide_extraction_attempts_exact_classification FOREIGN KEY (classification_id, binding_id, content_id, setup_generation) REFERENCES public.guide_source_format_classifications(id, binding_id, content_id, setup_generation);
ALTER TABLE ONLY public.guide_source_extraction_retry_budgets
    ADD CONSTRAINT fk_guide_extraction_retry_budgets_exact_binding FOREIGN KEY (binding_id, content_id, setup_generation) REFERENCES public.guide_source_artifact_bindings(id, content_id, setup_generation);
ALTER TABLE ONLY public.guide_source_extraction_retry_budgets
    ADD CONSTRAINT fk_guide_extraction_retry_budgets_exact_classification FOREIGN KEY (classification_id, binding_id, content_id, setup_generation) REFERENCES public.guide_source_format_classifications(id, binding_id, content_id, setup_generation);
ALTER TABLE ONLY public.guide_source_extraction_usages
    ADD CONSTRAINT fk_guide_extraction_usages_exact_attempt FOREIGN KEY (extraction_attempt_id, binding_id, content_id, setup_generation, attempt_status) REFERENCES public.guide_source_extraction_attempts(id, binding_id, content_id, setup_generation, status);
ALTER TABLE ONLY public.guide_source_extraction_usages
    ADD CONSTRAINT fk_guide_extraction_usages_exact_binding FOREIGN KEY (binding_id, content_id, source_item_id, project_setup_run_id, setup_generation) REFERENCES public.guide_source_artifact_bindings(id, content_id, source_item_id, project_setup_run_id, setup_generation);
ALTER TABLE ONLY public.guide_source_extraction_usages
    ADD CONSTRAINT fk_guide_extraction_usages_exact_content FOREIGN KEY (extracted_content_id, content_id) REFERENCES public.guide_source_extracted_contents(id, content_id);
ALTER TABLE ONLY public.guide_source_artifact_incidents
    ADD CONSTRAINT fk_guide_incidents_exact_binding FOREIGN KEY (binding_id, content_id, verified_replica_id, setup_generation) REFERENCES public.guide_source_artifact_bindings(id, content_id, verified_replica_id, setup_generation);
ALTER TABLE ONLY public.guide_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_mutation_idempotency_records_actor_profile_id__2ee3 FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.guide_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_mutation_idempotency_records_identity_link_id__3ddf FOREIGN KEY (identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.guide_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_mutation_idempotency_records_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.guide_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_mutation_idempotency_records_setup_run_id_proj_7dc3 FOREIGN KEY (setup_run_id) REFERENCES public.project_setup_runs(id);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT fk_guide_source_artifact_bindings_content_id_artifact_contents FOREIGN KEY (content_id) REFERENCES public.artifact_contents(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT fk_guide_source_artifact_bindings_supersedes_binding_id_bfa2 FOREIGN KEY (supersedes_binding_id) REFERENCES public.guide_source_artifact_bindings(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.guide_source_artifact_ingests
    ADD CONSTRAINT fk_guide_source_artifact_ingests_actor_profile_id_actor_22c1 FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.guide_source_artifact_ingests
    ADD CONSTRAINT fk_guide_source_artifact_ingests_source_item_id_guide_s_7ba9 FOREIGN KEY (source_item_id) REFERENCES public.guide_source_snapshot_items(id);
ALTER TABLE ONLY public.guide_source_extracted_contents
    ADD CONSTRAINT fk_guide_source_extracted_contents_content_id_artifact_contents FOREIGN KEY (content_id) REFERENCES public.artifact_contents(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT fk_guide_source_snapshots_created_actor FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT fk_guide_source_snapshots_created_admin_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT fk_guide_source_snapshots_created_decision FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT fk_guide_source_snapshots_created_identity_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT fk_guide_source_snapshots_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT fk_guide_source_snapshots_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT fk_guide_source_snapshots_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_sufficiency_mutation_idempotency_records_actor_16d8 FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_sufficiency_mutation_idempotency_records_guide_1d2b FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_sufficiency_mutation_idempotency_records_ident_2378 FOREIGN KEY (identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_sufficiency_mutation_idempotency_records_proje_7f82 FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_sufficiency_mutation_idempotency_records_repor_48c3 FOREIGN KEY (report_id) REFERENCES public.guide_sufficiency_reports(id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_sufficiency_mutation_idempotency_records_setup_7059 FOREIGN KEY (setup_run_id) REFERENCES public.project_setup_runs(id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_sufficiency_mutation_idempotency_records_sourc_9985 FOREIGN KEY (source_snapshot_id) REFERENCES public.guide_source_snapshots(id);
ALTER TABLE ONLY public.guide_sufficiency_report_source_usages
    ADD CONSTRAINT fk_guide_sufficiency_report_source_usages_report_id_gui_1d57 FOREIGN KEY (report_id) REFERENCES public.guide_sufficiency_reports(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_guide_sufficiency_reports_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_guide_sufficiency_reports_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_guide_sufficiency_reports_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_guide_sufficiency_reports_source_snapshot_hash FOREIGN KEY (source_snapshot_id, source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.legacy_workflow_eligibility
    ADD CONSTRAINT fk_legacy_workflow_eligibility_actor_id_legacy_actor_identities FOREIGN KEY (actor_id) REFERENCES public.legacy_actor_identities(actor_id);
ALTER TABLE ONLY public.outbox_events
    ADD CONSTRAINT fk_outbox_events_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.payment_policies
    ADD CONSTRAINT fk_payment_policies_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.payment_policies
    ADD CONSTRAINT fk_payment_policies_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.policy_mutation_idempotency_records
    ADD CONSTRAINT fk_policy_mutation_idempotency_records_actor_profile_id_41c2 FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.policy_mutation_idempotency_records
    ADD CONSTRAINT fk_policy_mutation_idempotency_records_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.policy_mutation_idempotency_records
    ADD CONSTRAINT fk_policy_mutation_idempotency_records_identity_link_id_b806 FOREIGN KEY (identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.policy_mutation_idempotency_records
    ADD CONSTRAINT fk_policy_mutation_idempotency_records_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_checker_policies_effective_hash FOREIGN KEY (effective_policy_id, effective_policy_hash) REFERENCES public.effective_project_submission_artifact_policies(id, effective_policy_hash);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_checker_policies_guide FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_checker_policies_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_checker_policies_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_checker_policies_source_snapshot_hash FOREIGN KEY (source_snapshot_id, source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_checker_policies_supersedes FOREIGN KEY (supersedes_pre_submit_checker_policy_id) REFERENCES public.pre_submit_checker_policies(id);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_assignment FOREIGN KEY (assignment_id, task_id, actor_profile_id) REFERENCES public.task_assignments(id, task_id, contributor_id);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_guide_lineage FOREIGN KEY (guide_id, project_id, guide_version) REFERENCES public.project_guides(id, project_id, version);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_identity_actor FOREIGN KEY (identity_link_id, actor_profile_id) REFERENCES public.actor_identity_links(id, actor_profile_id);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_predecessor FOREIGN KEY (predecessor_submission_id, task_id, predecessor_submission_version) REFERENCES public.submissions(id, task_id, version);
ALTER TABLE ONLY public.pre_submit_evidence_results
    ADD CONSTRAINT fk_pre_submit_evidence_results_evidence_set_id_pre_subm_096e FOREIGN KEY (evidence_set_id) REFERENCES public.pre_submit_evidence_sets(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_actor_profile_id_actor_profiles FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_assignment_id_task_assignments FOREIGN KEY (assignment_id) REFERENCES public.task_assignments(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_effective_policy_id_effecti_6a99 FOREIGN KEY (effective_policy_id) REFERENCES public.effective_project_submission_artifact_policies(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_identity_link_id_actor_iden_5cef FOREIGN KEY (identity_link_id) REFERENCES public.actor_identity_links(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_pre_submit_policy_id_pre_su_c77f FOREIGN KEY (pre_submit_policy_id) REFERENCES public.pre_submit_checker_policies(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_predecessor_submission_id_s_6ec2 FOREIGN KEY (predecessor_submission_id) REFERENCES public.submissions(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_source_snapshot_id_guide_so_1667 FOREIGN KEY (source_snapshot_id) REFERENCES public.guide_source_snapshots(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_task_artifact_policy FOREIGN KEY (task_id, effective_policy_id, locked_artifact_policy_sha256) REFERENCES public.workstream_tasks(id, locked_effective_project_submission_artifact_policy_id, locked_effective_project_submission_artifact_policy_hash);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_task_checker_policy FOREIGN KEY (task_id, pre_submit_policy_id, locked_checker_policy_sha256) REFERENCES public.workstream_tasks(id, locked_pre_submit_checker_policy_id, locked_pre_submit_checker_bundle_hash);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_task_guide FOREIGN KEY (task_id, guide_version) REFERENCES public.workstream_tasks(id, locked_guide_version);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_task_project FOREIGN KEY (task_id, project_id) REFERENCES public.workstream_tasks(id, project_id);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_task_source_snapshot FOREIGN KEY (task_id, source_snapshot_id, source_snapshot_sha256) REFERENCES public.workstream_tasks(id, locked_guide_source_snapshot_id, locked_guide_source_snapshot_hash);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_policy_creation_actor FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_policy_creation_decision FOREIGN KEY (creation_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_policy_creation_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_policy_creation_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_policy_creation_project FOREIGN KEY (creation_scope_project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_compensation_units
    ADD CONSTRAINT fk_project_compensation_unit_created_by FOREIGN KEY (created_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_compensation_units
    ADD CONSTRAINT fk_project_compensation_unit_iso_currency FOREIGN KEY (iso_currency_code) REFERENCES public.iso_4217_currency_codes(code);
ALTER TABLE ONLY public.project_compensation_units
    ADD CONSTRAINT fk_project_compensation_unit_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_compensation_units
    ADD CONSTRAINT fk_project_compensation_unit_retired_by FOREIGN KEY (retired_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_create_idempotency_records
    ADD CONSTRAINT fk_project_create_idempotency_records_actor_profile_id__ebb1 FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_create_idempotency_records
    ADD CONSTRAINT fk_project_create_idempotency_records_identity_link_id__ddce FOREIGN KEY (identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT fk_project_guide_compilation_attempts_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT fk_project_guide_compilation_attempts_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilation_predecessor FOREIGN KEY (supersedes_compilation_id, project_id, guide_id) REFERENCES public.project_guide_compilations(id, project_id, guide_id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_attempt_id_project_guide__0e94 FOREIGN KEY (attempt_id) REFERENCES public.project_guide_compilation_attempts(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_authorization_decision_ev_42ad FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_created_by_actor_profile__953f FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_created_via_identity_link_b250 FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_setup_run_id_project_setup_runs FOREIGN KEY (setup_run_id) REFERENCES public.project_setup_runs(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_source_snapshot_id_guide__033a FOREIGN KEY (source_snapshot_id) REFERENCES public.guide_source_snapshots(id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_last_mutated_actor FOREIGN KEY (last_mutated_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_last_mutated_admin_grant FOREIGN KEY (last_mutated_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_last_mutated_decision FOREIGN KEY (last_authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_last_mutated_identity_link FOREIGN KEY (last_mutated_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_selected_review_policy FOREIGN KEY (project_id, version, selected_review_policy_id, selected_review_policy_generation, selected_review_policy_hash) REFERENCES public.review_policies(project_id, guide_version, id, policy_generation, policy_hash);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_selected_revision_policy FOREIGN KEY (project_id, version, selected_revision_policy_id, selected_revision_policy_generation, selected_revision_policy_hash) REFERENCES public.revision_policies(project_id, guide_version, id, policy_generation, policy_hash);
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT fk_project_role_grants_actor_profile_id_actor_profiles FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT fk_project_role_grants_granted_by_actor_profile_id_acto_c240 FOREIGN KEY (granted_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT fk_project_role_grants_granted_by_admin_role_grant_id_a_71d7 FOREIGN KEY (granted_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT fk_project_role_grants_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT fk_project_role_grants_revoked_by_actor_profile_id_acto_a5dd FOREIGN KEY (revoked_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT fk_project_role_grants_revoked_by_admin_role_grant_id_a_aa4d FOREIGN KEY (revoked_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.project_role_qualification_snapshots
    ADD CONSTRAINT fk_project_role_qualification_snapshots_actor_profile_i_aedc FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_role_qualification_snapshots
    ADD CONSTRAINT fk_project_role_qualification_snapshots_captured_by_act_ab57 FOREIGN KEY (captured_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_role_qualification_snapshots
    ADD CONSTRAINT fk_project_role_qualification_snapshots_captured_by_adm_c8b8 FOREIGN KEY (captured_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.project_role_qualification_snapshots
    ADD CONSTRAINT fk_project_role_qualification_snapshots_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_artifact_incident FOREIGN KEY (error_artifact_incident_id) REFERENCES public.guide_source_artifact_incidents(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_authorized_actor FOREIGN KEY (authorized_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_authorized_admin_grant FOREIGN KEY (authorized_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_authorized_decision FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_authorized_identity_link FOREIGN KEY (authorized_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_continuation_verification_job FOREIGN KEY (continuation_verification_job_id) REFERENCES public.artifact_verification_jobs(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_post_submit_checker_policy FOREIGN KEY (output_post_submit_checker_policy_id) REFERENCES public.checker_policies(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_source_snapshot_hash FOREIGN KEY (source_snapshot_id, source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_source_snapshot_id_guide_source_snapshots FOREIGN KEY (source_snapshot_id) REFERENCES public.guide_source_snapshots(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_submission_artifact_policy FOREIGN KEY (output_submission_artifact_policy_id) REFERENCES public.submission_artifact_policies(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_sufficiency_report FOREIGN KEY (output_sufficiency_report_id) REFERENCES public.guide_sufficiency_reports(id);
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT fk_projects_creation_actor FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT fk_projects_creation_admin_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT fk_projects_creation_decision FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT fk_projects_creation_identity_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT fk_review_admission_checker FOREIGN KEY (admitting_checker_run_id) REFERENCES public.checker_runs(id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT fk_review_admission_committed_queue FOREIGN KEY (review_queue_entry_id, project_id, task_id, submission_id, submission_version, admitting_checker_run_id) REFERENCES public.review_queue_entries(id, project_id, task_id, submission_id, submission_version, admitting_checker_run_id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT fk_review_admission_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT fk_review_admission_queue FOREIGN KEY (review_queue_entry_id) REFERENCES public.review_queue_entries(id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT fk_review_admission_submission FOREIGN KEY (submission_id) REFERENCES public.submissions(id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT fk_review_admission_submission_lineage FOREIGN KEY (submission_id, task_id, submission_version) REFERENCES public.submissions(id, task_id, version);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT fk_review_admission_task FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT fk_review_lease_policy_version FOREIGN KEY (reviewer_contribution_policy_version_id, project_id) REFERENCES public.contribution_policy_versions(id, project_id);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT fk_review_lease_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT fk_review_lease_queue_lineage FOREIGN KEY (review_queue_entry_id, project_id, task_id, submission_id, submission_version) REFERENCES public.review_queue_entries(id, project_id, task_id, submission_id, submission_version);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT fk_review_lease_reviewer FOREIGN KEY (reviewer_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT fk_review_lease_submission FOREIGN KEY (submission_id) REFERENCES public.submissions(id);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT fk_review_lease_task FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT fk_review_policies_actor_profile FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT fk_review_policies_admin_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT fk_review_policies_decision_event FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT fk_review_policies_identity_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT fk_review_policies_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT fk_review_policies_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT fk_review_policies_supersedes FOREIGN KEY (supersedes_policy_id) REFERENCES public.review_policies(id);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT fk_review_queue_active_lease FOREIGN KEY (active_lease_id, id) REFERENCES public.review_leases(id, review_queue_entry_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT fk_review_queue_checker FOREIGN KEY (admitting_checker_run_id) REFERENCES public.checker_runs(id);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT fk_review_queue_preferred_reviewer FOREIGN KEY (preferred_reviewer_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT fk_review_queue_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT fk_review_queue_submission FOREIGN KEY (submission_id) REFERENCES public.submissions(id);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT fk_review_queue_submission_lineage FOREIGN KEY (submission_id, task_id, submission_version) REFERENCES public.submissions(id, task_id, version);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT fk_review_queue_task FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT fk_revision_policies_actor_profile FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT fk_revision_policies_admin_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT fk_revision_policies_decision_event FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT fk_revision_policies_identity_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT fk_revision_policies_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT fk_revision_policies_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT fk_revision_policies_supersedes FOREIGN KEY (supersedes_policy_id) REFERENCES public.revision_policies(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_sap_supersedes_policy FOREIGN KEY (supersedes_policy_id) REFERENCES public.submission_artifact_policies(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_artifact_policies_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_artifact_policies_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_artifact_policies_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_artifact_policies_source_snapshot_hash FOREIGN KEY (source_snapshot_id, source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_actor_profile_id_actor_profiles FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_artifact_content_id_art_12c8 FOREIGN KEY (artifact_content_id) REFERENCES public.artifact_contents(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_assignment_id_task_assignments FOREIGN KEY (assignment_id) REFERENCES public.task_assignments(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_consumed_by_submission__2b23 FOREIGN KEY (consumed_by_submission_id) REFERENCES public.submissions(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_durable_intent_id_submi_102c FOREIGN KEY (durable_intent_id) REFERENCES public.submission_bundle_durable_intents(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_identity_link_id_actor__d29d FOREIGN KEY (identity_link_id) REFERENCES public.actor_identity_links(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_pre_submit_evidence_set_a752 FOREIGN KEY (pre_submit_evidence_set_id) REFERENCES public.pre_submit_evidence_sets(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_predecessor_submission__242d FOREIGN KEY (predecessor_submission_id) REFERENCES public.submissions(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_put_attempt_id_artifact_bbc3 FOREIGN KEY (put_attempt_id) REFERENCES public.artifact_put_attempts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_put_observation_receipt_5136 FOREIGN KEY (put_observation_receipt_id) REFERENCES public.artifact_put_observation_receipts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_put_operation_receipt_i_9602 FOREIGN KEY (put_operation_receipt_id) REFERENCES public.artifact_operation_receipts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_verification_receipt_id_0ea1 FOREIGN KEY (verification_receipt_id) REFERENCES public.artifact_verification_receipts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_verified_replica_id_art_3a4e FOREIGN KEY (verified_replica_id) REFERENCES public.artifact_replicas(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_durable_intents
    ADD CONSTRAINT fk_submission_bundle_durable_intents_pre_submit_evidenc_c406 FOREIGN KEY (pre_submit_evidence_set_id) REFERENCES public.pre_submit_evidence_sets(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_durable_intents
    ADD CONSTRAINT fk_submission_bundle_durable_intents_put_attempt_id_art_b4e4 FOREIGN KEY (put_attempt_id) REFERENCES public.artifact_put_attempts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_approval_actor FOREIGN KEY (approved_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_approval_decision FOREIGN KEY (approval_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_approval_grant FOREIGN KEY (approved_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_approval_link FOREIGN KEY (approved_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_approval_project FOREIGN KEY (approval_scope_project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_creation_actor FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_creation_decision FOREIGN KEY (creation_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_creation_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_creation_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_creation_project FOREIGN KEY (creation_scope_project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_actor_f5bb FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_commi_4fa6 FOREIGN KEY (committed_effective_policy_id) REFERENCES public.effective_project_submission_artifact_policies(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_commi_571a FOREIGN KEY (committed_policy_id) REFERENCES public.submission_artifact_policies(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_commi_baa9 FOREIGN KEY (committed_pre_submit_policy_id) REFERENCES public.pre_submit_checker_policies(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_guide_ed8d FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_ident_2567 FOREIGN KEY (identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_proje_442a FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_setup_a102 FOREIGN KEY (setup_run_id) REFERENCES public.project_setup_runs(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_sourc_536e FOREIGN KEY (source_snapshot_id) REFERENCES public.guide_source_snapshots(id);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_contributor_id_actor_profiles FOREIGN KEY (contributor_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_locked_effective_policy_hash FOREIGN KEY (locked_effective_project_submission_artifact_policy_id, locked_effective_project_submission_artifact_policy_hash) REFERENCES public.effective_project_submission_artifact_policies(id, effective_policy_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_locked_post_submit_policy_hash FOREIGN KEY (locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash) REFERENCES public.checker_policies(id, guide_version, policy_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_locked_pre_submit_checker_hash FOREIGN KEY (locked_pre_submit_checker_policy_id, locked_pre_submit_checker_bundle_hash) REFERENCES public.pre_submit_checker_policies(id, compiled_bundle_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_locked_source_snapshot_hash FOREIGN KEY (locked_guide_source_snapshot_id, locked_guide_source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_supersedes_submission_id_submissions FOREIGN KEY (supersedes_submission_id) REFERENCES public.submissions(id);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_effective_policy_hash FOREIGN KEY (task_id, locked_effective_project_submission_artifact_policy_id, locked_effective_project_submission_artifact_policy_hash) REFERENCES public.workstream_tasks(id, locked_effective_project_submission_artifact_policy_id, locked_effective_project_submission_artifact_policy_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_guide FOREIGN KEY (task_id, locked_guide_version) REFERENCES public.workstream_tasks(id, locked_guide_version);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_payment_policy FOREIGN KEY (task_id, locked_payment_policy_version) REFERENCES public.workstream_tasks(id, locked_payment_policy_version);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_post_submit_policy_hash FOREIGN KEY (task_id, locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash) REFERENCES public.workstream_tasks(id, locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_pre_submit_checker_hash FOREIGN KEY (task_id, locked_pre_submit_checker_policy_id, locked_pre_submit_checker_bundle_hash) REFERENCES public.workstream_tasks(id, locked_pre_submit_checker_policy_id, locked_pre_submit_checker_bundle_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_review_policy FOREIGN KEY (task_id, locked_review_policy_id, locked_review_policy_generation, locked_review_policy_hash) REFERENCES public.workstream_tasks(id, locked_review_policy_id, locked_review_policy_generation, locked_review_policy_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_revision_policy FOREIGN KEY (task_id, locked_revision_policy_id, locked_revision_policy_generation, locked_revision_policy_hash) REFERENCES public.workstream_tasks(id, locked_revision_policy_id, locked_revision_policy_generation, locked_revision_policy_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_source_snapshot_hash FOREIGN KEY (task_id, locked_guide_source_snapshot_id, locked_guide_source_snapshot_hash) REFERENCES public.workstream_tasks(id, locked_guide_source_snapshot_id, locked_guide_source_snapshot_hash);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_ack_actor FOREIGN KEY (warnings_acknowledged_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_ack_decision FOREIGN KEY (warning_acknowledgement_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_ack_grant FOREIGN KEY (warnings_acknowledged_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_ack_link FOREIGN KEY (warnings_acknowledged_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_ack_project FOREIGN KEY (warning_acknowledgement_scope_project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_create_actor FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_create_decision FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_create_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_create_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_create_project FOREIGN KEY (creation_scope_project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.guide_sufficiency_report_source_usages
    ADD CONSTRAINT fk_sufficiency_report_source_usage_exact_extraction FOREIGN KEY (extraction_usage_id, source_item_id, binding_id, content_id, extraction_attempt_id, extracted_content_id, project_setup_run_id, setup_generation) REFERENCES public.guide_source_extraction_usages(id, source_item_id, binding_id, content_id, extraction_attempt_id, extracted_content_id, project_setup_run_id, setup_generation);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_sufficiency_reports_setup_run FOREIGN KEY (project_setup_run_id) REFERENCES public.project_setup_runs(id);
ALTER TABLE ONLY public.task_assignments
    ADD CONSTRAINT fk_task_assignments_contributor_id_actor_profiles FOREIGN KEY (contributor_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.task_assignments
    ADD CONSTRAINT fk_task_assignments_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_effective_policy_hash FOREIGN KEY (locked_effective_project_submission_artifact_policy_id, locked_effective_project_submission_artifact_policy_hash) REFERENCES public.effective_project_submission_artifact_policies(id, effective_policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_guide FOREIGN KEY (project_id, locked_guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_payment_policy FOREIGN KEY (project_id, locked_payment_policy_version) REFERENCES public.payment_policies(project_id, guide_version);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_post_submit_policy_hash FOREIGN KEY (locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash) REFERENCES public.checker_policies(id, guide_version, policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_pre_submit_checker_hash FOREIGN KEY (locked_pre_submit_checker_policy_id, locked_pre_submit_checker_bundle_hash) REFERENCES public.pre_submit_checker_policies(id, compiled_bundle_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_review_policy FOREIGN KEY (project_id, locked_guide_version, locked_review_policy_id, locked_review_policy_generation, locked_review_policy_hash) REFERENCES public.review_policies(project_id, guide_version, id, policy_generation, policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_revision_policy FOREIGN KEY (project_id, locked_guide_version, locked_revision_policy_id, locked_revision_policy_generation, locked_revision_policy_hash) REFERENCES public.revision_policies(project_id, guide_version, id, policy_generation, policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_source_snapshot_hash FOREIGN KEY (locked_guide_source_snapshot_id, locked_guide_source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT qualification_ownership FOREIGN KEY (qualification_snapshot_id, actor_profile_id, project_id, role) REFERENCES public.project_role_qualification_snapshots(id, actor_profile_id, project_id, requested_role) ON DELETE RESTRICT;
