---
layout: post
title: "1.3.1 The Monolith vs Microservices Spectrum"
author: "Glenn Lum"
date:   2026-01-29 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most teams talk about monoliths and microservices as if they are choosing between two buildings. In practice, they are choosing where to put walls inside one building — and every wall they add changes the plumbing, the wiring, the fire code, and who holds the keys to which rooms. The Level 1 post laid out what monoliths and microservices are and sketched the surface-level tradeoffs. What it did not cover is the thing that actually determines whether an architecture succeeds or fails: the mechanics of what happens at a service boundary, why the space between monolith and microservices is where most real systems live, and why drawing a boundary in the wrong place costs more than having no boundary at all.

## What a Service Boundary Actually Does

When all your code runs in one process, a function call between the order module and the inventory module is a stack frame. It completes in nanoseconds. It either succeeds or throws an exception that you catch in the same call stack. The data it operates on can participate in a single database transaction — either the order is placed and inventory decremented atomically, or neither happens.

The moment you extract the inventory module into a separate service, that function call becomes an HTTP request or a gRPC call. This is not just "slower." It is a categorical change in the failure model. The call can now fail in ways that a function call cannot: the network can partition, the remote service can be up but slow (the worst failure mode in distributed systems, because it holds resources open), the response can arrive after your timeout fires, or the service can process the request successfully but the acknowledgment can be lost on the way back. You now have a state where *you don't know whether the operation succeeded*, which is a condition that does not exist inside a single process.

This also means the data involved in that interaction can no longer participate in a local transaction. If the order service writes an order to its database and then calls the inventory service to decrement stock, and that call fails, you now have an order with no corresponding inventory adjustment. You are in the world of **distributed data consistency**, and your options are some form of saga pattern (a chain of compensating operations), eventual consistency (accepting that the two data stores will be temporarily out of sync), or the outbox pattern (writing events to your local database transactionally and publishing them asynchronously). All of these are real engineering work with real edge cases. None of them are free.

Every service boundary you introduce is a commitment to solving this class of problem at that boundary, forever.

## The Spectrum Between Monolith and Microservices

The binary framing obscures the architecture most teams actually need. Between a single-process monolith and fine-grained microservices sits a range of options, and the transitions between them have specific mechanical properties.

### The Modular Monolith

A **modular monolith** is a single deployable unit where the internal code is organized into well-defined modules with explicit boundaries — enforced through access control at the code level, separate module directories or packages, and defined interfaces between modules. Critically, the modules may or may not share a database, but if they do, they access only their own tables through their own data access layer.

The mechanical advantage is significant: you get the deployment simplicity and transactional integrity of a monolith while building the internal separation that would make future extraction possible. A module boundary enforced in code is dramatically cheaper to maintain than a service boundary enforced over the network. You can refactor across it using your IDE. You can test across it without standing up infrastructure. You can reason about it with a debugger.

The discipline required is real, though. Without enforcement — whether through build system constraints, architecture tests (tools like ArchUnit), or code review rigor — module boundaries erode. Someone writes a direct SQL join across module tables because it's expedient, and now those modules are coupled at the data layer in a way that would block future extraction.

### Coarse-Grained Services

The next step on the spectrum is a small number of independently deployable services, each owning a significant business domain. This is not microservices — it is closer to what was historically called **service-oriented architecture**, though that term carries a lot of baggage. Think three to eight services for a mid-sized system: an order service, a user service, a payments service, a notification service.

At this granularity, each service boundary represents a major organizational boundary (usually aligned to a team), and the interaction patterns between services are well-understood and relatively infrequent compared to the intra-service communication within each one. The ratio of network calls to local calls is still heavily weighted toward local. This is where many production systems that call themselves "microservices" actually operate.

### Fine-Grained Microservices

At the far end, each service does one narrow thing: a pricing service, a tax calculation service, a cart service, a checkout orchestration service, an address validation service. The mechanical reality here is that a single user-facing request touches many services. A checkout operation might involve eight to twelve network hops. Latency is additive. Failure probability is multiplicative — if each service has 99.9% availability, twelve services in a synchronous chain gives you roughly 98.8% availability for that operation, before you have done anything wrong.

This granularity buys you maximum deployment independence and team autonomy. But the operational infrastructure required to make it work is substantial: service mesh or API gateway for routing and traffic management, distributed tracing as a non-negotiable requirement (not a nice-to-have), centralized logging with correlation IDs threaded through every request, circuit breakers and bulkheads to prevent cascade failures, and a deployment pipeline mature enough to handle dozens of independent release cycles without coordination chaos.

## The Data Boundary Is the Hard Part

Teams consistently underestimate this: splitting code into separate services is straightforward. Splitting the data is where architectural decisions become genuinely difficult and often irreversible.

When two modules in a monolith share a database, they can join across tables, enforce foreign key constraints, and participate in the same transaction. The moment those modules become separate services with separate databases — which is the whole point, because a shared database between services is a coupling mechanism that defeats the purpose of the split — you lose all of that.

Concretely: if the order service needs to display an order with the customer's name and address, and that data now lives in the user service's database, the order service has to call the user service at query time, or maintain a local cache or read-model of user data that it keeps synchronized. The first option adds latency and a failure dependency to every order query. The second option means you are building and maintaining a data synchronization mechanism — and accepting that the order service's copy of the user's name might be stale by seconds or minutes.

This is not a theoretical concern. It is the daily mechanical reality of operating a system with split data ownership. Every reporting query that used to be a SQL join is now either an API aggregation call or a denormalized read model that must be kept in sync. Every data integrity guarantee that the relational database used to enforce for free is now your application's responsibility.

The question to ask before splitting a data boundary is not "can we split this?" It is: "What queries, transactions, and consistency guarantees cross this boundary, and are we prepared to replace all of them with application-level solutions?"

## Coupling Does Not Disappear — It Moves

Extracting a service does not remove coupling between two parts of a system. It moves the coupling from the code layer (where it is visible, searchable, and enforceable by the compiler) to the network layer (where it is implicit, runtime-dependent, and discoverable only through tracing and testing).

A **distributed monolith** is what you get when you split a system into services that still need to be deployed together, still share data schemas, or still fail together. You have all the operational complexity of microservices — network boundaries, serialization overhead, distributed debugging — with none of the benefits. This is not a rare edge case. It is the most common failure mode of microservice migrations.

The mechanical signature of a distributed monolith: you cannot deploy Service A without also deploying Service B. A schema change in Service A's API requires synchronized changes in three other services. Your services communicate through a shared database rather than through APIs. A failure in one service reliably cascades into failures in services that are supposed to be independent.

What went wrong is usually that the boundary was drawn along technical lines (a "database service," an "auth service," a "logging service") rather than along domain lines where the actual independence exists. If two services must change in lockstep for most feature work, they are not independent services — they are a monolith with a network call in the middle.

## Tradeoffs and Failure Modes

### Premature Decomposition

The most expensive architectural mistake is splitting too early, before you understand the domain well enough to draw boundaries correctly. Moving a boundary between modules in a monolith is a refactoring exercise — hours or days of work. Moving a boundary between services means migrating data, rewriting API contracts, updating every consumer, and changing the operational topology. It is weeks or months of work, and it often doesn't happen because the cost is prohibitive, so the wrong boundary persists and becomes load-bearing.

This is why the standard advice — start with a monolith, extract services when you have evidence that the boundary is correct — is not conservative timidity. It is engineering risk management. You are deferring irreversible decisions until you have the information to make them well.

### The Hidden Cost of Organizational Coordination

Microservices shift coordination costs from code-level integration to API contract negotiation and operational coordination. In a monolith, adding a field to a shared data structure is a code change with compiler-checked impact. In a microservices architecture, adding a field to a service's API requires versioning, backward compatibility analysis, consumer migration, and potentially running two versions simultaneously. The total person-hours spent on the change may be higher, not lower.

This cost is worth paying when teams genuinely need independent release cycles — when the alternative is a weekly deployment meeting with fifteen teams arguing over merge conflicts. It is not worth paying when two developers on the same team are maintaining both sides of the API.

### Observability as a Prerequisite, Not a Feature

In a monolith, you can troubleshoot a production issue with application logs and a stack trace. In a microservices architecture, a single user request may traverse a dozen services. Without distributed tracing (OpenTelemetry, Jaeger, Zipkin), you cannot reconstruct what happened. Without correlation IDs threading through every service hop, your logs are a disconnected pile of events. This is not an enhancement you add later — it is foundational infrastructure that must exist before the second service goes into production. Teams that skip this spend months debugging issues that would be trivial to diagnose in a monolith.

## The Mental Model

The decision between monolith and microservices is not a choice between simplicity and sophistication. It is a decision about where to pay the cost of boundaries. Every boundary you draw — whether it is a module boundary in code or a service boundary over the network — exists to enable independent change. The value of that independence is directly proportional to how often the things on each side of the boundary need to change independently, and the cost is directly proportional to how often they need to coordinate.

A well-structured monolith with clean module boundaries gives you most of the organizational benefits at a fraction of the operational cost. Extracting a service is justified when the coordination cost of keeping it in the monolith exceeds the operational cost of maintaining it as a separate system — and that calculation depends on team structure, deployment frequency, scaling requirements, and domain boundaries that you can only identify through experience with the actual system.

The question is never "should we use microservices?" The question is: "Where do the real boundaries in our system lie, and what is the cheapest boundary mechanism that gives us the independence we actually need?"

## Key Takeaways

- **Every service boundary converts a function call into a network call**, introducing failure modes that do not exist inside a single process — including the state of not knowing whether an operation succeeded.

- **Splitting data is the hard part of service extraction**, not splitting code. Every cross-boundary query, transaction, and foreign key constraint must be replaced with an application-level mechanism.

- **A distributed monolith — services that must deploy, change, or fail together — is the most common outcome of poorly planned microservice migrations**, and it carries the costs of both architectures with the benefits of neither.

- **The modular monolith is a legitimate architectural choice**, not a waypoint on the road to microservices. It provides internal separation with dramatically lower operational cost than network boundaries.

- **Observability infrastructure (distributed tracing, correlation IDs, centralized logging) is a prerequisite for operating microservices**, not a feature to add after migration. Without it, debugging distributed failures is effectively guesswork.

- **Premature service extraction is expensive to reverse.** Moving a boundary between modules is a refactor; moving a boundary between services is a migration. Defer service boundaries until you have evidence the boundary is correct.

- **The value of a boundary is proportional to the independence it enables; the cost is proportional to the coordination it requires.** Draw boundaries where change frequency diverges, not along technical layers.

- **The right question is not "monolith or microservices" but "where are the real boundaries, and what is the cheapest mechanism that provides the independence we need?"**

[← Back to Home]({{ "/" | relative_url }})
