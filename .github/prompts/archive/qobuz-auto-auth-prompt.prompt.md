# qobuz-auto-auth-prompt — Prompt for Qobuz credentials inline when missing

## Do not recreate existing files. Do not modify files not listed in scope.

## Goal

When `tagslut index enrich --hoarding` runs and Qobuz has no credentials
(no app_id, app_secret, or user_auth_token in tokens.json), instead of
silently skipping all Qobuz requests with a warning, prompt the user
interactively for their email and password right there in the terminal.

This should happen once, at provider initialization time, not per-request.

## Behaviour

When `QobuzProvider` is initialized (or on first request) and credentials
are missing:

1. Print: `Qobuz credentials not found. Enter credentials to enable Qobuz metadata.`
2. Prompt: `Qobuz email: ` (plain input)
3. Prompt: `Qobuz password: ` (hidden input, no echo)
4. MD5-hash the password
5. Call `extract_qobuz_credentials()` to get app_id + app_secret
6. Call `token_manager.set_qobuz_credentials(app_id, app_secret)`
7. Call `token_manager.login_qobuz(email, password_md5)`
8. If login fails: print error and mark provider as permanently failed
   (set `self._auth_permanently_failed = True`) — do not retry per-request
9. If login succeeds: print `Qobuz: authenticated OK` and continue

If `token_manager` is None (test/offline mode): skip the prompt, fail silently.

## Scope of changes

### 1. `tagslut/metadata/providers/qobuz.py`

Add a `_ensure_credentials(self) -> bool` method:

```python
def _ensure_credentials(self) -> bool:
    """
    Ensure Qobuz credentials are present. Prompts interactively if missing.
    Returns True if credentials are available, False otherwise.
    """
```

Logic:
- If `self.token_manager is None`: return False
- Call `self.token_manager.get_qobuz_app_credentials()` and
  `self.token_manager.ensure_qobuz_token()`
- If both present: return True
- If already `self._auth_permanently_failed`: return False
- Otherwise: run the interactive prompt flow (steps 1–9 above)
- Use `getpass.getpass("Qobuz password: ")` for hidden password input
- Use `input("Qobuz email: ")` for email
- Import `hashlib` and `getpass` inside the method (not at module level)

Call `self._ensure_credentials()` at the top of `fetch_by_id`,
`search_by_isrc`, and `search` — replace the existing
`_get_app_id_and_token` guard blocks with a single:

```python
if not self._ensure_credentials():
    return None  # or []
app_id, user_auth_token = self._get_app_id_and_token()
```

The existing warning logs for missing credentials can be removed —
they are replaced by the interactive prompt.

## What NOT to change

- Do not modify `TokenManager`, `auth.py`, or `qobuz_credential_extractor.py`
- Do not modify any other provider
- Do not modify the enrichment runner or CLI commands
- Do not modify tests — the existing tests use `_StubTokenManager` which
  returns valid credentials so `_ensure_credentials` will return True
  without prompting

## No new tests required

The existing provider tests cover the credential-present path.
The prompt path requires a live terminal and is not unit-testable.

## Commit

```
git add -A
git commit -m "feat(qobuz): prompt for credentials inline when missing during enrichment"
```
