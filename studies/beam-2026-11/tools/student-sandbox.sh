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
#   SANDBOX_MODEL_ALLOW   (required unless SANDBOX_MODEL_LEARN=1) comma-separated "METHOD /path" entries, exact path or a
#                         prefix ending in "*": the only requests the model bridge forwards (anything else gets 403)
#   SANDBOX_MODEL_LEARN   1: allow everything the bridge can frame and log each request's METHOD and PATH to SANDBOX_LOG
#   SANDBOX_RO_BINDS + SANDBOX_RO_ROOT, SANDBOX_RW_BINDS + SANDBOX_RW_ROOT   optional colon-separated absolute
#                         directories bound read-only / read-write at their own paths (the tools directory; the proctor
#                         directory). Each ROOT is required with its binds and every entry must lie inside it. The slot,
#                         each root and each entry obey the class rules in the R1/R2 block below.
#   SANDBOX_PROTECT      REQUIRED. Colon-separated absolute EXISTING paths (files or directories) that no slot, root or entry
#                         may equal, contain or lie inside: the dataset file, the key-list directory. Empty or unset is a refusal.
#   HOME (the caller's own)  must resolve to the slot (realpath equal): refused otherwise, so the student's HOME exists inside
#   SANDBOX_LOG          optional file (outside the box) for launch lines, per-connection counts/timings and refusals
#   Caps (constants below, provisional until the pilot's learn mode has measured a real run; test-mode overrides only):
#                         the bridge's trusted side (per request, total buffered, concurrent connections) and the box's own
#                         systemd user scope (tasks, memory). Every effective value is on the launch line.
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
for n in SANDBOX_SLOT SANDBOX_BINARY SANDBOX_BINARY_SHA256 SANDBOX_MODEL_HOST SANDBOX_MODEL_PORT SANDBOX_PROTECT; do
  [ -n "${!n:-}" ] || refuse "$n is not set or is empty"
done
[[ $SANDBOX_BINARY_SHA256 =~ ^[0-9a-fA-F]{64}$ ]] || refuse "SANDBOX_BINARY_SHA256 is not 64 hex characters"
[[ $SANDBOX_MODEL_PORT =~ ^[0-9]{1,5}$ ]] && ((10#$SANDBOX_MODEL_PORT >= 1 && 10#$SANDBOX_MODEL_PORT <= 65535)) \
  || refuse "SANDBOX_MODEL_PORT is not a port number (1-65535)"
PORT=$((10#$SANDBOX_MODEL_PORT))
# the listener inside the box is unprivileged: a port below 1024 would fail there with a traceback, not a refusal
[ "$PORT" -ge 1024 ] || refuse "SANDBOX_MODEL_PORT is below 1024: the in-box listener cannot bind a privileged port"
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

# ---- R5: the model bridge is an HTTP request allow-list. SANDBOX_MODEL_ALLOW is required, unless SANDBOX_MODEL_LEARN=1,
# which allows everything and logs each request's METHOD and PATH (never bodies or query strings) to SANDBOX_LOG.
LEARN=0
case "${SANDBOX_MODEL_LEARN:-}" in
  "") ;;
  1) LEARN=1; [ -n "${SANDBOX_LOG:-}" ] || refuse "SANDBOX_MODEL_LEARN=1 needs SANDBOX_LOG to learn into" ;;
  *) refuse "SANDBOX_MODEL_LEARN must be 1 or unset" ;;
esac
MODEL_MODE=learn; ALLOW_N=0   # the launch line records which one this run used, and how many entries the list has
if [ "$LEARN" = 0 ]; then
  [ -n "${SANDBOX_MODEL_ALLOW:-}" ] || refuse "SANDBOX_MODEL_ALLOW is not set or is empty"
  MODEL_MODE=allow
  ALLOW_N=$("$PY" -I "$FWD" check-allow --text="$SANDBOX_MODEL_ALLOW" 2>&1) || refuse "SANDBOX_MODEL_ALLOW $ALLOW_N"
fi

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
# ANY home directory in the account database (all users) or of the slot, contains the pinned binary, is equal to,
# contains or lies inside a SANDBOX_PROTECT path, touches a path the box provides (S3), or sits below a home directory at any depth through a path component that begins with "." (dot-directories
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
# SANDBOX_PROTECT (required): every entry an absolute path that exists (file or directory), resolved once here.
[[ $SANDBOX_PROTECT == :* || $SANDBOX_PROTECT == *: || $SANDBOX_PROTECT == *::* ]] && refuse "SANDBOX_PROTECT has an empty entry"
PROTECT=()
IFS=: read -r -a PENTRIES <<< "$SANDBOX_PROTECT"
for e in "${PENTRIES[@]}"; do
  [[ $e == /* ]] || refuse "SANDBOX_PROTECT entry is not an absolute path: $e"
  [ -e "$e" ] || refuse "SANDBOX_PROTECT entry does not exist: $e"
  r=$(realpath -e -- "$e" 2>/dev/null) && [ -n "$r" ] || refuse "SANDBOX_PROTECT entry cannot be resolved: $e"
  PROTECT+=("$r")
done
[ "${#PROTECT[@]}" -gt 0 ] || refuse "SANDBOX_PROTECT is not set or is empty"

# ---- S3: ONE list of the paths the box provides (binds, masks or creates). The bwrap argv below is built from these
# arrays, and the class rules refuse a slot, root or entry that touches any of them, so a path added to the box has to
# be added here, where both read it. SOCKBASE is where the bridge socket directory is created.
BOX_RO=(/usr /bin /sbin /lib /lib32 /lib64 /libx32 /etc)   # system directories, read-only (with the /etc overlays)
BOX_PSEUDO=(/proc /dev)                                     # the box's own /proc and /dev
BOX_SHM=/dev/shm                                            # its own capped tmpfs, inside /dev
BOX_TMPFS_BIG=(/tmp /var/tmp)                               # fresh tmpfs, the TMP cap
BOX_HOME=/home; BOX_RUN=/run
BOX_TMPFS_SMALL=("$BOX_HOME" "$BOX_RUN")                    # fresh tmpfs, the home/run cap
BOX_ABSENT=(/sys)                                           # not provided at all: masked by absence
SOCKBASE=${TMPDIR:-/tmp}
# Classes of refusal. SYSTEM: equal, inside or an ancestor. FRESH (a fresh tmpfs whose host content is never shown, and the
# socket base): equal or an ancestor only, because a bind placed under a fresh tmpfs shows only what the caller named.
BOX_SYSTEM=("${BOX_RO[@]}" "${BOX_PSEUDO[@]}" "$BOX_SHM" "$BOX_RUN" "${BOX_ABSENT[@]}")
BOX_FRESH=("${BOX_TMPFS_BIG[@]}" "$BOX_HOME" "$(realpath -m -- "$SOCKBASE")")
box_paths() { printf '%s\n' "${BOX_RO[@]}" "${BOX_PSEUDO[@]}" "$BOX_SHM" "${BOX_TMPFS_BIG[@]}" "${BOX_TMPFS_SMALL[@]}" \
  "${BOX_ABSENT[@]}" "$(realpath -m -- "$SOCKBASE")"; }

inside() { [ "$1" = / ] && return 0; case "$2/" in "$1"/*) return 0 ;; esac; return 1; }   # $2 equal to or inside $1
class_check() {   # $1 variable name, $2 resolved path, $3 kind: slot | ro | rw. Refuses; returns when the path is fine.
  local v=$1 p=$2 kind=$3 h rel q r
  [ "$p" != / ] || refuse "$v is the filesystem root"
  for h in "${HOMES[@]}"; do
    if inside "$p" "$h"; then refuse "$v $p is, or is an ancestor of, a home directory in the account database"; fi
  done
  if [ "$kind" != slot ] && inside "$p" "$SLOT"; then refuse "$v $p is, or is an ancestor of, the slot"; fi
  if inside "$p" "$BIN_REAL" && ! { [ "${SANDBOX_TEST:-}" = 1 ] && [ "${SANDBOX_TEST_ALLOW_BINARY_IN_RW:-}" = 1 ] && [ "$kind" != ro ]; }; then
    refuse "$v $p contains the pinned binary"
  fi
  for q in "${PROTECT[@]}"; do
    if inside "$p" "$q" || inside "$q" "$p"; then refuse "$v $p is, contains or lies inside a protected path (SANDBOX_PROTECT)"; fi
  done
  for q in "${BOX_SYSTEM[@]}"; do
    for r in "$q" "$(realpath -m -- "$q")"; do
      if inside "$r" "$p" || inside "$p" "$r"; then refuse "$v $p is, contains or lies inside a path the box provides: $q"; fi
    done
  done
  for q in "${BOX_FRESH[@]}"; do
    for r in "$q" "$(realpath -m -- "$q")"; do
      if inside "$p" "$r"; then refuse "$v $p is, or contains, a path the box provides: $q"; fi
    done
  done
  for h in "${HOMES[@]}"; do
    [ "$h" != / ] && [ "$p" != "$h" ] && inside "$h" "$p" || continue
    rel=${p#"$h"/}
    if [[ /$rel == */.* ]]; then refuse "$v $p is inside a dot-directory of a home"; fi
  done
}
class_check SANDBOX_SLOT "$SLOT" slot

# ---- B: the student's HOME is the slot. The environment is passed through unchanged (S5), so a run script that gets HOME
# wrong would hand the student a HOME that does not exist inside the box: a confusing run, not a named refusal. HOME is
# read from the block bash was started with (the same source the box's environment comes from), so a HOME bash would
# default is not mistaken for one the caller passed. Equal after realpath: a symlink to the slot or a trailing slash passes.
CALLER_HOME=""
while IFS= read -r -d '' kv; do case $kv in HOME=*) CALLER_HOME=${kv#HOME=} ;; esac; done < "/proc/$$/environ"
[ -n "$CALLER_HOME" ] || refuse "HOME is not set or is empty: it must be the slot (SANDBOX_SLOT)"
HOME_REAL=$(realpath -e -- "$CALLER_HOME" 2>/dev/null) && [ "$HOME_REAL" = "$SLOT" ] \
  || refuse "HOME is not the slot: realpath of HOME differs from realpath of SANDBOX_SLOT"

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

# ---- R4/S5: /etc stays (read-only: removing it risks breaking the harness in ways the tests may not see), minus what
# names people or agents. Overlaid read-only, all generated at launch:
#   /etc/passwd, /etc/group   synthetic: root and the invoking uid/gid only, the invoker's home is the slot
#   /etc/machine-id           a fixed zero id;   /etc/hostname   "sandbox" (and the box has its own UTS namespace)
#   every other readable regular file under /etc that contains "/home/" or the name of any account with uid >= 1000
#                             (nobody excluded) as a whole word, any delimiter: an empty file (system account names are not matched)
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

# ---- R6/S4: tmpfs caps, so a student cannot fill host memory: /tmp, /var/tmp and /dev/shm 2 GiB each, /home and /run
# 64 MiB; /dev itself (a tmpfs of its own, half of host RAM) is remounted read-only after /dev/shm is mounted.
# Overridable only in test mode, so a cell can show a write past a small cap failing.
TMP_CAP=2147483648; HOME_CAP=67108864   # /dev/shm gets the TMP cap
if [ "${SANDBOX_TEST:-}" = 1 ]; then
  for v in SANDBOX_TEST_TMP_CAP SANDBOX_TEST_HOME_RUN_CAP; do
    [ -z "${!v:-}" ] || { [[ ${!v} =~ ^[1-9][0-9]{0,15}$ ]] || refuse "$v is not a positive byte count"; }
  done
  [ -z "${SANDBOX_TEST_TMP_CAP:-}" ] || TMP_CAP=$SANDBOX_TEST_TMP_CAP
  [ -z "${SANDBOX_TEST_HOME_RUN_CAP:-}" ] || HOME_CAP=$SANDBOX_TEST_HOME_RUN_CAP
fi

# ---- A2: caps on the TRUSTED side of the bridge. The outer forwarder buffers a whole request before it sends a byte
# upstream, and it runs outside the box (and outside any cap on the box), so a student must not be able to make it
# allocate without bound. PROVISIONAL until the wrapper-cost pilot's learn mode records the real maxima (the harness
# sends whole contexts, order of 1 MB): 32 MiB per request, 64 MiB over all connections, 4 concurrent connections (the
# harness opens one). Past the first two: a named 413; past the third: a 503. Overridable only in test mode.
REQ_CAP=33554432; TOTAL_CAP=67108864; CONN_CAP=4
if [ "${SANDBOX_TEST:-}" = 1 ]; then
  for v in SANDBOX_TEST_MAX_REQUEST SANDBOX_TEST_MAX_TOTAL SANDBOX_TEST_MAX_CONNS; do
    [ -z "${!v:-}" ] || { [[ ${!v} =~ ^[1-9][0-9]{0,15}$ ]] || refuse "$v is not a positive count"; }
  done
  [ -z "${SANDBOX_TEST_MAX_REQUEST:-}" ] || REQ_CAP=$SANDBOX_TEST_MAX_REQUEST
  [ -z "${SANDBOX_TEST_MAX_TOTAL:-}" ] || TOTAL_CAP=$SANDBOX_TEST_MAX_TOTAL
  [ -z "${SANDBOX_TEST_MAX_CONNS:-}" ] || CONN_CAP=$SANDBOX_TEST_MAX_CONNS
fi

# ---- C: process and memory caps on the box itself. The box runs in its own systemd USER scope with TasksMax (pids, threads
# included), MemoryMax and MemorySwapMax=0, entered by this wrapper's own exec, so the caps cover the box alone: the host
# uid, the host-side forwarder (started above this line, so it stays in the caller's cgroup) and the feeder are outside.
# Measured on the study host (2026-11-20): bubblewrap 0.9.0 has no rlimit options; prlimit around the wrapper fails
# (the limit is charged to the uid's host-wide count) and prlimit inside the box caps processes only, not memory;
# RLIMIT_AS cannot be set from RSS intuition (the pinned binary's runtime reserves about 9.4 GiB of address space for
# about 200 MiB resident); the cgroup route caps what matters and kills only the hog. PROVISIONAL until the pilot has
# measured a real run: 1024 tasks, 4 GiB. It replaces the caller's cgroup for the box: a memory limit set around the whole
# run (memrun's) no longer covers the box, which has its own. Overridable only in test mode.
BOX_TASKS=1024; BOX_MEM=4294967296
if [ "${SANDBOX_TEST:-}" = 1 ]; then
  for v in SANDBOX_TEST_TASKS_MAX SANDBOX_TEST_MEMORY_MAX; do
    [ -z "${!v:-}" ] || { [[ ${!v} =~ ^[1-9][0-9]{0,15}$ ]] || refuse "$v is not a positive count"; }
  done
  [ -z "${SANDBOX_TEST_TASKS_MAX:-}" ] || BOX_TASKS=$SANDBOX_TEST_TASKS_MAX
  [ -z "${SANDBOX_TEST_MEMORY_MAX:-}" ] || BOX_MEM=$SANDBOX_TEST_MEMORY_MAX
fi
# Fail closed, before anything is created or started: without a user manager that can start the scope the caps cannot be
# applied, and a box without them is not the registered box. systemd-run reaches the user bus through XDG_RUNTIME_DIR,
# which a feeder's minimal environment lacks; it is set for this call and the exec below only (the box's own environment
# is built from the block bash was started with, so it does not reach the student).
command -v systemd-run >/dev/null || refuse "systemd-run not found: the box's process and memory caps cannot be applied"
SCOPE_RT=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCOPE=(systemd-run --user --scope --quiet --collect -p "TasksMax=$BOX_TASKS" -p "MemoryMax=$BOX_MEM" -p MemorySwapMax=0
       -p OOMPolicy=continue)   # continue: the kernel kills the hog alone; the default (stop) would SIGTERM the whole box
XDG_RUNTIME_DIR=$SCOPE_RT "${SCOPE[@]}" -- "$PY" -I -c pass >/dev/null 2>&1 \
  || refuse "systemd-run could not start a user scope with TasksMax and MemoryMax: the box's process and memory caps cannot be applied (needs a user systemd manager with the pids and memory controllers delegated)"

# ---- the bridge: a host-side forwarder on a UNIX socket (the only thing that crosses the network boundary) --
# A forwarder that was SIGKILLed cannot remove its socket directory. Each directory records the pid it watches in
# watch.pid; the next launch removes the directories of ours (owned by this user, a real directory, never a link)
# whose watched pid is gone, touching only the two files the launcher itself puts there.
for d in "$SOCKBASE"/student-sandbox.*; do
  [ -d "$d" ] && [ ! -L "$d" ] && [ -O "$d" ] && [ -f "$d/watch.pid" ] && [ ! -L "$d/watch.pid" ] || continue
  wp=$(head -c 20 "$d/watch.pid" 2>/dev/null)
  wp=${wp//[$'\n\r ']/}
  [[ $wp =~ ^[0-9]{1,10}$ ]] || continue
  [ -d "/proc/$wp" ] && continue
  rm -f -- "$d/bridge.sock" "$d/watch.pid"
  rmdir -- "$d" 2>/dev/null
done
SOCKDIR=$(mktemp -d "$SOCKBASE/student-sandbox.XXXXXX") || refuse "cannot create the bridge socket directory"
chmod 700 "$SOCKDIR"
printf '%s\n' "$$" > "$SOCKDIR/watch.pid"
SOCK="$SOCKDIR/bridge.sock"
FWDARGS=(outer --sock "$SOCK" --host "$SANDBOX_MODEL_HOST" --port "$PORT" --watch "$$"
         --max-request "$REQ_CAP" --max-total "$TOTAL_CAP" --max-conns "$CONN_CAP")
[ -n "${SANDBOX_LOG:-}" ] && FWDARGS+=(--log "$SANDBOX_LOG")
if [ "$LEARN" = 1 ]; then FWDARGS+=(--learn); else FWDARGS+=(--allow "$SANDBOX_MODEL_ALLOW"); fi
# It watches this pid, which becomes bwrap by the exec below, and removes the socket when that pid is gone.
"$PY" -I "$FWD" "${FWDARGS[@]}" </dev/null >/dev/null 2>&1 {BINFD}<&- &
FPID=$!
for ((i = 0; i < 250; i++)); do [ -S "$SOCK" ] && break; sleep 0.02; done
if [ ! -S "$SOCK" ]; then
  kill "$FPID" 2>/dev/null; rm -f -- "$SOCKDIR/watch.pid"; rmdir "$SOCKDIR" 2>/dev/null
  printf '%s: the bridge forwarder did not start\n' "$PROG" >&2; exit 3
fi
disown "$FPID" 2>/dev/null

# The launch line records everything that shaped this run: the model mode (learn allows everything the bridge can frame)
# and the allow-list's entry count, whether SANDBOX_TEST was set, and every effective cap. A stray test flag in a run
# is therefore visible in the log and, in test mode, on stderr (a loud marker, printed here by the wrapper, before
# the box starts: it is not part of the student's streams).
TESTFLAG=0
if [ "${SANDBOX_TEST:-}" = 1 ]; then
  TESTFLAG=1
  printf '%s: *** TEST MODE (SANDBOX_TEST=1): test knobs are honoured; this is not a registered run (caps: tmp=%s home_run=%s request=%s total=%s conns=%s tasks=%s memory=%s) ***\n' \
    "$PROG" "$TMP_CAP" "$HOME_CAP" "$REQ_CAP" "$TOTAL_CAP" "$CONN_CAP" "$BOX_TASKS" "$BOX_MEM" >&2
fi
log "wrapper-launch time=$EPOCHREALTIME pid=$$ binary_sha256=$BIN_SUM model=$SANDBOX_MODEL_HOST:$PORT model_mode=$MODEL_MODE model_allow_entries=$ALLOW_N test_mode=$TESTFLAG test_exec=$TESTMODE cap_tmp=$TMP_CAP cap_home_run=$HOME_CAP cap_request=$REQ_CAP cap_total=$TOTAL_CAP cap_conns=$CONN_CAP cap_tasks=$BOX_TASKS cap_memory=$BOX_MEM ro_binds=$RO_LOG rw_binds=$RW_LOG etc_masked=$ETC_MASKED box_paths=$(box_paths | paste -sd: -)"

# ---- the box. /home, /tmp, /var/tmp and /run are fresh tmpfs; only the allow-listed system directories are bound
# (read-only), then the slot (read-write), the binary FILE (read-only) and the validated extra binds at their own
# paths. bwrap creates the missing parent directories inside the tmpfs for the file bind.
SYSARGS=(); for d in "${BOX_RO[@]}"; do SYSARGS+=(--ro-bind-try "$d" "$d"); done
TMPARGS=()
for d in "${BOX_TMPFS_BIG[@]}"; do TMPARGS+=(--size "$TMP_CAP" --tmpfs "$d"); done
for d in "${BOX_TMPFS_SMALL[@]}"; do TMPARGS+=(--size "$HOME_CAP" --tmpfs "$d"); done
BW=("$BWRAP" --die-with-parent --new-session --unshare-pid --unshare-net --unshare-ipc --unshare-uts --hostname sandbox
    --cap-drop ALL   # explicit: in an unprivileged user namespace every set is already empty, but that is bwrap's default, not ours
    --clearenv "${ENVARGS[@]}"
    --proc /proc --dev /dev --size "$TMP_CAP" --tmpfs "$BOX_SHM" --remount-ro /dev
    "${SYSARGS[@]}" "${ETCARGS[@]}"
    "${TMPARGS[@]}"
    --bind "$SLOT" "$SLOT"
    "${EXTRA_BINDS[@]}"
    --ro-bind "$SOCK" /run/sandbox-bridge.sock
    --ro-bind "$FWD" /run/sandbox-forward.py
    --ro-bind-fd "$BINFD" "$BIN_REAL")   # LAST, so nothing mounted before it can shadow the pinned binary
XDG_RUNTIME_DIR=$SCOPE_RT exec "${SCOPE[@]}" -- "${BW[@]}" -- "$PY" -I /run/sandbox-forward.py inner --sock /run/sandbox-bridge.sock --port "$PORT" "${INNER_UNSET[@]}" -- "${CMD[@]}"
