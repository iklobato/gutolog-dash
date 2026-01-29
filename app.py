"""Streamlit dashboard: merged freight metrics and visualizations."""

from pathlib import Path

import pandas as pd
import streamlit as st

# Add project root so merge package is importable
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from merge.merge_all import merge_all


def load_data():
    root = Path(__file__).resolve().parent
    main, context = merge_all(
        base_valores_path=root / "BASE_VALORES.xlsx",
        calculo_path=root / "CALCULO FRETE PESO.xlsx",
        cotacao_path=root / "COTAÇÃO_LOTAÇÃO.xlsm",
    )
    return main, context


@st.cache_data(ttl=300)
def get_merged_data():
    return load_data()


def main():
    st.set_page_config(
        page_title="Frete Dashboard",
        page_icon="📦",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("Dashboard de Frete – Métricas Consolidadas")

    main_df, context_df = get_merged_data()
    if main_df.empty:
        st.warning("Nenhum dado carregado. Verifique se os arquivos Excel estão na pasta do projeto.")
        return

    # ---- Sidebar: filters ----
    st.sidebar.header("Filtros")
    vehicle_types = sorted(main_df["vehicle_type"].dropna().unique().tolist())
    selected_vehicles = st.sidebar.multiselect(
        "Tipo de veículo",
        options=vehicle_types,
        default=vehicle_types[:3] if len(vehicle_types) > 3 else vehicle_types,
    )
    km_min = float(main_df["km_inicial"].min()) if main_df["km_inicial"].notna().any() else 0
    km_max = float(main_df["km_final"].max()) if main_df["km_final"].notna().any() else 10000
    km_range = st.sidebar.slider(
        "Faixa de KM (inicial)",
        min_value=int(km_min),
        max_value=int(km_max),
        value=(int(km_min), min(int(km_max), 500)),
        step=50,
    )
    filter_km_min, filter_km_max = km_range

    # Apply filters
    filtered = main_df.copy()
    if selected_vehicles:
        filtered = filtered[filtered["vehicle_type"].isin(selected_vehicles)]
    filtered = filtered[
        (filtered["km_inicial"].notna())
        & (filtered["km_inicial"] >= filter_km_min)
        & (filtered["km_inicial"] <= filter_km_max)
    ]

    # ---- Context summary ----
    if not context_df.empty:
        with st.expander("Contexto da cotação / base", expanded=False):
            ctx = context_df.iloc[0]
            cols = st.columns(4)
            if "dias_uteis" in ctx and pd.notna(ctx["dias_uteis"]):
                cols[0].metric("Dias úteis", int(ctx["dias_uteis"]))
            if "numero_cotacao" in ctx and pd.notna(ctx.get("numero_cotacao")):
                cols[1].metric("Nº Cotação", str(ctx["numero_cotacao"]))
            if "data_cotacao" in ctx and pd.notna(ctx.get("data_cotacao")):
                cols[2].metric("Data", str(ctx["data_cotacao"])[:10])
            if "km_rota" in ctx and pd.notna(ctx.get("km_rota")):
                cols[3].metric("KM rota", ctx["km_rota"])
            if "cliente" in ctx and pd.notna(ctx.get("cliente")):
                st.caption(f"Cliente: {ctx['cliente']}")
            if "origem" in ctx or "destino" in ctx:
                st.caption(f"Origem → Destino: {ctx.get('origem', '')} → {ctx.get('destino', '')}")

    # ---- Metrics overview (first row) ----
    st.subheader("Resumo")
    num_rows = len(filtered)
    num_vehicles = filtered["vehicle_type"].nunique()
    num_km_bands = filtered.groupby(["km_inicial", "km_final"]).ngroups
    m1, m2, m3 = st.columns(3)
    m1.metric("Registros", num_rows)
    m2.metric("Tipos de veículo", num_vehicles)
    m3.metric("Faixas de KM", num_km_bands)

    # ---- Tabs: Tabela | Gráficos ----
    tab_table, tab_charts = st.tabs(["Tabela de métricas", "Gráficos"])

    with tab_table:
        st.subheader("Todas as métricas")
        # Drop internal columns for display
        display_cols = [c for c in filtered.columns if not c.startswith("_source")]
        numeric_cols = filtered[display_cols].select_dtypes(include=["number"]).columns.tolist()
        id_cols = ["vehicle_type", "km_inicial", "km_final", "km_total"]
        order_cols = [c for c in id_cols if c in filtered.columns]
        other_cols = [c for c in display_cols if c not in order_cols]
        show_cols = order_cols + other_cols
        st.dataframe(
            filtered[show_cols].head(500),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("Exibindo até 500 linhas. Use os filtros na barra lateral para refinar.")

    with tab_charts:
        st.subheader("Visualizações")

        # Ensure we have numeric columns for charts
        chart_df = filtered.copy()
        for c in ("km_inicial", "km_final", "km_total"):
            if c in chart_df.columns:
                chart_df[c] = pd.to_numeric(chart_df[c], errors="coerce")
        chart_df = chart_df.dropna(subset=["km_inicial", "vehicle_type"])

        if chart_df.empty:
            st.info("Nenhum dado numérico para exibir nos gráficos. Ajuste os filtros.")
        else:
            # Line chart: valor por KM (one line per vehicle) – use first available valor column
            valor_cols = [
                "valor_dia_util_calculo",
                "frete_peso_entrega",
                "frete_peso_total_cotacao",
                "frete_peso_viagem",
                "pct_frete_ida",
            ]
            chosen_valor = next((c for c in valor_cols if c in chart_df.columns and chart_df[c].notna().any()), None)
            if chosen_valor:
                st.markdown(f"**{chosen_valor}** por faixa de KM (média por veículo)")
                pivot = chart_df.pivot_table(
                    index="km_inicial",
                    columns="vehicle_type",
                    values=chosen_valor,
                    aggfunc="mean",
                )
                st.line_chart(pivot)

            # Bar chart: compare vehicles (aggregate over KM)
            st.markdown("**Comparativo por veículo** (média sobre as faixas de KM filtradas)")
            agg_cols = [c for c in valor_cols if c in chart_df.columns]
            if agg_cols:
                by_vehicle = chart_df.groupby("vehicle_type")[agg_cols].mean().reset_index()
                plot_cols = [c for c in agg_cols[:6] if by_vehicle[c].notna().any()]
                if plot_cols:
                    st.bar_chart(by_vehicle.set_index("vehicle_type")[plot_cols])

            # Scatter: frete entrega vs retorno
            if "frete_peso_entrega" in chart_df.columns and "frete_peso_retorno" in chart_df.columns:
                scatter_df = chart_df[["vehicle_type", "km_total", "frete_peso_entrega", "frete_peso_retorno"]].dropna()
                if len(scatter_df) > 0:
                    st.markdown("**Frete entrega vs retorno** (por registro)")
                    st.scatter_chart(
                        scatter_df,
                        x="frete_peso_entrega",
                        y="frete_peso_retorno",
                        color="vehicle_type",
                        size="km_total",
                    )

    st.sidebar.caption("Dados consolidados de BASE_VALORES, CALCULO FRETE PESO e COTAÇÃO_LOTAÇÃO.")


if __name__ == "__main__":
    main()
