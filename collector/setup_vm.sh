#!/usr/bin/env bash
# One-time setup of the live RBN collector on a fresh Debian or Ubuntu machine (for example a Google Cloud e2-micro).
# Run it once, as root, with the callsign to log in to the RBN feed with:
#
#     sudo bash setup_vm.sh K5OHY
#
# It installs the collector as a service that starts by itself and restarts if it stops, puts a web server (Caddy) in front of it with a free
# HTTPS certificate, and prints the two lines to give the app. Running it again is safe: it updates the code and keeps your key and your data.
set -euo pipefail

CALL="${1:?Give the callsign to log in with, for example: sudo bash setup_vm.sh K5OHY}"
REPO="${REPO:-https://github.com/K5OHY/FarField-Lab.git}"
BRANCH="${BRANCH:-main}"
APP=/opt/rbn/app
ENVFILE=/etc/rbn-collector.env

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this with sudo." >&2
  exit 1
fi

echo "== Installing what is needed"
apt-get update -y
apt-get install -y git curl gpg python3 debian-keyring debian-archive-keyring apt-transport-https
if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy
fi

echo "== Getting the collector code ($BRANCH)"
id rbn >/dev/null 2>&1 || useradd --system --create-home --home-dir /opt/rbn --shell /usr/sbin/nologin rbn
if [ -d "$APP/.git" ]; then
  git -C "$APP" fetch --depth 1 origin "$BRANCH"
  git -C "$APP" checkout -f FETCH_HEAD
else
  git clone --depth 1 --branch "$BRANCH" "$REPO" "$APP"
fi
chown -R rbn:rbn /opt/rbn

echo "== Settings"
if [ ! -f "$ENVFILE" ]; then
  KEY="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
  printf 'RBN_CALL=%s\nRBN_SERVICE_KEY=%s\n' "$CALL" "$KEY" > "$ENVFILE"
  chmod 600 "$ENVFILE"
else
  sed -i "s/^RBN_CALL=.*/RBN_CALL=$CALL/" "$ENVFILE"
fi
KEY="$(grep '^RBN_SERVICE_KEY=' "$ENVFILE" | cut -d= -f2-)"

echo "== The collector service"
cat > /etc/systemd/system/rbn-collector.service <<'UNIT'
[Unit]
Description=Live RBN spot collector for FarField Lab
After=network-online.target
Wants=network-online.target

[Service]
User=rbn
EnvironmentFile=/etc/rbn-collector.env
ExecStart=/usr/bin/python3 /opt/rbn/app/collector/rbn_service.py --call ${RBN_CALL} --db /var/lib/rbn/spots.db --bind 127.0.0.1 --port 8080
Restart=always
RestartSec=5
StateDirectory=rbn
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable rbn-collector >/dev/null
systemctl restart rbn-collector

echo "== The web address"
# Google Cloud tells the machine its own public address. Any other host: set IP=1.2.3.4 before running.
if [ -z "${IP:-}" ]; then
  IP="$(curl -s -H 'Metadata-Flavor: Google' 'http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip' || true)"
fi
if [ -z "$IP" ]; then
  IP="$(curl -s https://api.ipify.org || true)"
fi
if [ -z "$IP" ]; then
  echo "Could not work out this machine's public address. Run again as: sudo IP=1.2.3.4 bash setup_vm.sh $CALL" >&2
  exit 1
fi
# sslip.io is a free service that turns 34-12-56-78.sslip.io into the address 34.12.56.78, so no domain has to be bought.
HOST="$(echo "$IP" | tr . -).sslip.io"
cat > /etc/caddy/Caddyfile <<CADDY
$HOST {
    reverse_proxy 127.0.0.1:8080
}
CADDY
systemctl enable caddy >/dev/null
systemctl restart caddy

echo
echo "== Waiting a moment, then checking"
sleep 8
systemctl is-active rbn-collector
curl -s http://127.0.0.1:8080/health || true
echo
echo
echo "Done. Put these two lines in the app's secrets (Streamlit: Settings, Secrets):"
echo
echo "LIVE_RBN_URL = \"https://$HOST\""
echo "LIVE_RBN_KEY = \"$KEY\""
echo
echo "To check from anywhere:  https://$HOST/health   (the certificate can take a minute the first time)"
