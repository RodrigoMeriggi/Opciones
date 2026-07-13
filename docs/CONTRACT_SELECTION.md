# Selección de contratos (Prompt 17)

`ContractSelector` separa:

1. Señal sobre el subyacente  
2. Selección del contrato  
3. Validación `RiskManager`  
4. Ejecución (fuera del selector)

## Reglas

- Nunca elegir solo por prima baja (el componente `premium` tiene tope de score 70).
- Filtros obligatorios: bid/ask, spread, frescura, DTE, volumen, capital, griegas si se exigen, RiskManager.
- Score 0–100 con pesos YAML y explicaciones parciales.
- Si no hay candidato aceptable → **no operar**.

Ver `config/contract_selector.yaml`.
