#!/usr/bin/env python3
# ansible managed

# Icinga/Nagios check plugin for GlusterFS mount health.
# Uses the nagiosplugin library.

# Dependencies:
#   pip install nagiosplugin

# Usage:
#   check_glusterfs_mount.py -m /mnt/gluster
#   check_glusterfs_mount.py -m /mnt/gluster -t 30

# The MIT License (MIT)
# Copyright (c) 2026 marek@igloonet.cz

# Permission is hereby granted, free of charge, to any person obtaining a copy of this
# software and associated documentation files (the "Software"), to deal in the Software
# without restriction, including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies
# or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
# PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
# FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT
# OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

import argparse
import errno
import logging
import os
import stat
import threading
import nagiosplugin

_log = logging.getLogger("nagiosplugin")

# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


class GlusterMount(nagiosplugin.Resource):
    # Checks accessibility of a GlusterFS FUSE mountpoint.

    # Emits three metrics:
    #   - ``mounted``   : 1 if the mountpoint is present in /proc/self/mountinfo, otherwise 0
    #   - ``accessible``: 1 if stat() + listdir() succeed without ENOTCONN/ESTALE, otherwise 0
    #   - ``entries``   : number of entries in the mountpoint root (informational only)

    # A FUSE mount with no responsive server can make stat()/listdir() block
    # indefinitely in the kernel - this is NOT interruptible by nagiosplugin's
    # SIGALRM-based check timeout if the alarm fires while we're elsewhere in
    # the code (e.g. formatting an error message), which produces an ugly
    # UNKNOWN traceback instead of a clean CRITICAL. So we run the syscalls in
    # a daemon thread and enforce our own short timeout while waiting on it.

    def __init__(self, mountpoint: str, access_timeout: float = 3.0):
        self.mountpoint = mountpoint.rstrip("/")
        self.access_timeout = access_timeout

    def _is_in_mountinfo(self) -> bool:
        try:
            with open("/proc/self/mountinfo") as f:
                for line in f:
                    parts = line.split()
                    # field 4 (0-indexed) is the mountpoint
                    if len(parts) > 4 and parts[4] == self.mountpoint:
                        return True
        except OSError as e:
            _log.warning("Cannot read /proc/self/mountinfo: %s", e)
        return False

    # Errno values that indicate a broken/disconnected GlusterFS cluster.
    # These are reported as CRITICAL (accessible=0), not UNKNOWN.
    _CLUSTER_DOWN_ERRORS = frozenset(
        {
            errno.ENOTCONN,  # Transport endpoint is not connected (errno=107)
            errno.ESTALE,  # Stale file handle (errno=116)
            errno.ETIMEDOUT,  # Connection timed out (errno=110)
            errno.ECONNRESET,  # Connection reset by peer (errno=104)
            errno.EHOSTDOWN,  # Host is down (errno=112)
        }
    )

    def _run_with_timeout(self, func, *args):
        # Runs func(*args) in a daemon thread and waits up to
        # self.access_timeout seconds. Returns (completed, result, error).
        # If the thread doesn't finish in time, it's abandoned (daemon=True
        # means it won't block process exit) and completed=False is returned.
        result_box = {}

        def target():
            try:
                result_box["value"] = func(*args)
            except OSError as e:
                result_box["error"] = e
            except BaseException as e:  # noqa: BLE001
                # Anything that isn't an OSError is unexpected; remember it so
                # the main thread can re-raise it instead of silently returning
                # (True, None, None) and tripping over a None result later.
                result_box["unexpected"] = e

        t = threading.Thread(target=target, daemon=True)
        t.start()
        t.join(self.access_timeout)

        if t.is_alive():
            return False, None, None
        if "unexpected" in result_box:
            raise result_box["unexpected"]
        if "error" in result_box:
            return True, None, result_box["error"]
        return True, result_box["value"], None

    def _access_mount(self) -> tuple[bool, int]:
        # Returns (accessible, entry_count).
        # accessible=False signals a known cluster-down condition → CRITICAL.
        # Raises CheckError only for truly unexpected errors → UNKNOWN.
        completed, st, err = self._run_with_timeout(os.stat, self.mountpoint)

        if not completed:
            _log.warning(
                "stat() did not return within %.1fs - treating as cluster down",
                self.access_timeout,
            )
            return False, 0

        if err is not None:
            if err.errno in self._CLUSTER_DOWN_ERRORS:
                _log.warning(
                    "stat() cluster down: %s", self._oserror_msg("stat()", err)
                )
                return False, 0
            raise nagiosplugin.CheckError(self._oserror_msg("stat()", err))

        if not stat.S_ISDIR(st.st_mode):
            raise nagiosplugin.CheckError(f"{self.mountpoint!r} is not a directory")

        completed, entries, err = self._run_with_timeout(os.listdir, self.mountpoint)

        if not completed:
            _log.warning(
                "listdir() did not return within %.1fs - treating as cluster down",
                self.access_timeout,
            )
            return False, 0

        if err is not None:
            if err.errno in self._CLUSTER_DOWN_ERRORS:
                _log.warning(
                    "listdir() cluster down: %s", self._oserror_msg("listdir()", err)
                )
                return False, 0
            raise nagiosplugin.CheckError(self._oserror_msg("listdir()", err))

        return True, len(entries)

    @staticmethod
    def _oserror_msg(op: str, e: OSError) -> str:
        labels = {
            errno.ENOTCONN: "Transport endpoint is not connected",
            errno.ESTALE: "Stale file handle",
            errno.ENOENT: "No such file or directory",
        }
        if e.errno is not None:
            detail = labels.get(e.errno, e.strerror)
        else:
            detail = str(e)
        return f"{op} failed: {detail} (errno={e.errno})"

    def probe(self):
        _log.info("Checking mountpoint %r", self.mountpoint)

        mounted = self._is_in_mountinfo()
        _log.debug("mountinfo: %s", mounted)
        yield nagiosplugin.Metric("mounted", int(mounted), min=0, max=1)

        if not mounted:
            # If not in mountinfo, stat/listdir would fail anyway -
            # return accessible=0 and entries=0 so the Context generates CRITICAL.
            yield nagiosplugin.Metric("accessible", 0, min=0, max=1)
            yield nagiosplugin.Metric("entries", 0, min=0)
            return

        # May raise CheckError for unexpected errors → UNKNOWN.
        # Returns (accessible, entry_count); accessible=False → CRITICAL.
        accessible, entry_count = self._access_mount()
        yield nagiosplugin.Metric("accessible", int(accessible), min=0, max=1)
        yield nagiosplugin.Metric("entries", entry_count, min=0)


# ---------------------------------------------------------------------------
# Contexts
# ---------------------------------------------------------------------------


class BoolContext(nagiosplugin.Context):
    # Context for binary metrics (0 = problem, 1 = OK).

    # Parameters:
    #   critical_state: nagiosplugin state used when value is 0
    #                   (default: nagiosplugin.Critical)

    def __init__(self, name: str, critical_state=None, fmt_metric=None):
        super().__init__(name, fmt_metric=fmt_metric)
        self.critical_state = critical_state or nagiosplugin.Critical

    def evaluate(self, metric, resource):
        if metric.value == 0:
            return self.result_cls(self.critical_state, None, metric)
        return self.result_cls(nagiosplugin.Ok, None, metric)

    def describe(self, metric):
        if self.fmt_metric:
            return super().describe(metric)
        return "OK" if metric.value else "FAILED"


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class GlusterSummary(nagiosplugin.Summary):

    def ok(self, results):
        if "entries" in results:
            return f"{results['entries'].metric.value} entries in mount"
        return "GlusterFS OK"

    def problem(self, results):
        # Returns the description of the worst result
        worst = results.most_significant[0]
        return str(worst)

    def verbose(self, results):
        lines = []
        for r in results:
            lines.append(f"  {r.metric.name}: {r.metric.value} -> {r.state}")
        return lines


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


@nagiosplugin.guarded
def main():
    argp = argparse.ArgumentParser(
        description="Icinga/Nagios check for GlusterFS mount health"
    )
    argp.add_argument(
        "-m",
        "--mount",
        required=True,
        metavar="PATH",
        help="Path to the GlusterFS mountpoint, e.g. /mnt/gluster",
    )
    argp.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase output verbosity (up to 3 times)",
    )
    argp.add_argument(
        "-t",
        "--timeout",
        default=15,
        type=int,
        help="Check timeout in seconds (default: 15)",
    )
    args = argp.parse_args()

    # Leave headroom under the overall check timeout for nagiosplugin's own
    # setup/teardown, so our internal access timeout fires first and produces
    # a clean CRITICAL instead of racing nagiosplugin's SIGALRM into an
    # UNKNOWN traceback. Minimum 1s, otherwise overall timeout minus 2s.
    access_timeout = max(1.0, args.timeout - 2.0)

    resources = [
        GlusterMount(args.mount, access_timeout=access_timeout),
        BoolContext(
            "mounted",
            fmt_metric="mountpoint in /proc/self/mountinfo: {value}",
        ),
        BoolContext(
            "accessible",
            fmt_metric="mount accessible (stat+listdir): {value}",
        ),
        nagiosplugin.Context(
            "entries",
            fmt_metric="{value} entries in mount root",
        ),
    ]

    resources.append(GlusterSummary())

    check = nagiosplugin.Check(*resources)
    check.main(args.verbose, args.timeout)


if __name__ == "__main__":
    main()
