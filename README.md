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

### GitHub Codespaces

The backup if the hub is unavailable. You need a GitHub account; nothing is installed on your computer.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/UTAS-TerraLuma/aeo-workshop-notebooks?quickstart=1)

1. Click the button, then **Create codespace** (or **Resume** if you already have one).
2. Wait for the setup to finish. It installs the environment from `pixi.lock`, which takes a few minutes unless a prebuild is ready.
3. JupyterLab opens in a new browser tab. If your browser blocks the pop-up, open the **Ports** tab in VS Code and click the globe icon next to **JupyterLab**. You can also open the notebooks in VS Code itself; pick the `.pixi/envs/default` kernel.
4. When finished, stop the codespace: **Codespaces** menu (bottom-left) → **Stop Current Codespace**. Idle codespaces stop on their own after 30 minutes.

Codespaces run on your own GitHub account's free monthly allowance (120 core-hours, which is 60 hours on the default 2-core machine), which is plenty for the workshop. Delete the codespace at <https://github.com/codespaces> afterwards to free its storage.

The setup lives in [`.devcontainer/`](.devcontainer/). It reads `pixi.lock`, so there's no extra dependency list to keep in sync, but `pixi.lock` must be up to date (`pixi install` updates it) or the codespace setup stops with an error.

#### Prebuilds (maintainers)

A prebuild installs the environment ahead of time, so codespaces start in seconds. To set one up (needs repo admin, and the org needs a payment method and a Codespaces spending limit):

1. Repo **Settings** → **Codespaces** → **Set up prebuild**.
2. Branch `main`, configuration `.devcontainer/devcontainer.json`.
3. Trigger: **Every push**. (*On configuration change* only watches `devcontainer.json` and the `Dockerfile`, so it would miss changes to `pixi.lock`.)
4. Under **Reduce prebuild available to only specific regions**, pick the region nearest the workshop to cut storage costs. Set **Template history** to 1.
5. Wait for the prebuild to finish (its status shows on the same page), then check that **Prebuild ready** appears next to the machine type when you create a codespace.

Prebuilds run on GitHub Actions, and their storage is billed to the org per region and per retained version. Delete the prebuild configuration after the workshop to stop the storage charges.

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
