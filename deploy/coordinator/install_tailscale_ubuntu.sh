#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo '请使用 sudo/root 执行本脚本' >&2
  exit 1
fi
command -v curl >/dev/null || { echo '缺少 curl，请先安装 curl' >&2; exit 1; }

# Official Tailscale Linux installer; installs the stable package and systemd service.
curl -fsSL https://tailscale.com/install.sh | sh
systemctl enable --now tailscaled.service
echo 'Tailscale 已安装并启动，下面会显示官方登录链接：'
tailscale version
tailscale up
echo '完成后请保存 tailscale ip -4 的结果，并用 tailscale status 验证节点。'
