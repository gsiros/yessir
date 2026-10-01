#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Install from a checkout or from a downloaded copy of this script.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: bash install.sh [--prefix PATH] [--ref REF]

--prefix PATH  Install in PATH/bin and PATH/share/yessir. Default: ~/.local.
--ref REF      Download this GitHub branch, tag, or commit. Default: main.
--help         Show these instructions.

A checkout is used when --ref is absent and bin/ exists beside this script.
Stop active yessir watchers before you update an installation.
EOF
}

fail() {
    printf 'yessir install: %s\n' "$*" >&2
    exit 1
}

prefix="${HOME:?HOME must be set}/.local"
ref=main
force_download=0
while (( $# )); do
    case "$1" in
        --prefix)
            (( $# >= 2 )) || fail '--prefix needs a path'
            [[ -n "$2" ]] || fail '--prefix needs a non-empty path'
            prefix="$2"
            shift 2
            ;;
        --ref)
            (( $# >= 2 )) || fail '--ref needs a branch, tag, or commit'
            ref="$2"
            [[ "$ref" =~ ^[[:alnum:]][[:alnum:]_.\/-]*$ ]] || fail 'invalid --ref value'
            force_download=1
            shift 2
            ;;
        --help|-h) usage; exit 0 ;;
        *) fail "unknown argument: $1" ;;
    esac
done

[[ "$(uname -s)" == Linux && -r /proc/self/stat ]] || fail 'Linux with /proc is required'
for dependency in python3 tmux install mktemp; do
    command -v "$dependency" >/dev/null 2>&1 || fail "required command not found: $dependency"
done
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' || fail 'Python 3.8 or later is required'

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/yessir-install.XXXXXXXX")
pending_file=''
cleanup() {
    [[ -z "$pending_file" ]] || rm -f -- "$pending_file"
    rm -rf -- "$work_dir"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

source_dir=''
script_path="${BASH_SOURCE[0]:-}"
if [[ "$force_download" == 0 && -n "$script_path" && -f "$script_path" ]]; then
    candidate=$(CDPATH='' cd -- "$(dirname -- "$script_path")" && pwd -P)
    if [[ -f "$candidate/bin/yessir" && -f "$candidate/bin/claude-tmux-yes" && -f "$candidate/LICENSE" ]]; then
        source_dir="$candidate"
    fi
fi

if [[ -z "$source_dir" ]]; then
    for dependency in curl tar; do
        command -v "$dependency" >/dev/null 2>&1 || fail "required command not found: $dependency"
    done
    printf 'Download gsiros/yessir (%s).\n' "$ref"
    curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
        --connect-timeout 15 --max-time 120 --retry 2 \
        "https://codeload.github.com/gsiros/yessir/tar.gz/$ref" \
        --output "$work_dir/source.tar.gz"
    mkdir -- "$work_dir/source"
    tar -xzf "$work_dir/source.tar.gz" --strip-components=1 -C "$work_dir/source"
    source_dir="$work_dir/source"
fi

for file in bin/yessir bin/claude-tmux-yes LICENSE; do
    [[ -f "$source_dir/$file" && ! -L "$source_dir/$file" ]] || fail "source file missing or invalid: $file"
done
sh -n "$source_dir/bin/yessir"
python3 - "$source_dir/bin/claude-tmux-yes" <<'PY'
import ast
import pathlib
import sys
ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
PY

mkdir -p -- "$prefix/bin" "$prefix/share/yessir"
prefix=$(CDPATH='' cd -- "$prefix" && pwd -P)

# Rename each complete file into place. Do not copy into a running script.
put_file() {
    local source="$1" destination="$2" mode="$3"
    pending_file=$(mktemp "$(dirname -- "$destination")/.yessir-install.XXXXXXXX")
    install -m "$mode" -- "$source" "$pending_file"
    mv -f -- "$pending_file" "$destination"
    pending_file=''
}
put_file "$source_dir/bin/claude-tmux-yes" "$prefix/bin/claude-tmux-yes" 755
put_file "$source_dir/bin/yessir" "$prefix/bin/yessir" 755
put_file "$source_dir/LICENSE" "$prefix/share/yessir/LICENSE" 644

printf '\nInstalled: %s/bin/yessir\n' "$prefix"
printf 'License: %s/share/yessir/LICENSE\n' "$prefix"
case ":${PATH:-}:" in
    *":$prefix/bin:"*) ;;
    *)
        printf '\nAdd this command to your shell startup file:\n'
        # Leave $PATH literal so it expands in the user's shell startup file.
        # shellcheck disable=SC2016
        printf 'export PATH=%q:"$PATH"\n' "$prefix/bin"
        ;;
esac
printf '\nWhile Claude is open, use the tmux command prompt:\n'
printf 'run-shell '\''yessir --on'\''\n'
printf 'run-shell '\''yessir --off'\''\n'
