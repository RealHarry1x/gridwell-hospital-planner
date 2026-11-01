"""Beginner-friendly setup and single-server launcher. Python 3.12+ required.

Windows: py -3.12 run.py --setup
macOS/Linux: python3 run.py --setup
Subsequent launches: python3 run.py (Windows: py -3.12 run.py)
"""

import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import venv
import webbrowser

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
FRONTEND = ROOT / "frontend"


def run_command(command, cwd=ROOT):
    print("\n> " + " ".join(str(part) for part in command), flush=True)
    # Windows npm.cmd needs the normal command shell. All arguments here are
    # fixed project paths or fixed flags, never API / user-submitted values.
    result = subprocess.run([str(part) for part in command], cwd=cwd, shell=(os.name == "nt" and str(command[0]).endswith(".cmd")))
    if result.returncode:
        raise RuntimeError("That command did not finish successfully. Read its message above and try again.")


def setup():
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    node = shutil.which("node")
    if not npm or not node:
        raise RuntimeError("Install Node.js 22.12+ (LTS is fine), reopen the terminal, then run this command again.")
    version = subprocess.check_output([node, "--version"], text=True).strip().lstrip("v")
    parts = tuple(int(v) for v in version.split(".")[:2])
    if parts < (22, 12):
        raise RuntimeError(f"Node.js {version} found. Please use Node.js 22.12 or newer.")
    if not PYTHON.exists():
        print("Creating a private Python environment in .venv…", flush=True)
        # A copied/moved virtual environment can contain broken interpreter
        # links. Explicit --setup may safely rebuild only that disposable folder.
        venv.EnvBuilder(with_pip=True, clear=VENV.exists()).create(VENV)
    run_command([PYTHON, "-m", "pip", "install", "-r", "requirements.txt"])
    run_command([npm, "ci", "--no-audit", "--no-fund"], FRONTEND)
    run_command([npm, "run", "build"], FRONTEND)
    print("\nSetup complete. Sample mode needs no key; Gemini is optional and configured on the Python server.", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Run Gridwell locally in your browser.")
    parser.add_argument("--setup", action="store_true", help="Install dependencies, build the React frontend, then run.")
    parser.add_argument("--setup-only", action="store_true", help="Install/build without starting the app.")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open a browser tab.")
    parser.add_argument("--port", type=int, default=8000, help="Local port (default: 8000).")
    parser.add_argument("--preview", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--host", help=argparse.SUPPRESS)
    parser.add_argument("--strictPort", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        raise RuntimeError("Please install Python 3.12 or newer. On Windows, try: py -3.12 run.py --setup")
    if args.setup or args.setup_only:
        setup()
    if args.setup_only:
        return
    if not PYTHON.exists() or not (FRONTEND / "dist" / "index.html").exists():
        raise RuntimeError("First-time setup is needed. Run this same command with --setup added. See README.md.")
    installed = subprocess.run([str(PYTHON), "-c", "import fastapi, pydantic, uvicorn, google.genai, dotenv"], capture_output=True)
    if installed.returncode:
        raise RuntimeError("Python packages are missing. Run with --setup to repair the environment.")
    port = int(os.environ.get("PORT", str(args.port))) if args.preview else args.port
    if not (1 <= port <= 65535):
        raise RuntimeError("Choose a port between 1 and 65535.")
    host = "0.0.0.0" if args.preview else "127.0.0.1"
    # Catch a common beginner error without interfering with the preview daemon.
    with socket.socket() as probe:
        try:
            probe.bind((host, port))
        except OSError as exc:
            raise RuntimeError(f"Port {port} is in use. Close the previous app or add --port 8001.") from exc
    command = [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port)]
    print(f"\nGridwell is starting at http://127.0.0.1:{port}\nKeep this terminal open. Press Ctrl+C to stop.\n", flush=True)
    server = subprocess.Popen(command, cwd=ROOT / "backend")
    try:
        if not args.no_browser and not args.preview:
            # Open only after the process is accepting connections, without a
            # fixed long wait or a second server process.
            for _ in range(40):
                if server.poll() is not None:
                    break
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.15):
                        webbrowser.open(f"http://127.0.0.1:{port}")
                        break
                except OSError:
                    time.sleep(0.15)
        server.wait()
    except KeyboardInterrupt:
        print("\nStopping Gridwell…", flush=True)
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f"\nGridwell: {error}\n", file=sys.stderr)
        sys.exit(1)
