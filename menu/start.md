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

The three tiers are knowledge — what is true about software in general. Putting that knowledge to work on a system you have never seen is a separate skill, and it has its own page.

[**Own the System**]({{ "/own-the-system" | relative_url }}) — a strategy map for taking control of any production system you've never seen before. Where the three tiers map the body of knowledge, this page maps the act of finding that knowledge inside a real codebase: the difference between knowing how software works and having genuine leverage over the specific system in front of you. It is the bridge between everything above and the real thing on your screen.

---

### Why this blog exists

I entered the industry in 2020, and learned fast that the most valuable knowledge in software is also the least written down. It lives in senior engineers' heads and gets passed on by luck and proximity — if it gets passed on at all. The result is everywhere once you notice it: people who can run the command but can't tell you what it does, who inherit a setup and never question it, who execute instructions instead of making decisions. That isn't a personal failing. It's what a craft looks like when it hands down rituals instead of reasons.

This blog exists to write the reasons down. Not to catalogue tools or document procedures, but to give you the mental models that make tools legible — so that when you meet something new, you can reason about it instead of inheriting a ritual from whoever set it up before you.

And this matters far beyond the people who call themselves engineers. The wall between "building systems" and "everything else" is coming down. As AI shifts the work from writing code toward directing, evaluating, and owning outcomes, more and more people — not a specialist few — spend their days standing in front of systems they have to understand and steer. Reading a system is no longer niche knowledge held by a handful of specialists; it's becoming basic literacy for anyone who works. This blog is an attempt to democratise it — to put the principles in the open, so that understanding a system is something you can learn, not something you have to be let into.