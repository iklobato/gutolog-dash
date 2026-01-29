# Gutolog Dash

Streamlit dashboard that merges freight data from three Excel workbooks (BASE_VALORES, CALCULO FRETE PESO, COTAÇÃO_LOTAÇÃO) into a single table with filters and visualizations.

## Run locally

```bash
uv run streamlit run app.py
```

Place the Excel files (`BASE_VALORES.xlsx`, `CALCULO FRETE PESO.xlsx`, `COTAÇÃO_LOTAÇÃO.xlsm`) in the project root.

## Run with Docker

```bash
docker compose up
```

Open http://localhost:8501. The image includes the app; mount the Excel files as volumes if you need to use your own data without rebuilding.

## Dependencies

Managed with [uv](https://github.com/astral-sh/uv). Install: `uv sync`.
