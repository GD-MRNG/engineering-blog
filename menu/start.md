---
layout: page
title: "From Coder to Engineer"
image: start.jpg
permalink: /start
---

There is a meaningful difference between writing code and engineering software. Writing code is the act of translating logic into a programming language. Engineering software is the act of designing, building, delivering, operating, and continuously improving a system that serves real users in a real environment. The gap between these two is the territory this document maps.

This competency map below is organized around a single governing idea: software is not valuable when it is written; it is valuable when it is running. Everything between the moment a developer types a line of code and the moment a user benefits from it is the domain of operational engineering. DevOps is the cultural and technical philosophy that treats that entire journey as a first-class engineering concern, not an afterthought handled by a separate "ops" team.

To help you build a mental model, the framework is divided into three tiers. 

[**Tier 1: Foundational Knowledge**]({{ "/1-tier-1-foundational-knowledge" | relative_url }})
covers the foundational knowledge, the "physics" of how software runs, which underpins every decision in every other tier. 

[**Tier 2: Core Lifecycle Stages**]({{ "/2-tier-2-core-lifecycle-stages" | relative_url }})
covers the core lifecycle stages, the sequential process by which code becomes a deployed, running artifact. 

[**Tier 3: Cross-Cutting Disciplines**]({{ "/3-tier-3-cross-cutting-disciplines" | relative_url }})
covers the cross-cutting disciplines, the practices that apply continuously at every stage and that separate reliable systems from fragile ones.

The three tiers are not sequential phases. They are better understood as concentric layers. Tier 1 is the ground. Tier 2 is the structure built on that ground. Tier 3 is the ongoing maintenance, safety, and governance of that structure.

When you encounter a problem in practice, you will find that it almost always spans multiple segments. A deployment failure might originate in a networking misconfiguration (Tier 1.1), be discovered because of a missing health check (Tier 3.1), and be difficult to roll back because of an incompatible database migration (Tier 2.5). The ability to reason across these segments simultaneously is what defines operational seniority.

[← Back to Home]({{ "/" | relative_url }})