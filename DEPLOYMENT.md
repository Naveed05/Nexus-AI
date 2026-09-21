# NEXUS Deployment

## Container runtime

Build and start the API with:

```bash
docker compose up --build -d
```

The API listens on port 8000.

## Operational endpoints

- `GET /api/v1/health` — process/liveness check.
- `GET /api/v1/ready` — readiness check for runtime and frontend.
- `GET /api/v1/production/health` — production runtime capacity.
- `GET /api/v1/observability/summary` — runtime observability snapshot.

## Persistence

The compose configuration mounts `.nexus` into a named volume. This preserves SQLite runtime state and local workspace artifacts across container restarts.

For production environments, place the volume on durable storage and back it up according to the deployment platform's recovery policy.

## Security

Run the container as the non-root `nexus` user. Supply secrets through the deployment platform's secret manager rather than committing `.env` files or provider credentials.

## Scaling boundary

The current local SQLite stores and in-process registries are intentionally safe for a single API instance. Before horizontal scaling, move shared runtime/job state to a transactional database and shared object storage, then introduce a distributed queue and shared cache.

## CI/CD

GitHub Actions remains the source-of-truth regression gate. A deployment pipeline should promote only commits whose API test workflow is green.
