# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MAST Acquisition is a Tkinter GUI tool for stellar target selection at the Weizmann Institute's MAST (Multi-purpose Acquisition & Spectrographic Tool) telescope. It resolves target names via SIMBAD, fetches astrometry from Gaia DR3, applies proper motion corrections, and sends acquisition parameters to the local MAST control server via HTTP.

## Setup & Running

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

python smart_acq.py
```

There is no build system, test suite, or linter configured.

## Architecture

The entire application is a single file: `smart_acq.py` (394 lines). The structure is:

- **Backend functions** (top of file): pure functions for catalog queries and coordinate math — `coords_by_name()`, `query_gaia_box()`, `compute_lha()`
- **GUI callbacks** (bottom of file): event handlers wired to Tkinter widgets — `on_start()`, `on_source_select()`, `on_mode_change()`
- **State**: the module-level `_sources` list holds `(ra_deg, dec_deg, gmag)` tuples parallel to rows in the Treeview widget

Long-running catalog queries run in background threads. All GUI updates from those threads must use `root.after()` — direct widget access from worker threads is unsafe in Tkinter.

## Coordinate Resolution Priority

When resolving a target name, the code applies this fallback chain:
1. Gaia DR3 match with reliable parallax + PM → PM-corrected to current epoch
2. Gaia DR3 match with PM but unreliable parallax → PM-corrected assuming 1 kpc
3. Gaia DR3 match without PM → raw epoch 2016.0 coordinates
4. No Gaia source within 10 arcsec → SIMBAD fallback coordinates

## External Services

| Service | URL | Purpose |
|---|---|---|
| Gaia DR3 TAP | `https://gea.esac.esa.int/tap-server/tap` | Astrometry + photometry |
| SIMBAD TAP | `https://simbad.cds.unistra.fr/simbad/sim-tap` | Name resolution |
| MAST server | `http://127.0.0.1:8000/mast/api/v1/unit/start_acquisition_and_guiding` | Send acquisition params |

The MAST server URL is editable in the GUI before sending. The observatory site is hardcoded: latitude 30.0483° N, longitude 35.0233° E.

## Key Dependencies

- `astropy` — coordinate frames, time, units
- `pyvo` — TAP service queries (Gaia, SIMBAD)
- `astroquery` — SIMBAD name resolution
- `requests` — HTTP POST to MAST server

XIMEA SDK (camera control) appears only in `oren_notebook.ipynb` and is not required to run the GUI.
