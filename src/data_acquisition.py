"""
data_acquisition.py
-------------------
Downloads and caches all raw data sources for the school-noise analysis.

Usage (CLI):
    python -m src.data_acquisition --all
    python -m src.data_acquisition --schools
    python -m src.data_acquisition --ejscreen
    python -m src.data_acquisition --ccd
    python -m src.data_acquisition --check
"""

import argparse
import logging
import zipfile
from pathlib import Path

import requests
from tqdm import tqdm

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_RAW, URLS

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _download(url: str, dest: Path, chunk_size: int = 1 << 20) -> Path:
    """Stream-download *url* to *dest* with a progress bar."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        log.info("Already downloaded: %s", dest.name)
        return dest
    log.info("Downloading %s -> %s", url, dest)
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    total = int(r.headers.get("content-length", 0))
    with open(dest, "wb") as f, tqdm(total=total, unit="B", unit_scale=True) as bar:
        for chunk in r.iter_content(chunk_size):
            f.write(chunk)
            bar.update(len(chunk))
    return dest


def _extract_zip(zip_path: Path, extract_to: Path) -> Path:
    """Extract a ZIP archive, skipping if already extracted."""
    extract_to.mkdir(parents=True, exist_ok=True)
    flag = extract_to / ".extracted"
    if flag.exists():
        log.info("Already extracted: %s", extract_to)
        return extract_to
    log.info("Extracting %s -> %s", zip_path.name, extract_to)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_to)
    flag.touch()
    return extract_to


# ── Individual downloaders ────────────────────────────────────────────────────

def download_nces_schools() -> Path:
    """NCES EDGE School Universe 2022-23. Returns extracted directory."""
    dest_zip = DATA_RAW / "nces_edge_schools.zip"
    _download(URLS["nces_edge_schools"], dest_zip)
    return _extract_zip(dest_zip, DATA_RAW / "nces_edge_schools")


def download_nces_ccd() -> Path:
    """NCES Common Core of Data — enrollment and demographics."""
    dest_zip = DATA_RAW / "nces_ccd.zip"
    _download(URLS["nces_ccd"], dest_zip)
    return _extract_zip(dest_zip, DATA_RAW / "nces_ccd")


def download_ejscreen() -> Path:
    """EPA EJScreen 2023 block group CSV. Returns CSV path."""
    dest_zip = DATA_RAW / "ejscreen.zip"
    _download(URLS["ejscreen"], dest_zip)
    out = _extract_zip(dest_zip, DATA_RAW / "ejscreen")
    csvs = list(out.glob("*.csv"))
    if not csvs:
        raise FileNotFoundError("No CSV found inside EJScreen ZIP.")
    return csvs[0]


def check_manual_downloads() -> None:
    """Print status of data sources that require manual download."""
    manual = {
        "BTS Noise Map": {
            "path": DATA_RAW / "bts_noise",
            "instructions": (
                "Download National Transportation Noise Map GeoTIFF tiles from "
                "https://www.bts.gov/geospatial/national-transportation-noise-map "
                "and place in data/raw/bts_noise/"
            ),
        },
        "FHWA HPMS Shapefile": {
            "path": DATA_RAW / "hpms",
            "instructions": (
                "Download HPMS Highway shapefile from "
                "https://www.fhwa.dot.gov/policyinformation/hpms/shapefiles.cfm "
                "and place in data/raw/hpms/"
            ),
        },
        "CA CAASPP Results": {
            "path": DATA_RAW / "caaspp",
            "instructions": (
                "Download California CAASPP school-level results (All Students CSV) from "
                "https://caaspp-elpac.cde.ca.gov/caaspp/ResearchFileList "
                "and place in data/raw/caaspp/"
            ),
        },
    }

    print("\n=== Manual Download Status ===")
    for name, info in manual.items():
        path: Path = info["path"]
        found = path.exists() and any(path.iterdir()) if path.exists() else False
        icon = "FOUND" if found else "MISSING"
        print(f"[{icon}] {name}")
        if not found:
            print(f"  --> {info['instructions']}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Download raw data for school-noise analysis")
    p.add_argument("--all",      action="store_true")
    p.add_argument("--schools",  action="store_true")
    p.add_argument("--ccd",      action="store_true")
    p.add_argument("--ejscreen", action="store_true")
    p.add_argument("--check",    action="store_true")
    args = p.parse_args()

    if args.all or args.schools:
        download_nces_schools()
    if args.all or args.ccd:
        download_nces_ccd()
    if args.all or args.ejscreen:
        download_ejscreen()
    if args.check or args.all:
        check_manual_downloads()


if __name__ == "__main__":
    main()
