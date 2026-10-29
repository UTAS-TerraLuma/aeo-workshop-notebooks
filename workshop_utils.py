"""
workshop_utils.py
=================
Shared helpers for the MicaSense drone data analysis workshop.

This file must sit in the same folder as the workshop notebooks. The data
folder must also be here:

    workshop/
    ├── data/
    │   ├── NTABRT0007-20240828-ms-cog-subset.tif
    │   └── NTABRT0007-20240828-ms-cog-subset3.tif
    ├── workshop_utils.py          ← this file
    ├── ch1_bands_and_visualisation.ipynb
    ├── ch2_spectral_indices.ipynb
    └── ch3_normalisation_and_maps.ipynb
"""

# What this does: provides the shared raster, index, and display helpers used
# by all three Jupyter notebooks.
from pathlib import Path
import struct
import zlib
import base64
import numpy as np
import rasterio
import xarray as xr

_HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Default data path — notebooks can override this if needed
# ---------------------------------------------------------------------------
# Chapters 2-4 use subset3; Chapter 1 sets its own RASTER_FILENAME (subset).
DATA_PATH = _HERE / "data" / "NTABRT0007-20240828-ms-cog-subset3.tif"

# ---------------------------------------------------------------------------
# Band catalogue — MicaSense RedEdge-P Dual, 10 bands
# ---------------------------------------------------------------------------
BAND_INFO = [
    {"var": "coastal",  "name": "Coastal",      "nm": 444, "fwhm": 28,  "colour": "#7744bb"},
    {"var": "blue",     "name": "Blue",          "nm": 475, "fwhm": 32,  "colour": "#3355cc"},
    {"var": "green",    "name": "Green",         "nm": 531, "fwhm": 14,  "colour": "#22aa44"},
    {"var": "green560", "name": "Green-560",     "nm": 560, "fwhm": 27,  "colour": "#44bb33"},
    {"var": "red650",   "name": "Red-650",       "nm": 650, "fwhm": 16,  "colour": "#cc4422"},
    {"var": "red668",   "name": "Red-668",       "nm": 668, "fwhm": 14,  "colour": "#dd2222"},
    {"var": "re705",    "name": "Red-Edge 705",  "nm": 705, "fwhm": 10,  "colour": "#cc8800"},
    {"var": "re717",    "name": "Red-Edge 717",  "nm": 717, "fwhm": 12,  "colour": "#ddaa00"},
    {"var": "nir740",   "name": "NIR-740",       "nm": 740, "fwhm": 18,  "colour": "#009999"},
    {"var": "nir842",   "name": "NIR-842",       "nm": 842, "fwhm": 57,  "colour": "#006688"},
]

# ---------------------------------------------------------------------------
# Index catalogue
# NDVI is included as a widely-known reference index.
# CCI, CIRE, CRI2, ARI2 are the four pigment-sensitive indices for this workshop.
# ---------------------------------------------------------------------------
INDEX_INFO = {
    "NDVI": {
        "full_name":     "Normalised Difference Vegetation Index",
        "formula":       "(NIR-842 − Red-668) / (NIR-842 + Red-668)",
        "bands_used":    "NIR-842, Red-668",
        "purpose":       "Reference index. Measures overall vegetation density and greenness.",
        "interpretation":"0.6–0.9 = healthy dense canopy  ·  0.2–0.5 = sparse/stressed  ·  <0.1 = soil or water",
        "cmap":          "YlGn",
        "vlim":          (-0.1, 0.85),
        "pigment":       False,
    },
    # "CCI": {
        # "full_name":     "Chlorophyll/Carotenoid Index",
        # "formula":       "(Green-531 − Red-668) / (Green-531 + Red-668)",
        # "bands_used":    "Green-531, Red-668",
        # "purpose":       "Tracks the ratio of chlorophyll (green) to carotenoid (red-absorbing) pigments.",
        # "interpretation":"Higher = more chlorophyll relative to carotenoids  ·  Lower = pigment stress or senescence",
        # "cmap":          "RdYlGn",
        # "vlim":          (-1.0, 1.0),
        # "pigment":       True,
    # },
    "CIRE": {
        "full_name":     "Chlorophyll Index Red-Edge",
        "formula":       "(NIR-842 / Red-Edge-705) − 1",
        "bands_used":    "NIR-842, Red-Edge-705",
        "purpose":       "Sensitive to total leaf chlorophyll content. Less saturated than NDVI in dense canopies.",
        "interpretation":"Higher = more total chlorophyll  ·  Dense productive canopy typically 1–4",
        "cmap":          "YlOrRd",
        "vlim":          (0.0, 4.0),
        "pigment":       True,
    },
    "CRI2": {
        "full_name":     "Carotenoid Reflectance Index 2",
        "formula":       "(1 / Green-531) − (1 / Red-Edge-705)",
        "bands_used":    "Green-531, Red-Edge-705",
        "purpose":       "Carotenoid-sensitive proxy using the nearest available bands to the standard 510 nm and 700 nm wavelengths.",
        "interpretation":"Higher = stronger carotenoid-related spectral response; values are scene- and sensor-dependent",
        "cmap":          "YlOrBr",
        "vlim":          (-1.0, 10.0),
        "pigment":       True,
    },
    "ARI2": {
        "full_name":     "Anthocyanin Reflectance Index 2  (canopy-corrected)",
        "formula":       "NIR-842 × [(1 / Green-560) − (1 / Red-Edge-705)]",
        "bands_used":    "NIR-842, Green-560, Red-Edge-705",
        "purpose":       "ARI weighted by NIR reflectance. Corrects for variation in leaf area index.",
        "interpretation":"More robust than ARI where canopy density varies across the scene",
        "cmap":          "PuRd",
        "vlim":          (0.0, 5.0),
        "pigment":       True,
    },
}

# Ordered list of all five workshop index names
WORKSHOP_INDICES = list(INDEX_INFO.keys())   # ["NDVI","CCI","CIRE","CRI2","ARI2"]

# # ---------------------------------------------------------------------------
# # Data-loading helpers
# # ---------------------------------------------------------------------------

def load_data(path=None):
    """
    Load the MicaSense GeoTIFF as an xarray.Dataset.
    NoData pixels (value 0 in the raw file) are automatically set to NaN.
    If path is None, DATA_PATH is used.
    """
    p = Path(path) if path else DATA_PATH
    if not p.exists():
        raise FileNotFoundError(
            f"Raster not found: {p}\n"
            f"Copy the 10-band GeoTIFF to data/{DATA_PATH.name}, or set DATA_PATH "
            "in the notebook to the correct file."
        )

    with rasterio.open(p) as src:
        if src.count != len(BAND_INFO):
            raise ValueError(
                f"Expected {len(BAND_INFO)} bands for a MicaSense RedEdge-P "
                f"Dual image, but {p.name} contains {src.count}."
            )

        data = src.read(out_dtype="float32")
        nodata = src.nodata
        invalid = ~np.isfinite(data)
        if nodata is not None:
            invalid |= data == nodata
        # Workshop surface-reflectance images use zero for background/NoData.
        invalid |= data <= 0
        data[invalid] = np.nan

        x = src.transform.c + (np.arange(src.width) + 0.5) * src.transform.a
        y = src.transform.f + (np.arange(src.height) + 0.5) * src.transform.e
        variables = {
            band["var"]: (("y", "x"), data[i])
            for i, band in enumerate(BAND_INFO)
        }
        ds = xr.Dataset(variables, coords={"x": x, "y": y})
        ds.attrs.update({
            "filename": p.name,
            "source_path": str(p.resolve()),
            "instrument": "MicaSense RedEdge-P Dual",
            "image_width_px": src.width,
            "image_height_px": src.height,
            "pixel_size_m": float(abs(src.transform.a)),
            "crs": str(src.crs),
            "transform": tuple(src.transform),
        })
        for band in BAND_INFO:
            ds[band["var"]].attrs.update({
                "long_name": band["name"],
                "centre_wavelength_nm": band["nm"],
                "fwhm_nm": band["fwhm"],
            })
    return ds


# def compute_indices(ds, names=None):
#     """
#     Calculate spectral indices and attach them as new variables in ds.
#     names: list of index keys from INDEX_INFO; defaults to all five.
#     Returns the updated dataset.
#     """
#     if names is None:
#         names = WORKSHOP_INDICES

#     formulas = {
#         "NDVI": lambda d: _safe_divide(d["nir842"] - d["red668"], d["nir842"] + d["red668"]),
#         "CCI":  lambda d: _safe_divide(d["green"] - d["red668"], d["green"] + d["red668"]),
#         "CIRE": lambda d: _safe_divide(d["nir842"], d["re705"]) - 1.0,
#         "CRI2": lambda d: _safe_divide(1.0, d["green"]) - _safe_divide(1.0, d["re705"]),
#         "ARI2": lambda d: d["nir842"] * (
#             _safe_divide(1.0, d["green560"]) - _safe_divide(1.0, d["re705"])
#         ),
#     }
#     unknown = sorted(set(names) - formulas.keys())
#     if unknown:
#         raise KeyError(f"Unknown workshop index/indices: {', '.join(unknown)}")

#     out = ds.copy()
#     for name in names:
#         values = formulas[name](out).astype("float32")
#         values = values.where(np.isfinite(values))
#         values.attrs.update({
#             "long_name": INDEX_INFO[name]["full_name"],
#             "formula": INDEX_INFO[name]["formula"],
#         })
#         out[name] = values
#     return out


# def _safe_divide(numerator, denominator, eps=1e-10):
#     """Divide xarray objects while masking zero or near-zero denominators."""
#     return numerator / denominator.where(np.abs(denominator) > eps)


def compute_indices(ds, names=None, reflectance_floor=0.01):
    """
    Calculate spectral indices and attach them as new variables in ds.

    Invalid input reflectance (non-finite, <= reflectance_floor, or > 1)
    is excluded. Set reflectance_floor based on the sensor's reliable
    measurement range.

    names: index keys from INDEX_INFO; defaults to all workshop indices.
    Returns a copy of ds with the requested index variables added.

    The reflectance floor is a minimum reflectance cutoff. Values at or below it are treated as unreliable and excluded from index calculations.

    It helps prevent very small positive values from making reciprocal indices such as CRI2 and ARI2 extremely large. 
    In the function, reflectance_floor=0.01 means input values must be greater than 0.01 and no more than 1.

    That cutoff is a choice, not a universal constant. Set it using your sensor’s calibration or noise characteristics; increasing it also excludes more dark pixels.

    """
    if names is None:
        names = WORKSHOP_INDICES

    formulas = {
        "NDVI": lambda d: _safe_divide(
            d["nir842"] - d["red668"],
            d["nir842"] + d["red668"],
        ),
        "CCI": lambda d: _safe_divide(
            d["green"] - d["red668"],
            d["green"] + d["red668"],
        ),
        "CIRE": lambda d: _safe_divide(d["nir842"], d["re705"]) - 1.0,
        "CRI2": lambda d: (
            _safe_divide(1.0, d["green"])
            - _safe_divide(1.0, d["re705"])
        ),
        "ARI2": lambda d: d["nir842"] * (
            _safe_divide(1.0, d["green560"])
            - _safe_divide(1.0, d["re705"])
        ),
    }

    required_bands = {
        "NDVI": ("nir842", "red668"),
        "CCI": ("green", "red668"),
        "CIRE": ("nir842", "re705"),
        "CRI2": ("green", "re705"),
        "ARI2": ("nir842", "green560", "re705"),
    }

    unknown = sorted(set(names) - formulas.keys())
    if unknown:
        raise KeyError(
            f"Unknown workshop index/indices: {', '.join(unknown)}"
        )

    # Only use input pixels with finite, plausible reflectance.
    valid_band = {
        band: (
            np.isfinite(ds[band])
            & (ds[band] > reflectance_floor)
            & (ds[band] <= 1)
        )
        for band in set(
            band
            for name in names
            for band in required_bands[name]
        )
    }

    out = ds.copy()

    for name in names:
        valid_inputs = valid_band[required_bands[name][0]]
        for band in required_bands[name][1:]:
            valid_inputs = valid_inputs & valid_band[band]

        values = formulas[name](out).astype("float32")
        values = values.where(valid_inputs & np.isfinite(values))
        values.attrs.update({
            "long_name": INDEX_INFO[name]["full_name"],
            "formula": INDEX_INFO[name]["formula"],
            "minimum_input_reflectance": float(reflectance_floor),
        })
        out[name] = values

    return out


def _safe_divide(numerator, denominator, eps=1e-10):
    """Divide xarray values, masking non-finite or near-zero denominators."""
    safe_denominator = denominator.where(
        np.isfinite(denominator)
        & (np.abs(denominator) > eps)
    )
    result = numerator / safe_denominator
    return result.where(np.isfinite(result))


# ---------------------------------------------------------------------------
# Array processing helpers
# ---------------------------------------------------------------------------

def pstretch(arr, lo=2, hi=98):
    """
    Percentile stretch for display: map arr to [0, 1] using the p-lo and
    p-hi percentiles so that outlier pixels do not dominate the colour scale.
    NaN pixels are set to 0 after stretching.
    """
    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        return np.zeros_like(arr, dtype="float32")
    vmin, vmax = np.percentile(valid, [lo, hi])
    out = (arr.astype("float32") - vmin) / max(float(vmax - vmin), 1e-9)
    out = np.clip(out, 0.0, 1.0)
    out[~np.isfinite(arr)] = 0.0
    return out


def minmax(arr):
    """
    Min-max normalise arr to [0, 1] using the scene's own valid min and max.
    Formula: (x − scene_min) / (scene_max − scene_min)
    NaN pixels are set to 0.
    """
    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        return np.zeros_like(arr, dtype="float32")
    vmin, vmax = float(valid.min()), float(valid.max())
    out = (arr.astype("float32") - vmin) / max(vmax - vmin, 1e-9)
    out = np.clip(out, 0.0, 1.0)
    out[~np.isfinite(arr)] = 0.0
    return out

def to_uint8(rgb01):
    """Convert a float image scaled to [0, 1] into uint8 (NaN -> 0)."""
    rgb01 = np.nan_to_num(np.asarray(rgb01, dtype="float32"), nan=0.0, posinf=1.0, neginf=0.0)
    return np.round(np.clip(rgb01, 0.0, 1.0) * 255).astype(np.uint8)


def array_to_png_b64(rgb_uint8):
    """
    Convert a (H, W, 3) uint8 numpy array to a PNG data-URI string.
    Uses only the Python standard library — no Pillow required.
    The returned string can be used directly in HTML <img> tags or
    as the image source in a Folium ImageOverlay.
    """
    h, w = rgb_uint8.shape[:2]

    def _chunk(ctype, data):
        # PNG chunk: Length(4) + Type(4) + Data(n) + CRC32(4)
        payload = ctype + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    sig  = b"\x89PNG\r\n\x1a\n"
    # IHDR: width, height, bit-depth=8, colour-type=2(RGB), compress=0, filter=0, interlace=0
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    # Raw pixel data: filter-byte 0 (None) + R,G,B bytes per row
    raw  = b"".join(b"\x00" + rgb_uint8[y].tobytes() for y in range(h))
    idat = _chunk(b"IDAT", zlib.compress(raw, level=6))
    iend = _chunk(b"IEND", b"")

    png_bytes = sig + ihdr + idat + iend
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode()


# ---------------------------------------------------------------------------
# Index export and visualisation helpers
# ---------------------------------------------------------------------------

INDEX_CMAPS = {
    name: info["cmap"]
    for name, info in INDEX_INFO.items()
}


def _resolve_indices(ds, indices=None):
    """Return a validated list of workshop indices present in *ds*."""
    if indices is None:
        names = [name for name in WORKSHOP_INDICES if name in ds]
    elif isinstance(indices, str):
        names = [indices]
    else:
        names = list(indices)

    if not names:
        raise ValueError(
            "No workshop indices were found. Run compute_indices(ds) first."
        )

    unsupported = [name for name in names if name not in WORKSHOP_INDICES]
    if unsupported:
        raise ValueError(
            "Unsupported workshop indices: " + ", ".join(unsupported) + ". "
            "Available indices: " + ", ".join(WORKSHOP_INDICES)
        )

    missing = [name for name in names if name not in ds]
    if missing:
        raise ValueError(
            "Indices not present in the Dataset: " + ", ".join(missing) + ". "
            "Run compute_indices(ds, names=...) first."
        )

    return names


def _dataset_crs(ds):
    """Read a rasterio CRS from the Dataset's rioxarray or attrs metadata."""
    try:
        crs = ds.rio.crs
    except (AttributeError, RuntimeError):
        crs = None
    if crs is None:
        crs = ds.attrs.get("crs")
    if crs is None:
        raise ValueError("The Dataset does not contain CRS information.")
    return rasterio.crs.CRS.from_user_input(crs)


def _dataset_transform(ds):
    """Read or reconstruct the affine transform for a Dataset."""
    from affine import Affine

    stored = ds.attrs.get("transform")
    if stored is not None:
        if isinstance(stored, Affine):
            return stored
        values = tuple(stored)
        if len(values) >= 6:
            return Affine(*values[:6])

    if "x" not in ds.coords or "y" not in ds.coords:
        raise ValueError("The Dataset must contain one-dimensional x/y coordinates.")

    x = np.asarray(ds["x"].values, dtype="float64")
    y = np.asarray(ds["y"].values, dtype="float64")
    if x.ndim != 1 or y.ndim != 1 or x.size < 2 or y.size < 2:
        raise ValueError("At least two one-dimensional x/y coordinates are required.")

    dx = float(np.median(np.diff(x)))
    dy = float(np.median(np.diff(y)))
    return Affine(dx, 0.0, x[0] - dx / 2.0,
                  0.0, dy, y[0] - dy / 2.0)


def save_indices_to_tiff(
    ds,
    indices=None,
    out_path=None,
    out_dir=None,
    nodata=np.nan,
    compress="deflate",
    dtype="float32",
):
    """
    Export NDVI, CCI, CIRE, CRI2, ARI2 as GeoTIFF files.

    Use ``out_path`` to create one multi-band GeoTIFF, or ``out_dir`` to
    create one file per index. If neither is supplied, per-index files are
    written to the current directory. CRS, transform, dimensions, band names,
    formulas and NoData are preserved.

    Examples
    --------
    save_indices_to_tiff(ds, indices="NDVI", out_path="NDVI.tif")
    save_indices_to_tiff(ds, indices=["CIRE", "CRI2", "ARI2"], out_dir="outputs")
    save_indices_to_tiff(ds, out_path="workshop_indices.tif")
    """
    if out_path is not None and out_dir is not None:
        raise ValueError("Use either out_path or out_dir, not both.")

    names = _resolve_indices(ds, indices)
    crs = _dataset_crs(ds)
    transform = _dataset_transform(ds)
    dtype = np.dtype(dtype).name

    if "x" not in ds.sizes or "y" not in ds.sizes:
        raise ValueError("The Dataset must have x and y dimensions.")
    height, width = ds.sizes["y"], ds.sizes["x"]

    if nodata is not None and np.issubdtype(np.dtype(dtype), np.integer):
        try:
            nodata_is_nan = bool(np.isnan(nodata))
        except TypeError:
            nodata_is_nan = False
        if nodata_is_nan:
            raise ValueError("NaN NoData requires a floating-point output dtype.")

    compression = None if str(compress).lower() == "none" else compress

    def prepared_array(name):
        da = ds[name].squeeze(drop=True)
        if "y" not in da.dims or "x" not in da.dims:
            raise ValueError(f"{name} must contain y and x dimensions.")
        arr = np.asarray(da.transpose("y", "x").values, dtype=dtype)
        if arr.shape != (height, width):
            raise ValueError(
                f"{name} has shape {arr.shape}; expected {(height, width)}."
            )
        if nodata is not None and np.isfinite(nodata):
            arr = np.where(np.isfinite(arr), arr, nodata).astype(dtype)
        return arr

    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "dtype": dtype,
        "crs": crs,
        "transform": transform,
        "nodata": nodata,
    }
    if compression is not None:
        profile["compress"] = compression

    written = []

    if out_path is not None:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(path, "w", count=len(names), **profile) as dst:
            for band_number, name in enumerate(names, start=1):
                dst.write(prepared_array(name), band_number)
                dst.set_band_description(band_number, name)
                dst.update_tags(
                    band_number,
                    index=name,
                    full_name=INDEX_INFO[name]["full_name"],
                    formula=INDEX_INFO[name]["formula"],
                )
        written.append(path)
    else:
        directory = Path(".") if out_dir is None else Path(out_dir)
        directory.mkdir(parents=True, exist_ok=True)
        for name in names:
            path = directory / f"{name}.tif"
            with rasterio.open(path, "w", count=1, **profile) as dst:
                dst.write(prepared_array(name), 1)
                dst.set_band_description(1, name)
                dst.update_tags(
                    1,
                    index=name,
                    full_name=INDEX_INFO[name]["full_name"],
                    formula=INDEX_INFO[name]["formula"],
                )
            written.append(path)

    for path in written:
        print(f"Saved: {path}")
    return written


from pathlib import Path
import numpy as np
from pyproj import CRS
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_indices(
    ds,
    indices=None,
    colorscale=None,
    cols=2,
    robust=True,
    vmin=None,
    vmax=None,
    show_colorbars=False,
    width_per_panel=430,
    height_per_panel=390,
    save_path=None,
    show=True,
):
    """
    Plot spectral indices interactively with Plotly using the dataset's
    native projected CRS.

    The original arrays are displayed without spatial downsampling.
    Projected x/y coordinates are used directly, normally as Easting and
    Northing in metres.

    Parameters
    ----------
    ds : xarray.Dataset
        Dataset containing x/y coordinates and calculated indices.
    indices : sequence of str, optional
        Index variables to plot.
    colorscale : str or dict, optional
        Plotly colour scale, either global or keyed by index.
    cols : int
        Number of subplot columns.
    robust : bool
        If True, use P2-P98 as the default display limits.
    vmin, vmax : float or dict, optional
        Explicit display limits, either global or keyed by index.
    show_colorbars : bool
        Show a separate colour bar for each index.
    save_path : str or Path, optional
        Standalone HTML output path.
    show : bool
        Display the figure in the notebook.
    """

    names = _resolve_indices(ds, indices)

    if cols < 1:
        raise ValueError("cols must be at least 1.")

    # --------------------------------------------------------
    # Read projected coordinates
    # --------------------------------------------------------
    x = np.asarray(ds["x"].values, dtype=np.float64)
    y = np.asarray(ds["y"].values, dtype=np.float64)

    rows_px = ds.sizes["y"]
    cols_px = ds.sizes["x"]

    if x.size != cols_px or y.size != rows_px:
        raise ValueError(
            "The x/y coordinate lengths do not match the raster dimensions."
        )

    if x.ndim != 1 or y.ndim != 1:
        raise ValueError("Projected x and y coordinates must be one-dimensional.")

    if x.size < 2 or y.size < 2:
        raise ValueError("At least two x and y coordinates are required.")

    # --------------------------------------------------------
    # Read and validate the source CRS
    # --------------------------------------------------------
    source_crs = CRS.from_user_input(_dataset_crs(ds))

    if not source_crs.is_projected:
        raise ValueError(
            "plot_indices expected a projected CRS, but found "
            f"{source_crs.to_string()}."
        )

    crs_name = source_crs.name
    crs_id = source_crs.to_string()

    # Determine the projected coordinate unit
    unit_name = (
        source_crs.axis_info[0].unit_name
        if source_crs.axis_info
        else "projected unit"
    )

    if unit_name and unit_name.lower() in {"metre", "meter", "metres", "meters"}:
        unit_label = "m"
    else:
        unit_label = unit_name or "projected units"

    # --------------------------------------------------------
    # Calculate exact raster extent from pixel centres
    # --------------------------------------------------------
    dx = float(np.median(np.diff(x)))
    dy = float(np.median(np.diff(y)))

    if np.isclose(dx, 0) or np.isclose(dy, 0):
        raise ValueError("The x/y coordinate spacing cannot be zero.")

    x_range = sorted([
        float(x[0] - dx / 2),
        float(x[-1] + dx / 2),
    ])

    y_range = sorted([
        float(y[0] - dy / 2),
        float(y[-1] + dy / 2),
    ])

    # --------------------------------------------------------
    # Parameter helpers
    # --------------------------------------------------------
    def option_for(option, name, fallback):
        if isinstance(option, dict):
            return option.get(name, fallback)
        return fallback if option is None else option

    def display_limits(name, valid):
        if robust:
            default_low, default_high = np.percentile(valid, [2, 98])
        else:
            default_low = np.min(valid)
            default_high = np.max(valid)

        low = float(option_for(vmin, name, default_low))
        high = float(option_for(vmax, name, default_high))

        if not np.isfinite(low) or not np.isfinite(high):
            raise ValueError(
                f"Non-finite display limits for {name}: {low}, {high}"
            )

        if low >= high:
            if np.isclose(low, high):
                high = low + 1e-6
            else:
                raise ValueError(
                    f"Invalid display limits for {name}: {low}, {high}"
                )

        return low, high

    # --------------------------------------------------------
    # Create subplot grid
    # --------------------------------------------------------
    ncols = min(int(cols), len(names))
    nrows = (len(names) + ncols - 1) // ncols

    titles = [
        f"{name} — {INDEX_INFO[name]['full_name']}"
        for name in names
    ]

    titles.extend([""] * (nrows * ncols - len(titles)))

    fig = make_subplots(
        rows=nrows,
        cols=ncols,
        subplot_titles=titles,
        horizontal_spacing=0.10,
        vertical_spacing=0.12,
    )

    # --------------------------------------------------------
    # Add index maps
    # --------------------------------------------------------
    for position, name in enumerate(names):
        row = position // ncols + 1
        col = position % ncols + 1

        array = np.asarray(
            ds[name].transpose("y", "x").values,
            dtype=np.float32,
        )

        if array.shape != (rows_px, cols_px):
            raise ValueError(
                f"{name} has shape {array.shape}; expected "
                f"{(rows_px, cols_px)}."
            )

        valid = array[np.isfinite(array)]

        if valid.size == 0:
            continue

        low, high = display_limits(name, valid)

        scale = option_for(
            colorscale,
            name,
            INDEX_CMAPS.get(name, "Viridis"),
        )

        # Plotly subplot axis identifier
        axis_number = position + 1
        axis_suffix = "" if axis_number == 1 else str(axis_number)

        fig.add_trace(
            go.Heatmap(
                x=x,
                y=y,
                z=array,
                colorscale=scale,
                zmin=low,
                zmax=high,
                zsmooth=False,
                showscale=show_colorbars,
                colorbar=(
                    dict(
                        title=name,
                        thickness=12,
                    )
                    if show_colorbars
                    else None
                ),
                hovertemplate=(
                    f"<b>{name}</b><br>"
                    f"Easting: %{{x:,.3f}} {unit_label}<br>"
                    f"Northing: %{{y:,.3f}} {unit_label}<br>"
                    "Value: %{z:.4f}"
                    "<extra></extra>"
                ),
                name="",
            ),
            row=row,
            col=col,
        )

        # Projected x axis
        fig.update_xaxes(
            title_text=(
                f"Easting ({unit_label})"
                if row == nrows
                else None
            ),
            range=x_range,
            tickformat=",.0f",
            constrain="domain",
            row=row,
            col=col,
        )

        # Projected y axis with equal physical scale
        fig.update_yaxes(
            title_text=(
                f"Northing ({unit_label})"
                if col == 1
                else None
            ),
            range=y_range,
            tickformat=",.0f",
            scaleanchor=f"x{axis_suffix}",
            scaleratio=1,
            constrain="domain",
            row=row,
            col=col,
        )

    # --------------------------------------------------------
    # Layout
    # --------------------------------------------------------
    filename = ds.attrs.get(
        "filename",
        "MicaSense RedEdge-P Dual",
    )

    fig.update_layout(
        title=dict(
            text=(
                f"Workshop Spectral Indices — {filename}<br>"
                f"<sup>{crs_name} ({crs_id})</sup>"
            ),
            x=0.5,
            xanchor="center",
        ),
        template="plotly_white",
        width=max(750, width_per_panel * ncols),
        height=max(500, height_per_panel * nrows + 100),
        showlegend=False,
        margin=dict(
            l=90,
            r=50,
            t=120,
            b=80,
        ),
    )

    # --------------------------------------------------------
    # Optional standalone HTML export
    # --------------------------------------------------------
    if save_path is not None:
        path = Path(save_path)

        if path.suffix.lower() != ".html":
            raise ValueError(
                "plot_indices save_path must end in '.html'."
            )

        path.parent.mkdir(parents=True, exist_ok=True)

        fig.write_html(
            path,
            include_plotlyjs=True,
        )

        print(f"Saved: {path}")

    if show:
        fig.show(
            config={
                "scrollZoom": True,
                "displaylogo": False,
            }
        )

    return fig
    
    
    
def plot_indices2(
    ds,
    indices=None,
    colorscale=None,
    cols=2,
    robust=True,
    vmin=None,
    vmax=None,
    show_colorbars=False,
    width_per_panel=430,
    height_per_panel=390,
    save_path=None,
    show=True,
):
    """
    Plot spectral indices interactively with Plotly using the native
    projected CRS.

    Axis labels use compact offset notation, for example:

        Easting ticks:  5, 10, 15, 20
        Axis offset:    +4.618e5

    Full projected coordinates are retained in the hover information.
    """

    names = _resolve_indices(ds, indices)

    if cols < 1:
        raise ValueError("cols must be at least 1.")

    # ========================================================
    # Projected coordinates and CRS
    # ========================================================
    x = np.asarray(ds["x"].values, dtype=np.float64)
    y = np.asarray(ds["y"].values, dtype=np.float64)

    rows_px = ds.sizes["y"]
    cols_px = ds.sizes["x"]

    if x.ndim != 1 or y.ndim != 1:
        raise ValueError("The x and y coordinates must be one-dimensional.")

    if x.size != cols_px or y.size != rows_px:
        raise ValueError(
            "The x/y coordinate lengths do not match the raster dimensions."
        )

    if x.size < 2 or y.size < 2:
        raise ValueError("At least two x and y coordinates are required.")

    source_crs = CRS.from_user_input(_dataset_crs(ds))

    if not source_crs.is_projected:
        raise ValueError(
            "Expected a projected CRS, but found "
            f"{source_crs.to_string()}."
        )

    crs_name = source_crs.name
    crs_id = source_crs.to_string()

    unit_name = (
        source_crs.axis_info[0].unit_name
        if source_crs.axis_info
        else "projected unit"
    )

    if unit_name.lower() in {"metre", "meter", "metres", "meters"}:
        unit_label = "m"
    else:
        unit_label = unit_name

    # ========================================================
    # Exact raster extent from pixel centres
    # ========================================================
    dx = float(np.median(np.diff(x)))
    dy = float(np.median(np.diff(y)))

    if np.isclose(dx, 0) or np.isclose(dy, 0):
        raise ValueError("The x/y coordinate spacing cannot be zero.")

    x_range = sorted([
        float(x[0] - dx / 2),
        float(x[-1] + dx / 2),
    ])

    y_range = sorted([
        float(y[0] - dy / 2),
        float(y[-1] + dy / 2),
    ])

    # ========================================================
    # Compact projected-axis formatting
    # ========================================================
    def calculate_axis_offset(axis_range):
        """Calculate a Matplotlib-style additive coordinate offset."""

        lower, upper = sorted(axis_range)
        span = upper - lower

        if not np.isfinite(span) or span <= 0:
            return 0.0

        centre = (lower + upper) / 2

        # Use offset notation only when coordinates are much larger
        # than the displayed spatial extent.
        if abs(centre) < 100 * span:
            return 0.0

        offset_step = 10 ** (np.floor(np.log10(span)) + 1)
        return float(np.floor(lower / offset_step) * offset_step)

    def nice_tick_values(axis_range, target_ticks=6):
        """Calculate approximately evenly spaced, rounded tick positions."""

        lower, upper = sorted(axis_range)
        span = upper - lower

        if not np.isfinite(span) or span <= 0:
            return np.array([lower])

        raw_step = span / max(target_ticks - 1, 1)
        magnitude = 10 ** np.floor(np.log10(raw_step))
        fraction = raw_step / magnitude

        if fraction <= 1:
            nice_fraction = 1
        elif fraction <= 2:
            nice_fraction = 2
        elif fraction <= 2.5:
            nice_fraction = 2.5
        elif fraction <= 5:
            nice_fraction = 5
        else:
            nice_fraction = 10

        step = nice_fraction * magnitude

        first = np.ceil(lower / step) * step
        last = np.floor(upper / step) * step

        ticks = np.arange(
            first,
            last + step * 0.5,
            step,
        )

        return ticks

    def format_local_tick(value, offset, ticks):
        """Format tick value after subtracting the displayed offset."""

        local_value = value - offset

        if np.isclose(local_value, 0):
            local_value = 0.0

        if len(ticks) > 1:
            step = abs(float(ticks[1] - ticks[0]))
        else:
            step = 1.0

        if step >= 1:
            decimals = 0
        else:
            decimals = max(
                0,
                int(np.ceil(-np.log10(step))),
            )

        return f"{local_value:.{decimals}f}"

    def format_offset(offset):
        """Format offsets as +4.618e5 or +6.2375e6."""

        if np.isclose(offset, 0):
            return ""

        sign = "+" if offset > 0 else "−"
        absolute = abs(offset)

        scientific = f"{absolute:.10e}"
        mantissa, exponent = scientific.split("e")

        mantissa = mantissa.rstrip("0").rstrip(".")
        exponent = int(exponent)

        return f"{sign}{mantissa}e{exponent}"

    x_offset = calculate_axis_offset(x_range)
    y_offset = calculate_axis_offset(y_range)

    x_ticks = nice_tick_values(x_range)
    y_ticks = nice_tick_values(y_range)

    x_tick_labels = [
        format_local_tick(value, x_offset, x_ticks)
        for value in x_ticks
    ]

    y_tick_labels = [
        format_local_tick(value, y_offset, y_ticks)
        for value in y_ticks
    ]

    x_offset_text = format_offset(x_offset)
    y_offset_text = format_offset(y_offset)

    # ========================================================
    # Display-option helpers
    # ========================================================
    def option_for(option, name, fallback):
        if isinstance(option, dict):
            return option.get(name, fallback)

        return fallback if option is None else option

    def display_limits(name, valid):
        if robust:
            default_low, default_high = np.percentile(
                valid,
                [2, 98],
            )
        else:
            default_low = np.min(valid)
            default_high = np.max(valid)

        low = float(option_for(vmin, name, default_low))
        high = float(option_for(vmax, name, default_high))

        if not np.isfinite(low) or not np.isfinite(high):
            raise ValueError(
                f"Non-finite display limits for {name}: "
                f"{low}, {high}"
            )

        if low >= high:
            if np.isclose(low, high):
                high = low + 1e-6
            else:
                raise ValueError(
                    f"Invalid display limits for {name}: "
                    f"{low}, {high}"
                )

        return low, high

    # ========================================================
    # Subplot layout
    # ========================================================
    ncols = min(int(cols), len(names))
    nrows = (len(names) + ncols - 1) // ncols

    titles = [
        f"<b>{name}</b> — {INDEX_INFO[name]['full_name']}"
        for name in names
    ]

    titles.extend([""] * (nrows * ncols - len(titles)))

    fig = make_subplots(
        rows=nrows,
        cols=ncols,
        subplot_titles=titles,
        horizontal_spacing=0.12,
        vertical_spacing=0.17,
    )

    # ========================================================
    # Add index maps
    # ========================================================
    for position, name in enumerate(names):
        row = position // ncols + 1
        col = position % ncols + 1

        array = np.asarray(
            ds[name].transpose("y", "x").values,
            dtype=np.float32,
        )

        if array.shape != (rows_px, cols_px):
            raise ValueError(
                f"{name} has shape {array.shape}; "
                f"expected {(rows_px, cols_px)}."
            )

        valid = array[np.isfinite(array)]

        if valid.size == 0:
            continue

        low, high = display_limits(name, valid)

        scale = option_for(
            colorscale,
            name,
            INDEX_CMAPS.get(name, "Viridis"),
        )

        axis_number = position + 1
        axis_suffix = "" if axis_number == 1 else str(axis_number)

        x_axis_reference = (
            "x domain"
            if axis_number == 1
            else f"x{axis_number} domain"
        )

        y_axis_reference = (
            "y domain"
            if axis_number == 1
            else f"y{axis_number} domain"
        )

        fig.add_trace(
            go.Heatmap(
                x=x,
                y=y,
                z=array,
                colorscale=scale,
                zmin=low,
                zmax=high,
                zsmooth=False,
                showscale=show_colorbars,
                colorbar=(
                    dict(
                        title=name,
                        thickness=12,
                    )
                    if show_colorbars
                    else None
                ),
                hovertemplate=(
                    f"<b>{name}</b><br>"
                    f"Easting: %{{x:,.3f}} {unit_label}<br>"
                    f"Northing: %{{y:,.3f}} {unit_label}<br>"
                    "Value: %{z:.4f}"
                    "<extra></extra>"
                ),
                name="",
            ),
            row=row,
            col=col,
        )

        # Compact Easting tick labels
        fig.update_xaxes(
            title_text=(
                f"Easting ({unit_label})"
                if row == nrows
                else None
            ),
            range=x_range,
            tickmode="array",
            tickvals=x_ticks,
            ticktext=x_tick_labels,
            constrain="domain",
            row=row,
            col=col,
        )

        # Compact Northing tick labels
        fig.update_yaxes(
            title_text=(
                f"Northing ({unit_label})"
                if col == 1
                else None
            ),
            range=y_range,
            tickmode="array",
            tickvals=y_ticks,
            ticktext=y_tick_labels,
            scaleanchor=f"x{axis_suffix}",
            scaleratio=1,
            constrain="domain",
            row=row,
            col=col,
        )

        # Northing offset at the upper-left
        if y_offset_text:
            fig.add_annotation(
                x=0,
                y=1.01,
                xref=x_axis_reference,
                yref=y_axis_reference,
                text=y_offset_text,
                showarrow=False,
                xanchor="left",
                yanchor="bottom",
                font=dict(
                    size=10,
                    color="#333333",
                ),
            )

        # Easting offset at the lower-right
        if x_offset_text:
            fig.add_annotation(
                x=1,
                y=-0.06,
                xref=x_axis_reference,
                yref=y_axis_reference,
                text=x_offset_text,
                showarrow=False,
                xanchor="right",
                yanchor="top",
                font=dict(
                    size=10,
                    color="#333333",
                ),
            )

    # ========================================================
    # Figure layout
    # ========================================================
    filename = ds.attrs.get(
        "filename",
        "MicaSense RedEdge-P Dual",
    )

    fig.update_layout(
        title=dict(
            text=(
                f"Workshop Spectral Indices — {filename}<br>"
                f"<sup>{crs_name} ({crs_id})</sup>"
            ),
            x=0.5,
            xanchor="center",
        ),
        template="plotly_white",
        width=max(750, width_per_panel * ncols),
        height=max(
            500,
            height_per_panel * nrows + 120,
        ),
        showlegend=False,
        margin=dict(
            l=90,
            r=50,
            t=125,
            b=90,
        ),
    )

    # ========================================================
    # Optional HTML export
    # ========================================================
    if save_path is not None:
        path = Path(save_path)

        if path.suffix.lower() != ".html":
            raise ValueError(
                "plot_indices save_path must end in '.html'."
            )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        fig.write_html(
            path,
            include_plotlyjs=True,
        )

        print(f"Saved: {path}")

    if show:
        fig.show(
            config={
                "scrollZoom": True,
                "displaylogo": False,
            }
        )

    return fig


# ---------------------------------------------------------------------------
# Shared projected-CRS Plotly helpers
# ---------------------------------------------------------------------------

def projected_plot_context(ds, tick_count=6, tick_step=5):
    """Return validated projected coordinates and compact axis formatting.

    The returned coordinates are the original pixel centres. Raster ranges are
    calculated from the outer pixel edges, so maps retain their exact source
    extent. Compact tick labels follow Matplotlib-style additive notation, for
    example ticks ``5, 10, 15`` with an axis annotation ``+4.618e5``. The
    default tick interval is 5 projected units (5 m for a metre-based CRS).
    Set ``tick_step=None`` to select a spacing automatically from
    ``tick_count``.
    """

    x = np.asarray(ds["x"].values, dtype="float64")
    y = np.asarray(ds["y"].values, dtype="float64")

    if x.ndim != 1 or y.ndim != 1 or x.size < 2 or y.size < 2:
        raise ValueError(
            "The Dataset must contain at least two one-dimensional x/y "
            "coordinates."
        )
    if x.size != ds.sizes.get("x") or y.size != ds.sizes.get("y"):
        raise ValueError("The x/y coordinates do not match the raster dimensions.")

    crs = CRS.from_user_input(_dataset_crs(ds))
    if not crs.is_projected:
        raise ValueError(
            "A projected CRS is required, but the Dataset contains "
            f"{crs.to_string()}."
        )

    dx = float(np.median(np.diff(x)))
    dy = float(np.median(np.diff(y)))
    if np.isclose(dx, 0) or np.isclose(dy, 0):
        raise ValueError("The x/y coordinate spacing cannot be zero.")

    x_range = sorted([float(x[0] - dx / 2), float(x[-1] + dx / 2)])
    y_range = sorted([float(y[0] - dy / 2), float(y[-1] + dy / 2)])

    unit_name = crs.axis_info[0].unit_name if crs.axis_info else "projected units"
    unit_label = (
        "m"
        if unit_name and unit_name.lower() in {"metre", "meter", "metres", "meters"}
        else (unit_name or "projected units")
    )

    def axis_offset(axis_range):
        lower, upper = axis_range
        span = upper - lower
        centre = (lower + upper) / 2
        if not np.isfinite(span) or span <= 0 or abs(centre) < 100 * span:
            return 0.0
        base = 10 ** (np.floor(np.log10(span)) + 1)
        return float(np.floor(lower / base) * base)

    def tick_values(axis_range):
        lower, upper = axis_range
        span = upper - lower
        if tick_step is not None:
            step = float(tick_step)
            if not np.isfinite(step) or step <= 0:
                raise ValueError("tick_step must be a positive finite number or None.")
        else:
            raw = span / max(int(tick_count) - 1, 1)
            magnitude = 10 ** np.floor(np.log10(raw))
            fraction = raw / magnitude
            if fraction <= 1:
                nice_fraction = 1
            elif fraction <= 2:
                nice_fraction = 2
            elif fraction <= 2.5:
                nice_fraction = 2.5
            elif fraction <= 5:
                nice_fraction = 5
            else:
                nice_fraction = 10
            step = nice_fraction * magnitude
        first = np.ceil(lower / step) * step
        last = np.floor(upper / step) * step
        return np.arange(first, last + step * 0.5, step)

    def tick_text(values, offset):
        step = abs(float(values[1] - values[0])) if values.size > 1 else 1.0
        decimals = 0 if step >= 1 else max(0, int(np.ceil(-np.log10(step))))
        labels = []
        for value in values:
            local = float(value - offset)
            if np.isclose(local, 0):
                local = 0.0
            labels.append(f"{local:.{decimals}f}")
        return labels

    def offset_text(offset):
        if np.isclose(offset, 0):
            return ""
        sign = "+" if offset > 0 else "−"
        mantissa, exponent = f"{abs(offset):.10e}".split("e")
        return f"{sign}{mantissa.rstrip('0').rstrip('.')}e{int(exponent)}"

    x_offset = axis_offset(x_range)
    y_offset = axis_offset(y_range)
    x_ticks = tick_values(x_range)
    y_ticks = tick_values(y_range)

    return {
        "x": x,
        "y": y,
        "dx": dx,
        "dy": dy,
        "x_range": x_range,
        "y_range": y_range,
        "x_ticks": x_ticks,
        "y_ticks": y_ticks,
        "x_ticktext": tick_text(x_ticks, x_offset),
        "y_ticktext": tick_text(y_ticks, y_offset),
        "x_offset_text": offset_text(x_offset),
        "y_offset_text": offset_text(y_offset),
        "unit_label": unit_label,
        "crs": crs,
        "crs_name": crs.name,
        "crs_id": crs.to_string(),
        "shape": (y.size, x.size),
    }


def apply_projected_axes(
    fig,
    context,
    row=1,
    col=1,
    axis_number=1,
    x_title=True,
    y_title=True,
    show_ticklabels=True,
    add_offsets=True,
):
    """Apply exact projected extent, equal scale and compact coordinate ticks."""

    suffix = "" if axis_number == 1 else str(axis_number)
    xref = "x domain" if axis_number == 1 else f"x{axis_number} domain"
    yref = "y domain" if axis_number == 1 else f"y{axis_number} domain"
    unit = context["unit_label"]

    # Plain go.Figure objects do not have a subplot grid, so row/col may only
    # be supplied when the figure was created with make_subplots().
    subplot = getattr(fig, "_grid_ref", None) is not None
    axis_target = {"row": row, "col": col} if subplot else {}

    fig.update_xaxes(
        title_text=f"Easting ({unit})" if x_title else None,
        range=context["x_range"],
        tickmode="array",
        tickvals=context["x_ticks"],
        ticktext=context["x_ticktext"],
        showticklabels=show_ticklabels,
        constrain="domain",
        **axis_target,
    )
    fig.update_yaxes(
        title_text=f"Northing ({unit})" if y_title else None,
        range=context["y_range"],
        tickmode="array",
        tickvals=context["y_ticks"],
        ticktext=context["y_ticktext"],
        showticklabels=show_ticklabels,
        scaleanchor=f"x{suffix}",
        scaleratio=1,
        constrain="domain",
        **axis_target,
    )

    if add_offsets and show_ticklabels:
        if context["y_offset_text"]:
            fig.add_annotation(
                x=0,
                y=1.01,
                xref=xref,
                yref=yref,
                text=context["y_offset_text"],
                showarrow=False,
                xanchor="left",
                yanchor="bottom",
                font={"size": 10, "color": "#333333"},
            )
        if context["x_offset_text"]:
            fig.add_annotation(
                x=1,
                y=-0.06,
                xref=xref,
                yref=yref,
                text=context["x_offset_text"],
                showarrow=False,
                xanchor="right",
                yanchor="top",
                font={"size": 10, "color": "#333333"},
            )
    return fig


def make_projected_heatmap(
    ds,
    variable=None,
    array=None,
    context=None,
    colorscale="Viridis",
    zmin=None,
    zmax=None,
    robust=False,
    percentiles=(2, 98),
    showscale=False,
    colorbar=None,
    hover_name=None,
    value_label="Value",
):
    """Create a Plotly map using the Dataset's native projected CRS."""
    """ make_projected_heatmap() creates the coloured raster/index map on the left side of your figure.""" 

    context = projected_plot_context(ds) if context is None else context
    if array is None:
        if variable is None or variable not in ds:
            raise KeyError("Provide an existing Dataset variable or an array.")
        array = ds[variable].transpose("y", "x").values

    array = np.asarray(array, dtype="float32")
    if array.shape != context["shape"]:
        raise ValueError(
            f"Raster shape {array.shape} does not match {context['shape']}."
        )
    valid = array[np.isfinite(array)]
    if valid.size == 0:
        raise ValueError(f"{variable or 'Raster'} contains no valid pixels.")

    if robust:
        default_low, default_high = np.percentile(valid, percentiles)
    else:
        default_low, default_high = np.min(valid), np.max(valid)
    low = float(default_low if zmin is None else zmin)
    high = float(default_high if zmax is None else zmax)
    if not np.isfinite(low) or not np.isfinite(high):
        raise ValueError("Heatmap display limits must be finite.")
    if low >= high:
        high = low + 1e-6

    name = hover_name or variable or "Raster"
    unit = context["unit_label"]
    return go.Heatmap(
        x=context["x"],
        y=context["y"],
        z=array,
        colorscale=colorscale,
        zmin=low,
        zmax=high,
        zsmooth=False,
        showscale=showscale,
        colorbar=colorbar,
        hovertemplate=(
            # f"<b>{name}</b><br>"
            # f"Easting: %{{x:,.3f}} {unit}<br>"
            # f"Northing: %{{y:,.3f}} {unit}<br>"
            f"{value_label}: %{{z:.4f}}<extra></extra>"
        ),
        name="",
    )


def make_projected_image(
    ds,
    image,
    context=None,
    customdata=None,
    hovertemplate=None,
):
    """Create a georeferenced Plotly RGB/RGBA Image trace."""

    context = projected_plot_context(ds) if context is None else context
    image = np.asarray(image)
    if image.shape[:2] != context["shape"]:
        raise ValueError(
            f"Image shape {image.shape[:2]} does not match {context['shape']}."
        )
    unit = context["unit_label"]
    if hovertemplate is None:
        hovertemplate = (
            f"Easting: %{{x:,.3f}} {unit}<br>"
            f"Northing: %{{y:,.3f}} {unit}<extra></extra>"
        )
    return go.Image(
        z=image,
        x0=float(context["x"][0]),
        y0=float(context["y"][0]),
        dx=context["dx"],
        dy=context["dy"],
        customdata=customdata,
        hovertemplate=hovertemplate,
        name="",
    )


def _plot_metadata(metadata, variable):
    if metadata is None:
        return {}
    if variable in metadata and isinstance(metadata[variable], dict):
        return metadata[variable]
    return metadata if isinstance(metadata, dict) else {}


def _plot_option(option, variable, fallback):
    if isinstance(option, dict):
        return option.get(variable, fallback)
    return fallback if option is None else option


def plot_raster_distribution(
    ds,
    variable,
    metadata=None,
    colorscale=None,
    histogram_color=None,
    value_label=None,
    robust=True,
    percentiles=(2, 98),
    bins=100,
    statistics=("min", "median", "max"),
    show_colorbar=False,
    width=1150,
    height=550,
    title=None,
    show=True,
):
    """Plot one projected raster beside its full-pixel histogram."""

    if variable not in ds:
        raise KeyError(f"{variable!r} is not present in the Dataset.")

    context = projected_plot_context(ds)
    array = np.asarray(ds[variable].transpose("y", "x").values, dtype="float32")
    valid = array[np.isfinite(array)]
    if valid.size == 0:
        raise ValueError(f"{variable} contains no valid pixels.")

    meta = _plot_metadata(metadata, variable)
    label = meta.get("label", meta.get("full_name", variable))
    map_scale = _plot_option(
        colorscale,
        variable,
        meta.get("colorscale", meta.get("cmap", "Viridis")),
    )
    bar_color = _plot_option(
        histogram_color,
        variable,
        meta.get("histogram_color", meta.get("colour", "#397d54")),
    )
    value_name = _plot_option(
        value_label,
        variable,
        meta.get("value_label", variable),
    )

    p_low, p_high = np.percentile(valid, percentiles)
    minimum = float(np.min(valid))
    median = float(np.median(valid))
    maximum = float(np.max(valid))
    mean = float(np.mean(valid))
    stat_values = {
        "min": minimum,
        "median": median,
        "max": maximum,
        "mean": mean,
        "p2": float(p_low),
        "p98": float(p_high),
    }
    stat_labels = {
        "min": "Min",
        "median": "Median",
        "max": "Max",
        "mean": "Mean",
        "p2": f"P{percentiles[0]:g}",
        "p98": f"P{percentiles[1]:g}",
    }
    stat_styles = {
        "min": ("#2166ac", "dot", "left"),
        "median": ("#1a9850", "dash", "center"),
        "max": ("#d73027", "dot", "right"),
        "mean": ("#c0392b", "dash", "center"),
        "p2": ("#2980b9", "dot", "center"),
        "p98": ("#2980b9", "dot", "center"),
    }

    counts, edges = np.histogram(valid, bins=int(bins))
    centres = (edges[:-1] + edges[1:]) / 2
    widths = np.diff(edges)

    fig = make_subplots(
        rows=1,
        cols=2,
        column_widths=[0.5, 0.5],
        horizontal_spacing=0.10,
        subplot_titles=[label, f"{value_name} distribution (n={valid.size:,})"],
    )
    fig.add_trace(
        make_projected_heatmap(
            ds,
            variable=variable,
            context=context,
            colorscale=map_scale,
            robust=robust,
            percentiles=percentiles,
            showscale=show_colorbar,
            colorbar={"title": value_name, "thickness": 12},
            hover_name=label,
            value_label=value_name,
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=centres,
            y=counts,
            width=widths,
            marker_color=bar_color,
            showlegend=False,
            hovertemplate=(
                f"{value_name}: %{{x:.4f}}<br>"
                "Pixel count: %{y:,}<extra></extra>"
            ),
        ),
        row=1,
        col=2,
    )

    for position, statistic in enumerate(statistics):
        key = statistic.lower()
        if key not in stat_values:
            raise ValueError(f"Unsupported statistic: {statistic}")
        value = stat_values[key]
        colour, dash, anchor = stat_styles[key]
        fig.add_vline(
            x=value,
            line_color=colour,
            line_width=2,
            line_dash=dash,
            row=1,
            col=2,
        )
        fig.add_annotation(
            x=value,
            y=0.96 - 0.08 * position,
            xref="x2",
            yref="y2 domain",
            text=f"{stat_labels[key]}: {value:.4f}",
            showarrow=False,
            xanchor=anchor,
            yanchor="top",
            font={"color": colour, "size": 10},
            bgcolor="rgba(255,255,255,0.90)",
            bordercolor=colour,
            borderwidth=1,
            borderpad=2,
        )

    apply_projected_axes(fig, context, row=1, col=1, axis_number=1)
    fig.update_xaxes(title_text=value_name, row=1, col=2)
    fig.update_yaxes(title_text="Pixel count", rangemode="tozero", row=1, col=2)
    fig.update_layout(
        title={
            "text": title or f"{label} Map and Distribution",
            "x": 0.5,
            "xanchor": "center",
        },
        template="plotly_white",
        width=width,
        height=height,
        showlegend=False,
        hoverlabel={"bgcolor": "white", "font": {"color": "black"}},
        margin={"l": 90, "r": 40, "t": 110, "b": 85},
        bargap=0.02,
    )
    if show:
        fig.show(config={"scrollZoom": True, "displaylogo": False})
    return fig



def interactive_raster_explorer(
    ds,
    variables,
    metadata=None,
    default=None,
    dropdown_description="Variable:",
    colorscale=None,
    histogram_color=None,
    value_label=None,
    robust=True,
    percentiles=(2, 98),
    bins=100,
    statistics=("min", "median", "max"),
    show_colorbar=False,
    show_metadata=False,
    width=1150,
    height=550,
):
    """Display a dropdown-controlled projected raster map and histogram."""

    try:
        import ipywidgets as widgets
        from IPython.display import Markdown, clear_output, display
    except ImportError as exc:
        raise ImportError(
            "interactive_raster_explorer requires ipywidgets and IPython."
        ) from exc

    variables = list(variables)
    if not variables:
        raise ValueError("At least one raster variable is required.")
    missing = [name for name in variables if name not in ds]
    if missing:
        raise KeyError("Variables missing from Dataset: " + ", ".join(missing))

    options = []
    for name in variables:
        meta = _plot_metadata(metadata, name)
        options.append((meta.get("dropdown_label", meta.get("label", name)), name))

    selected = default or variables[0]
    if selected not in variables:
        raise ValueError(f"Default variable {selected!r} is not in variables.")

    selector = widgets.Dropdown(
        options=options,
        value=selected,
        description=dropdown_description,
    )
    output = widgets.Output()

    def render(change=None):
        with output:
            clear_output(wait=True)
            name = selector.value
            meta = _plot_metadata(metadata, name)
            if show_metadata and meta:
                rows = []
                for label, key in (
                    ("Formula", "formula"),
                    ("Bands used", "bands_used"),
                    ("Purpose", "purpose"),
                    ("Interpretation", "interpretation"),
                ):
                    if meta.get(key):
                        rows.append(f"| {label} | {meta[key]} |")
                if rows:
                    display(Markdown(
                        f"**{name} — {meta.get('full_name', name)}**\n\n"
                        "| | |\n|---|---|\n" + "\n".join(rows)
                    ))

            fig = plot_raster_distribution(
                ds,
                variable=name,
                metadata=metadata,
                colorscale=colorscale,
                histogram_color=histogram_color,
                value_label=value_label,
                robust=robust,
                percentiles=percentiles,
                bins=bins,
                statistics=statistics,
                show_colorbar=show_colorbar,
                width=width,
                height=height,
                title=" ",  # Remove overall title
                show=False,
            )

            # Use abbreviated subplot titles
            fig.layout.annotations[0].text = name
            fig.layout.annotations[1].text = f"{name} distribution"

            # Position the colour bar beside the index map
            if show_colorbar:
                fig.data[0].update(
                    colorbar=dict(
                        title=name,
                        x=0.455,
                        xanchor="left",
                        y=0.5,
                        len=0.82,
                        thickness=12,
                        xpad=4,
                    )
                )

            fig.update_layout(margin=dict(l=90, r=40, t=70, b=85))

            fig.show(config={"scrollZoom": True, "displaylogo": False})

    selector.observe(render, names="value")
    display(selector, output)
    render()
    return selector, output


def plot_raster_grid(
    ds,
    variables,
    metadata=None,
    colorscale=None,
    cols=2,
    robust=True,
    vmin=None,
    vmax=None,
    show_colorbars=False,
    width_per_panel=430,
    height_per_panel=390,
    title=None,
    save_path=None,
    show=True,
):
    """Plot any collection of 2-D Dataset variables in projected coordinates."""

    variables = list(variables)
    if not variables:
        raise ValueError("At least one raster variable is required.")
    missing = [name for name in variables if name not in ds]
    if missing:
        raise KeyError("Variables missing from Dataset: " + ", ".join(missing))
    if cols < 1:
        raise ValueError("cols must be at least 1.")

    context = projected_plot_context(ds)
    ncols = min(int(cols), len(variables))
    nrows = (len(variables) + ncols - 1) // ncols
    titles = []
    for name in variables:
        meta = _plot_metadata(metadata, name)
        titles.append(meta.get("label", meta.get("full_name", name)))
    titles.extend([""] * (nrows * ncols - len(titles)))
    fig = make_subplots(
        rows=nrows,
        cols=ncols,
        subplot_titles=titles,
        horizontal_spacing=0.10,
        vertical_spacing=0.16,
    )

    for position, name in enumerate(variables):
        row = position // ncols + 1
        col = position % ncols + 1
        meta = _plot_metadata(metadata, name)
        scale = _plot_option(
            colorscale,
            name,
            meta.get("colorscale", meta.get("cmap", "Viridis")),
        )
        low = _plot_option(vmin, name, None)
        high = _plot_option(vmax, name, None)
        fig.add_trace(
            make_projected_heatmap(
                ds,
                variable=name,
                context=context,
                colorscale=scale,
                zmin=low,
                zmax=high,
                robust=robust,
                showscale=show_colorbars,
                colorbar={"title": name, "thickness": 12},
                hover_name=name,
                value_label=name,
            ),
            row=row,
            col=col,
        )
        apply_projected_axes(
            fig,
            context,
            row=row,
            col=col,
            axis_number=position + 1,
            x_title=row == nrows,
            y_title=col == 1,
        )

    filename = ds.attrs.get("filename", "MicaSense RedEdge-P Dual")
    fig.update_layout(
        title={
            "text": title or (
                f"Raster Maps — {filename}<br>"
                f"<sup>{context['crs_name']} ({context['crs_id']})</sup>"
            ),
            "x": 0.5,
            "xanchor": "center",
        },
        template="plotly_white",
        width=max(750, width_per_panel * ncols),
        height=max(500, height_per_panel * nrows + 120),
        showlegend=False,
        margin={"l": 90, "r": 50, "t": 125, "b": 90},
    )

    if save_path is not None:
        path = Path(save_path)
        if path.suffix.lower() != ".html":
            raise ValueError("save_path must end in '.html'.")
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(path, include_plotlyjs=True)
        print(f"Saved: {path}")
    if show:
        fig.show(config={"scrollZoom": True, "displaylogo": False})
    return fig


# Override the earlier notebook-compatible definition with the shared generic
# projected implementation. Existing notebook calls keep the same API.
def plot_indices(
    ds,
    indices=None,
    colorscale=None,
    cols=2,
    robust=True,
    vmin=None,
    vmax=None,
    show_colorbars=False,
    width_per_panel=430,
    height_per_panel=390,
    save_path=None,
    show=True,
):
    names = _resolve_indices(ds, indices)
    # metadata = {
        # name: {
            # **INDEX_INFO[name],
            # "label": f"{name} — {INDEX_INFO[name]['full_name']}",
            # "colorscale": INDEX_CMAPS.get(name, "Viridis"),
        # }
        # for name in names
    # }
    metadata = {
        name: {
            **INDEX_INFO[name],

            # Show only the abbreviated index name
            "label": name,

            "colorscale": INDEX_CMAPS.get(name, "Viridis"),
        }
        for name in names
    }
    
    return plot_raster_grid(
        ds,
        variables=names,
        metadata=metadata,
        colorscale=colorscale,
        cols=cols,
        robust=robust,
        vmin=vmin,
        vmax=vmax,
        show_colorbars=show_colorbars,
        width_per_panel=width_per_panel,
        height_per_panel=height_per_panel,
        title=" ",  # Removes the overall workshop title
        # title=(
            # f"Workshop Spectral Indices — "
            # f"{ds.attrs.get('filename', 'MicaSense RedEdge-P Dual')}"
        # ),
        save_path=save_path,
        show=show,
    )