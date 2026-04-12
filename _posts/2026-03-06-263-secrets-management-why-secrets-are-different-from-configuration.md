---
layout: post
title: "2.6.3 Secrets Management: Why Secrets Are Different from Configuration"
author: "Glenn Lum"
date:   2026-03-06 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers know that secrets shouldn't be committed to source control. That much is obvious. But the more pervasive problem isn't the engineer who checks a database password into Git — it's the team that externalizes that password into an environment variable and believes the problem is solved. They've followed the twelve-factor principle. The secret isn't in the code. It's injected at runtime. So what's left to worry about?

Nearly everything. The reason secrets management exists as a distinct discipline — not a subcategory of configuration management — is that secrets and configuration differ in ways that matter operationally, and treating them identically produces failures that configuration best practices alone cannot prevent. The difference isn't just that secrets are "more sensitive." It's that secrets have fundamentally different lifecycle requirements, access semantics, and blast radii. Understanding those differences is what separates an externalized config value from an actually managed secret.

## What Makes a Secret a Secret

Configuration tells your application how to behave. A database hostname, a log level, a feature flag value — these shape behavior. A secret grants your application the ability to act. A database password, an API key, a TLS private key — these are proof of identity or authorization. The distinction matters because the consequences of exposure are categorically different.

If someone reads your log level configuration, they know something about your observability setup. If someone reads your database credentials, they can impersonate your application. They can read, modify, or delete data. They can pivot laterally to other systems that trust those credentials. The exposure isn't informational — it's **access escalation**.

This produces three properties that secrets have and configuration values do not:

**Secrets are revocable.** When a secret is exposed, the correct response is to invalidate it and issue a new one. This means the system must support rotation without downtime. A configuration value like a service URL doesn't have this property — if someone learns your staging endpoint, you don't change the endpoint.

**Secrets require audit.** You need to know who accessed a secret, when, and from where. Not because you're paranoid, but because after a breach, the first question is always "what was the blast radius?" Without access logs on secrets, you cannot answer that question.

**Secrets have a trust boundary.** A configuration value can reasonably be shared across all services in an environment. A database credential should not be. The principle of least privilege applies to secrets in a way it doesn't meaningfully apply to most configuration: each workload should have access only to the specific secrets it needs, and nothing else.

## Why Environment Variables and Config Files Fall Short

The Level 1 post describes environment variables as the simplest configuration injection mechanism. For configuration, they work well. For secrets, they introduce specific risks that aren't always visible.

Environment variables are inherited by child processes. If your application spawns a subprocess, a debugging tool, or a crash reporter, that process has access to every environment variable in the parent's environment, including secrets. Environment variables are also commonly dumped in debug output, error reports, and process listings. Running `ps eww` on a Linux system shows the full environment of every running process. If your secret is in `DATABASE_PASSWORD`, it's visible to anyone with process-listing permissions on that host.

Configuration files mounted into a container are marginally better — they don't leak through process inheritance — but they sit on a filesystem. The secret exists as plaintext bytes on disk (or in a tmpfs mount) for the entire lifetime of the process. Anyone with shell access to the container, or the ability to exec into it, can read the file. And the file persists in container images, layer caches, and volume snapshots unless explicitly excluded.

Neither mechanism supports rotation without restarting the process. Neither provides access logging. Neither enforces granular access control — if a pod can read its own environment, it can read all of its environment variables, including secrets it doesn't need.

These aren't theoretical risks. The most common credential exposure path in cloud environments is a secret stored in a plain environment variable that gets logged by an error-tracking service, exposed through a misconfigured debug endpoint, or captured in a container image layer that gets pushed to a shared registry.

## How Secrets Management Systems Actually Work

A secrets management system — Vault, AWS Secrets Manager, Google Secret Manager, Azure Key Vault — is fundamentally a **gated access broker for sensitive material**. The core mechanic has three parts: storage, authentication, and retrieval.

### Storage: Encryption at Rest with Controlled Key Hierarchy

Secrets are stored encrypted. But "encrypted at rest" is doing less work than it sounds like unless you understand the key hierarchy. In a system like HashiCorp Vault, the stored data is encrypted with a data encryption key, which is itself encrypted with a master key, which is itself protected by an **unseal mechanism** — typically Shamir's Secret Sharing (where the master key is split into multiple shares and a threshold of shares must be provided to reconstruct it) or an auto-unseal backed by a cloud KMS.

This matters because it means no single compromised component reveals the secrets. A database dump of Vault's storage backend is useless without the unseal keys. A compromised KMS alone doesn't help without access to the encrypted storage. The security model is layered, not perimeter-based.

AWS Secrets Manager takes a different approach: encryption is handled transparently by AWS KMS, and the key hierarchy is managed entirely by AWS. You choose a KMS key (or use the default), and every secret version is envelope-encrypted under that key. The tradeoff is less operational complexity (no unseal ceremony) in exchange for trusting AWS's key management completely.

### Authentication: Proving You Are Who You Claim to Be

Before a workload can retrieve a secret, it must prove its identity. This is the **bootstrap problem**, and it is the hardest part of secrets management to get right.

Consider the flow: your application starts up and needs to call Vault to get a database password. But how does it authenticate to Vault? If you give it a Vault token via an environment variable, you've moved the problem — now the Vault token is the secret sitting in plaintext. You've added a layer of indirection without adding security.

The real solutions use **platform identity**. In AWS, an EC2 instance or Lambda function authenticates to Secrets Manager using its IAM role, which is assigned by the infrastructure, not by a developer placing a credential. In Kubernetes, a service account token (projected into the pod by the kubelet) can be exchanged for a Vault token using Vault's Kubernetes auth backend. The identity proof comes from the platform itself — the fact that this pod is running in namespace `payments` with service account `payment-processor` is attested by the Kubernetes API server, and Vault trusts that attestation.

This is the key insight: **the first credential is not a secret you manage — it's an identity the platform provides.** The machine's identity bootstraps access to everything else. If your secrets management architecture still has a "first secret" problem — a token or password that has to be manually placed somewhere — you haven't fully solved the bootstrap problem.

### Retrieval: Pull-Based, Sidecar, or Injected

Once authenticated, the workload retrieves secrets. There are three common patterns:

**Direct API call.** The application itself calls the secrets manager API at startup (or on demand), retrieves the secret value, and uses it. This gives the application full control over caching and refresh but couples your application code to a specific secrets provider's SDK.

**Sidecar or init container.** A separate process — running as a Kubernetes init container or a sidecar — handles authentication and retrieval, writing secrets to a shared volume or in-memory filesystem before the main application starts. The application reads a file from a known path and doesn't know or care where the value came from. This decouples the application from the secrets infrastructure entirely.

**Operator-driven injection.** Tools like the Vault Agent Injector or External Secrets Operator watch for annotations on Kubernetes pods and automatically inject secrets as volumes or environment variables. The developer declares what they need; the platform delivers it.

Each pattern moves further from application awareness toward platform responsibility. The tradeoff is control versus coupling: direct API calls give you the most control over refresh and error handling, but they embed the secrets provider into your application. Sidecar injection gives you clean separation, but you lose the ability to react programmatically to a rotation event.

## Dynamic Secrets and the Lease Model

The most powerful concept in mature secrets management is the **dynamic secret**: a credential that doesn't exist until it is requested and that expires automatically after a defined period.

Instead of storing a long-lived database password in Vault and handing it to your application, Vault can be configured to connect to the database, create a new set of credentials with a specific set of permissions, hand those credentials to the requesting application, and revoke them automatically when the **lease** expires (or when the application's Vault token expires).

This changes the threat model fundamentally. There is no long-lived credential to steal. If a dynamic credential is intercepted, it expires on its own. If an application is compromised, revoking its Vault lease immediately invalidates every credential it was issued. Forensic investigation becomes tractable — each credential is unique to a specific workload at a specific time, so access logs on the database directly correlate with Vault's audit log.

The cost is operational complexity. Your secrets manager must have privileged access to every backend it creates dynamic credentials for. Credential creation adds latency to application startup. And your application or its sidecar must handle lease renewal — if a lease expires mid-operation because a renewal failed, your database connections drop.

## The Kubernetes Secrets Problem

Kubernetes Secrets deserve specific attention because they are often misunderstood. A Kubernetes Secret is a native API object that looks like it was designed for secrets management but is actually a configuration distribution mechanism with minimal security properties.

By default, Kubernetes Secrets are stored in etcd **unencrypted** (or rather, base64-encoded, which is encoding, not encryption). They are accessible to anyone with RBAC permissions to read secrets in a namespace. They are transmitted to nodes in plaintext (within the cluster network) and mounted into pods as tmpfs volumes or environment variables.

You can enable encryption at rest for etcd. You can configure a KMS provider so that Kubernetes encrypts secrets before writing them to etcd. You can restrict RBAC carefully. But even with all of these in place, Kubernetes Secrets lack audit logging of access, rotation support, dynamic credential generation, and lease management. They are a delivery mechanism, not a management system.

The common pattern in production is to use Kubernetes Secrets as the *last mile delivery mechanism* — the External Secrets Operator or Vault Agent syncs secrets from a real secrets manager into Kubernetes Secrets, which are then mounted into pods. This gives you the management properties of Vault or AWS Secrets Manager with the deployment simplicity of native Kubernetes volumes.

## Tradeoffs and Failure Modes

### Availability Dependency

Your secrets manager is now on the critical path for every service startup. If Vault is down and a pod restarts, that pod cannot retrieve its secrets and will not come back up. This is a real operational risk. Vault itself must be highly available, backed up, monitored, and treated as tier-zero infrastructure. Teams that adopt Vault without investing in its operational maturity often discover this during an incident, at the worst possible time.

### Secret Sprawl and Access Creep

Without governance, secrets accumulate. Teams create secrets in Vault or AWS Secrets Manager with broad access policies because narrow policies are harder to write. Over time, service accounts accumulate access to secrets they no longer need. The result is a secrets store that technically manages access but doesn't actually enforce least privilege — it's just a centralized place where everything is readable by everything.

### Rotation That Breaks Things

Automated rotation is a security best practice that can cause outages. If you rotate a database credential but a running application is holding a connection pool authenticated with the old credential, new connections will fail. Rotation must be coordinated with how applications consume secrets — either through dual-credential rotation (where both old and new credentials are valid during a rotation window) or through application-level secret refresh (where the application watches for rotation events and re-authenticates). Many teams enable rotation, see it cause an incident, and disable it permanently. The correct response is to fix the consumption pattern, not to stop rotating.

## The Mental Model

Configuration is about behavior. Secrets are about identity and access. This distinction drives every design decision in secrets management.

A secret is not a value to be stored — it's a **lease on access** that must be issued, scoped, audited, rotated, and revoked. When you treat secrets as configuration values that happen to be sensitive, you get encrypted storage at best and no lifecycle management. When you treat them as access leases, you build systems where credentials are short-lived, scoped to the workload that needs them, automatically revoked when that workload terminates, and auditable after the fact.

The hardest part of secrets management is not encryption or storage. It's the bootstrap problem — establishing an initial identity without a "first secret" — and the rotation problem — changing credentials without breaking running workloads. Any system you build will eventually have to solve both. Understanding why they are hard is what lets you evaluate tools and patterns without cargo-culting someone else's architecture.

## Key Takeaways

- Secrets differ from configuration not merely in sensitivity but in lifecycle requirements: they must be revocable, auditable, and scoped to specific workloads, which ordinary configuration mechanisms do not support.

- Environment variables and mounted files can deliver secrets to a process but provide no access control granularity, no audit trail, no rotation support, and are vulnerable to leaking through child processes, debug endpoints, and error reporters.

- The bootstrap problem — how an application authenticates to a secrets manager without itself possessing a pre-placed secret — is solved by leveraging platform identity (IAM roles, Kubernetes service account tokens), not by hiding a token in another layer.

- Dynamic secrets, where credentials are generated on demand and automatically expire, eliminate the category of risk associated with long-lived credential theft and make forensic correlation between access logs tractable.

- Kubernetes Secrets are a delivery mechanism, not a secrets management system; production use should treat them as the last mile, synced from a real secrets manager via an operator or agent.

- Automated secret rotation is only safe when the consumption pattern supports it — either through dual-credential windows or application-level secret refresh — and rotation that isn't coordinated with consumers will cause outages.

- A secrets manager becomes tier-zero infrastructure the moment services depend on it for startup; it requires the same availability investment as your database or service mesh control plane.

- The correct mental model for a secret is not "a sensitive config value" but "a scoped, time-bounded lease on access" — and every architectural decision follows from that reframing.

[← Back to Home]({{ "/" | relative_url }})
