"""
demographic_overlay.py
Phase 2: Join demographic, EJScreen, and CCD data to school noise classifications.
"""
import logging
import json
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import requests
from scipy.stats import chi2_contingency

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_RAW, DATA_PROCESSED, CENSUS_API_KEY, DEEP_DIVE_FIPS, WGS84

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def load_ccd(ccd_dir: Path = None) -> pd.DataFrame:
    """Load NCES Common Core of Data enrollment/demographics."""
    if ccd_dir is None:
        ccd_dir = DATA_RAW / "nces_ccd"
    csvs = list(ccd_dir.glob("*.csv"))
    if not csvs:
        raise FileNotFoundError(
            f"No CCD CSVs in {ccd_dir}. Run: python -m src.data_acquisition --ccd"
        )
    dfs = [pd.read_csv(f, dtype=str, low_memory=False, encoding="latin-1") for f in csvs]
    ccd = pd.concat(dfs, ignore_index=True)
    ccd.columns = ccd.columns.str.upper()
    log.info("CCD loaded: %d rows", len(ccd))
    return ccd


def merge_ccd_to_schools(schools: gpd.GeoDataFrame, ccd: pd.DataFrame) -> gpd.GeoDataFrame:
    """Join CCD enrollment data to school GeoDataFrame via NCESSCH identifier."""
    nces_col = next((c for c in schools.columns if "NCESSCH" in c or "NCESID" in c), None)
    ccd_id   = next((c for c in ccd.columns    if "NCESSCH" in c or "NCESID" in c), None)
    if not nces_col or not ccd_id:
        log.warning("Cannot find NCESSCH join key -- skipping CCD merge")
        return schools
    keywords = ["MEMBER", "FRL", "FREE", "LUNCH", "HISP", "BLACK", "WHITE", "ENROLL"]
    keep = list(dict.fromkeys(
        [ccd_id] + [c for c in ccd.columns for kw in keywords if kw in c]
    ))
    merged = schools.merge(ccd[keep], left_on=nces_col, right_on=ccd_id, how="left")
    log.info("After CCD merge: %d schools, %d columns", len(merged), merged.shape[1])
    return merged


def fetch_acs_block_groups(state_fips: str = DEEP_DIVE_FIPS) -> pd.DataFrame:
    """Fetch ACS 5-year median income and poverty at block group level via Census API."""
    if not CENSUS_API_KEY:
        log.warning("No CENSUS_API_KEY in config.py -- skipping ACS")
        return pd.DataFrame()
    url = (
        "https://api.census.gov/data/2021/acs/acs5"
        "?get=GEO_ID,B19013_001E,B17001_002E,B17001_001E"
        f"&for=block+group:*&in=state:{state_fips}&key={CENSUS_API_KEY}"
    )
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data[1:], columns=data[0])
    df = df.rename(columns={
        "B19013_001E": "median_income",
        "B17001_002E": "poverty_count",
        "B17001_001E": "poverty_total",
    })
    for col in ["median_income", "poverty_count", "poverty_total"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["poverty_rate"] = (df["poverty_count"] / df["poverty_total"] * 100).round(1)
    df["GEOID"] = df["GEO_ID"].str.replace("1500000US", "", regex=False)
    log.info("ACS fetched: %d block groups", len(df))
    return df


def load_ejscreen(ejscreen_dir: Path = None) -> pd.DataFrame:
    """Load EPA EJScreen block group data."""
    if ejscreen_dir is None:
        ejscreen_dir = DATA_RAW / "ejscreen"
    csvs = list(ejscreen_dir.glob("*.csv"))
    if not csvs:
        raise FileNotFoundError(
            f"No EJScreen CSV in {ejscreen_dir}. Run: python -m src.data_acquisition --ejscreen"
        )
    ej = pd.read_csv(csvs[0], dtype=str, low_memory=False)
    ej.columns = ej.columns.str.upper()
    keep_kw = ["ID", "GEOID", "P_", "PEOPCOLORPCT", "LOWINCPCT", "DSLPM", "CANCER", "RESP"]
    return ej[[c for c in ej.columns if any(k in c for k in keep_kw)]]


def spatial_join_ejscreen(
    schools: gpd.GeoDataFrame,
    ej: pd.DataFrame,
    state_fips: str = DEEP_DIVE_FIPS,
) -> gpd.GeoDataFrame:
    """Spatially join EJScreen block group percentiles to schools."""
    ej = ej.copy()
    id_col = next((c for c in ej.columns if "ID" in c or "GEOID" in c), None)
    if id_col:
        ej["GEOID"] = ej[id_col].astype(str).str.zfill(12)
        ej = ej[ej["GEOID"].str.startswith(state_fips)]
    try:
        bg_url = (
            "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
            f"tigerWMS_ACS2021/MapServer/10/query?where=STATE+%3D+%27{state_fips}%27"
            "&outFields=GEOID&returnGeometry=true&f=geojson"
        )
        bgs = gpd.read_file(bg_url).merge(ej, on="GEOID", how="left")
        joined = gpd.sjoin(
            schools.to_crs(bgs.crs),
            bgs.drop(columns=["geometry"]),
            how="left",
            predicate="within",
        )
        return joined.to_crs(WGS84)
    except Exception as e:
        log.warning("EJScreen spatial join failed: %s", e)
        return schools


def equity_analysis(schools: gpd.GeoDataFrame) -> dict:
    """
    Chi-square tests: are Tier 3/4 schools disproportionately in
    low-income or high-minority communities?
    """
    results = {}
    if "noise_tier" not in schools.columns:
        return results
    schools = schools.copy()
    schools["high_noise"] = schools["noise_tier"].isin([3, 4]).astype(int)

    frl_col = next((c for c in schools.columns if "FRL" in c or "FREE" in c), None)
    if frl_col:
        schools[frl_col] = pd.to_numeric(schools[frl_col], errors="coerce")
        schools["low_income"] = (schools[frl_col] > schools[frl_col].median()).astype(int)
        ct = pd.crosstab(schools["high_noise"], schools["low_income"])
        chi2_val, p, dof, _ = chi2_contingency(ct)
        results["income_chi2"] = {
            "chi2": round(float(chi2_val), 3),
            "p": round(float(p), 4),
            "dof": int(dof),
        }
        log.info("Income chi-square: chi2=%.3f, p=%.4f", chi2_val, p)
    return results


def run_phase2(schools: gpd.GeoDataFrame = None) -> gpd.GeoDataFrame:
    """Run Phase 2 end-to-end."""
    out = DATA_PROCESSED / "schools_with_demographics.gpkg"
    if out.exists() and schools is None:
        log.info("Loading cached Phase 2 output: %s", out)
        return gpd.read_file(out)

    if schools is None:
        p1 = DATA_PROCESSED / "schools_noise_classified.gpkg"
        if not p1.exists():
            raise FileNotFoundError("Run Phase 1 first: python -m src.noise_classification")
        schools = gpd.read_file(p1)

    log.info("=== Phase 2: Demographic and Equity Overlay ===")

    try:
        schools = merge_ccd_to_schools(schools, load_ccd())
    except FileNotFoundError as e:
        log.warning("%s", e)

    try:
        schools = spatial_join_ejscreen(schools, load_ejscreen())
    except FileNotFoundError as e:
        log.warning("%s", e)

    eq_results = equity_analysis(schools)
    if eq_results:
        with open(DATA_PROCESSED / "equity_analysis.json", "w") as f:
            json.dump(eq_results, f, indent=2)
        log.info("Equity analysis saved.")

    schools.to_file(out, driver="GPKG")
    log.info("Phase 2 complete: %s", out)
    return schools


if __name__ == "__main__":
    run_phase2()
