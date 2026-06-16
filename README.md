# MAST Acquisition

GUI tool for stellar target selection and acquisition control at the Weizmann MAST instrument.

## Overview

`smart_acq.py` resolves a star name via SIMBAD, retrieves precise Gaia DR3 astrometry, and sends acquisition parameters to the local MAST control server. The Local Hour Angle (LHA) is computed in real time for the observatory site and colour-coded to indicate observability.

## Requirements

- Python 3.11+
- XIMEA SDK (for camera control — handled separately, not in pip requirements)
- All other dependencies are in `requirements.txt`

### Install

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Usage

```bash
python smart_acq.py
```

### Workflow

1. **Enter a target name** (e.g. `Sabik`, `HD 189733`) in the text box.
2. **Choose mode:**
   - *Name only* — resolves RA/Dec via SIMBAD → Gaia DR3 crossmatch.
   - *Name + G magnitude* — additionally queries the Gaia DR3 box around the resolved position and lists all sources within ±0.5 mag.
3. Click **Start**. Results appear in the output box:
   - Coordinates (RA in decimal hours, Dec in degrees)
   - LHA computed for the observatory site — **green** if −1.5 h ≤ LHA ≤ 1.5 h, **red** otherwise
4. **Double-click** a source in the target list to open the Acquisition Parameters window.
5. Edit any parameter if needed and click **Send** to issue the GET request to the MAST control server.

### Coordinate resolution priority

| Condition | Source used |
|---|---|
| Gaia DR3 match with good parallax + proper motion | Gaia DR3, PM-corrected to now |
| Gaia DR3 match, PM available, parallax unreliable | Gaia DR3, PM-corrected (assumed 1 kpc) |
| Gaia DR3 match, no PM data | Gaia DR3 raw (epoch 2016.0) |
| No Gaia DR3 source within 10 arcsec | SIMBAD position (fallback) |

### Observatory site

| Parameter | Value |
|---|---|
| Latitude | 30.0483° N |
| Longitude | 35.0233° E |

### MAST control server

Default endpoint: `http://127.0.0.1:8000/mast/api/v1/unit/start_acquisition_and_guiding`

All request parameters are editable in the Acquisition Parameters window before sending.

## Files

| File | Description |
|---|---|
| `smart_acq.py` | Main GUI script |
| `oren_notebook.ipynb` | Original development notebook (includes camera capture and PSF analysis) |
| `requirements.txt` | Pinned Python dependencies |
