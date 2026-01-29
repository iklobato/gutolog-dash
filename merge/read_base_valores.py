"""Read BASE_VALORES.xlsx and return DataFrames for merge."""

from pathlib import Path

import pandas as pd

from .vehicle_mapping import CANONICAL_VEHICLES, normalize_vehicle


def read_base_valores(path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read BASE_VALORES.xlsx.

    Returns:
        (main_df, context_df):
        - main_df: rows (vehicle_type, km_inicial, km_final, km_total, ...metrics)
        - context_df: one row with dias_uteis, etc.
    """
    path = Path(path)
    xl = pd.ExcelFile(path, engine="openpyxl")

    # ---- Context: VIAGEM (dias úteis) ----
    df_viagem = pd.read_excel(xl, sheet_name="VIAGEM", header=None)
    dias_uteis = None
    for _, row in df_viagem.iterrows():
        if row.iloc[0] == "DIAS ÚTEIS:":
            try:
                dias_uteis = int(float(row.iloc[1]))
            except (ValueError, TypeError):
                pass
            break
    context_df = pd.DataFrame([{"dias_uteis": dias_uteis or 24}])

    # ---- Vehicle-level metrics (unpivot cost sheets) ----
    cost_sheets = [
        "PATRIMÔNIO + CAPITAL",
        "TAXAS E IMPOSTOS",
        "LICENÇAS E CERTIFICAÇÕES",
        "GERENCIAMENTO DE RISCO",
        "SEGURO - FROTA",
        "MANUTENÇÃO+PNEUS",
        "MÃO DE OBRA + %",
        "COMBUSTÍVEL",
    ]
    sheet_prefix = {
        "PATRIMÔNIO + CAPITAL": "patrimonio_",
        "TAXAS E IMPOSTOS": "taxas_",
        "LICENÇAS E CERTIFICAÇÕES": "licencas_",
        "GERENCIAMENTO DE RISCO": "risco_",
        "SEGURO - FROTA": "seguro_",
        "MANUTENÇÃO+PNEUS": "manutencao_",
        "MÃO DE OBRA + %": "mao_obra_",
        "COMBUSTÍVEL": "combustivel_",
    }
    vehicle_metrics: list[dict] = []

    for sheet in cost_sheets:
        if sheet not in xl.sheet_names:
            continue
        df = pd.read_excel(xl, sheet_name=sheet, header=None)
        if df.empty or df.shape[1] < 2:
            continue
        # Row 0: first col is category name, rest are vehicle names
        header_row = df.iloc[0]
        vehicle_cols = []
        for c in range(1, len(header_row)):
            v = header_row.iloc[c]
            if pd.notna(v) and isinstance(v, str) and v.strip() in CANONICAL_VEHICLES:
                vehicle_cols.append((c, v.strip()))
        if not vehicle_cols:
            continue
        prefix = sheet_prefix.get(sheet, "").replace(" ", "_").lower()
        for r in range(1, len(df)):
            metric_label = df.iloc[r, 0]
            if pd.isna(metric_label) or str(metric_label).strip() == "":
                continue
            metric_name = f"{prefix}{_slug(str(metric_label))}"
            for col_idx, vehicle in vehicle_cols:
                val = df.iloc[r, col_idx]
                try:
                    num = float(val) if pd.notna(val) and str(val).strip() != "" else None
                except (ValueError, TypeError):
                    num = None
                if num is not None:
                    vehicle_metrics.append(
                        {"vehicle_type": vehicle, "metric": metric_name, "value": num}
                    )

    # Pivot vehicle-level metrics to columns (one row per vehicle, no KM yet)
    if vehicle_metrics:
        df_v = pd.DataFrame(vehicle_metrics)
        vehicle_pivot = df_v.pivot_table(
            index="vehicle_type", columns="metric", values="value", aggfunc="first"
        ).reset_index()
    else:
        vehicle_pivot = pd.DataFrame({"vehicle_type": CANONICAL_VEHICLES})

    # ---- RELAÇÃO % FRETE IDA: KM bands × vehicle ----
    df_rel = pd.read_excel(xl, sheet_name="RELAÇÃO % FRETE IDA", header=0)
    if "KM INICIAL" not in df_rel.columns or "KM FINAL" not in df_rel.columns:
        # Fallback: first two columns as km_inicial, km_final
        df_rel = pd.read_excel(xl, sheet_name="RELAÇÃO % FRETE IDA", header=None)
        df_rel.columns = [str(i) for i in range(len(df_rel.columns))]
        df_rel = df_rel.rename(columns={"0": "KM INICIAL", "1": "KM FINAL"})
    km_cols = [c for c in df_rel.columns if c in CANONICAL_VEHICLES]
    if not km_cols:
        # Try column names from first row
        rel_raw = pd.read_excel(xl, sheet_name="RELAÇÃO % FRETE IDA", header=None)
        if len(rel_raw.columns) >= 2:
            rel_raw = rel_raw.rename(columns={0: "KM INICIAL", 1: "KM FINAL"})
            for c in range(2, len(rel_raw.columns)):
                v = rel_raw.iloc[0, c]
                if pd.notna(v) and str(v).strip() in CANONICAL_VEHICLES:
                    rel_raw = rel_raw.rename(columns={c: str(v).strip()})
            df_rel = rel_raw.iloc[1:].copy()
            df_rel["KM INICIAL"] = pd.to_numeric(df_rel["KM INICIAL"], errors="coerce")
            df_rel["KM FINAL"] = pd.to_numeric(df_rel["KM FINAL"], errors="coerce")
            km_cols = [c for c in df_rel.columns if c in CANONICAL_VEHICLES]

    rows_rel: list[dict] = []
    for _, row in df_rel.iterrows():
        try:
            km_i = float(row["KM INICIAL"])
            km_f = float(row["KM FINAL"])
        except (TypeError, ValueError):
            continue
        if pd.isna(km_i) or pd.isna(km_f):
            continue
        km_total = km_f - km_i + 1 if km_f >= km_i else 0
        for v in km_cols:
            val = row.get(v)
            try:
                pct = float(val) if pd.notna(val) else None
            except (ValueError, TypeError):
                pct = None
            if pct is not None:
                rows_rel.append(
                    {
                        "vehicle_type": v,
                        "km_inicial": km_i,
                        "km_final": km_f,
                        "km_total": km_total,
                        "pct_frete_ida": pct,
                    }
                )

    if not rows_rel:
        # Build minimal km bands from sheet
        rel_raw = pd.read_excel(xl, sheet_name="RELAÇÃO % FRETE IDA", header=None)
        for r in range(1, len(rel_raw)):
            try:
                km_i = float(rel_raw.iloc[r, 0])
                km_f = float(rel_raw.iloc[r, 1])
            except (TypeError, ValueError):
                continue
            for c in range(2, min(rel_raw.shape[1], 2 + len(CANONICAL_VEHICLES))):
                v = rel_raw.iloc[0, c]
                if pd.notna(v) and str(v).strip() in CANONICAL_VEHICLES:
                    val = rel_raw.iloc[r, c]
                    try:
                        pct = float(val) if pd.notna(val) else None
                    except (ValueError, TypeError):
                        pct = None
                    if pct is not None:
                        rows_rel.append(
                            {
                                "vehicle_type": str(v).strip(),
                                "km_inicial": km_i,
                                "km_final": km_f,
                                "km_total": km_f - km_i + 1,
                                "pct_frete_ida": pct,
                            }
                        )
    df_rel_long = pd.DataFrame(rows_rel)

    # ---- Combine: for each (vehicle, km_band) add vehicle-level metrics ----
    if not df_rel_long.empty:
        main_bv = df_rel_long.merge(vehicle_pivot, on="vehicle_type", how="left")
    else:
        # No KM bands: create one dummy band per vehicle so we still have vehicle metrics
        main_bv = vehicle_pivot.copy()
        main_bv["km_inicial"] = 0
        main_bv["km_final"] = 0
        main_bv["km_total"] = 0
    main_bv["source"] = "BASE_VALORES"
    return main_bv, context_df


def _slug(s: str) -> str:
    return (
        s.lower()
        .replace(" ", "_")
        .replace("%", "pct")
        .replace("/", "_")
        .replace("(", "")
        .replace(")", "")
        .replace("-", "_")
        .replace(":", "")
        .replace(".", "")
    )[:50]
