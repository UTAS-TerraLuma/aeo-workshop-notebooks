import marimo

__generated_with = "0.25.1"
app = marimo.App(
    width="medium",
    app_title="Chapter 2 — Spectral indices (marimo pilot)",
)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Chapter 2 — Calculating and Exploring Spectral Indices

    *A marimo version of this chapter, trialled for the workshop.*

    This notebook calculates four vegetation and pigment-sensitive indices —
    **NDVI, CIRE, CRI2 and ARI2** — and explores them with index maps,
    histograms, an interactive index-to-index scatter plot and a correlation
    matrix.

    Everything runs by itself: change a control and every result that depends
    on it updates. Index values, statistics, histograms and correlations use
    every valid pixel; the maps and the scatter plot draw a subset so the
    browser stays responsive.
    """)
    return


@app.cell
def _():
    import marimo as mo
    import numpy as np
    import pandas as pd
    import plotly.express as px
    import plotly.graph_objects as go
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    from pathlib import Path
    from scipy.stats import gaussian_kde

    from workshop_utils import (
        INDEX_INFO,
        WORKSHOP_INDICES,
        compute_indices,
        load_data,
        plot_indices,
        plot_raster_distribution,
        save_indices_to_tiff,
    )

    return (
        INDEX_INFO,
        LinearSegmentedColormap,
        Path,
        WORKSHOP_INDICES,
        compute_indices,
        gaussian_kde,
        go,
        load_data,
        mo,
        np,
        plot_indices,
        plot_raster_distribution,
        plt,
        px,
        save_indices_to_tiff,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1. Index catalogue

    | Index | Formula | Main interpretation |
    |---|---|---|
    | NDVI | (NIR-842 − Red-668) / (NIR-842 + Red-668) | General vegetation density and greenness |
    | CIRE | (NIR-842 / Red-Edge-705) − 1 | Total chlorophyll via red-edge reflectance |
    | CRI2 | (1 / Green-531) − (1 / Red-Edge-705) | Carotenoids, often elevated under stress or senescence |
    | ARI2 | NIR-842 × [(1 / Green-560) − (1 / Red-Edge-705)] | Anthocyanin index weighted by NIR for canopy variation |

    ## 2. Load data and calculate indices

    `load_data` reads the study area (from a copy saved on the workshop server,
    or from the workshop STAC catalogue). `compute_indices` then adds the four
    indices as new float32 variables. Pixels whose input reflectance is
    implausible (at or below 0.01, or above 1) are left as NaN in the indices,
    so every statistic and plot below ignores them.
    """)
    return


@app.cell
def _(compute_indices, load_data, mo):
    with mo.status.spinner("Loading the study area…"):
        ds = compute_indices(load_data())
    mo.md(
        f"**Image:** {ds.sizes['y']:,} rows × {ds.sizes['x']:,} columns at "
        f"{ds.attrs['pixel_size_m'] * 100:.1f} cm per pixel, CRS {ds.attrs['crs']}"
    )
    return (ds,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3. Index formulas and scene statistics

    Each index becomes one column of a pandas table (one row per pixel).
    `describe()` then summarises every valid pixel, skipping NaN.
    """)
    return


@app.cell
def _(INDEX_INFO, WORKSHOP_INDICES, ds):
    index_table = ds[WORKSHOP_INDICES].to_dataframe()

    index_stats = index_table.describe(percentiles=[0.02, 0.5, 0.98]).T.astype({"count": int})
    index_stats.insert(0, "Formula", [INDEX_INFO[name]["formula"] for name in WORKSHOP_INDICES])
    index_stats.round(4)
    return (index_table,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4. Index maps

    `plot_indices` returns a Plotly figure. `robust=True` (the default) uses
    each index's P2–P98 range for the colour scale, so a few extreme pixels do
    not wash out the map. Scroll to zoom, drag to pan.
    """)
    return


@app.cell
def _(ds, plot_indices):
    plot_indices(ds, show=False)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 5. Interactive index explorer

    Choose an index and a colour stretch. **Full range** colours from the
    minimum to the maximum; **Robust** uses the P2–P98 range, which reveals
    spatial detail that a full-range scale hides when a few pixels are
    extreme. The histogram and statistic lines use every valid pixel.
    """)
    return


@app.cell
def _(WORKSHOP_INDICES, mo):
    explorer_index = mo.ui.dropdown(WORKSHOP_INDICES, value="NDVI", label="Index")
    explorer_stretch = mo.ui.radio(
        ["Full range (min–max)", "Robust (P2–P98)"],
        value="Robust (P2–P98)",
        label="Colour stretch",
        inline=True,
    )
    mo.hstack([explorer_index, explorer_stretch], justify="start", gap=2)
    return explorer_index, explorer_stretch


@app.cell
def _(INDEX_INFO, ds, explorer_index, explorer_stretch, mo, plot_raster_distribution):
    _name = explorer_index.value
    _info = INDEX_INFO[_name]
    _robust = explorer_stretch.value.startswith("Robust")
    _fig = plot_raster_distribution(
        ds,
        variable=_name,
        metadata=INDEX_INFO,
        robust=_robust,
        statistics=("mean", "p2", "p98") if _robust else ("min", "median", "max"),
        show_colorbar=True,
        title=f"{_name} — {_info['full_name']}",
        show=False,
    )
    mo.vstack([
        mo.md(
            f"**Formula:** {_info['formula']}  \n"
            f"**Purpose:** {_info['purpose']}  \n"
            f"**Interpretation:** {_info['interpretation']}"
        ),
        _fig,
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 6. Interactive index-to-index scatter plot

    Drawing every pixel (millions of points) would freeze the browser, so the
    plot shows a random sample. The correlation coefficient in the title uses
    **all** valid pixel pairs.
    """)
    return


@app.cell
def _(WORKSHOP_INDICES, mo):
    scatter_x = mo.ui.dropdown(WORKSHOP_INDICES, value="NDVI", label="X")
    scatter_y = mo.ui.dropdown(WORKSHOP_INDICES, value="CIRE", label="Y")
    scatter_n = mo.ui.slider(
        5_000, 100_000, step=5_000, value=20_000, label="Samples",
        debounce=True, show_value=True,
    )
    mo.hstack([scatter_x, scatter_y, scatter_n], justify="start", gap=2)
    return scatter_n, scatter_x, scatter_y


@app.cell
def _(go, index_table, np, scatter_n, scatter_x, scatter_y):
    _x, _y = scatter_x.value, scatter_y.value
    _pairs = index_table[[_x, _y]].dropna().to_numpy()
    _r = np.corrcoef(_pairs, rowvar=False)[0, 1]
    _n = min(scatter_n.value, len(_pairs))
    _rng = np.random.default_rng(42)
    _sample = _pairs[_rng.choice(len(_pairs), size=_n, replace=False)].astype("float32")

    _fig = go.Figure(go.Scattergl(
        x=_sample[:, 0], y=_sample[:, 1], mode="markers",
        marker=dict(size=3, opacity=0.35, color="#2c7fb8"),
        hovertemplate=f"{_x}: %{{x:.4f}}<br>{_y}: %{{y:.4f}}<extra></extra>",
    ))
    _fig.update_layout(
        title=(f"{_x} vs {_y} — {_n:,} sampled of {len(_pairs):,} valid pixels "
               f"(Pearson r = {_r:.3f}, all pixels)"),
        xaxis_title=_x, yaxis_title=_y,
        template="plotly_white", height=520,
        margin=dict(l=70, r=30, t=70, b=60),
    )
    _fig
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 7. Correlation between indices

    Pearson correlations use every pixel that is valid in all four indices.
    """)
    return


@app.cell
def _(index_table, px):
    complete_pixels = index_table.dropna()
    corr_matrix = complete_pixels.corr()

    _fig = px.imshow(
        corr_matrix, text_auto=".2f", color_continuous_scale="RdYlGn", zmin=-1, zmax=1,
    )
    _fig.update_layout(
        title=f"Pearson correlation matrix — n={len(complete_pixels):,} complete pixels",
        height=480, width=560, template="plotly_white",
    )
    _fig
    return complete_pixels, corr_matrix


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 7.1 Correlation matrix with distributions

    The lower triangle shows the correlations; the diagonal shows each index's
    smoothed distribution. The KDE uses a random sample of 50,000 pixels for
    speed — this affects only the drawn curve, not the correlations.
    """)
    return


@app.cell
def _(
    LinearSegmentedColormap,
    WORKSHOP_INDICES,
    complete_pixels,
    corr_matrix,
    gaussian_kde,
    np,
    plt,
):
    _values = corr_matrix.to_numpy()
    _n = len(WORKSHOP_INDICES)
    _upper = np.triu(np.ones_like(_values, dtype=bool))  # hide the diagonal and upper triangle
    _cmap = LinearSegmentedColormap.from_list("correlation", ["#5b8fa8", "#f2f2f2", "#c95735"])

    _fig, _ax = plt.subplots(figsize=(7, 7))
    _ax.imshow(np.ma.array(_values, mask=_upper), cmap=_cmap, vmin=-1, vmax=1)
    _ax.set_xticks(range(_n), WORKSHOP_INDICES, rotation=90)
    _ax.set_yticks(range(_n), WORKSHOP_INDICES)
    for _i in range(_n):
        for _j in range(_i):
            _ax.text(_j, _i, f"{_values[_i, _j]:.2f}", ha="center", va="center", fontsize=10)

    _kde_sample = complete_pixels.sample(n=min(50_000, len(complete_pixels)), random_state=42)
    for _i, _name in enumerate(WORKSHOP_INDICES):
        _data = _kde_sample[_name].to_numpy()
        _low, _high = np.percentile(_data, [1, 99])
        _grid = np.linspace(_low, _high, 200)
        _density = gaussian_kde(_data[(_data >= _low) & (_data <= _high)])(_grid)
        _kde_ax = _ax.inset_axes([_i - 0.45, _i - 0.45, 0.9, 0.9], transform=_ax.transData)
        _kde_ax.fill_between(_grid, _density, color="#5b8fa8", alpha=0.35)
        _kde_ax.plot(_grid, _density, color="#5b8fa8", linewidth=1.2)
        _kde_ax.axis("off")

    _ax.set_xticks(np.arange(-0.5, _n, 1), minor=True)
    _ax.set_yticks(np.arange(-0.5, _n, 1), minor=True)
    _ax.grid(which="minor", color="white", linewidth=1)
    _ax.tick_params(which="minor", bottom=False, left=False)
    _ax.set_title("Correlation matrix")
    _fig.tight_layout()
    _fig
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 8. Save the indices as GeoTIFFs (optional)

    Writes all four indices at full resolution, with the source CRS and
    geotransform, to `outputs/workshop_indices.tif`, ready to open in QGIS.
    """)
    return


@app.cell
def _(mo):
    export_button = mo.ui.run_button(label="Write GeoTIFF")
    export_button
    return (export_button,)


@app.cell
def _(Path, ds, export_button, mo, save_indices_to_tiff):
    mo.stop(not export_button.value, mo.md("*Nothing written yet.*"))
    _paths = save_indices_to_tiff(ds, out_path=Path("outputs") / "workshop_indices.tif")
    mo.md("Saved: " + ", ".join(f"`{_p}`" for _p in _paths))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Activities

    1. Compare NDVI and CIRE in the explorer. Can you find dense-canopy areas
       where CIRE retains variation but NDVI appears saturated?
    2. Locate the highest-ARI2 cluster, then compare the same location in NDVI.
    3. Identify the strongest positive and the weakest/most negative pairs in
       the correlation matrix. Which pigment proxy is least related to NDVI?

    ARI2 and CRI2 can be negative where the reciprocal-difference formulas are
    applied to soil or shadow pixels.
    """)
    return


if __name__ == "__main__":
    app.run()
