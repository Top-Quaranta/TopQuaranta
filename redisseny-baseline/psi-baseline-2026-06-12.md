# PSI / CWV baseline — 2026-06-12 (source: server MetricaCWV, recollir_metrics_psi cron)

Lab PageSpeed Insights, latest stored run. Score = Lighthouse perf 0-100.

| URL | desktop score | desktop LCP | desktop CLS | mobile score | mobile LCP | mobile CLS |
|---|---|---|---|---|---|---|
| / (home)        | 99  | 968ms  | 0.036 | 93 | 2820ms | 0.000 |
| /top            | 100 | 533ms  | 0.032 | 96 | 2552ms | 0.047 |
| /artistes       | 100 | 807ms  | 0.000 | 95 | 2565ms | 0.000 |
| /artista/<slug> | 98  | 1064ms | 0.040 | 83 | 4216ms | 0.078 |
| /canco/<slug>   | 100 | 773ms  | ~0    | 89 | 3506ms | 0.021 |
| /mapa           | 100 | 536ms  | 0.004 | 95 | 2589ms | 0.000 |

Weakest (watch after redesign): **artista mobile 83 / LCP 4216ms**, **canço mobile 89 / LCP 3506ms**.
Glass blur + full-page grain overlay are the obvious new perf risks on mobile.
