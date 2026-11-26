"""Build Lab2B_STUDENTID_attack_surge_analysis.pdf from summary_table.csv and the chart PNGs.
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
OUT = HERE / "Lab2B_STUDENTID_attack_surge_analysis.pdf"

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

    data = [["Measure", "Normal run", "High-load run (attack_surge)"]]
    data += [[r, fmt(t.loc[r, "normal"]), fmt(t.loc[r, "attack_surge"])] for r in ROWS]
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
        Paragraph("Student ID: STUDENTID &nbsp;|&nbsp; Assigned profile: <b>attack_surge</b> (5000 events) compared with "
                  "<b>normal</b> (500 events) &nbsp;|&nbsp; Normal run_id 881e71e6-07f1-4f14-9114-73c0ab292fe4; "
                  "attack_surge run_id dc6e32cf-e7da-4fce-acc8-5b7c31e327ed. Source: dashboard CSV exports only.", small),
        Spacer(1, 4),
        Paragraph("1. Summary statistics", h2),
        table,
        Paragraph("Throughput is reported two ways: the mean of the per-event rolling 5-second rate samples written by each "
                  "stage, and the active-period rate (final counter ÷ time between that stage's first and last record), "
                  "which excludes idle time. Utilization is computed per 1-second bin as (events completed × mean stage "
                  "processing ms) / 1000, i.e. the busy fraction of each second, then averaged over the active period. "
                  "E2E latency = orchestrator completion time − generator timestamp.", small),
        Paragraph("2. Charts", h2),
        Image(str(HERE / "chart_throughput.png"), width=17.5 * cm, height=5.8 * cm),
        Image(str(HERE / "chart_backlog.png"), width=17.5 * cm, height=5.8 * cm),
        Paragraph("3. Engineering analysis", h2),
        P("<b>Q6 — Bottleneck.</b> The <b>detector</b>. (a) Arrivals averaged 177.5 events/s during the 28.2 s generator "
          "window, while the detector completed only 29.9 events/s — a ≈5.9× arrival/service ratio. (b) The ingress topic "
          "(telemetry → detector) backlog peaked at 4,323 events, 8.6× the configured 500-message capacity, while the "
          "alert backlog (detector → orchestrator) never exceeded 28. (c) Detector queue wait averaged 71,931 ms versus "
          "29.7 ms of actual detector processing. With ≈29.7 ms per event the detector's theoretical ceiling is "
          "≈1000/29.7 ≈ 34 events/s, consistent with the observed plateau at ~30 events/s and 87.6 % utilization."),
        P("<b>Q7 — Backlog trend.</b> During the active period (0–28 s) the ingress backlog <b>grew</b> almost linearly at "
          "≈150 events/s (stair-steps match the 500-event bursts). It peaked exactly when the generator stopped and then "
          "<b>drained</b> linearly at ≈30 events/s, reaching zero at ≈167 s — i.e. drainage happened only <i>after</i> the "
          "generator stopped. In the normal run the backlog was transient: a 32-alert start-up spike at the orchestrator "
          "(it began consuming ~1.5 s after the first alert) drained by 6.7 s while the generator was still running."),
        P("<b>Q8 — Queue wait vs processing.</b> Under attack_surge E2E latency was overwhelmingly <b>queue waiting</b>: "
          "mean E2E 72,421 ms ≈ detector queue wait 71,931 ms + orchestrator wait 409 ms + ~58 ms of processing; processing "
          "is &lt;0.1 % of E2E. In steady-state normal operation (after 7 s) E2E was ≈60.5 ms, of which ≈58 ms was "
          "processing and ≈4 ms orchestrator queue wait — processing-dominated."),
        P("<b>Q9 — Did the orchestrator keep pace?</b> Yes. Orchestrator active-period rate 29.9 alerts/s equals the detector "
          "rate (29.9 events/s), all 5000 alerts were orchestrated, alert backlog stayed ≤28 and orchestrator queue wait "
          "averaged 0.4 s. Note, however, that its own service time (28.6 ms ⇒ ≈35 alerts/s ceiling, 84.4 % utilization) is "
          "almost identical to the detector's, so it is only shielded because the detector throttles its input."),
        P("<b>Q10 — Earliest warning.</b> <b>Detector queue wait / ingress backlog.</b> Queue wait exceeded 1 s at "
          "t = 1.31 s and the ingress backlog was already &gt;450 by t ≈ 2 s, while detector throughput looked flat and "
          "utilization stayed below the 90 % critical threshold for the whole run (max ≈88 %). By the dashboard's own "
          "rule the status turns OVERLOADED once backlog ≥85 % of capacity (425), which the ingress backlog crossed at "
          "≈2 s; utilization alone would only ever have signalled 'HIGH LOAD'. The screenshot was taken after drainage, "
          "so it shows HIGH LOAD with 0/500 backlog."),
        P("<b>Q11 — Recommended improvement.</b> Scale the detector horizontally: partition the telemetry topic (e.g. 6–8 "
          "partitions) and run several detector consumers in one consumer group (≈34 ev/s each ⇒ ≥6 instances for "
          "177 ev/s), then scale the orchestrator similarly since it is the next bottleneck. <i>Security trade-off:</i> "
          "per-user fingerprinting and Isolation-Forest state become split across instances unless events are keyed by "
          "user/host; poor keying weakens behavioural baselines and can let an attacker's events spread across shards. "
          "The cheaper alternative — load shedding or sampling of low-risk events — reduces latency but risks dropping "
          "true attack telemetry."),
        P("<b>Q12 — High-load vs normal.</b> Normal: all stages matched at ≈25 events/s, ingress backlog ≤4, mean E2E "
          "284 ms (60 ms steady state), status NORMAL. attack_surge: 7× higher arrival rate, detector capped at ≈30 ev/s, "
          "backlog 4,323, mean E2E 72 s (max 139.6 s), and the pipeline needed 167 s to process 28 s of traffic. Every "
          "event in both runs produced an alert (500/500 and 5000/5000), so alert volume scaled 1:1 with telemetry."),
    ]
    SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                      topMargin=1.2 * cm, bottomMargin=1.2 * cm,
                      title="Lab 2b analysis — attack_surge").build(story)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
