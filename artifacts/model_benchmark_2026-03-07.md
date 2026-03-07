# Model Benchmark (Leak-Safe Meta Stack)

- Generated: `2026-03-07T07:30:09`
- Date window: `2026-02-18` to `2026-03-07`

## Data/Cohort definition

Final games with known winner. Prediction rows are leak-safe only:
- exclude `prediction_source='backfill'`
- include only `prediction_source IN ('live','refresh')` or NULL/empty (legacy-live)
- require `predicted_at <= (game_datetime - 5 minutes)`; fallback cutoff = `game_date 23:54:59` when game time missing

### Filter counts

- Total candidate prediction rows: **23754**
- Excluded backfill rows: **3354**
- Excluded disallowed source rows: **0**
- Excluded late/invalid timestamp rows: **4514**
- Kept leak-safe rows: **15886**

## Leak-safe per-model leaderboard

| Model | n predictions | Win accuracy | Brier | Log loss | ECE |
|---|---:|---:|---:|---:|---:|
| meta_ensemble | 781 | 0.6633 | 0.2209 | 0.6484 | 0.0918 |
| elo | 1093 | 0.6487 | 0.2132 | 0.6163 | 0.0191 |
| pythagorean | 1093 | 0.6386 | 0.2255 | 0.6479 | 0.0468 |
| lightgbm | 1091 | 0.6398 | 0.2339 | 0.6767 | 0.0569 |
| poisson | 1093 | 0.6304 | 0.2351 | 0.7120 | 0.0740 |
| xgboost | 1091 | 0.6251 | 0.2403 | 0.6976 | 0.0704 |
| pitching | 1093 | 0.7200 | 0.1852 | 0.5493 | 0.0299 |
| pear | 708 | 0.6582 | 0.2107 | 0.6127 | 0.0711 |
| quality | 732 | 0.6393 | 0.2250 | 0.6523 | 0.0611 |
| neural | 1090 | 0.6413 | 0.2263 | 0.6489 | 0.0429 |
| venue | 182 | 0.6209 | 0.2603 | 0.8659 | 0.1638 |
| rest_travel | 182 | 0.6703 | 0.2221 | 0.7101 | 0.0474 |
| upset | 182 | 0.6703 | 0.2090 | 0.6149 | 0.1021 |

### Legacy models present (leak-safe cohort)

| Model | n predictions | Win accuracy | Brier | Log loss | ECE |
|---|---:|---:|---:|---:|---:|
| advanced | 1095 | 0.6320 | 0.2420 | 0.7296 | 0.0769 |
| conference | 1095 | 0.6237 | 0.2327 | 0.6792 | 0.0754 |
| ensemble | 1095 | 0.6484 | 0.2214 | 0.6441 | 0.0522 |
| log5 | 1095 | 0.6301 | 0.2417 | 0.7408 | 0.0769 |
| prior | 1095 | 0.6457 | 0.2166 | 0.6247 | 0.0294 |

## Strict cohort leaderboard

- Strict cohort size (games with predictions from all active models + meta): **168**
- Strict cohort date range: **2026-03-04 to 2026-03-06**

| Model | n predictions | Win accuracy | Brier | Log loss | ECE |
|---|---:|---:|---:|---:|---:|
| meta_ensemble | 168 | 0.7262 | 0.1865 | 0.5604 | 0.0836 |
| elo | 168 | 0.6667 | 0.2005 | 0.5911 | 0.0420 |
| pythagorean | 168 | 0.6607 | 0.2064 | 0.6020 | 0.0591 |
| lightgbm | 168 | 0.6607 | 0.2168 | 0.6241 | 0.0540 |
| poisson | 168 | 0.6607 | 0.2175 | 0.6260 | 0.0340 |
| xgboost | 168 | 0.6607 | 0.2286 | 0.6492 | 0.0914 |
| pitching | 168 | 0.6905 | 0.1907 | 0.5660 | 0.0834 |
| pear | 168 | 0.6905 | 0.1853 | 0.5486 | 0.0813 |
| quality | 168 | 0.6845 | 0.2073 | 0.6077 | 0.0538 |
| neural | 168 | 0.6905 | 0.2057 | 0.5995 | 0.0482 |
| venue | 168 | 0.6012 | 0.2652 | 0.8613 | 0.1711 |
| rest_travel | 168 | 0.6667 | 0.2268 | 0.7277 | 0.0585 |
| upset | 168 | 0.6726 | 0.2090 | 0.6160 | 0.1056 |

## Calibration table

Reliability bins on strict cohort (10 bins):

| Model | Bin range | n | Avg predicted home win | Actual home win | Gap |
|---|---|---:|---:|---:|---:|
| meta_ensemble | [0.0, 0.1) | 2 | 0.0766 | 1.0000 | +0.9234 |
|  | [0.1, 0.2) | 6 | 0.1650 | 0.1667 | +0.0016 |
|  | [0.2, 0.3) | 10 | 0.2532 | 0.4000 | +0.1468 |
|  | [0.3, 0.4) | 10 | 0.3596 | 0.2000 | -0.1596 |
|  | [0.4, 0.5) | 23 | 0.4480 | 0.4783 | +0.0302 |
|  | [0.5, 0.6) | 8 | 0.5450 | 0.6250 | +0.0800 |
|  | [0.6, 0.7) | 20 | 0.6541 | 0.6000 | -0.0541 |
|  | [0.7, 0.8) | 30 | 0.7411 | 0.6667 | -0.0744 |
|  | [0.8, 0.9) | 44 | 0.8514 | 0.9318 | +0.0804 |
|  | [0.9, 1.0] | 15 | 0.9289 | 0.8667 | -0.0622 |
| elo | [0.3, 0.4) | 8 | 0.3813 | 0.5000 | +0.1187 |
|  | [0.4, 0.5) | 55 | 0.4889 | 0.4909 | +0.0020 |
|  | [0.6, 0.7) | 29 | 0.6479 | 0.6207 | -0.0272 |
|  | [0.7, 0.8) | 53 | 0.7453 | 0.8113 | +0.0660 |
|  | [0.8, 0.9) | 7 | 0.8659 | 0.8571 | -0.0088 |
|  | [0.9, 1.0] | 16 | 0.9150 | 0.8125 | -0.1025 |
| pythagorean | [0.5, 0.6) | 60 | 0.5255 | 0.4833 | -0.0421 |
|  | [0.6, 0.7) | 37 | 0.6412 | 0.7027 | +0.0615 |
|  | [0.7, 0.8) | 69 | 0.7335 | 0.7971 | +0.0636 |
|  | [0.8, 0.9) | 2 | 0.8679 | 0.5000 | -0.3679 |
| lightgbm | [0.5, 0.6) | 10 | 0.5316 | 0.2000 | -0.3316 |
|  | [0.6, 0.7) | 145 | 0.6540 | 0.6828 | +0.0287 |
|  | [0.7, 0.8) | 4 | 0.7498 | 0.5000 | -0.2498 |
|  | [0.8, 0.9) | 9 | 0.8239 | 0.8889 | +0.0650 |
| poisson | [0.5, 0.6) | 53 | 0.5223 | 0.5283 | +0.0060 |
|  | [0.6, 0.7) | 44 | 0.6641 | 0.7273 | +0.0631 |
|  | [0.7, 0.8) | 41 | 0.7212 | 0.6829 | -0.0382 |
|  | [0.8, 0.9) | 30 | 0.8014 | 0.7667 | -0.0348 |
| xgboost | [0.5, 0.6) | 136 | 0.5422 | 0.6324 | +0.0901 |
|  | [0.6, 0.7) | 19 | 0.6429 | 0.7895 | +0.1466 |
|  | [0.7, 0.8) | 12 | 0.7593 | 0.7500 | -0.0093 |
|  | [0.8, 0.9) | 1 | 0.8044 | 1.0000 | +0.1956 |
| pitching | [0.0, 0.1) | 5 | 0.0729 | 0.0000 | -0.0729 |
|  | [0.1, 0.2) | 2 | 0.1264 | 0.0000 | -0.1264 |
|  | [0.2, 0.3) | 11 | 0.2814 | 0.5455 | +0.2641 |
|  | [0.3, 0.4) | 3 | 0.3653 | 1.0000 | +0.6347 |
|  | [0.4, 0.5) | 26 | 0.4723 | 0.4615 | -0.0108 |
|  | [0.5, 0.6) | 15 | 0.5685 | 0.4667 | -0.1019 |
|  | [0.6, 0.7) | 18 | 0.6889 | 0.5556 | -0.1333 |
|  | [0.7, 0.8) | 35 | 0.7174 | 0.7429 | +0.0255 |
|  | [0.8, 0.9) | 29 | 0.8448 | 0.8966 | +0.0518 |
|  | [0.9, 1.0] | 24 | 0.9574 | 0.8750 | -0.0824 |
| pear | [0.0, 0.1) | 1 | 0.0010 | 0.0000 | -0.0010 |
|  | [0.2, 0.3) | 12 | 0.2627 | 0.3333 | +0.0706 |
|  | [0.3, 0.4) | 10 | 0.3349 | 0.2000 | -0.1349 |
|  | [0.4, 0.5) | 28 | 0.4398 | 0.6071 | +0.1674 |
|  | [0.5, 0.6) | 26 | 0.5750 | 0.5769 | +0.0020 |
|  | [0.6, 0.7) | 13 | 0.6497 | 0.4615 | -0.1882 |
|  | [0.7, 0.8) | 29 | 0.7773 | 0.7586 | -0.0187 |
|  | [0.8, 0.9) | 23 | 0.8397 | 0.9565 | +0.1168 |
|  | [0.9, 1.0] | 26 | 0.9250 | 0.8846 | -0.0404 |
| quality | [0.3, 0.4) | 2 | 0.3500 | 0.0000 | -0.3500 |
|  | [0.4, 0.5) | 36 | 0.4235 | 0.4722 | +0.0488 |
|  | [0.5, 0.6) | 21 | 0.5509 | 0.6667 | +0.1158 |
|  | [0.6, 0.7) | 43 | 0.6129 | 0.6047 | -0.0083 |
|  | [0.7, 0.8) | 32 | 0.7696 | 0.8125 | +0.0429 |
|  | [0.8, 0.9) | 22 | 0.8717 | 0.8636 | -0.0081 |
|  | [0.9, 1.0] | 12 | 0.9368 | 0.7500 | -0.1868 |
| neural | [0.4, 0.5) | 11 | 0.4523 | 0.2727 | -0.1796 |
|  | [0.5, 0.6) | 50 | 0.5372 | 0.5400 | +0.0028 |
|  | [0.6, 0.7) | 40 | 0.6483 | 0.7250 | +0.0767 |
|  | [0.7, 0.8) | 63 | 0.7356 | 0.7778 | +0.0422 |
|  | [0.8, 0.9) | 4 | 0.8136 | 0.7500 | -0.0636 |
| venue | [0.0, 0.1) | 2 | 0.0667 | 1.0000 | +0.9333 |
|  | [0.1, 0.2) | 8 | 0.1205 | 0.5000 | +0.3795 |
|  | [0.2, 0.3) | 2 | 0.2963 | 0.5000 | +0.2037 |
|  | [0.3, 0.4) | 20 | 0.3436 | 0.6500 | +0.3064 |
|  | [0.4, 0.5) | 18 | 0.4396 | 0.5556 | +0.1160 |
|  | [0.5, 0.6) | 6 | 0.5853 | 0.6667 | +0.0813 |
|  | [0.6, 0.7) | 32 | 0.6578 | 0.6250 | -0.0328 |
|  | [0.7, 0.8) | 28 | 0.7297 | 0.7857 | +0.0560 |
|  | [0.8, 0.9) | 29 | 0.8589 | 0.6897 | -0.1692 |
|  | [0.9, 1.0] | 23 | 0.9652 | 0.6522 | -0.3130 |
| rest_travel | [0.0, 0.1) | 2 | 0.0010 | 1.0000 | +0.9990 |
|  | [0.3, 0.4) | 5 | 0.3457 | 0.2000 | -0.1457 |
|  | [0.4, 0.5) | 2 | 0.4825 | 0.5000 | +0.0175 |
|  | [0.5, 0.6) | 4 | 0.5707 | 0.2500 | -0.3207 |
|  | [0.6, 0.7) | 138 | 0.6464 | 0.6667 | +0.0202 |
|  | [0.7, 0.8) | 11 | 0.7459 | 0.9091 | +0.1632 |
|  | [0.8, 0.9) | 4 | 0.8000 | 0.7500 | -0.0500 |
|  | [0.9, 1.0] | 2 | 0.9990 | 0.5000 | -0.4990 |
| upset | [0.0, 0.1) | 1 | 0.0710 | 1.0000 | +0.9290 |
|  | [0.1, 0.2) | 9 | 0.1311 | 0.4444 | +0.3134 |
|  | [0.2, 0.3) | 18 | 0.2697 | 0.3889 | +0.1192 |
|  | [0.3, 0.4) | 5 | 0.3871 | 0.6000 | +0.2129 |
|  | [0.4, 0.5) | 5 | 0.4244 | 0.6000 | +0.1756 |
|  | [0.5, 0.6) | 34 | 0.5673 | 0.5000 | -0.0673 |
|  | [0.6, 0.7) | 2 | 0.6756 | 1.0000 | +0.3244 |
|  | [0.7, 0.8) | 43 | 0.7577 | 0.6744 | -0.0833 |
|  | [0.8, 0.9) | 20 | 0.8738 | 0.9000 | +0.0262 |
|  | [0.9, 1.0] | 31 | 0.9631 | 0.8710 | -0.0922 |

## Correlation findings

Top 10 highest absolute pairwise correlations (strict cohort):

| Model A | Model B | Correlation | abs(corr) |
|---|---|---:|---:|
| meta_ensemble | pitching | 0.9014 | 0.9014 |
| elo | upset | 0.8896 | 0.8896 |
| pythagorean | pitching | 0.8277 | 0.8277 |
| elo | pythagorean | 0.8163 | 0.8163 |
| elo | pear | 0.8145 | 0.8145 |
| pythagorean | neural | 0.8137 | 0.8137 |
| meta_ensemble | pear | 0.8110 | 0.8110 |
| pitching | pear | 0.8109 | 0.8109 |
| elo | neural | 0.8076 | 0.8076 |
| elo | pitching | 0.7982 | 0.7982 |

Meta disagreement analysis (strict cohort):

| Meta vs model | Agreement rate | Meta accuracy when agree | Meta accuracy when disagree |
|---|---:|---:|---:|
| upset | 0.8393 | 0.7376 | 0.6667 |
| pitching | 0.9167 | 0.7273 | 0.7143 |
| pear | 0.8571 | 0.7431 | 0.6250 |
| venue | 0.6726 | 0.7434 | 0.6909 |
| rest_travel | 0.6786 | 0.7895 | 0.5926 |

## Risks/interpretation notes

- Strict cohort can be much smaller than leak-safe per-model cohort; this may change rank ordering.
- High correlation means less independent signal and limits stacking upside.
- ECE is sample-size sensitive; sparse bins can look noisy on small cohorts.
- Accuracy alone can hide confidence miscalibration, so Brier/log loss/ECE should be considered together.

## Recommended next experiments

- Re-rank meta base-feature set using strict-cohort incremental gain vs high-correlation redundancy.
- Compare meta calibration before/after isotonic/Platt post-calibration on strict cohort only.
- Stress-test upset/pitching/venue contributions on disagreement-only slices.
- Add time-slice stability (weekly rolling strict-cohort metrics) before any hyperparameter tuning.
- Audit games dropped from strict cohort to identify model coverage gaps by source/date.
