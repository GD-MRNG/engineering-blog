---
layout: post
title: "3.5 Emerging Technology"
author: "Glenn Lum"
date:   2026-01-15 10:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Concept]
---

The experience of feeling behind is familiar to most engineers. A new technology appears with enough momentum — job postings, conference talks, a quiet sense that everyone else already understands it — and the implicit message is clear: what you currently know is not enough. You need to learn this new thing, and you need to learn it fast, on its own terms, from scratch.

That feeling is worth examining. Because it does not usually mean what it appears to mean.

The disorientation most engineers feel around emerging technology is not a knowledge gap. It is a framing problem. New technologies get introduced through their most novel surface — the interface, the API, the new workflow, the unfamiliar terminology. The implicit story is always about what is *different*. What does not get communicated, because the people who built the thing take it for granted, is everything that is the same.

## The Practice

Reasoning from foundations toward the novel is a habit — a way of encountering anything new by asking what stable layer of the stack it is operating on and what tradeoff it is making there, before asking anything else.

Every system that moves data across a network is subject to the same underlying constraints. Every system that stores state has to make decisions about consistency and durability. Every system that handles concurrent requests has to navigate synchronous versus asynchronous processing. These are not historical facts about old technology. They are the physics of computing. Emerging technologies do not override them. They express different positions within them, trading one constraint for another.

The engineers who built whatever new thing just arrived had to solve networking problems, storage problems, latency problems, and consistency problems. They solved them using the same concepts this series covers. They just did not ship a press release about the familiar parts.

## What Breaks Without This Habit

Without this frame, each new wave of technology requires starting from scratch. You accumulate knowledge about specific tools rather than understanding of durable problems. When the tools change — and they always change — the knowledge depreciates with them.

This is what produces the cycle of perpetual disorientation. Engineers who learned tools without the reasoning behind them have to reverse-engineer a new map every time the landscape shifts. The learning never compounds because it is attached to surfaces that keep changing rather than to foundations that do not.

LLM-based systems are a clear current illustration. The engineering challenges they create — high and unpredictable latency, non-deterministic outputs, context constraints, stateless inference — are not a new category of problem. They are existing problems under specific and unusual constraints. Deciding whether to cache a probabilistic output is a caching problem. Managing a 30-second inference call in a user-facing product is a distributed systems problem. Engineers who can locate these challenges on a map they already hold can reason about them immediately. Engineers who treat them as entirely novel have to build the map from scratch every time.

## What Becomes Possible

When this habit is in place, new technology stops arriving as disruption and starts arriving as information. You can ask the right diagnostic questions quickly: what problem is this solving, what layer does that problem live on, what tradeoff is being made, and is that tradeoff a good one in your context?

This is not a way of avoiding learning new things. It is a way of learning them faster and retaining the understanding longer — because new knowledge attaches to a stable structure rather than floating free with no relationship to anything you already know.

The engineers who build durable expertise across a long career are not the ones who learn each new thing the fastest. They are the ones whose understanding of the problem space is deep enough that new tools become recognisable quickly — variations on patterns they have already understood, making tradeoffs they can already name.

That is what the foundational posts in this series are building toward. Not a catalogue of technologies, but a vocabulary for diagnosing any technology — including ones that do not exist yet.

**Level 2 goes deeper into the mechanics of this habit** — what the underlying problem layers actually look like, how to identify what a new technology is trading away, and where reasoning from foundations breaks down or needs updating when something is genuinely novel.

---

## Key Takeaways

- The disorientation engineers feel around new technology is usually a framing problem, not a knowledge gap — new tools get introduced through their novel surface, obscuring the familiar foundations beneath.
- Every technology operates on the same underlying substrate and inherits its constraints, regardless of how new its interface appears.
- Engineers who learn tools without the reasoning behind them have to start from scratch with each new wave. Engineers who understand the reasoning evaluate each wave against a frame that doesn't expire.
- The most useful first question when encountering something new is not "what is this?" but "what problem is this solving, and what is it trading away to solve it?"
- Strong foundational knowledge does not become obsolete when new technology appears. It becomes the lens through which new technology can be understood quickly and evaluated accurately.

[← Back to Home]({{ "/" | relative_url }})