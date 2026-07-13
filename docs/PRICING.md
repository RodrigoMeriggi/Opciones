# Motor de valuación (Prompt 16)

## Modelos

| Modelo | Uso |
|--------|-----|
| Black-Scholes | Europeas, q=0 (referencia) |
| Black-Scholes-Merton | Europeas con dividend yield continuo |
| Binomial CRR | Americanas (BYMA puede ser americano); griegas por diferencias finitas |

La estrategia depende de `OptionPricingModel`, no de una implementación concreta.

## Fórmulas (BSM)

Con \(S\) spot, \(K\) strike, \(T\) tiempo, \(r\) tasa, \(q\) yield, \(\sigma\) vol:

\[
d_1 = \frac{\ln(S/K)+(r-q+\sigma^2/2)T}{\sigma\sqrt{T}},\quad d_2=d_1-\sigma\sqrt{T}
\]

Call: \(S e^{-qT}N(d_1)-K e^{-rT}N(d_2)\)  
Put: \(K e^{-rT}N(-d_2)-S e^{-qT}N(-d_1)\)

## Volatilidad implícita

Solvers: Brent → Newton → bisección (fallback).  
Si no hay bracket o no converge: **no se inventa IV**.

## Tasa y dividendos

- `RiskFreeRateProvider`: manual, curva (sin extrapolación silenciosa), adaptador externo.
- `DividendProvider`: yield continuo, discretos, o ausencia explícita (con supuesto registrado si se asume cero).

## Superficie

Interpolación marcada; sin extrapolación silenciosa; distancia a observados y score de confianza.

## Disclaimer

Estas métricas son de referencia operativa. **No constituyen garantía de rentabilidad.**
