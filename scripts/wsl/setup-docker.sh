#!/usr/bin/env bash
# =============================================================================
# WSL の Ubuntu に Docker Engine と uv を入れる（実起動の試験の準備。何度実行してもよい）
#
#   Windows から:  wsl -d Ubuntu -u root -- bash scripts/wsl/setup-docker.sh <WSL のユーザー名>
#   WSL の中から:  sudo bash scripts/wsl/setup-docker.sh "$USER"
#
# - Docker は公式の手順（https://docs.docker.com/engine/install/ubuntu/）で、
#   Docker の apt リポジトリから入れる。Docker Desktop は使わない
# - systemd が有効な WSL を前提にする（/etc/wsl.conf の [boot] systemd=true）
# - uv は公式の手順（https://docs.astral.sh/uv/）でユーザーのホームに入れる
# =============================================================================
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "root で実行してください（sudo か wsl -u root）" >&2
  exit 1
fi
TARGET_USER="${1:?WSL のユーザー名を指定してください}"

echo "== パッケージを最新にする"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -y -q

echo "== Docker の apt リポジトリを登録する"
apt-get install -y -q ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
# shellcheck disable=SC1091
codename="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu ${codename} stable" > /etc/apt/sources.list.d/docker.list
apt-get update -q

echo "== Docker Engine と compose を入れる"
apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
getent group docker > /dev/null || groupadd docker
usermod -aG docker "$TARGET_USER"

echo "== uv を入れる（${TARGET_USER} のホーム）"
if ! sudo -u "$TARGET_USER" -H bash -lc 'test -x "$HOME/.local/bin/uv"'; then
  sudo -u "$TARGET_USER" -H bash -lc 'curl -LsSf https://astral.sh/uv/install.sh | sh'
fi

echo "== 確認"
docker version --format 'docker engine {{.Server.Version}}'
docker compose version
sudo -u "$TARGET_USER" -H bash -lc '$HOME/.local/bin/uv --version'
