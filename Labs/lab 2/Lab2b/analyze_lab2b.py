"""Lab 2b analysis: summary statistics + charts from the exported dashboard CSVs.

Usage (from this folder):  python analyze_lab2b.py
Inputs : Lab2B_normal.csv, Lab2B_attack_surge.csv
Outputs: summary_table.csv, chart_throughput.png, chart_backlog.png, chart_latency.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
    """Per-second utilisation = events completed in that second x mean stage ms / 1000 (as %)."""
    st = series(df, component, "stage_latency_ms").copy()
    st["sec"] = st.elapsed_s.astype(int)
    g = st.groupby("sec").agg(n=("value", "size"), ms=("value", "mean"))
    u = (g.n * g.ms / 10.0).clip(upper=100.0)
    return u


def summarize(name, df):
    run_id = df["label.run_id"].dropna().iloc[0]
    gen_rate, gen_dur = active_rate(df, "generator", "events_sent")
    det_rate, det_dur = active_rate(df, "detector", "events_processed")
    orch_rate, orch_dur = active_rate(df, "orchestrator", "events_processed")
    bl = counters(df)
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
        "Maximum ingress backlog (events)": bl.ingress_backlog.max(),
        "Maximum alert backlog (alerts)": bl.alert_backlog.max(),
        "Mean detector utilization (%)": utilization(df, "detector").mean(),
        "Mean orchestrator utilization (%)": utilization(df, "orchestrator").mean(),
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
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for ax, (name, df) in zip(axes, data.items()):
        for comp in ("generator", "detector", "orchestrator"):
            s = series(df, comp, "throughput_eps")
            ax.plot(s.elapsed_s, s.value, label=comp, color=colors[comp], lw=1)
        ax.set_title(f"Stage throughput — profile: {name}")
        ax.set_xlabel("Elapsed time (s)")
        ax.set_ylabel("Throughput (events/s or alerts/s)")
        ax.grid(alpha=.3)
        ax.legend()
    fig.tight_layout()
    fig.savefig(HERE / "chart_throughput.png", dpi=130)

    # Chart 2: backlog vs elapsed time
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for ax, (name, df) in zip(axes, data.items()):
        bl = counters(df)
        ax.plot(bl.elapsed_s, bl.ingress_backlog, label="Ingress backlog (telemetry → detector)", color="#d62728")
        ax.plot(bl.elapsed_s, bl.alert_backlog, label="Alert backlog (detector → orchestrator)", color="#2ca02c")
        gen_end = series(df, "generator", "events_sent").elapsed_s.max()
        ax.axvline(gen_end, ls="--", color="grey", lw=1)
        ax.text(gen_end, ax.get_ylim()[1] * .9, " generator stops", color="grey", fontsize=8)
        ax.set_title(f"Kafka backlog — profile: {name}")
        ax.set_xlabel("Elapsed time (s)")
        ax.set_ylabel("Backlog (messages)")
        ax.grid(alpha=.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(HERE / "chart_backlog.png", dpi=130)

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
