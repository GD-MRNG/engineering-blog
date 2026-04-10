---
layout: post
title: "1.2.5 Serverless and the Event-Driven Compute Model"
author: "Glenn Lum"
date:   2026-01-25 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most engineers understand serverless as "you don't manage servers and you pay per invocation." That's accurate in the way that "a database stores data" is accurate — true, but missing everything that would help you make a real decision. The gap that causes problems isn't at the definition level. It's in the execution model. Serverless doesn't just change *where* your code runs; it changes what "running" means. Your code doesn't exist as a process until something triggers it. It materializes, executes, and either freezes or disappears. Understanding the mechanics of that lifecycle — what actually happens between "event fires" and "response returns" — is what separates someone who can architect on serverless from someone who deploys to it and then fights it for the next two years.

## The Invocation Lifecycle

In a containerized or VM-based model, your application boots once and stays resident. It holds open database connections, maintains in-memory caches, and waits for incoming requests on a port. The process is long-lived. In Functions-as-a-Service, there is no long-lived process. The **unit of compute is a single invocation**: one event in, one execution, one result out.

Here's what actually happens when a function is invoked on a platform like AWS Lambda, though the model is substantively similar on Azure Functions, Google Cloud Functions, and Cloudflare Workers.

An event arrives at the platform — an HTTP request through an API gateway, a message landing on a queue, a file uploaded to object storage, a cron-like schedule firing. The platform's control plane receives this event and needs to route it to an **execution environment**: an isolated sandbox (typically a lightweight microVM or a container-like construct) that can run your function's code. The platform checks whether a **warm** execution environment already exists — one that previously ran this function and hasn't been reclaimed yet. If one exists, the event is routed to it. The function handler is invoked directly, and the response is returned. This is the **warm start** path, and it's fast — single-digit milliseconds of platform overhead on top of your code's execution time.

If no warm environment exists, the platform must create one from scratch. This is the **cold start** path, and understanding what happens here is essential.

## What a Cold Start Actually Costs

A cold start isn't one delay. It's a sequence of discrete steps, each with its own cost:

The platform provisions an execution environment — allocating a microVM or container sandbox, assigning CPU and memory according to your function's configuration. It then downloads your **deployment package** (your code plus bundled dependencies) from the platform's internal storage into that environment. Next, it initializes the **language runtime** — starting the Python interpreter, the Node.js V8 engine, the JVM, or the .NET CLR. Finally, it runs your **initialization code**: the module-level imports, the global variable assignments, the SDK client instantiations — everything outside your handler function that executes once when the module loads.

Only after all of that does your handler function execute against the actual event.

The practical latency this adds depends on several factors. Language runtime matters significantly: a Python or Node.js function might add 100–300ms of cold start latency. A Java function on the JVM can add 1–5 seconds, sometimes more, because the JVM's startup cost is fundamentally higher. Deployment package size matters: a 5MB zip downloads and unpacks faster than a 50MB one. **VPC attachment**, if your function needs to reach resources inside a private network, historically added seconds of cold start latency due to elastic network interface creation (AWS has improved this substantially with Hyperplane, but VPC-attached functions still carry some additional cold start penalty).

The critical insight is that the platform *will freeze and eventually reclaim* warm environments after some period of inactivity. This period is not contractually guaranteed — on AWS Lambda, it's typically 5–15 minutes, but it's an implementation detail the platform can change. You cannot rely on a warm environment being available. Your code must be correct regardless of whether it's executing in a cold or warm start. But you can — and in latency-sensitive paths, you must — design to *minimize* cold start impact: keep deployment packages small, avoid heavyweight frameworks, defer expensive initialization where possible, or use **provisioned concurrency** (pre-warmed environments you pay for whether they're invoked or not, which effectively trades the serverless billing model for cold start elimination).

## The Event-Driven Trigger Model

The "event-driven" part of serverless isn't decorative. It defines the programming model. Your function doesn't listen on a port. It doesn't poll. It declares what **event sources** it responds to, and the platform handles the wiring.

These event sources fall into a few categories that behave differently:

**Synchronous invocations** are request-response. An HTTP request arrives through API Gateway, the function executes, and the caller blocks until the response is returned. If the function fails, the caller gets an error. Retries are the caller's responsibility.

**Asynchronous invocations** decouple the caller from the execution. The event is placed onto an internal queue, the caller gets an immediate acknowledgment, and the platform invokes the function independently. If the function fails, the *platform* retries — typically twice — and then routes the event to a **dead-letter queue** if it still fails. This means your function can be invoked multiple times for the same event. If your function is not **idempotent** — if running it twice with the same input produces a different outcome than running it once — you will have data correctness bugs that are intermittent, hard to reproduce, and very expensive to diagnose.

**Stream-based invocations** (Kinesis, DynamoDB Streams, Kafka) are different again. The platform polls the stream on your behalf and invokes your function with batches of records. Failure handling here is particularly sharp-edged: by default, a failed batch *blocks the entire shard*. The platform retries the same batch until it succeeds, your function's retry limit is exhausted, or the records expire — and no subsequent records on that shard are processed until the failure is resolved. A single poison record can halt an entire pipeline.

Understanding which invocation model you're operating under isn't optional. It determines your error handling strategy, your idempotency requirements, and your failure blast radius.

## Concurrency, Scaling, and the Downstream Problem

Serverless functions scale horizontally by creating more execution environments. If ten events arrive simultaneously, the platform spins up ten environments (subject to your account's concurrency limits). If a thousand arrive, it attempts to spin up a thousand. This is the model's greatest strength and one of its most dangerous properties.

Each execution environment handles **one invocation at a time** (this is the default model on most platforms; some newer runtimes allow limited concurrency per instance, but the single-invocation model is the dominant paradigm). There is no request queuing within an instance. There's no connection pooling shared across invocations running in different environments. Each environment is isolated.

This means that if your function connects to a relational database, and your function scales to 500 concurrent invocations, you now have 500 separate database connections. Most relational databases (PostgreSQL, MySQL) are not designed to handle hundreds or thousands of simultaneous connections efficiently. Their connection handling involves per-connection memory overhead, process or thread creation, and context switching costs. The result is that a traffic spike that your serverless functions handle beautifully *crushes your database*. This is not a hypothetical failure mode — it's one of the most common production issues in serverless architectures, and it's why services like **RDS Proxy** and **PgBouncer** exist: to pool connections between the functions and the database.

The broader pattern here is that serverless shifts the scaling bottleneck. Your compute layer scales automatically and nearly instantly. Everything your compute layer talks to — databases, APIs, third-party services, legacy systems — almost certainly does not. If you design your serverless functions without considering the scaling characteristics of their downstream dependencies, you will build a system that auto-scales itself into failure.

Concurrency limits are the platform-side safety valve. AWS Lambda defaults to 1,000 concurrent executions per account per region. When that limit is hit, additional invocations are **throttled** — either rejected (synchronous) or queued for retry (asynchronous). You can set **reserved concurrency** per function to guarantee capacity for critical functions and prevent a noisy-neighbor function from consuming the entire account's limit. But reserved concurrency is a zero-sum game: capacity reserved for one function is unavailable to others.

## Execution Constraints as Architectural Boundaries

Serverless platforms impose hard constraints that aren't just implementation details — they're architectural boundaries you must design around.

**Execution duration** is capped. AWS Lambda allows a maximum of 15 minutes per invocation. Azure Functions' consumption plan has a default of 5 minutes (extendable to 10). If your workload involves processing a 2GB video file, training a model, or running a long-running ETL pipeline, a single function invocation cannot do it. You must decompose the work: fan out across multiple invocations, use step functions or durable workflows to coordinate stages, or accept that this workload doesn't belong in FaaS.

**Memory** is your only direct performance lever. On Lambda, you configure memory from 128MB to 10GB, and CPU is allocated proportionally. You don't choose CPU independently. A function configured with 1,769MB of memory gets one full vCPU. Below that, you get a fraction. This means that a CPU-bound function (image processing, compression, JSON parsing of large payloads) will run faster with more allocated memory even if it doesn't need the memory — because more memory means more CPU. The cost implication is that you're tuning a single dial that affects both performance and price, and the optimal setting is workload-specific. Tools like AWS Lambda Power Tuning exist specifically to find the memory configuration that minimizes cost for a given function's execution profile.

**Statelesness** is absolute. There is no guarantee that two invocations of the same function will hit the same execution environment. Even if they do (warm start reuse), relying on in-environment state — writing a temp file and expecting it to be there on the next invocation — is a correctness bug waiting for a cold start to trigger it. All durable state must live in external services: databases, object storage, caches. This isn't a recommendation — it's a hard constraint of the model.

## Where Serverless Breaks Down

**Observability is harder.** In a long-running service, a request flows through your application in a traceable path. In a serverless architecture, a single user action might trigger an API Gateway invocation, which writes to DynamoDB, which triggers a stream-based Lambda, which publishes to SNS, which triggers another Lambda. Tracing that path requires **distributed tracing** instrumented across every hop, and the ephemeral nature of execution environments makes it harder to correlate logs and metrics. You're not debugging a server — you're debugging a chain of events.

**Cost crossover is real.** Serverless is cheap at low utilization and expensive at sustained high throughput. The per-invocation and per-GB-second pricing means that a function running constantly — handling a steady stream of requests 24/7 — will cost significantly more than the equivalent container running at high utilization on reserved compute. The crossover point varies by workload, but as a rough heuristic: if your function would be running at over 20-30% utilization around the clock, you should run the numbers against a container-based deployment. Serverless excels at spiky, unpredictable, or low-volume workloads where you'd otherwise be paying for idle capacity.

**Vendor lock-in goes deeper than API surfaces.** It's not just that your function code calls `context.succeed()` or uses `event['Records']` in a platform-specific format. It's that your architecture is built on the platform's event routing fabric — the connections between API Gateway and Lambda, between S3 event notifications and Lambda, between Step Functions and Lambda. Porting a serverless architecture to another cloud isn't rewriting function handlers; it's rebuilding the event topology.

## The Mental Model

Think of serverless not as "containers you don't manage" but as a fundamentally different execution model: **event-materialized compute**. Your code does not exist as a running process. It exists as an artifact stored on the platform, and the platform materializes a runtime for it when an event demands execution. Every consequence flows from this single fact. Cold starts exist because materialization takes time. Statelessness is mandatory because the materialized runtime is ephemeral. Scaling is automatic because the platform can materialize as many runtimes as there are events. The billing is per-invocation because compute exists only during invocation.

Once you internalize this model, the architectural decisions become tractable. You can reason about when materialization cost matters (latency-sensitive synchronous paths) and when it doesn't (asynchronous queue processors). You can predict where the model will stress downstream systems (anywhere concurrency is unbounded) and where it will save money (anywhere utilization is low or bursty). You stop treating serverless as a deployment target and start treating it as a compute model with specific physics — and you design around those physics instead of fighting them.

## Key Takeaways

- **A cold start is a sequence of discrete steps** — environment provisioning, code download, runtime initialization, and application initialization — and each step has different levers for optimization.

- **The invocation model (synchronous, asynchronous, stream-based) determines your failure semantics**, including who retries, how many times, and whether a single failure can block an entire pipeline.

- **Every asynchronous or stream-based trigger can deliver events more than once**, making idempotent function design a correctness requirement, not a best practice.

- **Serverless shifts the scaling bottleneck from compute to everything compute touches** — databases, APIs, and third-party services that cannot absorb unbounded concurrency become the failure point.

- **Memory configuration is the single tuning dial for both performance and cost on most FaaS platforms**, because CPU allocation scales with memory, meaning CPU-bound functions benefit from higher memory settings even when they don't need the RAM.

- **Execution duration limits are architectural boundaries**, not inconveniences — workloads that cannot complete within the platform's time limit must be decomposed into coordinated steps or moved to a different compute model.

- **The cost advantage of serverless inverts at sustained high utilization** — run the numbers against container-based alternatives when a function would be continuously active rather than sporadically invoked.

- **Vendor lock-in in serverless is primarily in the event topology**, not the function code — the platform-specific wiring between event sources, functions, and downstream services is the expensive thing to migrate.

[← Back to Home]({{ "/" | relative_url }})
