# Limited MVE2 Selected Report

## Current Conclusion

The limited MVE2 validation pack remains a limited, independent audited-store research result. It validated `9` frozen candidates from `limited_mve2_20260502_142702` and did not start formal MVE2.

Decision distribution:

- pass_to_next_validation: `1`
- conditional: `6`
- observation_only: `2`

Every candidate remains `formal_mve2_supported=false`.

## Why This Is Not A Formal Baseline

The pack is based on limited candidate validation, not on a formal MVE2 universe, formal data gate, approved benchmark set, or formal replay standard. It cannot replace the current v8.2 frozen Pool A `top5_ytdcap80p_derisk100p` baseline.

## Why This Cannot Directly Enter v10

Formal v10 remains disallowed because the limited MVE2 line has not passed a separate formal MVE2 data quality gate. The current evidence is useful for review and follow-up design only.

## Evidence Chain Isolation

- v8.2 frozen formal baseline: remains the formal comparison baseline and is not mixed into this pack.
- formal v9 failed branch: remains a failure and risk reference only; it is not used as a baseline here.
- limited MVE2: uses the audited-store line with `adj_close` and `volume`, and remains separate from both formal branches.

## Allowed Next Step

The next allowed step is P1-B human review or P2 formal MVE2 data quality gate. Direct formal MVE2 search design, v10 work, or baseline replacement is not supported by this pack.
