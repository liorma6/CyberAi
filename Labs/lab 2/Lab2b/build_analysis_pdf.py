"""Build Lab2B_attack_surge_analysis.pdf from summary_table.csv and the chart PNGs.
Run analyze_lab2b.py first.  Requires: reportlab, pandas.
"""
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
    "Maximum ingress backlog (events)",
    "Maximum alert backlog (alerts)",
    "Mean detector utilization (%)",
    "Mean orchestrator utilization (%)",
    "Mean detector queue wait (ms)",
    "Mean detector processing (ms)",
    "Mean orchestrator queue wait (ms)",
    "Mean orchestrator processing (ms)",
    "Mean full-pipeline E2E latency (ms)",
    "Max full-pipeline E2E latency (ms)",
]


def fmt(v):
    try:
        return f"{float(v):,.1f}"
    except (TypeError, ValueError):
        return str(v)


def main():
    t = pd.read_csv(HERE / "summary_table.csv", index_col=0)
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.6, leading=11, spaceAfter=3)
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=14, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=10.5, spaceBefore=6, spaceAfter=3)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, textColor=colors.grey)

    derived = {
        "Maximum ingress backlog (events)": "† derived",
        "Maximum alert backlog (alerts)": "† derived",
        "Mean detector utilization (%)": "‡ derived",
        "Mean orchestrator utilization (%)": "‡ derived",
    }
    data = [["Measure", "Normal run", "High-load run (attack_surge)"]]
    data += [[f"{r}  [{derived[r]}]" if r in derived else r,
              fmt(t.loc[r, "normal"]), fmt(t.loc[r, "attack_surge"])] for r in ROWS]
    table = Table(data, colWidths=[9.2 * cm, 3.6 * cm, 4.6 * cm])
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7.6),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4b2e83")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef0f7")]),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c8c8d8")),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]))

    P = lambda s: Paragraph(s, body)
    story = [
        Paragraph("Lab 2b — High-Load Cybersecurity: Analysis (Morpheus Lite v0.3.4)", h1),
        Paragraph("Assigned profile: <b>attack_surge</b> (5000 events) compared with "
                  "<b>normal</b> (500 events) &nbsp;|&nbsp; Normal run_id 881e71e6-07f1-4f14-9114-73c0ab292fe4; "
                  "attack_surge run_id 4e981da1-06eb-445c-bf22-de1174241f08. Source: dashboard CSV exports only. "
                  "Environment check: <b>python -m pytest -q → 14 passed in 0.65 s</b>. All services (Redpanda in Docker, "
                  "generator, detector, orchestrator, dashboard) on one Windows 10 laptop.", small),
        Spacer(1, 4),
        Paragraph("1. Summary statistics", h2),
        table,
        Paragraph("<b>Derived rows</b> are not columns in the CSV; they are computed from it. "
                  "<b>†</b> Backlog = running max of the cumulative counters: ingress = generator.events_sent − "
                  "detector.events_processed; alert = detector.alerts_emitted − orchestrator.events_processed (same rule "
                  "as the dashboard). <b>‡</b> Utilization per 1-second bin = events completed × mean stage_latency_ms / 1000 "
                  "(busy fraction of that second), averaged over the stage's active period. All other rows are means/maxima "
                  "of metrics recorded directly in the CSV. Throughput is shown two ways: the mean of the rolling 5-second "
                  "rate samples, and the active-period rate (final counter ÷ time between that stage's first and last "
                  "record), which excludes idle time. E2E latency = orchestrator completion time − generator timestamp.", small),
        Paragraph("2. Charts", h2),
        Image(str(HERE / "chart_throughput.png"), width=18 * cm, height=7.2 * cm),
        Image(str(HERE / "chart_backlog.png"), width=18 * cm, height=7.2 * cm),
        Paragraph("3. Engineering analysis", h2),
        P("<b>Offered load vs target.</b> The attack_surge profile targets 500 events/s (label.target_rate = 500), but the "
          "single local Python generator reached only <b>157.9 events/s</b> over its active period (≈32 % of target; "
          "168.4 events/s mean of rolling samples). The measured overload is therefore a <i>lower bound</i>: at the full "
          "target rate the arrival/service gap would be ≈3.2× larger."),
        P("<b>Q6 — Bottleneck.</b> The <b>detector</b>. (a) Arrivals averaged 157.9 events/s during the 31.7 s generator "
          "window, while the detector completed only 28.5 events/s — a ≈5.5× arrival/service ratio (≈17.5× at the "
          "500 events/s target). (b) The ingress topic (telemetry → detector) backlog peaked at 4,363 events, 8.7× the "
          "dashboard's 500-message backlog threshold (Kafka itself has no such limit), while the alert backlog (detector → orchestrator) never exceeded 15. "
          "(c) Detector queue wait averaged 77,884 ms versus 31.1 ms of actual detector processing. With ≈31.1 ms per "
          "event the detector's ceiling is ≈1000/31.1 ≈ 32 events/s, consistent with the observed plateau at ~29 events/s "
          "and 87.6 % utilization. (d) <b>CPU contention, measured:</b> while the generator was running (0–31.8 s) the "
          "detector completed only 637 events (<b>20.1 events/s</b>, 43.7 ms per event; the mid-run screenshot shows "
          "380 detected at ≈19 s). After the generator stopped it ran at <b>30.3 events/s</b> (29.3 ms per event). The "
          "orchestrator slowed the same way (36.6 vs 28.6 ms). Sharing one machine with the generator cost the detector "
          "about a third of its capacity, so per-instance capacity under load is ≈20–23 events/s, not 32."),
        P("<b>Q7 — Backlog trend.</b> During the active period (0–31.8 s) the ingress backlog <b>grew</b> almost linearly at "
          "≈137 events/s. It peaked exactly when the generator stopped (t = 31.8 s) "
          "and then <b>drained</b> linearly at ≈30 events/s, reaching zero at ≈175 s, so drainage happened only "
          "<i>after</i> the generator stopped. In the normal run the backlog was transient: a 32-alert start-up spike at "
          "the orchestrator drained by 6.7 s while the generator was "
          "still running."),
        P("<b>Q8 — Queue wait vs processing.</b> Under attack_surge E2E latency was overwhelmingly <b>queue waiting</b>: "
          "mean E2E 78,279 ms ≈ detector queue wait 77,884 ms + orchestrator wait 210 ms + ~61 ms of processing; processing "
          "is &lt;0.1 % of E2E. In steady-state normal operation (after 7 s) E2E was ≈60.5 ms, of which ≈58 ms was "
          "processing and ≈4 ms orchestrator queue wait, so it was processing-dominated."),
        P("<b>Q9 — Did the orchestrator keep pace?</b> Yes. Orchestrator active-period rate 28.5 alerts/s equals the detector "
          "rate (28.5 events/s), all 5000 alerts were orchestrated, alert backlog stayed ≤15 and orchestrator queue wait "
          "averaged 0.2 s. However, its own service time (29.6 ms ⇒ ≈34 alerts/s ceiling, 83.2 % utilization) is almost "
          "identical to the detector's, so it is only shielded because the detector throttles its input."),
        P("<b>Q10 — Earliest warning.</b> <b>Detector queue wait / ingress backlog.</b> Queue wait exceeded 1 s at "
          "t = 1.29 s and the ingress backlog crossed the dashboard's critical level (85 % of 500 = 425) at t = 2.14 s, "
          "which switches the status to OVERLOADED. Per-second detector utilization first touched 90 % in the 2–3 s bin, "
          "but it is noisy (70–91 % in the first 12 s, ≥90 % in only 50 of 176 seconds, mean 87.6 %), so it is a weaker "
          "signal than queue wait, which rose monotonically. The dashboard screenshot was taken "
          "mid-run (≈19 s): status OVERLOADED, ingress backlog 2,620 / 500, detector queue wait 12.6 s."),
        P("<b>Q11 — Recommended improvement (sized to the 500 events/s target).</b> Scale the detector horizontally: "
          "partition the telemetry topic and run detector consumers in one consumer group, keyed by user/host. At ≈32 "
          "events/s per instance, 500 events/s needs ≥16 instances at 100 % utilization, or <b>≈23 instances</b> to stay "
          "under the 70 % warning threshold (500 / (32.2 × 0.7)), so provision ≥24 partitions. This assumes instances on "
          "hosts separate from the producers; at the contended ≈20 events/s measured in Q6(d), 500 events/s would need "
          "≈36 instances, so isolating the detector from other CPU load is part of the fix. Because every event became "
          "an alert, the orchestrator needs the same: ≈34 alerts/s each ⇒ ≥15 instances, ≈22 at 70 %. Scaling only the "
          "detector would move the bottleneck straight to the orchestrator. <i>Security trade-off:</i> per-user "
          "fingerprinting and Isolation-Forest state become split across instances unless events are keyed by user/host; "
          "poor keying weakens behavioural baselines and can let an attacker's events spread across shards. The cheaper "
          "alternative, load shedding or sampling low-risk events, reduces latency but risks dropping true attack "
          "telemetry."),
        P("<b>Q12 — High-load vs normal.</b> Normal: all stages matched at ≈25 events/s, ingress backlog ≤4, mean E2E "
          "284 ms (60 ms steady state), status NORMAL. attack_surge: 6.3× higher arrival rate, detector capped at "
          "≈29 events/s, backlog 4,363, mean E2E 78 s (max 144.1 s), status OVERLOADED, and the pipeline needed 175 s to "
          "process 32 s of traffic. Every event in both runs produced an alert (500/500 and 5000/5000), so alert volume "
          "scaled 1:1 with telemetry."),
    ]
    SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                      topMargin=1.2 * cm, bottomMargin=1.2 * cm,
                      title="Lab 2b analysis — attack_surge").build(story)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
