# Case study · Burned area of the Chilecito fire (La Rioja, Argentina, July 2026)

The fire shown in the challenge video (CONAE activation ACT#356) mapped at 30 m and compared across three methods.
Code: `packages/nina/src/nina/io/burn_case.py`; outputs in `source/context/burn_case/` (`summary.json` holds scenes,
thresholds, areas, overlaps, failures and licences). Not validated against a field perimeter or an official CONAE
figure: none was available.

## Context in NINA's record

In the harmonized record (method 0.5.0, dataset `7a274cb30ec2558be1eccb24`), July 2026 is the highest July since 2003
for the area around Guanchín (lon −67.75 to −67.05, lat −29.35 to −28.75): about 46 VIIRS-equivalent active cell-days
against a median of 4 for the other Julys (rank 1 of 24). 2026 comes from near-real-time data (provisional).

## Data

- FIRMS: 955 nominal/high-confidence detections, 27 July – 1 August 2026 (standard data replaced NRT where available).
- HLS L30: pre-fire 2026-07-14, post-fire 2026-08-07 (check: 2026-08-23), tiles T19JFJ and T19JFH, 0–2 % cloud.
- MODIS MCD64A1 c6.1, tile h12v11, July and August 2026.
- Prithvi-EO-2.0-300M-BurnScars (IBM/NASA, Apache-2.0), CPU inference on 512 × 512 chips.

The hotspots extend west of the requested box, so the analysis box was widened to −67.90.

## Results

| Method | Burned area (ha) |
|---|---|
| HLS dNBR ≥ 0.27, pixels clear on both dates (lower bound) | 3,895 |
| HLS dNBR ≥ 0.10, pixels clear on both dates | 7,962 |
| HLS dNBR, gaps inside the burned outline filled (≥ 0.27 / ≥ 0.10) | 4,804 / 9,630 |
| HLS dNBR, shaded slopes included (≥ 0.27 / ≥ 0.10) | 6,071 / 11,159 |
| MODIS MCD64A1 (500 m) | 13,846 |
| Prithvi, patches touching the hotspots | 14,755 |

Quote it as a range: **about 4,000–11,000 ha by HLS dNBR** depending on threshold and terrain shadow; MCD64A1
about 13,800 ha (it counts whole 21.5 ha cells and includes a few late-August burn dates).

Agreement: MCD64A1 vs dNBR ≥ 0.10, IoU 0.47 (0.63 with shaded slopes); the two post-fire dates, IoU 0.78. Prithvi
finds 96–99 % of the dNBR burned area but has low precision (IoU 0.51 against dNBR ≥ 0.10): over the whole box it also
marks 46,010 ha of clear unburned slopes, irrigated fields and snow. It was fine-tuned on US burn scars; this is an
out-of-domain test, not a measurement.

## Caveats

- Steep winter shadow is flagged as water by the HLS quality mask (29 % of the hotspot buffer); only 67 % of the buffer is
  measurable on both dates, so the clear-pixel figures are lower bounds.
- Standard dNBR thresholds were not calibrated for this arid shrubland; the area roughly doubles between 0.27 and 0.10.
- Burned area is a different quantity from NINA's active cell-days: the calendar says when and where fire was active;
  these products estimate the area that burned.
