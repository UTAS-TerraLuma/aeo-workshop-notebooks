# AEO workshop notebooks

Jupyter notebooks for analysing MicaSense RedEdge-P Dual multispectral drone imagery.

| Notebook | Topic |
| --- | --- |
| `CHAPTER1_DATA_and_VISUALISATION_DASK.ipynb` | Loading the data and visualising bands |
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

## Running the notebooks

1. **Get the data.** Copy the GeoTIFFs listed under [Data](#data) into `data/`.
2. **Start Jupyter from the repo root.** The notebooks look for `workshop_utils.py` and `data/` in the folder Jupyter was started from. Starting it anywhere else gives a `FileNotFoundError` in the first code cell.

   ```bash
   pixi run lab
   ```

   Or, with conda/mamba: `mamba activate aeo-workshop`, then `jupyter lab`.

   Jupyter Lab opens in your browser. If it doesn't, copy the `http://localhost:8888/lab?token=…` link from the terminal.
3. **Run the chapters in order, 1 → 4.** In each notebook use **Kernel → Restart Kernel and Run All Cells**, or step through with <kbd>Shift</kbd>+<kbd>Enter</kbd>. Each chapter loads the raster on its own, so you can open any chapter directly. Chapter 4 is optional and the longest.
4. **Skip the install cell.** Chapter 1's first code cell has commented-out `%pip install` lines. Your environment already has everything, so leave them commented.
5. **Watch Dask (optional).** The setup cell starts a local Dask cluster and prints a `Dask dashboard:` link. Open it in another tab to see the work in progress.
6. **Use the widgets.** The dropdowns, sliders and maps only respond while the kernel is running. Change a widget and its plot redraws.
7. **Shut down when finished.** Use **File → Shut Down**, or press <kbd>Ctrl</kbd>+<kbd>C</kbd> twice in the terminal. Each notebook runs its own Dask cluster, so shut down kernels you're done with (**Kernel → Shut Down Kernel**) to free memory.

| Chapter | What it does | Writes to `outputs/` |
| --- | --- | --- |
| 1 | Loads the 10 bands, band summaries, true/false-colour composites, interactive basemap | — |
| 2 | Calculates NDVI, CIRE, CRI2 and ARI2: maps, histograms, scatter plot, correlations | `workshop_indices.tif`, `indices/*.tif` |
| 3 | Masks NDVI by threshold and range, with an interactive map and histogram | `masked_ndvi.tif` |
| 4 | Optional: normalises the indices, pigment-proxy composite, thresholding, basemap overlay | `pigment_rgb_relative.tif` |

To use a different raster, edit `RASTER_FILENAME` in the setup cell near the top of the notebook.

## Data

The imagery is not stored in git, and `data/` is ignored. For now, put the GeoTIFFs in `data/` yourself. Eventually the data will be downloaded from URLs.

| File | Used by |
| --- | --- |
| `data/NTABRT0007-20240828-ms-cog-subset.tif` | Chapter 1 |
| `data/NTABRT0007-20240828-ms-cog-subset3.tif` | Chapters 2–4, and `workshop_utils.DATA_PATH` |

Each notebook sets its file with `RASTER_FILENAME` near the top.

Files the notebooks write go to `outputs/`, which is also ignored.

## Committing notebooks

The notebooks contain large embedded outputs. One of them is over 240 MB, which is too big for GitHub. The repo uses [nbstripout](https://github.com/kynan/nbstripout) as a git filter: outputs stay in your working copy, and only code and markdown are committed. Run this once after cloning:

```bash
pixi run setup-git
```

Or, from an activated conda env: `nbstripout --install --attributes .gitattributes`.
