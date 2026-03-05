"""
noise_classification.py
Phase 1: National noise exposure classification.
"""
import logging
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import rasterio
from scipy.spatial import cKDTree

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_RAW, DATA_PROCESSED, TIER_LABELS, WGS84, CONUS_ALBERS

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def load_schools(edge_dir: Path = None) -> gpd.GeoDataFrame:
    if edge_dir is None:
        edge_dir = DATA_RAW / "nces_edge_schools"
    csvs = list(edge_dir.glob("*.csv"))
    shps = list(edge_dir.glob("*.shp")) + list(edge_dir.glob("*.gpkg"))
    if shps:
        gdf = gpd.read_file(shps[0])
    elif csvs:
        df = pd.read_csv(csvs[0], dtype=str, low_memory=False)
        df.columns = df.columns.str.upper()
        lat_col = next(c for c in df.columns if "LAT" in c)
        lon_col = next(c for c in df.columns if "LON" in c)
        df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
        df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")
        df = df.dropna(subset=[lat_col, lon_col])
        gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[lon_col], df[lat_col]), crs=WGS84)
    else:
        raise FileNotFoundError(f"No school data in {edge_dir}. Run: python -m src.data_acquisition --schools")
    gdf.columns = [c.upper() for c in gdf.columns]
    itlev = next((c for c in gdf.columns if "ITLEV" in c or "LEVEL" in c), None)
    if itlev:
        gdf = gdf[gdf[itlev].astype(str).isin(["1", "Primary"])]
    log.info("Loaded %d elementary schools", len(gdf))
    return gdf.set_crs(WGS84, allow_override=True)


def extract_noise_at_schools(schools: gpd.GeoDataFrame, noise_dir: Path = None) -> gpd.GeoDataFrame:
    if noise_dir is None:
        noise_dir = DATA_RAW / "bts_noise"
    tifs = sorted(noise_dir.glob("*.tif")) + sorted(noise_dir.glob("*.tiff"))
    if not tifs:
        raise FileNotFoundError(f"No GeoTIFF in {noise_dir}. Download BTS noise tiles -- see README.")
    schools = schools.to_crs(WGS84).copy()
    schools["noise_db"] = np.nan
    for tif in tifs:
        log.info("Sampling: %s", tif.name)
        with rasterio.open(tif) as src:
            s = schools.to_crs(src.crs)
            coords = [(g.x, g.y) for g in s.geometry]
            vals = np.array([v[0] if (src.nodata is None or v[0] != src.nodata) else np.nan for v in src.sample(coords)], dtype=float)
        mask = schools["noise_db"].isna() & ~np.isnan(vals)
        schools.loc[mask, "noise_db"] = vals[mask]
    log.info("Noise extraction: %d valid, %d missing", (~schools["noise_db"].isna()).sum(), schools["noise_db"].isna().sum())
    return schools


def classify_noise_tiers(schools: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    def _tier(db):
        if pd.isna(db): return np.nan
        if db < 50: return 1
        elif db < 55: return 2
        elif db < 65: return 3
        else: return 4
    schools = schools.copy()
    schools["noise_tier"] = schools["noise_db"].apply(_tier)
    schools["noise_tier_label"] = schools["noise_tier"].map(TIER_LABELS)
    return schools


def add_highway_proximity(schools: gpd.GeoDataFrame, hpms_dir: Path = None) -> gpd.GeoDataFrame:
    if hpms_dir is None:
        hpms_dir = DATA_RAW / "hpms"
    shps = list(hpms_dir.glob("*.shp")) + list(hpms_dir.glob("*.gpkg"))
    if not shps:
        log.warning("No HPMS shapefile in %s -- skipping highway proximity", hpms_dir)
        schools["dist_highway_m"] = np.nan
        schools["nearest_aadt"] = np.nan
        return schools
    hpms = gpd.read_file(shps[0]).to_crs(CONUS_ALBERS)
    schools_ea = schools.to_crs(CONUS_ALBERS)
    tree = cKDTree(np.array([[g.centroid.x, g.centroid.y] for g in hpms.geometry]))
    dists, idxs = tree.query(np.array([[g.x, g.y] for g in schools_ea.geometry]), k=1)
    schools = schools.copy()
    schools["dist_highway_m"] = dists
    aadt_col = next((c for c in hpms.columns if "AADT" in c.upper() or "VOLUME" in c.upper()), None)
    schools["nearest_aadt"] = hpms.iloc[idxs][aadt_col].values if aadt_col else np.nan
    log.info("Highway proximity done")
    return schools


def national_summary(schools: gpd.GeoDataFrame) -> pd.DataFrame:
    state_col = next((c for c in schools.columns if c in ("STABR", "ST", "STATE_ABBR", "STABBR")), None)
    if not state_col:
        return pd.DataFrame()
    summary = schools.groupby([state_col, "noise_tier_label"]).size().unstack(fill_value=0)
    summary["total"] = summary.sum(axis=1)
    high = [c for c in summary.columns if "Significant" in str(c) or "Severe" in str(c)]
    if high:
        summary["pct_high_noise"] = (summary[high].sum(axis=1) / summary["total"] * 100).round(1)
    return summary.sort_values("pct_high_noise", ascending=False)


def run_phase1() -> gpd.GeoDataFrame:
    out = DATA_PROCESSED / "schools_noise_classified.gpkg"
    if out.exists():
        log.info("Loading cached output: %s", out)
        return gpd.read_file(out)
    log.info("=== Phase 1: National Noise Exposure Classification ===")
    schools = load_schools()
    schools = extract_noise_at_schools(schools)
    schools = classify_noise_tiers(schools)
    schools = add_highway_proximity(schools)
    schools.to_file(out, driver="GPKG")
    summary = national_summary(schools)
    if not summary.empty:
        summary.to_csv(DATA_PROCESSED / "state_noise_summary.csv")
    log.info("Phase 1 complete: %d schools", len(schools))
    return schools


if __name__ == "__main__":
    run_phase1()
