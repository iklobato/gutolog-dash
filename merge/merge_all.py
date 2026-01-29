"""Merge BASE_VALORES, CALCULO FRETE PESO, and COTAÇÃO into one main table + context."""

from pathlib import Path

import pandas as pd

from .read_base_valores import read_base_valores
from .read_calculo_frete import read_calculo_frete
from .read_cotacao import read_cotacao


def merge_all(
    base_valores_path: str | Path = "BASE_VALORES.xlsx",
    calculo_path: str | Path = "CALCULO FRETE PESO.xlsx",
    cotacao_path: str | Path = "COTAÇÃO_LOTAÇÃO.xlsm",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge all Excel sources into main table and context table.

    Returns:
        (main_df, context_df):
        - main_df: one row per (vehicle_type, km_inicial, km_final) with all metric columns
        - context_df: one row with dias_uteis, numero_cotacao, data_cotacao, etc.
    """
    base_valores_path = Path(base_valores_path)
    calculo_path = Path(calculo_path)
    cotacao_path = Path(cotacao_path)

    main_dfs: list[pd.DataFrame] = []
    context_dfs: list[pd.DataFrame] = []

    if base_valores_path.exists():
        bv_main, bv_ctx = read_base_valores(base_valores_path)
        bv_main["_source_bv"] = True
        main_dfs.append(bv_main)
        context_dfs.append(bv_ctx)

    if calculo_path.exists():
        cf_main = read_calculo_frete(calculo_path)
        if not cf_main.empty:
            cf_main["_source_cf"] = True
            main_dfs.append(cf_main)

    if cotacao_path.exists():
        cot_main, cot_ctx = read_cotacao(cotacao_path)
        if not cot_main.empty:
            cot_main["_source_cot"] = True
            main_dfs.append(cot_main)
        context_dfs.append(cot_ctx)

    if not main_dfs:
        return pd.DataFrame(), pd.DataFrame()

    # Join keys: vehicle_type, km_inicial, km_final (allow small float tolerance for km)
    def round_km(df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        for c in ("km_inicial", "km_final", "km_total"):
            if c in d.columns:
                d[c] = pd.to_numeric(d[c], errors="coerce")
        return d

    main = main_dfs[0]
    for df in main_dfs[1:]:
        main = main.merge(
            df,
            on=["vehicle_type", "km_inicial", "km_final"],
            how="outer",
            suffixes=("", "_dup"),
        )
        # Drop duplicate columns (suffix _dup)
        dup_cols = [c for c in main.columns if c.endswith("_dup")]
        main = main.drop(columns=dup_cols, errors="ignore")

    # Fill km_total if missing
    if "km_total" in main.columns:
        mask = main["km_total"].isna() & main["km_inicial"].notna() & main["km_final"].notna()
        main.loc[mask, "km_total"] = (
            main.loc[mask, "km_final"] - main.loc[mask, "km_inicial"] + 1
        )

    # Deduplicate: keep first row per (vehicle_type, km_inicial, km_final)
    main = main.drop_duplicates(
        subset=["vehicle_type", "km_inicial", "km_final"],
        keep="first",
    ).reset_index(drop=True)

    # Context: concat all context rows (one row per source)
    if context_dfs:
        context = pd.concat(context_dfs, axis=1)
        # Flatten to one row: take first non-null per column
        context_flat = context.iloc[0:1].copy()
        for c in context.columns:
            if c in context_flat.columns and context_flat[c].isna().all():
                first = context[c].dropna()
                if len(first):
                    context_flat[c] = first.iloc[0]
    else:
        context_flat = pd.DataFrame()

    return main, context_flat
