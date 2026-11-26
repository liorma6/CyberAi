"""Lab 2b analysis: summary statistics + charts from the exported dashboard CSVs.

Usage (from this folder):  python analyze_lab2b.py
Inputs : Lab2B_normal.csv, Lab2B_attack_surge.csv
Outputs: summary_table.csv, chart_throughput.png, chart_backlog.png, chart_latency.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RUNS = {
    "normal": HERE / "Lab2B_normal.csv",
    "attack_surge": HERE / "Lab2B_attack_surge.csv",
}


def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="mixed")
    return df


def series(df, component, metric):
    s = df[(df.component == component) & (df.metric == metric)]
    return s[["elapsed_s", "value"]]


def counters(df):
    """Cumulative counters over time -> ingress / alert backlog (same logic as dashboard)."""
    c = {"generated": 0.0, "detected": 0.0, "alerts": 0.0, "orchestrated": 0.0}
    keymap = {
        ("generator", "events_sent"): "generated",
        ("detector", "events_processed"): "detected",
        ("detector", "alerts_emitted"): "alerts",
        ("orchestrator", "events_processed"): "orchestrated",
    }
    rows = []
    for comp, met, val, t in df[["component", "metric", "value", "elapsed_s"]].itertuples(index=False):
        k = keymap.get((comp, met))
        if k is None:
            continue
        c[k] = max(c[k], val)
        rows.append({"elapsed_s": t, "ingress_backlog": max(0.0, c["generated"] - c["detected"]),
                     "alert_backlog": max(0.0, c["alerts"] - c["orchestrated"])})
    return pd.DataFrame(rows)


def active_rate(df, component, metric):
    """Events / active duration (first to last record of that counter)."""
    s = series(df, component, metric)
    dur = s.elapsed_s.max() - s.elapsed_s.min()
    return s.value.max() / dur if dur > 0 else float("nan"), dur


def utilization(df, component):
    """Estimated per-second utilisation (%) from processing times.

    Each stage_latency_ms record is an operation that ended at its timestamp and lasted
    `value` ms, i.e. busy over [end - value, end]. That busy time is split across every
    1-second bin it overlaps (not charged to the second it ended in). Only complete
    seconds between the first operation start and the last operation end are returned;
    the partial first and last seconds are dropped. Not clipped, so values > 100 % would
    reveal overlapping or mis-timed records.
    """
    st = df[(df.component == component) & (df.metric == "stage_latency_ms")]
    t0 = df["timestamp"].min()
    end = (st["timestamp"] - t0).dt.total_seconds().to_numpy()
    start = end - st["value"].to_numpy() / 1000.0
    first, last = int(np.ceil(start.min())), int(np.floor(end.max()))
    busy = np.zeros(last - first)
    for s, e in zip(start, end):
        for sec in range(max(first, int(np.floor(s))), min(last, int(np.ceil(e)))):
            busy[sec - first] += max(0.0, min(e, sec + 1) - max(s, sec))
    return pd.Series(busy * 100.0, index=range(first, last), name="util_pct")


def window_rates(df):
    """Same-window comparison: completions from t=0 to the last generated event."""
    gen_end = series(df, "generator", "events_sent").elapsed_s.max()
    out = {}
    for comp, met in [("generator", "events_sent"), ("detector", "events_processed"),
                      ("orchestrator", "events_processed")]:
        s = series(df, comp, met)
        out[comp] = s[s.elapsed_s <= gen_end].value.max() / gen_end
    d = series(df, "detector", "events_processed")
    after = d[d.elapsed_s > gen_end]
    done_at_end = d[d.elapsed_s <= gen_end].value.max()
    out["drain"] = ((after.value.max() - done_at_end) / (after.elapsed_s.max() - gen_end)
                    if len(after) > 1 else float("nan"))
    out["gen_end"] = gen_end
    return out


def summarize(name, df):
    run_id = df["label.run_id"].dropna().iloc[0]
    gen_rate, gen_dur = active_rate(df, "generator", "events_sent")
    det_rate, det_dur = active_rate(df, "detector", "events_processed")
    orch_rate, orch_dur = active_rate(df, "orchestrator", "events_processed")
    bl = counters(df)
    w = window_rates(df)
    du, ou = utilization(df, "detector"), utilization(df, "orchestrator")
    return {
        "Run ID / profile": f"{run_id[:8]} / {name}",
        "Events generated / detected / orchestrated": (
            f"{int(series(df,'generator','events_sent').value.max())} / "
            f"{int(series(df,'detector','events_processed').value.max())} / "
            f"{int(series(df,'orchestrator','events_processed').value.max())}"),
        "Mean generator throughput (events/s, rolling 5 s samples)": series(df, "generator", "throughput_eps").value.mean(),
        "Mean detector throughput (events/s, rolling 5 s samples)": series(df, "detector", "throughput_eps").value.mean(),
        "Mean orchestrator throughput (alerts/s, rolling 5 s samples)": series(df, "orchestrator", "throughput_eps").value.mean(),
        "Generator active-period rate (events/s)": gen_rate,
        "Detector active-period rate (events/s)": det_rate,
        "Orchestrator active-period rate (alerts/s)": orch_rate,
        "Generator / detector / orchestrator active duration (s)": f"{gen_dur:.1f} / {det_dur:.1f} / {orch_dur:.1f}",
        "Same window, 0 s to last generated event: gen / det / orch rate (events/s)": (
            f"0–{w['gen_end']:.1f} s: {w['generator']:.1f} / {w['detector']:.1f} / {w['orchestrator']:.1f}"),
        "Detector drain rate after generator stops (events/s)": w["drain"],
        "Maximum ingress backlog (events)": bl.ingress_backlog.max(),
        "Maximum alert backlog (alerts)": bl.alert_backlog.max(),
        "Mean detector utilization (%)": du.mean(),
        "Mean orchestrator utilization (%)": ou.mean(),
        "Detector / orchestrator utilization: seconds ≥ 90 % / seconds averaged": (
            f"{int((du >= 90).sum())}/{len(du)}  ·  {int((ou >= 90).sum())}/{len(ou)}"),
        "Mean detector queue wait (ms)": series(df, "detector", "queue_wait_ms").value.mean(),
        "Mean detector processing (ms)": series(df, "detector", "stage_latency_ms").value.mean(),
        "Mean orchestrator queue wait (ms)": series(df, "orchestrator", "queue_wait_ms").value.mean(),
        "Mean orchestrator processing (ms)": series(df, "orchestrator", "stage_latency_ms").value.mean(),
        "Mean full-pipeline E2E latency (ms)": series(df, "orchestrator", "end_to_end_latency_ms").value.mean(),
        "Max full-pipeline E2E latency (ms)": series(df, "orchestrator", "end_to_end_latency_ms").value.max(),
    }


def main():
    data = {name: load(p) for name, p in RUNS.items()}
    table = pd.DataFrame({name: summarize(name, df) for name, df in data.items()})
    table.index.name = "Measure"
    table.to_csv(HERE / "summary_table.csv")
    with pd.option_context("display.max_colwidth", 60, "display.width", 200):
        print(table.map(lambda v: f"{v:,.1f}" if isinstance(v, float) else v))

    colors = {"generator": "#1f77b4", "detector": "#d62728", "orchestrator": "#2ca02c"}

    # Chart 1: throughput by stage vs elapsed time
    # y-axis is clipped so the steady state is readable; the generator's first-second
    # start-up spike (~270 events/s, rolling window not yet filled) is cut off.
    ylims = {"normal": 50, "attack_surge": 250}
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
    for ax, (name, df) in zip(axes, data.items()):
        for comp in ("generator", "detector", "orchestrator"):
            s = series(df, comp, "throughput_eps")
            ax.plot(s.elapsed_s, s.value, label=comp, color=colors[comp], lw=1.2)
        gen_end = series(df, "generator", "events_sent").elapsed_s.max()
        run_end = series(df, "orchestrator", "events_processed").elapsed_s.max()
        ax.axvline(gen_end, ls="--", color="grey", lw=1)
        if run_end - gen_end > 2:
            ax.axvspan(gen_end, run_end, color="grey", alpha=0.10)
            ax.text((gen_end + run_end) / 2, ylims.get(name, 1) * 0.55, "drain period\n(generator stopped)",
                    ha="center", fontsize=8.5, color="dimgrey")
        ax.set_ylim(0, ylims.get(name))
        ax.set_title(f"Stage throughput — {name}", fontsize=11)
        ax.set_xlabel("Elapsed time (s)", fontsize=10)
        ax.set_ylabel("Throughput (events/s, alerts/s)", fontsize=10)
        ax.tick_params(labelsize=9)
        ax.grid(alpha=.3)
    axes[0].legend(fontsize=9, loc="lower right")
    axes[1].legend(fontsize=9, loc="upper right")
    fig.text(0.5, 0.005, "Dashed line = generator stops. y-axis clipped: first-second generator start-up spike (~270 events/s) not shown.",
             ha="center", fontsize=8, color="grey")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(HERE / "chart_throughput.png", dpi=160)

    # Chart 2: backlog vs elapsed time
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
    for ax, (name, df) in zip(axes, data.items()):
        bl = counters(df)
        ax.plot(bl.elapsed_s, bl.ingress_backlog, label="Ingress (telemetry → detector)", color="#d62728", lw=1.2)
        ax.plot(bl.elapsed_s, bl.alert_backlog, label="Alert (detector → orchestrator)", color="#2ca02c", lw=1.2)
        gen_end = series(df, "generator", "events_sent").elapsed_s.max()
        run_end = series(df, "orchestrator", "events_processed").elapsed_s.max()
        ax.axvline(gen_end, ls="--", color="grey", lw=1, label="Generator stops")
        if run_end - gen_end > 2:
            ax.axvspan(gen_end, run_end, color="grey", alpha=0.10, label="Drain period")
            # Inset: the alert backlog is invisible next to a 4,000+ ingress backlog.
            ins = ax.inset_axes([0.56, 0.56, 0.41, 0.36])
            ins.plot(bl.elapsed_s, bl.alert_backlog, color="#2ca02c", lw=0.8)
            ins.axvline(gen_end, ls="--", color="grey", lw=0.8)
            ins.set_ylim(0, max(20, bl.alert_backlog.max() * 1.2))
            ins.set_title("Alert backlog (zoom)", fontsize=8, pad=2)
            ins.tick_params(labelsize=7)
            ins.grid(alpha=.3)
        ax.set_title(f"Kafka backlog — {name}", fontsize=11)
        ax.set_xlabel("Elapsed time (s)", fontsize=10)
        ax.set_ylabel("Backlog (messages)", fontsize=10)
        ax.tick_params(labelsize=9)
        ax.grid(alpha=.3)
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, fontsize=9, frameon=False)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(HERE / "chart_backlog.png", dpi=160)

    # Chart 3: E2E latency + decomposition
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for ax, (name, df) in zip(axes, data.items()):
        for comp, met, lab, col in [
            ("orchestrator", "end_to_end_latency_ms", "Full-pipeline E2E", "black"),
            ("detector", "queue_wait_ms", "Detector queue wait", "#d62728"),
            ("orchestrator", "queue_wait_ms", "Orchestrator queue wait", "#2ca02c"),
        ]:
            s = series(df, comp, met)
            ax.plot(s.elapsed_s, s.value / 1000.0, label=lab, color=col, lw=1)
        ax.set_title(f"Latency — profile: {name}")
        ax.set_xlabel("Elapsed time (s)")
        ax.set_ylabel("Latency (s)")
        ax.grid(alpha=.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(HERE / "chart_latency.png", dpi=130)


if __name__ == "__main__":
    main()
