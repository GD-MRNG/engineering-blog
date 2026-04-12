---
layout: post
title: "3.2.2 Threat Modeling: Thinking About What Can Go Wrong Before You Build"
author: "Glenn Lum"
date:   2026-03-22 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most engineers encounter threat modeling as a meeting they get pulled into or a document template they're asked to fill out. They list some threats — SQL injection, DDoS, credential theft — assign some severity labels, and move on. The document gets filed. Nothing about the system's design actually changes.

This is not threat modeling. This is security Mad Libs.

Real threat modeling is a structured decomposition of your system that produces specific design decisions. It works not because it makes you think about security in general, but because it forces you to trace how data actually moves through your architecture, identify the exact boundaries where trust assumptions change, and systematically ask what can go wrong at each one. The output is not a list of fears — it is a set of architectural constraints that shape what you build. The Level 1 post covered why shifting security left matters and what kinds of tools operate at different stages. This post is about the mechanics of the thinking process itself: how you decompose a system for security analysis, how STRIDE actually works as a reasoning tool, and how identified threats become design requirements.

## The Foundation: Data Flow Diagrams and Trust Boundaries

Threat modeling does not start with thinking about attackers. It starts with understanding your own system. The primary artifact is a **data flow diagram (DFD)** — a deliberately simplified representation of your system as four types of elements: external entities (things outside your control — users, third-party APIs, external services), processes (your running code — services, functions, workers), data stores (databases, caches, file systems, message queues), and data flows (the arrows connecting them, representing data moving between components).

This is not a UML diagram and it is not an architecture diagram. A DFD is optimized for one purpose: making visible where data goes and what it crosses along the way.

The critical concept that gives a DFD its security value is the **trust boundary**. A trust boundary exists wherever data crosses between components that run at different privilege levels, are controlled by different entities, or operate in different security contexts. Between a user's browser and your API: trust boundary. Between your application code and your database: trust boundary. Between your Kubernetes pod and the host node: trust boundary. Between your internal service and a third-party payment provider's API: trust boundary.

Trust boundaries are where threats concentrate, because they are the points where assumptions change. Data arriving from a user's browser cannot be assumed to be well-formed or honest. Data leaving your network to a third-party API is leaving your confidentiality perimeter. Every trust boundary crossing is a site where the receiving component must decide what it can and cannot assume about what it just received.

### A Concrete Decomposition

Consider a standard e-commerce payment flow. The DFD looks like this, read top to bottom:

The user's browser (external entity) sends a checkout request across a trust boundary to the API Gateway (process). The API Gateway terminates TLS, validates the authentication token, and forwards the authenticated request across an internal trust boundary to the Order Service (process). The Order Service retrieves pricing data from the Product Catalog database (data store) across a trust boundary, constructs a payment request, and sends it across a trust boundary to the Payment Provider's API (external entity). The Payment Provider responds with a transaction result. The Order Service writes the completed order to the Orders Database (data store) across a final trust boundary.

Each arrow that crosses a dashed trust boundary line is a point where you will apply STRIDE. This is not incidental — it is the entire mechanism. Without the DFD, threat identification devolves into brainstorming. With it, you have a structured map that tells you exactly where to focus and ensures you do not skip anything.

## STRIDE as a Reasoning Framework

STRIDE is six categories of threats. Its value is not that it is exhaustive in an absolute sense — it is that it provides systematic coverage across the categories of security properties that matter. Without it, threat identification is biased toward whatever the participants happen to have seen recently or read about last week. STRIDE ensures you ask six distinct questions at every relevant point in the system.

Each STRIDE category maps directly to a security property it threatens and, by extension, to the category of control that mitigates it:

| Category | Threatens | Example Control Category |
|---|---|---|
| **Spoofing** | Authentication | Tokens, mutual TLS, certificates |
| **Tampering** | Integrity | Signatures, checksums, input validation |
| **Repudiation** | Non-repudiation | Audit logs, immutable event streams |
| **Information Disclosure** | Confidentiality | Encryption (transit/rest), access controls |
| **Denial of Service** | Availability | Rate limiting, circuit breakers, quotas |
| **Elevation of Privilege** | Authorization | RBAC, least-privilege, input validation |

This mapping is the engine of the framework. When you identify a threat, the category immediately tells you what kind of mitigation to consider.

### Applying STRIDE to the Payment Flow

Walk the DFD's trust boundaries and apply each category. At the browser-to-API-Gateway boundary: **Spoofing** — can an attacker forge or steal a session token and submit a checkout request as another user? **Tampering** — can the request body be modified in transit (this is largely handled by TLS, but what about after TLS termination — does the API Gateway validate the integrity of the payload before forwarding it)? **Information Disclosure** — do error responses from the gateway leak internal service names, stack traces, or valid user IDs?

At the Order Service–to–Payment Provider boundary: **Spoofing** — how does the Payment Provider verify that requests are genuinely from your system and not from an attacker who has discovered the endpoint? (API keys, mutual TLS, IP allowlisting.) **Tampering** — can an attacker intercept and modify the payment amount between your service and the provider? **Repudiation** — if a payment succeeds but the user claims it didn't, do you have a signed, timestamped record from the provider that proves otherwise? **Information Disclosure** — are raw credit card numbers flowing through your system at all, or are you using tokenization to keep them off your servers entirely?

At the Order Service–to–Database boundary: **Elevation of Privilege** — if the Order Service's database credentials are compromised, can they be used to read or modify data in other databases? Does the service's database user have `DROP TABLE` permissions it never needs? **Tampering** — can a compromised Order Service modify historical order records, or are completed orders written to an append-only store?

Each of these is not a hypothetical worry — it is a specific architectural question that demands a specific design decision. That is the mechanism: STRIDE applied at trust boundaries converts a vague concern about security into a concrete engineering task.

## From Threats to Design Requirements

A real system produces dozens to hundreds of identified threats. You cannot address them all equally, and attempting to do so will either stall the project or produce uniformly shallow mitigations. Prioritization requires assessing two dimensions for each threat: how likely is it to be exploited, and how severe is the impact if it is.

A straightforward approach is a risk matrix — categorize each threat as high, medium, or low along both dimensions. A threat that is high-likelihood and high-impact (credential theft through a spoofed session at your API boundary) demands immediate mitigation. A threat that is low-likelihood and low-impact (denial of service against an internal admin tool used by three people) can be accepted.

For each prioritized threat, you choose one of four responses. **Mitigate** means implementing a control that reduces likelihood or impact — this is the most common response. **Accept** means explicitly deciding not to address a threat because the cost of mitigation exceeds the expected risk — this must be a documented, conscious decision, not a silent omission. **Transfer** means shifting the risk to another party, like using a managed service that assumes responsibility for that security boundary or purchasing insurance. **Eliminate** means removing the component or feature that creates the threat entirely — if you use tokenized payment references and never handle raw card numbers, the entire category of cardholder data exposure disappears from your threat surface.

The critical output is not the threat list itself. It is the resulting design requirements. "The Order Service database user must have only `INSERT` and `SELECT` permissions on the `orders` table." "All service-to-payment-provider communication must use mutual TLS with certificate pinning." "Checkout API responses must not include internal error details; errors must be mapped to generic client-safe codes." These statements are implementable. They go into the design document. They become acceptance criteria. They are the bridge between threat modeling and the code that gets written.

## When and Who

Threat modeling is triggered by architectural decisions, not by schedules. The right moments are: when designing a new service or system, when adding an integration with an external party, when changing how authentication or authorization works, when introducing a new data store for sensitive information, and when significantly changing a deployment topology. You do not threat model every pull request. You threat model the decisions that create or move trust boundaries.

The session requires someone who understands the system's architecture (typically the designing engineer or tech lead), and ideally someone with security expertise who can recognize non-obvious attack patterns. The security person is not there to generate a list of requirements from on high — they are there because recognizing that a particular API design enables parameter tampering that bypasses authorization checks requires specific adversarial knowledge that most application engineers have not built.

## Where Threat Modeling Breaks Down

**The ritual failure mode.** Organizations adopt threat modeling, create templates with pre-populated threat categories, and mandate that every project fill one out. Engineers treat it as a compliance exercise. They write "SQL injection" in the threats column without examining whether their system uses SQL at all. They write "DDoS" without identifying which specific component lacks rate limiting. The output is a document that provides false confidence — it looks like security was considered, but no actual reasoning about the system's specific architecture occurred. If your threat model does not reference specific components and specific data flows in your system, it is not a threat model.

**Scope explosion.** A system of any real complexity can generate a threat surface that is unmanageable in a single analysis. Teams that try to model their entire microservices architecture in one session produce an overwhelming list that never gets prioritized and never results in action. Effective threat modeling is scoped tightly: one flow, one subsystem, one significant change. The payment processing flow is a scope. "Our platform" is not.

**Model decay.** A threat model captures your architecture at a specific point in time. When the architecture changes — a new service is added, a data flow is rerouted, a new external integration is introduced — the threat model becomes stale. Mitigations designed for the original architecture may not cover the current one. A trust boundary that didn't exist when the model was built now exists unexamined. This means threat modeling is not a one-time design phase artifact. It requires revisiting when the architecture it describes changes.

**The expertise ceiling.** STRIDE provides structure, but structure alone does not produce insight. Asking "can an entity gain elevated privileges here?" is useful only if you can recognize the mechanisms by which privilege escalation actually happens — insecure direct object references, JWT algorithm confusion, path traversal, deserialization attacks. Purely engineering-driven threat modeling without adversarial security knowledge catches the obvious architectural issues but misses the subtle implementation-level threats that experienced attackers exploit. This is not a reason to skip threat modeling — catching the obvious architectural issues is enormously valuable. But it is a reason to involve security expertise when it is available and to invest in adversarial thinking skills across the engineering team over time.

**Completeness is not the goal.** No threat model will ever identify every possible threat. Novel techniques, creative adversaries, and implementation bugs that only manifest under specific conditions will always produce surprises. Threat modeling addresses the structural, predictable threats that emerge from your architecture — the ones that are visible in the data flows and trust boundaries. The remaining tail risk is handled by the defense-in-depth mechanisms covered in the Level 1 post: runtime monitoring, anomaly detection, network policies, and incident response.

## The Model to Carry Forward

Threat modeling is architecture review through an adversarial lens, made systematic by two structural tools: the DFD tells you where to look, and STRIDE tells you what to ask. The output is not awareness — it is design requirements that exist at specific points in your system for specific, articulable reasons.

The conceptual shift that matters: security controls are not features you bolt onto a system after designing it. They are constraints that emerge from the architecture itself, discoverable through structured analysis. Mutual TLS between services, input validation at API boundaries, rate limiting at entry points, audit logging for sensitive operations — these are not items from a generic security checklist. They are responses to specific threats at specific trust boundaries in your specific system. When you understand why a control needs to exist at a particular point, you implement it correctly. When you are just following a checklist, you implement it superficially and miss the cases the checklist didn't enumerate.

This is what makes building with confidence possible. When you sit down to implement security controls, you are not guessing at what matters — you are executing design decisions that trace back to a structured analysis of how your system actually works.

## Key Takeaways

- Threat modeling is not brainstorming about what might go wrong — it is a structured decomposition of your system's data flows and trust boundaries, with systematic threat enumeration at each crossing point.

- Trust boundaries — where data moves between components at different privilege levels or controlled by different entities — are where threats concentrate and where your analysis should focus.

- STRIDE provides six categories of threats (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege), each mapping to a specific security property and a specific category of mitigation, which is what makes it a reasoning tool rather than just a mnemonic.

- The output of a threat model is not a document or a risk register — it is a set of concrete, implementable design requirements tied to specific components and data flows in your system.

- Every identified threat gets one of four responses: mitigate, accept, transfer, or eliminate — and "accept" must be an explicit, documented decision, not a silent omission.

- Threat modeling should be scoped to a specific flow, subsystem, or architectural change — attempting to model an entire system at once produces analysis that is too broad to act on.

- Threat models decay when the architecture they describe changes; they must be revisited when new services, data flows, or trust boundaries are introduced.

- STRIDE provides structure but not adversarial insight — involving someone with security expertise significantly improves the quality of identified threats beyond what application engineers will find on their own.

[← Back to Home]({{ "/" | relative_url }})
