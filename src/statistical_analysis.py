"""
statistical_analysis.py
Phase 3: Multivariate OLS regression, GWR, and sensitivity analysis.

Deep-dive is California, using CAASPP test scores joined to noise/demographic data.
"""
import logging
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import statsmodels.api as sm
from scipy.stats import pearsonr

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_RAW, DATA_PROCESSED

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# ── CAASPP data ───────────────────────────────────────────────────────────────

def load_caaspp(caaspp_dir: Path = None) -> pd.DataFrame:
    """
    Load California CAASPP school-level results.
    Filters to grades 3-5, All Students group.
    """
    if caaspp_dir is None:
        caaspp_dir = DATA_RAW / "caaspp"
    files = list(caaspp_dir.glob("*.csv")) + list(caaspp_dir.glob("*.txt"))
    if not files:
        raise FileNotFoundError(
            f"No CAASPP data in {caaspp_dir}. "
            "Download from https://caaspp-elpac.cde.ca.gov/caaspp/ResearchFileList"
        )
    dfs = [pd.read_csv(f, dtype=str, low_memory=False) for f in files]
    ca = pd.concat(dfs, ignore_index=True)
    ca.columns = ca.columns.str.strip().str.upper().str.replace(" ", "_")
    log.info("CAASPP loaded: %d rows", len(ca))

    grade_col = next((c for c in ca.columns if "GRADE" in c), None)
    type_col  = next((c for c in ca.columns if "TYPE" in c and "ID" in c), None)
    if grade_col:
        ca = ca[ca[grade_col].isin(["3", "4", "5"])]
    if type_col:
        ca = ca[ca[type_col] == "1"]
    log.info("After grade/type filter: %d rows", len(ca))
    return ca


def aggregate_caaspp(ca: pd.DataFrame) -> pd.DataFrame:
    """Aggregate to school level: mean pct meeting/exceeding standard."""
    pct_col = next(
        (c for c in ca.columns if "PERCENT" in c and ("MET" in c or "STANDARD" in c)), None
    )
    sch_col = next((c for c in ca.columns if "SCHOOL" in c and "CODE" in c), None)
    if not pct_col or not sch_col:
        log.warning("Cannot find required CAASPP columns.")
        return ca
    ca = ca.copy()
    ca[pct_col] = pd.to_numeric(ca[pct_col], errors="coerce")
    agg = ca.groupby(sch_col)[pct_col].mean().reset_index()
    agg.columns = [sch_col, "pct_proficient_mean"]
    log.info("CAASPP aggregated: %d schools", len(agg))
    return agg


# ── OLS Regression ────────────────────────────────────────────────────────────

def build_ols_model(df: pd.DataFrame):
    """
    OLS: pct_proficient_mean ~ noise_db + pct_frl + enrollment + median_income + dist_highway_m
    Returns fitted statsmodels OLS result.
    """
    dep_var = "pct_proficient_mean"
    candidates = ["noise_db", "noise_tier", "pct_frl", "enrollment", "median_income", "dist_highway_m"]
    available = [dep_var] + [c for c in candidates if c in df.columns]
    model_df = df[available].dropna()
    if len(model_df) < 30:
        raise ValueError(f"Insufficient observations for regression: {len(model_df)}")

    X_cols = [c for c in candidates if c in model_df.columns]
    X = sm.add_constant(model_df[X_cols])
    y = model_df[dep_var]
    model = sm.OLS(y, X).fit()
    log.info("\nOLS Results:\n%s", model.summary())
    return model


def sensitivity_buffer_analysis(schools: gpd.GeoDataFrame, buffers=(100, 200, 300)) -> pd.DataFrame:
    """
    Correlate school-level proficiency with mean noise at each buffer distance.
    Expects columns noise_mean_{N}m pre-computed during Phase 1.
    """
    results = []
    for buf in buffers:
        col = f"noise_mean_{buf}m"
        if col not in schools.columns:
            continue
        valid = schools[[col, "pct_proficient_mean"]].dropna()
        if len(valid) > 10:
            r, p = pearsonr(valid[col], valid["pct_proficient_mean"])
            results.append({"buffer_m": buf, "pearson_r": round(r, 3), "p_value": round(p, 4), "n": len(valid)})
    return pd.DataFrame(results)


# ── Geographically Weighted Regression ───────────────────────────────────────

def run_gwr(df: pd.DataFrame) -> None:
    """
    Run GWR using mgwr package if available.
    Saves local coefficients and R2 to data/processed/.
    """
    try:
        from mgwr.gwr import GWR
        from mgwr.sel_bw import Sel_BW
    except ImportError:
        log.warning("mgwr not installed (pip install mgwr). Falling back to spatial OLS.")
        _run_spatial_lag(df)
        return

    dep_var = "pct_proficient_mean"
    indep   = [c for c in ["noise_db", "pct_frl", "median_income"] if c in df.columns]
    model_df = df[[dep_var] + indep + ["geometry"]].dropna()
    if len(model_df) < 50:
        log.warning("Too few obs for GWR (%d). Skipping.", len(model_df))
        return

    coords = np.array([[g.x, g.y] for g in model_df.geometry])
    y = model_df[dep_var].values.reshape(-1, 1)
    X = model_df[indep].values

    bw = Sel_BW(coords, y, X).search()
    results = GWR(coords, y, X, bw).fit()
    log.info("GWR complete. Bandwidth: %s, R2: %.3f", bw, results.R2)

    coef_df = pd.DataFrame(results.params, columns=["intercept"] + indep)
    coef_df["R2_local"] = results.localR2
    coef_df.to_csv(DATA_PROCESSED / "gwr_coefficients.csv", index=False)
    log.info("GWR coefficients saved.")


def _run_spatial_lag(df: pd.DataFrame) -> None:
    """Fallback spatial OLS with KNN weights via libpysal/spreg."""
    try:
        import libpysal
        from spreg import OLS as spOLS
        dep = "pct_proficient_mean"
        indep = [c for c in ["noise_db", "pct_frl", "median_income"] if c in df.columns]
        valid = df[[dep] + indep + ["geometry"]].dropna()
        w = libpysal.weights.KNN.from_dataframe(valid, k=8)
        w.transform = "r"
        result = spOLS(
            valid[[dep]].values, valid[indep].values,
            w=w, name_y=dep, name_x=indep
        )
        log.info("Spatial OLS:\n%s", result.summary)
    except ImportError:
        log.warning("libpysal/spreg not installed. Skipping spatial regression.")


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_phase3(schools: gpd.GeoDataFrame = None) -> dict:
    """Run Phase 3 statistical analysis. Returns dict with model summaries."""
    if schools is None:
        for p in [DATA_PROCESSED / "schools_with_demographics.gpkg",
                  DATA_PROCESSED / "schools_noise_classified.gpkg"]:
            if p.exists():
                schools = gpd.read_file(p)
                break
    if schools is None:
        raise FileNotFoundError("Run Phase 1 (and optionally Phase 2) first.")

    # Filter to California for deep-dive
    state_col = next((c for c in schools.columns if c in ("STABR", "ST", "STATE_ABBR", "STABBR")), None)
    ca = schools[schools[state_col] == "CA"].copy() if state_col else schools.copy()
    log.info("California schools: %d", len(ca))

    # Merge CAASPP test scores
    try:
        caaspp = aggregate_caaspp(load_caaspp())
        sch_col  = next((c for c in caaspp.columns if "SCHOOL" in c and "CODE" in c), None)
        nces_col = next((c for c in ca.columns if "NCESSCH" in c or "CDS" in c or "SCHOOL" in c), None)
        if sch_col and nces_col:
            ca = ca.merge(caaspp, left_on=nces_col, right_on=sch_col, how="left")
            n_scores = ca["pct_proficient_mean"].notna().sum()
            log.info("CAASPP merged: %d schools with scores", n_scores)
    except FileNotFoundError as e:
        log.warning("%s", e)

    results = {}
    if "pct_proficient_mean" in ca.columns and ca["pct_proficient_mean"].notna().sum() > 30:
        try:
            model = build_ols_model(ca)
            results["ols_r2"] = round(model.rsquared, 3)
            results["ols_r2_adj"] = round(model.rsquared_adj, 3)
            with open(DATA_PROCESSED / "ols_results.txt", "w") as f:
                f.write(model.summary().as_text())
            run_gwr(ca)
            buf = sensitivity_buffer_analysis(ca)
            if not buf.empty:
                buf.to_csv(DATA_PROCESSED / "buffer_sensitivity.csv", index=False)
        except Exception as e:
            log.error("Regression failed: %s", e)

    log.info("=== Phase 3 complete ===")
    return results


if __name__ == "__main__":
    run_phase3()
