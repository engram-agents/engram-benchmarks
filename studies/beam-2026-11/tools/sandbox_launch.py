#!/usr/bin/env python3
"""The ONE door through which a BEAM student session is started (design A10). Standard library only. This file is the
study's harness, not shipped product code.

`run_feeder(py, feeder, argv, ...)` turns "run this feeder for a student session" into a wrapped launch and reads its
verdict. Every launcher in this directory that starts a feeder (feed.py, feed2.py, feed4.py: `FEEDERS`) calls it; a
launcher that starts a student any other way is retired (RETIRED-LAUNCHER marker) and a cell searches the tree for strays.

For a student session it
  1. makes a fresh directory holding `claude` (a COPY of student-sandbox.sh) and sandbox-forward.py, and puts it FIRST on
     the PATH it hands the feeder. A copy, not a symlink: the wrapper finds sandbox-forward.py next to the path it was
     started as, a symlink would look beside the link, and a copy cannot change under the run;
  2. chooses this session's SANDBOX_LOG, a path that does not exist before the launch (one log per launch);
  3. hashes the two copies and refuses, before anything starts, if either differs from the expected value (M4b);
  4. builds the feeder's `--env` list: every SANDBOX_* setting the wrapper requires, SANDBOX_LOG and the proctor binds.
     The feeder builds the student's environment from scratch (feed4.py / feed2.py `Student.__init__`), so a SANDBOX_*
     variable that is merely EXPORTED never reaches the wrapper; only an `--env` pair does (a cell shows it);
  5. runs the feeder, then `sandbox-forward.py log-verdict --log <that log>` and compares the launch line's
     wrapper_sha256 and forwarder_sha256 with the expected values (M5).
  6. TEARDOWN (round 2), in every case, whatever the feeder's exit code and even if it raised: reads `scope_unit`,
     `forwarder_pid`, `forwarder_start` and `bridge_sock` from the launch line, runs `systemctl --user stop <scope_unit>`, and
     asserts NOTHING of the launch remains (the scope's own cgroup empty; the forwarder pid gone or a different process, by
     start time; no process anywhere with the bridge socket path in its argv). A leftover is a LaunchStop naming each pid.
     A session whose log has no launch line (the wrapper refused before launching) has nothing to stop.
And BEFORE any launch (`state_dir`, required, no default: one record per launch, written before the session starts and
closed after the teardown passes) it refuses while any earlier record fails those three checks or any user scope unit named
`student-sandbox-*` is active (LaunchRefused naming each unit or pid and how to stop it). The module's stop is the
guarantee: the wrapper's own box teardown on a caller's SIGKILL has been seen to fail (mechanism unproven, filed separately).
A feeder call that starts no student (`--dump-plan`) runs through the same function with no wrapper and no log.

Refusals before anything starts raise LaunchRefused (exit 2 semantics, the message names the reason). A log-verdict
refusal or a launch-line hash mismatch after the session raises LaunchStop (a harness failure) BEFORE the caller can read
any answer of that session; its `.result` holds the feeder's own exit code. `flagged` is a verdict, never a stop.

What the module can and cannot see: it reads the feeder's argv (`--out`, `--env`), the feeder's environment
(BEAM_OLLAMA_URL) and the PATH the feeder's Popen will use. (A student session's feeder gets an environment the module BUILDS:
FEEDER_ENV_ALLOW from the caller's environment, plus the built PATH; see there.) It cannot see a student started by anything else.
"""
import hashlib, ipaddress, itertools, json, os, re, secrets, shutil, signal, subprocess, sys, tempfile, time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
# The single list of student-starting implementations. Every process invocation of one by a launcher goes through
# run_feeder; the no-second-door cell reads this tuple, not a hand list.
FEEDERS = ("feed.py", "feed2.py", "feed4.py")
# The no-second-door gate (a cell in tests/test_sandbox_launch.py reads this dict). Every file in this directory (any extension,
# outside tests/) whose text mentions a feeder (feed, feed2, feed4) or the word `claude` must be exactly one of: this module; a
# feeder in FEEDERS; a file carrying the RETIRED-LAUNCHER marker in its first three lines; or listed HERE with a one-line
# reason: files that only read a feeder's text or constants, or name `claude` in prose. A "consumer:" entry is a file that starts
# students only through run_feeder (the cell checks it really calls it). Adding a name here is the review point: nothing else
# lets a launcher through.
NON_LAUNCHERS = {
    "README.md": "documentation: names the feeders and claude in prose, starts nothing",
    "analyze-gate2.redacted.py": "analysis of gate runs; imports feed's exchanges() for a count check, starts no student",
    "answer-delivery-check.py": "reads the turns.jsonl a feeder wrote; starts nothing",
    "reading-delivery-check.py": "reads the turns.jsonl a feeder wrote; starts nothing",
    "check-port-identity.py": "imports feed and feed2 in a subprocess to compare their constants; never uses Student",
    "control-source-check.py": "reads files a feeder and the planting step wrote; starts nothing",
    "coverage.py": "imports feed.py's renderer to count coverage; starts nothing",
    "gate-input-evidence.py": "rebuilds the messages feed.py renders and compares them with a run's transcripts; starts nothing",
    "pilot-memcheck.sh": "lists memory folders under the arm home's .claude directory; starts nothing",
    "plant-control.py": "plants facts into an arm home's stores (names .claude paths); starts no student",
    "setup-id.py": "hashes the feed scripts and their imports into a setup id; starts nothing",
    "student-sandbox.sh": "the wrapper itself: it is the file named claude on the PATH and starts the box, not a feeder",
    "p1-session.py": "consumer: starts every student session only through sandbox_launch.run_feeder",
}
WRAPPER_SRC = os.path.join(HERE, "student-sandbox.sh")
FORWARDER_SRC = os.path.join(HERE, "sandbox-forward.py")
# Every SANDBOX_* name student-sandbox.sh refuses without (a cell derives this set from the wrapper's own source).
# SANDBOX_MODEL_ALLOW is required unless SANDBOX_MODEL_LEARN=1.
REQUIRED_SANDBOX = ("SANDBOX_SLOT", "SANDBOX_BINARY", "SANDBOX_BINARY_SHA256", "SANDBOX_MODEL_HOST",
                    "SANDBOX_MODEL_PORT", "SANDBOX_PROTECT", "SANDBOX_MODEL_ALLOW")
# Names the module itself sets for each launch; a caller may not supply them.
MODULE_OWNED = ("SANDBOX_LOG", "SANDBOX_RO_BINDS", "SANDBOX_RO_ROOT", "SANDBOX_RW_BINDS", "SANDBOX_RW_ROOT")
# feed.py's OLLAMA_URL: BEAM_OLLAMA_URL, else Ollama's documented default (a cell reads feed.py and requires this).
OLLAMA_DEFAULT = "http://localhost:11434"  # privacy-scan: allow (Ollama's documented default endpoint, as in feed.py)
VERDICT_NOT_FLAGGED = "not-flagged"
VERDICT_FLAGGED_PREFIX = "flagged:"
HEX64 = re.compile(r"[0-9a-f]{64}")
_SEQ = itertools.count(1)


class LaunchRefused(Exception):
    """A named refusal BEFORE anything started (exit 2 semantics). `.leftover_count` is how many leftovers of earlier
    launches the before-launch check found (0 for every other refusal): a caller reports it per run."""
    leftover_count = 0


class LaunchStop(Exception):
    """After the session: log-verdict refused, or the launch line's hashes differ from the expected ones. The caller must
    stop and read no answer of that session. `.result` is the LaunchResult (the feeder's exit code, the log)."""
    def __init__(self, message, result):
        super().__init__(message)
        self.result = result


class LaunchResult:
    def __init__(self, returncode, log=None, verdict=None, wrapper_sha256=None, forwarder_sha256=None):
        self.returncode, self.log, self.verdict = returncode, log, verdict
        self.wrapper_sha256, self.forwarder_sha256 = wrapper_sha256, forwarder_sha256
        self.test_mode = self.test_exec = None   # from the launch line, after the session
        self.caps = {}                            # every cap_* value the launch line records (the caller writes them to its record)
        self.feeder_path = None                   # the PATH the module built and passed to the feeder (the caller writes it to its record)
        self.feeder_env_names = None              # the NAMES (never the values) of the environment the module built for the feeder


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_expected(path):
    """The expected-hashes file (no default; the scored run passes the registered one): exactly two lines,
    `wrapper_sha256=<64 hex>` then `forwarder_sha256=<64 hex>` (lower case). Anything else is a named refusal."""
    if not path:
        raise LaunchRefused("the expected-hashes file is not given (the module has no default)")
    try:
        text = open(path, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError) as e:
        raise LaunchRefused(f"the expected-hashes file {path} cannot be read ({type(e).__name__})")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    keys = ("wrapper_sha256", "forwarder_sha256")
    if len(lines) != 2:
        raise LaunchRefused(f"the expected-hashes file {path} is malformed: it must hold exactly the two lines "
                            "wrapper_sha256=<64 hex> and forwarder_sha256=<64 hex>")
    out = {}
    for key, line in zip(keys, lines):
        name, eq, val = line.partition("=")
        if name != key or not eq or not HEX64.fullmatch(val):
            raise LaunchRefused(f"the expected-hashes file {path} is malformed: line {len(out) + 1} must be "
                                f"{key}=<64 lower-case hex>")
        out[key] = val
    return out


def required_names(settings):
    learn = settings.get("SANDBOX_MODEL_LEARN") == "1"
    return tuple(n for n in REQUIRED_SANDBOX if not (learn and n == "SANDBOX_MODEL_ALLOW"))


def check_settings(settings, allow_test=False):
    """Refuse a missing or empty required SANDBOX_* setting, any setting the module owns, and (in a REAL run, the default) any
    test-mode setting: SANDBOX_TEST, SANDBOX_TEST_EXEC, the cap knobs, SANDBOX_TEST_ALLOW_BINARY_IN_RW and every other
    SANDBOX_TEST* name would put the student in a box that is not the registered one. A test run passes `allow_test=True`
    explicitly (the cells; p1-session only under P1_TEST_HOOKS=1). Returns a clean copy."""
    for n in required_names(settings):
        if not settings.get(n):
            raise LaunchRefused(f"{n} is not set or is empty (the wrapper requires it; it must be passed to the feeder "
                                "as an --env pair, an exported variable never reaches it)")
    for n in MODULE_OWNED:
        if n in settings:
            raise LaunchRefused(f"{n} is set by the launch module for each launch; the caller may not supply it")
    if not allow_test:
        for n in sorted(settings):
            if n.startswith("SANDBOX_TEST"):
                raise LaunchRefused(f"{n} is a test-mode setting and is refused in a real run (the student would not be in the "
                                    "registered box); only a test run, which says so explicitly, may pass it")
    for n in settings:
        if not n.startswith("SANDBOX_"):
            raise LaunchRefused(f"{n} is not a SANDBOX_* setting")
    return dict(settings)


TEST_PREFIX_NAME = "SANDBOX_TEST_UNIT_PREFIX"
_PREFIX_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*-")


def unit_prefix(settings):
    """The prefix the wrapper names this launch's scope with: `student-sandbox-` in a real run (the only value there), or the
    test-only SANDBOX_TEST_UNIT_PREFIX, accepted ONLY together with SANDBOX_TEST=1 so that two test runs on one host can be
    told apart. A named refusal otherwise."""
    p = settings.get(TEST_PREFIX_NAME)
    if p is None:
        return UNIT_PREFIX
    if settings.get("SANDBOX_TEST") != "1":
        raise LaunchRefused(f"{TEST_PREFIX_NAME} is refused without SANDBOX_TEST=1: a real run names its scopes "
                            f"{UNIT_PREFIX}<pid>-<hex> and has no other prefix")
    if not _PREFIX_RE.fullmatch(p):
        raise LaunchRefused(f"{TEST_PREFIX_NAME} {p!r} is not a prefix (letters, digits, . _ - and a trailing -)")
    return p


def unit_name_re(prefix):
    """The wrapper's scope naming (SCOPE_UNIT in student-sandbox.sh): <prefix><wrapper pid>-<8 hex>, with `.scope` optional."""
    return re.compile(re.escape(prefix) + r"[0-9]+-[0-9a-f]+(\.scope)?")


class Sandbox:
    """What a launch needs besides the feeder call: the SANDBOX_* settings and the expected hashes."""
    def __init__(self, settings, expected_file, allow_test=False):
        self.allow_test = bool(allow_test)
        self.settings = check_settings(settings, self.allow_test)
        self.prefix = unit_prefix(self.settings)
        self.expected = load_expected(expected_file)
        self.expected_file = expected_file


# DEFAULT DENY on a feeder's argv (the security seat's recommendation). argparse (feed2.py's and feed4.py's parsers use its
# defaults) maps several spellings onto one option: `--opt=value` and any unambiguous prefix (`--en`, `--ou`, `--arm-hom`). The
# module's guards read only the exact `--flag VALUE` spelling (the PATH check, the model-URL check, the refusal of a caller's
# SANDBOX_* pair, the proctor binds), so any other spelling would be applied by the feeder and be invisible to them. Instead of
# listing the spellings to refuse, ONE dict names what a launcher may pass: {feeder basename: {exact long option: arity}}, and
# run_feeder refuses, named, before anything starts, any argv token that is not exactly an allowed option, the value of one,
# or (nothing else exists) anything at all. That covers `--env=K=V`, abbreviations, short flags and any option a feeder adds
# later, by construction. ARITY (0: a flag, 1: takes the next token as its value) is stated here and a cell checks it against
# the feeder's own add_argument call. A launcher that needs a new feeder option adds it here, in the PR that adds it, or its
# launch is refused (loud, by design).
# The options below are what the in-tree callers pass. feed4.py: exactly what p1-session.py passes (the answering run, the
# continue-reading run and both plan dumps). feed2.py: no in-tree launcher passes feed2 through the module yet, so this is the
# options the retired run-engram-full.sh used (--arm-home --out --conv --turns --first-session --setup-only --force-compact --ask)
# plus --env, which the module itself passes to every feeder. feed.py: no in-tree caller; its first-turn options only, and note
# that feed.py declares no --env, which the module passes, so feed.py cannot be launched through the module until it does.
FEEDER_OPTIONS = {
    "feed4.py": {"--arm-home": 1, "--out": 1, "--conv": 1, "--turns": 1, "--resume": 1, "--start": 1, "--per-round": 1,
                 "--question-file": 1, "--expect-components": 1, "--env": 1, "--force-compact": 0, "--dump-plan": 0},
    "feed2.py": {"--arm-home": 1, "--out": 1, "--conv": 1, "--turns": 1, "--first-session": 0, "--setup-only": 0,
                 "--force-compact": 0, "--ask": 1, "--env": 1},
    "feed.py": {"--arm-home": 1, "--out": 1, "--conv": 1, "--turns": 1},
}
_NEG_NUMBER = re.compile(r"-[0-9]+(\.[0-9]+)?")


def check_argv_options(argv, options, feeder):
    """Refuse (LaunchRefused, naming the token) any argv token that is not exactly an allowed option or the value of one.
    An option is told from a value by position: after an allowed option of arity 1 the next token is its value (it may not
    look like an option: a leading `-` is refused unless it is a plain negative number); after one of arity 0, or after a
    value, the next token must be an allowed option again. Nothing else is a token: a positional or an unknown option is
    refused."""
    expect_value = None
    for tok in argv:
        if expect_value is not None:
            if tok.startswith("-") and not _NEG_NUMBER.fullmatch(tok):
                raise LaunchRefused(f"the feeder argument {tok!r} follows {expect_value} but looks like an option, not a "
                                    f"value: {os.path.basename(feeder)} launches only take exact long options "
                                    f"({sorted(options)}) and their values")
            expect_value = None
            continue
        if tok in options:
            expect_value = tok if options[tok] == 1 else None
            continue
        raise LaunchRefused(f"the feeder argument {tok!r} is not an option {os.path.basename(feeder)} may be launched with "
                            f"through this module (exact long options only, no `--opt=value`, no abbreviation: "
                            f"{sorted(options)}); add a needed option to FEEDER_OPTIONS in the PR that needs it")
    if expect_value is not None:
        raise LaunchRefused(f"the feeder option {expect_value} has no value")


def env_pairs(argv):
    """The `--env KEY=VALUE` pairs in a feeder's argv, in order."""
    out = []
    for i, a in enumerate(argv):
        if a == "--env" and i + 1 < len(argv):
            k, _, v = argv[i + 1].partition("=")
            out.append((k, v))
    return out


# The caller's `--env KEY=VALUE` pairs are an ALLOWLIST too. feed4.py / feed2.py Student.__init__ put every pair into the STUDENT's
# environment, which is the environment the shell-script wrapper runs in, so an unlisted key (BASH_ENV, LD_PRELOAD, NODE_OPTIONS,
# PATH, ...) would be a door past the built feeder environment. Only these keys may be passed by a caller; any other is refused BY
# NAME before anything starts (never silently dropped), PATH included (the PATH is built, build_feeder_path). The module's own
# SANDBOX_* pairs are added after this check and a caller's SANDBOX_* pair is refused. Derived from the callers, not guessed:
#   CLAUDE_CODE_MAX_CONTEXT_TOKENS   p1-session.py feed4_args() passes it (WINDOW); the value is digits only (check_env_pairs)
#   ANTHROPIC_BASE_URL               read by model_url() below and matched against MODEL_URL_RE before launch
# A key added here is a name a caller can steer the student with: add one only on the design owner's ruling, by name, here and in the
# pinned literal of tests/test_sandbox_launch.py.
CONTEXT_TOKENS_KEY = "CLAUDE_CODE_MAX_CONTEXT_TOKENS"
FEEDER_ENV_PAIR_ALLOW = (CONTEXT_TOKENS_KEY, "ANTHROPIC_BASE_URL")
_DIGITS_RE = re.compile(r"[0-9]+")   # ASCII digits only (not \d: no other script's digits), matched whole (fullmatch: no trailing newline)


def check_env_pairs(argv):
    """Refuse, before anything starts and naming the key, any caller `--env` pair that is not allowed: a SANDBOX_* key (the module
    passes its own), a key outside FEEDER_ENV_PAIR_ALLOW, a CLAUDE_CODE_MAX_CONTEXT_TOKENS value that is not a positive integer
    written in digits. (An ANTHROPIC_BASE_URL value is checked by check_model_url.)"""
    for k, v in env_pairs(argv):
        if k.startswith("SANDBOX_"):
            raise LaunchRefused(f"{k} is passed to the feeder by the launch module only, not by the caller")
        if k not in FEEDER_ENV_PAIR_ALLOW:
            raise LaunchRefused(f"--env {k!r} is refused: a caller may pass only {list(FEEDER_ENV_PAIR_ALLOW)} to the student's "
                                "environment (the PATH is built by the module, never passed)")
        if k == CONTEXT_TOKENS_KEY and not (_DIGITS_RE.fullmatch(v) and int(v) > 0):
            raise LaunchRefused(f"--env {k} value {v!r} is refused: digits only, a positive integer (no sign, no space)")


def argv_value(argv, flag):
    for i in range(len(argv) - 2, -1, -1):
        if argv[i] == flag:
            return argv[i + 1]
    return None


def model_url(argv, env):
    """The URL the student will use, as the feeder resolves it: an `--env ANTHROPIC_BASE_URL=` pair (the last wins, as in
    Student.__init__), else feed.py's OLLAMA_URL = BEAM_OLLAMA_URL else the default."""
    url = None
    for k, v in env_pairs(argv):
        if k == "ANTHROPIC_BASE_URL":
            url = v
    return url if url is not None else (env.get("BEAM_OLLAMA_URL") or OLLAMA_DEFAULT)


# The model URL the student will use is accepted ONLY in this strict form: http, a loopback host, an explicit port, and an
# optional plain path. No userinfo, no backslash, no percent-escape, no query, no fragment, no other scheme. A parser
# differential is the reason: `http://evil.com\\@127.0.0.1/v1` (with a port) has the host 127.0.0.1 for Python's urlsplit and evil.com
# for the WHATWG parser the student (a Node program) uses, so the module does not parse a URL, it matches this pattern.
MODEL_URL_RE = re.compile(r"http://(127\.0\.0\.1|localhost|\[::1\]):([0-9]{1,5})(/[A-Za-z0-9._~/-]*)?")


def check_model_url(url, port):
    m = MODEL_URL_RE.fullmatch(url)
    if not m:
        raise LaunchRefused(f"the model URL the student will use ({url!r}) is not of the strict form "
                            "http://(127.0.0.1|localhost|[::1]):<port>[/path]: a host that is not loopback, userinfo, a backslash, "
                            "a percent-escape, a query, a fragment, another scheme or a missing port are all refused")
    try:
        want = int(port)
    except ValueError:
        raise LaunchRefused(f"SANDBOX_MODEL_PORT {port!r} is not a number")
    if int(m.group(2)) != want:
        raise LaunchRefused(f"the model URL the student will use ({url}) has port {int(m.group(2))}, not SANDBOX_MODEL_PORT {port}")


# The PATH the feeder (and so the student session) sees is BUILT by the module, never inherited from the caller: the directory of
# the wrapper this launch prepared first, then this ONE fixed list of system directories. This list is a FLOOR for the wrapper's
# children (the system tools they may reach), NOT the security line: the line is the assertion in run_feeder that `claude`
# resolves, under the built path, to the wrapper this launch prepared (check_claude_first), together with the guard that no other
# directory of the path holds an executable `claude` (check_no_other_claude). So widening this list moves what the children can
# reach, and never what `claude` means. A directory outside it that a session turns out to need is added here, by name, on the
# design owner's ruling, and nowhere else.
FEEDER_SYSTEM_DIRS = ("/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin")


# The feeder's ENVIRONMENT is built too: only the names below reach it, from the caller's environment, and nothing else is
# inherited (so LD_PRELOAD, LD_LIBRARY_PATH, BASH_ENV, NODE_OPTIONS and every other name are simply absent; this is an allowlist,
# never a deny-list). Derived from what the code reads, not guessed:
#   BEAM_OLLAMA_URL   feed.py `OLLAMA_URL = os.environ.get("BEAM_OLLAMA_URL", ...)` (imported by feed2.py and feed4.py), and this
#                     module's own model_url() check of the URL the student will use
#   BEAM_PARQUET      feed.py data_path() `os.environ.get("BEAM_PARQUET")`, the dataset the feeders read
# PATH is not a name to pass: it is built (build_feeder_path). Nothing else in the feeders, the wrapper or the forwarder reads the
# FEEDER's environment: feed.py/feed2.py/feed4.py Student.__init__ build the student's environment from scratch (PATH, HOME,
# TERM, LANG, ... and the `--env` pairs), and the wrapper and the forwarder run inside THAT environment. A name added here is a
# name a caller's shell can steer the feeder with: add one only on the design owner's ruling, by name, here and in the pinned
# literal of tests/test_sandbox_launch.py.
FEEDER_ENV_ALLOW = ("BEAM_OLLAMA_URL", "BEAM_PARQUET")


def build_feeder_env(caller_env, wrapper_dir, extra_names=()):
    """The feeder's whole environment: the allowlisted names present in `caller_env` (plus `extra_names`, a test seam that
    run_feeder accepts only for a test stub), and the built PATH. Nothing else of `caller_env` is in it."""
    out = {k: caller_env[k] for k in (*FEEDER_ENV_ALLOW, *extra_names) if k in caller_env}
    out["PATH"] = build_feeder_path(wrapper_dir)
    return out


def build_feeder_path(wrapper_dir):
    """The built PATH: the wrapper's directory, then FEEDER_SYSTEM_DIRS. Nothing of the caller's environment is in it."""
    return os.pathsep.join((wrapper_dir, *FEEDER_SYSTEM_DIRS))


def resolve_on_path(name, path, cwd):
    """The file Popen([name], env={'PATH': path}, cwd=cwd) would start: the first executable regular file among the PATH
    entries in order (an empty entry is the child's working directory). The candidate is joined, never normalised: exec hands
    the path to the kernel, which follows a symlink and THEN applies `..`, so a lexical normpath would name a different file
    from the one that runs (`<d>/L/../wd` with L a symlink is not `<d>/wd`)."""
    for d in path.split(os.pathsep):
        cand = os.path.join(d if os.path.isabs(d) else (os.path.join(cwd, d) if d else cwd), name)   # empty entry: the cwd itself
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def _feeder_path(argv, env, feeder):
    """(the PATH the feeder's Popen will see, the working directory it resolves an empty or relative entry against). The feeder
    builds it as its own PATH (the built one) + `:` + its directory; a caller's `--env PATH=` never gets here (refused by
    the key check, run_feeder)."""
    path = env["PATH"] + ":" + os.path.dirname(os.path.abspath(feeder))   # what Student.__init__ builds
    home = argv_value(argv, "--arm-home")
    cwd = os.path.join(os.getcwd(), home, "work") if home else os.getcwd()   # as the child's chdir resolves it: no lexical abspath
    return path, cwd


def check_claude_first(wrapper_path, argv, env, feeder):
    """The assertion that is the security line: under the PATH the feeder will see (the built one, with what the feeder appends),
    `claude` resolves to the wrapper this launch prepared, or the launch is refused before anything starts."""
    path, cwd = _feeder_path(argv, env, feeder)
    got = resolve_on_path("claude", path, cwd)
    if got is None or not os.path.samefile(got, wrapper_path):
        raise LaunchRefused(f"the `claude` first on the PATH the feeder will see is {got or 'not found'}, not the sandbox "
                            f"wrapper this launch prepared ({wrapper_path})")


def check_no_other_claude(wrapper_path, path, cwd):
    """Popen falls through to the NEXT `claude` on the PATH when the first cannot exec (a missing interpreter, an invalid
    format), with no error, which would start a student unwrapped. So no directory of `path` other than the wrapper's own may hold
    an executable regular file named `claude` (the same file rules as resolve_on_path; an empty entry is `cwd`). This is safe
    because the wrapper starts the real binary from SANDBOX_BINARY, an absolute path, and never needs `claude` on the PATH. The
    refusal names each such directory of the built PATH; the caller cannot edit that PATH, so it says the fixed directory list is
    the design owner's to change."""
    others = []
    for d in path.split(os.pathsep):
        cand = os.path.join(d if os.path.isabs(d) else (os.path.join(cwd, d) if d else cwd), "claude")   # as resolve_on_path
        if os.path.isfile(cand) and os.access(cand, os.X_OK) and not os.path.samefile(cand, wrapper_path):
            if os.path.dirname(cand) not in others:
                others.append(os.path.dirname(cand))
    if others:
        raise LaunchRefused("a second executable `claude` is on the PATH the feeder will see, in " + ", ".join(others)
                            + ": if the wrapper could not be exec'd, the next `claude` would start unwrapped. The PATH the feeder sees is "
                            + "built, not the caller's (the built PATH holds " + ("that directory" if len(others) == 1 else "those directories")
                            + "); the fixed list of directories is the design owner's to change")


def _prepare_dir():
    d = tempfile.mkdtemp(prefix="sandbox-launch-")
    try:
        w, f = os.path.join(d, "claude"), os.path.join(d, "sandbox-forward.py")
        shutil.copyfile(WRAPPER_SRC, w); os.chmod(w, 0o500)
        shutil.copyfile(FORWARDER_SRC, f); os.chmod(f, 0o400)
    except OSError:
        shutil.rmtree(d, ignore_errors=True)
        raise
    return d


def _fresh_log(log_dir):
    if not os.path.isdir(log_dir):
        raise LaunchRefused(f"the log directory {log_dir} does not exist")
    for _ in range(100):   # bounded: a naming scheme that keeps colliding is a named refusal, never a spin
        p = os.path.join(os.path.abspath(log_dir), f"sandbox-{next(_SEQ)}-{secrets.token_hex(4)}.log")
        if not os.path.lexists(p):
            return p
    raise LaunchRefused(f"no fresh SANDBOX_LOG name was found in {log_dir} after 100 tries")


def read_launch_hashes(log):
    """wrapper_sha256 and forwarder_sha256 from the log's launch line (the FIRST one, as read_launch_fields: one place parses
    the line); {} when there is none, None for a field the line lacks."""
    fields = read_launch_fields(log)
    if fields is None:
        return {}
    return {k: fields.get(k) for k in ("wrapper_sha256", "forwarder_sha256")}


def read_verdict(wrapper_dir, log):
    """Run `sandbox-forward.py log-verdict --log LOG` (the copy that ran). Returns (exit code, stdout line, stderr)."""
    r = subprocess.run([sys.executable, "-I", os.path.join(wrapper_dir, "sandbox-forward.py"), "log-verdict", "--log", log],
                       capture_output=True, text=True)
    return r.returncode, r.stdout.rstrip("\n"), r.stderr.strip()


# ------------------------------------------------------------------------------------------------------ teardown (round 2)
# The module's stop is the guarantee that no box or bridge outlives its session (design owner, 2026-11-20): a caller's
# SIGKILL has been seen not to end the box, and the mechanism is unproven. So after every session the module stops the
# launch's scope itself and then checks that NOTHING of the launch remains, by three positive markers the wrapper put on
# the launch line (never by a process-name search): the scope's own cgroup, the forwarder's pid AND start time, and the
# bridge socket path in any process's argv.
UNIT_PREFIX = "student-sandbox-"   # the wrapper names its scope units this way (SCOPE_UNIT in student-sandbox.sh)
LAUNCH_MARKERS = ("scope_unit", "forwarder_pid", "forwarder_start", "bridge_sock")
_SETTLE_S = 3.0   # how long a dying box and forwarder are given before they count as left over
_TERM_S = 3.0     # how long a terminated forwarder is given


class SystemctlError(Exception):
    pass


class LaunchMarkerError(Exception):
    pass


class LaunchLogUnreadable(Exception):
    """A launch log that EXISTS but cannot be read: nothing is known about whether its wrapper launched, so it is never
    read as 'the wrapper never launched' (read_launch_fields raises it; both callers turn it into a named refusal or stop)."""


def scope_name(unit):
    """systemctl takes a bare name as a .service; the wrapper's units are scopes (`systemd-run --scope --unit NAME`)."""
    return unit if unit.endswith(".scope") else unit + ".scope"


def _systemctl(*args, timeout=150):
    env = dict(os.environ, XDG_RUNTIME_DIR=os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid())
    try:
        return subprocess.run(["systemctl", "--user", *args], env=env, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SystemctlError(f"`systemctl --user {' '.join(args)}` could not run ({type(e).__name__})")


def read_launch_fields(log):
    """The key=value fields of the log's `wrapper-launch` line. THREE cases, told apart: the log is ABSENT (the wrapper refused
    before it made one: None); the log has NO launch line (a log the forwarder wrote alone: None); the log is PRESENT BUT
    UNREADABLE (permission, a directory, an I/O error: LaunchLogUnreadable, because nothing is known and it must never be
    closed as 'never launched'). Absent and no-line both answer None because the callers treat them the same (nothing to stop);
    only an unreadable log is a different answer."""
    try:
        text = open(log, "rb").read().decode("utf-8", "replace")
    except FileNotFoundError as e:
        if not os.path.lexists(log):   # absence is decided by lexists: a link that cannot be followed is PRESENT, not absent
            return None
        raise LaunchLogUnreadable(f"the launch log {log} exists but cannot be read ({type(e).__name__}): whether its wrapper "
                                  "launched is not known")
    except OSError as e:
        raise LaunchLogUnreadable(f"the launch log {log} exists but cannot be read ({type(e).__name__}): whether its wrapper "
                                  "launched is not known")
    for line in text.splitlines():
        if line.startswith("wrapper-launch "):
            return dict(tok.partition("=")[::2] for tok in line.split()[1:] if "=" in tok)
    return None


def launch_markers(fields):
    """The four teardown markers from a launch line's fields, strictly validated (the before-launch check uses this);
    LaunchMarkerError names what is missing."""
    missing = [k for k in LAUNCH_MARKERS if not fields.get(k)]
    if missing:
        raise LaunchMarkerError("the launch line lacks " + ", ".join(missing))
    try:
        pid, start = int(fields["forwarder_pid"]), int(fields["forwarder_start"])
    except ValueError:
        raise LaunchMarkerError("the launch line's forwarder_pid or forwarder_start is not a number")
    if pid <= 0 or start <= 0:
        raise LaunchMarkerError("the launch line's forwarder_pid or forwarder_start is not a real value")
    return {"scope_unit": fields["scope_unit"], "forwarder_pid": pid, "forwarder_start": start,
            "bridge_sock": fields["bridge_sock"]}


def partial_markers(fields):
    """The teardown's reading of a launch line: (markers, unchecked). `scope_unit` is the one marker the stop needs; the
    forwarder's pid and start time and the bridge socket path feed checks (ii) and (iii). A marker that is missing or not a
    real value (the wrapper writes forwarder_start=0 if the forwarder died before its start time could be read) is None, and
    `unchecked` says which check could not run: that is reported, never read as clean."""
    m = {"scope_unit": fields.get("scope_unit"), "forwarder_pid": None, "forwarder_start": None,
         "bridge_sock": fields.get("bridge_sock") or None}
    unchecked = []
    try:
        pid, start = int(fields.get("forwarder_pid", "")), int(fields.get("forwarder_start", ""))
        if pid > 0 and start > 0:
            m["forwarder_pid"], m["forwarder_start"] = pid, start
    except ValueError:
        pass
    if m["forwarder_pid"] is None:
        unchecked.append("check (ii) (the forwarder pid and start time) could not run: forwarder_pid or forwarder_start is "
                         f"missing or 0 on the launch line (forwarder_pid={fields.get('forwarder_pid')!r}, "
                         f"forwarder_start={fields.get('forwarder_start')!r})")
    if m["bridge_sock"] is None:
        unchecked.append("check (iii) (the bridge socket path in any argv) could not run: bridge_sock is missing on the launch line")
    return m, unchecked


def proc_start(pid):
    """/proc/<pid>/stat field 22 (start time, clock ticks since boot): a reused pid has another. None: the process is gone."""
    try:
        fields = open("/proc/%d/stat" % pid).read().rsplit(")", 1)[1].split()
        return None if fields[0] == "Z" else int(fields[19])   # a zombie holds nothing: it is a process that has ended
    except (OSError, IndexError, ValueError):
        return None


def argv_pids(path):
    """Pids (other than this process) that carry `path` as one whole argv element, from /proc."""
    out = []
    for d in os.listdir("/proc"):
        if d.isdigit() and int(d) != os.getpid():
            try:
                if path.encode() in open("/proc/%s/cmdline" % d, "rb").read().split(b"\0"):
                    out.append(int(d))
            except OSError:
                pass
    return out


def unit_pids(unit):
    """The pids in the unit's own cgroup (the cgroup path is read from the unit); [] when the unit is gone. FAIL CLOSED: an
    unreadable or missing `cgroup.procs` while the unit still exists is not clean, it is a SystemctlError naming the unit.
    Only a unit that has vanished between the two reads counts as empty."""
    unit = scope_name(unit)

    def control_group():
        r = _systemctl("show", "-p", "ControlGroup", "--value", unit)
        if r.returncode != 0:
            raise SystemctlError(f"`systemctl --user show {unit}` failed: {r.stderr.strip()}")
        return r.stdout.strip()

    cg = control_group()
    if not cg:
        return []
    try:
        return [int(x) for x in open("/sys/fs/cgroup%s/cgroup.procs" % cg).read().split()]
    except FileNotFoundError:
        if not control_group():   # the unit went away between the two reads: that is empty
            return []
        raise SystemctlError(f"cgroup.procs of {unit} is missing while the unit still exists (cgroup {cg}): its processes "
                             "cannot be listed, which is not the same as none")
    except (OSError, ValueError) as e:
        raise SystemctlError(f"cgroup.procs of {unit} cannot be read ({type(e).__name__}) while the unit still exists "
                             f"(cgroup {cg}): its processes cannot be listed, which is not the same as none")


def active_units(prefix=UNIT_PREFIX):
    """Every scope unit named under `prefix` that is not `inactive`: querying `systemctl --user list-units --type=scope --all
    '<prefix>*'` and keeping activating, active, deactivating and reloading units, and a `failed` unit that still has
    processes in its cgroup (an `inactive` or processless failed unit holds nothing)."""
    r = _systemctl("list-units", "--type=scope", "--all", "--no-legend", "--plain", prefix + "*")
    if r.returncode != 0:
        raise SystemctlError(f"`systemctl --user list-units` failed: {r.stderr.strip()}")
    out = []
    for line in r.stdout.splitlines():
        cols = line.split()
        if len(cols) < 3 or not cols[0].startswith(prefix):
            continue
        unit, state = cols[0], cols[2]
        if state == "inactive":
            continue
        if state == "failed" and not unit_pids(unit):
            continue
        out.append(unit)
    return out


def leftovers(m):
    """What of the launch described by markers `m` is still there: {pid: [why, ...]}. The three checks of the teardown; a
    check whose marker is None cannot run (see partial_markers: the caller reports that, never reads it as clean)."""
    left = {}
    for pid in unit_pids(m["scope_unit"]):                                  # (i) the scope's own cgroup
        left.setdefault(pid, []).append(f"still in the cgroup of scope {m['scope_unit']}")
    if m.get("forwarder_pid") is not None:                                  # (ii) the forwarder: same pid AND same start time
        if proc_start(m["forwarder_pid"]) == m["forwarder_start"]:
            left.setdefault(m["forwarder_pid"], []).append("the launch's outer forwarder (same pid and start time) is still alive")
    if m.get("bridge_sock"):                                                # (iii) the bridge socket path in any argv
        for pid in argv_pids(m["bridge_sock"]):
            left.setdefault(pid, []).append(f"its argv carries this launch's bridge_sock {m['bridge_sock']}")
    return left


def _settle(m, secs):
    deadline = time.time() + secs
    while True:
        left = leftovers(m)
        if not left or time.time() >= deadline:
            return left
        time.sleep(0.1)


def _describe(left):
    return "; ".join(f"pid {pid}: " + " and ".join(whys) for pid, whys in sorted(left.items()))


def teardown(m):
    """Stop the launch's scope FIRST (whatever the other markers say), then make sure nothing of it remains. Returns what is
    left ({} when clean). A missing forwarder or socket marker means a check could not run: the caller reports that."""
    _systemctl("stop", scope_name(m["scope_unit"]))   # the exit code is not read: a unit that is already gone is exactly the goal
    left = _settle(m, _SETTLE_S)
    pid = m.get("forwarder_pid")
    if pid is not None and pid in left and proc_start(pid) == m["forwarder_start"]:   # still the very process the launch started
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.kill(pid, sig)
            except OSError:
                pass
            end = time.time() + _TERM_S
            while proc_start(pid) == m["forwarder_start"] and time.time() < end:
                time.sleep(0.05)
            if proc_start(pid) != m["forwarder_start"]:
                break
        left = _settle(m, _SETTLE_S)
    return left


def _write_record(path, rec):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f, sort_keys=True)
    os.replace(tmp, path)


def check_before_launch(state_dir, prefix=UNIT_PREFIX):
    """B: refuse to launch while anything earlier is alive. Two positive markers, no process search: (1) every record in
    `state_dir` not marked done is re-checked with the teardown's three checks (a record whose session never wrote a launch
    line has nothing to check and is closed); (2) any user scope unit under the launch's prefix (`student-sandbox-` in a real
    run) that is not inactive. A record whose scope_unit is not a name this wrapper makes is refused, never stopped."""
    problems, count = [], 0
    try:
        for name in sorted(os.listdir(state_dir)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(state_dir, name)
            try:
                rec = json.load(open(path))
            except (OSError, ValueError):
                problems.append(f"the launch record {name} cannot be read"); count += 1
                continue
            if rec.get("state") == "done":
                continue
            try:
                fields = read_launch_fields(rec.get("log", ""))
            except LaunchLogUnreadable as e:
                problems.append(f"the earlier launch {name}: {e}; its record is left open, and nothing can be said about what it started")
                count += 1
                continue
            if fields is None:
                rec.update(state="done", note="no launch line in the log: the wrapper never launched, nothing to stop")
                _write_record(path, rec)
                continue
            try:
                m = launch_markers(fields)
            except LaunchMarkerError as e:
                problems.append(f"the earlier launch {name}: {e}"); count += 1
                continue
            if not unit_name_re(prefix).fullmatch(m["scope_unit"]):
                problems.append(f"the earlier launch {name} names scope_unit {m['scope_unit']!r}, which is not a unit this "
                                f"wrapper makes ({prefix}<pid>-<hex>): it is not touched")
                count += 1
                continue
            left = _settle(m, _SETTLE_S)
            if left:
                problems.append(f"the earlier launch {name} left something alive: {_describe(left)} (stop it with: "
                                f"systemctl --user stop {scope_name(m['scope_unit'])}; end a leftover pid you have confirmed is this "
                                "launch's own)")
                count += len(left)
            else:
                rec.update(m, state="done", note="found gone at a later launch")
                _write_record(path, rec)
        for unit in active_units(prefix):
            problems.append(f"the scope unit {unit} is active (stop it with: systemctl --user stop {unit})")
            count += 1
    except SystemctlError as e:
        raise LaunchRefused(f"cannot check for leftovers of earlier launches: {e}")
    if problems:
        err = LaunchRefused("refusing to launch while anything of an earlier launch is alive (leftovers found: %d): %s"
                            % (count, " | ".join(problems)))
        err.leftover_count = count
        raise err


def _close_launch(rec_path, rec, log, res, prefix=UNIT_PREFIX):
    """T: after the feeder returned (whatever its exit code). Returns None when the launch is torn down and its record is
    closed, else the LaunchStop that names what remains. A session whose wrapper wrote no launch line (it refused before
    launching) is told apart by exactly that: there is nothing to stop. Whenever a launch line names a scope_unit that is a
    unit this wrapper makes, that scope is stopped FIRST, whatever the other markers say and whether or not the record can be
    written; the three checks then run with what the line has, and a check that could not run is reported, never read as clean."""
    try:
        fields = read_launch_fields(log)
    except LaunchLogUnreadable as e:
        return LaunchStop(f"teardown: {e}; the launch record is left open and nothing of this launch was stopped or checked", res)
    if fields is None:
        try:
            rec.update(state="done", note="no launch line in the log: the wrapper refused before it launched, nothing to stop")
            _write_record(rec_path, rec)
        except OSError as e:
            return LaunchStop(f"teardown: nothing to stop (no launch line), but the launch record could not be closed ({e})", res)
        return None
    unit = fields.get("scope_unit")
    if not unit:
        return LaunchStop("teardown: the launch line has no scope_unit, so the launch's scope cannot be stopped by name", res)
    if not unit_name_re(prefix).fullmatch(unit):
        return LaunchStop(f"teardown: the launch line's scope_unit {unit!r} is not a unit this wrapper makes "
                          f"({prefix}<pid>-<hex>); it is NOT stopped", res)
    m, unchecked = partial_markers(fields)
    try:
        left = teardown(m)                 # the stop comes first inside; nothing before it can skip it
    except SystemctlError as e:
        return LaunchStop(f"teardown: {e}", res)
    rec_err = None
    try:
        rec.update({k: v for k, v in m.items() if v is not None})
        _write_record(rec_path, rec)
    except OSError as e:
        rec_err = e
    problems = []
    if left:
        problems.append(f"after `systemctl --user stop {scope_name(unit)}` something of this launch remains: {_describe(left)}")
    problems += unchecked
    if rec_err is not None:
        problems.append(f"the launch record {rec_path} could not be written ({type(rec_err).__name__}); the scope was stopped")
    if problems:
        return LaunchStop("teardown: " + "; ".join(problems), res)
    try:
        rec.update(state="done", note="torn down")
        _write_record(rec_path, rec)
    except OSError as e:
        return LaunchStop(f"teardown: the scope is stopped and nothing remains, but the record could not be closed ({e})", res)
    return None


def run_feeder(py, feeder, argv, *, sandbox=None, log_dir=None, log_path=None, state_dir=None, env=None, test_stub=False,
               stub_as="feed4.py", test_env_names=(), **run_kw):
    """Run `py -I feeder *argv`. See the module docstring. `sandbox` is a Sandbox for a student session; None only for a
    call that starts no student (`--dump-plan`). `log_dir` is where this session's SANDBOX_LOG is chosen (or `log_path`
    names it; it must not exist). `state_dir` (required for a student session, no default) holds one record per launch.
    `test_stub=True` lets a test substitute a stub script for a feeder (the P1_FEED4 hook, refused outside
    P1_TEST_HOOKS=1): the stub is wrapped like a feeder, so every check still runs on it, and its argv obeys the allow-list
    of the feeder it stands in for (`stub_as`, feed4.py by default). `test_env_names` (refused without `test_stub`) names further
    caller-environment variables a STUB needs to receive, on top of FEEDER_ENV_ALLOW.
    `py`, the interpreter that runs the feeder, is resolved against the CALLER's PATH, not the built one; only the feeder's
    children see the built PATH.
    Extra keyword arguments go to subprocess.run (stdout=...)."""
    if os.path.basename(feeder) not in FEEDERS and not test_stub:
        raise LaunchRefused(f"{feeder} is not one of the feeders {FEEDERS}")
    if test_env_names and not test_stub:
        raise LaunchRefused("test_env_names is a seam for a test stub only; a real feeder gets FEEDER_ENV_ALLOW and nothing else")
    env = dict(os.environ if env is None else env)
    argv = list(argv)
    check_argv_options(argv, FEEDER_OPTIONS[os.path.basename(feeder) if os.path.basename(feeder) in FEEDER_OPTIONS else stub_as],
                       feeder)
    if "--dump-plan" in argv:   # starts no student: no wrapper, no log
        return LaunchResult(subprocess.run([py, "-I", feeder, *argv], env=env, **run_kw).returncode)
    if sandbox is None:
        raise LaunchRefused("a feeder call that starts a student needs the sandbox (only --dump-plan runs without it)")
    if not state_dir:
        raise LaunchRefused("a student session needs a state directory for its launch record (the module has no default)")
    check_env_pairs(argv)
    out = argv_value(argv, "--out")
    if not out:
        raise LaunchRefused("the feeder's --out directory is not in its argv (the proctor binds are made from it)")
    out = os.path.abspath(out)
    if log_path is None:
        log_path = _fresh_log(log_dir if log_dir is not None else os.path.dirname(out))
    elif os.path.lexists(log_path):
        raise LaunchRefused(f"SANDBOX_LOG {log_path} already exists (one log per launch)")
    log_path = os.path.abspath(log_path)
    check_model_url(model_url(argv, env), sandbox.settings["SANDBOX_MODEL_PORT"])
    os.makedirs(state_dir, mode=0o700, exist_ok=True)
    check_before_launch(state_dir, sandbox.prefix)   # B: nothing of an earlier launch may be alive
    wdir = _prepare_dir()
    try:
        wrapper = os.path.join(wdir, "claude")
        got = {"wrapper_sha256": sha256_file(wrapper), "forwarder_sha256": sha256_file(os.path.join(wdir, "sandbox-forward.py"))}
        for k in ("wrapper_sha256", "forwarder_sha256"):   # M4b: the files this launch will use, before anything starts
            if got[k] != sandbox.expected[k]:
                raise LaunchRefused(f"{k} of the file this launch would use is {got[k]}, expected {sandbox.expected[k]} "
                                    f"(from {os.path.basename(sandbox.expected_file)})")
        fenv = build_feeder_env(env, wdir, test_env_names)   # built, not inherited: the caller's environment is read by name only
        check_claude_first(wrapper, argv, fenv, feeder)
        check_no_other_claude(wrapper, *_feeder_path(argv, fenv, feeder))
        os.makedirs(os.path.join(out, "proctor"), exist_ok=True)
        tools = os.path.dirname(os.path.abspath(feeder))
        pairs = dict(sandbox.settings)
        pairs.update(SANDBOX_LOG=log_path, SANDBOX_RO_BINDS=tools, SANDBOX_RO_ROOT=os.path.dirname(tools),
                     SANDBOX_RW_BINDS=os.path.join(out, "proctor"), SANDBOX_RW_ROOT=out)
        extra = [x for k, v in pairs.items() for x in ("--env", f"{k}={v}")]
        # the record is written BEFORE the session starts, so a caller that is killed leaves it open for the next launch
        rec_path = os.path.join(state_dir, os.path.basename(log_path)[:-len(".log")] + ".json")
        rec = {"state": "open", "log": log_path, "feeder": os.path.basename(feeder)}
        _write_record(rec_path, rec)
        res = LaunchResult(None, log=log_path)
        res.feeder_path, res.feeder_env_names = fenv["PATH"], sorted(fenv)
        try:
            res.returncode = subprocess.run([py, "-I", feeder, *argv, *extra], env=fenv, **run_kw).returncode
        except BaseException as exc:   # a feeder that could not run, or was interrupted: still torn down
            td = _close_launch(rec_path, rec, log_path, res, sandbox.prefix)
            if td is not None and hasattr(exc, "add_note"):
                exc.add_note(str(td))
            raise
        td = _close_launch(rec_path, rec, log_path, res, sandbox.prefix)   # T: the log is final once the launch is torn down
        vs = None
        try:
            rc, line, err = read_verdict(wdir, log_path)
            if rc != 0:
                raise LaunchStop(f"log-verdict refused (exit {rc}): {err or 'no message'}; the session is not read", res)
            if line != VERDICT_NOT_FLAGGED and not line.startswith(VERDICT_FLAGGED_PREFIX):
                raise LaunchStop(f"log-verdict printed an unrecognised line {line!r}; it is not read as not-flagged", res)
            res.verdict = line
            launched = read_launch_hashes(log_path)
            res.wrapper_sha256, res.forwarder_sha256 = launched.get("wrapper_sha256"), launched.get("forwarder_sha256")
            lf = read_launch_fields(log_path) or {}
            res.test_mode, res.test_exec = lf.get("test_mode"), lf.get("test_exec")
            res.caps = {k: v for k, v in sorted(lf.items()) if k.startswith("cap_")}
            if not sandbox.allow_test and (res.test_mode != "0" or res.test_exec != "0"):   # read off the line, fail closed
                raise LaunchStop(f"the launch line says test_mode={res.test_mode} test_exec={res.test_exec} in a real run: the "
                                 "student ran in a test-mode box, not the registered one; no answer of this session is read", res)
            for k in ("wrapper_sha256", "forwarder_sha256"):
                if res.__dict__[k] != sandbox.expected[k]:
                    raise LaunchStop(f"the launch line's {k} is {res.__dict__[k]}, expected {sandbox.expected[k]}: what ran "
                                     "is not what was registered; no answer of this session is read", res)
        except LaunchStop as e:
            vs = e
        except LaunchLogUnreadable as e:
            vs = LaunchStop(f"{e}; no answer of this session is read", res)
        if td is not None:
            raise LaunchStop(str(td) + (f"; also: {vs}" if vs else ""), res) from None
        if vs is not None:
            raise vs
        return res
    finally:
        shutil.rmtree(wdir, ignore_errors=True)
