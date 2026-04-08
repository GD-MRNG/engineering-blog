---
layout: post
title: "1.3 Service Architecture Awareness"
author: "Glenn Lum"
date:   2026-01-03 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Concept]
---

`[Tier 1, Foundation Knowledge, Concept]`

The pattern by which your system is organized has cascading effects on every operational decision you will ever make. You do not need to be a systems architect, but you need to understand how your system's architectural pattern shapes the operational constraints you work within.

A **monolithic architecture** is one where all the functionality of your application lives in a single deployable unit: one process, one codebase, one database. The operational simplicity of a monolith is often undervalued. Deployment is a single event. Debugging is straightforward because all code runs in the same process and you can inspect it with a single debugger. Transactions are local and reliable. Testing is simpler because there are no network boundaries to stub or mock. The challenges emerge at scale: a monolith can only scale as a whole (you can't scale just the checkout service during a sale), a failure in one part of the application can cascade into a failure of the whole thing, and multiple teams working on the same codebase eventually create coordination overhead.

**Microservices** decompose the application into many independently deployable services, each responsible for a specific domain. This buys you independent deployability (the team owning the payment service can deploy without coordinating with the team owning the recommendation service), independent scalability (you can run fifty instances of your search service during peak times without scaling everything), and resilience in theory (a failure in the recommendation service shouldn't take down checkout). What it costs you is significant: you have introduced a distributed system. Every interaction between services is now a network call, which can be slow, can fail, can return partial results, or can time out. You now have to think about service discovery (how does Service A find Service B?), circuit breakers (if Service B is failing, how does Service A protect itself from being dragged down too?), distributed tracing (how do you follow a single user request as it fans out across twelve services?), and data consistency (if two services own different parts of a transaction, how do you ensure they don't get out of sync?).

**Event-driven architectures** add another dimension: services communicate not through direct synchronous calls but through events published to a shared message bus. Service A publishes "Order Placed" and does not wait for a response. Service B, which is responsible for sending confirmation emails, subscribes to that event and processes it independently. This decoupling is powerful for scalability and resilience, but it makes debugging considerably harder, because the relationship between cause and effect is no longer direct or synchronous.

The reason this belongs in your foundational layer is that an operational strategy cannot be designed in the abstract. Deployment strategies, testing strategies, observability strategies, and reliability patterns all need to be chosen with full awareness of the architectural context. The decision to "just restart the server" works for a monolith. In a microservices environment with dozens of interdependent services, it can cause a cascading failure that takes hours to resolve.