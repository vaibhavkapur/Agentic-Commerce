# API Reference

[Documentation](index.md) · [Getting Started](getting-started.md) · [Repository README](../README.md)

The API runs at `http://127.0.0.1:4318`. Requests are validated in [server/index.ts](../server/index.ts); client calls are in [src/api.ts](../src/api.ts) and shared data types in [src/types.ts](../src/types.ts).

All non-GET API requests need `x-ralio-client: workspace`. Local mode enforces loopback Host/origin checks. Supabase mode requires `Authorization: Bearer <token>` except for `/api/config`; `x-organization-id` selects one of the authenticated user's memberships.

`POST /api/projects` accepts a multipart `archive` plus project fields. The [Source Contract](source-contract.md) defines ZIP limits. Generation and verification operate on the named project; downloads are scoped to the same organization.

## Routes

- `GET /api/config`
- `GET /api/projects`
- `POST /api/projects/sample`
- `POST /api/projects`
- `GET /api/projects/:id`
- `POST /api/projects/:id/generate`
- `POST /api/projects/:id/verify`
- `POST /api/projects/:id/cancel`
- `GET /api/projects/:id/patch`
- `GET /api/projects/:id/report`
- `GET /api/docs`
- `POST /api/docs/:topic`
