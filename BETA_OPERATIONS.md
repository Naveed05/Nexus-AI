# Public Beta Operations

## Pre-release checks

1. Run the full API and benchmark CI workflows.
2. Build the production container.
3. Verify `/api/v1/health` and `/api/v1/ready`.
4. Verify `/api/v1/metrics` is reachable only inside the trusted deployment network.
5. Configure `BETA_ACCESS_KEY` in the deployment secret manager when production beta access is enabled.
6. Confirm durable storage and backup retention for `.nexus`.
7. Exercise a restore drill before accepting production data.
8. Review provider credentials and remove any test keys.

## Backup and recovery

The beta runtime uses local SQLite and filesystem artifacts as a deliberate single-instance boundary. Take regular snapshots of the `.nexus` data directory and test restoration into a clean instance.

A restore drill is successful when the restored instance can start, pass `/api/v1/ready`, and read previously persisted run/workspace state.

## Incident response

For an operational incident:

1. Stop new traffic if data integrity is uncertain.
2. Preserve logs and the affected `.nexus` snapshot.
3. Inspect `/api/v1/observability/summary` and `/api/v1/metrics`.
4. Restore into an isolated instance if recovery is required.
5. Validate health, readiness, and representative workflows before reopening traffic.

## Security boundary

The beta access key is an additional gate, not a replacement for a full identity provider. Before multi-user public scale, replace the header-based beta gate with authenticated sessions/tokens, centralized authorization, distributed rate limiting, shared state, and an external secret manager.
