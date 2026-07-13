# Ingesta de datos históricos

## Pipeline

Lectura → validación → normalización de símbolos/fechas/TZ → duplicados → inválidos → huecos → enriquecimiento → persistencia → quality report.

Los registros **nunca se borran en silencio**: se clasifican como VALID / CORRECTABLE / SUSPICIOUS / REJECTED con motivo.

## Formatos

- CSV, JSON, Parquet
- API: interfaz `HistoricalApiSource` — **documentación del proveedor faltante** (no se inventan endpoints)

## Ejemplos

- `data/sample/csv/ggal_bars.csv`
- `data/sample/json/options_sample.json`

## Versionado

Hash SHA-256 del contenido; importaciones duplicadas bloqueadas salvo `allow_duplicate_import=True`.
