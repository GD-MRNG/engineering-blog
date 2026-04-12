---
layout: post
title: "3.3.5 Toil: The Invisible Reliability Tax"
author: "Glenn Lum"
date:   2026-04-01 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most engineers experience toil as a morale problem — the tedious parts of the job that make work feel unrewarding. That framing is why toil stays invisible for so long. Toil is not primarily a morale problem. It is a capacity problem with specific scaling properties that make it structurally dangerous. The tedium is a symptom. The actual threat is that toil grows proportionally with the size and complexity of your system while your engineering headcount does not. A team doing thirty minutes of manual work per deploy doesn't have a morale problem when they deploy twice a week. They have a capacity crisis when they deploy thirty times a day. The mechanics of how toil accumulates, hides, and eventually crowds out all other work are precise and worth understanding, because by the time toil is obvious, recovery is expensive.

## What Qualifies as Toil and What Does Not

Google's SRE book gave toil a formal definition with specific properties. These properties are not arbitrary — each one contributes to the scaling dynamics that make toil dangerous.

**Manual** means a human is in the loop. Not "a human initiates an automated process," but "a human performs steps that a machine could perform." Clicking through a console to restart a service is toil. Running a script that restarts the service is not, even though a human triggered it.

**Repetitive** means it recurs. A one-time manual migration is operational work, not toil. A manual migration you perform every time a new customer onboards is toil. The frequency matters because it determines the rate at which the work consumes capacity over time.

**Automatable** means there exists a technical path to eliminating the human from the loop. If the work requires genuine human judgment — deciding whether a nuanced edge case warrants an exception to a policy — it is not toil regardless of how tedious it feels. If the work follows a decision tree that could be encoded in logic, it is automatable, and therefore toil.

**Tactical** means it is reactive rather than strategic. Toil is interrupt-driven: an alert fires, a ticket arrives, a deploy needs babysitting. It does not advance the system's long-term capabilities. It responds to the system's current demands.

**Scales with service size** is the property that makes toil lethal. If adding ten more customers means ten more manual configuration steps per week, the work scales linearly with growth. Engineering work — building the system that auto-provisions customer configurations — is a fixed cost that absorbs growth without additional human effort.

**No enduring value** means that after the toil is performed, the system is not in a better state than before. It is in the same state. You cleared the queue, you restarted the process, you updated the certificate. Tomorrow, the same work exists again.

The distinction that trips people up: not all operational work is toil. On-call rotations involve toil (manually restarting a failing service at 3 AM) but also involve engineering work (investigating a novel failure mode, improving alerting). Overhead — meetings, planning, HR processes — is not toil either. Toil is specifically the subset of operational work that is manual, repetitive, automatable, and scales with service size.

## How Toil Accumulates

Toil rarely arrives as a single large block. It accumulates through a process that looks, at each individual step, completely reasonable.

A new service launches. It has a manual deploy step that takes five minutes because the team prioritized shipping over automation. Reasonable — the service deploys once a week and the team has higher priorities. A month later, the service is popular, and deploys increase to daily. Five minutes a day, still small. Then a second service launches with its own manual step. Then the first service adds a configuration change that requires a manual database update on each deploy. Then an incident produces a runbook that requires a human to verify a health check sequence after each restart.

None of these individually register as a problem. Each is a small, justified decision. But the aggregate grows monotonically. Toil almost never decreases on its own — it only increases, because each new service, each new failure mode, each new customer integration adds a small, permanent tax on the team's time.

The accumulation has a specific shape: it is the sum of many small O(n) contributions, where n is some dimension of scale — number of services, number of customers, number of deploys, number of alerts. Each contribution is trivial in isolation. The sum eventually dominates the team's capacity budget.

Consider a platform team responsible for 15 microservices. Each service has an average of two manual operational tasks per week, each taking about 20 minutes. That is 10 hours per week — more than a full day of one engineer's time — consumed by work that produces no lasting improvement. When the platform grows to 30 services, it becomes 20 hours. The team did not get slower or less competent. The toil scaled with the system.

## Why Toil Is Invisible

Three properties conspire to hide toil from teams and leadership until it reaches critical levels.

**It is distributed across individuals.** No single person sees the full picture. One engineer spends forty minutes manually rotating secrets on Tuesday. Another spends an hour triaging duplicate alerts on Thursday. A third spends thirty minutes hand-editing a config file for a new environment on Friday. No one person experiences the aggregate. In standup, each mentions their task briefly and moves on. It does not feel like a systemic problem because no individual carries the full weight.

**It masquerades as productive work.** An engineer who spent four hours manually processing a backlog of customer onboarding requests has a full day of visible output. Tickets were closed. Work was done. From the outside — from a sprint review, from a manager's perspective, from a JIRA board — this looks like productivity. The fact that those four hours could have been zero with a self-service provisioning system is not visible in any artifact the team normally examines.

**It is normalized.** Teams develop a tolerance for toil through repeated exposure. "That's just how deploys work here." "Yeah, you have to manually restart the cache after a config change — it's been like that since last year." Toil that has existed for months stops being perceived as a problem. It becomes part of the team's mental model of what their job *is*, rather than something imposed on them by a gap in their tooling. New team members, who might otherwise flag toil as surprising, are trained into the existing norms during onboarding.

The measurement problem compounds this. Most teams have no systematic way to track toil. Time-tracking systems capture project work, not the fifteen-minute interrupt to manually clear a stuck queue. Incident tracking captures outages, not the manual remediation steps that prevented an outage from happening. Without measurement, toil has no advocate in planning discussions. It loses to every project that has a visible deliverable.

## The Crowding-Out Dynamics

The most important mechanic of toil is the feedback loop it creates.

A team's capacity is finite. Every hour spent on toil is an hour not spent on engineering work — building automation, improving reliability, reducing future toil. As toil grows, the team's capacity for engineering work shrinks. As engineering capacity shrinks, the team builds less automation. As less automation is built, toil continues to grow unchecked. This is a positive feedback loop in the systems dynamics sense: the more toil you have, the faster you accumulate more toil.

This loop has a tipping point. Below the tipping point, the team has enough engineering capacity to periodically automate away their worst sources of toil, keeping the total manageable. Above it, the team is fully consumed by toil and cannot invest in the automation that would reduce it. At this point, the team is in a **toil trap** — a stable equilibrium where 100% of capacity is consumed by reactive work and no improvement is possible without external intervention (additional headcount, a mandated toil reduction sprint, or a deliberate decision to let some toil-driven tasks fail).

Google SRE established a guideline that toil should not exceed 50% of any individual SRE's time, with the other 50% reserved for engineering work. This is not an arbitrary threshold — it is a structural safeguard against the feedback loop. At 50%, the team retains enough engineering capacity to automate its worst toil sources faster than new toil accumulates. Above 50%, the loop starts to dominate.

The 50% number is a target, not a law of physics. The actual tipping point depends on how quickly toil grows (which depends on the system's growth rate) and how effective the team's automation efforts are (which depends on tooling maturity, system architecture, and organizational support). A team in a slow-growth environment might sustain 60% toil for years. A team in a hypergrowth environment might hit the trap at 40%.

## Where This Breaks: Tradeoffs and Failure Modes

**Automation is not free.** The most common misunderstanding of toil reduction is that automation is pure savings. Every piece of automation is code that must be written, tested, deployed, monitored, and maintained. A script that automates a twenty-minute manual task sounds like an obvious win until you account for the two days to write it, the half-day to handle edge cases that emerge in production, and the ongoing maintenance when the underlying system changes. The breakeven calculation is straightforward — multiply the time saved per execution by the expected number of executions, subtract the development and maintenance cost — but teams routinely get it wrong by underestimating maintenance and overestimating execution frequency.

**Premature automation creates its own burden.** Automating a task that is still changing — a deploy process for a service whose architecture is under active development, an onboarding flow whose business requirements shift quarterly — means you are maintaining automation that needs constant rework. Sometimes the correct response to toil is to defer automation until the underlying process stabilizes. The SRE book's own guidance suggests that some toil should be tolerated deliberately while the team gathers information about whether the manual process is the right process.

**Toil measurement itself is toil.** If you ask engineers to track every manual, repetitive task in a spreadsheet, you have added a new manual, repetitive task. Effective toil measurement needs to be low-friction — lightweight tagging in existing ticketing systems, periodic time-sampling surveys, or automated detection of repetitive operational patterns in runbook execution logs. Teams that implement heavyweight toil-tracking processes often abandon them within weeks, which reinforces the invisibility problem.

**The political failure mode.** Toil reduction requires convincing stakeholders that doing less visible work (closing fewer tickets, processing fewer manual requests) in the short term will produce more capacity in the long term. This is a hard sell in organizations that measure productivity by output volume. A team that spends a sprint building a self-service provisioning tool will, for that sprint, close zero provisioning tickets. To a manager tracking ticket throughput, the team appears to have stopped working. Without organizational understanding of toil dynamics, teams that try to escape the toil trap get punished for the attempt.

**The reliability failure mode.** Teams deep in the toil trap cut corners on the manual work itself. An engineer performing the same manual remediation step for the fiftieth time does it faster, skips verification steps, and misses the one time the failure has a different root cause. Toil degrades the quality of the work it consumes. This is how toil, which often exists to maintain reliability, eventually degrades reliability — the human performing the work is no longer applying careful judgment; they are executing a memorized script with decreasing attention.

## The Mental Model

Toil is operational debt with a growth rate. Like financial debt, small amounts are manageable and sometimes strategically useful — you can tolerate manual work for a new service while you focus on shipping. But toil compounds. Each unit of toil you carry reduces your capacity to pay it down, and each unit of growth adds new principal. The interest rate is your system's growth rate: a system that is not growing accumulates toil slowly; a system in hypergrowth accumulates it fast.

The critical insight is that toil is not a backlog to be worked through — it is a rate to be managed. You do not "finish" toil the way you finish a feature. You reduce the rate of toil accumulation by automating the highest-volume sources, and you maintain engineering capacity to keep that rate below your ability to address it. The moment the accumulation rate exceeds your engineering capacity, the feedback loop takes over, and the team is in a structural trap that cannot be escaped through effort alone.

## Key Takeaways

- Toil is specifically manual, repetitive, automatable work that scales with service size — not all operational work, and not all unpleasant work.

- Toil accumulates as the sum of many small, individually reasonable decisions, and it almost never decreases on its own.

- Toil is invisible because it is distributed across individuals, looks like productive work from the outside, and becomes normalized over time.

- The core danger is a positive feedback loop: toil consumes engineering capacity, which prevents automation, which allows toil to grow further.

- The 50% toil cap exists as a structural safeguard to ensure teams retain enough engineering capacity to automate faster than toil accumulates.

- Automation has real costs — development, edge case handling, and ongoing maintenance — and the breakeven math is routinely underestimated.

- Premature automation of unstable processes creates maintenance burden that can exceed the toil it replaced; defer automation until the underlying process stabilizes.

- Teams deep in the toil trap cannot escape through effort alone — they need external intervention in the form of additional capacity or a deliberate decision to let some toil-driven tasks fail while engineering capacity is rebuilt.

[← Back to Home]({{ "/" | relative_url }})
