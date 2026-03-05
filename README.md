# Noise Pollution & Cognitive Development: Are Schools Too Close to Highways?

A national-scale spatial analysis classifying every US public elementary school by modeled highway noise exposure, testing whether noise exposure is disproportionately borne by low-income communities, and quantifying the statistical relationship between noise and academic performance.

---

## Research Question

How many US elementary schools sit inside highway noise corridors exceeding WHO cognitive-impact thresholds (55 dB LAeq), which communities are most affected, and is there a statistically detectable relationship between modeled noise exposure and student academic performance after controlling for socioeconomic factors?

---

## Project Structure

```
School Noise/
├── config.py                    # Paths, WHO tiers, CRS settings
├── requirements.txt
├── src/
│   ├── data_acquisition.py      # Download all raw data sources
│   ├── noise_classification.py  # Phase 1: raster extraction, tier classification
│   ├── demographic_overlay.py   # Phase 2: CCD, ACS, EJScreen joins + equity analysis
│   ├── statistical_analysis.py  # Phase 3: OLS, GWR, sensitivity analysis
│   └── visualization.py         # Phase 4: static maps + GeoJSON export
├── notebooks/
│   ├── 01_data_acquisition.ipynb
│   ├── 02_noise_classification.ipynb
│   ├── 03_demographic_overlay.ipynb
│   ├── 04_statistical_analysis.ipynb
│   └── 05_visualization.ipynb
├── web_map/
│   └── index.html               # Interactive Leaflet map (works offline with demo data)
├── data/
│   ├── raw/                     # Downloaded source data (not committed)
│   └── processed/               # Pipeline outputs (GeoPackages, CSVs)
└── outputs/
    ├── maps/                    # Static PNG cartographic outputs
    ├── reports/                 # OLS results, GWR coefficients, equity analysis JSON
    └── data/                    # GeoJSON export for web map
```

---

## Data Sources

| Dataset | Source | Format | Access |
|---|---|---|---|
| Transportation Noise Map | BTS National Transportation Noise Map | GeoTIFF (dB LAeq) | **Manual download** |
| School Locations | NCES EDGE School Universe | CSV / Shapefile | Automated |
| School Performance | CA CAASPP Results | CSV | **Manual download** |
| Demographics | ACS 5-Year Estimates | Census API | Automated (API key needed) |
| Environmental Justice | EPA EJScreen 2023 | CSV | Automated |
| Highway Traffic | FHWA HPMS | Shapefile | **Manual download** |
| Enrollment Demographics | NCES Common Core of Data | CSV | Automated |

### Manual Downloads

**1. BTS National Transportation Noise Map**
- URL: https://www.bts.gov/geospatial/national-transportation-noise-map
- Download the GeoTIFF tiles for the contiguous US
- Place files in `data/raw/bts_noise/`

**2. FHWA HPMS Highway Shapefile**
- URL: https://www.fhwa.dot.gov/policyinformation/hpms/shapefiles.cfm
- Download the national highway shapefile
- Place in `data/raw/hpms/`

**3. California CAASPP Test Results**
- URL: https://caaspp-elpac.cde.ca.gov/caaspp/ResearchFileList
- Download "All Students" research file (most recent year)
- Place in `data/raw/caaspp/`

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Download automated data sources
python -m src.data_acquisition --all

# 3. Check manual download status
python -m src.data_acquisition --check

# 4. Run Phase 1: Noise classification (requires BTS noise map)
python -m src.noise_classification

# 5. Run Phase 2: Demographic overlay
python -m src.demographic_overlay

# 6. Run Phase 3: Statistical analysis (requires CAASPP data)
python -m src.statistical_analysis

# 7. Generate maps and web map export
python -m src.visualization

# 8. Open the interactive web map
python -m http.server 8000
# Navigate to: http://localhost:8000/web_map/
```

Or run everything through the Jupyter notebooks in order.

---

## WHO Noise Exposure Tiers

| Tier | dB LAeq | Classification | Health Impact |
|---|---|---|---|
| 1 | < 50 dB | Minimal Risk | No significant cognitive effects |
| 2 | 50–55 dB | Elevated Risk | Some evidence of reading delays |
| 3 | 55–65 dB | **Significant Impact** | Impaired reading comprehension, memory |
| 4 | > 65 dB | **Severe Exposure** | Substantial cognitive development risk |

*Source: WHO Environmental Noise Guidelines for the European Region (2018)*

---

## Methodology

### Phase 1: National Noise Exposure Classification
- Load ~67,000 NCES public elementary school locations
- Sample BTS GeoTIFF noise tiles at each school point using `rasterio`
- Classify into 4 WHO-derived tiers
- Compute distance to nearest HPMS highway segment via `cKDTree`
- Generate state-by-state summary ranked by high-noise school percentage

### Phase 2: Demographic and Equity Overlay
- Join NCES CCD enrollment and FRL (free/reduced lunch) data
- Fetch ACS block group median income and poverty rate via Census API
- Spatially join EPA EJScreen environmental justice indices
- Chi-square tests: are Tier 3/4 schools disproportionately low-income or high-minority?

### Phase 3: Statistical Analysis (California Deep Dive)
- Merge California CAASPP school-level test scores (grades 3–5, ELA + Math)
- **OLS regression**: proficiency ~ noise_db + FRL% + enrollment + median_income + dist_highway
- **GWR (mgwr)**: test whether the noise-performance relationship varies spatially
- **Sensitivity analysis**: re-run at 100m, 200m, 300m buffer distances

### Phase 4: Deliverables
- Static maps: national dot map, state scorecard, noise distribution histogram, equity scatter
- GeoJSON export for the interactive web map
- Interactive Leaflet map with clustering, tier toggles, state filter, popup detail

---

## Census API Setup

To fetch ACS demographic data automatically:

1. Get a free API key: https://api.census.gov/data/key_signup.html
2. Set `CENSUS_API_KEY = "your_key_here"` in `config.py`

---

## Key Outputs

| Output | Location | Description |
|---|---|---|
| School noise database | `data/processed/schools_noise_classified.gpkg` | All schools with noise tier, dB, highway distance |
| Demographic database | `data/processed/schools_with_demographics.gpkg` | Above + CCD + EJScreen |
| State summary | `data/processed/state_noise_summary.csv` | States ranked by high-noise % |
| Equity analysis | `data/processed/equity_analysis.json` | Chi-square test results |
| OLS results | `data/processed/ols_results.txt` | Regression summary |
| GWR coefficients | `data/processed/gwr_coefficients.csv` | Local noise effect estimates |
| National map | `outputs/maps/national_noise_overview.png` | Cartographic output |
| State scorecard | `outputs/maps/state_scorecard.png` | Ranking bar chart |
| Web map data | `outputs/data/schools_webmap.geojson` | Minimal GeoJSON for Leaflet |

---

## Technical Stack

| Component | Tool |
|---|---|
| GIS / raster | Python · rasterio · rasterstats · geopandas |
| Statistical analysis | statsmodels · mgwr · scipy · libpysal |
| Data processing | pandas · numpy |
| Visualization | matplotlib |
| Web mapping | Leaflet.js · Leaflet.markercluster |
| Reproducibility | Jupyter notebooks · Python modules |
