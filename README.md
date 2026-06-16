# MAST Acquisition

GUI tool for stellar target selection and acquisition control at the Weizmann MAST instrument.

## What it does

`smart_acq.py` is a self-contained Python/Tkinter application used at the telescope to prepare and issue an acquisition command. Given a star name, it:

1. Resolves the name to sky coordinates via SIMBAD
2. Cross-matches with the Gaia DR3 catalog for precise astrometry
3. Applies proper motion corrections to the current epoch
4. Computes the Local Hour Angle (LHA) in real time and colour-codes it to indicate whether the target is currently within the acceptable observing window (|LHA| ≤ 1.5 h)
5. Sends the acquisition parameters to the local MAST control server via an HTTP GET request

It was written to replace a manual coordinate lookup workflow and to ensure that proper motion and epoch corrections are applied consistently before every acquisition.

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/mast_acquisition.git
cd mast_acquisition
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
```

**Windows:**
```bash
.venv\Scripts\activate
```

**macOS / Linux:**
```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** Python 3.11 or later is required. The XIMEA camera SDK (used in the development notebook) is **not** a requirement for running `smart_acq.py` and is not available via pip — install it separately if needed for camera work.

### 4. Run the application

```bash
python smart_acq.py
```

---

## Usage

### Modes

| Mode | Description |
|---|---|
| **Name only** | Resolves the target name and shows a single result with RA, Dec, G magnitude, and LHA. |
| **Name + G magnitude** | Additionally queries Gaia DR3 within ±0.5 mag of the entered G magnitude and lists all sources in the field. |

### Workflow

1. Enter a target name (e.g. `Sabik`, `HD 189733`, `HIP 98036`) in the text box.
2. Select a mode. In *Name + G magnitude* mode, also enter the approximate G magnitude.
3. Click **Start**. The output box shows the resolved coordinates and LHA, colour-coded green (observable) or red (outside window).
4. **Double-click** any row in the target list to open the Acquisition Parameters window.
5. Review or edit any parameter, then click **Send**.

### Coordinate resolution priority

| Condition | Coordinates used |
|---|---|
| Gaia DR3 match, reliable parallax + PM | Gaia DR3, proper-motion corrected to current epoch |
| Gaia DR3 match, PM available, parallax unreliable | Gaia DR3, PM-corrected (distance assumed 1 kpc) |
| Gaia DR3 match, no PM data | Gaia DR3 raw (epoch 2016.0) |
| No Gaia DR3 source within 10 arcsec | SIMBAD position (fallback) |

### Observatory site (hardcoded)

| Parameter | Value |
|---|---|
| Latitude | 30.0483° N |
| Longitude | 35.0233° E |

---

## MAST control server API

The application issues a **GET** request to the MAST control server. The default endpoint is:

```
http://127.0.0.1:8000/mast/api/v1/unit/start_acquisition_and_guiding
```

All parameters are sent as URL query parameters. A fully-formed request looks like:

```
http://127.0.0.1:8000/mast/api/v1/unit/start_acquisition_and_guiding
  ?ra_j2000_hours=17.60394
  &dec_j2000_degs=-15.72483
  &seconds=3
  &gain_absolute=170
  &approach_mode=2
  &make_corrections=true
  &skip_sky=false
  &use_set_limit_frame=false
  &handover_automatically_to_guider=true
```

| Parameter | Default | Description |
|---|---|---|
| `ra_j2000_hours` | resolved | Right ascension in decimal hours, J2000 |
| `dec_j2000_degs` | resolved | Declination in decimal degrees, J2000 |
| `seconds` | `3` | Acquisition exposure time (seconds) |
| `gain_absolute` | `170` | Camera gain |
| `approach_mode` | `2` | Acquisition approach mode |
| `make_corrections` | `true` | Apply pointing corrections |
| `skip_sky` | `false` | Skip sky background measurement |
| `use_set_limit_frame` | `false` | Use configured limit frame |
| `handover_automatically_to_guider` | `true` | Hand over to guider after acquisition |

> **Compatibility note:** If your MAST control server uses a different base URL, port, path structure, or parameter names, update the URL field in the Acquisition Parameters window before sending. The URL field is fully editable at runtime — changes there do not affect the hardcoded default for future launches. To change the default permanently, edit `_DEFAULT_URL` at line 16 of `smart_acq.py`.

---

## Files

| File | Description |
|---|---|
| `smart_acq.py` | Main GUI application |
| `oren_notebook.ipynb` | Development notebook — includes XIMEA camera capture, PSF fitting, and encircled-energy analysis |
| `requirements.txt` | Pinned Python dependencies |
