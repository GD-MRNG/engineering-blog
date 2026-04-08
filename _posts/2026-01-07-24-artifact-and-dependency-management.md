---
layout: post
title: "2.4 Artifact and Dependency Management"
author: "Glenn Lum"
date:   2026-01-07 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2, Core Lifecycle Stages, Concept]
---

`[Tier 2, Core Lifecycle Stages, Concept]`

Once CI produces a verified artifact, that artifact needs a home. An **artifact registry** (also called a container registry or package registry depending on the artifact type) is the storage system for your built, versioned artifacts. The registry provides versioning (so you can identify exactly which version of the artifact is running where), promotion tracking (tagging an artifact as "staging-verified" before it is allowed into production), retention policies (cleaning up old artifacts to manage storage costs), and access control (preventing unauthorized parties from pulling or pushing artifacts).

**Semantic versioning** is the convention by which artifacts are numbered in a way that communicates the nature of the change. A version number of the form `MAJOR.MINOR.PATCH` communicates whether a change is a breaking change (major), a backward-compatible addition (minor), or a backward-compatible fix (patch). Understanding semantic versioning is important for dependency management because it tells you how risky it is to update a dependency. Upgrading from `2.3.1` to `2.3.2` should be safe. Upgrading from `2.3.1` to `3.0.0` may require significant code changes on your part.

**Dependency pinning and lock files** are the practices that make your dependency tree explicit and reproducible. When you declare a dependency as `"requests": "^2.28.0"`, you are saying "any version from 2.28.0 up to but not including 3.0.0 is acceptable." This means your build might use `2.28.0` today and `2.31.1` tomorrow if the library author releases an update, and those two versions may behave differently. A lock file (like `package-lock.json` in Node or `Pipfile.lock` in Python) records the exact version of every dependency (including transitive dependencies, the dependencies of your dependencies) that was used in a specific build. When a lock file is committed to version control, your build tool will always use exactly those versions, making the build reproducible across machines and over time.

**Supply chain security** has moved from an academic concern to a practical operational requirement. The 2020s saw a series of high-profile supply chain attacks in which malicious code was introduced into widely-used open-source libraries and executed in the applications of everyone who depended on them. Your application's attack surface is not limited to the code you write; it includes every library you import, and the libraries those libraries import. The mitigations for this include vulnerability scanning (automated tools that compare your dependency versions against databases of known vulnerabilities), integrity verification (checking that the dependency you download matches a known cryptographic hash), and artifact provenance (establishing a verifiable chain of custody from source code to deployed artifact). These practices belong in your CI pipeline so that every build is automatically checked against known vulnerabilities, and every dependency is verified against its expected signature.

[← Back to Home]({{ "/" | relative_url }})