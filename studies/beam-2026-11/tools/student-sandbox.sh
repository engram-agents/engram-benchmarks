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
#   SANDBOX_RO_BINDS / SANDBOX_RW_BINDS   optional colon-separated absolute directories bound read-only / read-write at
#                         their own paths (the tools directory; the proctor directory); SANDBOX_RW_ROOT (required with
#                         SANDBOX_RW_BINDS) is the directory every RW entry must lie inside. Refused when an entry is
#                         "/" or contains a protected path (home, /home, the slot's parent, BEAM_PARQUET...)
#   SANDBOX_LOG          optional file (outside the box) for launch lines and per-connection counts/timings
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

# (R3) Open the binary ONCE. The sha256 is taken from that open file and THAT descriptor is what bwrap binds
# (--ro-bind-fd), so the file hashed is the file bound: replacing the path after this point changes nothing. The
# path the descriptor resolves to is where the box sees it. A hash mismatch is A9's "refuse on mismatch" in
# launcher form.
exec {BINFD}< "$SANDBOX_BINARY" || refuse "SANDBOX_BINARY could not be read"
BIN_REAL=$(readlink -f -- "/proc/$$/fd/$BINFD" 2>/dev/null)
[ -n "$BIN_REAL" ] && [ -f "$BIN_REAL" ] || refuse "SANDBOX_BINARY could not be resolved"
BIN_SUM=$("$PY" -I -c '
import hashlib, sys
h = hashlib.sha256()
for chunk in iter(lambda: sys.stdin.buffer.read(1 << 20), b""):
    h.update(chunk)
print(h.hexdigest())' <&"$BINFD" 2>/dev/null) || refuse "SANDBOX_BINARY could not be read"
[ -n "${BIN_SUM:-}" ] || refuse "SANDBOX_BINARY could not be read"
want=${SANDBOX_BINARY_SHA256,,}
[ "$BIN_SUM" = "$want" ] || refuse "SANDBOX_BINARY_SHA256 mismatch: the binary's sha256 is not the pinned one"
SLOT=$(realpath -e -- "$SANDBOX_SLOT" 2>/dev/null) && [ -n "$SLOT" ] || refuse "SANDBOX_SLOT cannot be resolved"

# ---- R1/R2: an allow-list by declared roots. The slot, each ROOT and each entry obey the same class rules, all
# generated from the host at run time (no path is named here): refused when it is "/", equal to or an ancestor of
# ANY home directory in the account database (all users) or of the slot, contains the dataset file or the pinned
# binary, or sits below a home directory at any depth through a path component that begins with "." (dot-directories
# hold secrets, ssh keys, config, the ENGRAM home). Every RO entry must lie inside SANDBOX_RO_ROOT and every RW entry
# inside SANDBOX_RW_ROOT, after realpath. (Round 3 withdrew the hand-listed protected array of round 2.)
HOMES=()
while IFS= read -r -d '' h; do HOMES+=("$h"); done < <("$PY" -I "$FWD" homes 2>/dev/null)
if [ "${SANDBOX_TEST:-}" = 1 ] && [ -n "${SANDBOX_TEST_EXTRA_HOMES:-}" ]; then
  # test only: extra stand-in home directories, so the home rules are tested without touching host homes. It adds
  # homes, so it can only add refusals.
  IFS=: read -r -a XH <<< "$SANDBOX_TEST_EXTRA_HOMES"
  for h in "${XH[@]}"; do HOMES+=("$(realpath -m -- "$h")"); done
fi
[ "${#HOMES[@]}" -gt 0 ] || refuse "cannot read the account database"
DATASET=""
[ -z "${BEAM_PARQUET:-}" ] || DATASET=$(realpath -m -- "$BEAM_PARQUET")

inside() { [ "$1" = / ] && return 0; case "$2/" in "$1"/*) return 0 ;; esac; return 1; }   # $2 equal to or inside $1
class_check() {   # $1 variable name, $2 resolved path, $3 kind: slot | ro | rw. Refuses; returns when the path is fine.
  local v=$1 p=$2 kind=$3 h rel
  [ "$p" != / ] || refuse "$v is the filesystem root"
  for h in "${HOMES[@]}"; do
    if inside "$p" "$h"; then refuse "$v $p is, or is an ancestor of, a home directory in the account database"; fi
  done
  if [ "$kind" != slot ] && inside "$p" "$SLOT"; then refuse "$v $p is, or is an ancestor of, the slot"; fi
  if [ -n "$DATASET" ] && inside "$p" "$DATASET"; then refuse "$v $p contains the dataset file"; fi
  if inside "$p" "$BIN_REAL" && ! { [ "${SANDBOX_TEST:-}" = 1 ] && [ "${SANDBOX_TEST_ALLOW_BINARY_IN_RW:-}" = 1 ] && [ "$kind" != ro ]; }; then
    refuse "$v $p contains the pinned binary"
  fi
  for h in "${HOMES[@]}"; do
    [ "$h" != / ] && [ "$p" != "$h" ] && inside "$h" "$p" || continue
    rel=${p#"$h"/}
    if [[ /$rel == */.* ]]; then refuse "$v $p is inside a dot-directory of a home"; fi
  done
}
class_check SANDBOX_SLOT "$SLOT" slot

# ---- F2: extra binds, validated here (same refuse-before-anything rule) ------------------------------------
# SANDBOX_RO_BINDS / SANDBOX_RW_BINDS: colon-separated absolute directories, bound at their own (resolved) paths,
# each inside its declared root (SANDBOX_RO_ROOT / SANDBOX_RW_ROOT, required with the binds).
RO_LIST=(); RW_LIST=()
CANON=""
canon_entry() {   # $1 variable name, $2 one entry, $3 "entry " or ""; sets CANON to its resolved path, or refuses
  local e=$2
  [ -n "$e" ] || refuse "$1 has an empty entry"
  [[ $e == /* ]] || refuse "$1 ${3}is not an absolute path: $e"
  [ -d "$e" ] || refuse "$1 ${3}is not an existing directory: $e"
  CANON=$(realpath -e -- "$e" 2>/dev/null) && [ -n "$CANON" ] || refuse "$1 ${3}cannot be resolved: $e"
}
split_entries() {  # $1 variable name, $2 list; fills ENTRIES
  ENTRIES=()
  [[ $2 == :* || $2 == *: || $2 == *::* ]] && refuse "$1 has an empty entry"
  IFS=: read -r -a ENTRIES <<< "$2"
}
bind_list() {   # $1 kind ro|rw, $2 binds variable name, $3 root variable name; fills RO_LIST / RW_LIST
  local kind=$1 bv=$2 rv=$3 root e
  [ -n "${!rv:-}" ] || refuse "$rv is required when $bv is set"
  canon_entry "$rv" "${!rv}" ""
  root=$CANON
  class_check "$rv" "$root" "$kind"
  split_entries "$bv" "${!bv}"
  for e in "${ENTRIES[@]}"; do
    canon_entry "$bv" "$e" "entry "
    class_check "$bv" "$CANON" "$kind"
    inside "$root" "$CANON" || refuse "$bv entry $e is not inside $rv"
    if [ "$kind" = ro ]; then RO_LIST+=("$CANON"); else RW_LIST+=("$CANON"); fi
  done
}
[ -z "${SANDBOX_RO_BINDS:-}" ] || bind_list ro SANDBOX_RO_BINDS SANDBOX_RO_ROOT
[ -z "${SANDBOX_RW_BINDS:-}" ] || bind_list rw SANDBOX_RW_BINDS SANDBOX_RW_ROOT
EXTRA_BINDS=()
for d in "${RO_LIST[@]}"; do EXTRA_BINDS+=(--ro-bind "$d" "$d"); done
for d in "${RW_LIST[@]}"; do EXTRA_BINDS+=(--bind "$d" "$d"); done
RO_LOG=$(IFS=:; echo "${RO_LIST[*]}"); RW_LOG=$(IFS=:; echo "${RW_LIST[*]}")

# ---- R4: /etc stays (read-only: removing it risks breaking the harness in ways the tests may not see), minus what
# names other people. Overlaid read-only, all generated at launch:
#   /etc/passwd, /etc/group   synthetic: root and the invoking uid/gid only, the invoker's home is the slot
#   /etc/machine-id           a fixed zero id;   /etc/hostname   "sandbox" (and the box has its own UTS namespace)
#   every other readable regular file under /etc that contains "/home/" or another account's name: an empty file
# bwrap cannot create files in the read-only /etc, so an overlay applies only where the host file exists.
ETCARGS=()
overlay_data() {   # $1 destination, $2 content
  local d fd
  d=$(realpath -e -- "$1" 2>/dev/null) || return 0
  case $d in /etc/*) ;; *) return 0 ;; esac
  [ -f "$d" ] || return 0
  exec {fd}<<< "$2"
  ETCARGS+=(--ro-bind-data "$fd" "$d")
}
PASSWD_TXT=$("$PY" -I "$FWD" account-file passwd --home "$SLOT" 2>/dev/null) || refuse "cannot read the invoking account"
GROUP_TXT=$("$PY" -I "$FWD" account-file group --home "$SLOT" 2>/dev/null) || refuse "cannot read the invoking account"
overlay_data /etc/passwd "$PASSWD_TXT"
overlay_data /etc/group "$GROUP_TXT"
overlay_data /etc/machine-id "00000000000000000000000000000000"
overlay_data /etc/hostname "sandbox"
mapfile -d '' -t MASKS < <("$PY" -I "$FWD" etc-scan 2>/dev/null; printf 'END\0')
[ "${#MASKS[@]}" -gt 0 ] && [ "${MASKS[-1]}" = END ] || refuse "cannot scan /etc"
unset 'MASKS[-1]'
ETC_MASKED=${#MASKS[@]}
# One descriptor per mask: bwrap reads and closes each --ro-bind-data descriptor, and binding /dev/null instead gives
# a device file that the nodev mount makes unreadable. The cap keeps the descriptor count far below any limit.
[ "$ETC_MASKED" -le 200 ] || refuse "$ETC_MASKED files under /etc name a home or another account: more than this launcher masks"
for f in "${MASKS[@]}"; do exec {fd}</dev/null; ETCARGS+=(--ro-bind-data "$fd" "$f"); done

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
"$PY" -I "$FWD" "${FWDARGS[@]}" </dev/null >/dev/null 2>&1 {BINFD}<&- &
FPID=$!
for ((i = 0; i < 250; i++)); do [ -S "$SOCK" ] && break; sleep 0.02; done
if [ ! -S "$SOCK" ]; then
  kill "$FPID" 2>/dev/null; rmdir "$SOCKDIR" 2>/dev/null
  printf '%s: the bridge forwarder did not start\n' "$PROG" >&2; exit 3
fi
disown "$FPID" 2>/dev/null

log "wrapper-launch time=$EPOCHREALTIME pid=$$ binary_sha256=$BIN_SUM model=$SANDBOX_MODEL_HOST:$PORT test_exec=$TESTMODE ro_binds=$RO_LOG rw_binds=$RW_LOG etc_masked=$ETC_MASKED"

# ---- the box. /home, /tmp, /var/tmp and /run are fresh tmpfs; only the allow-listed system directories are bound
# (read-only), then the slot (read-write), the binary FILE (read-only) and the validated extra binds at their own
# paths. bwrap creates the missing parent directories inside the tmpfs for the file bind.
BW=("$BWRAP" --die-with-parent --new-session --unshare-pid --unshare-net --unshare-ipc --unshare-uts --hostname sandbox
    --clearenv "${ENVARGS[@]}"
    --proc /proc --dev /dev
    --ro-bind-try /usr /usr --ro-bind-try /bin /bin --ro-bind-try /sbin /sbin
    --ro-bind-try /lib /lib --ro-bind-try /lib32 /lib32 --ro-bind-try /lib64 /lib64 --ro-bind-try /libx32 /libx32
    --ro-bind-try /etc /etc "${ETCARGS[@]}"
    --tmpfs /home --tmpfs /tmp --tmpfs /var/tmp --tmpfs /run
    --bind "$SLOT" "$SLOT"
    "${EXTRA_BINDS[@]}"
    --ro-bind "$SOCK" /run/sandbox-bridge.sock
    --ro-bind "$FWD" /run/sandbox-forward.py
    --ro-bind-fd "$BINFD" "$BIN_REAL")   # LAST, so nothing mounted before it can shadow the pinned binary
exec "${BW[@]}" -- "$PY" -I /run/sandbox-forward.py inner --sock /run/sandbox-bridge.sock --port "$PORT" "${INNER_UNSET[@]}" -- "${CMD[@]}"
