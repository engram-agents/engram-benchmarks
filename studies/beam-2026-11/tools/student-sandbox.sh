#!/usr/bin/env bash
# student-sandbox.sh : a process boundary around the BEAM student (both arms). See tools/README.md.
#
# Installed by the run script as the file named `claude` in a directory put FIRST on PATH, so feed4's
# subprocess.Popen(["claude", ...], env=...) starts it. It checks and prepares OUTSIDE the box, then `exec`s
# bwrap, so there is no moment at which the student exists outside the box.
#
# Configuration (environment; exit 2 with one named line on stderr if any is missing or malformed):
#   SANDBOX_SLOT          the benchmark home (the student's HOME): an existing directory, bound read-write
#   SANDBOX_BINARY        the pinned Claude Code binary (absolute path)
#   SANDBOX_BINARY_SHA256 its full sha256 (64 hex); refuse on mismatch
#   SANDBOX_MODEL_HOST / SANDBOX_MODEL_PORT   the model endpoint as the host sees it
#   SANDBOX_LOG           optional file (outside the box) for launch lines and per-connection counts/timings
#   SANDBOX_TEST=1 + SANDBOX_TEST_EXEC="<shell command>"   test only: run that command inside the same box instead
#                         of the binary, after every check and mount (the hash check still runs)
set -u
PROG=student-sandbox
HERE=$(cd -P -- "${BASH_SOURCE[0]%/*}" && pwd -P)
FWD="$HERE/sandbox-forward.py"
PY=/usr/bin/python3

refuse() { printf '%s: refused: %s\n' "$PROG" "$1" >&2; exit 2; }
log() { [ -n "${SANDBOX_LOG:-}" ] && printf '%s\n' "$*" >> "$SANDBOX_LOG"; return 0; }

# ---- S1: every refusal happens here, before anything is started or created --------------------------------
for n in SANDBOX_SLOT SANDBOX_BINARY SANDBOX_BINARY_SHA256 SANDBOX_MODEL_HOST SANDBOX_MODEL_PORT; do
  [ -n "${!n:-}" ] || refuse "$n is not set or is empty"
done
[[ $SANDBOX_BINARY_SHA256 =~ ^[0-9a-fA-F]{64}$ ]] || refuse "SANDBOX_BINARY_SHA256 is not 64 hex characters"
[[ $SANDBOX_MODEL_PORT =~ ^[0-9]{1,5}$ ]] && ((10#$SANDBOX_MODEL_PORT >= 1 && 10#$SANDBOX_MODEL_PORT <= 65535)) \
  || refuse "SANDBOX_MODEL_PORT is not a port number (1-65535)"
PORT=$((10#$SANDBOX_MODEL_PORT))
[[ $SANDBOX_MODEL_HOST =~ ^[A-Za-z0-9._:-]+$ ]] || refuse "SANDBOX_MODEL_HOST is not a host name or address"
[[ $SANDBOX_SLOT == /* ]] || refuse "SANDBOX_SLOT is not an absolute path"
[ -d "$SANDBOX_SLOT" ] || refuse "SANDBOX_SLOT is not an existing directory"
[[ $SANDBOX_BINARY == /* ]] || refuse "SANDBOX_BINARY is not an absolute path"
[ -f "$SANDBOX_BINARY" ] && [ -x "$SANDBOX_BINARY" ] || refuse "SANDBOX_BINARY is not an existing executable file"
if [ -n "${SANDBOX_LOG:-}" ]; then
  logdir=${SANDBOX_LOG%/*}; [ "$logdir" = "$SANDBOX_LOG" ] && logdir=.
  [ -d "$logdir" ] || refuse "SANDBOX_LOG is in a directory that does not exist"
fi
[ -x "$PY" ] || refuse "$PY not found"
[ -f "$FWD" ] || refuse "sandbox-forward.py not found next to the wrapper"
BWRAP=$(command -v bwrap) || refuse "bwrap not found on PATH"

# Resolve symlinks (the box must see the real file's directory) and hash that file. A hash mismatch is A9's
# "refuse on mismatch" in launcher form.
{ IFS= read -r BIN_REAL && IFS= read -r BIN_SUM; } < <("$PY" -I -c '
import hashlib, os, sys
p = os.path.realpath(sys.argv[1])
print(p); print(hashlib.sha256(open(p, "rb").read()).hexdigest())' "$SANDBOX_BINARY" 2>/dev/null) \
  || refuse "SANDBOX_BINARY could not be read"
[ -n "${BIN_SUM:-}" ] || refuse "SANDBOX_BINARY could not be read"
want=${SANDBOX_BINARY_SHA256,,}
[ "$BIN_SUM" = "$want" ] || refuse "SANDBOX_BINARY_SHA256 mismatch: the binary's sha256 is not the pinned one"
SLOT=$(cd -P -- "$SANDBOX_SLOT" && pwd -P)
BIN_DIR=${BIN_REAL%/*}
[ -n "$BIN_DIR" ] || refuse "SANDBOX_BINARY is at the filesystem root"
case "$SLOT/" in "$BIN_DIR/"*) refuse "SANDBOX_BINARY directory contains the slot" ;; esac

# ---- the environment the caller passed, exactly (minus SANDBOX_*) -----------------------------------------
# /proc/$$/environ is the block bash was started with, before bash adds PWD/SHLVL/_ of its own.
ENVARGS=()
INNER_UNSET=(--unset PWD)   # bwrap exports PWD itself; the inner step drops it unless the caller passed one
while IFS= read -r -d '' kv; do
  k=${kv%%=*}; v=${kv#*=}
  [[ $k =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
  case $k in SANDBOX_*) continue ;; PWD) INNER_UNSET=() ;; esac
  ENVARGS+=(--setenv "$k" "$v")
done < "/proc/$$/environ"

if [ "${SANDBOX_TEST:-}" = 1 ] && [ -n "${SANDBOX_TEST_EXEC:-}" ]; then
  CMD=(/bin/sh -c "$SANDBOX_TEST_EXEC" sh "$@")
  TESTMODE=1
else
  CMD=("$BIN_REAL" "$@")
  TESTMODE=0
fi

# ---- the bridge: a host-side forwarder on a UNIX socket (the only thing that crosses the network boundary) --
SOCKDIR=$(mktemp -d "${TMPDIR:-/tmp}/student-sandbox.XXXXXX") || refuse "cannot create the bridge socket directory"
chmod 700 "$SOCKDIR"
SOCK="$SOCKDIR/bridge.sock"
FWDARGS=(outer --sock "$SOCK" --host "$SANDBOX_MODEL_HOST" --port "$PORT" --watch "$$")
[ -n "${SANDBOX_LOG:-}" ] && FWDARGS+=(--log "$SANDBOX_LOG")
# It watches this pid, which becomes bwrap by the exec below, and removes the socket when that pid is gone.
"$PY" -I "$FWD" "${FWDARGS[@]}" </dev/null >/dev/null 2>&1 &
FPID=$!
for ((i = 0; i < 250; i++)); do [ -S "$SOCK" ] && break; sleep 0.02; done
if [ ! -S "$SOCK" ]; then
  kill "$FPID" 2>/dev/null; rmdir "$SOCKDIR" 2>/dev/null
  printf '%s: the bridge forwarder did not start\n' "$PROG" >&2; exit 3
fi
disown "$FPID" 2>/dev/null

log "wrapper-launch time=$EPOCHREALTIME pid=$$ binary_sha256=$BIN_SUM model=$SANDBOX_MODEL_HOST:$PORT test_exec=$TESTMODE"

# ---- the box. /home, /tmp, /var/tmp and /run are fresh tmpfs; only the allow-listed system directories are bound
# (read-only), then the slot (read-write) and the binary's directory (read-only) at their own paths.
BW=("$BWRAP" --die-with-parent --new-session --unshare-pid --unshare-net --unshare-ipc
    --clearenv "${ENVARGS[@]}"
    --proc /proc --dev /dev
    --ro-bind-try /usr /usr --ro-bind-try /bin /bin --ro-bind-try /sbin /sbin
    --ro-bind-try /lib /lib --ro-bind-try /lib32 /lib32 --ro-bind-try /lib64 /lib64 --ro-bind-try /libx32 /libx32
    --ro-bind-try /etc /etc --ro-bind-try /opt /opt
    --tmpfs /home --tmpfs /tmp --tmpfs /var/tmp --tmpfs /run
    --bind "$SLOT" "$SLOT"
    --ro-bind "$BIN_DIR" "$BIN_DIR"
    --ro-bind "$SOCK" /run/sandbox-bridge.sock
    --ro-bind "$FWD" /run/sandbox-forward.py)
exec "${BW[@]}" -- "$PY" -I /run/sandbox-forward.py inner --sock /run/sandbox-bridge.sock --port "$PORT" "${INNER_UNSET[@]}" -- "${CMD[@]}"
