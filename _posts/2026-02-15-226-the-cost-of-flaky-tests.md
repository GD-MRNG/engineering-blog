---
layout: post
title: "2.2.6 The Cost of Flaky Tests"
author: "Glenn Lum"
date:   2026-02-15 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most teams know they have flaky tests. They'll tell you as much, usually with a shrug. There's a Slack channel with messages like "known flake, re-running." There's a dashboard nobody checks. There might even be a Jira ticket labeled "reduce test flakiness" sitting in a backlog with no sprint assignment. The implicit framing is that flaky tests are a quality-of-life problem — annoying, like a slow coffee machine in the break room. Something to fix when things calm down.

This framing is wrong, and the reason it's wrong is mathematical. Flaky tests don't degrade your test suite linearly. They degrade it combinatorially. A handful of flaky tests in a large suite doesn't produce a "slightly less reliable" CI signal. It produces a signal that is wrong so often that engineers learn to ignore it. And a CI signal that engineers ignore is not a weak safety net — it is no safety net at all, with the added cost of still taking thirty minutes to run.

## The Mechanics of a Flake

A test is flaky when it produces different pass/fail outcomes on the same code. The code didn't change, but the result did. This means the test's outcome is determined by something other than the code under test, and that something is not controlled.

The specific sources of non-determinism fall into a few distinct categories, and understanding them matters because the fix is completely different for each one.

### Shared Mutable State

Test A writes a row to a database. Test B reads from the same table and expects it to be empty. Run them in order A→B and B fails. Run them B→A and both pass. The flake manifests when the test runner parallelizes execution or when the ordering changes between runs, which many modern test frameworks do by default.

This is the most common source of flakiness in integration test suites. It's also the most insidious because it often doesn't appear until the suite reaches a certain size. A suite of fifty integration tests might run reliably for months. Add twenty more and suddenly three of the original fifty start flaking — not because those tests changed, but because the new tests introduced state mutations that leak across test boundaries.

The shared state doesn't have to be a database. It can be a file on disk, an environment variable, a class-level variable in a test helper, a port number, or an entry in a shared cache. Anything mutable and shared across test processes is a candidate.

### Timing and Concurrency

A test starts an async operation and then asserts on the result after a fixed `sleep(500)`. On a developer's laptop with no load, 500 milliseconds is plenty. On a CI runner handling four parallel jobs with constrained CPU, it isn't. The operation hasn't completed yet, the assertion fires, the test fails.

This category also includes race conditions in the code under test that only manifest under specific thread scheduling. The test isn't wrong — it's exposing a real bug — but the bug only appears in one out of every hundred runs, so it gets labeled a "flake" and ignored. This is a particularly damaging failure mode: a test that is *correctly detecting an intermittent bug* gets quarantined as unreliable.

### Environmental Coupling

A test makes an HTTP call to a third-party sandbox API. The sandbox is slow for two minutes on a Tuesday morning. The test times out. It passes on every other run.

Or: a test assumes a specific DNS resolution behavior, or a particular timezone setting on the host, or that `/tmp` has a certain amount of free space. These assumptions hold on most machines most of the time, and then they don't.

Environmental coupling is especially prevalent in end-to-end tests because, by definition, they exercise the full stack including infrastructure. This is one of the real mechanical reasons the test pyramid prescribes so few E2E tests — not just because they're slow, but because every additional layer of real infrastructure is another source of non-determinism.

### Non-Deterministic Inputs

`Date.now()`, `Math.random()`, UUIDs, auto-incrementing IDs, floating-point arithmetic across architectures. A test that generates a timestamp and then asserts on a formatted string might fail at midnight when the date rolls over between generation and assertion. A test that uses random data for a field and then asserts on sort order might fail when two randomly generated values happen to collide.

These are usually the easiest flakes to fix once identified — inject deterministic clocks, seed random generators, use fixed test data — but they're surprisingly common because they often hide behind utility functions or framework defaults that the test author didn't think about.

## The Combinatorics of Flake Rates

Here is where the intuition breaks. A single test with a 1% flake rate feels negligible. That test will pass 99 out of 100 times. If that were the whole story, flaky tests would be a minor irritation.

But test suites don't contain one test. Consider a suite of 2,000 tests where just 50 of them — 2.5% of the suite — each have an independent 1% flake rate. The probability that *at least one* of those 50 tests flakes on any given run is:

```
P(at least one flake) = 1 - (0.99)^50 ≈ 39.5%
```

Four out of every ten CI runs produce a spurious red build. Now make it 200 tests at 1%:

```
P(at least one flake) = 1 - (0.99)^200 ≈ 86.6%
```

Nearly nine out of ten runs fail for reasons unrelated to the code change being tested. The CI pipeline has become a coin flip that's biased toward failure.

Even at a 0.1% flake rate per test — a rate most teams would consider acceptable — a suite of 5,000 tests produces:

```
P(at least one flake) = 1 - (0.999)^5000 ≈ 99.3%
```

Virtually every run will contain at least one false failure. This is not a theoretical concern. Large monorepos at companies with thousands of tests hit this wall routinely. The math is unforgiving: flake rates that look harmless per-test become dominant at suite scale.

## What Happens When the Signal Dies

The organizational damage follows a predictable sequence, and it's worth walking through because each stage enables the next.

**Stage one: re-runs become normal.** A CI run fails. The developer glances at the failure, recognizes (or guesses) it's a known flake, and clicks "retry." The pipeline runs again. This time it passes. The PR merges. This feels like a minor inconvenience — a few minutes lost. But it has introduced something corrosive: the developer has learned that red does not mean broken. They have learned that the correct response to a CI failure is not "investigate" but "retry."

**Stage two: investigation stops.** Once re-running is the default response, developers stop reading failure logs on the first failure. They retry immediately. If the second run passes, they never look at the failure at all. This means that a *real* failure — a genuine bug introduced by the change — that happens to co-occur with a flaky test gets retried instead of investigated. If the real failure is itself intermittent (a race condition, a resource leak under load), the retry might pass, and the bug ships to production.

**Stage three: the skip culture.** Developers begin annotating tests with `@skip`, `xit`, `test.skip`, or the equivalent. The test suite's coverage silently contracts. Nobody tracks the rate of skipped tests. The total test count stays high, which looks healthy on dashboards, but a growing fraction of those tests aren't running. The suite provides less coverage with each passing month while still taking the same amount of time to execute.

**Stage four: the test suite becomes decoration.** At this point, CI is a gate that everyone knows how to get past. Developers write tests because the PR template requires them, not because they expect those tests to catch anything. The test suite still runs. It still costs compute. It still takes time. But it has lost its operational function: it no longer tells you whether the code is safe to deploy. You've replaced a reliable signal with an expensive ritual.

This progression typically takes six to eighteen months. It is rarely a conscious decision. Nobody declares "we no longer trust our tests." It happens through a thousand small rational choices by individual developers responding to unreliable feedback.

## The Tradeoffs of Common Responses

### Automatic Retries

The most common organizational response to flakiness is automatic retries: if a test fails, run it again, and only report it as a real failure if it fails twice (or three times). This works in the narrow sense that it reduces false-positive CI failures. It fails in every other sense. It doubles or triples compute cost. It extends pipeline duration. And critically, it eliminates the pressure to actually fix the flaky test. The flake rate can climb indefinitely because no individual flake ever causes enough pain to prioritize a fix. Retries are an analgesic that masks a progressive disease.

### Quarantine

A more sophisticated approach is quarantining: moving flaky tests into a separate suite that runs but whose results don't gate deployment. This preserves the signal quality of the main suite. The tradeoff is that quarantine lists grow monotonically. Without explicit ownership and a forcing function (a policy like "quarantined tests are deleted after 30 days if not fixed"), the quarantine becomes a graveyard. Those tests represented real assertions about system behavior. Moving them out of the critical path means those behaviors are now unverified in CI. Quarantine is better than retries, but only if the quarantine has a defined exit — either back into the main suite or into deletion.

### Deletion

Deleting a flaky test is often the correct choice, and it's the choice teams are most reluctant to make. The resistance is psychological: someone spent time writing that test, it asserts something real, and deleting it feels like moving backward. But a flaky test is not providing the value of a passing test. It is providing negative value — consuming compute, degrading signal, and occasionally hiding real bugs behind noise. A gap in coverage that you *know about* is more honest and less dangerous than a test that covers something unreliably. You can track missing coverage. You cannot track how many real failures were masked by a flaky test that was retried into green.

## The Mental Model

Think of your test suite as a **signal system**, not as a collection of individual checks. Each test is not independently valuable — its value comes from its contribution to a composite signal that answers one question: is this change safe to deploy? A flaky test degrades that composite signal the way a noisy sensor degrades a control system. The sensor might be "right most of the time," but the controller can't distinguish the noise from real readings, so it either starts ignoring the sensor entirely or it starts making wrong decisions based on bad data. Both outcomes are worse than removing the sensor and acknowledging the gap.

The operational question is never "does this test sometimes catch real bugs?" It is: "does the expected value of this test — accounting for true positives, false positives, investigation time, retry cost, and trust erosion — make the overall suite more or less reliable?" When you frame it this way, the answer for many flaky tests is clearly negative. The Level 3 post will walk through building the infrastructure to measure this — detecting, tracking, and systematically eliminating flakes. But the prerequisite is this shift in framing: flaky tests are not a backlog item. They are an active drain on your deployment confidence, and they compound.

## Key Takeaways

- A test is flaky when its outcome depends on something other than the code under test — shared state, timing, environment, or non-deterministic inputs — and that dependency is not controlled.

- Flake rates that look negligible per-test (0.1–1%) produce near-certain false failures at suite scale due to combinatorial probability; a suite of 2,000 tests with 50 flaky tests at 1% each will produce a spurious red build 40% of the time.

- The organizational damage from flaky tests follows a predictable progression: re-runs become normal, investigation stops, tests get skipped, and eventually the test suite becomes a deployment ritual with no real signal value.

- Automatic retries reduce the visible symptom (red builds) while eliminating the pressure to fix the root cause, allowing flake rates to grow unchecked and compute costs to multiply.

- Quarantining flaky tests preserves main-suite signal quality but requires an enforced exit policy — fix or delete within a defined window — or the quarantine becomes permanent coverage loss with no visibility.

- Deleting a flaky test is often the highest-value action: an acknowledged gap in coverage is safer than an unreliable test that masks real failures behind noise and erodes trust in the suite.

- A test that intermittently detects a real concurrency bug is the most dangerous kind of flake — it gets classified as unreliable and quarantined or retried, which means the real bug ships to production under the label of "known flake."

- The value of an individual test is not whether it can catch a bug in isolation, but whether it improves the composite signal quality of the suite as a whole — flaky tests fail this criterion by definition.

[← Back to Home]({{ "/" | relative_url }})
