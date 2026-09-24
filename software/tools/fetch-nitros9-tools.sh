#!/bin/sh
# Build LWTOOLS and ToolShed, the toolchain NitrOS-9 builds with, into
# <repo>/.tools/bin.
#
#   LWTOOLS 4.25   (c) William Astle, GPL v3.  software/tools/lwtools-4.25.tar.gz
#                  (http://lwtools.projects.l-w.ca), which is not tracked.
#   ToolShed       (c) Boisy Pitre and others.  https://github.com/n6il/toolshed
#
# Build tools, used the way fetch-a09.sh uses A09: nothing of theirs is
# committed and nothing arm6309 ships links against them.
#
# ⭐ The install lives in the repository, not in $HOME or /usr/local, for the
# reason CLAUDE.md gives for .wine_atf: this project is developed in a sandbox
# whose $HOME does not survive the session. `.tools/` is .gitignored.
#
# Then:   export PATH="$(pwd)/.tools/bin:$PATH"     (from the repo root)
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PREFIX="${NITROS9_TOOLS:-$ROOT/.tools}"
WORK="${NITROS9_TOOLS_WORK:-$(cd "$_here/." && pwd)/build/nitros9-tools}"
LWTAR="${LWTOOLS_TAR:-$ROOT/software/tools/lwtools-4.25.tar.gz}"
TSREV="${TOOLSHED_REV:-master}"

mkdir -p "$WORK" "$PREFIX/bin"

# --- LWTOOLS ---------------------------------------------------------------
if [ ! -x "$PREFIX/bin/lwasm" ]; then
  [ -f "$LWTAR" ] || { echo "FAIL: no $LWTAR"; exit 1; }
  rm -rf "$WORK/lwtools"; mkdir -p "$WORK/lwtools"
  tar xzf "$LWTAR" -C "$WORK/lwtools" --strip-components=1
  make -C "$WORK/lwtools" -j4 >"$WORK/lwtools.log" 2>&1 \
    || { tail -n 20 "$WORK/lwtools.log"; echo "FAIL: lwtools build"; exit 1; }
  make -C "$WORK/lwtools" install PREFIX="$PREFIX" >>"$WORK/lwtools.log" 2>&1
fi

# --- ToolShed --------------------------------------------------------------
# Its top-level `make` builds cocofuse, which needs libfuse, and runs the
# directories in an order its own -l flags cannot link against in parallel.
# Build the parts NitrOS-9 needs, libraries first, one at a time.
if [ ! -x "$PREFIX/bin/os9" ]; then
  if [ ! -d "$WORK/toolshed/.git" ]; then
    rm -rf "$WORK/toolshed"
    git clone -q https://github.com/n6il/toolshed.git "$WORK/toolshed"
  fi
  git -C "$WORK/toolshed" checkout -q "$TSREV"
  U="$WORK/toolshed/build/unix"
  for d in libtoolshed libnative libcecb librbf libcoco libdecb libmisc libsys \
           ar2 os9 mamou decb tocgen makewav cecb; do
    make -C "$U/$d" >"$WORK/toolshed-$d.log" 2>&1 \
      || { tail -n 20 "$WORK/toolshed-$d.log"; echo "FAIL: toolshed $d"; exit 1; }
  done
  for t in ar2 os9 mamou decb tocgen makewav cecb; do
    install -m 0755 "$U/$t/$t" "$PREFIX/bin/$t"
  done
fi

"$PREFIX/bin/lwasm" --version | head -1
"$PREFIX/bin/os9" 2>&1 | head -1 || true
echo "ok    tools in $PREFIX/bin"
