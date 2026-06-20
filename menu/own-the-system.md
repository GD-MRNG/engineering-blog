---
layout: page
title: "Own the System"
permalink: /own-the-system
---

Most engineers inherit systems they didn't design, built by people who've since left, running infrastructure owned by someone else. You are handed a codebase and expected to operate it — to keep it running, extend it, fix it at 3am — without ever being given the keys. The keys are not handed out. You take them.

Owning a system means you can answer: how does work get in? What path does it travel? Where does state live? What happens when something it depends on fails? How does a change reach production? Where do you look first when it breaks? These are not academic questions. They are the difference between someone who executes instructions and someone who has genuine leverage over the thing they operate.

Understanding a system is the first act of agency. You cannot push back on a decision, spot a bad tradeoff, or redirect something that's going wrong until you know how it works. Knowledge is what converts access into control.

**The core idea: a system is not understood by reading its files. It is understood by locating a small, fixed set of subsystems and tracing what flows through them.**

---

## The Skeleton

Nine subsystems that exist in every running system, defined by responsibility rather than folder name. This is what you're looking for — regardless of language, framework, or how the repo is organised.

**1. Entry points** — every way work gets in: routes, message consumers, scheduled jobs, CLI commands, the startup bootstrap. The system's real table of contents.

*Keywords: routes, consumers, handlers, entrypoints, bootstrap*
*→ [1.1 Networking Fundamentals]({{ "/11-networking-fundamentals" | relative_url }}), [1.3 Service Architecture Awareness]({{ "/13-service-architecture-awareness" | relative_url }})*

**2. The request path** — the route work travels from entry to response. Learn one and you learn how all of them are laid out.

*Keywords: middleware, handler chain, request lifecycle, controller*
*→ [1.1 Networking Fundamentals]({{ "/11-networking-fundamentals" | relative_url }}), [1.3 Service Architecture Awareness]({{ "/13-service-architecture-awareness" | relative_url }})*

**3. The domain core** — the business rules, the reason the system exists. Usually a small island in a sea of plumbing. Worth finding early.

*Keywords: domain logic, business rules, services, use cases*
*→ [1.3 Service Architecture Awareness]({{ "/13-service-architecture-awareness" | relative_url }})*

**4. State and data** — the stores, the schema, the data model. Often the truest map of the domain, because data cannot quietly drift out of date the way comments can.

*Keywords: schema, migrations, data model, stores, source of truth*
*→ [1.3 Service Architecture Awareness]({{ "/13-service-architecture-awareness" | relative_url }})*

**5. Outbound dependencies** — what it calls, and what it does when those calls fail. Places the system inside the wider topology instead of treating it as an island.

*Keywords: clients, adapters, third-party integrations, timeouts, retries*
*→ [1.1 Networking Fundamentals]({{ "/11-networking-fundamentals" | relative_url }}), [1.3 Service Architecture Awareness]({{ "/13-service-architecture-awareness" | relative_url }}), [3.3 Reliability Engineering]({{ "/33-reliability-engineering" | relative_url }})*

**6. The control surface** — config, secrets, and feature flags: everything that changes behaviour without changing code.

*Keywords: environment variables, secrets management, feature flags, config*
*→ [2.6 Configuration and Feature Management]({{ "/26-configuration-and-feature-management" | relative_url }})*

**7. Build and delivery** — how source becomes an artifact and reaches production, and how a bad release rolls back. The road your own change will travel.

*Keywords: CI pipeline, build scripts, deployment, rollback*
*→ [2.3 Continuous Integration]({{ "/23-continuous-integration-ci" | relative_url }}), [2.4 Artifact and Dependency Management]({{ "/24-artifact-and-dependency-management" | relative_url }}), [2.5 Continuous Delivery and Deployment]({{ "/25-continuous-delivery-and-deployment-cd" | relative_url }})*

**8. Runtime topology** — where it actually runs: environments, replicas, network shape.

*Keywords: environments, replicas, load balancer, infra, cloud*
*→ [1.1 Networking Fundamentals]({{ "/11-networking-fundamentals" | relative_url }}), [1.2 Compute Abstractions]({{ "/12-compute-abstractions" | relative_url }})*

**9. Observability** — logs, metrics, traces, and alerts. The difference between a system and a black box.

*Keywords: logs, metrics, traces, dashboards, alerts, on-call*
*→ [3.1 Observability and Monitoring]({{ "/31-observability-and-monitoring" | relative_url }})*

---

## The Four Traces

The skeleton tells you *what* to find. Tracing tells you *how* to find it without drowning. Follow one thing depth-first — don't browse the tree breadth-first.

**1. Read the root first**
Before opening any source, read the configuration at the repository root — the dependency manifest, container files, CI workflow, infrastructure definitions, build scripts. In about a minute this tells you the language, the framework, how it builds, how it deploys, and how to run it. The highest-yield minute available, and the step most people skip.

*Keywords: package manifest, Dockerfile, CI config, README, Makefile*
*→ [2.1 Source Control and Collaboration]({{ "/21-source-control-and-collaboration" | relative_url }}), [2.3 Continuous Integration]({{ "/23-continuous-integration-ci" | relative_url }})*

**2. Trace one request**
Pick a single representative endpoint and follow it end to end: entry → handler → core → data → outbound → response. This one walk teaches the grammar all the others obey. You see the intake, spine, engine, memory, and linkages in a single pass.

*Keywords: request lifecycle, handler, middleware, query, response*
*→ [1.1 Networking Fundamentals]({{ "/11-networking-fundamentals" | relative_url }}), [1.3 Service Architecture Awareness]({{ "/13-service-architecture-awareness" | relative_url }})*

**3. Trace one change**
Follow a commit from source control through CI to a built artifact, then through deployment into staging and production. Note how a bad release is undone. This is the trace that lets you *act* on the system, not merely understand it.

*Keywords: commit, pipeline, artifact, deploy, rollback*
*→ [2.1 Source Control and Collaboration]({{ "/21-source-control-and-collaboration" | relative_url }}), [2.3 Continuous Integration]({{ "/23-continuous-integration-ci" | relative_url }}), [2.4 Artifact and Dependency Management]({{ "/24-artifact-and-dependency-management" | relative_url }}), [2.5 Continuous Delivery and Deployment]({{ "/25-continuous-delivery-and-deployment-cd" | relative_url }})*

**4. Trace one failure**
Ask where you would look first if it broke at 3am. Find the logs, dashboards, and alerts before you ever need them.

*Keywords: logs, alerts, dashboards, runbook, on-call*
*→ [3.1 Observability and Monitoring]({{ "/31-observability-and-monitoring" | relative_url }}), [3.3 Reliability Engineering]({{ "/33-reliability-engineering" | relative_url }})*

---

## Your Ownership Map

You don't own a system until you can write this down. In about a dozen lines:

- The stack and how to run it locally
- Where the entry points live
- One fully traced request, end to end
- Where the domain core sits
- The data stores and source of truth
- The external dependencies
- The config and secrets it needs to boot
- How it ships and how to roll back
- Where it runs
- Where the logs are

Written down, this survives the three-month gap that makes a familiar system feel foreign again. It onboards the next person in an afternoon. It is shareable, durable, and yours. A mental model belongs to one person and fades. A map belongs to whoever holds it.

---

*The quickest version when you just need to get unstuck: read the root manifests, find the entry points, trace one request to the data and back, open the CI config to see how it ships, note where the logs go. Five moves and you know the shape of it. Everything else can be deepened on demand.*

---

[← Back to Home]({{ "/" | relative_url }})