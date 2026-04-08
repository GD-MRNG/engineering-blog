---
layout: post
title: "2.6 Configuration and Feature Management"
author: "Glenn Lum"
date:   2026-01-09 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2, Core Lifecycle Stages, Concept]
---

The **twelve-factor app** methodology, a set of principles for building portable, scalable software-as-a-service applications, contains a principle that is operationally critical: the strict separation of configuration from code. Configuration is anything that varies between deployment environments: database connection strings, API keys, service endpoint URLs, resource limits, feature flags. If this information is hardcoded in your application, then changing a database URL requires recompiling and redeploying your code, which is slow, dangerous, and unnecessary. If configuration is externalized, the same immutable artifact can be deployed to development, staging, and production environments with entirely different behaviors simply by changing the configuration injected into it at runtime.

The mechanisms for configuration injection are **environment variables** (the simplest approach, appropriate for small numbers of values), **configuration files** mounted at runtime (appropriate for larger or more structured configuration), and **configuration management services** (centralized systems that distribute configuration to services dynamically and support versioning and rollback of configuration changes independently of code deployments). The key operational property of all these mechanisms is the same: the code doesn't know where it is running, which means the same code runs identically in all environments, eliminating the category of bugs that only appear in one environment because of a hardcoded assumption.

**Feature flags** deserve extended treatment because they fundamentally change the operational model of software delivery. A feature flag is a conditional in your code that activates or deactivates a code path based on a configuration value. In the simplest case, this is a boolean: if the flag is true, the new checkout flow is shown; if false, the old one is shown. More sophisticated feature flag systems support targeting (show the new feature to users in a specific country, or users with a specific account tier, or a random 5% of users), experimentation (A/B testing, where metrics are compared between the flag-on and flag-off groups), and gradual rollout (automatically increasing the percentage of users who see the new feature over time, rolling back automatically if error rates increase).

The operational implications are significant. Flags allow you to merge incomplete work to the main branch without affecting users, which keeps your integration costs low and avoids long-lived feature branches. They allow you to test in production safely, because real production traffic exercises the new code path with real data. They allow you to kill a misbehaving feature without a deployment, which reduces the mean time to recovery for feature-related incidents from "time to deploy a revert" to "time to toggle a flag." The operational risk of flags is that they accumulate over time: flags that were created for a specific release and then never cleaned up become permanent conditionals in your codebase, making the code harder to reason about and test. A flag lifecycle discipline, where every flag has an owner, a purpose, an expected expiry date, and is removed from the code once its purpose is served, is necessary to prevent this accumulation from becoming a maintenance burden.

[← Back to Home]({{ "/" | relative_url }})