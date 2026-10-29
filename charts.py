import io
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")  # draw to memory, no window
import matplotlib.pyplot as plt
from flask import Blueprint, Response
from sqlalchemy import text

from db import engine
from routes.analysis import (calculate_consumption, default_factor,
                             find_high_usage, summarize)
from utils import error

charts_bp = Blueprint("charts", __name__, url_prefix="/charts")


def fig_to_png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return Response(buf.getvalue(), mimetype="image/png")


@charts_bp.get("/trend/<int:meter_id>.png")
def trend_chart(meter_id):
    with engine.connect() as conn:
        code = conn.execute(
            text("SELECT meter_code FROM meters WHERE meter_id = :m"), {"m": meter_id}
        ).scalar()
        if code is None:
            return error("meter not found", 404)
        rows = conn.execute(
            text("SELECT reading_date, cumulative_kwh FROM meter_readings "
                 "WHERE meter_id = :m ORDER BY reading_date"),
            {"m": meter_id},
        ).mappings().all()

    periods = calculate_consumption(rows)
    if not periods:
        return error("not enough readings to draw a chart", 400)

    monthly = summarize(periods, "monthly")
    _, limit, flagged = find_high_usage(periods, default_factor())
    flagged_months = {p["period_start"][:7] for p in flagged}

    labels = [m["period"] for m in monthly]
    values = [m["total_kwh"] for m in monthly]
    colors = ["#d9534f" if label in flagged_months else "#4a90d9" for label in labels]
    x = list(range(len(labels)))

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(x, values, color=colors)
    if limit:
        ax.axhline(limit, linestyle="--", color="gray",
                   label=f"High-usage limit ({limit} kWh)")
        ax.legend()
    for i, m in enumerate(monthly):
        if m["reset_periods"]:
            ax.annotate("meter reset", (i, 0), ha="center", va="bottom", color="gray")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_title(f"Monthly consumption: meter {code}")
    ax.set_xlabel("Month")
    ax.set_ylabel("Consumption (kWh)")
    return fig_to_png(fig)


@charts_bp.get("/compare.png")
def compare_chart():
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT c.consumer_code, m.meter_id, r.reading_date, r.cumulative_kwh "
                 "FROM consumers c "
                 "JOIN meters m ON m.consumer_id = c.consumer_id "
                 "JOIN meter_readings r ON r.meter_id = m.meter_id "
                 "ORDER BY m.meter_id, r.reading_date")
        ).mappings().all()

    by_meter = defaultdict(list)
    for r in rows:
        by_meter[(r["consumer_code"], r["meter_id"])].append(
            {"reading_date": r["reading_date"], "cumulative_kwh": r["cumulative_kwh"]})

    totals = defaultdict(float)
    for (code, _), readings in by_meter.items():
        for p in calculate_consumption(readings):
            if p["status"] == "valid":
                totals[code] += p["consumption_kwh"]

    if not totals:
        return error("no consumption data to chart", 400)

    codes = sorted(totals)
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(codes, [totals[c] for c in codes], color="#4a90d9")
    ax.bar_label(bars, fmt="%.0f")
    ax.set_title("Total valid consumption by consumer")
    ax.set_xlabel("Consumer")
    ax.set_ylabel("Consumption (kWh)")
    return fig_to_png(fig)