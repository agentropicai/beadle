"""Beadle — build an AI employee without building an agent platform.

This package is a thin installer. Beadle itself is a workspace you own and edit, not a library
you import: employees are folders, tasks are scripts you change. So `beadle init` fetches the
starter workspace into a directory and then gets out of your way.

    pip install beadle
    beadle init my-employees
    cd my-employees && ./beadle doctor

Everything after that is documented in the workspace itself — README.md, QUICKSTART.md and
EXAMPLE.md. Source: https://github.com/agentropicai/beadle
"""
__version__ = "0.2.0"

import os
import shutil
import subprocess
import sys
import tempfile

REPO = "https://github.com/agentropicai/beadle"

USAGE = """beadle — fetch the Beadle starter workspace.

    beadle init [directory]     create a workspace (default: ./beadle)
    beadle --version

Beadle is a workspace, not a library. Once `init` has run, use the ./beadle script inside it:

    cd <directory>
    ./beadle doctor
    ./beadle run example-site-watch uptime-check
    ./beadle new my-first-employee

Docs: %s
""" % REPO


def _init(target):
    dest = os.path.abspath(target)
    if os.path.exists(dest) and os.listdir(dest):
        sys.exit("%s already exists and is not empty" % dest)
    if not shutil.which("git"):
        sys.exit("git is required to fetch the workspace. Install it, or clone %s by hand." % REPO)

    with tempfile.TemporaryDirectory() as tmp:
        staging = os.path.join(tmp, "beadle")
        r = subprocess.run(["git", "clone", "--depth", "1", "--quiet", REPO, staging],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit("could not fetch the workspace:\n" + (r.stderr or "")[:400])
        # The workspace is yours from here — drop our history so your first commit is your own.
        shutil.rmtree(os.path.join(staging, ".git"), ignore_errors=True)
        shutil.rmtree(os.path.join(staging, "src"), ignore_errors=True)
        for name in ("pyproject.toml",):
            f = os.path.join(staging, name)
            if os.path.exists(f):
                os.remove(f)
        shutil.copytree(staging, dest, dirs_exist_ok=True)

    os.chmod(os.path.join(dest, "beadle"), 0o755)
    rel = os.path.relpath(dest)
    print("Created %s\n" % rel)
    print("  cd %s" % rel)
    print("  ./beadle doctor                                # do the pieces work?")
    print("  ./beadle run example-site-watch uptime-check   # a real employee, no config needed")
    print("  ./beadle new my-first-employee                 # now write your own")
    print("\nRead EXAMPLE.md for a full worked build, bug included.")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if argv[0] in ("-V", "--version", "version"):
        print("beadle %s" % __version__)
        return 0
    if argv[0] == "init":
        _init(argv[1] if len(argv) > 1 else "beadle")
        return 0
    print(USAGE)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
