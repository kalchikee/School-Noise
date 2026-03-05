"""
visualization.py
Generate static maps and export processed data for the interactive web map.
"""
import logging
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import BoundaryNorm, ListedColormap

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_PROCESSED, MAPS_DIR, DATA_OUT, TIER_COLORS, TIER_LABELS

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

TIER_COLOR_LIST = [TIER_COLORS[TIER_LABELS[i]] for i in range(1, 5)]


def plot_national_overview(schools: gpd.GeoDataFrame, out: Path = None) -> None:
    """Dot map: every school colored by WHO noise tier."""
    if out is None:
        out = MAPS_DIR / "national_noise_overview.png"
    fig, ax = plt.subplots(figsize=(20, 12))
    ax.set_facecolor("#1a1a2e")
    fig.patch.set_facecolor("#1a1a2e")

    cmap = ListedColormap(TIER_COLOR_LIST)
    norm = BoundaryNorm([0.5, 1.5, 2.5, 3.5, 4.5], cmap.N)

    schools.to_crs("EPSG:5070").plot(
        column="noise_tier", ax=ax, cmap=cmap, norm=norm,
        markersize=0.5, alpha=0.7, legend=False,
    )
    patches = [
        mpatches.Patch(color=TIER_COLORS[TIER_LABELS[i]], label=TIER_LABELS[i])
        for i in range(1, 5)
    ]
    ax.legend(
        handles=patches, loc="lower left", framealpha=0.3,
        facecolor="#1a1a2e", edgecolor="white", labelcolor="white", fontsize=9,
    )
    ax.set_title(
        "US Elementary Schools by Highway Noise Exposure (WHO Tiers)",
        color="white", fontsize=16, pad=15,
    )
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(out, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    log.info("Saved: %s", out)
    plt.close()


def plot_state_scorecard(summary: pd.DataFrame, top_n: int = 20, out: Path = None) -> None:
    """Horizontal bar chart: top N states by high-noise school percentage."""
    if out is None:
        out = MAPS_DIR / "state_scorecard.png"
    if "pct_high_noise" not in summary.columns:
        return
    data = summary.head(top_n)[["pct_high_noise"]].reset_index()
    state_col = data.columns[0]
    colors = [
        "#e74c3c" if v >= 30 else "#e67e22" if v >= 15 else "#f1c40f"
        for v in data["pct_high_noise"]
    ]
    fig, ax = plt.subplots(figsize=(10, 8))
    bars = ax.barh(data[state_col], data["pct_high_noise"], color=colors, edgecolor="white", linewidth=0.5)
    for bar, val in zip(bars, data["pct_high_noise"]):
        ax.text(
            bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
            f"{val:.1f}%", va="center", fontsize=9,
        )
    ax.set_xlabel("% of Elementary Schools in Tier 3 or 4 (>55 dB)")
    ax.set_title(f"Top {top_n} States: Elementary Schools in High Noise Zones")
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    log.info("Saved: %s", out)
    plt.close()


def plot_noise_distribution(schools: gpd.GeoDataFrame, out: Path = None) -> None:
    """Histogram of modeled noise_db values at all schools."""
    if out is None:
        out = MAPS_DIR / "noise_distribution.png"
    if "noise_db" not in schools.columns:
        return
    vals = schools["noise_db"].dropna()
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(vals, bins=50, color="#3498db", edgecolor="white", linewidth=0.3)
    for thresh, color, label in [
        (50, "#f1c40f", "50 dB"),
        (55, "#e67e22", "55 dB WHO Threshold"),
        (65, "#e74c3c", "65 dB Severe"),
    ]:
        ax.axvline(thresh, color=color, linewidth=2, linestyle="--", label=label)
    ax.set_xlabel("Modeled Noise Level (dB LAeq)")
    ax.set_ylabel("Number of Schools")
    ax.set_title("Distribution of Highway Noise Exposure at US Elementary Schools")
    ax.legend()
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    log.info("Saved: %s", out)
    plt.close()


def plot_equity_scatter(schools: gpd.GeoDataFrame, out: Path = None) -> None:
    """Scatter plot: FRL% vs. noise_db, colored by tier."""
    if out is None:
        out = MAPS_DIR / "equity_scatter.png"
    frl_col = next((c for c in schools.columns if "FRL" in c or "FREE" in c), None)
    if not frl_col or "noise_db" not in schools.columns:
        return
    df = schools[[frl_col, "noise_db", "noise_tier"]].copy()
    df[frl_col] = pd.to_numeric(df[frl_col], errors="coerce")
    df = df.dropna()

    fig, ax = plt.subplots(figsize=(10, 7))
    for tier in [1, 2, 3, 4]:
        sub = df[df["noise_tier"] == tier]
        ax.scatter(sub[frl_col], sub["noise_db"], c=TIER_COLORS[TIER_LABELS[tier]],
                   label=TIER_LABELS[tier], alpha=0.5, s=8)
    ax.axhline(55, color="orange", linestyle="--", linewidth=1.5, label="WHO 55 dB Threshold")
    ax.set_xlabel("Free/Reduced Lunch Eligibility (%)")
    ax.set_ylabel("Modeled Noise Level (dB LAeq)")
    ax.set_title("School Poverty Rate vs. Noise Exposure")
    ax.legend(fontsize=8, markerscale=2)
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    log.info("Saved: %s", out)
    plt.close()


def export_geojson_for_webmap(schools: gpd.GeoDataFrame, max_rows: int = 70000) -> Path:
    """Export school data as GeoJSON for the interactive web map (minimal columns)."""
    out = DATA_OUT / "schools_webmap.geojson"
    keep = ["geometry", "noise_db", "noise_tier", "noise_tier_label",
            "dist_highway_m", "nearest_aadt"]
    optional = ["pct_proficient_mean", "STABR", "ST", "STATE_ABBR",
                "SCHNAM", "NAME", "NCESSCH"]
    keep += [c for c in optional if c in schools.columns]
    keep = list(dict.fromkeys(c for c in keep if c in schools.columns or c == "geometry"))

    export = schools[keep].to_crs("EPSG:4326")
    if len(export) > max_rows:
        export = export.head(max_rows)
    export.to_file(out, driver="GeoJSON")
    log.info("GeoJSON exported: %s (%d KB)", out, out.stat().st_size // 1024)
    return out


def run_phase4_static(schools: gpd.GeoDataFrame = None, summary: pd.DataFrame = None) -> None:
    """Generate all static cartographic outputs."""
    if schools is None:
        for p in [DATA_PROCESSED / "schools_with_demographics.gpkg",
                  DATA_PROCESSED / "schools_noise_classified.gpkg"]:
            if p.exists():
                schools = gpd.read_file(p)
                break
    if schools is None:
        raise FileNotFoundError("Run Phase 1 first.")

    if summary is None:
        p = DATA_PROCESSED / "state_noise_summary.csv"
        summary = pd.read_csv(p, index_col=0) if p.exists() else pd.DataFrame()

    plot_national_overview(schools)
    plot_noise_distribution(schools)
    plot_equity_scatter(schools)
    if not summary.empty:
        plot_state_scorecard(summary)
    export_geojson_for_webmap(schools)
    log.info("=== Phase 4 static outputs complete ===")


if __name__ == "__main__":
    run_phase4_static()
