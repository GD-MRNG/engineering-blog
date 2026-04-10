---
layout: post
title: "1.3.6 The Data Ownership Problem: Why Shared Databases Break Service Independence"
author: "Glenn Lum"
date:   2026-02-03 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most teams that adopt microservices get the deployment topology right. Separate repositories, separate CI pipelines, separate containers. Clean boxes on the architecture diagram. Then they connect three, five, or fifteen of those boxes to the same PostgreSQL instance, reading and writing to the same tables, and wonder why they still can't deploy a service without coordinating with two other teams.

The shared database is where microservice independence goes to die — not as a vague architectural concern, but in the specific, mechanical sense that a shared schema is a shared contract, and a shared contract between independently deployed services means every schema change is a cross-team coordination event. You've built a distributed monolith: all the operational complexity of a distributed system with none of the deployment independence you were after.

Understanding *why* this happens — at the level of the coupling mechanics, not the architectural principle — is what separates teams that successfully decompose systems from teams that end up with something worse than the monolith they started from.

## The Schema Is an Unversioned API

When Service A and Service B both connect to the same database and query the `orders` table, they share a dependency on that table's structure: its column names, types, constraints, indexes, and relationships to other tables. This is a contract. It functions exactly like an API contract between the two services — it defines the shape of the data one service produces and another consumes.

The difference between this contract and an actual API is that nobody treats it like one. There's no versioning. There's no backward compatibility policy. There's no contract test. There's no deprecation path. When a developer on Service A's team needs to rename a column, split a table, or change a foreign key relationship, they're making a breaking change to every other service that touches that table. But unlike a breaking change to a REST endpoint — which would be caught by integration tests, flagged in API reviews, and managed through versioning — a schema change often isn't discovered until something fails in production.

This is the core mechanic: **a shared database creates an implicit, unversioned, untested API between every service that touches it.** The coupling isn't visible in any service's codebase. It lives in the schema itself, and it becomes apparent only when someone tries to change it.

## How Schema Coupling Defeats Deployment Independence

Walk through a concrete scenario. You have an `orders` service and a `billing` service. Both read and write to an `orders` table:

```sql
CREATE TABLE orders (
  id UUID PRIMARY KEY,
  customer_id UUID NOT NULL,
  status VARCHAR(50) NOT NULL,
  total_amount DECIMAL(10,2) NOT NULL,
  billing_address TEXT,
  created_at TIMESTAMP NOT NULL
);
```

The orders service manages order lifecycle — creation, status transitions, fulfillment. The billing service reads from this table to generate invoices and writes back payment status.

Now the orders team needs to support multi-currency pricing. They need to change `total_amount` to store a value alongside a currency code. Maybe they split it into `amount` and `currency`, maybe they add a separate column, maybe they restructure entirely.

Any of these changes will break the billing service. The billing service has queries like `SELECT total_amount FROM orders WHERE ...` baked into its code. It has logic that assumes `total_amount` is a plain decimal representing a single currency.

So the orders team can't just deploy their change. They need to coordinate with the billing team. They need to agree on a migration strategy. They need to deploy in lockstep or design a multi-phase migration where both old and new columns coexist. They need to verify their changes against the billing service's queries.

This is the exact coordination overhead microservices were supposed to eliminate. Two separately deployable services that cannot, in practice, be deployed separately.

This isn't a one-time cost. It recurs on every schema change that touches a shared surface. Over time, teams learn to avoid schema changes, so the schema calcifies and becomes a constraint on how fast any service can evolve. Or teams make changes without coordinating, and things break at runtime.

## The Read Path Is Not Innocent

A common rationalization: "We only *read* from that table. We're not writing, so there's no real coupling."

This is wrong. Read-only access to another service's tables creates coupling in two distinct ways.

First, **you are coupled to the schema's shape.** If the owning service restructures its tables — normalizes, denormalizes, renames columns, changes types — your queries break. The coupling is identical to the write case.

Second, **you are coupled to the schema's semantics.** When the billing service reads `status = 'completed'` from the orders table, it's making an assumption about what "completed" means in the orders domain. If the orders team later introduces a distinction between "completed" and "fulfilled" to handle partial fulfillment, the billing service's interpretation of that field is wrong. The data hasn't changed shape, but its meaning has shifted, and the billing service has no way to know.

This semantic coupling is subtler and more dangerous than structural coupling. Schema changes produce errors. Semantic drift produces *wrong behavior* that passes all validation checks.

## The Write Path and Ownership Ambiguity

When multiple services write to the same table, the problems compound. You get ambiguity about who owns the data and who's responsible for its integrity.

Consider our orders table. The orders service sets `status` to `'pending'` on creation. The billing service sets it to `'paid'` after successful payment. The fulfillment service sets it to `'shipped'` after dispatch. Three services writing to the same column.

Who enforces valid state transitions? In a monolith, a single `Order` model contains the business logic: an order can move from `pending` to `paid`, never from `shipped` back to `pending`. With three services writing to the same column, that business logic is either duplicated across all three codebases (and inevitably diverges), or it doesn't exist at all and you rely on convention.

This is how you get an order with `status = 'shipped'` that was never paid for. Not because anyone made an obvious mistake, but because the state machine that should govern that column is scattered across three codebases with no single point of enforcement.

**Data ownership** means one service is the authoritative source for a piece of data: it controls writes, enforces invariants, and defines what the data means. When a database is shared, ownership is ambiguous by default, and ambiguous ownership is effectively no ownership.

## What the Alternatives Actually Look Like

If services can't share a database, how does Service B get data that Service A owns? Three fundamental patterns, differing in when the data moves and what consistency guarantees you retain.

### API-Mediated Access

Service B calls Service A's API at query time. Service A exposes only what it chooses, in a format it controls, with versioning it manages. The underlying schema is fully encapsulated — Service B never sees the table structure.

The cost: Service B now depends on Service A being available at query time. If Service A is down or slow, Service B degrades. You've traded schema coupling for runtime coupling. For many use cases this is a good trade — runtime coupling is visible, measurable, and manageable with circuit breakers and timeouts. Schema coupling is invisible and discovered during incidents.

For high-throughput read paths or queries that would need to join data across multiple services, synchronous API calls introduce latency and fragility that may not be acceptable.

### Event-Carried State Transfer

Service A publishes events carrying the data Service B needs. When an order is created, Service A emits an `OrderCreated` event containing the order ID, customer ID, amount, and currency. Service B consumes this event and stores a local copy in its own database, in whatever schema suits its domain.

Service B now has zero runtime dependency on Service A. It queries its own local store at any time. It owns its schema and can restructure its local representation without coordinating with anyone.

The cost: the data in Service B's local store is **eventually consistent** with Service A's authoritative data. If Service A updates an order and Service B hasn't processed the event yet, Service B is working with stale data. The event structure between the services becomes the new contract — it needs versioning and backward compatibility management just like a REST endpoint.

### Change Data Capture

A mechanical variant of event-carried state transfer: instead of the application publishing explicit domain events, a tool like Debezium reads the database's write-ahead log and publishes row-level changes as events. Service B consumes these and materializes its own read model.

This is valuable when you can't modify Service A's code to publish events — common during incremental migrations away from a shared database. It carries the same eventual consistency costs, plus an additional one: the events are shaped like database mutations (inserts, updates, deletes on specific columns) rather than domain events, which makes them harder for consumers to interpret meaningfully. You're leaking schema structure through the back door, which partially reintroduces the coupling you were trying to eliminate.

## Where This Breaks and What It Costs

### The Distributed Monolith Trap

The most common failure: teams adopt microservices, keep the shared database, and end up with a system that has all the operational costs of distribution (network failures, partial failures, distributed tracing) and none of the benefits (independent deployment, team autonomy). This is strictly worse than a monolith. The monolith at least gave you local transactions and a single debugger.

The response should not be to panic-split the database. Prematurely separating data stores without understanding domain boundaries leads to a different failure.

### Splitting Along Wrong Boundaries

If you separate databases along incorrect service boundaries, you end up performing expensive cross-service joins or multi-service transactions for operations that should be local. A team that splits `orders` and `order_items` into separate services with separate databases will spend enormous effort replicating what a single SQL join did for free.

The database split must follow the domain boundary, not the other way around. If two tables are almost always queried together and participate in the same transactions, they belong to the same service. Splitting them introduces distributed coordination for zero architectural benefit.

### Underestimating the Consistency Cost

Teams that move from a shared database to event-carried state transfer often underestimate how much of their system's correctness was silently relying on strong consistency. When the billing service could read directly from the orders table, it always saw the latest state. Now it works from a local copy that might be seconds — or during an outage, minutes — behind.

This produces concrete bugs: a customer cancels an order, but the billing service hasn't received the cancellation event and charges them anyway. The refund path now has to handle a case that never existed when both services read from the same source of truth.

The answer isn't to avoid eventual consistency. It's to design explicitly for it. But you can't design for it if you don't understand that leaving the shared database means giving up an implicit consistency guarantee that was silently keeping things correct.

### The "Just One More Query" Erosion

Even teams that start with clean ownership erode it incrementally. A developer needs one column from another service's table for a report. A direct database connection is five minutes of work. Building the proper API endpoint that doesn't exist yet is a week. The expedient choice wins. Six months later, fifteen services read from each other's tables through a web of cross-schema queries, and you're back to a shared database in all but name.

This is a governance problem, not a technical one. Direct database access to another service's schema must be treated as a boundary violation, not a shortcut.

## The Model to Carry Forward

A database is not just storage — it is a contract surface. When two services share a database, the schema becomes an implicit API between them: unversioned, untested, and invisible in any service's dependency graph. Every schema change becomes a cross-team coordination event, which is the precise coupling that service decomposition exists to eliminate.

The principle: **each service should own its data the way it owns its code.** The service controls the internal representation, enforces the invariants, and exposes only an explicit, versioned interface for others to consume. The database is an implementation detail of the service, not a shared integration layer.

This creates real costs — you lose cross-service joins, you lose distributed ACID transactions, you take on eventual consistency. These costs are the price of deployment independence, and they are worth paying only when you actually need that independence. Understanding this tradeoff is the conceptual prerequisite to reasoning about sagas, event sourcing, CQRS, and every other pattern that exists to manage data across service boundaries.

## Key Takeaways

- A shared database between services creates an implicit, unversioned API at the schema level — every schema change becomes a cross-team coordination event that defeats the deployment independence microservices are supposed to provide.

- Read-only access to another service's tables is still coupling: you depend on both the shape and the semantic meaning of the data, both of which can change without warning.

- When multiple services write to the same table, data ownership becomes ambiguous, business invariants get scattered across codebases, and state corruption becomes a matter of time rather than possibility.

- The distributed monolith — microservices sharing a database — is strictly worse than a well-structured monolith because you absorb the costs of distribution while gaining none of its benefits.

- Splitting a database along the wrong service boundaries forces expensive cross-service coordination for operations that should be local; the data split must follow the domain boundary, not precede it.

- API-mediated access trades invisible schema coupling for visible runtime coupling — generally a favorable trade because runtime dependencies can be measured, monitored, and mitigated.

- Event-carried state transfer eliminates runtime coupling but introduces eventual consistency, which requires explicit design for every case where stale data could produce incorrect behavior.

- Data ownership boundaries erode through incremental shortcuts; maintaining them is a governance discipline, not a one-time architectural decision.

[← Back to Home]({{ "/" | relative_url }})
