## Dec 22, 2025 — Database layer + repository tests
- ✅ Added SQLite database schema defining plans, limits, subjects, and relationships.
- ✅ Implemented a repository layer to encapsulate all database access and queries.
- ✅ Added SQLite connection setup with foreign key enforcement and runtime DB creation.
- ✅ Wrote comprehensive unit tests covering repository behavior, constraints, and edge cases.
- ✅ Validated database constraints and referential integrity through brute-force and fuzz-style tests.
- ❓ How do we fight SQL-Injection. What are the best methods in making sure our SQL DB are safe. 
- ❓ What other functons are helpful in Repo.py.
- ❓ How much of the database should be exposed? In tests, it gives a clear picture of what our database looks like.

## Dec 25, 2025 — API V1 and Entitlements

- ✅ Implemented an entitlement service to resolve effective permissions and limits from authenticated identity.
- ✅ Updated the database schema to preserve custom plan overrides when users switch between subscription tiers.
- ✅ Extended the repository layer to support subject-scoped entitlement resolution.
- ❓ Need to refactor entitlement service construction using FastAPI Depends for proper database connection lifecycle management.
- ❓ Need to finalize the JWT claim contract to determine which identity fields are included in issued tokens.
- ❓ Open design question around subject provisioning: explicit onboarding vs gateway-driven creation. 

## Dec 31, 2025 — README and Settings
- ✅ Modified README to encapsulate whole REPO.
- ❓ Need to indentify what should be grabbed from .env
to go into settings and what should go into settings
- ❓ Once auth is set up, switch HS256 Algorithm to RS256.
- ❓ Clean commit history.

## Jan 14th, 2026 — Update SQL to JWT Settings
 ✅ Updated SCHEMA to account for personalized JWT
 ✅ Updated userID to now be UUID format instead of integer.
 ✅ Modified auth.py to account for correct public key verification instead of hs256.





