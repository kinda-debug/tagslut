# Postman exports

This folder stores **sanitized** Postman exports (Collection + Environment) for this repo.

## What lives here

- `postman/collection.json` — exported Postman Collection
- `postman/environment.json` — exported Postman Environment (**no secrets**)
- Optional local-only files (do **not** commit):
  - `postman/environment.secrets.json`
  - `postman/*.local.json`

> Keep secrets out of Git. Postman exports can include tokens and credentials.

---

## Keeping Postman Cloud in sync with this repo

This folder is the Git-tracked “source of truth” for the latest **sanitized** exports:

- `postman/collection.json` ← export of the [tagslut-api](collection/53520441-d3f8de55-e4a7-4728-b3ca-5ee725b60aef) collection
- `postman/environment.json` ← export of the [Metadata Validation Operator (TIDAL v2 + Beatport)](environment/53520441-47ecd53d-7f46-4803-823a-b0b71b513bd8) environment (**no secrets**)

When you change requests / scripts / variables in Postman Cloud, **re-export** into these files so the repo stays in sync.

---

## Export from Postman UI → write to `postman/*.json`

### Export the collection (`postman/collection.json`)

1. In Postman, locate the **tagslut-api** collection.
2. Click **…** (More actions) → **Export**.
3. Choose **Collection v2.1** format.
4. Save/overwrite:
   - `postman/collection.json`

### Export the environment (`postman/environment.json`)

1. In Postman, open **Environments**.
2. Find **Metadata Validation Operator (TIDAL v2 + Beatport)**.
3. Click **Export**.
4. Save/overwrite:
   - `postman/environment.json`

---

## Secrets: don’t commit them

Postman environment exports can include tokens, API keys, refresh tokens, client secrets, etc. Do **not** commit real secret values.

- Use `postman/environment.secrets.example.json` as the template for which secret keys are expected.
- Store real secrets in **Postman Vault** (preferred) or in a local-only file/flow (for example via `postman/env_exports.sh`).

Before committing, open `postman/environment.json` and ensure secret values are placeholders/empty.

---

## Import from `postman/*.json` → Postman UI

### Import the collection

1. In Postman, click **Import**.
2. Select `postman/collection.json`.
3. If prompted, choose the target workspace and complete the import.

### Import the environment

1. In Postman, click **Import**.
2. Select `postman/environment.json`.
3. Set it as the active environment.


## Update workflow (keeping exports current)

When requests / scripts / variables change:

1. Make and verify your changes in Postman.
2. Re-export:
   - the collection to `postman/collection.json`
   - the environment to `postman/environment.json`
3. **Sanitize before committing** (see below).
4. Commit the updated JSON exports.

---

## Secrets warning (access tokens, API keys)

### What not to commit

Do **not** commit real values for items like:

- `tidal_access_token`
- `beatport_access_token`
- API keys, refresh tokens, client secrets, or passwords

These often appear in exported environment JSON.

### Recommended approach

- Keep `postman/environment.json` committed with **placeholder values** (or empty strings) for secret variables.
- Keep your real secrets in a **local-only** file such as:
  - `postman/environment.secrets.json` (ignored by git)
- Use `postman/environment.secrets.example.json` as the template of which secrets are expected:
  - `tidal_access_token`
  - `beatport_access_token`
  - `spotify_access_token`

If you need to share how to set secrets:

1. Document the variable names (only) in `postman/environment.json`.
2. Provide setup instructions in this README.
3. Each developer fills in secret values locally in Postman (or via a local-only environment export).

> Tip: In Postman, consider keeping secret values in the "Current value" field (local to your account/workspace) and leaving "Initial value" blank/placeholder. Exports can still include values depending on how you export—always review before committing.
