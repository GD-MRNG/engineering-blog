---
layout: page
title: "From Coder to Engineer"
image: start.jpg
permalink: /start
---

There is a meaningful difference between writing code and engineering software. Writing code is the act of translating logic into a programming language. Engineering software is the act of designing, building, delivering, operating, and continuously improving a system that serves real users in a real environment. The gap between these two is the territory this document maps.

This framework is organized around a single governing idea: software is not valuable when it is written; it is valuable when it is running. Everything between the moment a developer types a line of code and the moment a user benefits from it is the domain of operational engineering. DevOps is the cultural and technical philosophy that treats that entire journey as a first-class engineering concern, not an afterthought handled by a separate "ops" team.

To help you build a mental model, the content is divided into three tiers.

[**Tier 1: Foundational Knowledge**]({{ "/t1-archive.html" | relative_url }})
— the "physics" of how software runs. These are the mental models that underpin every decision in every other tier.

[**Tier 2: Core Lifecycle Stages**]({{ "/t2-archive.html" | relative_url }})
— the sequential process by which code becomes a deployed, running artifact.

[**Tier 3: Cross-Cutting Disciplines**]({{ "/t3-archive.html" | relative_url }})
— the practices that apply continuously at every stage, and that separate reliable systems from fragile ones.

The three tiers are not sequential phases. They are better understood as concentric layers. Tier 1 is the ground. Tier 2 is the structure built on that ground. Tier 3 is the ongoing maintenance, safety, and governance of that structure.

When you encounter a problem in practice, you will find that it almost always spans multiple segments. A deployment failure might originate in a networking misconfiguration (Tier 1.1), be discovered because of a missing health check (Tier 3.1), and be difficult to roll back because of an incompatible database migration (Tier 2.5). The ability to reason across these segments simultaneously is what defines operational seniority.

---

### Why this blog exists

I entered the software industry in 2020 — fresh out of a CS degree, during COVID, with no onboarding and no mentor. The knowledge that would have helped most was tribal, locked inside senior engineers' heads, or simply never articulated. No one explained the *why* behind the tools, the decisions, the conventions — and engineers who don't understand why they're doing something are executing instructions, not making decisions. This blog exists to close that gap. The goal is not to catalogue tools or document procedures, but to give you the mental models that make tools legible — so that when you encounter something new, you can reason about it rather than inherit a ritual from whoever set it up before you. That orientation matters more now than ever: as AI-assisted development shifts the craft away from writing code toward directing, evaluating, and owning outcomes, the engineers who thrive will be those who invested in understanding principles, not in any particular tool or syntax.