"""Resource safety controls for local MLX jobs.

This module is deliberately self-contained (stdlib only, no package-relative
imports) because it is also executed directly as a watchdog subprocess::

    .venv/bin/python -m language_tutor.safety watchdog --pid ... --start ...

Resource guarantees implemented here:

* available memory is computed from ``vm_stat`` ``free + inactive`` pages using
  the page size reported in the ``vm_stat`` header (never assumed to be 16384);
  a machine that sets ``LANGUAGE_TUTOR_COUNT_FILE_CACHE=1`` also counts
  ``speculative`` pages (reclaimable read-ahead file cache, which grows by the
  size of every model file read);
* ``preflight`` refuses a job that needs more than 8GB or longer than 1800s
  without an explicit grant, that would drop available memory below
  ``ceiling + 6GiB``, that would run with swap already above 90%, or that would
  run while a competing MLX/attribution job is active;
* the Seagate volume is verified to be a *actually mounted* APFS/HFS volume,
  writable and with enough free space, **before** any directory is created;
* ``MLXGuard`` takes an atomic cross-process own-job lock under the project's
  ``.local/`` directory, runs the preflight *before* importing MLX, applies
  hard memory/cache limits, logs per-step memory and clears the MLX cache, and
  releases everything on exit;
* a separate watchdog process kills **only** the guarded PID, and only when its
  start-time fingerprint still matches, when available memory drops below 3GiB,
  swap exceeds 95%, or the deadline passes.

Collection and decision logic is split into pure, injectable functions
(``read_vm_stat``, ``read_swap``, ``list_processes``, ``detect_conflicts``,
``snapshot``, ``decide_watchdog_action``) so the refusal and cleanup paths can
be tested without a GPU, without MLX, and without putting the host under
memory pressure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

__all__ = [
    "DEFAULT_LOCK_PATH",
    "GIB",
    "LOCAL_DIR",
    "SEAGATE_MOUNT",
    "JobLock",
    "MLXGuard",
    "SafetyError",
    "WatchdogConfig",
    "decide_watchdog_action",
    "detect_conflicts",
    "list_processes",
    "preflight",
    "process_start_token",
    "read_swap",
    "read_vm_stat",
    "secure_dir",
    "snapshot",
    "verify_secure_mount",
    "watchdog_run",
]

GIB = 1024**3
MIB = 1024**2

#: Verified Seagate volume location.
SEAGATE_MOUNT = "/Volumes/Seagate Portable Drive"
#: Filesystems accepted for MLX work; exFAT (``/Volumes/Exchange``) is rejected.
ACCEPTED_FILESYSTEMS = frozenset({"apfs", "hfs", "hfs+"})

#: Repo root derived from this file: <root>/src/language_tutor/safety.py
# Vendored from language-tutor safety.py for this bounded benchmark runner.
# Original AGPL project attribution retained; only the default project root changes.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
#: Project-local (gitignored) runtime state directory.
LOCAL_DIR = PROJECT_ROOT / ".local"
DEFAULT_LOCK_PATH = LOCAL_DIR / "mlx_job.lock"
DEFAULT_LOG_PATH = LOCAL_DIR / "mlx_job.log.jsonl"

#: Default preflight ceilings; larger jobs require an explicit grant.
DEFAULT_MAX_MEMORY_GB = 8.0
DEFAULT_MAX_DURATION_S = 1800
DEFAULT_RESERVE_GB = 6.0
DEFAULT_SWAP_LIMIT = 0.90

#: Watchdog hard floors.
WATCHDOG_MIN_AVAILABLE_BYTES = 3 * GIB
WATCHDOG_SWAP_LIMIT = 0.95

_CMD_TIMEOUT_S = 15.0


class SafetyError(RuntimeError):
    """Raised when a resource-safety gate refuses to proceed."""


# --------------------------------------------------------------------------- #
# Collection primitives (all accept injected raw text for testing)
# --------------------------------------------------------------------------- #


def _run(argv: list[str], *, timeout: float = _CMD_TIMEOUT_S) -> str:
    """Run a command and return stdout, raising SafetyError on failure."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - host specific
        raise SafetyError(f"failed to run {argv[0]!r}: {exc}") from exc
    if proc.returncode != 0:
        raise SafetyError(f"{argv[0]!r} exited {proc.returncode}: {proc.stderr.strip()}")
    return proc.stdout


_VM_PAGE_RE = re.compile(r"page size of (\d+) bytes")
# ``vm_stat`` prints one "Pages <name>: <count>." line per row, after the header
# line, so the anchors need MULTILINE.
_VM_PAGES_RE = re.compile(
    r"^Pages (free|inactive|speculative|active|wired down):\s+(\d+)\.", re.MULTILINE
)


def read_vm_stat(text: str | None = None, *, count_speculative: bool | None = None) -> dict:
    """Parse ``vm_stat``.

    Returns ``page_size``, ``free_bytes``, ``inactive_bytes`` and
    ``available_bytes`` where available memory is computed as:
    ``(free + inactive) * page_size`` using the page size reported in the
    header (not an assumed 16384).  ``count_speculative`` adds speculative
    pages; when ``None`` it follows ``LANGUAGE_TUTOR_COUNT_FILE_CACHE`` (an
    environment variable so the watchdog subprocess inherits it).

    ``text`` is the raw ``vm_stat`` output; when ``None`` the command is run.
    """
    if text is None:
        text = _run(["vm_stat"])
    if count_speculative is None:
        count_speculative = os.environ.get("LANGUAGE_TUTOR_COUNT_FILE_CACHE") == "1"

    page_match = _VM_PAGE_RE.search(text)
    if page_match is None:
        raise SafetyError("vm_stat output lacks a page-size header; cannot compute memory")
    page_size = int(page_match.group(1))
    if page_size <= 0:  # pragma: no cover - defensive
        raise SafetyError(f"invalid vm_stat page size {page_size}")

    pages: dict[str, int] = {}
    for name, value in _VM_PAGES_RE.findall(text):
        pages[name.replace(" ", "_")] = int(value)
    if "free" not in pages or "inactive" not in pages:
        raise SafetyError("vm_stat output lacks free/inactive page counts")

    free_bytes = pages["free"] * page_size
    inactive_bytes = pages["inactive"] * page_size
    speculative_bytes = pages.get("speculative", 0) * page_size if count_speculative else 0
    return {
        "page_size": page_size,
        "pages_free": pages["free"],
        "pages_inactive": pages["inactive"],
        "free_bytes": free_bytes,
        "inactive_bytes": inactive_bytes,
        "available_bytes": free_bytes + inactive_bytes + speculative_bytes,
    }


_SWAP_RE = re.compile(r"total\s*=\s*([0-9.]+)([KMGTP]?)\s+used\s*=\s*([0-9.]+)([KMGTP]?)")
_SWAP_UNITS = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}


def read_swap(text: str | None = None) -> dict:
    """Parse ``sysctl vm.swapusage`` into byte counts plus a used fraction.

    ``available_bytes``-style raw output is tiny (``vm.swapusage: total = ...``),
    so a missing/garbled line raises ``SafetyError`` rather than guessing.
    """
    if text is None:
        text = _run(["sysctl", "-n", "vm.swapusage"])

    match = _SWAP_RE.search(text)
    if match is None:
        raise SafetyError("cannot parse vm.swapusage output; refusing to guess swap use")
    total = float(match.group(1)) * _SWAP_UNITS[match.group(2).upper()]
    used = float(match.group(3)) * _SWAP_UNITS[match.group(4).upper()]
    total_bytes = int(total)
    used_bytes = int(used)
    fraction = (used_bytes / total_bytes) if total_bytes > 0 else 0.0
    return {
        "swap_total_bytes": total_bytes,
        "swap_used_bytes": used_bytes,
        "swap_used_fraction": fraction,
    }


_PS_RE = re.compile(r"^\s*(\d+)\s+(.*)$")


def list_processes(text: str | None = None) -> list[dict]:
    """Parse ``ps -axo pid=,command=`` into ``[{"pid": int, "command": str}]``."""
    if text is None:
        text = _run(["ps", "-axo", "pid=,command="])

    processes: list[dict] = []
    for line in text.splitlines():
        match = _PS_RE.match(line)
        if match is None:
            continue
        processes.append({"pid": int(match.group(1)), "command": match.group(2).strip()})
    return processes


#: Patterns that indicate a competing local GPU job.
COMPETING_PATTERNS: tuple[str, ...] = (
    r"qwen38-attribution",
    r"03_openrouter_generate",
    r"10_generate_adversaries",
    r"mlx_lm[./]",
    r"\bmlx-lm\b",
    r"\bmlx_whisper\b",
    r"--mem-limit-gb",
    r"--batch-size",
    r"\blora\b",
    r"language[-_]tutor.*(?:mlx|--batch)",
)
_COMPETING_RE = re.compile("|".join(COMPETING_PATTERNS), re.IGNORECASE)
#: Never flag our own watchdog or the ``ps``/``grep`` invocations themselves.
_EXCLUDE_RE = re.compile(r"(?:--watchdog\b|test_safety\.py|/safety\.py\s+watchdog)", re.IGNORECASE)


def detect_conflicts(processes: list[dict], *, own_pids: set[int] | None = None) -> list[dict]:
    """Return competing MLX/attribution jobs as ``{"pid", "command", "reason"}``.

    ``own_pids`` (this process, its watchdog and its ancestors) are excluded: a
    process that spawned this job is not competing with it.
    """
    excluded = set(own_pids or ())
    conflicts: list[dict] = []
    for proc in processes:
        pid = proc.get("pid")
        command = proc.get("command", "") or ""
        if pid is None or pid in excluded:
            continue
        if _EXCLUDE_RE.search(command):
            continue
        match = _COMPETING_RE.search(command)
        if match is not None:
            conflicts.append({"pid": pid, "command": command, "reason": match.group(0)})
    return conflicts


def _ancestor_pids() -> set[int]:
    """Best-effort ancestor chain of the current process (for conflict exclusion)."""
    pids: set[int] = set()
    pid = os.getpid()
    for _ in range(16):
        try:
            ppid = int(_run(["ps", "-o", "ppid=", "-p", str(pid)]).strip() or 0)
        except (SafetyError, ValueError):
            break
        if ppid <= 1 or ppid in pids:
            break
        pids.add(ppid)
        pid = ppid
    return pids


def snapshot(
    *,
    vm_stat_text: str | None = None,
    swap_text: str | None = None,
    ps_text: str | None = None,
    ps_data: list[dict] | None = None,
) -> dict:
    """One consistent view of host memory, swap and competing jobs.

    Keys: ``available_bytes``, ``swap_used_fraction``, ``conflicts`` (list of
    ``{"pid", "command", "reason"}``), plus ``free_bytes``, ``inactive_bytes``,
    ``page_size``, ``swap_total_bytes``, ``swap_used_bytes``, ``own_pid`` and
    ``captured_at``.
    """
    vm = read_vm_stat(vm_stat_text)
    swap = read_swap(swap_text)
    processes = ps_data if ps_data is not None else list_processes(ps_text)
    own = _ancestor_pids() | {os.getpid()} if ps_data is None else {os.getpid()}
    return {
        "captured_at": time.time(),
        "page_size": vm["page_size"],
        "free_bytes": vm["free_bytes"],
        "inactive_bytes": vm["inactive_bytes"],
        "available_bytes": vm["available_bytes"],
        "swap_total_bytes": swap["swap_total_bytes"],
        "swap_used_bytes": swap["swap_used_bytes"],
        "swap_used_fraction": swap["swap_used_fraction"],
        "conflicts": detect_conflicts(processes, own_pids=own),
        "own_pid": os.getpid(),
    }


# --------------------------------------------------------------------------- #
# Pre-flight gate (8GB / 1800s approval boundaries)
# --------------------------------------------------------------------------- #


def preflight(
    memory_gb: float = 6.0,
    duration_s: int = 900,
    *,
    allow_over_8gb: bool = False,
    allow_over_30min: bool = False,
    snapshot_data: dict | None = None,
    max_memory_gb: float = DEFAULT_MAX_MEMORY_GB,
    max_duration_s: int = DEFAULT_MAX_DURATION_S,
    reserve_gb: float = DEFAULT_RESERVE_GB,
    swap_limit: float = DEFAULT_SWAP_LIMIT,
) -> dict:
    """Refuse to start a local job unless every safety gate passes.

    Raises :class:`SafetyError` when:

    * ``memory_gb > max_memory_gb`` (default 8GB) without ``allow_over_8gb``;
    * ``duration_s > max_duration_s`` (default 1800s) without ``allow_over_30min``;
    * available memory (``vm_stat`` free + inactive) is below
      ``memory_gb + reserve_gb`` (default 6GiB);
    * swap is already above ``swap_limit`` (default 90%);
    * a competing MLX/attribution job is running.

    Returns a plan dict on success. ``snapshot_data`` injects a pre-collected
    :func:`snapshot` result (used by tests and by :class:`MLXGuard`, which takes
    exactly one snapshot per gate).
    """
    if memory_gb <= 0:
        raise SafetyError(f"memory_gb must be positive, got {memory_gb!r}")
    if duration_s <= 0:
        raise SafetyError(f"duration_s must be positive, got {duration_s!r}")
    if memory_gb > max_memory_gb and not allow_over_8gb:
        raise SafetyError(
            f"refusing {memory_gb:g}GB: above the {max_memory_gb:g}GB ceiling without an "
            "explicit grant (approval is required over 8GB)"
        )
    if duration_s > max_duration_s and not allow_over_30min:
        raise SafetyError(
            f"refusing {duration_s}s: above the {max_duration_s}s ceiling without an "
            "explicit grant (approval is required over 30 minutes)"
        )

    snap = snapshot_data if snapshot_data is not None else snapshot()
    available = int(snap["available_bytes"])
    required = round(memory_gb * GIB) + round(reserve_gb * GIB)
    swap_fraction = float(snap["swap_used_fraction"])
    conflicts = list(snap["conflicts"])

    if available < required:
        raise SafetyError(
            f"insufficient available memory: {available / GIB:.2f}GiB available "
            f"< required {required / GIB:.2f}GiB ({memory_gb:g}GB ceiling + "
            f"{reserve_gb:g}GiB reserve)"
        )
    if swap_fraction > swap_limit:
        raise SafetyError(
            f"swap use {swap_fraction:.1%} exceeds the {swap_limit:.0%} gate; refusing to start"
        )
    if conflicts:
        described = "; ".join(f"pid {c['pid']} ({c['reason']})" for c in conflicts)
        raise SafetyError(
            f"competing local GPU job(s) detected: {described}; wait and retry instead of "
            "stopping another project's process"
        )

    return {
        "memory_gb": float(memory_gb),
        "memory_limit_bytes": round(memory_gb * GIB),
        "duration_s": int(duration_s),
        "reserve_gb": float(reserve_gb),
        "required_bytes": required,
        "available_bytes": available,
        "swap_used_fraction": swap_fraction,
        "conflicts": conflicts,
        "grants": {"over_8gb": bool(allow_over_8gb), "over_30min": bool(allow_over_30min)},
        "captured_at": snap.get("captured_at"),
    }


# --------------------------------------------------------------------------- #
# Secure storage verification (no directory creation before verification)
# --------------------------------------------------------------------------- #

_MOUNT_RE = re.compile(r"^(?P<dev>\S+) on (?P<path>.*?) \((?P<opts>[^)]*)\)\s*$")


def _parse_mounts(text: str) -> list[dict]:
    mounts: list[dict] = []
    for line in text.splitlines():
        match = _MOUNT_RE.match(line.strip())
        if match is None:
            continue
        opts = [opt.strip() for opt in match.group("opts").split(",") if opt.strip()]
        mounts.append(
            {
                "device": match.group("dev"),
                "path": match.group("path"),
                "filesystem": opts[0].lower() if opts else "",
                "options": opts,
                "read_only": any(opt.lower() in {"read-only", "rdonly"} for opt in opts),
            }
        )
    return mounts


def verify_secure_mount(
    path: str = SEAGATE_MOUNT,
    *,
    min_free_gb: float = 50.0,
    mounts_text: str | None = None,
    statvfs_fn=None,
    require_ismount: bool | None = None,
) -> dict:
    """Verify ``path`` is a real, writable, accepted-filesystem mount with space.

    Fails closed (raises :class:`SafetyError`) when the path does not exist, is
    not present in the mount table (i.e. the volume is unmounted and a plain
    directory is sitting at ``/Volumes/...``), is not APFS/HFS, is mounted
    read-only, is not writable, or has less than ``min_free_gb`` free.

    **Nothing is created or modified** — callers must verify first and only then
    create subdirectories via :func:`secure_dir`.
    """
    target = Path(path)
    if mounts_text is None:
        mounts_text = _run(["mount"])
        if require_ismount is None:
            require_ismount = True
    if require_ismount is None:
        require_ismount = False

    entries = _parse_mounts(mounts_text)
    matches = [entry for entry in entries if entry["path"] == str(target)]
    if not matches:
        raise SafetyError(
            f"{target} is not a mounted volume (not in the mount table); refusing to use it "
            "and refusing to create a directory at an unmounted path"
        )
    entry = matches[0]
    if require_ismount and not os.path.ismount(target):
        raise SafetyError(f"{target} is in the mount table but os.path.ismount() is false")
    if not os.path.isdir(target):
        raise SafetyError(f"{target} is mounted but not a readable directory")

    filesystem = entry["filesystem"]
    if filesystem not in ACCEPTED_FILESYSTEMS:
        raise SafetyError(
            f"{target} is {filesystem or 'unknown'!r}; MLX work requires one of "
            f"{sorted(ACCEPTED_FILESYSTEMS)} (exFAT causes Metal GPU timeouts)"
        )
    if entry["read_only"]:
        raise SafetyError(f"{target} is mounted read-only")
    if not os.access(target, os.W_OK):
        raise SafetyError(f"{target} is not writable by this user")

    statvfs = statvfs_fn or os.statvfs
    try:
        st = statvfs(str(target))
    except OSError as exc:  # pragma: no cover - host specific
        raise SafetyError(f"cannot statvfs {target}: {exc}") from exc
    free_bytes = int(st.f_bavail) * int(st.f_frsize)
    min_free_bytes = round(min_free_gb * GIB)
    if free_bytes < min_free_bytes:
        raise SafetyError(
            f"{target} has {free_bytes / GIB:.1f}GiB free, below the required {min_free_gb:g}GiB"
        )

    return {
        "verified": True,
        "path": str(target),
        "device": entry["device"],
        "filesystem": filesystem,
        "read_only": False,
        "writable": True,
        "free_bytes": free_bytes,
        "min_free_bytes": min_free_bytes,
    }


def secure_dir(
    path: str = SEAGATE_MOUNT,
    *,
    subpath: str | None = None,
    min_free_gb: float = 50.0,
    create: bool = True,
    mounts_text: str | None = None,
    statvfs_fn=None,
) -> Path:
    """:func:`verify_secure_mount` first, *then* optionally create a subdirectory.

    Ordering is the point: the mount is proven before any ``mkdir``, so a missing
    or unmounted Seagate can never result in a stray directory on internal disk.
    """
    info = verify_secure_mount(
        path, min_free_gb=min_free_gb, mounts_text=mounts_text, statvfs_fn=statvfs_fn
    )
    root = Path(info["path"])
    if subpath and (Path(subpath).is_absolute() or '..' in Path(subpath).parts):
        raise SafetyError('subpath must be relative and may not traverse parents')
    target = root / subpath if subpath else root
    if not target.resolve().is_relative_to(root.resolve()):
        raise SafetyError('subpath escapes verified volume through a symlink')
    if create and subpath:
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SafetyError(f"cannot create {target} after verification: {exc}") from exc
    if not target.is_dir():
        raise SafetyError(f"{target} does not exist")
    return target


# --------------------------------------------------------------------------- #
# Own-job cross-process lock
# --------------------------------------------------------------------------- #


def process_start_token(pid: int) -> str | None:
    """Return a stable identity token for a live PID, or ``None`` if it is gone.

    The token is ``ps -o lstart=`` (second resolution). It exists so a reused PID
    is never mistaken for the process we started, which is what lets the watchdog
    kill safely.
    """
    if pid <= 1:
        return None
    try:
        out = _run(["ps", "-p", str(pid), "-o", "lstart="]).strip()
    except SafetyError:
        return None
    return out or None


@dataclass
class JobLock:
    """Atomic, cross-process "one MLX job of ours at a time" lock.

    The lock is an ``O_CREAT|O_EXCL`` file holding ``{"pid", "start_token",
    "created_at", "argv"}``. A lock is *stale* only when its recorded PID is
    gone or its start token no longer matches, in which case it is stolen
    exactly once per attempt. Anything unreadable older than
    ``stale_after_s`` is also treated as stale (crash recovery).
    """

    path: Path | str | os.PathLike = field(default_factory=lambda: DEFAULT_LOCK_PATH)
    stale_after_s: float = 600.0

    _fd: int | None = field(default=None, repr=False, compare=False)
    info: dict | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.path = Path(self.path)

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> dict:
        """Take the lock or raise :class:`SafetyError` if another job holds it."""
        if self.held:
            raise SafetyError(f"lock already held by this object ({self.path})")
        payload = {
            "pid": os.getpid(),
            "start_token": process_start_token(os.getpid()) or f"unknown-{time.time():.0f}",
            "created_at": time.time(),
            "argv": " ".join(sys.argv[:8]),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(2):
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                if attempt == 0 and self._try_steal():
                    continue
                holder = self._read()
                raise SafetyError(
                    f"another MLX job of ours holds the lock {self.path} "
                    f"(pid={holder.get('pid') if holder else '?'}); one MLX job at a time"
                ) from None
            else:
                os.write(fd, json.dumps(payload).encode())
                os.fsync(fd)
                self._fd = fd
                self.info = payload
                return payload
        raise SafetyError(f"could not acquire {self.path}")  # pragma: no cover

    def _read(self) -> dict | None:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def _try_steal(self) -> bool:
        """Remove the lock file iff its owner is provably gone. One shot."""
        info = self._read()
        if info is None:
            try:
                age = time.time() - self.path.stat().st_mtime
            except OSError:
                return False
            if age <= self.stale_after_s:
                return False
        else:
            owner = int(info.get("pid") or 0)
            token = process_start_token(owner)
            if token is not None and token == info.get("start_token"):
                return False  # owner is alive with the same start time: not stale
        try:
            self.path.unlink()
        except OSError:
            return False
        return True

    def release(self) -> None:
        """Release the lock (idempotent)."""
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:  # pragma: no cover - defensive
                pass
            self._fd = None
        if self.path.exists():
            holder = self._read()
            if holder and holder.get("pid") not in (os.getpid(), None):
                return  # someone else's lock; leave it alone
            try:
                self.path.unlink()
            except OSError:  # pragma: no cover - defensive
                pass
        self.info = None

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


# --------------------------------------------------------------------------- #
# Watchdog (separate process, guarded PID only, fingerprint verified)
# --------------------------------------------------------------------------- #


def decide_watchdog_action(
    metrics: dict,
    *,
    min_available_bytes: int = WATCHDOG_MIN_AVAILABLE_BYTES,
    swap_limit: float = WATCHDOG_SWAP_LIMIT,
    deadline_epoch: float | None = None,
    now: float | None = None,
) -> str:
    """Pure watchdog decision: ``"ok"`` or the kill reason.

    Precedence is deliberate: a blown deadline is the planned stop, then swap
    (system-wide pressure), then available memory.
    """
    now = time.time() if now is None else now
    if deadline_epoch is not None and now >= deadline_epoch:
        return "deadline"
    if float(metrics.get("swap_used_fraction", 0.0)) > swap_limit:
        return "swap"
    if int(metrics.get("available_bytes", 0)) < min_available_bytes:
        return "available_memory"
    return "ok"


@dataclass
class WatchdogConfig:
    """Configuration for :func:`watchdog_run` / the ``watchdog`` CLI."""

    pid: int
    start_token: str
    report_path: Path | str | os.PathLike | None = None
    poll_seconds: float = 5.0
    min_available_bytes: int = WATCHDOG_MIN_AVAILABLE_BYTES
    swap_limit: float = WATCHDOG_SWAP_LIMIT
    deadline_epoch: float | None = None
    grace_seconds: float = 5.0
    max_runtime_s: float = 3600.0

    def __post_init__(self) -> None:
        if self.report_path is not None:
            self.report_path = Path(self.report_path)

    def validate(self) -> None:
        if self.pid <= 1:
            raise SafetyError(f"refusing to watch pid {self.pid}")
        if self.pid == os.getpid():
            raise SafetyError("refusing to watch my own pid")
        if not self.start_token:
            raise SafetyError("start_token is required so a reused PID is never killed")
        if self.poll_seconds <= 0:
            raise SafetyError("poll_seconds must be positive")


def _write_report(cfg: WatchdogConfig, report: dict) -> None:
    if cfg.report_path is None:
        return
    try:
        path = Path(cfg.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(report), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:  # pragma: no cover - best effort reporting
        pass


def watchdog_run(
    cfg: WatchdogConfig,
    *,
    metrics_fn=None,
    kill_fn=None,
    token_fn=process_start_token,
    sleep_fn=time.sleep,
    now_fn=time.time,
) -> dict:
    """Watch the guarded PID and kill it only on a real safety breach.

    The kill path is fingerprint-gated: the PID is signalled only while
    ``token_fn(pid)`` still equals ``cfg.start_token``. A reused PID, a gone
    process, or a mismatched token degrades to *no kill* plus a report.
    """
    cfg.validate()
    metrics_fn = metrics_fn or (lambda: snapshot())
    kill_fn = kill_fn or _kill_process
    started = now_fn()
    report: dict = {
        "guarded_pid": cfg.pid,
        "start_token": cfg.start_token,
        "watchdog_pid": os.getpid(),
        "started_at": started,
        "deadline_epoch": cfg.deadline_epoch,
        "status": "ok",
        "reason": None,
        "metrics": None,
    }

    # The wall-clock budget below is authoritative; the iteration cap only exists
    # so a misbehaving injected clock/sleep can never spin this loop forever.
    max_iterations = max(1, int(cfg.max_runtime_s / cfg.poll_seconds) + 10)
    for _ in range(max_iterations):
        token = token_fn(cfg.pid)
        if token is None:
            report["status"], report["reason"] = "guarded_exited", "process gone"
            break
        if token != cfg.start_token:
            report["status"] = "stale_fingerprint"
            report["reason"] = f"pid {cfg.pid} reused: token {token!r} != {cfg.start_token!r}"
            break

        try:
            metrics = metrics_fn()
        except SafetyError as exc:
            report["status"], report["reason"] = "metrics_error", str(exc)
            break
        report["metrics"] = {
            "available_bytes": metrics.get("available_bytes"),
            "swap_used_fraction": metrics.get("swap_used_fraction"),
            "checked_at": now_fn(),
        }

        action = decide_watchdog_action(
            metrics,
            min_available_bytes=cfg.min_available_bytes,
            swap_limit=cfg.swap_limit,
            deadline_epoch=cfg.deadline_epoch,
            now=now_fn(),
        )
        if action != "ok":
            if token_fn(cfg.pid) != cfg.start_token:
                report["status"] = "stale_fingerprint"
                report["reason"] = "fingerprint changed before kill; not signalling"
                break
            killed = kill_fn(cfg.pid, cfg.grace_seconds, token_fn, cfg.start_token)
            report["status"] = "killed" if killed else "kill_failed"
            report["reason"] = action
            break

        if now_fn() - started > cfg.max_runtime_s:
            report["status"], report["reason"] = "watchdog_timeout", "max_runtime_s exceeded"
            break
        sleep_fn(cfg.poll_seconds)
    else:
        report["status"], report["reason"] = "watchdog_timeout", "iteration cap reached"

    _write_report(cfg, report)
    return report


def _kill_process(pid: int, grace_seconds: float, token_fn, expected_token: str) -> bool:
    """SIGTERM then SIGKILL ``pid``, re-checking its fingerprint before each step."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:  # pragma: no cover - permission issues
        return False
    deadline = time.time() + grace_seconds
    while time.time() < deadline:
        if token_fn(pid) is None:
            return True
        time.sleep(0.1)
    if token_fn(pid) != expected_token:
        return token_fn(pid) is None
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except OSError:  # pragma: no cover
        return False
    return True


# --------------------------------------------------------------------------- #
# MLXGuard
# --------------------------------------------------------------------------- #


def _default_mlx_factory():
    """Import ``mlx.core`` — called only *after* the preflight gate passes."""
    # Imported here on purpose: this must run only after the gate passes.
    import mlx.core as mx

    return mx


class MLXGuard:
    """Context manager enforcing the §2 rules around one MLX job.

    Usage from the runtime::

        with MLXGuard(memory_gb=6, cache_gb=0.5, duration_s=900) as g:
            out = g.mx.generate(...)   # mlx.core, already capped
            g.step()                   # per-step log + mx.clear_cache()

    Lifecycle: own-job lock → preflight (before any MLX import) → MLX import →
    hard limits → watchdog process. On exit (including on exception) the
    watchdog is stopped, the cache is cleared and the lock is released.
    """

    def __init__(
        self,
        memory_gb: float = 6.0,
        cache_gb: float = 0.5,
        duration_s: int = 900,
        *,
        allow_over_8gb: bool = False,
        allow_over_30min: bool = False,
        lock_path: str | os.PathLike | None = None,
        log_path: str | os.PathLike | None = None,
        storage_path: str | None = None,
        storage_min_free_gb: float = 50.0,
        watchdog: bool = True,
        watchdog_poll_s: float = 5.0,
        swap_limit: float = DEFAULT_SWAP_LIMIT,
        reserve_gb: float = DEFAULT_RESERVE_GB,
        log_every_steps: int = 1,
        preflight_fn=None,
        snapshot_fn=None,
        mlx_factory=_default_mlx_factory,
        watchdog_spawn=None,
    ) -> None:
        if cache_gb < 0:
            raise SafetyError(f"cache_gb must be >= 0, got {cache_gb!r}")
        if cache_gb > memory_gb:
            raise SafetyError(f"cache_gb ({cache_gb}GB) cannot exceed memory_gb ({memory_gb}GB)")
        self.memory_gb = float(memory_gb)
        self.cache_gb = float(cache_gb)
        self.duration_s = int(duration_s)
        self.allow_over_8gb = bool(allow_over_8gb)
        self.allow_over_30min = bool(allow_over_30min)
        self.lock_path = Path(lock_path) if lock_path else DEFAULT_LOCK_PATH
        self.log_path = Path(log_path) if log_path else DEFAULT_LOG_PATH
        self.storage_path = storage_path
        self.storage_min_free_gb = storage_min_free_gb
        self.watchdog_enabled = bool(watchdog)
        self.watchdog_poll_s = float(watchdog_poll_s)
        self.swap_limit = float(swap_limit)
        self.reserve_gb = float(reserve_gb)
        self.log_every_steps = max(1, int(log_every_steps))

        self._preflight_fn = preflight_fn or preflight
        self._snapshot_fn = snapshot_fn or snapshot
        self._mlx_factory = mlx_factory
        self._spawn = watchdog_spawn or _spawn_watchdog

        self.mx = None
        self.plan: dict | None = None
        self.lock: JobLock | None = None
        self.watchdog_pid: int | None = None
        self.watchdog_report_path: Path | None = None
        self.deadline_epoch: float | None = None
        self.steps = 0
        self._proc: subprocess.Popen | None = None
        self._entered = False

        self.memory_limit_bytes = round(self.memory_gb * GIB)
        self.cache_limit_bytes = round(self.cache_gb * GIB)

    # -- lifecycle --------------------------------------------------------- #

    def __enter__(self) -> Self:
        if self._entered:
            raise SafetyError("MLXGuard is not re-entrant")
        self._entered = True
        lock = JobLock(self.lock_path)
        try:
            lock.acquire()
            self.lock = lock

            if self.storage_path is not None:
                verify_secure_mount(self.storage_path, min_free_gb=self.storage_min_free_gb)

            snap = self._snapshot_fn()
            plan = self._preflight_fn(
                self.memory_gb,
                self.duration_s,
                allow_over_8gb=self.allow_over_8gb,
                allow_over_30min=self.allow_over_30min,
                snapshot_data=snap,
                swap_limit=self.swap_limit,
                # Only forwarded when changed, so injected preflight fakes keep working.
                **({'reserve_gb': self.reserve_gb}
                   if self.reserve_gb != DEFAULT_RESERVE_GB else {}),
            )
            self.plan = plan

            try:
                mx = self._mlx_factory()  # only reached after every gate passed
            except ImportError as exc:
                raise SafetyError(
                    f"MLX is unavailable ({exc}); install the MLX extra or run this step on a "
                    "machine with MLX before requesting a GPU job"
                ) from exc
            self._apply_limits(mx)
            self.mx = mx
            self.deadline_epoch = time.time() + self.duration_s

            if self.watchdog_enabled:
                self._start_watchdog()
            self._log(
                "guard_entered",
                memory_limit_bytes=self.memory_limit_bytes,
                cache_limit_bytes=self.cache_limit_bytes,
                available_bytes=plan["available_bytes"],
                duration_s=self.duration_s,
                watchdog_pid=self.watchdog_pid,
            )
        except BaseException:
            self._cleanup(entered_ok=False)
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._cleanup(entered_ok=True, error=exc)
        return False

    # -- limits / logging / steps ----------------------------------------- #

    def _apply_limits(self, mx) -> None:
        for name in ("set_memory_limit", "set_cache_limit"):
            if not callable(getattr(mx, name, None)):
                raise SafetyError(f"MLX is missing {name}(); refusing to run without hard caps")
        mx.set_memory_limit(self.memory_limit_bytes)
        mx.set_cache_limit(self.cache_limit_bytes)

    def _log(self, event: str, **fields) -> None:
        record = {"event": event, "ts": time.time(), "pid": os.getpid(), **fields}
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
        except OSError:  # pragma: no cover - logging must never break the job
            pass

    def _memory_metrics(self) -> dict:
        mx = self.mx
        active = (
            int(mx.get_active_memory()) if callable(getattr(mx, "get_active_memory", None)) else -1
        )
        peak = int(mx.get_peak_memory()) if callable(getattr(mx, "get_peak_memory", None)) else -1
        return {"active_bytes": active, "peak_bytes": peak}

    def step(self, label: str = "") -> dict:
        """Post-step hook: check the deadline, log memory, clear the MLX cache.

        Raises :class:`SafetyError` if the deadline has passed, if active memory
        is at or above the configured limit (a climbing peak is a leak), or if
        the watchdog process has died unexpectedly.
        """
        if not self._entered or self.mx is None:
            raise SafetyError("step() called outside the guard context")
        self.steps += 1
        now = time.time()
        if self.deadline_epoch is not None and now >= self.deadline_epoch:
            raise SafetyError(
                f"job deadline reached after {self.steps} steps "
                f"({self.duration_s}s budget); stopping our own job"
            )
        if self._proc is not None and self._proc.poll() is not None:
            raise SafetyError(
                f"watchdog exited unexpectedly (rc={self._proc.returncode}); stopping our own job"
            )

        metrics = self._memory_metrics()
        if metrics["active_bytes"] >= self.memory_limit_bytes:
            raise SafetyError(
                f"active MLX memory {metrics['active_bytes'] / GIB:.2f}GiB reached the "
                f"{self.memory_gb:g}GB limit; stopping our own job"
            )
        self.mx.clear_cache()
        if self.steps % self.log_every_steps == 0:
            self._log("step", label=label, step=self.steps, **metrics)
        return metrics

    # -- watchdog --------------------------------------------------------- #

    def _start_watchdog(self) -> None:
        token = process_start_token(os.getpid())
        if not token:
            raise SafetyError("cannot fingerprint own PID; refusing to run without a watchdog")
        report_path = self.log_path.with_suffix(".watchdog.json")
        self.watchdog_report_path = report_path
        cfg = WatchdogConfig(
            pid=os.getpid(),
            start_token=token,
            report_path=report_path,
            poll_seconds=self.watchdog_poll_s,
            swap_limit=self.swap_limit,
            deadline_epoch=self.deadline_epoch,
            max_runtime_s=self.duration_s + 300.0,
        )
        self._proc, self.watchdog_pid = self._spawn(cfg)

    def watchdog_report(self) -> dict | None:
        """Read the watchdog's report file, if it wrote one."""
        if self.watchdog_report_path is None or not self.watchdog_report_path.exists():
            return None
        try:
            return json.loads(self.watchdog_report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):  # pragma: no cover - defensive
            return None

    # -- cleanup ---------------------------------------------------------- #

    def _cleanup(self, *, entered_ok: bool, error: BaseException | None = None) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except (OSError, subprocess.SubprocessError):  # pragma: no cover - defensive
                    try:
                        proc.kill()
                    except OSError:
                        pass
            self.watchdog_pid = None
        if self.mx is not None:
            clear = getattr(self.mx, "clear_cache", None)
            if callable(clear):
                try:
                    clear()
                except Exception as exc:  # noqa: BLE001 - cleanup must not mask errors
                    self._log("clear_cache_failed", error=repr(exc))
            self._log("guard_exit", steps=self.steps, error=type(error).__name__ if error else None)
        if self.lock is not None:
            self.lock.release()
        if entered_ok:
            self._entered = False


def _spawn_watchdog(cfg: WatchdogConfig) -> tuple[subprocess.Popen, int]:
    """Spawn the watchdog as a separate process running this very file."""
    argv = [
        sys.executable,
        str(Path(__file__).resolve()),
        "watchdog",
        "--pid",
        str(cfg.pid),
        "--start",
        cfg.start_token,
        "--poll-seconds",
        str(cfg.poll_seconds),
        "--min-available-bytes",
        str(cfg.min_available_bytes),
        "--swap-limit",
        str(cfg.swap_limit),
        "--grace-seconds",
        str(cfg.grace_seconds),
        "--max-runtime-s",
        str(cfg.max_runtime_s),
    ]
    if cfg.report_path is not None:
        argv += ["--report", str(cfg.report_path)]
    if cfg.deadline_epoch is not None:
        argv += ["--deadline-epoch", str(cfg.deadline_epoch)]
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc, proc.pid


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m language_tutor.safety")
    sub = parser.add_subparsers(dest="cmd", required=True)

    snap = sub.add_parser("snapshot", help="print a host resource snapshot as JSON")
    snap.add_argument("--json", action="store_true", help="accepted for symmetry")

    gate = sub.add_parser("preflight", help="run the pre-flight gate and print the plan")
    gate.add_argument("--memory-gb", type=float, default=6.0)
    gate.add_argument("--duration-s", type=int, default=900)
    gate.add_argument("--allow-over-8gb", action="store_true")
    gate.add_argument("--allow-over-30min", action="store_true")

    wd = sub.add_parser("watchdog", help="watch one PID and kill it on a safety breach")
    wd.add_argument("--pid", type=int, required=True)
    wd.add_argument("--start", required=True)
    wd.add_argument("--report")
    wd.add_argument("--poll-seconds", type=float, default=5.0)
    wd.add_argument("--min-available-bytes", type=int, default=WATCHDOG_MIN_AVAILABLE_BYTES)
    wd.add_argument("--swap-limit", type=float, default=WATCHDOG_SWAP_LIMIT)
    wd.add_argument("--deadline-epoch", type=float)
    wd.add_argument("--grace-seconds", type=float, default=5.0)
    wd.add_argument("--max-runtime-s", type=float, default=3600.0)

    args = parser.parse_args(argv)

    if args.cmd == "snapshot":
        print(json.dumps(snapshot(), indent=2, sort_keys=True))
        return 0
    if args.cmd == "preflight":
        try:
            plan = preflight(
                args.memory_gb,
                args.duration_s,
                allow_over_8gb=args.allow_over_8gb,
                allow_over_30min=args.allow_over_30min,
            )
        except SafetyError as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    cfg = WatchdogConfig(
        pid=args.pid,
        start_token=args.start,
        report_path=Path(args.report) if args.report else None,
        poll_seconds=args.poll_seconds,
        min_available_bytes=args.min_available_bytes,
        swap_limit=args.swap_limit,
        deadline_epoch=args.deadline_epoch,
        grace_seconds=args.grace_seconds,
        max_runtime_s=args.max_runtime_s,
    )
    try:
        report = watchdog_run(cfg)
    except SafetyError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    # Exit 0 means the watchdog ran to a decision (including "killed"); 2 above
    # means the watchdog itself refused an invalid target.
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess in tests
    raise SystemExit(_main())
