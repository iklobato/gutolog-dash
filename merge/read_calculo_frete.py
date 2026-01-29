"""Read CALCULO FRETE PESO.xlsx and return DataFrame for merge."""

from pathlib import Path

import pandas as pd

from .vehicle_mapping import normalize_vehicle

# Sheet name -> canonical vehicle (for per-vehicle sheets)
SHEET_TO_VEHICLE = {
    "FIORINO_CS": "FIORINO - CARGA SECA",
    "FIORINO_CS_AG": "FIORINO - CARGA SECA",
    "VAN_CS": "VAN - CARGA SECA",
    "LEVE_CS": "LEVE - CARGA SECA",
    "TOCO_CS": "TOCO - CARGA SECA",
    "TRUCK_CS": "TRUCK - CARGA SECA",
    "CTA5_CS": "CARRETA 5 EIXOS - CARGA SECA",
    "CTA6_CS": "CARRETA 6 EIXOS - CARGA SECA",
    "VAN_CR": "VAN - REFRIGERADA",
    "LEVE_CR": "LEVE - REFRIGERADO",
    "TOCO_CR": "TOCO - REFRIGERADO",
    "TRUCK_CR": "TRUCK - REFRIGERADO",
    "CTA5_CR": "CARRETA 5 EIXOS - REFRIGERADA",
    "CTA6_CR": "CARRETA 6 EIXOS - REFRIGERADA",
}


def read_calculo_frete(path: str | Path) -> pd.DataFrame:
    """Read CALCULO FRETE PESO.xlsx.

    Returns DataFrame with columns: vehicle_type, km_inicial, km_final, km_total,
    valor_dia_util, frete_peso_entrega, frete_peso_retorno, mensal, por_km, diario, etc.
    """
    path = Path(path)
    xl = pd.ExcelFile(path, engine="openpyxl")
    out_rows: list[dict] = []

    for sheet in xl.sheet_names:
        if sheet not in SHEET_TO_VEHICLE:
            continue
        vehicle = SHEET_TO_VEHICLE[sheet]
        df = pd.read_excel(xl, sheet_name=sheet, header=None)
        if df.shape[0] < 2 or df.shape[1] < 12:
            continue
        # Row 0: labels. Row 1+: data. Col 9,10,11 = KM INICIAL, KM FINAL, KM TOTAL (0-based)
        # Col 3,4,5 = TIPO, MENSAL, POR KM, DIÁRIO -> row 1 has values
        # Col 18,19 = FRETE PESO ENTREGA, FRETE PESO RETORNO (0-based)
        idx_km_inicial = 9
        idx_km_final = 10
        idx_km_total = 11
        idx_mensal = 4
        idx_por_km = 5
        idx_diario = 6
        idx_frete_entrega = 18
        idx_frete_retorno = 19
        idx_frete_viagem = 20
        for r in range(1, len(df)):
            row = df.iloc[r]
            try:
                km_i = float(row.iloc[idx_km_inicial])
                km_f = float(row.iloc[idx_km_final])
                km_t = float(row.iloc[idx_km_total])
            except (TypeError, ValueError, IndexError):
                continue
            if pd.isna(km_i) or pd.isna(km_f):
                continue
            d: dict = {
                "vehicle_type": vehicle,
                "km_inicial": km_i,
                "km_final": km_f,
                "km_total": km_t,
                "valor_dia_util_calculo": _num(row.iloc[idx_diario]),
                "mensal_calculo": _num(row.iloc[idx_mensal]),
                "por_km_calculo": _num(row.iloc[idx_por_km]),
                "frete_peso_entrega": _num(row.iloc[idx_frete_entrega]),
                "frete_peso_retorno": _num(row.iloc[idx_frete_retorno]),
                "frete_peso_viagem": _num(row.iloc[idx_frete_viagem]),
            }
            out_rows.append(d)

    if not out_rows:
        # Fallback: try FRETE PESO - GERAL (multi-level header)
        df_geral = pd.read_excel(xl, sheet_name="FRETE PESO - GERAL", header=None)
        if df_geral.shape[0] >= 4 and df_geral.shape[1] >= 5:
            # Row 1: FAIXA DE KM, KM INICIAL, KM FINAL, KM TOTAL, then triplets (valor, label, valor)
            # Row 2: vehicle names in triplets
            # Row 3: ENTREGA, RETORNO, TOTAL
            # Data from row 4
            for r in range(4, len(df_geral)):
                try:
                    km_i = float(df_geral.iloc[r, 1])
                    km_f = float(df_geral.iloc[r, 2])
                    km_t = float(df_geral.iloc[r, 3])
                except (TypeError, ValueError):
                    continue
                c = 4
                while c + 2 < df_geral.shape[1]:
                    vehicle_name = df_geral.iloc[2, c + 1]
                    if pd.notna(vehicle_name) and isinstance(vehicle_name, str):
                        v = normalize_vehicle(vehicle_name.strip())
                        if v:
                            out_rows.append(
                                {
                                    "vehicle_type": v,
                                    "km_inicial": km_i,
                                    "km_final": km_f,
                                    "km_total": km_t,
                                    "valor_dia_util_calculo": _num(df_geral.iloc[r, c]),
                                    "frete_peso_entrega": _num(df_geral.iloc[r, c]),
                                    "frete_peso_retorno": _num(df_geral.iloc[r, c + 1]),
                                    "frete_peso_viagem": _num(df_geral.iloc[r, c + 2]),
                                }
                            )
                    c += 3

    return pd.DataFrame(out_rows)


def _num(x) -> float | None:
    if pd.isna(x):
        return None
    try:
        return float(x)
    except (ValueError, TypeError):
        return None
