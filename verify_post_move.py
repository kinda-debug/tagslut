#!/usr/bin/env bash
# Shim: forward to scripts/verify_post_move.py
exec python3 "$(dirname "$0")/scripts/verify_post_move.py" "$@"
#!/usr/bin/env python3
#!/usr/bin/env bash
# Root shim: forward to canonical script in scripts/
exec python3 "$(dirname "$0")/scripts/verify_post_move.py" "$@"