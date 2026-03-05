"""
Project configuration for School Noise & Cognitive Development Analysis.
"""

from pathlib import Path

# ── Root directories ──────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent
DATA_RAW = ROOT_DIR / "data" / "raw"
DATA_PROCESSED = ROOT_DIR / "data" / "processed"
OUTPUTS = ROOT_DIR / "outputs"
MAPS_DIR = OUTPUTS / "maps"
REPORTS_DIR = OUTPUTS / "reports"
DATA_OUT = OUTPUTS / "data"

# Create dirs if missing
for d in [DATA_RAW, DATA_PROCESSED, MAPS_DIR, REPORTS_DIR, DATA_OUT]:
    d.mkdir(parents=True, exist_ok=True)

# ── Census API ─────────────────────────────────────────────────────────────────
# Get a free key at https://api.census.gov/data/key_signup.html
CENSUS_API_KEY = ""

# ── WHO Noise Thresholds (dB LAeq) ───────────────────────────────────────────
NOISE_TIERS = {
    "Tier 1 - Minimal Risk":       (None, 50),   # < 50 dB
    "Tier 2 - Elevated Risk":      (50,   55),   # 50-55 dB
    "Tier 3 - Significant Impact": (55,   65),   # 55-65 dB
    "Tier 4 - Severe Exposure":    (65,   None), # > 65 dB
}

TIER_COLORS = {
    "Tier 1 - Minimal Risk":       "#2ecc71",
    "Tier 2 - Elevated Risk":      "#f1c40f",
    "Tier 3 - Significant Impact": "#e67e22",
    "Tier 4 - Severe Exposure":    "#e74c3c",
}

TIER_LABELS = {
    1: "Tier 1 - Minimal Risk",
    2: "Tier 2 - Elevated Risk",
    3: "Tier 3 - Significant Impact",
    4: "Tier 4 - Severe Exposure",
}

# ── Highway buffer distances for sensitivity analysis (meters) ────────────────
BUFFER_DISTANCES = [100, 200, 300]

# ── Deep-dive state ──────────────────────────────────────────────────────────
DEEP_DIVE_STATE = "California"
DEEP_DIVE_FIPS  = "06"

# ── Data URLs ─────────────────────────────────────────────────────────────────
URLS = {
    "nces_edge_schools": "https://nces.ed.gov/programs/edge/data/EDGESCHOOLPLACE2223.zip",
    "nces_ccd": "https://nces.ed.gov/ccd/data/zip/ccd_sch_029_2223_w_0a_220928.zip",
    "ejscreen": "https://gaftp.epa.gov/EJSCREEN/2023/2.22_September_UseMe/EJSCREEN_2023_BG_with_AS_CNMI_GU_VI.csv.zip",
    # BTS noise tiles require manual download from bts.gov — see README
    # HPMS data requires manual download from hpms.fhwa.dot.gov — see README
    # CA CAASPP results — download manually from caaspp-elpac.cde.ca.gov
}

# ── CRS ───────────────────────────────────────────────────────────────────────
WGS84 = "EPSG:4326"
CONUS_ALBERS = "EPSG:5070"   # Equal-area for national distance calculations
