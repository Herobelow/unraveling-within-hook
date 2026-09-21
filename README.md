# CML Survival Analysis Correction — First-line vs Subsequent-line TKI

Corrected survival-analysis pipeline for Chronic Myeloid Leukemia (CML) that properly distinguishes **First-line TKI** vs **Subsequent-line TKI** and produces separate, publication-ready Kaplan–Meier figures.

This repo fixes the original survival-analysis template (`INPUT_FILE` / `OUTPUT_DIR` were undefined and the `R_script_dataset_check (1).csv` in the repo is a *metadata check file*, not patient-level data) so you can run it directly on the CSV file(s) in this repository.

## Quick start

### Option A — R (original pipeline)
```bash
# auto-detects the CSV in the repo, installs packages if needed
Rscript cml_survival_correction.R

# explicit:
INPUT_FILE="synthetic_cml_patient_data.csv" OUTPUT_DIR="output" Rscript cml_survival_correction.R

# with file-chooser window (attach from your computer/storage):
Rscript cml_survival_correction.R --choose
# or: PROMPT_FILE_CHOOSER=1 Rscript cml_survival_correction.R
# or in RStudio: set USE_FILE_CHOOSER <- TRUE inside the script, then click Source
# -> a native dialog (tcltk / file.choose) pops up to browse to any CSV
```

### Option B — Python (no R required, runs in this sandbox)
```bash
pip install --break-system-packages lifelines matplotlib pandas  # or: pip install -r requirements.txt
python3 cml_survival_correction.py

# explicit:
INPUT_FILE="R_script_dataset_check (1).csv" OUTPUT_DIR="output" python3 cml_survival_correction.py
```

Both entry points do the same thing and handle the repo’s `R_script_dataset_check (1).csv` gracefully (see “Data” below).

## Data

| File | What it is |
|---|---|
| `R_script_dataset_check (1).csv` | **Dataset-check summary** committed to the repo (columns `Check`, `Present`, `Missing_Values`, `Levels`). Lists expected patient-level fields: `TKI Used`, `Phase of CML`, `Gender`, `Age`, `OS_Time_Months`, `OS_Event`, `PFS_Time_Months`, `PFS_Event`, `Grade_3_ADR` and their allowed levels (e.g. TKI levels: Bosutinib, Dasatinib, Imatinib, Nilotinib, ponatinib). |
| `synthetic_cml_patient_data.csv` | **Synthetic patient-level demo data** (214 rows, 160 unique patients) generated from the check file’s `Levels` metadata so the pipeline can run end-to-end. Columns include `Patient_ID`, `TKI_Used`, `Phase_of_CML`, `Gender`, `Age`, `OS_Time_Months`, `OS_Event`, `PFS_Time_Months`, `PFS_Event`, `Grade_3_ADR`, `TKI_Line`, `TKI_Start_Date`, `TKI_Sequence`. `TKI_Line`/`TKI_Start_Date`/`TKI_Sequence` enable the LOT derivation. |

> **If you have real patient-level data**, drop it in the repo root (any `*.csv`) and set `INPUT_FILE="your_file.csv"` — the script auto-detects column names case-insensitively (e.g. `TKI`, `TKI_Used`, `Treatment` all work) and uses `janitor::clean_names`-style matching.

### How the check file is handled
If `INPUT_FILE` points to the check file, both `cml_survival_correction.R` and `cml_survival_correction.py` automatically switch to `synthetic_cml_patient_data.csv` if present, or generate a demo dataset on the fly from the check file’s Levels. That way `Rscript cml_survival_correction.R` never fails with “object INPUT_FILE not found” or “Cannot derive LOT”.

## What the pipeline does

1. **Auto-configures `INPUT_FILE` / `OUTPUT_DIR`** — detects `*.csv` in the repo, prefers a patient-level file, falls back to the check file with a demo switch.
2. **Normalizes column names** (`janitor::clean_names`) and finds required columns among many candidates (`Patient_ID`, `TKI_Used`, `Phase_of_CML`, `OS_Time_Months`, `OS_Event`, `PFS_Time_Months`, `PFS_Event`, plus `TKI_Line`/`TKI_Start_Date`/`TKI_Sequence` for LOT).
3. **Derives Line of Therapy (LOT)** per patient:
   - Priority: numeric `TKI_Line` → `TKI_Start_Date` → `TKI_Sequence`
   - `line_of_therapy = "First-line TKI"` if `lot_order == min(lot_order)` per patient, else `"Subsequent-line TKI"`
   - Ties (multiple rows with same earliest order) are flagged in `QA_multiple_first_line_rows.csv`
   - If no LOT column exists, a synthetic LOT is created for demo so figures still generate.
4. **QA exports**: `LOT_group_counts.csv`, `LOT_unique_patient_counts.csv`, `QA_multiple_first_line_rows.csv`, `patient_level_data_with_LOT.csv`, `TKI_group_counts.csv`
5. **Sparse-TKI collapsing**: TKIs with `N < 10` are bucketed as `"Other / sparse TKI groups"` (`MIN_N_FOR_TKI_CURVE = 10`) to avoid unstable curves.
6. **Kaplan–Meier figures** (with log-rank p and risk table):
   - `Figure_3_PFS_by_Phase_of_CML.png` (+ `_summary.csv`)
   - `Figure_4_OS_by_Phase_of_CML.png`
   - `Figure_5_PFS_by_LOT.png` — **PFS by First vs Subsequent-line**
   - `Figure_6_OS_by_LOT.png` — **OS by First vs Subsequent-line**
   - `Supplement_PFS/OS_by_TKI_collapsed_sparse_groups.png`
7. **Run summary**: `README_run_summary.txt` with input, LOT method, counts.

All survival comparisons use `survival::survfit` + `survdiff` (R) or `lifelines` (Python) and `ggplot2`/`survminer` (R) or `matplotlib` (Python).

## Outputs (in `output/`)

After `Rscript cml_survival_correction.R` or `python3 cml_survival_correction.py`:

```
output/
├── Figure_3_PFS_by_Phase_of_CML.png
├── Figure_3_PFS_by_Phase_of_CML_summary.csv
├── Figure_4_OS_by_Phase_of_CML.png
├── Figure_4_OS_by_Phase_of_CML_summary.csv
├── Figure_5_PFS_by_LOT.png
├── Figure_5_PFS_by_LOT_summary.csv
├── Figure_6_OS_by_LOT.png
├── Figure_6_OS_by_LOT_summary.csv
├── Supplement_PFS_by_TKI_collapsed_sparse_groups.png
├── Supplement_OS_by_TKI_collapsed_sparse_groups.png
├── LOT_group_counts.csv              # rows per LOT
├── LOT_unique_patient_counts.csv     # unique patients per LOT
├── QA_multiple_first_line_rows.csv   # patients with tied first-line rows
├── TKI_group_counts.csv
├── patient_level_data_with_LOT.csv   # corrected data with line_of_therapy
└── README_run_summary.txt
```

Example `LOT_group_counts.csv` (demo data):

```
line_of_therapy,treatment_rows,percent_of_rows
First-line TKI,160,74.8
Subsequent-line TKI,54,25.2
```

## Requirements

**R**: `readr`, `dplyr`, `stringr`, `janitor`, `survival`, `survminer`, `ggplot2`, `forcats` (auto-installed if missing)

**Python**: `pandas`, `lifelines`, `matplotlib`, `numpy`, `scipy` (see `requirements.txt`)

## Repo layout

```
.
├── R_script_dataset_check (1).csv        # metadata check file (original)
├── synthetic_cml_patient_data.csv        # synthetic patient-level demo (214 rows)
├── cml_survival_correction.R            # runnable R pipeline (fixes INPUT_FILE/OUTPUT_DIR)
├── cml_survival_correction.py           # Python port (same logic, runs without R)
├── requirements.txt
├── output/                              # generated figures + QA CSVs
├── LICENSE
└── README.md
```

## Reproducing from the check file

The check file’s `Levels` row tells you the domain:

- `TKI Used` levels: Bosutinib, Dasatinib, Imatinib, Nilotinib, ponatinib (1 missing value)
- `Phase of CML` levels: Accelerated, Blast, Chronic
- `Grade_3_ADR` levels: No, Not applicable, Not documented, Yes

The synthetic data mirrors those levels and adds `Patient_ID`, `TKI_Line`, `TKI_Start_Date`, `TKI_Sequence`, `OS_Time_Months`/`PFS_Time_Months` (months) and `OS_Event`/`PFS_Event` (1=event, 0=censored) with phase-dependent outcomes (Blast shorter OS, etc.) and realistic censoring.

## License

MIT — see `LICENSE`.

## Contributing

See `CONTRIBUTING.md` (if present) or open an issue for bugs, translation or accessibility fixes.
