# Lab 2b — Reflection: evidence versus intuition

**Profile:** attack_surge (5000 events) vs normal (500 events)
**Run IDs:** attack_surge `dc6e32cf-e7da-4fce-acc8-5b7c31e327ed`, normal `881e71e6-07f1-4f14-9114-73c0ab292fe4`

## What did the dashboard initially suggest?
The lab guide primes you to expect **orchestrator pressure** in attack_surge, because the orchestrator runs the
"agent" stage (XAI, RAI, Meta-AI) and does more work per alert. The final dashboard view, captured after the queues
drained, also looked fairly calm. It showed **HIGH LOAD** rather than OVERLOADED, ingress and alert backlog both at
0/500, and detector and orchestrator throughput both about 30/s. The headline figure "Generated events/s 215.5" is only
the last rolling sample. The one strong signal on screen was a detector queue wait of about 136 s, which is the last
200 samples, not the run mean.

## What did the CSV confirm or contradict?
- **Contradicted** the orchestrator-pressure hypothesis. The alert backlog never went above 28 and orchestrator queue
  wait averaged 0.4 s. The **detector** was the stage that could not keep up.
- **Contradicted** the "0 / 500 backlog" reading. Rebuilding the counters over time shows the ingress backlog peaked at
  **4,323 events**, 8.6× the configured capacity, at the moment the generator stopped. The dashboard snapshot only shows
  the current value, so it hid the peak completely.
- **Confirmed** that latency was almost all queue waiting. Mean E2E was 72.4 s, against about 58 ms of real processing.
- **Confirmed** that the backlog drained only after the generator stopped. It fell linearly at about 30 events/s, so
  28 s of traffic took 167 s to process.

The conclusion that relied most on quantitative evidence was **which stage is the bottleneck**. The detector and the
orchestrator have nearly the same service time (29.7 ms vs 28.6 ms). From the architecture alone, either could have
been the bottleneck. Only the per-queue backlog and queue-wait series in the CSV separate them.

## What uncertainty remains in the bottleneck diagnosis?
- The orchestrator is only about 4 % faster than the detector. With the detector scaled out, the orchestrator becomes
  the next bottleneck almost immediately. The diagnosis describes this machine and this configuration, not a fixed
  property of the design.
- Every process (generator, detector, orchestrator, dashboard, Redpanda in Docker) ran on one Windows laptop. CPU
  contention probably inflated the detector's roughly 29 ms service time, which is far above the configured 2 ms
  artificial delay.
- Utilization peaked near 88 % instead of 100 % even though the queue was saturated. Some per-event time (Kafka
  poll/commit, metrics file writes) falls outside the measured "stage" window, so utilization understates true busy
  time. Utilization never reached the 90 % "critical" threshold. The OVERLOADED state can only have come from the
  backlog rule (backlog ≥ 425).
- This is a single run per profile, with no repetitions and no confidence intervals.

## What would I change in the architecture, and why?
1. **Partition the telemetry topic and run several detector consumers** in one consumer group, keyed by user/host so
   per-user fingerprints stay consistent. Then scale the orchestrator the same way. The evidence shows a single
   detector caps the whole pipeline at about 30 events/s.
2. **Alert on queue-wait and backlog growth rate, not utilization.** Queue wait passed 1 s at t = 1.3 s, while
   utilization never crossed the critical threshold.
3. **Show peak backlog and peak E2E latency on the dashboard**, not only the current values. The post-drain snapshot
   gives a misleadingly healthy picture of an overload event.
4. Possibly add **risk-based prioritisation**, so high-risk events skip ahead in the queue during a surge. The
   trade-off is that low-priority telemetry, which may still carry early signs of an attack, is delayed further.
