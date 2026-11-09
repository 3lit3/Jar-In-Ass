"""
Smoke test: launch the frozen exe, wait, and fail loudly if it dies at startup.

    python smoke_test.py <exe> <logfile>

Pass criteria: the process is still alive after WAIT seconds. On failure the last
lines of the captured console log are printed, because the console transcript is
where a frozen app reports the reason it could not start (missing DLL, import
error inside the PYZ archive, bad working directory).

Deliberately does NOT parse for specific strings — "alive after N seconds" is the
only contract a cold start has to keep, and anything more precise makes the build
script lie about app-version-specific log text.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

WAIT = 8.0
TAIL = 40


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: smoke_test.py <exe> <logfile>", file=sys.stderr)
        return 2
    exe = Path(sys.argv[1])
    log = Path(sys.argv[2])
    if not exe.is_file():
        print(f"[smoke] exe not found: {exe}", file=sys.stderr)
        return 2

    with log.open("w", encoding="utf-8", errors="replace") as fh:
        proc = subprocess.Popen(
            [str(exe)],
            stdout=fh,
            stderr=subprocess.STDOUT,
            cwd=str(exe.parent),
        )
        try:
            time.sleep(WAIT)
        except KeyboardInterrupt:
            proc.kill()
            raise

        if proc.poll() is not None:
            rc = proc.returncode
            tail = ""
            try:
                lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
                tail = "\n".join(lines[-TAIL:])
            except Exception:
                pass
            print(f"[smoke] FAILED - exited rc={rc} during first {WAIT:.0f}s")
            if tail:
                print(f"----- last {TAIL} log lines -----")
                print(tail)
                print("---------------------------------")
            return 1

    # Still alive. Kill it and treat a non-zero kill as a pass anyway (Windows
    # returns 1 on force-kill); liveness, not clean exit, is the contract.
    proc.kill()
    try:
        proc.wait(timeout=5)
    except Exception:
        pass
    print(f"[smoke] OK - still alive after {WAIT:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
