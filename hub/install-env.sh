#!/usr/bin/env bash
# Install the workshop packages into the TLJH user environment (/opt/tljh/user).
#
# The package list is read from the [dependencies] table in ../pixi.toml, so
# the hub always matches the local pixi/conda setup. Dev-only tools (see
# EXCLUDE below) are skipped. Everything comes from conda-forge: rasterio and
# GDAL must not come from pip.
#
#   sudo bash hub/install-env.sh            # install / update
#   sudo bash hub/install-env.sh --dry-run  # just print the package list
#
# Safe to re-run: mamba skips packages that are already satisfied.
set -euo pipefail

USER_ENV=/opt/tljh/user
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIXI_TOML="${PIXI_TOML:-$HERE/../pixi.toml}"
# Packages in pixi.toml that attendees don't need
EXCLUDE="nbstripout"
# Python to parse pixi.toml with (needs tomllib, i.e. Python >= 3.11)
PY="${PY:-$USER_ENV/bin/python}"
[ -x "$PY" ] || PY=python3

# Turn `name = ">=1.0"` lines into conda specs: name>=1.0, python=3.12.*, name
PACKAGES=$("$PY" - "$PIXI_TOML" "$EXCLUDE" <<'EOF'
import sys, tomllib
with open(sys.argv[1], "rb") as f:
    deps = tomllib.load(f)["dependencies"]
skip = set(sys.argv[2].split())
specs = []
for name, ver in deps.items():
    if name in skip:
        continue
    if isinstance(ver, dict):          # {version = "...", channel = "..."}
        ver = ver.get("version", "*")
    if ver in ("", "*"):
        specs.append(name)
    elif ver[0].isdigit():             # "3.12.*" -> python=3.12.*
        specs.append(f"{name}={ver}")
    else:                              # ">=1.3.0"
        specs.append(f"{name}{ver}")
print(" ".join(specs))
EOF
)

# Stop the shell glob-expanding specs like python=3.12.* below
set -f
echo "Workshop packages (from $PIXI_TOML):"
printf '  %s\n' $PACKAGES

if [ "${1:-}" = "--dry-run" ]; then
    exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this as root: sudo bash $0" >&2
    exit 1
fi
if [ ! -x "$USER_ENV/bin/mamba" ]; then
    echo "No mamba in $USER_ENV. Install TLJH first." >&2
    exit 1
fi

# conda needs a HOME (cloud-init runs without one)
export HOME="${HOME:-/root}"

# Pin a current sqlite: otherwise the solver can keep TLJH's older packages by
# picking an ancient `sqlite` build that overwrites libsqlite3.so and breaks
# Python's sqlite3 module (and with it jupyter_server).
# shellcheck disable=SC2086  # word-splitting the package list is intended
"$USER_ENV/bin/mamba" install --yes --channel conda-forge $PACKAGES "sqlite>=3.45" "libsqlite>=3.45"
# Put libsqlite's files back in case an old sqlite build had overwritten or,
# on its removal, deleted them.
"$USER_ENV/bin/mamba" install --yes --channel conda-forge --force-reinstall libsqlite

# The hub can't start anyone's server if conda broke the Jupyter pieces that
# TLJH installed with pip, so check them before declaring success.
echo "Checking the user environment..."
"$USER_ENV/bin/python" -c "import sqlite3, jupyter_server.serverapp, jupyterhub, jupyterlab, nbgitpuller, rasterio, rioxarray; print('  imports OK, SQLite', sqlite3.sqlite_version, 'GDAL', rasterio.__gdal_version__)"
[ -x "$USER_ENV/bin/jupyterhub-singleuser" ] || { echo "  FAIL: jupyterhub-singleuser missing" >&2; exit 1; }
echo "  jupyterhub-singleuser OK"
echo "Done."
