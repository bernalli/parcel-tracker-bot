#!/bin/bash
# tree-scan.sh — a companion CI check to any local pre-push guard that only
# scans lines added by new commits.
#
# A local pre-push guard that diffs added lines only protects the machine
# where it is installed, and only catches what changed in the commits being
# pushed. This script scans the WHOLE TRACKED TREE of the checked-out
# commit instead, so the guarantee holds regardless of which machine or
# host pushed, and regardless of when a line was first added.
#
# The five term lists are themselves the secret (hostnames, personal paths,
# handles, forbidden directory/file names): they NEVER appear in this file.
# They arrive as environment variables (repository secrets): LEAK_WORD_TERMS,
# LEAK_PHRASE_TERMS, LEAK_NAME_TERMS, LEAK_PII_TERMS, LEAK_PATH_TERMS. The
# two allowlists below (ATTRIBUTION_PATHS, PII_ALLOW) are publishable —
# generic patterns, no secret content — and stay hardcoded in this file.
#
# This script NEVER prints the matching line's text, nor the term that
# matched: only "path:line" (for content) or the bare path (for the two
# path-based stages), plus per-stage counts. GitHub's secret masking only
# redacts the EXACT registered secret value, never a fragment of it printed
# in surrounding context — so printing content would defeat masking.
#
# Stages:
#   PATH   — tracked paths matching LEAK_PATH_TERMS: the path itself is the
#            finding (directories/files that must not exist in a public
#            repo at all — internal tooling directories, internal
#            roadmap/journal files, and the like). Files hit by PATH are
#            excluded from the four content stages below, so a hit is
#            reported once, under PATH. LEAK_PATH_TERMS is secret exactly
#            like the other four: it names specific internal paths, not a
#            generic best-practice blocklist.
#   WORD   — LEAK_WORD_TERMS, whole-word match (grep -w), extended regex.
#   PHRASE — LEAK_PHRASE_TERMS, extended regex, substring match allowed.
#   NAME   — LEAK_NAME_TERMS, whole-word match, blocked everywhere except
#            files whose path matches ATTRIBUTION_PATHS.
#   PII    — LEAK_PII_TERMS, extended regex, blocked everywhere except
#            files whose path matches ATTRIBUTION_PATHS (like NAME), and
#            excluding any line that also matches PII_ALLOW.
#   PATH-TERMS — the other four secret lists (WORD/NAME/PHRASE/PII) applied
#            to tracked PATH NAMES rather than content, so a hostname or
#            handle that shows up as a directory/file name is caught too.
#            WORD/NAME are whole-word like their content counterparts; PII
#            hits are filtered through PII_ALLOW exactly as in the PII
#            stage. This is a DIFFERENT stage from PATH above: PATH matches
#            LEAK_PATH_TERMS, PATH-TERMS matches the other four secrets —
#            both against path names, neither against file content.
#
# LEAK_CONTENT_STAGES (env var, "all" or "skip", default "all" when unset):
# gates EVERY stage above — PATH, PATH-TERMS, WORD, PHRASE, NAME, PII —
# because every one of them now depends on a secret. This exists because a
# pull_request from a fork never receives repository secrets (see the
# workflow), and this script must never read that absence as "the lists
# happen to be empty": an empty term list would make `grep -E ""` match
# every line (or every path), turning a missing secret into a false
# positive on everything, not a safe no-op. On a fork PR nothing can be
# measured against any of the five lists, so nothing runs, and the script
# says so explicitly instead of reporting a false "clean". The workflow
# sets this explicitly per event; a value other than "all" or "skip" is
# always exit 3, never silently treated as either.
#
# Exit codes:
#   0 — clean for whatever was measured. In "all" mode: "MEASURED: N tracked
#       files, M subjected to the 4 content stages" with M > 0. In
#       "skip" mode: "MEASURED: N tracked files, 0 subjected to the stages"
#       — nothing ran at all, and the "0" is what tells the two apart; see
#       the LEAK_CONTENT_STAGES paragraph above for why that is the only
#       honest thing to print when no secret is available.
#   1 — findings in at least one stage that actually ran. Per-stage counts
#       and path:line (or bare path) only.
#   3 — precondition absent: LEAK_CONTENT_STAGES itself unrecognized; in
#       "all" mode, a required secret env var is empty/unset; the ref has
#       no commits; the tree has zero tracked files; the four content
#       stages would run over zero files; LEAK_EXCLUDE_PATHS is not a valid
#       extended regex (plain grep rc > 1); or an internal git-grep call
#       could not be measured (exit code neither 0 nor 1). Never 0, never 1.
#
# Pattern MATCHING happens only through grep -E (via `git grep -E`), never
# through awk's regex engine: awk here (mawk, in this environment) does NOT
# implement \b as a GNU-grep word boundary — measured: `printf
# 'foo@example.com\n' | awk '/\bexample\b/'` does not match what `grep -E`
# matches on the same input, and a PII term anchored on \b depends on that
# exact semantic. awk/tr are used only for NUL-delimited field splitting of
# `git grep -z` records and for exact-string set lookups (never a `~`/regex
# test). No `git grep -z` output is ever passed through bash command
# substitution ($(...)): bash silently drops embedded NUL bytes there
# ("ignored null byte in input", measured on this machine) and reassembles
# path/line/content into one corrupted field. NUL bytes are converted to
# TAB inside an unbroken pipe (git grep | tr), and only the TAB-safe result
# ever touches a bash variable.
#
# PERFORMANCE / large-blob exclusion: measured on real repositories, the
# unrestricted PII_TERMS pattern against a handful of vendored/generated
# blobs (a multi-MB geodata TSV in one repo, several 50-120KB-single-line
# deployment-artifact JSON files in another) did not finish in 60s — not a
# bug in this script, the regex engine's automaton grows with each
# bounded-repetition alternative in a term list this size, and that cost is
# paid per byte scanned. Files above LEAK_SCAN_CI_MAX_BYTES (default 51200
# = 50 KiB) are excluded from the four CONTENT stages only — the PATH stage
# still sees every tracked path regardless of size. This is a deliberate,
# disclosed trade-off, not a silent loophole: the count of size-excluded
# files is always printed.
#
# Usage: tree-scan.sh [TARGET_REF]
#   TARGET_REF defaults to HEAD (the checked-out commit). The CI workflow
#   always passes github.sha explicitly (see tree-scan.yml) — the same
#   commit actions/checkout already put on disk (the pushed commit for
#   `push`, the PR merge-test commit for `pull_request`, same-repo or
#   fork). TARGET_REF is spliced into a sed/awk regex to strip the
#   "TARGET_REF:" prefix git grep puts on every record, so it MUST be either
#   the literal string HEAD or a raw commit SHA (hex only, no regex
#   metacharacters) — never a branch name or anything else user-controlled
#   as free text.
#
# Optional env var LEAK_EXCLUDE_PATHS (extended regex over tracked paths,
# empty/unset = no exclusion): excludes matching paths from the FOUR content
# stages (WORD/PHRASE/NAME/PII) only — NEVER from the PATH stage, which
# always sees every tracked path regardless of this variable. This is meant
# to come from a GitHub Actions repository/org *variable* (vars.*), not a
# secret: a path prefix like "^lib/" for a vendored-dependency tree is not
# sensitive on its own. Rationale: a baseline scan can show vendored
# libraries under a lib/ tree triggering PII findings on upstream
# maintainer contact addresses that are not the repo owner's content at all.
#
# KNOWN GAP, accepted, not fixed here: this script does not replicate a
# stage some local pre-push guards have for tooling references inside
# PUBLIC .gitignore files (e.g. an internal tool's directory committed as
# an ignore entry rather than as a tracked path). A local guard that has
# that stage still catches it on any machine where it is installed; this CI
# check does not. If a .gitignore ever needs that coverage from the CI side
# too, it is a separate stage to add later, not something the stages below
# happen to catch as a side effect.
#
# KNOWN GAP #2, deliberate: `git grep -I` skips any blob git considers binary
# (a NUL byte in the first 8000), so a term inside a PDF, an image, or a
# minified bundle is invisible to the four content stages. The PATH and
# PATH-TERMS stages still see such a file's path. Pinned by the bench case
# "binary-file-ignored", which asserts this is the intended behaviour.

set -u
set -o pipefail

# Pathspecs (`-- .` and `:(exclude,literal)<path>`) are relative to the CWD,
# while paths produced by `git ls-tree` are relative to the repo ROOT: run
# from a subdirectory, the check would silently lose ALL exclusions. We move
# to the root once, explicitly.
_toplevel="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$_toplevel" ]; then
    echo "PRECONDITION MISSING: not inside a git repository" >&2
    exit 3
fi
cd "$_toplevel" || exit 3
unset _toplevel

# ---------------------------------------------------------------------------
# LEAK_CONTENT_STAGES gates every secret-dependent stage (see header). Read
# and validated FIRST, before the secret precondition below, so an
# unrecognized value is always exit 3 regardless of what the five secrets
# happen to be — never silently coerced to "all" or "skip".
# ---------------------------------------------------------------------------
CONTENT_STAGES="${LEAK_CONTENT_STAGES:-all}"
case "$CONTENT_STAGES" in
    all|skip) ;;
    *)
        echo "PRECONDITION MISSING: LEAK_CONTENT_STAGES=$CONTENT_STAGES not recognized (expected: all, skip)" >&2
        exit 3
        ;;
esac

# ---------------------------------------------------------------------------
# Precondition: the five secret term lists — only in "all" mode. In "skip"
# mode they are allowed to be absent (a fork PR never has them), and every
# stage that would use one of them does not run at all (enforced further
# below — not by leaving these variables empty and hoping nothing
# downstream notices).
# ---------------------------------------------------------------------------
if [ "$CONTENT_STAGES" = "all" ]; then
    for _v in LEAK_WORD_TERMS LEAK_PHRASE_TERMS LEAK_NAME_TERMS LEAK_PII_TERMS LEAK_PATH_TERMS; do
        eval "_val=\${$_v:-}"
        if [ -z "$_val" ]; then
            echo "PRECONDITION MISSING: $_v" >&2
            exit 3
        fi
    done
    unset _v _val
fi

WORD_TERMS="${LEAK_WORD_TERMS:-}"
PHRASE_TERMS="${LEAK_PHRASE_TERMS:-}"
NAME_TERMS="${LEAK_NAME_TERMS:-}"
PII_TERMS="${LEAK_PII_TERMS:-}"
PATH_TERMS="${LEAK_PATH_TERMS:-}"
MAX_BYTES="${LEAK_SCAN_CI_MAX_BYTES:-51200}"
EXCLUDE_PATHS="${LEAK_EXCLUDE_PATHS:-}"
TARGET_REF="${1:-HEAD}"
# TARGET_REF is spliced into a sed prefix-strip below without further
# escaping (see the usage note in the header): it must be exactly "HEAD" or
# a hex commit SHA, never anything containing regex metacharacters.
if [ "$TARGET_REF" != "HEAD" ]; then
    case "$TARGET_REF" in
        *[!0-9a-fA-F]*)
            echo "tree-scan: TARGET_REF must be HEAD or a hex SHA, received: $TARGET_REF" >&2
            exit 3
            ;;
    esac
fi

# ---------------------------------------------------------------------------
# Publishable allowlists — generic path/format patterns, no secret content.
# ---------------------------------------------------------------------------
ATTRIBUTION_PATHS='^AUTHORS$|^NOTICE$|^LICENSE|^CITATION|^README\.md$|^pyproject\.toml$|(^|/)package\.json$|^ietf/|(^|/)CONTRIBUTING\.md$|^\.mailmap$|^PATENTS\.md$'
PII_ALLOW='192\.0\.2\.|198\.51\.100\.|203\.0\.113\.|2001:db8|127\.0\.0\.1|0\.0\.0\.0|255\.255\.255|(^|[^:0-9a-f])::1([^0-9a-f:]|$)|@([A-Za-z0-9-]+\.)*[Ee]xample(\.[A-Za-z]{2,})?|@[Ee]x\.[A-Za-z]|@([Tt]est|[Ii]nvalid|[Ll]ocalhost)\b|@[A-Za-z0-9-]*\.?([Ee]xample|[Ii]nvalid|[Tt]est)\b|@[A-Za-z]\.[A-Za-z]{2,4}\b|[0-9]+\+bernalli@users\.noreply\.github\.com|noreply@github\.com|@pytest\.|@dataclass|@property|@staticmethod|@classmethod|@abstractmethod|LL@li\.org'

fail=0
word_count=0
phrase_count=0
name_count=0
pii_count=0
path_count=0

# ---------------------------------------------------------------------------
# HEAD must exist and have tracked files.
# ---------------------------------------------------------------------------
if ! git rev-parse -q --verify "$TARGET_REF" >/dev/null 2>&1; then
    echo "PRECONDITION MISSING: no commits on $TARGET_REF" >&2
    exit 3
fi

tracked_file="$(mktemp)"
large_file="$(mktemp)"
excludepaths_hits="$(mktemp)"
content_excl="$(mktemp)"
name_excl="$(mktemp)"
word_raw="$(mktemp)"; word_report="$(mktemp)"
phrase_raw="$(mktemp)"; phrase_report="$(mktemp)"
name_raw="$(mktemp)"; name_report="$(mktemp)"
pii_raw="$(mktemp)"; pii_report="$(mktemp)"
path_hits="$(mktemp)"
trap 'rm -f "$tracked_file" "$large_file" "$excludepaths_hits" "$content_excl" "$name_excl" \
         "$word_raw" "$word_report" "$phrase_raw" "$phrase_report" \
         "$name_raw" "$name_report" "$pii_raw" "$pii_report" "$path_hits" \
         "${pathterm_hits:-}" "${pathterm_tmp:-}"' EXIT

count_nul() { tr -dc '\0' < "$1" | wc -c | tr -d ' '; }

git ls-tree -r -z --name-only "$TARGET_REF" > "$tracked_file" 2>/dev/null
files_scanned="$(count_nul "$tracked_file")"
if [ -z "$files_scanned" ] || [ "$files_scanned" -eq 0 ]; then
    echo "PRECONDITION MISSING: zero tracked files in $TARGET_REF" >&2
    exit 3
fi

# ---------------------------------------------------------------------------
# LEAK_CONTENT_STAGES=skip: nothing below this point can run. A pull_request
# from a fork never gets any of the five secret term lists (see the
# workflow) — deliberately, to avoid turning this check into a membership
# oracle over its own secrets: a PR author who fully controls the checked-
# out content could otherwise add one candidate string per push and read
# the public log to learn whether THAT stage matched, i.e. whether the
# candidate is IN one of the five lists. PATH_TERMS is a secret exactly
# like the other four now, so even the one stage that used to be safe to
# run without any trust in the PR author (a public path blocklist) cannot
# run either: with it empty, an unconditional `grep -E ""` would match
# every path — a silent false-positive-on-everything, not a safe no-op.
# Only the tracked-file count above required no secret, and it is already
# printed below.
# ---------------------------------------------------------------------------
if [ "$CONTENT_STAGES" = "skip" ]; then
    echo "tree-scan: NOT MEASURED — LEAK_CONTENT_STAGES=skip (pull request from a fork: the lists are not available to this job by design); full coverage runs on the merge push" >&2
    echo "MEASURED: $files_scanned tracked files, 0 subjected to the stages"
    exit 0
fi

# ---------------------------------------------------------------------------
# STAGE: PATH — tracked paths matching LEAK_PATH_TERMS. The path is the
# finding.
# ---------------------------------------------------------------------------
grep -z -E "$PATH_TERMS" "$tracked_file" > "$path_hits" || true
path_count="$(count_nul "$path_hits")"
if [ "$path_count" -gt 0 ]; then
    fail=1
    echo "tree-scan: PATH STAGE — $path_count paths that must not exist in a public repo:" >&2
    tr '\0' '\n' < "$path_hits" | sed 's/^/  /' >&2
fi

# ---------------------------------------------------------------------------
# STAGE: PATH-TERMS — the four content-secret lists applied to the tracked
# PATHS themselves, not only to file CONTENT. A local guard that scans added
# lines typically also scans path names; without this stage a hostname or
# handle that shows up as a DIRECTORY or FILE NAME (infra/<host>/config.yml)
# is invisible to this check. WORD/NAME are whole-word like their content
# counterparts; PII hits are filtered through PII_ALLOW exactly as in the
# PII stage.
# ---------------------------------------------------------------------------
pathterm_hits="$(mktemp)"; pathterm_tmp="$(mktemp)"
grep -z -w -E "$WORD_TERMS|$NAME_TERMS" "$tracked_file" > "$pathterm_tmp" || true
grep -z -E "$PHRASE_TERMS" "$tracked_file" >> "$pathterm_tmp" || true
grep -z -E "$PII_TERMS" "$tracked_file" 2>/dev/null \
    | grep -z -v -E "$PII_ALLOW" >> "$pathterm_tmp" || true
sort -z -u "$pathterm_tmp" > "$pathterm_hits"
pathterm_count="$(count_nul "$pathterm_hits")"
rm -f "$pathterm_tmp"
if [ "$pathterm_count" -gt 0 ]; then
    fail=1
    echo "tree-scan: PATH-TERMS STAGE — $pathterm_count paths containing a watched term:" >&2
    tr '\0' '\n' < "$pathterm_hits" | sed 's/^/  /' >&2
fi

# ---------------------------------------------------------------------------
# Files over MAX_BYTES are excluded from the content stages only (see header
# note on performance). Reported as a plain diagnostic, never a finding.
# ---------------------------------------------------------------------------
while IFS= read -r -d '' _rec; do
    _meta="${_rec%%$'\t'*}"
    _size="${_meta##* }"
    _lpath="${_rec#*$'\t'}"
    case "$_size" in ''|*[!0-9]*) _size=0 ;; esac
    if [ "$_size" -gt "$MAX_BYTES" ]; then printf '%s\0' "$_lpath"; fi
done < <(git ls-tree -r -l -z "$TARGET_REF" 2>/dev/null) > "$large_file"
unset _rec _meta _size _lpath
large_count="$(count_nul "$large_file")"
echo "tree-scan: $large_count files > $MAX_BYTES bytes excluded from the 4 content stages by size (see the PERFORMANCE note at the top of the script); still covered by the PATH stage for their path" >&2

# ---------------------------------------------------------------------------
# LEAK_EXCLUDE_PATHS (optional, publishable — see header note): same
# treatment as the size exclusion above, on a SEPARATE line and a SEPARATE
# count, and — like the size exclusion — it NEVER touches path_hits/the PATH
# stage, only what the four content stages get to scan. An EMPTY pattern
# would make `grep -E ''` match every line, so an unset/empty variable is
# handled as "match nothing" explicitly rather than by accident.
# ---------------------------------------------------------------------------
if [ -n "$EXCLUDE_PATHS" ]; then
    grep -z -E "$EXCLUDE_PATHS" "$tracked_file" > "$excludepaths_hits"
    _eg=$?
    if [ "$_eg" -gt 1 ]; then
        echo "PRECONDITION MISSING: LEAK_EXCLUDE_PATHS is not a valid extended regex (grep rc=$_eg); the exclusion would not have been applied and the log would say '0 files excluded'" >&2
        exit 3
    fi
    unset _eg
else
    : > "$excludepaths_hits"
fi
excludepaths_count="$(count_nul "$excludepaths_hits")"
echo "tree-scan: $excludepaths_count files excluded from the 4 content stages by LEAK_EXCLUDE_PATHS (never from the PATH stage)" >&2

sort -z -u "$path_hits" "$large_file" "$excludepaths_hits" > "$content_excl"
grep -z -E "$ATTRIBUTION_PATHS" "$tracked_file" > "${tracked_file}.attrib" || true
sort -z -u "$content_excl" "${tracked_file}.attrib" > "$name_excl"
rm -f "${tracked_file}.attrib"

# Build `:(exclude,literal)<path>` pathspec arguments so `git grep` itself
# never has to scan the excluded blobs — the cost we're avoiding happens
# INSIDE git grep's own matching, so a post-hoc filter on its output would
# not help; the exclusion has to reach the `git grep` invocation itself.
build_exclude_args() {
    local file="$1" name="$2" line
    local -n arr_ref="$name"
    arr_ref=()
    while IFS= read -r -d '' line; do
        [ -n "$line" ] || continue
        arr_ref+=(":(exclude,literal)$line")
    done < "$file"
}
content_scanned=$(( files_scanned - $(count_nul "$content_excl") ))
if [ "$content_scanned" -le 0 ]; then
    echo "PRECONDITION MISSING: zero files reach the 4 content stages (tracked=$files_scanned, excluded: PATH=$path_count size=$large_count LEAK_EXCLUDE_PATHS=$excludepaths_count). The 4 stages measured nothing: this is not a clean tree." >&2
    exit 3
fi

build_exclude_args "$content_excl" CONTENT_EXCLUDE_ARGS
build_exclude_args "$name_excl" NAME_EXCLUDE_ARGS

# ---------------------------------------------------------------------------
# Runs `git grep -I -z -n -E [-w] -e "$pattern" HEAD -- . <excludes>`,
# streams straight through `tr` (NUL -> TAB) and `sed` (strip the leading
# "HEAD:" tree prefix) into $outfile with no bash variable ever holding a
# NUL byte, and checks git grep's OWN exit code via PIPESTATUS[0] (0 =
# matches, 1 = no matches — both legitimate; anything else is an unmeasured
# error and aborts the run rather than being read as "clean"). $3 is the
# name of a bash array variable (by reference) holding extra pathspec args.
# ---------------------------------------------------------------------------
git_grep_records() {
    local wflag="$1" pattern="$2" outfile="$3" exclude_arr_name="$4" rc
    local -n exclude_ref="$exclude_arr_name"
    if [ "$wflag" = "-w" ]; then
        git grep -I -z -n -w -E -e "$pattern" "$TARGET_REF" -- . "${exclude_ref[@]}" 2>/dev/null \
            | tr '\0' '\t' | sed "s/^$TARGET_REF://" > "$outfile"
    else
        git grep -I -z -n -E -e "$pattern" "$TARGET_REF" -- . "${exclude_ref[@]}" 2>/dev/null \
            | tr '\0' '\t' | sed "s/^$TARGET_REF://" > "$outfile"
    fi
    rc="${PIPESTATUS[0]}"
    if [ "$rc" -gt 1 ]; then
        echo "tree-scan: internal error in git grep (rc=$rc), unable to measure" >&2
        exit 3
    fi
    return 0
}

# ---------------------------------------------------------------------------
# STAGE: WORD
# ---------------------------------------------------------------------------
git_grep_records -w "$WORD_TERMS" "$word_raw" CONTENT_EXCLUDE_ARGS
awk -F'\t' '{print $1":"$2}' "$word_raw" > "$word_report"
word_count="$(wc -l < "$word_report" | tr -d ' ')"
if [ "$word_count" -gt 0 ]; then
    fail=1
    echo "tree-scan: WORD STAGE — $word_count occurrences:" >&2
    sed 's/^/  /' "$word_report" >&2
fi

# ---------------------------------------------------------------------------
# STAGE: PHRASE
# ---------------------------------------------------------------------------
git_grep_records "" "$PHRASE_TERMS" "$phrase_raw" CONTENT_EXCLUDE_ARGS
awk -F'\t' '{print $1":"$2}' "$phrase_raw" > "$phrase_report"
phrase_count="$(wc -l < "$phrase_report" | tr -d ' ')"
if [ "$phrase_count" -gt 0 ]; then
    fail=1
    echo "tree-scan: PHRASE STAGE — $phrase_count occurrences:" >&2
    sed 's/^/  /' "$phrase_report" >&2
fi

# ---------------------------------------------------------------------------
# STAGE: NAME — blocked everywhere except ATTRIBUTION_PATHS (excluded above,
# from the git grep call itself: no need to also filter the output).
# ---------------------------------------------------------------------------
git_grep_records -w "$NAME_TERMS" "$name_raw" NAME_EXCLUDE_ARGS
awk -F'\t' '{print $1":"$2}' "$name_raw" > "$name_report"
name_count="$(wc -l < "$name_report" | tr -d ' ')"
if [ "$name_count" -gt 0 ]; then
    fail=1
    echo "tree-scan: NAME STAGE — $name_count occurrences outside an attribution surface:" >&2
    sed 's/^/  /' "$name_report" >&2
fi

# ---------------------------------------------------------------------------
# STAGE: PII — like NAME, blocked everywhere except ATTRIBUTION_PATHS
# (excluded above, from the git grep call itself, via NAME_EXCLUDE_ARGS: a
# personal email address is exactly the kind of thing a README/AUTHORS/
# NOTICE surface legitimately publishes on purpose). On top of that, it
# excludes lines also matching PII_ALLOW. This needs the content field, so
# records are filtered with a vectorised grep -E / -Ev pass rather than a
# per-line loop (both are the real grep engine, never awk's `~`).
# ---------------------------------------------------------------------------
git_grep_records "" "$PII_TERMS" "$pii_raw" NAME_EXCLUDE_ARGS
# Isolate the content field (never the path or line number) for the
# PII_ALLOW test: extract content and path:line into two files that stay
# row-aligned by construction (same input, same order), find which content
# ROWS match PII_ALLOW via a real grep -nE (never awk ~), and exclude those
# row numbers from the path:line file with an awk NR join — never testing
# PII_ALLOW against anything but the content itself.
awk -F'\t' '{ c=$0; sub(/^[^\t]*\t[^\t]*\t/, "", c); print c }' "$pii_raw" > "${pii_raw}.content"
awk -F'\t' '{print $1":"$2}' "$pii_raw" > "${pii_raw}.pathline"
grep -nE "$PII_ALLOW" "${pii_raw}.content" 2>/dev/null | cut -d: -f1 | sort -un > "${pii_raw}.allow_lines"
# The classic "NR==FNR{arr[$0]=1;next}" two-file join misfires when the
# FIRST file (allow_lines) is EMPTY: FNR resets per file but NR is
# cumulative, so with a 0-line file1, NR and FNR stay in LOCKSTEP for the
# entire second file too (both start at 1 on file2's first line and
# increment together forever after) — so NR==FNR is true for every single
# line of file2, and the whole file is swallowed into the exclusion branch,
# not just its first line. Measured twice while building this script: the
# test bench went green with zero findings on content that plainly matched,
# and a real baseline scan reported a clean tree while genuine
# gettext-boilerplate matches were silently swallowed.
# "0" is never a valid FNR (awk line numbers start at 1), so appending it
# guarantees file1 is never empty without ever excluding a real record.
printf '0\n' >> "${pii_raw}.allow_lines"
awk 'NR==FNR{excl[$0]=1;next} !(FNR in excl)' "${pii_raw}.allow_lines" "${pii_raw}.pathline" > "$pii_report"
rm -f "${pii_raw}.content" "${pii_raw}.pathline" "${pii_raw}.allow_lines"
pii_count="$(wc -l < "$pii_report" | tr -d ' ')"
if [ "$pii_count" -gt 0 ]; then
    fail=1
    echo "tree-scan: PII STAGE — $pii_count occurrences:" >&2
    sed 's/^/  /' "$pii_report" >&2
fi

if [ "$fail" -ne 0 ]; then
    echo "tree-scan: counts — PATH=$path_count PATH-TERMS=$pathterm_count WORD=$word_count PHRASE=$phrase_count NAME=$name_count PII=$pii_count" >&2
    exit 1
fi

echo "MEASURED: $files_scanned tracked files, $content_scanned subjected to the 4 content stages (excluded: $path_count PATH, $large_count size, $excludepaths_count LEAK_EXCLUDE_PATHS)"
exit 0
