---
layout: page
title: "How to Read Any System"
permalink: /how-to-read-any-system
---

<img src="{{ site.url }}{{ site.baseurl }}/assets/img/read_any_system.jpg">

*A strategy map for orienting in any production system.*

Tiers 1–3 are knowledge — what is true about software in general. This page is the skill of using that knowledge on a system you have never seen. They are different abilities, and conflating them is why so much studying produces so little confidence in front of real code. You can hold every earlier concept in your head and still open a production repository — thousands of files, a half-familiar framework — and feel completely lost. That feeling is not a knowledge gap. It is an orientation gap, and it has its own remedy.

The remedy is a procedure, and — encouragingly — it barely depends on the technology in front of you. A seasoned engineer dropped into a language they have never written still gets their bearings fast, not because they recognise the syntax, but because they know what to look for and in what order.

Think of a driver versus a mechanic. The driver operates the car. The mechanic looks under the hood and sees *subsystems* — fuel, ignition, cooling, drivetrain, braking — and can find each one in a car they have never serviced, because every car has them. Their power is not memorising every model; it is carrying a fixed schema of what any car contains, plus a procedure for locating each part. This page is that schema and that procedure, for software.

One idea underpins all of it: **a system is not understood by reading its files; it is understood by locating a small, fixed set of subsystems and tracing what flows through them.** Files are where a system is stored, not how it is shaped.

## Why a codebase feels unreadable

Two features of every repository fight comprehension. First, the file tree is sorted alphabetically and by folder convention — *disk order* — which has nothing to do with where meaning lives, so reading it top to bottom is reading in the wrong order. Second, files are the wrong unit of analysis: a system is made of responsibilities and flows, and files merely store them. Trying to learn "what every file does" is like learning a city by reading the number on every building.

The fix for both is one realisation: a codebase has perhaps ten files that matter — its *anchors* — and thousands of *leaves* hanging off them. You hunt the anchors and read a leaf only when something leads you to it. That alone turns an unreadable wall into a short list.

## The skeleton: what every running system has

This is the fixed schema — the parts you look for, defined by *responsibility* rather than folder name, which is precisely why you can find them even when a project is organised in an unfamiliar way:

- **Entry points (the intake)** — every way work gets in: routes, message consumers, scheduled jobs, CLI commands, the startup bootstrap. This is the system's real table of contents.
- **The request path (the spine)** — the route work travels from entry to response. Learn one and you learn how all of them are laid out.
- **The domain core (the engine)** — the business rules, the reason the system exists. Usually a small island in a sea of plumbing, and worth finding early.
- **State and data (the memory)** — the stores, the schema, the data model. Often the truest map of the domain, because data cannot quietly drift out of date the way comments can.
- **Outbound dependencies (the linkages)** — what it calls, and what it does when those calls fail. This places the system inside the wider topology instead of treating it as an island.
- **The control surface (the dials)** — config, secrets, and feature flags: everything that changes behaviour without changing code.
- **Build and delivery (the assembly line)** — how source becomes an artifact and reaches production, and how a bad release rolls back. The road your own change will travel.
- **Runtime topology (the chassis)** — where it actually runs: environments, replicas, network shape.
- **Observability (the instruments)** — logs, metrics, traces, and alerts. The difference between a system and a black box.

Locate these nine and you are oriented. Everything else is detail you fetch on demand.

## The method: trace, don't browse

The skeleton tells you *what* to find; tracing tells you *how* to find it without drowning. The discipline is to follow one thing through the system, depth-first, instead of wandering the tree breadth-first. Four passes do the whole job.

**Walk around the car first.** Before opening any source, read the configuration at the repository root — the dependency manifest, the container files, the CI workflow, the infrastructure definitions, the build scripts. In about a minute, this tells you the language, the framework, how it builds, how it deploys, and how to run it. It is the highest-yield minute available, and the step most people skip on their way to getting lost in `src/`.

**Trace one request.** Pick a single representative endpoint and follow it end to end: entry → handler → core → data → outbound → response. Because a system applies the same layering to every request, this one walk teaches the grammar all the others obey — you learn the architecture from a single worked example, and you see the intake, spine, engine, memory, and linkages in one pass.

**Trace one change.** Follow a commit from source control through CI to a built artifact, then through deployment into staging and production, and note how a bad release is undone. This is the trace that lets you *act* on the system, not merely understand it.

**Trace one failure.** Ask where you would look first if it broke at three in the morning, and find the logs, dashboards, and alerts before you ever need them.

Throughout, prefer evidence to reading: running the system, following one real log line, reading the tests, and reading the schema are all faster than scrolling source.

## The output: a one-page map

Orientation should leave an artifact, not a fading feeling. Capture, in about a dozen lines: the stack; the command to run it; where the entry points live; one fully traced request; where the core sits; the data stores and source of truth; the external dependencies; the config and secrets it needs to boot; how it ships and how to roll back; where it runs; and where the logs are. Written down, this survives the three-month gap that makes a familiar system feel foreign again, and it onboards the next person in an afternoon. A mental model decays; a map does not.

## Where this meets Tiers 1–3

This page is what makes the others usable. Tracing a request is where Tier 1 — networking, compute, service architecture — stops being theory and becomes something you can point at. Tracing a change is Tier 2 — source control, CI, artifacts, delivery, infrastructure — walked through one real pipeline. Tracing a failure is Tier 3 — observability, reliability, security, cost — made concrete. And this is how abstract knowledge finally sticks: a concept becomes permanent the first time you locate it in a system you have traced. Knowledge attaches to systems, not to outlines.

Master the procedure and an unfamiliar codebase stops being a wall of files and becomes a system with a shape — one you can hold in your head, reason about, and change with confidence. That is the difference between operating the car and understanding the machine.

*The quickest version, when you just need to get unstuck: read the root manifests, find the entry points, trace one request to the data and back, open the CI config to see how it ships, and note where the logs go. Everything else can be deepened on demand.*