## Database

This service uses **SQLite** as its persistence layer for managing subscription plans, limits, and user–plan relationships.

The database is designed to be:
- **Lightweight** and easy to run locally
- **Schema-driven**, with constraints enforced at the database level
- **Accessed exclusively through a repository layer**, rather than raw SQL scattered throughout the codebase

### Structure

All database-related code lives under `app/db/`:


### Schema Overview

The schema includes:

- **plans**  
  Defines available subscription tiers (e.g. `free`, `pro`) and access flags.

- **plan_limits**  
  Has numeric and boolean limits per plan.

- **subjects**  
  Represents users or API consumers

- **subject_plan**  
  Ties each subject with exactly one plan.


### Database Access Pattern

All database access is performed through the repository layer (`PlanRepo` in `repo.py`). 
Other parts of the application should **not execute raw SQL directly**.

This provides:
- A single, well-defined interface for database queries
- Easier unit testing and validation
- Clear separation between business logic and persistence

### Local Development

- The SQLite database file is created automatically at runtime if it does not exist.
- Database files are stored in a runtime directory and are **not committed to the repository**.
- The schema is applied during initialization or test setup.
