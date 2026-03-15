-- supabase/migrations/YYYYMMDDHHMMSS_rls_policies_service_role.sql
--
-- Minimal RLS: Allow service_role complete access
-- This unblocks backend development while RLS guard is active
--
-- Service role is used by:
-- - Identity service (track identity deduplication, linking)
-- - Zone classification (asset file zone transitions)
-- - Audit system (reconcile_log, provenance_event)
-- - Scheduled jobs (scan runs, tag hoard maintenance)
-- - Admin tooling
--
-- Authenticated/user-level policies deferred to Phase 2

DO $$
DECLARE
  t text;
  policy_created int := 0;
BEGIN
  FOR t IN
    SELECT tablename FROM pg_tables WHERE schemaname = 'public'
  LOOP
    EXECUTE format('
      CREATE POLICY service_role_all ON public.%I
      FOR ALL
      USING (auth.role() = ''service_role'')
      WITH CHECK (auth.role() = ''service_role'');
    ', t);
    policy_created := policy_created + 1;
  END LOOP;
  
  RAISE NOTICE 'Created % RLS policies for service_role', policy_created;
END $$;
