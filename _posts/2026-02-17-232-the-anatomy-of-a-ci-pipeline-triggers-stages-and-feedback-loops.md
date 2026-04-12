---
layout: post
title: "2.3.2 The Anatomy of a CI Pipeline: Triggers, Stages, and Feedback Loops"
author: "Glenn Lum"
date:   2026-02-17 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers can describe what a CI pipeline does: it runs when you push code, it builds and tests your changes, and it tells you if something is broken. What most engineers have not internalized is that a pipeline is a *feedback system with economic properties*, and the design choices within it — what triggers it, how stages are ordered, what information flows back to the developer and when — are system design decisions with compounding consequences. A pipeline defined as a list of steps in a YAML file and a pipeline designed as an optimized feedback loop will run the same tools. They will not produce the same engineering culture, velocity, or reliability.

The Level 1 post established why CI matters, why reproducibility matters, and why pipeline speed shapes developer behavior. This post is about the internal structure: how triggers initiate execution, why stage ordering is an optimization problem with a correct framework, what makes feedback loops functional or broken, and what distinguishes a healthy pipeline from one that is actively degrading your team's ability to ship.

## How Triggers Actually Work

A CI pipeline does not "watch" your repository. The mechanism is event-driven. When you push a commit or open a pull request, your version control platform (GitHub, GitLab, Bitbucket) sends an HTTP POST — a **webhook** — to your CI system's ingestion endpoint. This webhook payload contains the event context: which repository, which branch, which commit SHA, which user, and what type of event occurred (push, pull request opened, tag created, etc.).

The CI system receives this payload and performs a **pipeline resolution step**: it matches the event against your pipeline configuration to determine which pipeline definitions apply and which stages within them should execute. This is where conditional logic takes effect. If your configuration specifies that a deployment stage only runs on the `main` branch, or that a particular test suite only runs when files in `/src/api/` change, the resolution step evaluates those conditions against the webhook context.

After resolution, the CI system places the resulting work onto a **job queue**. A runner — either a persistent machine or a dynamically provisioned container — picks the job off the queue, checks out the code at the specified commit, and begins execution.

This sequence matters because it explains several behaviors that otherwise seem mysterious. Two pushes to the same branch in quick succession produce two separate webhook events. Depending on your CI system's configuration, this may result in two full pipeline runs, or the system may cancel the first run when the second event arrives (**auto-cancellation of superseded commits**). If your CI system does not auto-cancel, you are burning compute on a commit that is already stale. If it does auto-cancel, you need to understand that intermediate commits never receive validation — which is fine for feature branches but dangerous if applied to your mainline.

The trigger mechanism also determines **what context is available inside the pipeline**. Environment variables like the branch name, commit SHA, event type, and changed file paths are populated from the webhook payload. Pipeline logic that branches on these values — running a lighter pipeline for documentation-only changes, skipping expensive integration tests for draft pull requests — is branching on trigger context, not on repository state. This distinction matters when debugging why a pipeline ran a stage you didn't expect or skipped one you needed.

## Stage Ordering as an Optimization Problem

The Level 1 post established the principle: run cheap, fast checks before expensive, slow ones. The underlying reason is economic, and the framework for reasoning about it is more precise than "fast things first."

Every stage in your pipeline has two relevant properties: its **cost** (wall-clock time multiplied by the compute resources it consumes) and its **failure probability** (how often it catches a problem). The goal of stage ordering is to minimize the **expected total cost** of a pipeline run across all commits, not just the successful ones.

Consider a pipeline with three stages: a lint check that takes 15 seconds and fails on 25% of commits, a unit test suite that takes 4 minutes and fails on 10% of commits, and an integration test suite that takes 12 minutes and fails on 5% of commits. If you run them sequentially in the order listed, a commit that fails linting never incurs the cost of unit or integration tests. You pay 15 seconds to eliminate a quarter of bad commits. Of the remaining commits, 10% fail unit tests at a cost of 4 minutes and 15 seconds total. Only commits that pass both reach integration testing.

Reverse the ordering — integration tests first — and every commit pays 12 minutes before you even check for lint errors. The average pipeline runtime across all commits increases substantially, and more importantly, the **time to first failure signal** increases for the most common category of failures.

The optimal ordering heuristic is: **sort stages by the ratio of failure probability to cost, descending**. Stages that are cheap and catch failures frequently should run first. Stages that are expensive and catch failures rarely should run last. This is directly analogous to short-circuit evaluation in boolean logic — you evaluate the cheapest predicate first.

This heuristic applies to stages that are independent. When stages have dependencies — you cannot run unit tests without first compiling the code — the dependency structure constrains your ordering. This is why a CI pipeline is more accurately modeled as a **directed acyclic graph (DAG)** than as a linear sequence. The build stage must precede the test stage, but linting and security scanning may have no dependency on the build output at all, meaning they can run in parallel with it.

```yaml
# A DAG-structured pipeline, not a linear sequence
stages:
  lint:
    runs: eslint, prettier --check
    # No dependencies — starts immediately
  security-scan:
    runs: trivy, gitleaks
    # No dependencies — starts immediately
  build:
    runs: docker build
    # No dependencies — starts immediately
  unit-test:
    needs: [build]
    runs: pytest
  integration-test:
    needs: [build]
    runs: pytest --integration
  publish-artifact:
    needs: [lint, security-scan, unit-test, integration-test]
```

In this structure, lint, security scanning, and the build all start concurrently. Unit and integration tests start as soon as the build completes. The artifact is only published if everything passes. The total wall-clock time is determined by the **critical path** through the DAG — the longest chain of dependent stages — not by the sum of all stage durations. Understanding this distinction is the difference between a 20-minute pipeline and an 8-minute pipeline running the same checks.

## What Makes a Feedback Loop Functional

A feedback loop is not just "the pipeline tells you pass or fail." A functional feedback loop has three measurable properties: **latency**, **specificity**, and **signal-to-noise ratio**.

**Latency** is the time from push to result. This is the property most teams focus on, and they're right to — but the relevant metric is not the total pipeline duration. It is the **time to first actionable signal**. If your lint stage fails in 15 seconds but the developer doesn't see the failure until the entire 12-minute pipeline completes, your effective latency is 12 minutes. CI systems that report stage results incrementally — surfacing failures as they occur rather than at the end — reduce effective latency without changing total duration. If your CI system does not do this natively, structuring your pipeline so that fast checks are in a separate, earlier phase (rather than parallel with slow checks) achieves the same effect.

**Specificity** is whether the failure tells the developer *what went wrong* and *where*. A pipeline that reports "unit tests failed" is less useful than one that reports "test_user_authentication.py::test_expired_token_returns_401 failed: AssertionError, expected 401 got 500." The mechanical investment here is in how test runners are configured to report output, how that output is surfaced in the CI UI, and whether failure annotations are pushed back to the pull request as inline comments on the relevant code. A developer who has to click through three pages of CI logs to find the relevant failure line is experiencing unnecessary friction, and that friction compounds into slower iteration cycles.

**Signal-to-noise ratio** is the property that, when degraded, destroys the entire value of CI. A **flaky test** — one that fails intermittently for reasons unrelated to the code change — is noise. When a developer sees a CI failure, they make a binary decision: "Is this my fault, or is it the pipeline's fault?" In a high-signal pipeline, the answer is almost always "my fault," and they investigate immediately. In a noisy pipeline, the answer is often "probably flaky," and they re-run the pipeline without investigating. Once this habit is established, *real* failures start getting re-run and ignored too. The feedback loop is now broken — it is producing output that no one trusts.

The mechanism of degradation is specific: flaky tests erode trust, eroded trust leads to re-run-and-ignore behavior, re-run-and-ignore behavior means genuine failures reach the mainline, failures on the mainline mean developers start their work from a broken baseline, and broken baselines produce more failures in CI, which further erode trust. This is a positive feedback loop in the destructive sense.

## The Shape of Pipeline Health

A healthy pipeline and a degraded pipeline can run the same stages using the same tools. The difference is observable in a small number of indicators.

In a **healthy pipeline**, the median time from push to result is stable and predictable. The failure rate on the mainline is near zero — failures happen on feature branches before merge, which is exactly where they should happen. When CI fails, developers investigate the failure rather than reflexively re-running. The pipeline definition changes intentionally, through reviewed pull requests, not through ad-hoc edits to "get the build passing."

In a **degraded pipeline**, median duration has crept upward because stages have been added without removing or optimizing existing ones. This is the **append-only pipeline** problem: every incident produces a new check, every new tool gets a new stage, and no one is accountable for total pipeline time. Flaky tests are "known issues" that have been known for months. Developers maintain a mental list of which failures are "real" and which can be ignored. Re-runs are so common that someone has written a bot to auto-retry failed jobs. The main branch fails often enough that `git bisect` doesn't work reliably because multiple commits are already broken.

The transition from healthy to degraded is not a sudden event. It is the accumulation of small decisions: adding a stage without measuring its impact, allowing a flaky test to persist "until next sprint," disabling a failing check instead of fixing the underlying issue, allowing pipeline duration to grow from 6 minutes to 14 minutes without anyone treating it as a problem. Each of these decisions is locally rational. Their aggregate effect is a CI system that costs more, catches less, and trains developers to ignore it.

## Tradeoffs and Failure Modes

### Parallelism vs. Resource Cost

Running stages in parallel reduces wall-clock time but multiplies resource consumption. If your pipeline runs five stages concurrently, each on its own runner, you are consuming five times the compute of a sequential pipeline for the same commit. For teams using metered CI services, this is a direct cost tradeoff. For teams running self-hosted runners, it is a capacity planning problem — high parallelism during peak push hours can exhaust your runner pool and create queuing delays that negate the parallelism gains. The correct level of parallelism depends on your runner capacity, your pipeline frequency, and how much wall-clock time is actually worth to your team.

### The Stage Sprawl Problem

As a codebase matures, the natural tendency is for pipelines to accumulate stages. Security scanning, license compliance checks, code coverage thresholds, performance benchmarks, documentation builds — each individually justified, collectively suffocating. A pipeline with 15 stages and a 25-minute runtime will be treated differently by developers than one with 6 stages and a 7-minute runtime, regardless of how valuable each individual stage is. The failure mode is not that any single stage is wrong. It is that no one is optimizing for the system-level property — total time to feedback — because each stage is owned by a different team or initiative.

### Flake Tolerance and the Re-Run Trap

Some teams respond to flaky tests by enabling automatic retries: if a job fails, re-run it once, and only report failure if it fails twice. This reduces developer friction but masks a deepening problem. Every automatic retry doubles the compute cost of flaky test runs. More critically, it makes flakiness invisible to the team — the pipeline is green, so no one investigates. The flake rate grows because there is no pain signal to drive fixes. The structurally sound response is to quarantine flaky tests (move them to a non-blocking stage or separate pipeline), track flake rates explicitly, and treat flake introduction as a defect.

## The Mental Model

A CI pipeline is a feedback system with economic properties. The trigger mechanism determines when and why it runs. The stage graph determines what it checks and in what order. The feedback loop determines whether the results actually change developer behavior.

The design goal is not "run all the checks." It is to *minimize the time and cost to deliver a trustworthy signal about every code change*. Trustworthy means the signal has high specificity and a high signal-to-noise ratio. Minimizing time means ordering stages so that the cheapest, most failure-prone checks create the earliest exit points. Minimizing cost means running expensive stages only when cheap stages have already passed, and parallelizing only where the wall-clock savings justify the resource multiplication.

If you can reason about your pipeline as a DAG with economic weights on each node and failure probabilities on each edge, you can make principled decisions about what to add, what to remove, what to reorder, and when your pipeline is becoming a liability instead of an asset.

## Key Takeaways

- A CI pipeline is triggered by webhook events from your VCS, not by polling — the event payload carries the context (branch, commit, changed files) that determines which stages execute.
- Stage ordering is an optimization problem: stages should be sorted by the ratio of failure probability to cost, with the cheapest and most frequently failing checks running first.
- A pipeline is a directed acyclic graph, not a linear sequence — stages without dependencies on each other can and should run concurrently, and total duration is determined by the critical path.
- Time to first actionable signal matters more than total pipeline duration; CI systems that surface stage-level results incrementally provide faster effective feedback even if total runtime is unchanged.
- Flaky tests degrade CI value through a specific mechanism: they train developers to distrust and ignore failures, which allows real failures to reach the mainline, which further degrades trust.
- Automatic retry of failed jobs masks flakiness and removes the pain signal that would drive fixes — quarantining flaky tests and tracking flake rates explicitly is structurally sounder.
- The append-only pipeline — stages accumulate, none are removed — is the most common degradation pattern, and it is driven by the fact that no single team owns total pipeline time as a system-level metric.
- A healthy pipeline is not one that runs more checks; it is one where every failure is investigated, the mainline is consistently green, and developers trust the signal enough to act on it immediately.

[← Back to Home]({{ "/" | relative_url }})
