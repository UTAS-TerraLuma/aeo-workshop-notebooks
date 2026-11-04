"""
smoke_test.py
=============
Check that this Python environment can run the workshop notebooks: every
package imports, and workshop_utils.load_data() can read the imagery from the
STAC catalogue on Nectar object storage.

On the hub (as any user, or as root over SSH):

    /opt/tljh/user/bin/python hub/smoke_test.py

Locally:

    pixi run python hub/smoke_test.py

Prints one OK/FAIL line per check and exits non-zero if anything failed.
"""

import importlib
import sys
import tempfile
import time
from pathlib import Path

# workshop_utils.py sits in the repo root, one level up from hub/
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Import name for each package the notebooks need (see pixi.toml)
MODULES = [
    "numpy", "scipy", "pandas", "xarray", "rasterio", "rioxarray", "pyproj",
    "pystac", "laspy", "lazrs", "requests", "plotly", "folium", "matplotlib", "ipywidgets", "anywidget",
    "nbformat", "jupyterlab", "notebook",
]

failures = 0


def report(ok, label, detail=""):
    """Print one aligned OK/FAIL line and count failures."""
    global failures
    failures += not ok
    print(f"{'OK  ' if ok else 'FAIL'}  {label:<34} {detail}")


def peak_memory_mb():
    """Peak resident memory of this process in MB (Linux/macOS only)."""
    try:
        import resource
    except ImportError:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports KB, macOS reports bytes
    return peak / 1024 if sys.platform != "darwin" else peak / 1024**2


print(f"Python {sys.version.split()[0]} at {sys.executable}\n")

# 1. Imports
for name in MODULES:
    try:
        mod = importlib.import_module(name)
        report(True, f"import {name}", getattr(mod, "__version__", ""))
    except Exception as exc:
        report(False, f"import {name}", repr(exc))

try:
    import rasterio
    report(True, "GDAL", rasterio.__gdal_version__)
except Exception as exc:
    report(False, "GDAL", repr(exc))

# 2. Plotly FigureWidget needs anywidget (Chapter 3)
try:
    import plotly.graph_objects as go
    go.FigureWidget()
    report(True, "plotly FigureWidget")
except Exception as exc:
    report(False, "plotly FigureWidget", repr(exc))

# 3. Read the imagery from the STAC catalogue
ds = None
try:
    import workshop_utils as wu
    report(True, "import workshop_utils", str(REPO / "workshop_utils.py"))
    start = time.perf_counter()
    href = wu.get_asset_href()
    report(True, "STAC catalogue reachable", href)
    ds = wu.load_data()
    took = time.perf_counter() - start
    size_mb = ds.nbytes / 1024**2
    report(True, "load_data()",
           f"{len(ds.data_vars)} bands, {ds.sizes['x']}x{ds.sizes['y']} px, "
           f"{size_mb:.0f} MB in {took:.1f} s")
except Exception as exc:
    report(False, "load_data()", repr(exc))

# 4. Compute an index and write a GeoTIFF, like Chapters 2-3 do
if ds is not None:
    try:
        indices = wu.compute_indices(ds)
        with tempfile.TemporaryDirectory() as tmp:
            wu.save_indices_to_tiff(indices, out_dir=tmp)
            n = len(list(Path(tmp).rglob("*.tif")))
        report(n > 0, "compute + save GeoTIFFs", f"{n} file(s) written")
    except Exception as exc:
        report(False, "compute + save GeoTIFFs", repr(exc))

# 5. Read part of the LiDAR point cloud (COPC), like Chapter 5 does
try:
    import numpy as np
    from laspy import Bounds, CopcReader
    start = time.perf_counter()
    left, bottom, right, top = wu.LIDAR_AOI_BOUNDS
    with CopcReader.open(wu.get_asset_href(wu.LIDAR_ITEM_ID, asset_key="pointcloud")) as reader:
        points = reader.query(bounds=Bounds(mins=np.array([left, bottom]),
                                            maxs=np.array([right, top])), level=range(0, 5))
    report(len(points) > 0, "COPC point cloud query",
           f"{len(points):,} points in {time.perf_counter() - start:.1f} s")
except Exception as exc:
    report(False, "COPC point cloud query", repr(exc))

peak = peak_memory_mb()
if peak:
    print(f"\nPeak memory of this test: {peak:.0f} MB")
print("\nALL OK" if failures == 0 else f"\n{failures} check(s) FAILED")
sys.exit(1 if failures else 0)
