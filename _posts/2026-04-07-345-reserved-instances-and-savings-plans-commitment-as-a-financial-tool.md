---
layout: post
title: "3.4.5 Reserved Instances and Savings Plans: Commitment as a Financial Tool"
author: "Glenn Lum"
date:   2026-04-07 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most engineers understand that Reserved Instances and Savings Plans give you a discount for committing in advance. That understanding is correct and almost entirely insufficient. The actual challenge is not "should we commit?" — for stable workloads the answer is obviously yes — but rather *what exactly are you committing to*, *how does the discount mechanically apply to your bill*, and *what happens when your infrastructure changes underneath an active commitment*. The gap between "we should buy some RIs" and making commitment decisions that hold up over twelve or thirty-six months is where real money gets wasted, either through over-commitment to resources you stop using or through under-commitment driven by fear of locking in wrong.

This post covers the mechanics that govern how commitment-based pricing actually works, so that when you reach the point of making these decisions, you are reasoning from a model rather than guessing.

## How the Discount Actually Applies

A Reserved Instance is not a special instance. This is the most common misconception. When you purchase an RI, you are not reserving a specific virtual machine that sits waiting for you. You are purchasing a **billing discount** that automatically applies to any running instance that matches the RI's attributes. If you buy a one-year RI for an `m5.xlarge` in `us-east-1`, and you have an `m5.xlarge` running in `us-east-1`, your bill for that instance drops from the on-demand rate to the reserved rate. If that instance stops and you launch a different `m5.xlarge` in the same region, the discount floats to the new instance. If no matching instance is running, you pay for the RI anyway. The reservation is a financial instrument attached to your account, not a resource allocation attached to a machine.

Savings Plans work similarly but commit on a different axis. Instead of reserving a specific instance type in a specific region, you commit to spending a **dollar amount per hour** on eligible compute. If you commit to $10/hour, AWS applies that $10 toward your compute usage at the Savings Plan rate rather than the on-demand rate. Any usage beyond what $10/hour covers at the discounted rate is billed at on-demand. The commitment is monetary, not infrastructural.

This distinction — RI commits to an instance shape, Savings Plan commits to a spend rate — is the foundation everything else builds on.

## The Dimensions of Commitment

Every commitment-based purchase has three independent dimensions that determine both the discount depth and the risk exposure.

### Term Length

One year or three years. Three-year terms offer significantly deeper discounts — often 55 to 72 percent off on-demand for all-upfront commitments versus 30 to 42 percent for one-year terms. The tradeoff is prediction horizon. You are betting that your compute needs in month thirty will resemble your compute needs today. For core infrastructure that has been stable for years, this is a reasonable bet. For a product line that is growing unpredictably or a team that is actively re-architecting, a three-year commitment is a leveraged position against your own roadmap.

### Payment Structure

Three options: **all upfront**, **partial upfront**, and **no upfront**. All upfront yields the deepest discount because AWS gets your money immediately and eliminates their collection risk. No upfront yields the smallest discount but preserves your cash and limits the sunk cost if you stop needing the resource — though you are still contractually committed to the hourly charge for the full term. Partial upfront splits the difference.

The payment structure does not change the total commitment. A no-upfront RI still obligates you for every hour of the term. The difference is cash flow timing and the marginal discount improvement. For most organizations, the delta between no-upfront and all-upfront within the same term is 3 to 8 percentage points — meaningful at scale, but not the primary lever.

### Scope and Flexibility

This is where the variants diverge most and where the decision has the most architectural consequence.

**Standard Reserved Instances** lock to a specific instance family, region (or availability zone), operating system, and tenancy. An `m5.xlarge` Linux RI in `us-east-1` applies only to `m5.xlarge` Linux instances in `us-east-1`. However, regional-scope RIs for Linux have **size flexibility** within the instance family, governed by a normalization factor. The normalization factor doubles with each size step: `small` is 1, `medium` is 2, `large` is 4, `xlarge` is 8, `2xlarge` is 16, and so on. A single `m5.xlarge` RI (factor 8) can cover two `m5.large` instances (factor 4 each), or one `m5.large` and four `m5.small` instances, or any combination that sums to 8. This flexibility is automatic and happens at billing time.

**Convertible Reserved Instances** offer less discount (typically 5 to 10 points less than Standard) but can be exchanged for a different instance family, OS, or tenancy mid-term, as long as the new reservation's value is equal to or greater than the original. You cannot convert down in value, but you can convert up by paying the difference. This is your hedge against architectural change.

**Compute Savings Plans** are the most flexible commitment instrument. They apply to any EC2 instance regardless of family, size, region, or OS, and also cover AWS Fargate and Lambda usage. The discount is slightly shallower than an equivalent EC2-specific commitment, but the plan automatically applies to whatever eligible compute you are running.

**EC2 Instance Savings Plans** sit between Compute Savings Plans and RIs. They lock to a specific instance family in a specific region but are flexible on size, OS, and tenancy. Discount depth is comparable to Convertible RIs but without the exchange friction.

The gradient is clear: more flexibility means a shallower discount. The question is not which instrument is "best" but which matches the stability profile of each layer of your infrastructure.

## Break-Even Math

The break-even calculation for commitment-based pricing is simpler and more useful than most people realize. If a commitment gives you a discount of *d* percent, you break even when your actual utilization of that commitment reaches *(1 − d)* of the total term.

Concretely: a commitment with a 40 percent discount breaks even at 60 percent utilization of the term. For a one-year, 40-percent-discount RI, that is roughly 7.2 months. If the matching instance runs for at least 7.2 months out of twelve, the RI saved you money compared to on-demand. If you decommission the workload at month five, you lost money. For a 60 percent discount (typical of a three-year all-upfront commitment), break-even is at 40 percent utilization — about 14.4 months out of 36. The deeper the discount, the earlier you break even and the more room you have for plans to change.

This means deep-discount, long-term commitments are paradoxically *more forgiving* of change than shallow-discount, short-term ones in absolute time, though the tail exposure (months 15 through 36 of wasted commitment) can still be significant in dollar terms.

## Application Order and Portfolio Behavior

When you hold multiple commitments — a mix of RIs and Savings Plans — the order in which they apply to your bill matters. AWS applies the most specific discounts first: zonal RIs, then regional RIs, then EC2 Instance Savings Plans, then Compute Savings Plans. On-demand pricing covers whatever remains.

This ordering means you can layer commitments: use specific RIs for the most stable, predictable workloads where you want the deepest discount, and layer a Compute Savings Plan on top to catch the rest of your baseline compute at a moderate discount. The Savings Plan acts as a flexible backstop. If your RI-covered workload shrinks, the freed-up RI has nowhere to apply (if nothing else matches), but the Savings Plan dollars automatically shift to cover whatever compute is actually running.

This portfolio approach — specific commitments for stable base, flexible commitments for the variable middle, on-demand for the peaks — mirrors how mature organizations actually manage commitment-based pricing. You are not making a single binary decision. You are constructing a layered portfolio.

## Tradeoffs and Failure Modes

### Over-Commitment to a Dying Architecture

The most expensive failure mode is committing heavily to infrastructure you are about to migrate away from. A team purchases three-year Standard RIs for a fleet of `r5` instances running a large Redis cluster, and six months later the organization decides to move that workload to a managed service like ElastiCache Serverless. The RIs cannot be converted (Standard, not Convertible), they do not apply to the managed service, and there are 30 months of commitment remaining. Standard RIs can be sold on the AWS Marketplace, but typically at a loss, and the process is manual and illiquid.

This is not a hypothetical edge case. It is the normal consequence of making infrastructure commitments without accounting for architectural roadmap.

### The Coverage Trap

Coverage — the percentage of your running compute hours that are covered by commitments — is the metric most teams optimize for. The instinct is to push coverage toward 100 percent. This is wrong. Pushing coverage to 100 percent means committing to your peak usage, which means you are paying committed rates for instances that only run part of the time. The correct target is to cover your **steady-state baseline**: the compute that runs 24/7, that you are confident will still be running at the end of the commitment term. Everything above that baseline should remain on-demand or, for interruptible workloads, on Spot.

Utilization — the percentage of your commitment hours that are actually used by matching instances — is the metric that tells you whether your existing commitments are healthy. If utilization is below 100 percent, you are paying for commitments that are not being applied to anything. Coverage tells you about opportunity. Utilization tells you about waste.

### Organizational Ownership Gaps

Commitment purchases are typically centralized (a FinOps team or cloud platform team buys them) but the workloads they cover are decentralized (individual product teams run the instances). When a product team decommissions a workload, they may not know or care that it was covered by a commitment that is now going unused. The team that purchased the commitment may not find out for weeks. This organizational gap — between who holds the financial instrument and who controls the underlying infrastructure — is a persistent source of waste and requires explicit process to manage: regular utilization reviews, commitment-aware change management, or automated alerting when commitment utilization drops.

### Discount Rate Illusion

A 60 percent discount sounds transformative. But the discount is relative to on-demand pricing, and on-demand pricing is the *highest* price AWS charges. If you are comparing a Savings Plan against Spot instances for a fault-tolerant batch workload, the Savings Plan discount may actually be more expensive than Spot. Commitments are the right tool for workloads that need consistent, uninterrupted capacity. For workloads that can tolerate interruption, Spot pricing often undercuts even the deepest committed rates.

## The Mental Model

Commitment-based pricing is a financial position on your future infrastructure, not a procurement transaction. Each commitment is a bet: you are betting that a specific pattern of compute usage will persist for one or three years, and AWS is giving you better pricing in exchange for the guaranteed revenue. Like any position, it has a payoff curve — it saves you money when your prediction holds and costs you money when it does not.

The strategic question is never "should we commit?" for workloads that clearly run continuously. The strategic question is: *how much of our compute estate is stable enough to commit against, at what level of specificity, and what is our exposure if we are wrong?* You are constructing a portfolio of bets with different risk-reward profiles — deep and specific where you are confident, shallow and flexible where you are not, and uncommitted where usage is variable or the architectural future is uncertain.

If you carry one idea from this post, it should be this: the discount percentage is not the decision variable. The decision variable is the stability of the workload over the commitment term. Discount depth is a consequence of that stability, not a reason to commit.

## Key Takeaways

- Reserved Instances are billing discounts that float to matching usage, not dedicated machines — if no matching instance is running, you pay for the RI anyway.
- Savings Plans commit to a dollar-per-hour spend rate on compute rather than a specific instance type, making them inherently more flexible than RIs but typically offering slightly shallower discounts.
- The break-even utilization for any commitment is approximately (1 − discount rate) of the term: a 40% discount breaks even at 60% utilization, a 60% discount at 40%.
- Size flexibility through normalization factors means a single regional RI can cover multiple smaller instances in the same family — this happens automatically at billing time and is one of the most underused features.
- The correct commitment target is your steady-state baseline, not your peak or average usage — committing above the baseline means paying reserved rates for hours where no matching instance is running.
- Coverage (how much of your usage is committed) and utilization (how much of your commitments are being used) are different metrics that answer different questions; optimizing for coverage alone leads to over-commitment.
- Layering specific commitments for stable workloads with flexible Savings Plans as a backstop and on-demand for variable peaks is how mature organizations construct their commitment portfolio.
- The primary risk of commitment-based pricing is not the commitment itself but the organizational gap between who purchases the commitment and who controls the workload it covers — architectural changes that orphan active commitments are the most common and most expensive failure mode.


[← Back to Home]({{ "/" | relative_url }})
