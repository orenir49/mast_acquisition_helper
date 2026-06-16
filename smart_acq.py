import threading
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
import pyvo
import requests as req
import astropy.units as u
from astropy.coordinates import EarthLocation, SkyCoord
from astropy.table import Table
from astropy.time import Time

service     = pyvo.dal.TAPService("https://gea.esac.esa.int/tap-server/tap")
simbad_tap  = pyvo.dal.TAPService("https://simbad.cds.unistra.fr/simbad/sim-tap")

_DEFAULT_URL = "http://127.0.0.1:8000/mast/api/v1/unit/start_acquisition_and_guiding"

LOCATION = EarthLocation(lat=30.0483 * u.deg, lon=35.0233 * u.deg)


def compute_lha(ra_hours):
    """Local Hour Angle in hours, normalised to [-12, 12]."""
    lst = Time.now().sidereal_time('apparent', longitude=LOCATION.lon)
    lha = (lst.hour - ra_hours + 12) % 24 - 12
    return lha

# Parallel list to source_listbox entries: each element is (ra_hours, dec_deg, gmag_or_None)
_sources = []


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

def coords_by_name(name):
    simbad_result = simbad_tap.search(f"""
        SELECT b.ra, b.dec
        FROM basic AS b
        JOIN ident AS i ON b.oid = i.oidref
        WHERE i.id = '{name}'
    """).to_table()
    if len(simbad_result) == 0:
        raise ValueError(f"Object '{name}' not found in SIMBAD.")
    ra_s = float(simbad_result['ra'][0])
    dec_s = float(simbad_result['dec'][0])

    radius = 10 / 3600
    gaia_result = service.search(f"""
        SELECT TOP 1 ra, dec, parallax, parallax_over_error, pmra, pmdec,
            DISTANCE(POINT('ICRS', ra, dec), POINT('ICRS', {ra_s}, {dec_s})) AS dist
        FROM gaiadr3.gaia_source
        WHERE CONTAINS(
            POINT('ICRS', ra, dec),
            CIRCLE('ICRS', {ra_s}, {dec_s}, {radius})
        ) = 1
        ORDER BY dist ASC
    """).to_table()

    if len(gaia_result) == 0:
        gui_print("  [coords: SIMBAD fallback — no Gaia DR3 source within 10 arcsec]")
        return ra_s, dec_s

    r = gaia_result[0]
    ra_g, dec_g = float(r['ra']), float(r['dec'])
    has_pm   = np.isfinite(r['pmra']) and np.isfinite(r['pmdec'])
    good_plx = (r['parallax'] > 0) and (r['parallax_over_error'] > 3)

    if has_pm:
        dist = (1000 / float(r['parallax']) * u.pc) if good_plx else (1 * u.kpc)
        coord = SkyCoord(
            ra=ra_g * u.deg, dec=dec_g * u.deg, frame='icrs',
            obstime='J2016.0',
            pm_ra_cosdec=float(r['pmra']) * u.mas / u.yr,
            pm_dec=float(r['pmdec']) * u.mas / u.yr,
            distance=dist,
        )
        new = coord.apply_space_motion(Time.now())
        tag = "Gaia DR3 + PM corrected" if good_plx else "Gaia DR3 + PM (assumed 1 kpc)"
        gui_print(f"  [coords: {tag}]")
        return float(new.ra.deg), float(new.dec.deg)

    gui_print("  [coords: Gaia DR3 raw epoch 2016.0]")
    return ra_g, dec_g


def query_gaia_box(ra_center, dec_center, Gmag_target, dG=0.5, ra_range_deg=0.5, dec_range_deg=0.5):
    ra_min = (ra_center - ra_range_deg) % 360.0
    ra_max = (ra_center + ra_range_deg) % 360.0
    dec_min = dec_center - dec_range_deg
    dec_max = dec_center + dec_range_deg

    if ra_min < ra_max:
        ra_clause = f"(ra BETWEEN {ra_min} AND {ra_max})"
    else:
        ra_clause = f"((ra BETWEEN {ra_min} AND 360.0) OR (ra BETWEEN 0.0 AND {ra_max}))"

    adql = f"""
        SELECT TOP 100 source_id, ra, dec, parallax, parallax_over_error,
            pmra, pmdec, phot_g_mean_mag, ref_epoch
        FROM gaiadr3.gaia_source
        WHERE {ra_clause}
        AND (dec BETWEEN {dec_min} AND {dec_max})
        AND (phot_g_mean_mag BETWEEN {Gmag_target - dG} AND {Gmag_target + dG})
    """

    result = service.search(adql)
    r = result.to_table()

    cut = (
        (r['parallax'] > 0)
        & (r['parallax_over_error'] > 5)
        & np.isfinite(r['pmra'])
        & np.isfinite(r['pmdec'])
    )
    r = r[cut]

    if len(r) == 0:
        if dec_range_deg < 4:
            gui_print("No sources found, expanding search box.")
            return query_gaia_box(ra_center, dec_center, Gmag_target,
                                  dG=1.0, ra_range_deg=ra_range_deg * 2, dec_range_deg=4)
        gui_print("No Gaia sources found in the requested window.")
        return r

    obs_time = Time.now()
    coords = SkyCoord(
        ra=r['ra'], dec=r['dec'], frame='icrs', equinox='J2000', obstime='J2016.0',
        pm_ra_cosdec=r['pmra'], pm_dec=r['pmdec'],
        distance=1000 / r['parallax'].data * u.pc,
    )
    new_coords = coords.apply_space_motion(obs_time)
    ra_hour   = new_coords.ra.to(u.hourangle)
    dec_corr  = new_coords.dec

    return Table(
        [ra_hour, dec_corr, r['phot_g_mean_mag'], r['pmra'], r['pmdec']],
        names=('ra_hour', 'dec_deg', 'phot_g_mean_mag', 'pmra', 'pmdec'),
        units=(u.hourangle, u.deg, u.mag, u.mas / u.yr, u.mas / u.yr),
    )


# ---------------------------------------------------------------------------
# GUI helpers  (all safe to call from any thread)
# ---------------------------------------------------------------------------

def gui_print(msg, tag=None):
    def _insert():
        output_box.config(state="normal")
        output_box.insert("end", msg + "\n", (tag,) if tag else ())
        output_box.see("end")
        output_box.config(state="disabled")
    root.after(0, _insert)


def gui_clear():
    def _clear():
        output_box.config(state="normal")
        output_box.delete("1.0", "end")
        output_box.config(state="disabled")
        _sources.clear()
        source_listbox.delete(0, "end")
        source_frame.grid_remove()
    root.after(0, _clear)


def gui_add_source(ra_h, dec_d, gmag, label):
    def _add():
        _sources.append((ra_h, dec_d, gmag))
        source_listbox.insert("end", label)
        source_frame.grid()
    root.after(0, _add)


# ---------------------------------------------------------------------------
# Parameter window
# ---------------------------------------------------------------------------

def open_params_window(ra_h, dec_d, gmag):
    win = tk.Toplevel(root)
    win.title("Acquisition Parameters")
    win.resizable(False, False)

    f = ttk.Frame(win, padding=16)
    f.grid()

    fields = [
        ("URL",                            _DEFAULT_URL),
        ("ra_j2000_hours",                 f"{ra_h:.5f}"),
        ("dec_j2000_degs",                 f"{dec_d:.5f}"),
        ("seconds",                        "3"),
        ("gain_absolute",                  "170"),
        ("approach_mode",                  "2"),
        ("make_corrections",               "true"),
        ("skip_sky",                       "false"),
        ("use_set_limit_frame",            "false"),
        ("handover_automatically_to_guider", "true"),
    ]

    vars_ = {}
    for i, (name, default) in enumerate(fields):
        ttk.Label(f, text=name + ":").grid(row=i, column=0, sticky="w", pady=3)
        v = tk.StringVar(value=default)
        ttk.Entry(f, textvariable=v, width=52).grid(row=i, column=1, padx=(10, 0), pady=3)
        vars_[name] = v

    resp_box = tk.Text(f, width=52, height=6, state="disabled",
                       wrap="word", font=("Courier", 9))
    resp_box.grid(row=len(fields) + 1, column=0, columnspan=2, pady=(10, 0))
    resp_sb = ttk.Scrollbar(f, orient="vertical", command=resp_box.yview)
    resp_sb.grid(row=len(fields) + 1, column=2, sticky="ns", pady=(10, 0))
    resp_box.config(yscrollcommand=resp_sb.set)

    def set_response(msg):
        resp_box.config(state="normal")
        resp_box.delete("1.0", "end")
        resp_box.insert("end", msg)
        resp_box.config(state="disabled")

    def send():
        url = vars_["URL"].get()
        params = {k: vars_[k].get() for k in vars_ if k != "URL"}
        send_btn.config(state="disabled")
        set_response("Sending…")

        def _do():
            try:
                r = req.get(url, params=params,
                            headers={"accept": "application/json"},
                            proxies={"http": None, "https": None},
                            timeout=30)
                msg = f"{r.status_code}\n{r.text}"
            except Exception as e:
                msg = f"Error: {e}"
            win.after(0, lambda m=msg: set_response(m))
            win.after(0, lambda: send_btn.config(state="normal"))

        threading.Thread(target=_do, daemon=True).start()

    send_btn = ttk.Button(f, text="Send", command=send)
    send_btn.grid(row=len(fields), column=0, columnspan=2, pady=(14, 0))


# ---------------------------------------------------------------------------
# Main GUI callbacks
# ---------------------------------------------------------------------------

def on_mode_change(*_):
    if mode_var.get() == "mag":
        gmag_label.grid()
        gmag_entry.grid()
    else:
        gmag_label.grid_remove()
        gmag_entry.grid_remove()


def on_source_select(event):
    sel = source_listbox.curselection()
    if not sel:
        return
    ra_h, dec_d, gmag = _sources[sel[0]]
    open_params_window(ra_h, dec_d, gmag)


def on_start():
    name = target_name_var.get().strip()
    if not name:
        messagebox.showwarning("Input required", "Please enter a target name.")
        return

    mode = mode_var.get()
    gmag = None
    if mode == "mag":
        try:
            gmag = float(gmag_var.get())
        except ValueError:
            messagebox.showwarning("Invalid input", "G magnitude must be a number.")
            return

    start_btn.config(state="disabled")
    status_var.set("Querying…")

    def run():
        gui_clear()
        try:
            ra_deg, dec_deg = coords_by_name(name)
            ra_hours = ra_deg / 15.0

            if mode == "name":
                lha = compute_lha(ra_hours)
                lha_tag = "lha_ok" if -1.5 <= lha <= 1.5 else "lha_bad"
                gui_print(f"Target: {name}")
                gui_print(f"  RA  = {ra_hours:.5f} h")
                gui_print(f"  Dec = {dec_deg:.5f} deg")
                gui_print(f"  LHA = {lha:.5f} h", tag=lha_tag)
                gui_add_source(ra_hours, dec_deg, None,
                               f"{name}  RA={ra_hours:.5f} h  Dec={dec_deg:.5f}°")
            else:
                gui_print(f"Target: {name}  (G ~ {gmag})")
                gui_print(f"  Center: RA = {ra_hours:.5f} h, Dec = {dec_deg:.5f} deg")
                tbl = query_gaia_box(ra_deg, dec_deg, Gmag_target=gmag)
                if len(tbl) == 0:
                    gui_print("  No matching Gaia sources found.")
                else:
                    gui_print(f"  Found {len(tbl)} Gaia source(s):")
                    for row in tbl:
                        rh  = float(row['ra_hour'])
                        dd  = float(row['dec_deg'])
                        gm  = float(row['phot_g_mean_mag'])
                        lha = compute_lha(rh)
                        lha_tag = "lha_ok" if -1.5 <= lha <= 1.5 else "lha_bad"
                        gui_print(f"    RA={rh:.5f} h  Dec={dd:.5f}°  G={gm:.2f}  LHA={lha:.5f} h",
                                  tag=lha_tag)
                        gui_add_source(rh, dd, gm,
                                       f"RA={rh:.5f} h   Dec={dd:.5f}°   G={gm:.2f}")
        except Exception as exc:
            root.after(0, lambda e=exc: messagebox.showerror("Error", str(e)))
        finally:
            root.after(0, lambda: start_btn.config(state="normal"))
            root.after(0, lambda: status_var.set(""))

    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------------------
# GUI layout
# ---------------------------------------------------------------------------

root = tk.Tk()
root.title("Smart Acquisition")
root.resizable(False, False)

frame = ttk.Frame(root, padding=20)
frame.grid()

# Target name
ttk.Label(frame, text="Target name:").grid(row=0, column=0, sticky="w", pady=(0, 4))
target_name_var = tk.StringVar()
ttk.Entry(frame, textvariable=target_name_var, width=28).grid(
    row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 4))

# Radio buttons
mode_var = tk.StringVar(value="name")
mode_var.trace_add("write", on_mode_change)

ttk.Radiobutton(frame, text="Name only", variable=mode_var, value="name").grid(
    row=1, column=0, columnspan=2, sticky="w", pady=(8, 2))
ttk.Radiobutton(frame, text="Name + G magnitude", variable=mode_var, value="mag").grid(
    row=2, column=0, columnspan=2, sticky="w", pady=(0, 8))

# G magnitude (hidden by default)
gmag_label = ttk.Label(frame, text="G magnitude:")
gmag_label.grid(row=3, column=0, sticky="w", pady=(0, 4))
gmag_label.grid_remove()

gmag_var = tk.StringVar()
gmag_entry = ttk.Entry(frame, textvariable=gmag_var, width=28)
gmag_entry.grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=(0, 4))
gmag_entry.grid_remove()

# Status + buttons
status_var = tk.StringVar()
ttk.Label(frame, textvariable=status_var, foreground="gray").grid(
    row=4, column=0, columnspan=2, pady=(8, 0))

start_btn = ttk.Button(frame, text="Start", command=on_start)
start_btn.grid(row=5, column=0, pady=(4, 0))
ttk.Button(frame, text="Exit", command=root.destroy).grid(row=5, column=1, pady=(4, 0))

# Info output box
output_box = tk.Text(frame, width=52, height=8, state="disabled",
                     wrap="none", font=("Courier", 9))
output_box.tag_config("lha_ok",  foreground="green")
output_box.tag_config("lha_bad", foreground="red")
output_box.grid(row=6, column=0, columnspan=2, pady=(14, 0))
sb1 = ttk.Scrollbar(frame, orient="vertical", command=output_box.yview)
sb1.grid(row=6, column=2, sticky="ns", pady=(14, 0))
output_box.config(yscrollcommand=sb1.set)

# Selectable source list (hidden until results arrive)
source_frame = ttk.LabelFrame(frame, text="Select a target — double-click to configure", padding=6)
source_frame.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(10, 0))
source_frame.grid_remove()

source_listbox = tk.Listbox(source_frame, width=52, height=6, font=("Courier", 9),
                            selectmode="single", activestyle="underline")
source_listbox.pack(side="left", fill="both", expand=True)
source_listbox.bind("<Double-Button-1>", on_source_select)

sb2 = ttk.Scrollbar(source_frame, orient="vertical", command=source_listbox.yview)
sb2.pack(side="right", fill="y")
source_listbox.config(yscrollcommand=sb2.set)

root.mainloop()
