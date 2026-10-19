#!/usr/bin/env bash
# PreToolUse hook (Bash): refuses `git commit` / `git push` when the change holds something that looks
# like a secret. Exit 2 blocks the tool call and shows the reason to Claude.
set -uo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null)"

case "$cmd" in
    *"git commit"*|*"git push"*) ;;
    *) exit 0 ;;
esac

cwd="$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("cwd",""))' 2>/dev/null)"
if [ -n "$cwd" ]; then cd "$cwd" 2>/dev/null || true; fi

# The command may `cd` into a worktree first; follow it so we scan the right repository.
target="$(printf '%s' "$cmd" | sed -nE 's/.*cd[[:space:]]+([^&;]+)[[:space:]]*&&.*/\1/p' | head -1 | sed "s/^[\"']//; s/[\"']$//")"
if [ -n "$target" ]; then cd "${target/#\~/$HOME}" 2>/dev/null || true; fi

git rev-parse --git-dir >/dev/null 2>&1 || exit 0

if [[ "$cmd" == *"git push"* ]]; then
    upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || echo origin/main)"
    diff="$(git diff "$upstream"...HEAD 2>/dev/null)"
else
    # `git commit -a` / `-am` commits unstaged tracked changes too.
    if [[ "$cmd" =~ commit[[:space:]]+(-[a-zA-Z]*a|--all) ]]; then
        diff="$(git diff HEAD 2>/dev/null)"
    else
        diff="$(git diff --cached 2>/dev/null)"
    fi
fi

# Files that must never be committed, whatever their content.
files="$(printf '%s\n' "$diff" | sed -nE 's#^\+\+\+ b/(.*)#\1#p')"
bad_files="$(printf '%s\n' "$files" | grep -E '(^|/)\.env$|(^|/)\.env\.[^e][^/]*$|(^|/)auth\.json$|\.pem$|\.key$|(^|/)id_(rsa|ed25519)$' | grep -v -E '\.env\.example$|stage\.env\.example$' || true)"

added="$(printf '%s\n' "$diff" | grep -E '^\+[^+]' || true)"
patterns='(AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,}|sk-ant-[A-Za-z0-9_-]{20,}|sk_live_[A-Za-z0-9]{20,}|rk_live_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|APP_KEY=base64:[A-Za-z0-9+/=]{40,}|"password"[[:space:]]*:[[:space:]]*"[^"]{8,}"|https?://[^/[:space:]:@]+:[^/[:space:]@]{6,}@)'
hits="$(printf '%s\n' "$added" | grep -oE "$patterns" | head -5 || true)"

if [ -n "$bad_files" ] || [ -n "$hits" ]; then
    {
        echo "block-secrets: refused — the change looks like it contains a secret."
        [ -n "$bad_files" ] && printf 'Files that must not be committed:\n%s\n' "$bad_files"
        [ -n "$hits" ] && printf 'Matched patterns (first chars only):\n%s\n' "$(printf '%s\n' "$hits" | cut -c1-12 | sed 's/$/…/')"
        echo "Remove it from the change (secrets live in the server .env or GitHub secrets), then retry."
    } >&2
    exit 2
fi
exit 0
