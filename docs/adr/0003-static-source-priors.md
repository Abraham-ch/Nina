# ADR 0003 · Static-source catalogue with independent temporal evaluation

Method **0.3.0**, under evaluation. The 0.2.0 attempt is kept as a failed candidate: it recovered 18,197 of 60,637 MODIS
static cells (30.01 %) and removed 120,665 of 12,847,381 vegetation detections (0.94 %). It was not published.

Nominal/high VIIRS persistence plus the urban, water and volcano layers are not enough to recover the reference
catalogue. An explicit prior of known static sources is added: cells with standard MODIS `type=1/2` labels on at least
two days before the evaluation period. The origin of each label and its dates are kept. Labels from the evaluated period
are never used to build the catalogue.

For Brazil, Australia, Indonesia, the United States and Peru, the prior is built with data up to 2023 and evaluated from
2024. For the rest of the world, which only has a recent archive, the last three complete standard S-NPP months are
reserved and the catalogue is built from earlier dates. With the current snapshot, the global training cut-off is
30 April 2026 and the test period is May–July 2026. VIIRS persistence and the auxiliary layers still apply.

The evaluation measures recovery against the reserved MODIS labels and false removals of `type=0`. It also reports the
share removed across the whole archive, to expose effects of the retrospective catalogue on earlier years. The gates stay
at **recovery ≥ 80 %** and **false removals ≤ 2 %**; a failed gate still blocks publication. A new industrial site, or one
not observed during training, can go unrecognised: the catalogue does not replace validation.

The monthly series includes months with zero detections when there is comparable archive support; support gaps remain
null. Evaluable strata need at least 24 months with activity, as in the previous candidate. Months without activity take
part in the correlation and the error, without turning a sparse stratum into a validated one.

The comparison keeps leave-one-year-out validation and the reserved years 2024–2025. The catalogue is retrospective; it
is not presented as a real-time detector or as an independent classification of all MODIS data. The filter's sources
and the period of its labels are published separately.
