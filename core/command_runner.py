"""Runs deck commands off the GTK main loop and reports failures back to it."""
import logging
import shutil
import subprocess
import threading

from gi.repository import GLib

logger = logging.getLogger(__name__)

# Commands that outlive this many seconds are treated as "started fine"
# (daemons, GUI apps). Their exit code is no longer reported.
_REPORT_WINDOW_S = 10
_STDERR_LIMIT = 400

_SHELL = shutil.which("bash") or "/bin/sh"


class CommandError(Exception):
    pass


def _first_useful_line(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:_STDERR_LIMIT]
    return ""


def run_command(command: str, on_error=None, on_finished=None) -> bool:
    """Run `command` in a background shell.

    Returns False (without running anything) if the command is empty.

    `on_error(message)` is invoked on the GTK main thread if the command fails
    quickly — long-running processes are assumed to have started successfully.

    `on_finished(succeeded)` is invoked on the GTK main thread when the command
    exits, or once it has clearly outlived the reporting window (a daemon or a
    GUI app), so callers can show "this is still running" state.
    """
    command = (command or "").strip()
    if not command:
        return False

    def _report(message):
        if on_error is not None:
            GLib.idle_add(on_error, message, priority=GLib.PRIORITY_DEFAULT)

    def _finish(succeeded):
        if on_finished is not None:
            GLib.idle_add(on_finished, succeeded, priority=GLib.PRIORITY_DEFAULT)

    def _run():
        try:
            proc = subprocess.Popen(
                [_SHELL, "-c", command],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,  # don't let the child take our signals
                text=True,
                errors="replace",
            )
        except OSError as e:
            logger.error("Could not start command %r: %s", command, e)
            _report(f"Could not run command: {e.strerror or e}")
            _finish(False)
            return

        try:
            _, stderr = proc.communicate(timeout=_REPORT_WINDOW_S)
        except subprocess.TimeoutExpired:
            # Still running: a daemon or GUI app. Leave it alone.
            logger.debug("Command still running after %ss: %r", _REPORT_WINDOW_S, command)
            _finish(True)
            return
        except Exception as e:  # pragma: no cover - defensive
            logger.error("Command %r failed: %s", command, e)
            _report(f"Command failed: {e}")
            _finish(False)
            return

        if proc.returncode != 0:
            detail = _first_useful_line(stderr)
            logger.warning("Command exited %s: %r (%s)", proc.returncode, command, detail)
            _report(detail or f"Command exited with status {proc.returncode}")
        _finish(proc.returncode == 0)

    threading.Thread(target=_run, daemon=True, name="deckapp-command").start()
    return True
