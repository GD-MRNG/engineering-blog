---
layout: post
title: "2.5.1 Delivery vs Deployment: The Most Important Distinction in CD"
author: "Glenn Lum"
date:   2026-02-27 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most teams that say they practice continuous delivery or continuous deployment cannot clearly describe the structural difference between the two pipelines. They know one involves a manual step and the other doesn't, but they treat the distinction as a preference — like choosing between a manual and automatic transmission. It is not a preference. It is an architectural decision about where risk accountability lives in your system, and it produces fundamentally different feedback loops, failure modes, and organizational behaviors. Getting it wrong doesn't just mean your pipeline is suboptimal. It means the pipeline you built is actively misaligned with how your organization actually makes release decisions, and that misalignment creates a slow, compounding drag on your ability to ship safely.

## The Pipeline Is Identical Until the Last Gate

Here is the part most discussions skip: a continuous delivery pipeline and a continuous deployment pipeline are structurally identical for roughly 90% of their length. Both start with a commit. Both run unit tests, integration tests, static analysis. Both produce a versioned, immutable artifact. Both deploy that artifact to one or more pre-production environments and run further validation — contract tests, smoke tests, performance tests, whatever your confidence model requires.

The divergence happens at exactly one point: what happens after the artifact has passed every automated quality gate and is sitting in a state where it *could* go to production.

In **continuous deployment**, the pipeline treats "passed all gates" as sufficient. The artifact proceeds to production automatically. There is no pause, no approval, no human in the loop. The pipeline's logic is: if every check passed, the change is production-worthy by definition.

In **continuous delivery**, the pipeline stops. The artifact is registered as **promotable** — it is available, tested, and ready — but it waits for a human decision. That decision might come thirty seconds later, or three days later, or on a scheduled release train. The pipeline's logic is: automated checks are necessary but not sufficient. Something else — a product decision, a compliance review, a coordination event — must also be true before this artifact goes live.

This single structural difference — an automatic transition versus a gated transition — cascades into everything downstream.

## What "Deployable at Any Time" Actually Requires

The phrase "can be deployed to production at any time" does real mechanical work in continuous delivery, but teams often treat it as aspirational rather than literal. For an artifact to be genuinely deployable at any moment a human presses a button, several things must be true simultaneously.

**The artifact must be immutable and self-contained.** It cannot depend on "the state of the repo at the time we deploy" or "the config that's currently in staging." It is a versioned, sealed unit — a Docker image with a digest, a signed binary, an OCI artifact in a registry. If your "deployment" involves checking out a branch and building on the target, you do not have a deployable artifact. You have a build script and a prayer.

**The artifact must be environment-agnostic.** The same artifact goes to staging, to pre-prod, to production. What changes between environments is configuration — injected at deploy time via environment variables, config maps, secrets managers — not the artifact itself. If you are building separate artifacts per environment, you are not testing what you deploy and you are not deploying what you tested.

**The promotion path must be a recorded, repeatable operation.** Deploying to production should be a single action against a known artifact version — `deploy artifact v1.42.0 to production` — not a sequence of manual steps that someone remembers. This is what makes the manual gate in continuous delivery a gate rather than a bottleneck: the human decides *when*, but the *how* is fully automated. If the human also has to decide *how*, you don't have continuous delivery. You have a CI pipeline with a manual deployment process bolted onto the end.

This is where many teams deceive themselves. They have CI. They have automated tests. They have a staging environment. But the distance between "tests passed" and "we can actually go to production" involves Slack threads, manual config changes, and someone SSH-ing into a box. That is not continuous delivery. That is continuous integration with a very long hallway to production.

## The Feedback Loop Divergence

The most consequential mechanical difference between delivery and deployment is not the presence or absence of a button. It is the **feedback loop from production**.

In continuous deployment, every commit that passes automated checks reaches production. This means every commit generates production telemetry — real latency data, real error rates, real user behavior signals. The feedback loop from "I wrote this code" to "I can see how it behaves under real load" is measured in minutes. This is not just fast; it changes what kinds of problems you can detect. Subtle performance regressions, edge cases that only appear under real traffic patterns, interaction effects between services — these surface immediately, while the change is small enough to reason about.

In continuous delivery, production feedback only arrives when someone triggers a deployment. If the team deploys once a day, the feedback loop is at least a day. If they deploy weekly, it's a week. And here's the mechanical trap: because each deployment now contains multiple changes, when production metrics degrade, you cannot trivially attribute the regression to a single commit. The signal-to-noise ratio of your production feedback is inversely proportional to the number of changes in each deployment.

This is not an argument that continuous deployment is always better. It is a description of a real mechanical property that you must account for. If you choose continuous delivery, you need to actively fight the tendency to batch changes and let the deployment gap grow, because the gap degrades the very feedback that makes deployment safe.

## The Batch Size Trap

Continuous deployment has a structural property that eliminates batch size growth by default: every commit goes out individually. You cannot accumulate a batch because there is nothing to accumulate against.

Continuous delivery has the opposite structural property. The manual gate, by its nature, creates a queue. Artifacts stack up behind the gate. Even well-intentioned teams drift toward batching: "We have three changes ready, let's deploy them together." This feels efficient. It is the opposite. Every additional change in a batch multiplies the diagnostic complexity of a production incident and increases the blast radius of a rollback.

The mechanical discipline required to counteract this is explicit: **deploy the oldest promotable artifact before queuing a new one.** Treat the gate as a single-item buffer, not a queue. Many deployment tools support this with artifact promotion policies — only one artifact is in the "awaiting production" state at a time, and a new artifact cannot enter that state until the previous one is either deployed or rejected.

Teams that do not enforce this discipline end up in a state where continuous delivery silently degrades into weekly batch releases with a CI system in front. The pipeline looks modern. The release process is the same monthly deploy they had before, just with better test coverage.

## Where the Choice Actually Lives

The Level 1 post noted that some organizations choose delivery over deployment for regulatory or risk management reasons. Let's make that concrete.

The decision is a function of three variables: **blast radius tolerance**, **detection capability**, and **recovery speed**.

**Blast radius tolerance** is a business input. How many users can be affected by a bad change before the cost becomes unacceptable? For a consumer social app, a 1% canary that shows a broken feed for thirty seconds is annoying but survivable. For a payment processing system, a single malformed transaction can trigger regulatory consequences. For a medical device, the answer might be zero.

**Detection capability** is an engineering input. How quickly and reliably can your monitoring, alerting, and automated rollback systems detect a bad deployment? If you have mature observability — real-time error rate comparison, latency percentile monitoring, automated canary analysis — you can detect most regressions within minutes. If your alerting is "someone notices a spike in the support queue," your detection time is measured in hours.

**Recovery speed** is also an engineering input. When you detect a problem, how fast can you get back to the previous known-good state? If rollback is a single API call that shifts traffic back to the previous version in seconds, recovery is effectively instant. If rollback involves a database migration revert and a 20-minute deployment cycle, recovery is slow enough that the damage is already done.

Continuous deployment is viable when detection is fast and recovery is fast — because the system catches and corrects problems before they reach most users. The human gate adds no value because no human can evaluate risk faster than the automated systems already do.

Continuous delivery is appropriate when any of those conditions is not met: when blast radius tolerance is extremely low and you need a human to verify that this specific change, at this specific time, is the right thing to release. When detection is not fast enough to prevent unacceptable impact. When the domain requires an auditable human decision for compliance reasons that are not negotiable.

The mistake teams make is choosing based on comfort rather than capability. "We're not ready for continuous deployment" is often true, but the response should be "what detection and recovery capabilities do we need to build?" not "manual gates forever."

## The Compliance Nuance

A common belief is that regulated industries require continuous delivery because they need a human approval step. This is partially true and frequently misunderstood.

What regulations typically require is an **auditable decision** — evidence that a qualified person authorized the change. They do not always require that decision to happen at deploy time. If a qualified person reviews and approves the pull request, and the pipeline has an auditable chain showing that the artifact deployed to production is the exact artifact produced from that approved commit, the compliance requirement may be satisfied without a manual deployment gate.

This is highly dependent on your specific regulatory framework and auditors. But the point is mechanical: the approval can be shifted earlier in the pipeline, to code review time, and the pipeline can maintain a cryptographic chain of custody from approved commit to deployed artifact. Some organizations that appear to require continuous delivery can, after rigorous analysis, implement continuous deployment with pre-commit approval and artifact provenance — and get the feedback loop benefits of deployment with the audit trail benefits of delivery.

Do not assume. Analyze your actual regulatory requirements with your compliance team. But also do not assume continuous deployment is incompatible with compliance without checking.

## The Mental Model

The distinction between continuous delivery and continuous deployment is not about automation maturity or team sophistication. It is about where in your pipeline the final risk decision lives, and whether that decision is better made by a human or by an automated system operating on production telemetry.

Everything before that decision point should be identical. The artifact pipeline, the test suite, the promotion mechanics, the deployment automation, the observability infrastructure — all of it is shared. The only variable is the gate: automatic or human. If you build your pipeline correctly, switching from delivery to deployment is a configuration change at one point in the pipeline, not a redesign. And if switching would be a redesign, that tells you something important about how much of your "continuous delivery" pipeline is actually continuous.

## Key Takeaways

- Continuous delivery and continuous deployment pipelines are structurally identical except for one gate: whether the transition to production is automatic or requires a human decision.

- "Deployable at any time" is a literal engineering requirement — immutable artifacts, environment-agnostic configuration, and a fully automated deployment operation — not an aspiration.

- Continuous deployment produces a tighter production feedback loop because every commit generates real production telemetry; continuous delivery only generates production feedback when someone triggers a deploy.

- The manual gate in continuous delivery structurally encourages batch accumulation, which degrades diagnostic clarity and increases rollback blast radius. Counteracting this requires explicit discipline and tooling.

- The choice between delivery and deployment is a function of three variables: blast radius tolerance (business input), detection capability (engineering input), and recovery speed (engineering input).

- Continuous deployment is viable when automated detection and recovery are fast enough that a human gate adds no value. Continuous delivery is appropriate when any of those conditions is not met or when an auditable human decision at deploy time is a non-negotiable requirement.

- Regulatory compliance often requires an auditable approval, but that approval can sometimes be shifted to code review time with cryptographic artifact provenance, making continuous deployment compatible with compliance requirements.

- If switching your pipeline from delivery to deployment would require significant rearchitecture, you likely do not have continuous delivery — you have CI with a manual deployment process attached.


[← Back to Home]({{ "/" | relative_url }})
