# Deployment — ZatGo Core

1. Ship app sources to the bench `apps/` path (or install from this monorepo).
2. `bench migrate`
3. `bench build --app zatgo_core`
4. Restart workers / web: `bench restart`
5. Verify `/api/method/zatgo_core.api.v1.health.get_system_health`

## Production hardening

- Restrict Integration / Security settings to System Manager + Application Admin.
- Store provider secrets only in Password fields / vault — never commit.
- Enable audit (`ZG Security Settings.audit_enabled`).
- Monitor Redis and queue depth via System Health API / dashboard.
