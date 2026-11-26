"""Build Lab2B_attack_surge_analysis.pdf from summary_table.csv and the chart PNGs.
Run analyze_lab2b.py first.  Requires: reportlab, pandas.
"""
import math
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).parent
OUT = HERE / "Lab2B_attack_surge_analysis.pdf"

ROWS = [
    "Run ID / profile",
    "Events generated / detected / orchestrated",
    "Mean generator throughput (events/s, rolling 5 s samples)",
    "Mean detector throughput (events/s, rolling 5 s samples)",
    "Mean orchestrator throughput (alerts/s, rolling 5 s samples)",
    "Generator active-period rate (events/s)",
    "Detector active-period rate (events/s)",
    "Orchestrator active-period rate (alerts/s)",
    "Generator / detector / orchestrator active duration (s)",
    "Same window, 0 s to last generated event: gen / det / orch rate (events/s)",
    "Detector drain rate after generator stops (events/s)",
    "Maximum ingress backlog (events)",
    "Maximum alert backlog (alerts)",
    "Mean detector utilization (%)",
    "Mean orchestrator utilization (%)",
    "Detector / orchestrator utilization: seconds ≥ 90 % / seconds averaged",
    "Mean detector queue wait (ms)",
    "Mean detector processing (ms)",
    "Mean orchestrator queue wait (ms)",
    "Mean orchestrator processing (ms)",
    "Mean full-pipeline E2E latency (ms)",
    "Max full-pipeline E2E latency (ms)",
]

LABELS = {  # shorter display names
    "Same window, 0 s to last generated event: gen / det / orch rate (events/s)":
        "Same-window rate, 0 s → last generated event: gen / det / orch (events/s)",
    "Detector / orchestrator utilization: seconds ≥ 90 % / seconds averaged":
        "Seconds with utilization ≥ 90 %: detector · orchestrator",
}
DERIVED = {
    "Maximum ingress backlog (events)": "†",
    "Maximum alert backlog (alerts)": "†",
    "Mean detector utilization (%)": "‡ estimate",
    "Mean orchestrator utilization (%)": "‡ estimate",
    "Detector / orchestrator utilization: seconds ≥ 90 % / seconds averaged": "‡ estimate",
}


def fmt(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return "n/a (no backlog)" if math.isnan(f) else f"{f:,.1f}"


def main():
    t = pd.read_csv(HERE / "summary_table.csv", index_col=0)
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.3, leading=10.3, spaceAfter=2.5)
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=13.5, spaceAfter=3)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=10.5, spaceBefore=4, spaceAfter=2)
    small = ParagraphStyle("s", parent=body, fontSize=7.2, leading=9, textColor=colors.HexColor("#555555"))

    data = [["Measure", "Normal run", "High-load run (attack_surge)"]]
    for r in ROWS:
        label = LABELS.get(r, r)
        if r in DERIVED:
            label = f"{label}  [{DERIVED[r]} derived]"
        data.append([label, fmt(t.loc[r, "normal"]), fmt(t.loc[r, "attack_surge"])])
    table = Table(data, colWidths=[10.2 * cm, 3.3 * cm, 4.5 * cm])
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7.3),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.6),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4b2e83")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef0f7")]),
        ("BACKGROUND", (0, 10), (-1, 11), colors.HexColor("#fff4d6")),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c8c8d8")),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
    ]))

    P = lambda s: Paragraph(s, body)
    story = [
        Paragraph("Lab 2b — High-Load Cybersecurity: Analysis (Morpheus Lite v0.3.4)", h1),
        Paragraph("Assigned profile: <b>attack_surge</b> (5000 events) compared with <b>normal</b> (500 events). "
                  "Normal run_id 881e71e6-07f1-4f14-9114-73c0ab292fe4; attack_surge run_id "
                  "4e981da1-06eb-445c-bf22-de1174241f08. Source: dashboard CSV exports only. Environment check: "
                  "<b>python -m pytest -q → 14 passed in 0.65 s</b>. All services (Redpanda in Docker, generator, "
                  "detector, orchestrator, dashboard) ran on one Windows 10 laptop; one run per profile.", small),
        Spacer(1, 3),
        Paragraph("1. Summary statistics", h2),
        table,
        Spacer(1, 2),
        Paragraph(
            "<b>Rate windows.</b> <i>Active-period</i> rate = final counter ÷ time between that stage's first and last "
            "record (generator ≈32 s, detector/orchestrator ≈175 s, so these windows differ). The highlighted "
            "<i>same-window</i> rows compare all stages over the generator's window and then give the detector's rate "
            "during the drain. <b>† Backlog</b> is not a CSV column: it is the running difference of cumulative "
            "counters (ingress = generator.events_sent − detector.events_processed; alert = detector.alerts_emitted − "
            "orchestrator.events_processed), the same rule the dashboard uses. <b>‡ Utilization is an estimate</b> from "
            "processing times: each stage_latency_ms record is treated as busy time [end − duration, end], split across "
            "every 1-second bin it overlaps, and averaged over the complete seconds between the stage's first start and "
            "last end (partial first/last seconds excluded; no bin exceeded 100 %). It counts only time inside the "
            "timed stage, not Kafka polling or metric writes. <b>Completeness:</b> latency means use the records "
            "available per metric (e.g. 4,963 E2E and 4,961 detector-processing samples for 5,000 events). 378 of "
            "74,647 lines (0.5 %) in the internal metrics log are unparseable, consistent with three processes "
            "appending to one file at once; the cumulative counters still reach 5,000, so the gaps do not indicate lost "
            "events. E2E = orchestrator completion time − generator timestamp.", small),
        Paragraph("2. Charts", h2),
        Image(str(HERE / "chart_throughput.png"), width=17.5 * cm, height=7.0 * cm),
        Image(str(HERE / "chart_backlog.png"), width=17.5 * cm, height=7.0 * cm),
        Paragraph("3. Engineering analysis", h2),
        P("<b>Offered load vs target.</b> attack_surge requests 500 events/s (label.target_rate), but the local Python "
          "generator delivered <b>157.3 events/s</b> over its 31.8 s window, about 31.5 % of target. The effect of "
          "actually arriving at 500 events/s was not measured in this experiment; the results below describe the "
          "157 events/s that did arrive."),
        P("<b>Q6 — Bottleneck: the detector.</b> (a) <i>Same window</i> (0–31.8 s, until the last event was generated): "
          "generator 5,000 events (157.3 events/s), detector 637 (<b>20.0 events/s</b>), orchestrator 637 (20.0 "
          "alerts/s). That gap, ≈137 events/s, is exactly the ingress backlog's growth rate (4,363 ÷ 31.8 s). (b) The "
          "ingress backlog peaked at 4,363 events, 8.7× the 500-message reference value shown in the dashboard; that "
          "value is high_load.queue_capacity in settings.yaml and is used only for the dashboard display and status "
          "thresholds, not as a limit on the Kafka topic. The alert backlog never exceeded 15. (c) Detector queue wait "
          "averaged 77,884 ms versus 31.1 ms of detector processing. (d) <b>CPU contention, measured:</b> during the "
          "generator window the detector took 43.7 ms per event and managed 20.0 events/s (the mid-run screenshot "
          "shows 380 detected at ≈19 s); in the drain period, with the generator stopped, it took 29.3 ms and "
          "drained at <b>30.3 events/s</b>. The orchestrator slowed the same way (36.6 vs 28.6 ms per event)."),
        P("<b>Q7 — Backlog trend.</b> <i>Active period</i> (0–31.8 s): the ingress backlog <b>grew</b> almost linearly at "
          "≈137 events/s and peaked when generation stopped. <i>Drain period</i> (31.8–175 s, shaded in the charts): "
          "it <b>drained</b> linearly at 30.3 events/s, reaching zero at ≈175 s. So it never stabilized or drained while "
          "events were arriving. In the normal run the only backlog was a 32-alert start-up spike at the "
          "orchestrator, cleared by 6.7 s while generation continued."),
        P("<b>Q8 — Queue wait vs processing.</b> attack_surge E2E was dominated by <b>queue waiting</b>: mean E2E "
          "78,279 ms ≈ detector queue wait 77,884 ms + orchestrator wait 210 ms + ≈61 ms of processing (&lt;0.1 % of "
          "E2E). In steady-state normal operation (after 7 s) E2E was ≈60.5 ms, ≈58 ms of it processing."),
        P("<b>Q9 — Did the orchestrator keep pace?</b> Yes. It matched the detector in both windows (20.0 = 20.0 during "
          "generation; 28.5 = 28.5 over the whole run), orchestrated all 5,000 alerts, and its backlog stayed ≤15 "
          "(mean queue wait 0.2 s). Its processing time (28.6 ms uncontended) is close to the detector's, so it was "
          "kept clear mainly because the detector limited its input."),
        P("<b>Q10 — Earliest warning: detector queue wait / ingress backlog.</b> Queue wait passed 1 s at t = 1.29 s, and "
          "the ingress backlog crossed the dashboard's OVERLOADED level (85 % of 500 = 425) at t = 2.14 s. Estimated "
          "detector utilization first reached 90 % in the 6–7 s bin and was ≥90 % in only 25 of 174 seconds (mean "
          "87.9 %). It also stayed flat across the contention change (86.5 % during generation vs 88.1 % in the drain) "
          "because longer processing offset the lower throughput, so it is a weak overload signal here. The screenshot "
          "(≈19 s) shows OVERLOADED, ingress backlog 2,620 / 500 and detector queue wait 12.6 s."),
        P("<b>Q11 — Recommended improvement: scale the detector out.</b> Partition the telemetry topic and run detector "
          "consumers in one consumer group, keyed by user/host. <i>Preliminary planning estimate</i> for 500 events/s, "
          "assuming linear scaling and enough partitions, broker capacity and CPU: at the uncontended 30.3 events/s "
          "measured per instance, ≥17 instances at full load or ≈24 to stay under 70 % utilization; at the contended "
          "20.0 events/s, ≈25 and ≈36. The orchestrator's saturated rate was not measured; its 28.6 ms processing time "
          "suggests ≈35 alerts/s each, so ≈15–21 instances, and it would become the next bottleneck if only the detector "
          "were scaled. These figures need a test at the higher rate before being relied on. <i>Security "
          "trade-off:</i> per-user fingerprinting and Isolation-Forest state split across instances unless events are "
          "keyed by user/host; poor keying weakens behavioural baselines and lets an attacker's events spread across "
          "shards. Load shedding or sampling low-risk events is cheaper but risks dropping real attack telemetry."),
        P("<b>Q12 — High-load vs normal.</b> Normal: all stages matched at ≈24.9 events/s in the same window, ingress "
          "backlog ≤4, mean E2E 284 ms (≈60 ms steady state), status NORMAL. attack_surge: 6.3× higher arrival rate "
          "(157.3 vs 24.9 events/s), detector at 20.0 events/s during generation and 30.3 in the drain, backlog 4,363, "
          "mean E2E 78 s (max 144 s), status OVERLOADED, and 175 s to process 32 s of traffic. Every event in both runs "
          "produced an alert (500/500, 5000/5000)."),
    ]
    SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                      topMargin=1.1 * cm, bottomMargin=1.1 * cm,
                      title="Lab 2b analysis — attack_surge").build(story)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
