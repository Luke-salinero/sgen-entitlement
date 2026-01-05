# SGen Entitlement Service
========================

This repository contains the Entitlement Service for SGen. Its job is to resolve a subject’s
effective permissions and limits (e.g., plan tier, feature flags, max values) from persisted
plan + override data, and expose that information to the rest of the platform (e.g., the gateway).

--------------------------------------------------------------------------------
## What this service does
--------------------------------------------------------------------------------

- Stores and manages subscription plans and enforceable plan limits
- Associates each subject (user / API consumer) with exactly one plan
- Supports subject-scoped overrides that survive plan changes (so custom limits aren’t wiped
  when a user moves between tiers)
- Computes effective entitlements by combining base plan limits with any subject overrides

--------------------------------------------------------------------------------
## Repository structure
--------------------------------------------------------------------------------

Typical layout:

- app/api/        FastAPI routes (REST interface)
- app/core/       app configuration + shared utilities (e.g., auth/config)
- app/db/         SQLite connection + repository layer + schema
- tests/          unit tests for auth/repo/services/api

--------------------------------------------------------------------------------
## Quickstart
--------------------------------------------------------------------------------

Requirements:
- Python 3.11+ (recommended)
- pip / venv

Setup:
  python -m venv .venv
  Windows: .venv\Scripts\activate
  Mac/Linux: source .venv/bin/activate

  pip install -r requirements.txt

Run locally:
  uvicorn app.main:app --reload

API docs:
- Swagger UI: /docs
- OpenAPI JSON: /openapi.json

--------------------------------------------------------------------------------
## Configuration
--------------------------------------------------------------------------------

Configuration is provided via environment variables (see `app/core/config.py`). No secrets should be committed.

Common variables:
- `ENV` — environment name (default: `dev`)
- `DEBUG` — set to `1` to enable debug mode (default: `0`)
- `SERVICE_NAME` — service identifier (default: `entitlements-service`)
- `REQUEST_ID_HEADER` — request ID header name (default: `X-Request-Id`)
- `DB_PATH` — path to the SQLite database file (default: `app/data/entitlements.db`)

JWT verification:
- `JWT_ISSUER`, `JWT_AUDIENCE`
- `JWT_ALGORITHMS` (default: `HS256`)
- `JWT_PUBLIC_KEY` (signing key / secret, depending on algorithm)


--------------------------------------------------------------------------------
## API endpoints

This service exposes its full interface via `/docs`. Current routes:

- `GET /v1/entitlements` — Returns the caller’s effective entitlements (plan + resolved limits).
- `GET /v1/whoami` — Returns the authenticated identity derived from the presented token.

--------------------------------------------------------------------------------
## Entitlement resolution rules
--------------------------------------------------------------------------------

At a high level, effective entitlements are computed like this:

1) Load the subject’s assigned plan (subject_plan)
2) Load the plan’s base limits (plan_limits)
3) Load any subject-specific overrides (e.g., subject_plan_limits)
4) Compute effective limits by preferring overrides when present

--------------------------------------------------------------------------------
## Database
--------------------------------------------------------------------------------

This service uses SQLite as its persistence layer for managing subscription plans, limits,
and user–plan relationships.

The database is designed to be:
- Schema-driven, with constraints enforced at the database level
- Accessed exclusively through a repository layer

Structure:
All database-related code lives under app/db/.

Schema Overview:
- plans
  Defines available subscription tiers (e.g. free, pro) and access flags.

- plan_limits
  Has numeric and boolean limits per plan.

- subjects
  Represents users or API consumers.

- subject_plan
  Ties each subject with exactly one plan.

(Optional, if overrides exist in your repo)
- subject_plan_limits (or similar)
  Stores subject-scoped custom limit overrides that take precedence over the base plan limits.

Database Access Pattern:
All database access is performed through the repository layer (e.g., PlanRepo in repo.py).
Other parts of the application should not execute raw SQL directly.

Local Development:
- The SQLite database file is created automatically at runtime if it does not exist.
- Database files are stored in a runtime directory and are not committed to the repository.
- The schema is applied during initialization or test setup.

--------------------------------------------------------------------------------
## Running tests
--------------------------------------------------------------------------------

Run unit tests with:

  python -m unittest discover -s tests -p "test_*.py" -v
