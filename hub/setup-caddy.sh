#!/usr/bin/env bash
# Put Caddy in front of the hub so it serves https://dronescape.earth and
# https://stac.dronescape.earth (see hub/Caddyfile).
#
# Create the DNS A records first, then on the VM:
#
#   cd /opt/aeo-workshop-notebooks && sudo git pull
#   sudo bash hub/setup-caddy.sh
#
# Safe to re-run, e.g. after editing hub/Caddyfile.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this as root: sudo bash $0" >&2
    exit 1
fi
export HOME="${HOME:-/root}"

echo "== Moving TLJH off ports 80/443 to localhost:8000"
tljh-config set https.enabled false >/dev/null
tljh-config set http.port 8000 >/dev/null
tljh-config reload proxy

if ! command -v caddy >/dev/null; then
    echo "== Installing Caddy (official apt repo)"
    apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gpg
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
        | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
        > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update
    apt-get install -y caddy
fi

echo "== Installing the Caddyfile"
caddy validate --config "$HERE/Caddyfile" --adapter caddyfile
cp "$HERE/Caddyfile" /etc/caddy/Caddyfile
systemctl enable caddy >/dev/null
systemctl reload-or-restart caddy

echo "Done. Certificates are requested in the background; in a minute try:"
echo "  https://dronescape.earth/aeo-workshop-notebooks"
echo "  https://stac.dronescape.earth"
echo "Caddy log: sudo journalctl -u caddy -f"
