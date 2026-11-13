"""Check the built binaries, Python API imports, and a HIP kernel on the workstation."""

import json
import subprocess
from pathlib import Path

import serve.server  # noqa: F401

lock = json.loads(Path("/opt/build/versions.lock.json").read_text())
print(json.dumps(lock, indent=2), flush=True)
for binary, option in (("strata", "--help"), ("strata-vision", "--version")):
    subprocess.run([f"/opt/strata/bin/{binary}", option], check=True)
subprocess.run(["/opt/strata/bin/check_hip"], check=True)
print("Strata binaries, API imports, and HIP kernel: PASS")
