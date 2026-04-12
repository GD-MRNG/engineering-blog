---
layout: post
title: "3.4.1 The Cloud Billing Model: On-Demand, Reserved, and Spot"
author: "Glenn Lum"
date:   2026-04-03 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most engineers encounter the three cloud pricing models — on-demand, reserved, and spot — as a dropdown menu or a line in a Terraform config. They appear to be three price tags for the same underlying resource: a virtual machine, a block of compute, a managed instance. Pick the cheaper one and move on.

This framing is wrong in a way that costs real money. On-demand, reserved, and spot are not three prices for the same thing. They are three different contracts that encode different assumptions about how your workload behaves over time, how much risk you're willing to absorb, and how your architecture responds to interruption. Choosing between them is not procurement. It is an architectural decision that propagates into how you design for failure, how you plan capacity, and what your system can tolerate when the contract's conditions activate.

The Level 1 post established that cost is an engineering responsibility and that architectural patterns have different cost profiles. This post explains the mechanics underneath the pricing models themselves — what you are actually purchasing in each case, why the discounts exist, and how the choice of pricing model constrains or liberates the systems you build on top of it.

## What the Cloud Provider Is Actually Selling

To understand the three models, you need to understand what the provider is optimizing on their side of the transaction. Cloud providers operate enormous fleets of physical hardware. Their fundamental economic challenge is **capacity utilization**: keeping as much of that hardware busy as possible, because idle servers cost them money (power, cooling, depreciation) without generating revenue.

The three pricing models are the provider's mechanism for segmenting demand by predictability.

**On-demand** customers are the least predictable. They spin up instances at arbitrary times, for arbitrary durations, and tear them down without notice. The provider must maintain enough spare capacity to serve this unpredictable demand, which means keeping servers idle as a buffer. On-demand prices are the highest because the customer is paying for optionality — the right to consume capacity at any time, for any duration, with no commitment. The premium you pay is the cost of the provider holding inventory for you.

**Reserved** customers are highly predictable. By committing to a specific quantity of compute for one or three years, they give the provider a demand signal that is stable enough to plan around. The provider can allocate capacity with confidence, reduce the buffer they need to maintain, and even make hardware purchasing decisions based on aggregate reservation commitments. The discount (typically 30% to 72% off on-demand, depending on the term length and payment structure) is the provider paying you for that predictability.

**Spot** customers absorb the provider's excess. At any given moment, some fraction of the provider's fleet is idle — reserved capacity that isn't being used yet, on-demand buffer that isn't needed right now, or capacity that was just freed by another customer. Spot pricing lets the provider sell this surplus rather than let it sit idle. The discount is steep (often 60% to 90% off on-demand) because the provider retains the right to reclaim that capacity with minimal notice when someone who is paying more needs it. You are buying leftover inventory, and you get a leftover-inventory price.

## On-Demand: No Commitment, No Constraints, No Discount

On-demand is the default. You request an instance, the provider provisions it from available capacity, and you pay a fixed per-hour (or per-second) rate for as long as it runs. There is no contract, no minimum, and no commitment beyond the current billing increment.

The non-obvious property of on-demand is that its simplicity is its cost. You are paying the highest rate not because the compute is better, but because you are giving the provider zero information about your future behavior. Every on-demand instance represents demand that could disappear in the next minute or persist for the next year, and the provider prices accordingly.

On-demand makes sense for workloads that are genuinely unpredictable: development environments, spike handling, short experiments, or any capacity you aren't confident you'll still need in three months. It also serves as the implicit baseline against which the other two models are measured. When someone says a reserved instance saves 40%, the comparison is always against on-demand.

The architectural implication is minimal. On-demand imposes no constraints on your system design. It doesn't shape how you handle failure or plan capacity. It simply costs more.

## Reserved: Commitment as a Financial Instrument

Reserved pricing is the most mechanically misunderstood of the three models. Engineers often think of it as "pre-purchasing" an instance — as if you are paying for a specific physical server that sits waiting for you. That is not what happens.

A reservation is a **billing construct**. When you purchase a reserved instance (or a savings plan, which is the more flexible evolution of the same concept), you are making a financial commitment to a certain volume of compute usage over a defined term. In return, any usage that matches the reservation's parameters is billed at the discounted rate instead of the on-demand rate. If you run matching instances, the discount applies automatically to your bill. If you don't, you still pay for the reservation.

This distinction matters because it reveals the core risk: **a reservation you don't use is more expensive than on-demand.** If you commit to a three-year reserved instance for a service that gets decommissioned after six months, you pay for the remaining thirty months of unused capacity. The discount only materializes as savings if your actual usage meets or exceeds the commitment.

### Payment Structures and Their Tradeoffs

Most providers offer three payment options for reservations: **all upfront**, **partial upfront**, and **no upfront**. The all-upfront option gives the deepest discount because the provider gets the entire payment immediately — they can invest that capital, and they bear no collection risk. Partial upfront splits the cost between an initial lump sum and a reduced monthly rate. No upfront spreads the entire cost across the term at a slightly higher rate, but still substantially below on-demand.

The choice between these is a capital allocation decision. All-upfront reservations produce the best unit economics but tie up cash and create the most painful write-off if the reservation goes unused. No-upfront reservations are less capital-efficient but more forgiving if your plans change, since the sunk cost at any point is lower.

### Savings Plans vs. Reserved Instances

AWS introduced Savings Plans as a more flexible version of reserved instances, and other providers have followed with similar constructs. A traditional reserved instance is scoped to a specific instance family, region, and sometimes availability zone. A savings plan commits to a dollar-per-hour spend rather than a specific instance type. If you commit to $10/hour of compute usage, any usage across eligible instance types in eligible regions is billed at the savings plan rate up to that threshold, and on-demand above it.

This matters architecturally because savings plans decouple the financial commitment from the infrastructure commitment. You can change instance types, migrate between regions, or refactor your service fleet without invalidating your cost savings — as long as your total compute spend stays at or above the committed level. This is a significant improvement for teams that expect their infrastructure to evolve over the commitment term.

### Scoping and Application

Reservations apply at the billing level, not the infrastructure level. A reserved instance for `m5.xlarge` in `us-east-1` doesn't attach to a specific running instance. It applies to any `m5.xlarge` usage in `us-east-1` across your account (or across your organization, depending on scope settings). This means reservations can float across instances as you scale up and down, which is useful — but it also means understanding where your reservations are applying requires reading the billing data carefully, not just looking at your infrastructure.

## Spot: Cheap Capacity with a Kill Switch

Spot instances are the model most likely to be underestimated in both their savings potential and their operational implications.

When you launch a spot instance, you receive a standard compute instance at a steep discount. That instance runs identically to an on-demand instance — same hardware, same performance, same networking. The difference is entirely in the contract: the provider can reclaim that instance with a **two-minute warning** (on AWS; the notice period varies by provider) whenever they need the capacity back for on-demand or reserved customers.

The two-minute window is not a grace period for you to find an alternative. It is a termination notice. Your workload gets two minutes to checkpoint state, flush buffers, deregister from load balancers, or do whatever it needs to do before it is forcibly shut down. If your application has not been designed to handle this, two minutes is nothing.

### What Drives Spot Reclamation

Reclamation frequency is not random. It is a function of supply and demand for a specific instance type in a specific availability zone. Popular instance types in busy regions get reclaimed more frequently. Obscure instance types or less popular zones may run for weeks without interruption. AWS publishes historical interruption frequency data by instance type, which is the single most useful signal for deciding whether spot is viable for a given workload.

This creates a non-obvious strategy: **instance type diversification**. Instead of requesting a single instance type, you configure your spot fleet to accept any of several instance types that meet your performance requirements. A workload that needs 8 vCPUs and 32 GB of RAM might accept `m5.2xlarge`, `m5a.2xlarge`, `m6i.2xlarge`, or `r5.2xlarge`. By spreading demand across multiple pools, you reduce the probability that all your instances get reclaimed simultaneously, and you increase the likelihood that at least one pool has available capacity.

### The Architectural Requirement

Spot is not a pricing option you apply to existing architecture. It is a pricing option that requires a specific class of architecture.

Workloads that run well on spot share common properties: they are **stateless** or can checkpoint and resume, they are **horizontally scalable** so that losing one node doesn't lose the whole job, and they either tolerate **partial results** during interruptions or have a mechanism to retry failed units of work. Batch processing, CI/CD builds, data pipeline stages, render jobs, and stateless web tier workers behind a load balancer are canonical examples. A singleton stateful database is not.

The critical design pattern is **graceful degradation on interruption**. Your system must detect the reclamation signal, stop accepting new work, complete or checkpoint in-progress work, and terminate cleanly — all within the notice window. This is real engineering work. It requires interrupt signal handlers, external state stores, and often a fallback to on-demand capacity to maintain availability during spot shortages.

## Where These Models Break and Where They Get Misused

**The unused reservation.** This is the most common and most expensive failure mode. A team purchases reserved instances based on current usage, then refactors a service, migrates to containers, or changes instance types. The reservations continue billing. At scale, organizations can accumulate hundreds of thousands of dollars in unused reservations. Mitigation requires either convertible reservations (which offer smaller discounts) or, preferably, savings plans scoped to flexible compute rather than specific instance types. It also requires a process — someone needs to monitor reservation utilization monthly.

**The unprotected spot deployment.** A team deploys a service on spot instances because of the cost savings, but the application has no interruption handling. When reclamation hits, requests drop, jobs fail, and the team scrambles. The savings evaporate into incident response time. Spot demands upfront investment in interruption-tolerant design; the cost savings are the return on that investment, not a free discount.

**The on-demand plateau.** Many organizations run entirely on on-demand for years because nobody has the mandate or the information to do anything else. This is not a failure of awareness — it is usually a failure of process. Reservation and spot decisions require usage data, forecasting, and ongoing management. Without a FinOps function or at least a designated owner, the default is the most expensive option.

**Overcomplicated blending.** Pursuing the theoretical optimum — the perfect mix of reserved, spot, and on-demand — can become its own cost center. Teams build elaborate automation to shift workloads between pricing models, maintain reservation portfolios, and track spot interruption rates. The operational overhead of managing this complexity sometimes exceeds the savings it produces, particularly for smaller-scale deployments where the absolute dollar difference is modest.

## The Model to Carry Forward

The three pricing models map to two axes: **time commitment** and **interruption tolerance**. On-demand sits at zero commitment and zero interruption risk — maximum flexibility, maximum cost. Reserved sits at high time commitment and zero interruption risk — you trade the ability to change your mind for a lower rate. Spot sits at zero time commitment but high interruption risk — you trade reliability for the lowest rate.

Every workload has a position on these two axes. A production database has near-zero interruption tolerance and predictable long-term demand — it belongs on reserved. A nightly batch pipeline can tolerate interruptions and doesn't need to run at a specific time — it's a natural fit for spot. A new service whose traffic patterns you don't yet understand belongs on on-demand until you have enough data to commit.

The mistake is treating pricing model selection as a finance exercise. It is an architecture exercise. The pricing model you choose constrains what your system can tolerate, and what your system can tolerate determines which pricing model is safe to use. These decisions compose: a fleet that is architecturally capable of spot can cut compute costs by 60% to 90%; a fleet that isn't will pay on-demand prices forever. The pricing model is downstream of the architecture, and the architecture should be upstream of the cost conversation.

## Key Takeaways

- On-demand, reserved, and spot are not three prices for the same product — they are three contracts that encode different assumptions about workload predictability and interruption tolerance.
- The cloud provider's discounts exist because predictable demand (reserved) and surplus absorption (spot) reduce the provider's own cost of maintaining idle capacity. The discount is not arbitrary; it reflects real value the customer provides to the provider.
- A reserved instance is a billing construct, not a physical allocation — it applies as a discount to matching usage on your bill, and unused reservations cost more than having bought nothing.
- Savings Plans decouple financial commitment from infrastructure commitment, making them more resilient to the architectural changes that frequently invalidate traditional reserved instances.
- Spot instances require architecture designed for interruption: stateless compute, external state, checkpointing, and graceful shutdown within the reclamation notice window. The discount is the return on that engineering investment.
- Instance type diversification across multiple spot pools is the primary mechanism for reducing correlated interruption risk in spot-based workloads.
- The most expensive failure mode at scale is not choosing the wrong pricing model — it is choosing none, defaulting to on-demand, and never revisiting the decision as usage patterns become clear.
- Pricing model selection is an architectural decision that should be made alongside decisions about fault tolerance, statefulness, and scaling strategy — not after the system is already in production.

[← Back to Home]({{ "/" | relative_url }})
