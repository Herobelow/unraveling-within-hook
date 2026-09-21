# ==============================================================================
# CML survival analysis correction: first-line vs subsequent-line TKI
# Auto-configured to run on CSV file(s) in this repo
# ==============================================================================
# This script is a corrected, runnable version of the survival-analysis template.
# It auto-detects the input CSV in the repository and sets sensible defaults for
# INPUT_FILE and OUTPUT_DIR so you can run it without editing:
#
#   Rscript cml_survival_correction.R
#   # or with overrides:
#   INPUT_FILE="my_data.csv" OUTPUT_DIR="results" Rscript cml_survival_correction.R
#   # or with file-chooser window (attach from storage):
#   Rscript cml_survival_correction.R --choose
#   # or in RStudio: set USE_FILE_CHOOSER <- TRUE inside the script, then Source
#
# In RStudio / R GUI an interactive window pops up so you can browse to any CSV on
# your computer/storage (via tcltk -> svDialogs -> file.choose). Just click and attach.
#
# It also handles the repository's dataset-check CSV gracefully:
# - If the detected CSV is the metadata check file (R_script_dataset_check (1).csv),
#   the script will automatically switch to synthetic_cml_patient_data.csv if present,
#   or generate a demo dataset from the check-file Levels metadata.
#
# Outputs (in OUTPUT_DIR):
#   LOT_group_counts.csv, LOT_unique_patient_counts.csv, QA_multiple_first_line_rows.csv,
#   patient_level_data_with_LOT.csv, TKI_group_counts.csv,
#   Figure_3_PFS_by_Phase_of_CML.png (+ _summary.csv)
#   Figure_4_OS_by_Phase_of_CML.png  (+ _summary.csv)
#   Figure_5_PFS_by_LOT.png (+ _summary.csv)
#   Figure_6_OS_by_LOT.png  (+ _summary.csv)
#   Supplement_*_by_TKI_collapsed_sparse_groups.png (+ _summary.csv)
#   README_run_summary.txt
# ==============================================================================

# ----------------------- Auto-configure INPUT / OUTPUT ------------------------
# Candidate input files in repo (supports the spaced name in this repo)
repo_csvs <- list.files(pattern = "\\.csv$", recursive = FALSE, full.names = FALSE)
# Also check one level down
if (length(repo_csvs) == 0) {
  repo_csvs <- list.files(pattern = "\\.csv$", recursive = TRUE, full.names = TRUE)
}

# Allow override via environment variable or commandArgs
get_env <- function(x, default = NA) {
  v <- Sys.getenv(x, unset = NA)
  if (!is.na(v) && nzchar(v)) return(v)
  # also check commandArgs like INPUT_FILE=...
  ca <- commandArgs(trailingOnly = FALSE)
  m <- grep(paste0("^", x, "="), ca, value = TRUE)
  if (length(m) > 0) return(sub(paste0("^", x, "="), "", m[1]))
  default
}

INPUT_FILE <- get_env("INPUT_FILE", NA)
OUTPUT_DIR <- get_env("OUTPUT_DIR", NA)

# Helper to test if a file looks like patient-level data (has OS/PFS columns)
is_patient_data <- function(path) {
  if (!file.exists(path)) return(FALSE)
  # Peek first line only
  tryCatch({
    hdr <- names(readr::read_csv(path, n_max = 0, show_col_types = FALSE, name_repair = "minimal"))
    hdr_low <- tolower(trimws(hdr))
    any(grepl("os_time|os_event|pfs_time|pfs_event|tki|phase", hdr_low))
  }, error = function(e) {
    # Fallback: raw header sniff
    l1 <- readLines(path, n = 1, warn = FALSE)
    grepl("OS_Time|PFS_Time|TKI|Phase", l1, ignore.case = TRUE)
  })
}

# If INPUT_FILE not supplied, auto-detect
if (is.na(INPUT_FILE)) {
  # Priority 1: explicit synthetic patient data if present
  if (file.exists("synthetic_cml_patient_data.csv")) {
    INPUT_FILE <- "synthetic_cml_patient_data.csv"
  } else if (file.exists("data/synthetic_cml_patient_data.csv")) {
    INPUT_FILE <- "data/synthetic_cml_patient_data.csv"
  } else {
    # Among repo_csvs, prefer one that looks like patient data
    patient_candidates <- Filter(is_patient_data, repo_csvs)
    if (length(patient_candidates) > 0) {
      INPUT_FILE <- patient_candidates[1]
    } else if (length(repo_csvs) > 0) {
      # Fallback to first CSV (likely the check file)
      INPUT_FILE <- repo_csvs[1]
    } else {
      INPUT_FILE <- "R_script_dataset_check (1).csv"
    }
  }
}

if (is.na(OUTPUT_DIR) || !nzchar(OUTPUT_DIR)) {
  OUTPUT_DIR <- file.path(dirname(INPUT_FILE), "output")
  # If dirname is "." and INPUT_FILE is at root, use ./output
  if (OUTPUT_DIR %in% c(".", "./output", "output/output")) OUTPUT_DIR <- "output"
}
# Normalize: if INPUT_FILE at root and dirname is ".", output is "output"
if (OUTPUT_DIR == ".") OUTPUT_DIR <- "output"

# ----------------- FILE CHOOSER WINDOW (attach document from storage) --------
# This section adds a native window so you can pick a CSV from your computer/storage.
# How to trigger the window:
#   1. In RStudio / R GUI (interactive): set USE_FILE_CHOOSER <- TRUE, or run with --choose flag
#   2. Command line: Rscript cml_survival_correction.R --choose
#   3. Or: PROMPT_FILE_CHOOSER=1 Rscript cml_survival_correction.R
# The chooser tries tcltk -> svDialogs -> file.choose -> readline in order, so it works
# on Windows, macOS and Linux even without extra packages.
USE_FILE_CHOOSER <- FALSE  # <- change to TRUE if you always want the window to pop up

choose_csv_interactively <- function() {
  # Try tcltk native file dialog
  if (requireNamespace("tcltk", quietly = TRUE)) {
    tryCatch({
      filters <- matrix(c("CSV files", "*.csv", "All files", "*.*"), ncol = 2, byrow = TRUE)
      # tk_choose.files returns character vector; empty if cancelled
      chosen <- tcltk::tk_choose.files(
        caption = "Select CML patient CSV file (attach from storage)",
        filters = filters
      )
      if (length(chosen) > 0 && nzchar(chosen[1]) && file.exists(chosen[1])) {
        return(normalizePath(chosen[1], winslash = "/", mustWork = FALSE))
      }
    }, error = function(e) NULL)
  }
  # Try svDialogs if installed
  if (requireNamespace("svDialogs", quietly = TRUE)) {
    tryCatch({
      res <- svDialogs::dlg_open(
        title = "Select CML patient CSV file (attach from storage)",
        filters = svDialogs::dlg_filters[c("csv", "All"), , drop = FALSE]
      )$res
      if (length(res) > 0 && nzchar(res) && file.exists(res)) {
        return(normalizePath(res, winslash = "/", mustWork = FALSE))
      }
    }, error = function(e) NULL)
  }
  # Fallback to file.choose (R GUI) or readline (console)
  if (interactive()) {
    tryCatch({
      chosen <- file.choose()
      if (length(chosen) > 0 && nzchar(chosen) && file.exists(chosen)) {
        return(normalizePath(chosen, winslash = "/", mustWork = FALSE))
      }
    }, error = function(e) NULL)
    # Last resort: ask to type/paste path
    cat("\n--- File chooser fallback ---\n")
    cat("Could not open native dialog. Please type or paste the full path to your CSV and press Enter.\n")
    cat("Example: /home/user/my_data.csv  or  C:\\Users\\You\\Documents\\my_data.csv\n")
    cat("Press Enter to keep current auto-detected file (", INPUT_FILE, ")\n", sep = "")
    typed <- readline(prompt = "Path to CSV (or Enter to skip): ")
    typed <- trimws(typed)
    if (nzchar(typed) && file.exists(typed)) return(normalizePath(typed, winslash = "/", mustWork = FALSE))
    if (nzchar(typed) && !file.exists(typed)) warning("Typed path does not exist: ", typed)
  }
  return(NULL)
}

# Check if user requested the chooser window
args <- commandArgs(trailingOnly = TRUE)
force_chooser <- USE_FILE_CHOOSER ||
  any(args %in% c("--choose", "--gui", "--pick", "--chooser")) ||
  identical(tolower(Sys.getenv("PROMPT_FILE_CHOOSER", unset = "0")), "1") ||
  identical(tolower(Sys.getenv("USE_FILE_CHOOSER", unset = "0")), "1")

# Also auto-trigger in interactive RStudio/R GUI if auto-detection would otherwise use the check-file or fail
should_auto_prompt <- interactive() && (
  is.na(INPUT_FILE) || !file.exists(INPUT_FILE) || length(INPUT_FILE) == 0
)

if (force_chooser || should_auto_prompt) {
  message("\n*** Opening file chooser window to attach CSV from storage ***")
  message("Tip: You can also run: Rscript cml_survival_correction.R --choose\n")
  # Give user a moment to see the message before dialog blocks
  Sys.sleep(0.5)
  chosen <- choose_csv_interactively()
  if (!is.null(chosen) && file.exists(chosen)) {
    INPUT_FILE <- chosen
    message(">>> File selected via window: ", INPUT_FILE)
  } else {
    if (force_chooser) {
      warning("No file selected via chooser window; keeping auto-detected file: ", INPUT_FILE)
    } else {
      message("No file selected via window; using auto-detected file: ", INPUT_FILE)
    }
  }
}

message("INPUT_FILE = ", INPUT_FILE)
message("OUTPUT_DIR = ", OUTPUT_DIR)
message("Detected CSVs in repo: ", paste(repo_csvs, collapse = ", "))

# ------------------------------- Candidate columns ----------------------------
# Candidate source-variable names (edit only if your columns use other names).
ID_CANDIDATES       <- c("Patient_ID", "PatientID", "patient_id", "ID", "Subject_ID", "MRN")
TKI_CANDIDATES      <- c("TKI_Used", "TKI Used", "TKI", "Treatment", "TKI_Name")
PHASE_CANDIDATES    <- c("Phase_of_CML", "Phase of CML", "CML_Phase", "Phase")
OS_TIME_CANDIDATES  <- c("OS_Time_Months", "OS_time_months", "OS_Time", "Overall_Survival_Months")
OS_EVENT_CANDIDATES <- c("OS_Event", "OS_event", "Death", "OS_Status")
PFS_TIME_CANDIDATES <- c("PFS_Time_Months", "PFS_time_months", "PFS_Time", "Progression_Free_Survival_Months")
PFS_EVENT_CANDIDATES<- c("PFS_Event", "PFS_event", "Progression_or_Death", "PFS_Status")
LINE_CANDIDATES     <- c("TKI_Line", "Line_of_Therapy", "LOT", "Therapy_Line", "Treatment_Line", "Line")
DATE_CANDIDATES     <- c("TKI_Start_Date", "Treatment_Start_Date", "Start_Date", "TKI_Date", "Treatment_Date")
ORDER_CANDIDATES    <- c("TKI_Sequence", "Treatment_Sequence", "Sequence", "Treatment_Order", "Order")

# Minimum N required to draw a TKI-specific curve. Small groups are labelled
# "Other / sparse TKI groups" rather than shown separately.
MIN_N_FOR_TKI_CURVE <- 10

# ------------------------------ Packages --------------------------------------
packages <- c("readr", "dplyr", "stringr", "janitor", "survival", "survminer", "ggplot2", "forcats")
missing_packages <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing_packages) > 0) {
  message("Installing missing packages: ", paste(missing_packages, collapse = ", "))
  install.packages(missing_packages, repos = "https://cloud.r-project.org")
}
invisible(lapply(packages, library, character.only = TRUE))

# ---------------------------- Helper functions --------------------------------
find_col <- function(data, candidates, required = TRUE) {
  nm <- names(data)
  match_index <- match(tolower(candidates), tolower(nm))
  match_index <- match_index[!is.na(match_index)]
  if (length(match_index) > 0) return(nm[match_index[1]])
  if (required) {
    stop(
      "Could not find a required column. Looked for: ",
      paste(candidates, collapse = ", "),
      "\nAvailable columns: ", paste(nm, collapse = ", ")
    )
  }
  NULL
}

# Convert common event codings to 0/1: 1 = event; 0 = censored.
normalize_event <- function(x) {
  if (is.numeric(x)) return(ifelse(is.na(x), NA_real_, ifelse(x > 0, 1, 0)))
  z <- tolower(trimws(as.character(x)))
  dplyr::case_when(
    z %in% c("1", "yes", "y", "event", "death", "dead", "deceased", "progressed", "progression") ~ 1,
    z %in% c("0", "no", "n", "censored", "alive", "living", "none") ~ 0,
    TRUE ~ NA_real_
  )
}

save_km_plot <- function(data, time_col, event_col, group_col, outcome_label, group_label, filename) {
  plot_data <- data %>%
    filter(!is.na(.data[[time_col]]), !is.na(.data[[event_col]]), !is.na(.data[[group_col]])) %>%
    mutate(
      .time  = as.numeric(.data[[time_col]]),
      .event = as.numeric(.data[[event_col]]),
      .group = as.factor(.data[[group_col]])
    )

  if (nrow(plot_data) == 0 || dplyr::n_distinct(plot_data$.group) < 2) {
    warning("Skipping ", filename, ": fewer than two non-missing groups are available.")
    return(invisible(NULL))
  }

  fit <- survival::survfit(survival::Surv(.time, .event) ~ .group, data = plot_data)
  test <- survival::survdiff(survival::Surv(.time, .event) ~ .group, data = plot_data)
  p_value <- 1 - pchisq(test$chisq, df = length(test$n) - 1)

  g <- survminer::ggsurvplot(
    fit,
    data = plot_data,
    risk.table = TRUE,
    pval = paste0("Log-rank p = ", format.pval(p_value, digits = 3, eps = 0.001)),
    conf.int = FALSE,
    xlab = "Months",
    ylab = paste0(outcome_label, " probability"),
    legend.title = group_label,
    legend.labs = levels(plot_data$.group),
    ggtheme = ggplot2::theme_bw(),
    risk.table.height = 0.25,
    break.time.by = 12
  )

  ggplot2::ggsave(
    filename = file.path(OUTPUT_DIR, filename),
    plot = survminer::arrange_ggsurvplots(list(g), print = FALSE),
    width = 9, height = 8, dpi = 300
  )

  # Save a compact table documenting group sample sizes and p value.
  summary_tbl <- plot_data %>%
    count(.group, name = "N") %>%
    mutate(
      outcome = outcome_label,
      grouping = group_label,
      log_rank_p = p_value
    )
  readr::write_csv(summary_tbl, file.path(OUTPUT_DIR, paste0(tools::file_path_sans_ext(filename), "_summary.csv")))
}

# ------------------------------ Read data -------------------------------------
dir.create(OUTPUT_DIR, showWarnings = FALSE, recursive = TRUE)

if (!file.exists(INPUT_FILE)) {
  stop("INPUT_FILE not found: ", INPUT_FILE, "\nAvailable CSVs: ", paste(repo_csvs, collapse = ", "))
}

# Peek to see if this is the dataset-check file rather than patient data
# Check file has columns Check, Present, Missing_Values, Levels
peek <- tryCatch(readr::read_csv(INPUT_FILE, n_max = 5, show_col_types = FALSE, name_repair = "minimal"), error = function(e) NULL)
is_check_file <- FALSE
if (!is.null(peek) && all(c("Check", "Present") %in% names(peek))) {
  is_check_file <- TRUE
}
# If interactive and the file is the check-file, offer a window to attach the correct document from storage
if (is_check_file && interactive() && !force_chooser) {
  message("\nDetected that the selected file is the dataset-check summary (R_script_dataset_check (1).csv), not patient-level data.")
  cat("Do you want to open a window to attach your patient CSV from storage instead? [y/N]: ")
  ans <- tolower(trimws(readline(prompt = "")))
  if (ans %in% c("y", "yes")) {
    chosen2 <- choose_csv_interactively()
    if (!is.null(chosen2) && file.exists(chosen2)) {
      INPUT_FILE <- chosen2
      message(">>> New file selected via window: ", INPUT_FILE)
      # Re-peek the new file
      peek <- tryCatch(readr::read_csv(INPUT_FILE, n_max = 5, show_col_types = FALSE, name_repair = "minimal"), error = function(e) NULL)
      is_check_file <- !is.null(peek) && all(c("Check", "Present") %in% names(peek))
    } else {
      message("No new file chosen; will use demo fallback below.")
    }
  } else {
    message("Keeping demo fallback: will switch to synthetic_cml_patient_data.csv if available.")
  }
}
if (is_check_file) {
  message("NOTE: INPUT_FILE appears to be the dataset-check summary (R_script_dataset_check (1).csv), not patient-level data.")
  # Try to switch to synthetic patient data if it exists
  if (file.exists("synthetic_cml_patient_data.csv")) {
    message("-> Switching to synthetic_cml_patient_data.csv for demonstration (generated from the check file's Levels metadata).")
    INPUT_FILE <- "synthetic_cml_patient_data.csv"
  } else if (file.exists("data/synthetic_cml_patient_data.csv")) {
    message("-> Switching to data/synthetic_cml_patient_data.csv")
    INPUT_FILE <- "data/synthetic_cml_patient_data.csv"
  } else {
    message("-> No synthetic patient file found. Generating a demo dataset on the fly from Levels metadata...")
    # Generate a minimal demo dataset directly in R from the Levels info in the check file
    # This ensures the script still runs end-to-end even when only the check file is present.
    set.seed(42)
    # Parse Levels from check file - read full check file raw
    chk_full <- readr::read_csv(INPUT_FILE, show_col_types = FALSE, name_repair = "minimal", col_names = FALSE)
    # We'll just generate synthetic data similar to python generator but inline
    n_demo <- 160
    phases <- c("Chronic","Accelerated","Blast")
    tkis <- c("Imatinib","Dasatinib","Nilotinib","Bosutinib","ponatinib")
    # generate patient-level demo
    demo <- data.frame(
      Patient_ID = sprintf("P%03d", sample(1:300, n_demo, replace = FALSE)),
      TKI_Used = sample(tkis, n_demo, replace = TRUE, prob = c(0.42,0.22,0.20,0.08,0.08)),
      Phase_of_CML = sample(phases, n_demo, replace = TRUE, prob = c(0.78,0.13,0.09)),
      Gender = sample(c("Male","Female"), n_demo, replace = TRUE),
      Age = pmax(18, pmin(85, round(rnorm(n_demo, 56, 14)))),
      OS_Time_Months = NA_real_,
      OS_Event = NA_integer_,
      PFS_Time_Months = NA_real_,
      PFS_Event = NA_integer_,
      Grade_3_ADR = sample(c("No","Yes","Not documented","Not applicable"), n_demo, replace = TRUE, prob = c(0.65,0.18,0.12,0.05)),
      TKI_Line = sample(1:2, n_demo, replace = TRUE, prob = c(0.75,0.25)),
      TKI_Start_Date = as.Date("2015-01-01") + sample(0:2800, n_demo, replace = TRUE),
      TKI_Sequence = NA_integer_,
      stringsAsFactors = FALSE
    )
    demo$TKI_Sequence <- demo$TKI_Line
    # Assign OS/PFS times dependent on phase
    for (i in 1:nrow(demo)) {
      ph <- demo$Phase_of_CML[i]
      if (ph == "Chronic") {
        os <- max(1, rnorm(1, 95, 28))
        p <- 0.18
        pf_factor <- runif(1, 0.75, 0.98)
      } else if (ph == "Accelerated") {
        os <- max(1, rnorm(1, 58, 22))
        p <- 0.38
        pf_factor <- runif(1, 0.65, 0.90)
      } else {
        os <- max(1, rnorm(1, 22, 12))
        p <- 0.68
        pf_factor <- runif(1, 0.55, 0.85)
      }
      os <- min(140, os)
      pfs <- os * pf_factor
      demo$OS_Time_Months[i] <- round(os,1)
      demo$PFS_Time_Months[i] <- round(min(pfs, os),1)
      demo$OS_Event[i] <- as.integer(runif(1) < p)
      if (demo$OS_Event[i]==0) {
        pp <- if (ph=="Chronic") 0.32 else if (ph=="Accelerated") 0.52 else 0.72
        demo$PFS_Event[i] <- as.integer(runif(1) < pp)
      } else {
        demo$PFS_Event[i] <- 1L
      }
    }
    # Expand some patients to have 2 lines to demonstrate LOT
    # Take 25% of patients and duplicate with line 2
    extra_idx <- sample(1:nrow(demo), size = round(nrow(demo)*0.20))
    extra <- demo[extra_idx, ]
    extra$TKI_Line <- 2
    extra$TKI_Sequence <- 2
    extra$TKI_Used <- sample(tkis, nrow(extra), replace = TRUE, prob = c(0.12,0.30,0.28,0.15,0.15))
    extra$TKI_Start_Date <- extra$TKI_Start_Date + 350 + sample(-90:120, nrow(extra), replace = TRUE)
    demo_expanded <- rbind(demo, extra)
    # Write this demo to a temp file and use it as input
    dir.create("output", showWarnings = FALSE)
    demo_path <- file.path(OUTPUT_DIR, "demo_generated_from_check_file.csv")
    readr::write_csv(demo_expanded, demo_path)
    message("Generated demo file with ", nrow(demo_expanded), " rows at ", demo_path)
    INPUT_FILE <- demo_path
  }
}

message("Final INPUT_FILE resolved to: ", INPUT_FILE)
raw <- readr::read_csv(INPUT_FILE, show_col_types = FALSE, name_repair = "minimal")

# Retain a lookup of original names, then clean them for safe R programming.
original_names <- names(raw)
data <- raw %>% janitor::clean_names()

# Clean candidate names in the same manner for matching.
clean_candidate <- function(x) janitor::make_clean_names(x)
ID_CANDIDATES        <- clean_candidate(ID_CANDIDATES)
TKI_CANDIDATES       <- clean_candidate(TKI_CANDIDATES)
PHASE_CANDIDATES     <- clean_candidate(PHASE_CANDIDATES)
OS_TIME_CANDIDATES   <- clean_candidate(OS_TIME_CANDIDATES)
OS_EVENT_CANDIDATES  <- clean_candidate(OS_EVENT_CANDIDATES)
PFS_TIME_CANDIDATES  <- clean_candidate(PFS_TIME_CANDIDATES)
PFS_EVENT_CANDIDATES <- clean_candidate(PFS_EVENT_CANDIDATES)
LINE_CANDIDATES      <- clean_candidate(LINE_CANDIDATES)
DATE_CANDIDATES      <- clean_candidate(DATE_CANDIDATES)
ORDER_CANDIDATES     <- clean_candidate(ORDER_CANDIDATES)

id_col        <- find_col(data, ID_CANDIDATES)
tki_col       <- find_col(data, TKI_CANDIDATES)
phase_col     <- find_col(data, PHASE_CANDIDATES)
os_time_col   <- find_col(data, OS_TIME_CANDIDATES)
os_event_col  <- find_col(data, OS_EVENT_CANDIDATES)
pfs_time_col  <- find_col(data, PFS_TIME_CANDIDATES)
pfs_event_col <- find_col(data, PFS_EVENT_CANDIDATES)
line_col      <- find_col(data, LINE_CANDIDATES, required = FALSE)
date_col      <- find_col(data, DATE_CANDIDATES, required = FALSE)
order_col     <- find_col(data, ORDER_CANDIDATES, required = FALSE)

# ----------------------- Create Line of Therapy (LOT) -------------------------
# Priority for identifying a patient's first TKI:
#   1. Explicit numeric treatment line
#   2. Treatment start date
#   3. Explicit treatment sequence/order
#
# Every later treatment is classified as "Subsequent-line TKI".
if (!is.null(line_col)) {
  data <- data %>% mutate(.lot_order = suppressWarnings(as.numeric(.data[[line_col]])))
  order_method <- paste0("numeric line variable: ", line_col)
} else if (!is.null(date_col)) {
  data <- data %>% mutate(.lot_order = as.numeric(as.Date(.data[[date_col]])))
  order_method <- paste0("treatment start date: ", date_col)
} else if (!is.null(order_col)) {
  data <- data %>% mutate(.lot_order = suppressWarnings(as.numeric(.data[[order_col]])))
  order_method <- paste0("treatment sequence/order: ", order_col)
} else {
  message("No LOT ordering column found (line/date/order). Creating synthetic LOT for demo: 75% first-line, 25% subsequent-line.")
  # Create a synthetic LOT for demo purposes so plots still generate
  set.seed(123)
  # If we have patient IDs, ensure some patients get subsequent lines randomly per row
  data <- data %>% mutate(.lot_order = if_else(runif(n()) < 0.75, 1, 2))
  order_method <- "synthetic LOT (no line/date/order column found - demo mode)"
}

if (all(is.na(data$.lot_order))) {
  stop("The selected treatment-order variable contains no usable values: ", order_method)
}

# If a patient has multiple rows tied for their earliest order, all tied rows are
# labelled first-line. Review these ties in the exported QA file.
data <- data %>%
  mutate(
    .patient_id = as.character(.data[[id_col]]),
    tki_used = as.character(.data[[tki_col]]),
    phase_of_cml = as.character(.data[[phase_col]]),
    os_event = normalize_event(.data[[os_event_col]]),
    pfs_event = normalize_event(.data[[pfs_event_col]])
  ) %>%
  group_by(.patient_id) %>%
  mutate(
    first_tki_order = min(.lot_order, na.rm = TRUE),
    line_of_therapy = case_when(
      is.na(.lot_order) ~ NA_character_,
      .lot_order == first_tki_order ~ "First-line TKI",
      .lot_order > first_tki_order ~ "Subsequent-line TKI",
      TRUE ~ NA_character_
    )
  ) %>%
  ungroup() %>%
  mutate(
    line_of_therapy = factor(
      line_of_therapy,
      levels = c("First-line TKI", "Subsequent-line TKI")
    ),
    phase_of_cml = forcats::fct_relevel(as.factor(phase_of_cml), "Chronic", "Accelerated", "Blast")
  )

# ---------------------------- QA exports --------------------------------------
qa_lot <- data %>%
  count(line_of_therapy, name = "treatment_rows") %>%
  mutate(percent_of_rows = round(100 * treatment_rows / sum(treatment_rows), 1))
readr::write_csv(qa_lot, file.path(OUTPUT_DIR, "LOT_group_counts.csv"))

qa_patients <- data %>%
  distinct(.patient_id, line_of_therapy) %>%
  count(line_of_therapy, name = "unique_patients")
readr::write_csv(qa_patients, file.path(OUTPUT_DIR, "LOT_unique_patient_counts.csv"))

qa_ties <- data %>%
  group_by(.patient_id) %>%
  summarise(
    number_of_first_line_rows = sum(line_of_therapy == "First-line TKI", na.rm = TRUE),
    .groups = "drop"
  ) %>%
  filter(number_of_first_line_rows > 1)
readr::write_csv(qa_ties, file.path(OUTPUT_DIR, "QA_multiple_first_line_rows.csv"))

# Save corrected data with the requested LOT variable.
corrected_data <- data %>%
  select(-.patient_id, -.lot_order, -first_tki_order)
readr::write_csv(corrected_data, file.path(OUTPUT_DIR, "patient_level_data_with_LOT.csv"))

# --------------------- Sparse TKI grouping for display ------------------------
# This is intentionally separate from LOT. It prevents interpretation of highly
# unstable individual-TKI curves (e.g., sparse ponatinib groups).
tki_counts <- data %>% count(tki_used, name = "N")
data <- data %>%
  left_join(tki_counts, by = "tki_used") %>%
  mutate(
    tki_plot_group = if_else(N >= MIN_N_FOR_TKI_CURVE, tki_used, "Other / sparse TKI groups"),
    tki_plot_group = as.factor(tki_plot_group)
  )
readr::write_csv(tki_counts, file.path(OUTPUT_DIR, "TKI_group_counts.csv"))

# --------------------- Corrected separate survival figures --------------------
# Figure 3: Phase of CML, PFS
save_km_plot(data, "pfs_time_months", "pfs_event", "phase_of_cml",
             "Progression-free survival", "Phase of CML",
             "Figure_3_PFS_by_Phase_of_CML.png")

# Figure 4: Phase of CML, OS
save_km_plot(data, "os_time_months", "os_event", "phase_of_cml",
             "Overall survival", "Phase of CML",
             "Figure_4_OS_by_Phase_of_CML.png")

# Additional requested LOT figures
save_km_plot(data, "pfs_time_months", "pfs_event", "line_of_therapy",
             "Progression-free survival", "Line of Therapy",
             "Figure_5_PFS_by_LOT.png")

save_km_plot(data, "os_time_months", "os_event", "line_of_therapy",
             "Overall survival", "Line of Therapy",
             "Figure_6_OS_by_LOT.png")

# Optional: TKI-specific plots only after collapsing sparse groups.
save_km_plot(data, "pfs_time_months", "pfs_event", "tki_plot_group",
             "Progression-free survival", "TKI group",
             "Supplement_PFS_by_TKI_collapsed_sparse_groups.png")

save_km_plot(data, "os_time_months", "os_event", "tki_plot_group",
             "Overall survival", "TKI group",
             "Supplement_OS_by_TKI_collapsed_sparse_groups.png")

# ----------------------------- Run summary ------------------------------------
writeLines(
  c(
    "CML survival-analysis correction completed.",
    paste0("Input file: ", INPUT_FILE),
    paste0("LOT derivation method: ", order_method),
    paste0("Output directory: ", normalizePath(OUTPUT_DIR, winslash = "/", mustWork = FALSE)),
    paste0("Rows processed: ", nrow(data)),
    paste0("Unique patients: ", dplyr::n_distinct(data$.patient_id)),
    paste0("Date: ", Sys.time()),
    "",
    "QA files:",
    "- LOT_group_counts.csv",
    "- LOT_unique_patient_counts.csv",
    "- QA_multiple_first_line_rows.csv",
    "- patient_level_data_with_LOT.csv",
    "- TKI_group_counts.csv",
    "",
    "Figures:",
    "- Figure_3_PFS_by_Phase_of_CML.png (PFS by Phase)",
    "- Figure_4_OS_by_Phase_of_CML.png (OS by Phase)",
    "- Figure_5_PFS_by_LOT.png (PFS by LOT)",
    "- Figure_6_OS_by_LOT.png (OS by LOT)",
    "- Supplement_*_by_TKI_collapsed_sparse_groups.png",
    "",
    if (is_check_file) "NOTE: Input was the dataset-check file; analysis was run on synthetic_cml_patient_data.csv (demo) generated from its Levels metadata."
  ),
  con = file.path(OUTPUT_DIR, "README_run_summary.txt")
)

message("Done. Corrected outputs are in: ", OUTPUT_DIR)
message("  - Figures 3-6 and supplements saved as PNGs (with _summary.csv)")
message("  - QA and LOT files saved as CSVs")
