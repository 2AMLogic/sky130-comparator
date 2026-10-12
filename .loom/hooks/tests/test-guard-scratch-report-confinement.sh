#!/usr/bin/env bash
# Test suite for defaults/hooks/guard-destructive-generic.sh — scratch-report
# write confinement (issue #164).
#
# Usage: ./.loom/hooks/tests/test-guard-scratch-report-confinement.sh
#
# Hermetic regression for the 2026-10-12T04:43:43Z false worktree-write-
# confinement DENY recorded in .loom/logs/guard-decisions.log: a sweep's
# compound command (claim/lease release -> literal /tmp report write via
# quoted heredoc -> comment post -> registry cleanup) was denied because the
# heredoc PROSE token `>=46,` (from "ngspice >=46, xschem 3.4.7") was
# tokenized as a live `>=` redirect cwd-joined into the main checkout.
#
# Root cause: is_interpreter_opener() split a segment like `N=127 ` (the
# space before `&&`) into [N=127, ""], the assignment-prefix skipper consumed
# the only real token, the `j > m` guard missed because the empty SPLIT
# ARTIFACT kept m>0, and the fail-closed tail (base == "") classified the
# whole opener line interpreter-fed — unmasking the quoted-delimiter body.
# Fix: drop true empty-string tokens (split artifacts) before command-word
# reasoning; quoted-empty words (`''`) still fail closed.
#
# Every case feeds command TEXT to the guard as stdin JSON — the command is
# never executed, so the recorded incident command (issue #127 sweep state
# changes, gh mutations) is replayed as inert hook-input data only.
#
# Controls that must KEEP denying (fail-closed preserved by the fix):
#   - real relative/absolute main-checkout writes
#   - a checkout write inside a bash-fed heredoc body (interpreter stays
#     visible)
#   - a checkout write behind an unresolvable command word (`$CMD <<'EOF'`)
#   - a checkout write behind a quoted-empty command word (`'' <<'EOF'`)
#   - a scratch symlink whose target resolves into the checkout (dangling,
#     existing, and chained) — final-component resolution (#164)
# Controls that must KEEP allowing:
#   - literal external scratch (quoted heredoc, assignment-prefixed shape)
#   - writes inside a managed worktree
#   - a scratch symlink into a managed worktree / to outside scratch
# Telemetry: worktree-write-confinement denies record the resolved target.
#
# The hook under test is the installed copy at .loom/ (this is a Loom
# consumer repo; no defaults/ tree). Exit 0 = all pass, 1 = fail.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# LOOM_TEST_HOOK_OVERRIDE: point the suite at a different copy of the guard
# (e.g. the pristine pre-fix copy) to demonstrate the regression live.
SRC_HOOK="${LOOM_TEST_HOOK_OVERRIDE:-}"
[[ -n "$SRC_HOOK" && -r "$SRC_HOOK" ]] || SRC_HOOK="$REPO_ROOT/.loom/hooks/guard-destructive-generic.sh"
[[ -r "$SRC_HOOK" ]] || SRC_HOOK="$REPO_ROOT/defaults/hooks/guard-destructive-generic.sh"
CONFIG_RESOLVER="$REPO_ROOT/.loom/scripts/lib/config-resolver.sh"
[[ -r "$CONFIG_RESOLVER" ]] || CONFIG_RESOLVER="$REPO_ROOT/defaults/scripts/lib/config-resolver.sh"
CANONICAL_PATH_LIB="$REPO_ROOT/.loom/scripts/lib/canonical-path.sh"
[[ -r "$CANONICAL_PATH_LIB" ]] || CANONICAL_PATH_LIB="$REPO_ROOT/defaults/scripts/lib/canonical-path.sh"

PASS=0
FAIL=0
TOTAL=0

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT
REPO="$TMPROOT/repo"
mkdir -p "$REPO"
git init -q "$REPO"
mkdir -p "$REPO/.loom/hooks" "$REPO/.loom/scripts/lib" "$REPO/.loom/worktrees/issue-1"
cp "$SRC_HOOK" "$REPO/.loom/hooks/guard-destructive-generic.sh"
chmod +x "$REPO/.loom/hooks/guard-destructive-generic.sh"
cp "$CONFIG_RESOLVER" "$REPO/.loom/scripts/lib/config-resolver.sh"
cp "$CANONICAL_PATH_LIB" "$REPO/.loom/scripts/lib/canonical-path.sh"
# A managed worktree sentinel makes worktree isolation "in play" for $REPO.
printf '# Loom-managed worktree\n# Branch: feature/issue-1\n' \
    > "$REPO/.loom/worktrees/issue-1/.loom-managed"
HOOK="$REPO/.loom/hooks/guard-destructive-generic.sh"
DECLOG="$TMPROOT/decisions.log"

pass() { PASS=$((PASS + 1)); TOTAL=$((TOTAL + 1)); printf "${GREEN}PASS${NC} %s\n" "$1"; }
fail() { FAIL=$((FAIL + 1)); TOTAL=$((TOTAL + 1)); printf "${RED}FAIL${NC} %s\n" "$1"; }

# Write a command-text case file (quoted heredoc => content is data) and
# echo its path.
case_file() {
    local name="$1"
    mkdir -p "$TMPROOT/cases"
    cat > "$TMPROOT/cases/$name"
    printf '%s' "$TMPROOT/cases/$name"
}

# Run the staged hook with $1 as a case file (command TEXT — data only,
# never executed). Prints "<exit_code>|<stdout>". Extra args are env
# assignments.
run_hook() {
    local cmd_file="$1"; shift
    local exit_code=0 output json
    json=$(jq -n --rawfile cmd "$cmd_file" --arg cwd "$REPO" \
        '{tool_input: {command: $cmd}, cwd: $cwd}')
    output=$(cd "$REPO" && env -u LOOM_FORCE_SCOPE -u LOOM_GUARD_DECISION_LOG \
        -u LOOM_WORKTREE_PATH -u LOOM_WORKTREE_ROOT \
        -u LOOM_GUARD_WORKTREE_ISOLATION "$@" bash "$HOOK" <<< "$json" 2>/dev/null) \
        || exit_code=$?
    printf '%s|%s' "$exit_code" "$output"
}

assert_allow() {
    local desc="$1" result="$2"
    local code="${result%%|*}" out="${result#*|}"
    if [[ "$code" == "0" && -z "$out" ]]; then
        pass "$desc"
    else
        fail "$desc (expected exit 0 + empty output, got exit=$code output=${out:0:160})"
    fi
}

assert_deny() {
    local desc="$1" result="$2"
    local code="${result%%|*}" out="${result#*|}"
    if [[ "$code" != "0" ]]; then
        fail "$desc (expected exit 0 with deny JSON, got NONZERO exit=$code)"
        return
    fi
    local decision
    decision=$(echo "$out" | jq -r '.hookSpecificOutput.permissionDecision // empty' 2>/dev/null || true)
    if [[ "$decision" == "deny" ]]; then
        pass "$desc"
    else
        fail "$desc (expected permissionDecision=deny, got: ${out:0:160})"
    fi
}

echo "=== guard-destructive-generic.sh scratch-report confinement tests (#164) ==="

# ---------------------------------------------------------------------------
# 1. The recorded incident command, verbatim (transcribed from
#    .loom/logs/guard-decisions.log 2026-10-12T04:43:43Z). DATA ONLY: the
#    guard classifies it; nothing here executes it. Pre-fix this was denied
#    with target '<repo>/=46,' — prose from the quoted heredoc body.
# ---------------------------------------------------------------------------
RECORDED=$(case_file recorded <<'RECORDED_CMD'
N=127 && gh issue edit $N --remove-label "loom:building" 2>&1 | tail -2; ./.loom/scripts/sweep-lease-renew.sh release $N 2>&1 | tail -2; cat > /tmp/sweep127.md <<'EOF'
`/loom:sweep` skipped #127 (reason: needs-capability). No Builder was dispatched.

The issue carries `loom:needs-capability`. Its acceptance criteria call for provisioning a compliant execution host (ngspice >=46, xschem 3.4.7, pinned PDK) through the tracked fleet process in `2AMLogic/2am`. That is a fleet-owner action, and the issue itself rules out launching instances, spending money and installing tools on a shared worker. A Builder can't satisfy it from a worktree. The daemon had already parked it twice (`pr-less hold`, `insta-crash quarantine`).

I released the sweep's `loom:building` claim and lease so the claim doesn't go stale. No other labels were changed. The issue should stay `loom:needs-capability` until the provisioning work is linked and a host is verified.
EOF
gh issue comment $N --body-file /tmp/sweep127.md 2>&1 | tail -1; ./.loom/scripts/sweep-run-registry.sh cleanup "sweep-20261012T044332Z-1243109-073b294a"; gh issue view $N --json labels --jq '[.labels[].name]'
RECORDED_CMD
)
assert_allow "recorded incident command allows (was: false deny on '<repo>/=46,')" \
    "$(run_hook "$RECORDED")"

# 2. Minimal artifact shape: assignment-only segment before `&&`, quoted
#    heredoc prose containing `>=46,`. This is the exact tokenizer artifact.
MINIMAL=$(case_file minimal <<'MIN_CMD'
N=127 && cat > SCRATCH_PLACEHOLDER/scratch.md <<'EOF'
host (ngspice >=46, xschem 3.4.7, pinned PDK)
EOF
MIN_CMD
)
sed -i "s|SCRATCH_PLACEHOLDER|$TMPROOT|" "$MINIMAL"
assert_allow "assignment-prefixed quoted heredoc with '>=46,' prose allows" \
    "$(run_hook "$MINIMAL")"

# 3. Same prose, no assignment prefix (control for the masking itself).
PLAIN=$(case_file plain <<'PLAIN_CMD'
cat > SCRATCH_PLACEHOLDER/scratch2.md <<'EOF'
host (ngspice >=46, xschem 3.4.7, pinned PDK)
EOF
PLAIN_CMD
)
sed -i "s|SCRATCH_PLACEHOLDER|$TMPROOT|" "$PLAIN"
assert_allow "plain quoted heredoc with '>=46,' prose allows" \
    "$(run_hook "$PLAIN")"

# 4. Real main-checkout writes must STILL deny (relative and absolute).
REL=$(case_file rel <<'REL_CMD'
echo x > repofile.txt
REL_CMD
)
assert_deny "relative main-checkout write denies" "$(run_hook "$REL")"

ABS=$(case_file abs <<ABS_CMD
echo x > $REPO/repofile.txt
ABS_CMD
)
assert_deny "absolute main-checkout write denies" "$(run_hook "$ABS")"

# 5. Writes inside a managed worktree allow (isolation active).
WT=$(case_file wt <<WT_CMD
echo x > $REPO/.loom/worktrees/issue-1/note.txt
WT_CMD
)
assert_allow "managed-worktree write allows" "$(run_hook "$WT")"

# 6. Interpreter-fed heredoc bodies stay VISIBLE: a checkout write inside a
#    bash-fed body denies (the fix must not over-mask).
INTERP=$(case_file interp <<'INT_CMD'
bash <<'EOF'
echo pwned > repofile.txt
EOF
INT_CMD
)
assert_deny "checkout write inside bash-fed heredoc body denies" "$(run_hook "$INTERP")"

# 7. Unresolvable command word keeps the fail-closed tail.
UNRES=$(case_file unres <<'UN_CMD'
$CMD <<'EOF'
echo pwned > repofile.txt
EOF
UN_CMD
)
assert_deny "checkout write behind \$CMD opener denies (fail-closed tail)" "$(run_hook "$UNRES")"

# 8. Quoted-empty command word (`''`) reduces to an empty basename but is a
#    NON-empty token: the artifact filter must not swallow it.
QEMPTY=$(case_file qempty <<'QE_CMD'
'' <<'EOF'
echo pwned > repofile.txt
EOF
QE_CMD
)
assert_deny "checkout write behind '' opener denies (fail-closed tail)" "$(run_hook "$QEMPTY")"

# 9. Scratch symlinks into the checkout must not bypass confinement
#    (final-component resolution; physical_abs_path only resolves ancestors).
ln -s "$REPO/dangling-target.txt" "$TMPROOT/link-dangling"
: > "$REPO/existing.txt"
ln -s "$REPO/existing.txt" "$TMPROOT/link-existing"
ln -s "$TMPROOT/link-dangling" "$TMPROOT/link-chain"

DANGLE=$(case_file dangle <<D_CMD
echo x > $TMPROOT/link-dangling
D_CMD
)
assert_deny "scratch symlink -> dangling checkout file denies" "$(run_hook "$DANGLE")"

EXISTING=$(case_file existing <<E_CMD
echo x > $TMPROOT/link-existing
E_CMD
)
assert_deny "scratch symlink -> existing checkout file denies" "$(run_hook "$EXISTING")"

CHAIN=$(case_file chain <<C_CMD
echo x > $TMPROOT/link-chain
C_CMD
)
assert_deny "two-hop scratch symlink chain -> checkout denies" "$(run_hook "$CHAIN")"

# 10. Symlinks NOT into the checkout keep allowing.
ln -s "$REPO/.loom/worktrees/issue-1/wt-file.txt" "$TMPROOT/link-worktree"
LNWT=$(case_file lnwt <<LW_CMD
echo x > $TMPROOT/link-worktree
LW_CMD
)
assert_allow "scratch symlink into managed worktree allows" "$(run_hook "$LNWT")"

ln -s "$TMPROOT/pure-scratch.txt" "$TMPROOT/link-pure-scratch.txt"
LNSCRATCH=$(case_file lnscratch <<LS_CMD
echo x > $TMPROOT/link-pure-scratch.txt
LS_CMD
)
assert_allow "scratch symlink to outside scratch allows" "$(run_hook "$LNSCRATCH")"

# 11. Telemetry: a worktree-write-confinement deny records the resolved
#     target; an allow records nothing.
rm -f "$DECLOG"
DENYRUN=$(run_hook "$ABS" LOOM_GUARD_DECISION_LOG=1 \
    "LOOM_GUARD_DECISION_LOG_FILE=$DECLOG")
assert_deny "telemetry probe run denies" "$DENYRUN"
if jq -e --arg t "$REPO/repofile.txt" \
        'select(.pattern=="worktree-write-confinement" and .target==$t)' \
        "$DECLOG" >/dev/null 2>&1; then
    pass "deny telemetry records resolved target"
else
    fail "deny telemetry records resolved target (log: $(cat "$DECLOG" 2>/dev/null))"
fi
ALLOWRUN=$(run_hook "$PLAIN" LOOM_GUARD_DECISION_LOG=1 \
    "LOOM_GUARD_DECISION_LOG_FILE=$DECLOG")
assert_allow "telemetry allow-probe run allows" "$ALLOWRUN"
if [[ $(wc -l < "$DECLOG" 2>/dev/null || echo 0) -eq 1 ]]; then
    pass "allow produces no telemetry record"
else
    fail "allow produced an extra telemetry record ($(wc -l < "$DECLOG" 2>/dev/null) lines)"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed (of $TOTAL) ==="
if [[ "$FAIL" -gt 0 ]]; then
    exit 1
fi
exit 0
