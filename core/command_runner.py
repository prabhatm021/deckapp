import subprocess
import threading
import logging

logger = logging.getLogger(__name__)


def run_command(command: str) -> None:
    """Run a shell command in a background thread so the GTK main loop is never blocked."""
    def _run():
        try:
            subprocess.run(
                ["bash", "-c", command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.error("Command failed %r: %s", command, e)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
