"""
prepare_data_cache.py
=====================
Download the two workshop study areas once into a shared folder on the hub:

- the multispectral window that load_data() reads (~50 MB GeoTIFF)
- the LiDAR points that load_lidar_points() reads (~180 MB .npz)

Without this, every attendee pulls ~110 MB from object storage in each of
Chapters 1-4 and ~100 MB in Chapter 5, all at the same moment. With it, the
notebooks read the local copy (same values) and only fall back to the STAC
catalogue if the files are missing. Nothing in the notebooks changes.

On the hub, as root (configure.sh points every user server at this folder):

    sudo /opt/tljh/user/bin/python /opt/aeo-workshop-notebooks/hub/prepare_data_cache.py

Another folder (then set AEO_DATA_CACHE to it for the user servers):

    python hub/prepare_data_cache.py /some/folder

Safe to re-run; it overwrites the files.
"""

import os
import sys
import time
from pathlib import Path

# workshop_utils.py sits in the repo root, one level up from hub/
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import workshop_utils as wu  # noqa: E402

cache_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else wu.DATA_CACHE_DIR
start = time.perf_counter()
written = wu.prepare_data_cache(cache_dir)

# Readable by every attendee, writable only by root
os.chmod(cache_dir, 0o755)
for path in written:
    os.chmod(path, 0o644)
print(f"Done in {time.perf_counter() - start:.0f} s. Cache folder: {cache_dir}")
