# AEO workshop notebooks

Jupyter notebooks for analysing MicaSense RedEdge-P Dual multispectral drone imagery.

| Notebook | Topic |
| --- | --- |
| `CHAPTER1_DATA_and_VISUALISATION.ipynb` | Loading the data and visualising bands |
| `CHAPTER2_COMPUTING_VISUALISING_DERIVATIVES_FINAL.ipynb` | Computing and visualising spectral indices |
| `CHAPTER3_QA_MASKING.ipynb` | QA and masking |
| `CHAPTER4_OPTIONAL_PROXY_DERIVATIVES.ipynb` | Optional: proxy derivatives |

`workshop_utils.py` holds the shared helpers and must stay next to the notebooks.

## Setup

Use pixi or conda/mamba. Both install the same conda-forge packages.

### Pixi

```bash
pixi install
pixi run lab
```

### Conda / mamba

```bash
mamba env create -f environment.yml
mamba activate aeo-workshop
jupyter lab
```

(`conda` works too: swap `mamba` for `conda`.)

### pip

```bash
pip install -r requirements.txt
```

The dependency lists live in `pixi.toml`, `environment.yml` and `requirements.txt`. Update all three when you add a package.

### Hosted JupyterHub (Nectar)

To run the workshop on a shared JupyterHub, follow [`hub/WALKTHROUGH.md`](hub/WALKTHROUGH.md).

## Running the notebooks

1. **Start Jupyter from the repo root.** The notebooks import `workshop_utils.py` from the folder Jupyter was started from. Starting it anywhere else gives a `ModuleNotFoundError` in the first code cell.

   ```bash
   pixi run lab
   ```

   Or, with conda/mamba: `mamba activate aeo-workshop`, then `jupyter lab`.

   Jupyter Lab opens in your browser. If it doesn't, copy the `http://localhost:8888/lab?token=…` link from the terminal.
2. **Run the chapters in order, 1 → 4.** In each notebook use **Kernel → Restart Kernel and Run All Cells**, or step through with <kbd>Shift</kbd>+<kbd>Enter</kbd>. Each chapter loads the imagery on its own, so you can open any chapter directly. Chapter 4 is optional and the longest.
3. **Stay online.** The imagery streams from the workshop STAC catalogue (see [Data](#data)), so loading needs an internet connection and takes 10–20 seconds.
4. **Use the widgets.** The dropdowns, sliders and maps only respond while the kernel is running. Change a widget and its plot redraws.
5. **Shut down when finished.** Use **File → Shut Down**, or press <kbd>Ctrl</kbd>+<kbd>C</kbd> twice in the terminal. Each open notebook holds its imagery in memory, so shut down kernels you're done with (**Kernel → Shut Down Kernel**).

| Chapter | What it does | Writes to `outputs/` |
| --- | --- | --- |
| 1 | Loads the 10 bands, band summaries, true/false-colour composites, interactive basemap | — |
| 2 | Calculates NDVI, CIRE, CRI2 and ARI2: maps, histograms, scatter plot, correlations | `workshop_indices.tif`, `indices/*.tif` |
| 3 | Masks NDVI by threshold and range, with an interactive map and histogram | `masked_ndvi.tif` |
| 4 | Optional: normalises the indices, pigment-proxy composite, thresholding, basemap overlay | `pigment_rgb_relative.tif` |

To use a different survey or study area, pass `item_id=` or `bounds=` to `load_data()`, or change `ITEM_ID` and `AOI_BOUNDS` in `workshop_utils.py`.

## Data

The imagery comes from the AEO 2026 workshop STAC catalogue on Nectar object storage:

<https://object-store.rc.nectar.org.au/v1/AUTH_4df2f67c2eed48a2aaeeed008a4bf0de/aeo2026-workshop/collection.json>

Each item is one drone survey (`PLOTID-YYYYMMDD`). The notebooks use the `ms` asset (the 10-band MicaSense orthomosaic) of `NTABRT0007-20240828`. That file is a 2.8 GB cloud-optimised GeoTIFF, so `workshop_utils.load_data()` reads only a small study area (`AOI_BOUNDS`, 1342 × 1265 pixels). Nothing is downloaded to disk.
