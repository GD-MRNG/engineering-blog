---
layout: post
title: "2.5.4 Rollback vs Roll Forward: Two Philosophies for Handling Bad Releases"
author: "Glenn Lum"
date:   2026-03-02 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most teams believe they have two options when a bad release hits production: roll back to the previous version, or fix the problem and ship a new version forward. They believe this is a decision they'll make in the moment, based on the severity of the issue and their best judgment under pressure. This belief is wrong in a specific and dangerous way. The choice between rollback and roll forward is not primarily a decision made during an incident. It is a consequence of architectural and operational decisions made weeks or months earlier. Teams discover this at the worst possible time — twenty minutes into an outage, when they attempt a rollback and find that it doesn't work, or decide to roll forward and realize their pipeline takes forty minutes. The gap between *having a philosophy* about bad releases and *having the mechanics in place to execute that philosophy* is where extended outages live.

The Level 1 post established the deployment strategies and introduced the expand-and-contract pattern for schema compatibility. This post is about the deeper question: what actually has to be true about your system for each strategy to work, why those preconditions are harder to maintain than they appear, and how to reason about which approach is viable in a given moment.

## What Rollback Actually Requires

Rollback sounds simple: deploy the previous version. But "deploy the previous version" is a description of what you want to happen, not a description of the mechanics. Here's what actually has to be true for a rollback to succeed.

### Artifact availability

The previous version's deployable artifact — container image, binary, package — must still exist in a registry or artifact store, tagged or referenced in a way that your deployment tooling can retrieve it without manual archaeology. This sounds trivial, but image retention policies, garbage collection on container registries, and ephemeral build outputs can quietly destroy this guarantee. If your CI pipeline builds artifacts on the fly and your previous version's branch has since been merged and deleted, you may not be able to reproduce it.

### Configuration compatibility

The previous version must be compatible with the *current* configuration and infrastructure state, not the configuration that existed when it was originally deployed. If you've rotated secrets, updated environment variables, changed service mesh routing rules, or modified infrastructure between the original deployment and now, the old artifact may not start cleanly. This is particularly insidious with infrastructure-as-code changes that are deployed independently of application code — the environment the old version expects may no longer exist.

### Data layer compatibility

This is the constraint that breaks most rollbacks. The Level 1 post covered the expand-and-contract pattern for schema migrations, but schema migrations are only the most visible form of state incompatibility. Consider what happens the moment a new version starts serving traffic: it begins writing data in formats the old version may not understand. New enum values in database columns. New fields serialized into JSON blobs. New message formats published to queues or event streams. Cache entries written with a new serialization layout. None of these require an explicit migration step — they happen as a natural consequence of the new code running.

A concrete example: your new version adds a `status` field to an order record with possible values `pending`, `confirmed`, and `waitlisted`. The old version doesn't know about `waitlisted`. You roll back. The old version reads an order with `status = waitlisted` and either crashes, silently drops it, or maps it to a default — all bad outcomes. Multiply this by every data path your application touches, and you begin to see the real surface area of the problem.

### Service compatibility in a distributed system

If you've deployed new versions of services A, B, and C together because they share a new API contract, rolling back A without rolling back B and C may create an incompatible constellation. Rolling back all three simultaneously is a coordination problem that most deployment tooling doesn't handle atomically. You end up with a period where some services are on the old version and some are on the new, which may be exactly the state that causes failures.

### The rollback window

These constraints combine to create an implicit **rollback window** — a period after deployment during which rollback is mechanically feasible. At the moment of deployment, the window is fully open: no state has been written by the new version, no downstream systems have adapted to its behavior. As time passes, state divergence accumulates, and the window closes. For a stateless API gateway, this window might be indefinite. For a service that writes to a database on every request, the window might be minutes. For a service that triggers an irreversible external side effect (sending emails, charging credit cards, publishing to a third-party API), the window is essentially zero for those specific operations.

The critical insight: **you don't choose when the rollback window closes. Your system's data flow determines it.** Teams that treat rollback as universally available are not accounting for the speed at which their system creates state that the old version cannot interpret.

## What Roll Forward Actually Requires

Roll forward means shipping a new version that fixes the problem introduced by the bad release. It sounds aggressive — you're deploying *more* code into an already-broken production environment — but it has one enormous structural advantage: it moves the system forward through a state that is compatible with the data already written. You don't have to reconcile old code with new data. You reconcile new code with new data, which is the direction the system was already heading.

But roll forward has its own hard requirements.

### Pipeline speed

Roll forward is bounded by your deployment pipeline's end-to-end time. If your CI/CD pipeline takes forty-five minutes from merge to production, then roll forward means forty-five minutes of continued impact (plus diagnosis time, plus fix authoring time). For teams with slow pipelines, roll forward is not a realistic incident response strategy — it's a strategy for non-urgent fixes. The teams that practice roll forward successfully typically have pipelines under ten minutes, and many have invested in **fast-path pipelines** — stripped-down build and deploy paths that skip non-essential validation steps for emergency fixes.

### Diagnosis under pressure

Roll forward requires you to understand the problem well enough to fix it while users are being affected. This is a fundamentally different cognitive challenge than rollback, which requires only the recognition that *something is wrong*. Roll forward demands root-cause identification (or at least sufficient understanding to write a correct fix) under time pressure, with incomplete information, often while also managing incident communication. The fix must be correct on the first attempt, because a second roll-forward iteration doubles the total time to resolution.

### Cultural and procedural permission

Many organizations have change approval processes, code review requirements, or deployment freezes that make shipping code during an incident procedurally difficult. If your roll-forward fix requires two approvals and a Jira ticket before it can merge, the organizational mechanics work against you. Teams that rely on roll forward need explicit **break-glass procedures** — documented, pre-approved paths for emergency deployments that bypass normal gates while maintaining an audit trail.

### Feature flags as a zero-deployment roll forward

The fastest possible roll forward isn't a deployment at all — it's a feature flag toggle. If the problematic code path was deployed behind a flag, you can disable it in seconds without touching the deployment pipeline. This is why the deployment-release decoupling described in the Level 1 post is not just a nice practice for gradual rollouts — it is an incident response mechanism. A feature flag turns a "roll forward" from a twenty-minute operation into a five-second operation. But this only works if the flag was in place *before* the problem surfaced. You cannot retroactively add a feature flag to code that's already broken in production.

## How Deployment Strategy Constrains Your Options

The deployment strategy you chose for the release directly determines the mechanics of both rollback and roll forward.

**Blue/green** gives you the fastest pure rollback: shift traffic back to the blue environment at the load balancer. But this only works if you haven't decommissioned or re-provisioned blue. Many teams tear down the idle environment after a stabilization period to save infrastructure cost. If the problem surfaces after that teardown, the "instant rollback" no longer exists. Blue/green also doesn't undo state changes — any writes to shared datastores during the green deployment's active period persist.

**Canary** gives you rollback for the canary population by routing their traffic back to the stable version. The blast radius is already limited, which buys you diagnostic time. But the canary's requests have already created state. If 2% of your traffic hit the new version and wrote data in a new format, you have 2% of your data in a state the old version may mishandle. Whether this matters depends entirely on what your service does with that data.

**Rolling updates** give you rollback, but it's another rolling update in reverse — it takes approximately the same amount of time as the original deployment. During the rollback, you again have a mixed fleet of old and new versions, which is exactly the condition that may have caused the problem in the first place.

## Tradeoffs and Failure Modes

The most common failure mode is **the assumed rollback**. A team deploys with the implicit assumption that they can roll back if anything goes wrong. They don't verify that the previous artifact exists, don't check schema compatibility, don't think about messages already published in a new format. Forty minutes into an incident, they attempt the rollback and discover it fails, or worse — it appears to succeed but introduces a second class of errors because the old code misinterprets the new data. They've now burned forty minutes and need to start the roll-forward process from scratch.

The second failure mode is **roll forward under panic**. A team decides to fix forward, writes a patch quickly under pressure, and ships it. The patch fixes the immediate symptom but introduces a subtle second bug. Now they're on their third version in an hour, the system's state is a product of all three, and reasoning about behavior becomes nearly impossible. Each successive emergency deployment layers more uncertainty.

The third failure mode is **the philosophical mismatch**. The team has a roll-forward culture but a rollback-speed pipeline — or a rollback assumption but a schema migration strategy that closes the rollback window on every deploy. The philosophy and the mechanics are misaligned, and the team doesn't discover this until the incident that reveals the gap.

A real scenario that illustrates the compounding problem: a team deploys a new version that introduces a background job processing orders into a new fulfillment workflow. The job runs for ten minutes before monitoring catches elevated error rates. By that time, three thousand orders have been processed through the new (buggy) workflow. Rolling back the code doesn't un-process those orders. Rolling forward with a fix addresses new orders but not the three thousand already affected. The actual recovery requires a data remediation script that someone has to write from scratch during the incident — a third category of work that neither "rollback" nor "roll forward" addresses. This is why the most prepared teams think not just about code versioning but about **data remediation runbooks** for their critical paths.

## The Mental Model

The choice between rollback and roll forward is not a runtime decision — it is a property of your system's architecture, your pipeline's speed, and your data model's compatibility guarantees. During an incident, you are not choosing a strategy. You are discovering which strategies are available to you based on decisions already made.

The single most important variable is **state**. Stateless operations can be rolled back trivially. The moment a new version writes state — to a database, a queue, a cache, an external system — rollback becomes a state reconciliation problem, not a deployment problem. The question to ask about any system is not "can we roll back?" but "how fast does our rollback window close, and what do we do after it's closed?"

Teams that handle bad releases well don't commit to one philosophy. They maintain the ability to do both, they know the constraints that determine which is viable in a given moment, and they've pre-decided the criteria before the incident starts.

## Key Takeaways

- **Rollback is not "deploy the previous version."** It is a claim that the previous version is compatible with the current state of your data, configuration, infrastructure, and dependent services. That claim must be verified, not assumed.

- **Every system has an implicit rollback window that begins closing the moment a new version serves traffic.** The speed at which it closes is determined by how quickly the new version creates state the old version cannot interpret.

- **Roll forward is bounded by pipeline speed plus diagnosis time.** If that total exceeds your tolerance for user impact, roll forward is not a viable incident response strategy — it's a cleanup strategy.

- **Feature flags are the fastest roll-forward mechanism because they require no deployment.** But they only work for problems in code paths that were flagged before the incident. They are a preparedness tool, not a reactive one.

- **Deployment strategy determines rollback mechanics, not just deployment mechanics.** Blue/green gives instant traffic rollback but doesn't undo state. Canary limits blast radius but still creates divergent state. Rolling updates roll back at the same speed they roll out.

- **The most dangerous failure mode is the assumed rollback** — the team that discovers mid-incident that the rollback they planned on is not mechanically possible, and has to switch strategies after already burning time.

- **Neither rollback nor roll forward addresses data already corrupted or state already changed by the bad version.** The third, often-forgotten category of incident work is data remediation, and it should be planned for explicitly on critical paths.

- **The decision between rollback and roll forward should be pre-decided based on system properties, not made under pressure during an incident.** Document which paths are rollback-safe, which require roll forward, and what the criteria are for choosing — before you need to choose.

[← Back to Home]({{ "/" | relative_url }})
