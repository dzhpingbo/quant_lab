# US Stock Selection v8 Gate Calibration Executive Summary - 20260428_111439

Final v8 verdict remains `credible_but_execution_sensitive`. `allow_enter_v9` remains `False`.

The existing `single_year_share` gate is code-confirmed as max absolute annual return divided by total absolute annual returns. For this short sample, 52.6% vs 46.7% mostly says 2024 was slightly stronger than 2025; it is a real gate failure, but not severe one-year monopoly.

Key results:

- Current abs annual-return share: `0.526027`
- Leave-one-year-out min CAGR / Calmar: `0.527392` / `1.617424`
- Top 1 / Top 3 / Top 5 positive month share: `0.168601` / `0.389378` / `0.541001`
- Remove top 3 months CAGR / Calmar: `0.283153` / `0.789229`
- Max ticker abs share / max monthly weight: `0.223603` / `0.200000`

Recommended v8.1 interpretation: `concentration_gate_passed` with concentration penalty score `0.116159`.

Recommendation: build v8.1 gate-aware improvement first. Do not enter v9, do not expand universe, and do not treat 31b as a fix for concentration; 31b is only optional model-stability evidence.
