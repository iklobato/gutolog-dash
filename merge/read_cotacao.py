"""Read COTAÇÃO_LOTAÇÃO.xlsm and return DataFrames for merge."""

from pathlib import Path

import pandas as pd

from .vehicle_mapping import TO_CANONICAL, normalize_vehicle


def read_cotacao(path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read COTAÇÃO_LOTAÇÃO.xlsm.

    Returns:
        (main_df, context_df):
        - main_df: (vehicle_type, km_inicial, km_final, km_total, frete_peso_total_cotacao, ...)
        - context_df: numero_cotacao, data, cliente, etc.
    """
    path = Path(path)
    xl = pd.ExcelFile(path, engine="openpyxl")

    # ---- Context from COTAÇÃO sheet ----
    df_cot = pd.read_excel(xl, sheet_name="COTAÇÃO", header=None)
    context: dict = {}
    for r in range(min(20, len(df_cot))):
        label = df_cot.iloc[r, 0]
        val = df_cot.iloc[r, 1] if df_cot.shape[1] > 1 else None
        if pd.notna(label):
            s = str(label).strip()
            if s == "Nº" and r + 1 <= len(df_cot):
                context["numero_cotacao"] = str(df_cot.iloc[r, 2]) if pd.notna(df_cot.iloc[r, 2]) else None
            elif s == "Data:" and pd.notna(val):
                context["data_cotacao"] = val
            elif s == "Revisão:" and pd.notna(df_cot.iloc[r, 3]):
                context["revisao"] = df_cot.iloc[r, 3]
            elif s == "Cliente:" and pd.notna(val):
                context["cliente"] = val
            elif s == "Origem:" and pd.notna(val):
                context["origem"] = val
            elif s == "Destino:" and pd.notna(val):
                context["destino"] = val
            elif "Km" in s and pd.notna(val):
                context["km_rota"] = val
    context_df = pd.DataFrame([context])

    # ---- BASE: vehicle-level (peso_maximo, diaria, valor_hora, eixos) ----
    df_base = pd.read_excel(xl, sheet_name="BASE", header=0)
    base_cols = [c for c in df_base.columns if "TIPOS" in str(c).upper() or "VEÍCULO" in str(c)]
    name_col = base_cols[0] if base_cols else df_base.columns[0]
    vehicle_base: list[dict] = []
    for _, row in df_base.iterrows():
        v_name = row.get(name_col)
        if pd.isna(v_name) or str(v_name).strip() in ("MERCADORIAS", "CARGA GERAL", "PRODUTO QUÍMICO", "MEDICAMENTOS", "ALIMENTOS"):
            continue
        v = normalize_vehicle(str(v_name).strip())
        if not v:
            v = str(v_name).strip()
        vehicle_base.append({
            "vehicle_type": v,
            "peso_maximo_cotacao": _num(row.get("PESO MÁXIMO")),
            "diaria_cotacao": _num(row.get("DIÁRIA")),
            "valor_hora_cotacao": _num(row.get("VALOR / HORA")),
            "eixos_cotacao": _num(row.get("EIXOS")),
        })
    df_vehicle_base = pd.DataFrame(vehicle_base)

    # ---- FRETE_PESO: KM bands × vehicle columns ----
    df_fp = pd.read_excel(xl, sheet_name="FRETE_PESO", header=None)
    if len(df_fp) < 2:
        main_cot = df_vehicle_base.copy() if not df_vehicle_base.empty else pd.DataFrame()
        if not main_cot.empty:
            main_cot["km_inicial"] = None
            main_cot["km_final"] = None
            main_cot["km_total"] = None
        return main_cot, context_df
    header_row = df_fp.iloc[1]
    # Col 0: FAIXA KM, 1: KM INICIAL, 2: KM FINAL, 3: KM TOTAL, 4+: vehicle columns
    long_rows: list[dict] = []
    for r in range(2, len(df_fp)):
        row = df_fp.iloc[r]
        try:
            km_i = float(row.iloc[1])
            km_f = float(row.iloc[2])
            km_t = float(row.iloc[3])
        except (TypeError, ValueError, IndexError):
            continue
        if pd.isna(km_i) or pd.isna(km_f):
            continue
        for c in range(4, min(len(header_row), len(row))):
            col_name = header_row.iloc[c]
            if pd.isna(col_name) or str(col_name).strip() == "":
                continue
            v = normalize_vehicle(str(col_name).strip())
            if v:
                val = _num(row.iloc[c])
                long_rows.append({
                    "vehicle_type": v,
                    "km_inicial": km_i,
                    "km_final": km_f,
                    "km_total": km_t,
                    "frete_peso_total_cotacao": val,
                })
    if long_rows:
        main_cot = pd.DataFrame(long_rows)
        main_cot = main_cot.merge(df_vehicle_base, on="vehicle_type", how="left")
    else:
        main_cot = df_vehicle_base.copy()
        main_cot["km_inicial"] = None
        main_cot["km_final"] = None
        main_cot["km_total"] = None
    main_cot["source"] = "COTAÇÃO"
    return main_cot, context_df


def _num(x) -> float | None:
    if pd.isna(x):
        return None
    try:
        return float(x)
    except (ValueError, TypeError):
        return None
