#!/usr/bin/env python3
"""
Voice Typing launcher with AUTO-RELOAD.

Runs the app (voice_typing.py) and watches this folder. If you change the app's
code (any .py file) and save, the app restarts automatically so your change
takes effect. Settings you change inside the app (config.json) do NOT trigger a
restart. Quitting the app (its window close, or Ctrl+Alt+Q-style exit) stops the
launcher too.
"""

import os
import sys
import time
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "voice_typing.py")
PYTHON = sys.executable  # pythonw.exe when launched as a windowed app

# No console under pythonw -> keep print() safe.
if sys.stdout is None:
    try:
        sys.stdout = open(os.path.join(HERE, "launcher.log"), "a", encoding="utf-8")
    except Exception:
        sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = sys.stdout

IGNORE_DIRS = {"venv", "__pycache__", ".git", ".idea", ".vscode"}
IGNORE_NAMES = {"run_app.py"}   # editing the launcher itself won't loop-restart
WATCH_EXT = {".py"}             # only code changes trigger a restart
POLL_SECONDS = 1.0


def snapshot():
    sig = {}
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for name in files:
            if name in IGNORE_NAMES:
                continue
            if os.path.splitext(name)[1].lower() not in WATCH_EXT:
                continue
            path = os.path.join(root, name)
            try:
                st = os.stat(path)
                sig[path] = (st.st_mtime, st.st_size)
            except OSError:
                pass
    return sig


def stop(proc):
    if proc is None or proc.poll() is not None:
        return
    # Kill the whole tree so child processes (e.g. the grammar Java server) die too.
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True)
        proc.wait(timeout=8)
        return
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=8)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def launch():
    return subprocess.Popen([PYTHON, TARGET])


def main():
    if not os.path.exists(TARGET):
        time.sleep(3)
        return
    state = snapshot()
    proc = launch()
    try:
        while True:
            time.sleep(POLL_SECONDS)
            current = snapshot()
            if current != state:
                state = current
                if proc.poll() is None:
                    stop(proc)
                time.sleep(0.4)
                state = snapshot()
                proc = launch()
                continue
            if proc.poll() is not None:
                if proc.returncode == 0:
                    break          # clean exit -> stop watching
                time.sleep(0.4)    # crashed -> wait for a code fix, then relaunch
    except KeyboardInterrupt:
        pass
    finally:
        stop(proc)


if __name__ == "__main__":
    main()
