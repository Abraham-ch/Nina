"""Catálogo de fuentes estáticas previas, separado temporalmente de su evaluación."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

from nina.config import CALIBRATION_COUNTRIES

HISTORICAL_COUNTRIES = set(CALIBRATION_COUNTRIES)
HISTORICAL_CUTOFF = date(2023, 12, 31)
HELD_OUT_MONTHS = 3
MIN_LABEL_DAYS = 2


def temporal_cutoff(last_reference: date) -> tuple[date, date]:
    """Reserva tres meses completos; no selecciona el corte mirando el error."""
    last_month = last_reference.year * 12 + last_reference.month - 1
    if last_reference.day < calendar.monthrange(last_reference.year, last_reference.month)[1]:
        last_month -= 1
    start_year, start_month = divmod(last_month - HELD_OUT_MONTHS + 1, 12)
    end_year, end_month = divmod(last_month + 1, 12)
    return (
        date(start_year, start_month + 1, 1) - timedelta(days=1),
        date(end_year, end_month + 1, 1) - timedelta(days=1),
    )


def build_catalog(connection: Any) -> dict[str, Any]:
    """Usa solo etiquetas anteriores; las etiquetas de prueba no crean su máscara."""
    last = connection.execute("""SELECT max(day) FROM normalized
        WHERE platform='S-NPP' AND processing='SP'""").fetchall()[0][0]
    if last is None:
        raise ValueError("Se requiere referencia S-NPP estándar para separar la evaluación")
    global_cutoff, global_test_end = temporal_cutoff(last)
    connection.execute("""CREATE OR REPLACE TABLE mask_cutoffs(
        country VARCHAR,train_cutoff DATE,test_end DATE)""")
    connection.executemany(
        "INSERT INTO mask_cutoffs VALUES (?,?,?)",
        [(country, HISTORICAL_CUTOFF, last) for country in sorted(HISTORICAL_COUNTRIES)]
        + [("world", global_cutoff, global_test_end)],
    )
    connection.execute(
        """CREATE OR REPLACE TABLE static_catalog AS
        SELECT n.cell8,min(n.day) AS first_labeled,max(n.day) AS last_labeled,
            count(DISTINCT n.day) AS confirmed_days
        FROM normalized n JOIN cells c USING(cell8)
        LEFT JOIN mask_cutoffs k ON k.country=c.country
        CROSS JOIN (SELECT train_cutoff FROM mask_cutoffs WHERE country='world') w
        WHERE n.platform IN ('Terra','Aqua') AND n.processing='SP'
        AND n.fire_type IN (1,2) AND NOT n.low_confidence
        AND n.day<=coalesce(k.train_cutoff,w.train_cutoff)
        GROUP BY n.cell8 HAVING count(DISTINCT n.day)>=?""",
        [MIN_LABEL_DAYS],
    )
    count = connection.execute("SELECT count(*) FROM static_catalog").fetchall()[0][0]
    return {
        "method": "prior_MODIS_static_labels_with_temporal_holdout",
        "cells": count,
        "minimum_label_days": MIN_LABEL_DAYS,
        "historical_cutoff": str(HISTORICAL_CUTOFF),
        "historical_countries": sorted(HISTORICAL_COUNTRIES),
        "global_cutoff": str(global_cutoff),
        "global_test_end": str(global_test_end),
        "held_out_complete_months": HELD_OUT_MONTHS,
    }
