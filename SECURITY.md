<!-- Status: Active document. Synced 2026-03-09 after recent code/doc review. Historical or superseded material belongs in docs/archive/. -->

# Security Policy

## Supported Surface

Security fixes are applied on the active development line only.

| Surface | Supported |
| --- | --- |
| Current `dev` branch / current repository head | Yes |
| Historical tags, archived docs, and `legacy/` code | No |
| Superseded workflow notes under `docs/archive/` | No |

This repository contains operational tooling, local-file workflows, provider credentials, and music-library metadata. Treat path disclosure, secret leakage, unsafe move behavior, and arbitrary file-write issues as security-relevant.

## Reporting a Vulnerability

Do not open a public issue with exploit details.

Use a private maintainer contact path if you already have one. If GitHub private security reporting is enabled for the repository, use that. If you only have public GitHub access, open a minimal public issue that requests a private contact route without posting the exploit, proof of concept, or sensitive logs.

Include:

- affected path or command
- concise impact statement
- reproduction steps
- required environment or flags
- whether the issue can overwrite, exfiltrate, or destroy local data
- any proposed mitigation if you already have one

## Handling Expectations

- Initial acknowledgement target: within 5 business days
- Triage focus: data loss, unsafe file moves, credential exposure, arbitrary command execution, unsafe path handling
- Fixes land on `dev` first

## Scope Notes

Examples of issues that are in scope:

- unsafe path handling during move or transcode workflows
- unintended overwrite or destructive file operations
- provider-token leakage in logs or artifacts
- command injection in wrappers or helper scripts
- local web UI behavior that exposes sensitive filesystem data unexpectedly

Examples that are usually out of scope unless they chain into a real exploit:

- stale historical docs in `docs/archive/`
- breakage in archived `legacy/` code that is not part of the active surface
- theoretical issues without a plausible local attack path

## Secrets and Local Safety

- Never commit provider tokens, cookies, `.env` secrets, or private URLs.
- Sanitize paths and tokens before sharing logs.
- Prefer dry-run or plan mode before executing file-move workflows against a real library.
