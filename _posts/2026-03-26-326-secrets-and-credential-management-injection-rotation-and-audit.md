---
layout: post
title: "3.2.6 Secrets and Credential Management: Injection, Rotation, and Audit"
author: "Glenn Lum"
date:   2026-03-26 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most engineers, when they hear "secrets management," think the problem is storage. Don't put credentials in Git. Put them in a vault. Problem solved. But storage is the easiest part of this entire domain. The hard problems are all operational: how does a secret get from the vault into a running process without being exposed in transit or at rest on the host? How do you replace a credential that ten services depend on without causing an outage? How do you know, six months from now, which service accessed which secret and when? The moment you move secrets out of your codebase and into a dedicated system, you have not eliminated complexity — you have traded static complexity (hardcoded credentials scattered across repos) for dynamic complexity (a runtime coordination problem involving encryption, identity, network access, and time). Understanding that coordination problem is what separates teams that use a secrets manager from teams that actually manage secrets.

## What Makes Secrets Different From Configuration

Configuration and secrets look similar — both are key-value pairs your application needs at runtime. But they have fundamentally different security properties that demand different operational models.

A configuration value like `LOG_LEVEL=debug` can be committed to source control, cached on disk, logged freely, and read by anyone with access to the repository. If it leaks, nothing is compromised. A secret like a database password or an API key is the opposite on every axis: it must not be stored in source control, must not be cached in plaintext on disk longer than necessary, must never appear in logs, and must be readable only by the specific identity that needs it. More critically, secrets are **time-sensitive**. A configuration value that was correct six months ago is probably still correct. A credential that was valid six months ago and has never been rotated is a liability, because every day it exists is another day it could have been exfiltrated without your knowledge.

This distinction matters because it means you cannot manage secrets with the same tools and workflows you use for configuration. Environment variables, Kubernetes ConfigMaps, `.env` files checked into repos with `.gitignore` protection — these are all configuration distribution mechanisms being misused as secret distribution mechanisms. They work until they don't, and when they fail, the failure mode is a security incident.

## How Secrets Storage Actually Works

A secrets management system — HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager, Azure Key Vault — is fundamentally an encrypted key-value store with an access control layer and an audit log. But the encryption model matters more than most practitioners realize.

The standard approach is **envelope encryption**. Your secret is encrypted with a data encryption key (DEK). That DEK is itself encrypted with a key encryption key (KEK), sometimes called a master key or root key. The KEK is typically managed by a hardware security module (HSM) or a cloud KMS service. The secrets manager stores the encrypted secret and the encrypted DEK together. When a request comes in, the secrets manager sends the encrypted DEK to the KMS, gets back the plaintext DEK, decrypts the secret, and returns it to the caller. The plaintext DEK lives in memory only for the duration of the operation.

Why this indirection? Because it separates the concern of encrypting data from the concern of protecting the encryption key. You can rotate the KEK without re-encrypting every secret — you just re-encrypt the DEKs. You can have the KMS running in an entirely separate trust domain from the secrets manager. And if someone exfiltrates the secrets manager's storage backend (its database, its disk), they get encrypted blobs and encrypted DEKs, neither of which is useful without the KMS.

In Vault specifically, there is an additional concept: the **unseal process**. Vault's master key is itself split into shares using Shamir's Secret Sharing. No single operator holds the full master key. To start Vault (or restart it after a failure), a threshold number of key holders must each provide their share. This means a compromised Vault server that gets rebooted is inert — it cannot decrypt anything until human operators actively unseal it. This is a powerful security property, but it has a direct operational cost: Vault cannot auto-recover from crashes without automation that itself holds unseal keys, which partially defeats the purpose.

## The Injection Problem

Getting secrets from the store into a running application is where the operational model gets genuinely complicated. There are three common injection mechanisms, and each has meaningful tradeoffs.

**Environment variable injection** is the simplest. An orchestrator (Kubernetes, ECS, a deployment script) fetches the secret at deploy time and passes it as an environment variable to the process. The application reads `os.environ["DB_PASSWORD"]` and connects. This is simple and widely supported, but it has real drawbacks: environment variables are visible in process listings on some operating systems, they are often dumped into crash reports and debug logs, they are inherited by child processes (so if your application spawns a subprocess, that subprocess gets all your secrets too), and they are static for the lifetime of the process — you cannot rotate a secret without restarting the application.

**Mounted file injection** is the model used by Kubernetes Secrets (backed by a secrets manager via something like the Secrets Store CSI Driver) and Vault Agent. The secret is written to a tmpfs volume (an in-memory filesystem that never touches disk) and the application reads it from a file path. This is better than environment variables: the secret doesn't appear in process listings, you can update the file contents without restarting the process (enabling rotation), and the tmpfs mount means the secret is not persisted to disk. The tradeoff is that your application must be written to watch the file for changes or periodically re-read it. A naive application that reads the database password once at startup and caches it in memory gets no benefit from the file being updated.

**Direct API calls** are the most flexible but most coupled approach. The application itself calls the secrets manager API, authenticates, retrieves the secret, and manages its lifecycle. This gives the application full control over when secrets are fetched and refreshed, enables features like dynamic secrets (more on this below), and avoids any intermediary having access to the plaintext. But it means every application must include a secrets manager client library, handle authentication, handle network failures to the secrets manager, and implement retry and caching logic. It pushes complexity into application code that many teams would rather keep in infrastructure.

## The Trust Bootstrap Problem

Every injection mechanism has a chicken-and-egg problem: the application needs a credential to authenticate to the secrets manager in order to get its credentials. This initial authentication — **trust bootstrapping** — is the most subtle part of the entire system.

The cleanest solution uses **platform identity**. In AWS, an EC2 instance or Lambda function has an IAM role. In Kubernetes, a pod has a service account with an associated OIDC token. In GCP, a workload has a service account bound via Workload Identity. The application presents this platform-native identity to the secrets manager, which verifies it against the platform's identity provider. No static credential is involved — the platform itself vouches for the identity of the workload. Vault calls this pattern its **auth methods**: the AWS auth method verifies an EC2 instance's identity document, the Kubernetes auth method verifies a pod's service account token, and so on.

When platform identity is not available — on-premises machines, developer workstations, CI runners — you fall back to some form of pre-placed credential: a token, a TLS certificate, or an AppRole secret ID. This credential must be delivered through a separate secure channel and should be short-lived and narrowly scoped. This is the weakest link in most secrets management architectures, and it is the point most often compromised. If your CI pipeline has a long-lived Vault token stored as a "secret" environment variable in your CI platform, you have moved the hardcoded credential problem from your application repo to your CI system. You have not solved it.

## How Rotation Actually Works

Rotation is conceptually simple — replace old credential with new credential — but operationally it is a coordination problem across multiple systems that do not share a transaction boundary.

The naive approach is: generate new credential, update the secret in the vault, restart all consumers. This creates a window where some consumers have the old credential and the target system (the database, the API) only accepts the new one. The result is an outage.

The correct approach uses a **dual-credential window**. The sequence works like this. First, generate a new credential. Then configure the target system to accept both the old and new credentials simultaneously. Then update the secret in the vault. Then wait for all consumers to pick up the new credential (via file watch, API re-fetch, or restart). Then, and only then, revoke the old credential on the target system. This requires that the target system supports multiple valid credentials at the same time — most databases and API gateways do, but not all systems are designed for this.

**Dynamic secrets** sidestep the coordination problem entirely. Instead of rotating a shared static credential, the secrets manager generates a unique, short-lived credential for each consumer on demand. Vault's database secrets engine, for example, creates a new database user with a unique username and password every time a service requests credentials, with a TTL of, say, one hour. When the TTL expires, Vault revokes the user. No rotation coordination is needed because nothing is shared and nothing is long-lived. The tradeoff is that your database (or whatever the target system is) must support programmatic user creation and revocation, and your secrets manager becomes a hard runtime dependency — if Vault is down, no new credentials can be issued, and as existing ones expire, services lose access.

## Audit: What It Actually Captures

Audit logging in a secrets manager records every interaction with the system: who authenticated, what secret they requested, whether the request was allowed or denied, and when it happened. This sounds straightforward, but the nuance matters.

The audit log tells you that service X read secret Y at time T. It does not tell you what service X did with that secret afterward. If service X reads a database password and then exfiltrates your entire customer table, the secrets manager audit log shows a normal, authorized read. You need the database's own audit log to see the exfiltration. Secrets audit logging is a necessary layer, not a sufficient one. It answers the question "who had access to which credentials and when" — which is critical for incident response (determining blast radius after a compromise) and compliance (proving that access patterns match policy). It does not answer "what was done with those credentials."

A practical implication: your audit log must be immutable and stored outside the secrets manager itself. If an attacker compromises Vault, they should not be able to modify the audit trail. Ship audit logs to a separate, append-only log store with independent access controls.

## Tradeoffs and Failure Modes

**The secrets manager as a single point of failure.** You centralized all your credentials into one system to improve security. Now, if that system is unavailable, every service that needs to authenticate to anything is dead. High availability for your secrets manager is not optional — it is more critical than HA for most of your application services, because a secrets manager outage is a cascading failure across your entire infrastructure. With dynamic secrets, this is even more acute: there is no static fallback credential to ride out the outage with.

**The false comfort of "we use a vault."** Teams adopt a secrets manager, move their secrets into it, and check the box. But the secrets inside are still static, still never rotated, still shared across environments, and the access policies are wide open because "we'll tighten them later." This is arguably worse than the starting position because the team now believes the problem is solved. The secrets manager is infrastructure. The operational discipline — rotation schedules, least-privilege policies, regular access reviews — is the actual security posture.

**Environment variable leakage.** Despite being the most common injection method, environment variables are the leakiest. They appear in `/proc/<pid>/environ` on Linux, in Docker inspect output, in crash dumps, in logging middleware that helpfully dumps the entire environment on error. Every layer of your stack that might capture environment variables for debugging purposes is a potential secret exposure vector. Teams discover this when a secret shows up in their centralized logging system because an error handler serialized the process environment into a log entry.

**Rotation that causes outages.** The most common rotation failure is revoking the old credential before all consumers have picked up the new one. This happens when the dual-credential window is too short, when a consumer is not correctly watching for secret updates, or when someone manually rotates a credential in the vault without coordinating with the target system. The result is an authentication failure that looks exactly like a credential compromise, triggering incident response for what is actually a self-inflicted outage.

**Audit log volume.** In a dynamic secrets model with short TTLs, a fleet of 200 services each renewing credentials every hour generates a massive volume of audit entries. Without structured log management and automated analysis, the audit log becomes write-only data — it exists for compliance but no human ever examines it, which means anomalous access patterns go unnoticed.

## The Mental Model

Secrets management is not a storage problem. It is a runtime coordination problem that spans four concerns: encrypted storage, identity-based access, time-bounded validity, and observable access patterns. The storage part is solved by any competent secrets manager. The hard parts are injection (getting the secret to the right process without exposing it in transit or at rest), rotation (replacing credentials across systems that do not share a transaction boundary), and audit (maintaining a trustworthy record of who accessed what and when).

The conceptual shift is this: a secret is not a value you configure once and forget. It is a lease — something that is granted, scoped to an identity, valid for a duration, and revocable. The closer your operational model gets to treating every credential as a short-lived lease rather than a static configuration value, the smaller your blast radius when something goes wrong. Dynamic secrets are the purest expression of this model, but even with static secrets, the lease metaphor should guide your thinking: who has this credential, how long have they had it, and can I revoke it right now if I need to?

## Key Takeaways

- **Secrets are not configuration.** They require different storage, different distribution mechanisms, different access controls, and different lifecycle management. Using configuration tooling to manage secrets is a category error with security consequences.

- **Envelope encryption separates data protection from key management.** Your secrets are encrypted with a data key, and the data key is encrypted with a master key held in a KMS or HSM. This layering is what makes key rotation and trust boundary separation practical.

- **The trust bootstrap problem is the weakest link in most architectures.** The credential your application uses to authenticate to the secrets manager is itself a secret. Platform identity (IAM roles, Kubernetes service accounts, Workload Identity) is the cleanest solution; anything else shifts the hardcoded credential problem rather than solving it.

- **Environment variables are the most common and most leaky injection method.** They are visible in process listings, inherited by child processes, captured in crash dumps, and often serialized into logs. Mounted tmpfs files or direct API calls are strictly better from a security standpoint.

- **Rotation is a multi-system coordination problem, not a single-system update.** Safe rotation requires a dual-credential window where both old and new credentials are valid simultaneously, followed by a confirmed rollover before the old credential is revoked.

- **Dynamic secrets eliminate the rotation problem by making every credential unique and short-lived.** The tradeoff is a hard runtime dependency on the secrets manager — if it goes down, credential renewal stops and services degrade as leases expire.

- **Audit logs tell you who accessed which secrets and when, not what was done with those secrets.** Secrets audit logging must be paired with target-system audit logging to get a complete picture during incident response.

- **A secrets manager you do not operate with discipline — rotation enforcement, least-privilege policies, access reviews — is security theater with better branding.**

[← Back to Home]({{ "/" | relative_url }})
