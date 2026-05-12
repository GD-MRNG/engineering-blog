---
layout: page
title: "From Coder to Engineer"
image: start.jpg
permalink: /start
---

## Why this blog exists

I entered the software industry in 2020 — fresh out of a CS degree, during COVID, with no onboarding, no mentor, and no one to walk me through how any of it actually worked. Everyone assumed you knew. The knowledge that would have helped most was either tribal — locked inside senior engineers' heads — or simply never articulated. People were absorbed in the details and had little time to surface the principles underneath, to explain the *why* behind the tools, the decisions, the conventions. That absence has a cost: engineers who don't understand why they're doing something are executing instructions, not making decisions.

This blog exists to close that gap — deliberately, and from first principles.

The goal is not to catalogue tools or document procedures. It is to give you the mental models that make tools legible. When you understand *why* a service mesh exists, configuring one becomes a purposeful act rather than a ritual you inherited from whoever set it up before you. When you understand *why* deployment strategies differ, you can choose between them rather than default to one. The difference is the difference between working in a system and reasoning about it.

There are a few motivations behind this:

**For teams.** Shared mental models are a force multiplier. A team where everyone understands *why* decisions are made — not just *what* was decided — moves faster, reviews more sharply, and argues more productively. This is a resource for building that shared floor.

**For juniors.** The conventional approach to onboarding is to start with the specific: the ticket, the tool, the task. This blog starts with the general: the map. Understanding where a task fits in the overall system — what problem it solves, what tradeoffs it carries — is what separates an engineer who executes from one who contributes. That orientation is what most juniors never get, and it is the thing that compounds most over a career.

**For the industry.** There is a strain of thinking in engineering culture that treats knowledge as a competitive asset — something to hoard, to gate, to leverage for personal advancement. This blog is a rejection of that posture. Elitism in technical disciplines produces fragile teams dependent on individuals rather than on shared understanding.

**For the moment we are in.** The shift to AI-assisted and AI-generated code changes what engineering skill means. Writing code well is becoming less scarce; knowing *what to build*, *why to build it*, and *whether what was built is correct* is becoming more critical. Engineers who cannot reason from first principles cannot write a tight specification. Those who cannot write a tight specification cannot effectively direct an agent, evaluate its output, or take responsibility for outcomes rather than just outputs. The craft is shifting from how well you write code to how clearly you think, how well you direct, and how sharply you review — from hands-on producer to director and quality gatekeeper.

That shift has a practical shape. It means investing more in clarity upfront — writing tight specs, scoping problems well — than in the act of implementation itself. And it means developing an orchestrator's eye: breaking work into parallelisable pieces, evaluating what gets produced, and owning the outcome.

The engineers who thrive in that environment will be the ones who invested in understanding — not in any particular tool, language, or framework, but in the principles that make all tools make sense. That is what this blog is for.


## The framework

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
