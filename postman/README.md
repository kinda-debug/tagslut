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

## Export from Postman (Collection + Environment)

### 1) Export the collection

1. In Postman (Cloud), locate the collection **"tagslut-api"**.
2. Click the **…** (More actions) menu → **Export**.
3. Choose **Collection v2.1** format.
4. Save the file to:

   - `postman/collection.json`

> Note: `postman/collection.example.json` is a tiny stub you can reference for shape, but the real file committed in this repo should be the full export at `postman/collection.json`.

### 2) Export the environment

1. In Postman, open **Environments**.
2. Find **"Metadata Validation Operator (TIDAL v2 + Beatport)"**.
3. Click **Export**.
4. Save the file to:

   - `postman/environment.json`

---

## Import into Postman

### Import the collection

1. In Postman, click **Import**.
2. Select `postman/collection.json`.

### Import the environment

1. In Postman, click **Import**.
2. Select `postman/environment.json`.
3. Select the imported environment as the active environment.

---

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
