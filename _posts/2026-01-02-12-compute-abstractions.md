---
layout: post
title: "1.2 Compute Abstractions"
author: "Glenn Lum"
date:   2026-01-02 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Concept]
---

"Where does my code actually run?" sounds like a simple question, but the answer defines almost everything about your operational model. The compute abstraction you choose determines how you deploy, how you scale, how you debug, how you handle failure, and how much you pay. Understanding the spectrum of options and their tradeoffs is essential for making any of those downstream decisions coherently.

At one end of the spectrum is **bare metal and virtual machines**. Here you manage everything: the operating system, the runtime, the network configuration, the security patches, the storage volumes. You have maximum control and maximum responsibility. If you need to install a dependency, you install it. If you need to change a firewall rule, you change it directly. The operational burden is high because servers tend to become "snowflakes" over time, each one slightly different from the others because of manual changes made under pressure.

**Containers** are the next abstraction. A container packages your application together with its runtime dependencies (libraries, environment variables, startup scripts) into a single, portable, immutable unit. The critical distinction to internalize is the difference between a **container image** and a **container**. The image is the blueprint, an immutable artifact that describes what should run. The container is a running process started from that image, analogous to the difference between a class definition and an object instance. Containers are isolated from each other (they can't directly interfere with each other's files or processes) and portable (the same image that runs on a developer's laptop runs identically in a staging environment and in production). This portability is what solves the "it works on my machine" problem, because the machine is packaged with the code.

Containers alone, however, don't tell you *which server* to run them on, how to restart them when they fail, how to route traffic to them, or how to scale them up under load. **Container orchestration** handles this. An orchestration platform manages the scheduling (which workload runs on which machine), the scaling (adding or removing container instances based on load), the networking (routing traffic between containers), the health checking (restarting failed containers automatically), and the rollout management (updating containers to new versions without downtime). This is the layer where concepts like "desired state" become practical: you declare "I want three replicas of this service running at all times," and the orchestrator continuously reconciles reality toward that declared state.

At the far end of the spectrum is **serverless or functions-as-a-service**. Here, you provide only the code. The platform manages the runtime, the scaling, the networking, and the infrastructure. You are billed for actual execution time rather than for reserved capacity. This model is extremely powerful for event-driven, sporadic, or bursty workloads, but it introduces different operational challenges: **cold starts** (the latency penalty when a function hasn't run recently and the platform needs to provision it), harder local debugging (you can't easily run the production environment on your laptop), and the risk of **vendor lock-in** (your code is tightly coupled to the platform's APIs and event models).

The practical implication is that your choice of compute abstraction is not a deployment detail; it is an architectural decision that shapes your CI/CD pipeline design, your IaC approach, your observability strategy, your scaling model, and your cost structure. A developer who understands these tradeoffs can make this choice intentionally; one who doesn't inherits the choice made for them and then spends years fighting its consequences.

[← Back to Home]({{ "/" | relative_url }})