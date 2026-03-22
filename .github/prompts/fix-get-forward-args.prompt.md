# Fix FORWARD_ARGS unbound variable in tools/get

Agent instructions: AGENT.md, CLAUDE.md

Read first: tools/get

---

## Problem

In zsh with `set -u`, an empty array expansion `${FORWARD_ARGS[@]}` is
treated as an unbound variable and causes:

  tools/get: line 226: FORWARD_ARGS[@]: unbound variable

This happens when `tools/get <tidal-url>` is run without extra flags,
leaving FORWARD_ARGS as an empty array.

## Fix

Find this exact line in tools/get (~line 225):

  exec "$TIDDL_WRAPPER" "$URL" "${FORWARD_ARGS[@]}"

Replace with the portable safe expansion:

  exec "$TIDDL_WRAPPER" "$URL" "${FORWARD_ARGS[@]+"${FORWARD_ARGS[@]}"}"

The `+` operator expands the array only when it has elements, and
expands to nothing when empty. This is safe in both bash and zsh.

## Verify

  bash -n tools/get
  tools/get https://tidal.com/album/497862476/u

Should run without the unbound variable error.

## Commit

  git add tools/get
  git commit -m "fix(get): safe FORWARD_ARGS array expansion for zsh compatibility"
  git push

## Constraints

- Touch only the one exec line. No other changes.
- Do not modify any other part of tools/get.
