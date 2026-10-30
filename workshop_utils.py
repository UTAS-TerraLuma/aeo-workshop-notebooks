"""
workshop_utils.py
=================
Shared helpers for the MicaSense drone data analysis workshop.

This file must sit in the same folder as the workshop notebooks. The imagery
is read straight from the workshop STAC catalogue (see STAC_COLLECTION_URL),
so there is nothing to download.
"""

# What this does: provides the shared raster, index, and display helpers used
# by all the Jupyter notebooks.
import os
from pathlib import Path
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pyproj import CRS
import pystac
import rasterio
from rasterio.windows import from_bounds
import xarray as xr

# ---------------------------------------------------------------------------
# Data source: the AEO 2026 workshop STAC catalogue on Nectar object storage
# ---------------------------------------------------------------------------
STAC_COLLECTION_URL = (
    "https://object-store.rc.nectar.org.au/v1/AUTH_4df2f67c2eed48a2aaeeed008a4bf0de"
    "/aeo2026-workshop/collection.json"
)
# One survey (PLOTID-YYYYMMDD) and its multispectral orthomosaic asset.
ITEM_ID = "NTABRT0007-20240828"
ASSET_KEY = "ms"

# The full orthomosaic is ~2.8 GB, so we only read a small study area.
# Bounds are (left, bottom, right, top) in the raster's CRS (GDA2020 / MGA 53).
# This is the same area as the old local "subset3" file: 1342 x 1265 pixels.
AOI_BOUNDS = (359842.06, 7534681.29, 359909.39, 7534744.75)

# Make GDAL's HTTP reads of cloud-optimised GeoTIFFs quick.
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")

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
# CIRE, CRI2, ARI2 are the three pigment-sensitive indices for this workshop.
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

# Ordered list of the workshop index names: ["NDVI", "CIRE", "CRI2", "ARI2"]
WORKSHOP_INDICES = list(INDEX_INFO.keys())

# ---------------------------------------------------------------------------
# Data-loading helpers
# ---------------------------------------------------------------------------

def get_asset_href(item_id=ITEM_ID, asset_key=ASSET_KEY,
                   collection_url=STAC_COLLECTION_URL):
    """Look up a survey in the STAC collection and return the URL of one asset."""
    collection = pystac.Collection.from_file(collection_url)
    item = collection.get_item(item_id)
    if item is None:
        ids = [i.id for i in collection.get_items()]
        raise KeyError(f"No item {item_id!r} in the collection. Available: {ids}")
    return item.assets[asset_key].get_absolute_href()


def load_data(item_id=ITEM_ID, bounds=AOI_BOUNDS):
    """
    Read the MicaSense multispectral orthomosaic from the STAC catalogue as an
    xarray.Dataset with one variable per band.

    Only the pixels inside `bounds` (left, bottom, right, top, in the raster's
    CRS) are downloaded. Pass bounds=None to read the whole orthomosaic, which
    is several GB. NoData and non-positive reflectance become NaN.
    """
    href = get_asset_href(item_id)

    with rasterio.open(href) as src:
        if src.count != len(BAND_INFO):
            raise ValueError(
                f"Expected {len(BAND_INFO)} bands for a MicaSense RedEdge-P "
                f"Dual image, but {href} contains {src.count}."
            )

        if bounds is None:
            window = rasterio.windows.Window(0, 0, src.width, src.height)
        else:
            window = from_bounds(*bounds, transform=src.transform)
            window = window.round_offsets().round_lengths()
        transform = src.window_transform(window)

        data = src.read(window=window, out_dtype="float32")
        nodata = src.nodata
        invalid = ~np.isfinite(data)
        if nodata is not None:
            invalid |= data == nodata
        # Workshop surface-reflectance images use zero for background/NoData.
        invalid |= data <= 0
        data[invalid] = np.nan

        height, width = data.shape[1:]
        x = transform.c + (np.arange(width) + 0.5) * transform.a
        y = transform.f + (np.arange(height) + 0.5) * transform.e
        variables = {
            band["var"]: (("y", "x"), data[i])
            for i, band in enumerate(BAND_INFO)
        }
        ds = xr.Dataset(variables, coords={"x": x, "y": y})
        ds.attrs.update({
            "filename": f"{item_id} ({ASSET_KEY})",
            "source_path": href,
            "instrument": "MicaSense RedEdge-P Dual",
            "image_width_px": width,
            "image_height_px": height,
            "pixel_size_m": float(abs(transform.a)),
            "crs": str(src.crs),
            "transform": tuple(transform),
        })
        for band in BAND_INFO:
            ds[band["var"]].attrs.update({
                "long_name": band["name"],
                "centre_wavelength_nm": band["nm"],
                "fwhm_nm": band["fwhm"],
            })
    return ds


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
    Export the workshop indices as GeoTIFF files.

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