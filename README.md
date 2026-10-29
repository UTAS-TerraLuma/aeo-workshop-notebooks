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
