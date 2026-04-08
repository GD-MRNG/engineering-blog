---
layout: post
title: "2.3 Continuous Integration (CI)"
author: "Glenn Lum"
date:   2026-01-06 11:00:00 +0800
categories: journal
tags: [Tier 2, Core Lifecycle Stages, Concept]
---

`[Tier 2, Core Lifecycle Stages, Concept]` 

Continuous Integration is the practice of integrating every developer's work into a shared mainline frequently, ideally multiple times per day, with each integration validated automatically. The word "continuously" is doing real work in that definition. It means that the pain of integration is distributed across many small events rather than accumulated into one catastrophic "merge day."

The most important principle in CI is **build reproducibility** : given the same source code and the same declared inputs, the build should always produce the same output. This sounds obvious but is frequently violated. Builds that depend on "latest" versions of dependencies will produce different outputs as those dependencies are updated by their authors. Builds that fetch resources from the network at build time are non-deterministic because those resources can change or disappear. Builds that embed the current timestamp in the artifact are by definition non-reproducible. Reproducibility matters because it is the foundation of trust: if you can't be certain that the artifact you built today is the same as the one you'll build from the same commit tomorrow, your confidence in any given deployment is undermined.

 **The "build once, deploy many" principle** is the single most important practice for maintaining integrity in your deployment pipeline. Your CI system should produce one artifact from a given commit. That artifact is versioned, stored in a registry, and promoted through environments: it runs in staging, it passes acceptance tests, and then the exact same artifact is deployed to production. If you rebuild the artifact for each environment, you have broken this principle. You are now deploying something that has never been tested, because the production build was built separately from the staging build. Even if the source code is identical, the build environment might differ in subtle ways (different versions of build tools, different transient dependencies). The invariant is: test the thing you ship, and ship the thing you tested.

 **Pipeline performance and structure** matter operationally because pipeline speed determines developer behavior. A CI pipeline that runs in five minutes will be used differently than one that runs in forty-five minutes. Fast feedback loops encourage small, frequent commits. Slow loops encourage batch commits and encourage developers to skip local testing because "CI will catch it anyway." The practical tools for making pipelines fast are caching (storing downloaded dependencies between runs so they don't need to be re-fetched), parallelism (running independent test suites simultaneously rather than sequentially), and pipeline structure (running cheap, fast checks first and expensive, slow checks only when the cheap ones pass, so that failures are surfaced as early as possible).

 **Branch protection and merge gates** are the mechanism by which CI is connected to collaboration. A branch protection rule prevents code from being merged to the main branch unless CI passes. This turns CI from an informational tool into an enforcement mechanism: broken code cannot enter the mainline, which guarantees that the mainline is always in a deployable state. This is a cultural and organizational commitment as much as a technical one, because it requires the team to trust the test suite and to treat a failing CI pipeline as a genuine priority rather than an inconvenience to be bypassed.
