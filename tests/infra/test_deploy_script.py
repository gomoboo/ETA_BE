"""Exercise the real shell deployment script with stubbed external commands."""
import json
import os
import subprocess
from pathlib import Path

import pytest

REGISTRY = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com"
OLD = f"{REGISTRY}/eta-test/api:{'a' * 40}"
NEW = f"{REGISTRY}/eta-test/api:{'b' * 40}"


@pytest.mark.parametrize("scenario", ["success", "pull-failure", "health-failure", "curl-failure"])
def test_api_replacement_preserves_data_services_and_restores_failed_image(tmp_path, scenario):
    root = Path(__file__).resolve().parents[2]
    server = tmp_path / "server"
    scripts = server / "repo/infra/scripts"
    scripts.mkdir(parents=True)
    env_dir = server / "env"
    env_dir.mkdir()
    image_file = env_dir / "image.env"
    image_file.write_text(f"API_IMAGE={OLD}\nAPI_DOMAIN=api.example.org\n")
    (env_dir / "api.env").write_text("POSTGRES_PASSWORD=not-a-real-secret\n")
    for filename in ("deploy.sh", "compose.sh"):
        source = (root / "infra/scripts" / filename).read_text().replace("/opt/eta", str(server))
        target = scripts / filename
        target.write_text(source)
        target.chmod(0o755)
    (scripts / "config.py").write_text(
        "import sys\nprint(" + repr({"ecr_registry": REGISTRY, "region": "ap-northeast-2", "image_parameter": "/eta-test/desired-image"}) + "[sys.argv[1]])\n"
    )
    binaries = tmp_path / "bin"
    binaries.mkdir()
    stub = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
scenario = os.environ['SCENARIO']
with open(os.environ['CALL_LOG'], 'a') as log:
    log.write(json.dumps([name, args])+'\\n')
if name == 'aws':
    print('synthetic-ecr-login-password')
elif name == 'docker':
    if args[0] == 'login':
        sys.stdin.read()
    if args[0] == 'pull' and scenario == 'pull-failure':
        sys.exit(1)
    if args[0] == 'compose' and 'up' in args:
        new_image = os.environ['NEW_IMAGE'] in Path(os.environ['IMAGE_FILE']).read_text()
        if new_image and scenario == 'health-failure':
            sys.exit(1)
elif name == 'curl' and scenario == 'curl-failure':
    sys.exit(1)
'''
    for name in ("aws", "docker", "curl"):
        path = binaries / name
        path.write_text(stub)
        path.chmod(0o755)
    log = tmp_path / "calls.jsonl"
    env = {**os.environ, "PATH": f"{binaries}:{os.environ['PATH']}", "SCENARIO": scenario,
           "CALL_LOG": str(log), "NEW_IMAGE": NEW, "IMAGE_FILE": str(image_file)}
    result = subprocess.run(["bash", str(scripts / "deploy.sh"), NEW], env=env, capture_output=True, text=True)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    replacements = [args for name, args in calls if name == "docker" and args[0] == "compose"]
    assert all("--no-deps" in args and args[-1] == "api" for args in replacements)
    assert all("down" not in args and "-v" not in args for name, args in calls if name == "docker")
    if scenario == "success":
        assert result.returncode == 0, result.stderr
        assert NEW in image_file.read_text()
        assert len(replacements) == 1
    else:
        assert result.returncode != 0
        assert OLD in image_file.read_text()
        assert len(replacements) == (0 if scenario == "pull-failure" else 2), result.stderr
        selections = [args for name, args in calls if name == "aws" and "put-parameter" in args]
        if scenario != "pull-failure":
            assert selections[0][-1] == OLD  # Next boot also restores the last healthy version.
        else:
            assert selections == []
