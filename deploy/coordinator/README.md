# Ubuntu Coordinator bootstrap deployment

This package is the M04 read-only bootstrap only. It exposes `/healthz`,
`/readyz` and `/api/v1/progress`; it has no order, QMT, Redis or OpenClaw
code. HTTPS/private-CA wrapping is installed in the next deployment step
after the service preflight passes.

## Install on 192.0.2.121

1. Copy a release to `/opt/bigqmt-coordinator/releases/<version>` and
   make `current` point at the verified release.
2. Run `sudo bash deploy/coordinator/preflight_ubuntu.sh`.
3. Create the locked service user and state directory:

```bash
sudo useradd --system --home /var/lib/kitling-bigqmt-coordinator --shell /usr/sbin/nologin bigqmt-coordinator
sudo install -d -o bigqmt-coordinator -g bigqmt-coordinator /var/lib/kitling-bigqmt-coordinator
```

4. Create a Python 3.12 venv at `/opt/bigqmt-coordinator/venv` and
   install the project without network dependencies.
5. Install the unit to `/etc/systemd/system/`, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kitling-bigqmt-coordinator.service
curl http://192.0.2.121:18443/healthz
```

The current bootstrap deliberately binds the selected LAN IP but uses plain
HTTP until the private CA/IP-SAN certificate is installed. Do not expose this
port outside the LAN. The production deployment gate requires TLS and a
firewall allow-list for `192.0.2.105` before any client integration.

## LAN firewall policy

An internal network still has multiple hosts, VLAN routes and failure modes;
the Coordinator is a control-plane service, so its port is not opened to the
whole LAN by default. Review existing rules first, then run
`ufw_allowlist.sh` on `.121`. It allows `.105` only. The `.125` and `.113`
rules remain commented until their read-only Host Agents are installed.

## Install Tailscale on `.121`

From an SSH session on `192.0.2.121`, run:

```bash
sudo bash deploy/coordinator/install_tailscale_ubuntu.sh
```

The script follows the official Linux installation method, enables
`tailscaled` at boot, and prints an authentication URL. Complete that URL in
the Tailscale admin flow, then verify with `tailscale status` and
`tailscale ip -4`. Do not enable subnet routing, exit-node mode, or Funnel for
the Coordinator. Tailscale is only the private management path; Coordinator
authorization and the one-active-executor lease remain separate.
