#!/usr/bin/env bash
# Apply the workshop settings to a TLJH hub with tljh-config.
#
# Settings come from environment variables (defaults in brackets):
#
#   WORKSHOP_PASSWORD [kept/generated]  The one password attendees share
#                           (8+ characters, not all digits). Attendees type any
#                           username they like plus this password. Saved in
#                           /root/workshop-password.txt; generated if unset.
#   ADMIN_PASSWORD [kept/generated]  Separate password for the admin user(s)
#                           (32+ characters). Saved in /root/admin-password.txt.
#   MEM_LIMIT      [4G]     RAM cap per attendee (kernels are restarted above it).
#   CPU_LIMIT      [2]      CPU cap per attendee (whole cores).
#   CULL_TIMEOUT   [7200]   Stop servers idle this many seconds (2 h, so a
#                           lunch break doesn't kill anyone's kernel).
#   KERNEL_CULL_TIMEOUT [3600]  Shut down a notebook's kernel after this many
#                           idle seconds, even with its tab open, so chapters
#                           people have moved on from free their memory.
#   AEO_DATA_CACHE [/srv/aeo-data]  Shared local copy of the study areas
#                           (hub/prepare_data_cache.py); passed to every server.
#   HTTPS_DOMAIN   []       e.g. aeo-hub.myproject.cloud.edu.au. With
#   HTTPS_EMAIL    []       HTTPS_EMAIL set too, turns on Let's Encrypt.
#                           The DNS record must already point at this VM.
#
#   sudo WORKSHOP_PASSWORD=drone-day-2026 bash hub/configure.sh
#   sudo HTTPS_DOMAIN=aeo-hub.myproject.cloud.edu.au HTTPS_EMAIL=me@utas.edu.au bash hub/configure.sh
#
# Safe to re-run; each run sets the same values again.
set -euo pipefail

MEM_LIMIT="${MEM_LIMIT:-4G}"
CPU_LIMIT="${CPU_LIMIT:-2}"
CULL_TIMEOUT="${CULL_TIMEOUT:-7200}"
KERNEL_CULL_TIMEOUT="${KERNEL_CULL_TIMEOUT:-3600}"
AEO_DATA_CACHE="${AEO_DATA_CACHE:-/srv/aeo-data}"
HTTPS_DOMAIN="${HTTPS_DOMAIN:-}"
HTTPS_EMAIL="${HTTPS_EMAIL:-}"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this as root: sudo bash $0" >&2
    exit 1
fi
command -v tljh-config >/dev/null || { echo "tljh-config not found. Install TLJH first." >&2; exit 1; }
export HOME="${HOME:-/root}"
cfg() { tljh-config "$@" >/dev/null; }

# Use the value passed in, else the one saved by an earlier run, else a new
# random one. Saved root-only so you can read it back with sudo cat.
password() {  # password <file> <value> <length>
    local file=$1 value=$2
    if [ -z "$value" ] && [ -s "$file" ]; then value=$(cat "$file"); fi
    if [ -z "$value" ]; then
        value=$(python3 -c "import secrets; print(''.join(secrets.choice('abcdefghjkmnpqrstuvwxyz23456789') for _ in range($3)))")
    fi
    (umask 077; printf '%s\n' "$value" > "$file")
    printf '%s' "$value"
}
WORKSHOP_PASSWORD=$(password /root/workshop-password.txt "${WORKSHOP_PASSWORD:-}" 12)
ADMIN_PASSWORD=$(password /root/admin-password.txt "${ADMIN_PASSWORD:-}" 40)
case "$WORKSHOP_PASSWORD" in *[!0-9]*) ;; *) echo "WORKSHOP_PASSWORD must not be all digits" >&2; exit 1 ;; esac
[ ${#WORKSHOP_PASSWORD} -ge 8 ] || { echo "WORKSHOP_PASSWORD needs 8+ characters" >&2; exit 1; }
[ ${#ADMIN_PASSWORD} -ge 32 ] || { echo "ADMIN_PASSWORD needs 32+ characters" >&2; exit 1; }

# SharedPasswordAuthenticator is built into JupyterHub 5.3+
/opt/tljh/hub/bin/python -m pip install --quiet "jupyterhub>=5.3,<6"

echo "== Login: one shared workshop password, attendees choose their own username"
cfg set auth.type jupyterhub.authenticators.shared.SharedPasswordAuthenticator
cfg set auth.SharedPasswordAuthenticator.user_password "$WORKSHOP_PASSWORD"
# Admins (users.admin) must log in with this one instead
cfg set auth.SharedPasswordAuthenticator.admin_password "$ADMIN_PASSWORD"
# Any username is accepted (JupyterHub 5 otherwise lets nobody in)
cfg set auth.SharedPasswordAuthenticator.allow_all true
echo "   workshop password: sudo cat /root/workshop-password.txt"
echo "   admin password:    sudo cat /root/admin-password.txt"

echo "== Limits: ${MEM_LIMIT} RAM, ${CPU_LIMIT} CPU per attendee"
cfg set limits.memory "$MEM_LIMIT"
cfg set limits.cpu "$CPU_LIMIT"

echo "== Environment for every server: ${CPU_LIMIT} compute threads, data cache ${AEO_DATA_CACHE}"
# Without these, NumPy/OpenBLAS, GDAL and laspy each start one thread per vCPU
# of the VM (32+ on a large flavour) in every kernel, all fighting over the
# ${CPU_LIMIT}-core quota. TLJH loads extra hub config from jupyterhub_config.d.
mkdir -p /opt/tljh/config/jupyterhub_config.d
cat > /opt/tljh/config/jupyterhub_config.d/aeo-env.py <<EOF
# Written by hub/configure.sh; re-run it to change.
c.Spawner.environment.update({
    "OMP_NUM_THREADS": "${CPU_LIMIT}",
    "OPENBLAS_NUM_THREADS": "${CPU_LIMIT}",
    "MKL_NUM_THREADS": "${CPU_LIMIT}",
    "RAYON_NUM_THREADS": "${CPU_LIMIT}",
    "GDAL_NUM_THREADS": "${CPU_LIMIT}",
    "AEO_DATA_CACHE": "${AEO_DATA_CACHE}",
})
EOF
if ! ls "$AEO_DATA_CACHE"/*.tif >/dev/null 2>&1; then
    echo "   No study-area copy in $AEO_DATA_CACHE yet; notebooks will read from object storage."
    echo "   Create it: sudo /opt/tljh/user/bin/python $(dirname "$0")/prepare_data_cache.py"
fi

echo "== Open JupyterLab (/lab) by default"
cfg set user_environment.default_app jupyterlab

echo "== Hide the hub setup files; shut down kernels idle for ${KERNEL_CULL_TIMEOUT}s"
# nbgitpuller copies the whole repo into each home folder. These names are left
# out of listings (anywhere, not only the repo folder) but can still be opened
# by path. The first line repeats Jupyter Server's defaults, which this replaces.
# It must go in jupyter_server_config.json itself: Jupyter Server reads only
# extension switches from jupyter_server_config.d/, so earlier versions of this
# script, which wrote there, had no effect. Merged in, keeping other settings.
jupyter_etc=/opt/tljh/user/etc/jupyter
rm -f "$jupyter_etc/jupyter_server_config.d/aeo-hide.json"
mkdir -p "$jupyter_etc"
/opt/tljh/user/bin/python - "$jupyter_etc/jupyter_server_config.json" "$KERNEL_CULL_TIMEOUT" <<'EOF'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
config = json.loads(path.read_text() or "{}") if path.exists() else {}
config.setdefault("ContentsManager", {})["hide_globs"] = [
    "__pycache__", "*.pyc", "*.pyo", ".DS_Store", "*.so", "*.dylib", "*~",
    "hub", "pixi.toml", "pixi.lock", "environment.yml", "requirements.txt",
    "pyproject.toml", "__marimo__",
]
# Each open chapter keeps its own kernel and its copy of the data. Shut down
# kernels nobody has run a cell in for a while, even if the tab is still open
# (cull_connected), but never one that is busy running a cell.
config.setdefault("MappingKernelManager", {}).update({
    "cull_idle_timeout": int(sys.argv[2]),
    "cull_interval": 120,
    "cull_connected": True,
    "cull_busy": False,
})
# marimo pilot: marimo-jupyter-extension serves marimo at <server>/marimo/
# inside each attendee's own (capped) server. Use the shared conda
# environment rather than its default per-notebook uv sandbox (which would
# lack GDAL), and free a notebook's kernel 15 min after its tab closes.
config.setdefault("MarimoProxyConfig", {}).update({
    "sandbox": None,
    "marimo_path": "/opt/tljh/user/bin/marimo",
    "session_ttl": 900,
    "skip_update_check": True,
})
path.write_text(json.dumps(config, indent=2) + "\n")
EOF

echo "== Idle culler: stop servers idle for ${CULL_TIMEOUT}s"
cfg set services.cull.enabled true
cfg set services.cull.timeout "$CULL_TIMEOUT"
cfg set services.cull.every 300

if [ -n "$HTTPS_DOMAIN" ] && [ -f /etc/caddy/Caddyfile ]; then
    echo "Caddy handles HTTPS on this hub (hub/setup-caddy.sh); leave HTTPS_DOMAIN unset." >&2
    exit 1
fi
if [ -n "$HTTPS_DOMAIN" ] && [ -n "$HTTPS_EMAIL" ]; then
    echo "== HTTPS via Let's Encrypt for $HTTPS_DOMAIN"
    if ! getent hosts "$HTTPS_DOMAIN" >/dev/null; then
        echo "   $HTTPS_DOMAIN does not resolve yet. Create the DNS record first." >&2
        exit 1
    fi
    echo "   $HTTPS_DOMAIN -> $(getent hosts "$HTTPS_DOMAIN" | awk '{print $1}')   (this VM: $(hostname -I))"
    cfg set https.enabled true
    cfg set https.letsencrypt.email "$HTTPS_EMAIL"
    tljh-config unset https.letsencrypt.domains >/dev/null 2>&1 || true
    cfg add-item https.letsencrypt.domains "$HTTPS_DOMAIN"
fi

echo "== Reloading the hub"
tljh-config reload
if [ -n "$HTTPS_DOMAIN" ] && [ -n "$HTTPS_EMAIL" ]; then
    tljh-config reload proxy
    echo "   Certificate is requested in the background; try https://$HTTPS_DOMAIN in a minute."
fi
echo "Done. Current settings: sudo tljh-config show"
