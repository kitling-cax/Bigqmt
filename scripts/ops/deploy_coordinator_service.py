"""Deploy the Coordinator service with a password supplied only at runtime.

The password is read from an environment variable, never from a project file,
command-line argument, Git commit, or deployment report.  This updates only
the Coordinator Python entry point and its gitignored machine-local alias map.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shlex
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def parse_alias(value: str) -> tuple[str, str]:
    deployment, separator, profile = value.partition("=")
    if not separator or not deployment.strip() or not profile.strip():
        raise argparse.ArgumentTypeError("alias must be deployment_account=synthetic_profile")
    return deployment.strip(), profile.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--remote-root", default="/opt/kitling-bigqmt-coordinator/current")
    parser.add_argument("--service", default="kitling-bigqmt-coordinator.service")
    parser.add_argument("--password-env", default="BIGQMT_COORDINATOR_SSH_PASSWORD")
    parser.add_argument("--alias", action="append", type=parse_alias, required=True)
    args = parser.parse_args()

    password = os.environ.get(args.password_env, "")
    if not password:
        raise SystemExit("missing runtime password environment variable: %s" % args.password_env)
    try:
        import paramiko
    except ImportError as exc:
        raise SystemExit("paramiko is required on the deployment machine: %s" % exc)

    aliases = dict(args.alias)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    remote_root = args.remote_root.rstrip("/")
    remote_tmp = "/tmp/kitling-bigqmt-coordinator-%s" % stamp
    remote_backup = "%s/backups/%s_before_alias_config" % (remote_root.rsplit("/current", 1)[0], stamp)
    local_serve = ROOT / "scripts" / "coordinator" / "serve.py"
    if not local_serve.is_file():
        raise SystemExit("missing local Coordinator source: %s" % local_serve)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(args.host, username=args.username, password=password, timeout=10)

    def run(command: str, sudo: bool = False) -> str:
        if sudo:
            command = "sudo -S -p '' bash -lc %s" % shlex.quote(command)
        stdin, stdout, stderr = client.exec_command(command, get_pty=False)
        if sudo:
            stdin.write(password + "\n")
            stdin.flush()
        output = stdout.read().decode("utf-8", "replace")
        error = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        if code:
            raise RuntimeError("remote command failed (%s): %s" % (code, error.strip() or output.strip()))
        return output

    try:
        run("test -f %s && test -f %s" % (
            shlex.quote(remote_root + "/scripts/coordinator/serve.py"),
            shlex.quote(remote_root + "/src/kitling_bigqmt/machine_config.py"),
        ))
        run("mkdir -p %s" % shlex.quote(remote_tmp))
        sftp = client.open_sftp()
        try:
            sftp.put(str(local_serve), remote_tmp + "/serve.py")
        finally:
            sftp.close()

        run(" && ".join((
            "mkdir -p %s" % shlex.quote(remote_backup),
            "cp %s %s" % (
                shlex.quote(remote_root + "/scripts/coordinator/serve.py"),
                shlex.quote(remote_backup + "/serve.py"),
            ),
            "install -m 0644 %s %s" % (
                shlex.quote(remote_tmp + "/serve.py"),
                shlex.quote(remote_root + "/scripts/coordinator/serve.py"),
            ),
        )), sudo=True)

        patch_script = """import json
from pathlib import Path
p = Path(%r)
data = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'schema_version': 1}
if not isinstance(data, dict): raise SystemExit('machine.local.json must be an object')
coordinator = data.setdefault('coordinator', {})
if not isinstance(coordinator, dict): raise SystemExit('coordinator must be an object')
coordinator['deployment_account_aliases'] = %s
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')
""" % (remote_root + "/config/machine.local.json", json.dumps(aliases, ensure_ascii=False))
        encoded = base64.b64encode(patch_script.encode("utf-8")).decode("ascii")
        run("echo %s | base64 -d | python3 -" % shlex.quote(encoded), sudo=True)
        run("systemctl restart %s && systemctl is-active %s" % (
            shlex.quote(args.service), shlex.quote(args.service)), sudo=True)
        print(json.dumps({
            "status": "deployed",
            "host": args.host,
            "service": args.service,
            "backup": remote_backup,
            "alias_count": len(aliases),
        }, ensure_ascii=False))
    finally:
        try:
            run("rm -rf %s" % shlex.quote(remote_tmp))
        except Exception:
            pass
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
