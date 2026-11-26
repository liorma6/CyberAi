# Lab 2b — Reflection: evidence versus intuition

**Profile:** attack_surge (5000 events) vs normal (500 events)
**Run IDs:** attack_surge `4e981da1-06eb-445c-bf22-de1174241f08`, normal `881e71e6-07f1-4f14-9114-73c0ab292fe4`

## What did the dashboard initially suggest?
The lab guide primes you to expect **orchestrator pressure** in attack_surge, because the orchestrator runs the
"agent" stage (XAI, RAI, Meta-AI) and does more work per alert. The mid-run dashboard (about 19 s in) pointed
elsewhere straight away. Status was **OVERLOADED**, ingress backlog was 2,620 / 500, detector queue wait was 12.6 s,
and the alert backlog was only 2 / 500. Some figures on screen were still misleading:
- **Single samples, not averages.** "Generated events/s 174.0" and "Detector events/s 19.7" are the latest samples.
  The detector's average over the run was 28.5/s.
- **The snapshot depends on timing.** In an earlier attempt (run `dc6e32cf`), I captured the dashboard only after the
  queues had drained. It showed HIGH LOAD with 0 / 500 backlog, which looks calm for a run that had a 4,300-event
  backlog. That is why I reran the profile and took the screenshot while the backlog was above 425.

## What did the CSV confirm or contradict?
- **Contradicted** the orchestrator-pressure hypothesis. The alert backlog never went above 15 and orchestrator queue
  wait averaged 0.2 s. The **detector** was the stage that could not keep up.
- **Added the peak the dashboard cannot show.** Rebuilding the counters over time shows the ingress backlog peaked at
  **4,363 events**, 8.7× the dashboard's 500-message backlog threshold (Kafka itself has no such limit), at t = 31.8 s when the generator stopped. The dashboard only ever
  shows the current value.
- **Confirmed** that latency was almost all queue waiting. Mean E2E was 78.3 s, against about 61 ms of real processing.
- **Confirmed** that the backlog drained only after the generator stopped. It fell linearly at about 30 events/s, so
  32 s of traffic took 175 s to process.
- **Revealed the offered load was below target.** The profile targets 500 events/s, but the generator delivered only
  157.9 events/s. The real overload at the target rate would be about 3.2× worse.

The conclusion that relied most on quantitative evidence was **which stage is the bottleneck**. The detector and the
orchestrator have nearly the same service time (31.1 ms vs 29.6 ms). From the architecture alone, either could have
been the bottleneck. Only the per-queue backlog and queue-wait series separate them.

## What uncertainty remains in the bottleneck diagnosis?
- The orchestrator is only about 5 % faster than the detector. With the detector scaled out, the orchestrator becomes
  the next bottleneck almost immediately. The diagnosis describes this machine and this configuration, not a fixed
  property of the design.
- Every process (generator, detector, orchestrator, dashboard, Redpanda in Docker) ran on one Windows laptop, and the
  CSV shows this CPU contention directly:
  - **While the generator ran (0–31.8 s):** the detector completed only 637 events, 20.1 events/s at 43.7 ms per
    event. The mid-run screenshot agrees: 380 detected at about 19 s.
  - **After the generator stopped:** the same detector ran at 30.3 events/s and 29.3 ms per event.
  - **Orchestrator:** it slowed the same way, 36.6 ms vs 28.6 ms per event.

  So the detector lost about a third of its capacity while it competed with the generator. The generator was limited
  too, reaching about 32 % of its target rate. Even uncontended, about 29 ms is far above the configured 2 ms
  artificial delay, so most of the service time is real model and Kafka work.
- Utilization is a derived and noisy measure. It averaged 87.6 % and was at or above 90 % in only 50 of 176 seconds,
  even though the queue was saturated the whole time. Some per-event time (Kafka poll/commit, metrics file writes)
  falls outside the measured "stage" window, so utilization understates true busy time.
- The sizing in the recommendation (about 23 detector instances for 500 events/s) assumes linear scaling. That
  assumption fails if Redpanda, the shared fingerprint state, or the host CPU becomes the limit first.
- This is a single measured run per profile, with no repetitions and no confidence intervals.

## What would I change in the architecture, and why?
1. **Partition the telemetry topic and run several detector consumers** in one consumer group, keyed by user/host so
   per-user fingerprints stay consistent. Size for the 500 events/s target: about 23 detector instances to stay
   under 70 % utilization, on hosts kept separate from the producers. At the contended 20 events/s it would take
   about 36. Then scale the orchestrator the same way (about 22 instances), since every event became
   an alert.
2. **Alert on queue wait and backlog growth rate, not utilization.** Queue wait passed 1 s at t = 1.3 s and rose
   steadily. Utilization moved between 70 % and 91 % in the same period.
3. **Show peak backlog and peak E2E latency on the dashboard**, not only the current values. A screenshot taken after
   drainage gives a misleadingly healthy picture of an overload event.
4. Possibly add **risk-based prioritisation**, so high-risk events skip ahead in the queue during a surge. The
   trade-off is that low-priority telemetry, which may still carry early signs of an attack, is delayed further.
