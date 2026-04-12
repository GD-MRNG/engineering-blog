---
layout: post
title: "2.4.4 Artifact Registries: Storage, Distribution, and Promotion"
author: "Glenn Lum"
date:   2026-02-24 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers treat an artifact registry the way they treat an S3 bucket: you push a thing in, you pull the thing out, and the interesting work happens elsewhere. This mental model is comfortable, and it works right up until the moment it doesn't — when a deployment that passed staging behaves differently in production, when a rollback pulls an artifact that isn't what you expected, or when a registry outage takes down your entire deployment pipeline because nothing was designed to tolerate it. The registry is not passive storage. It is a system with specific semantics — content addressing, mutable references, layered deduplication, distribution protocols — and those semantics directly determine whether your CI/CD pipeline is reliable or merely appears to be.

## What a Registry Actually Stores

A registry stores artifacts, but "artifact" is a more structured concept than "file." The mechanics differ by ecosystem, but the most instructive example is the OCI (Open Container Initiative) model used by container registries, because it makes the internal structure explicit. Other registries — npm, Maven, PyPI — follow similar principles with different implementation details.

In an OCI-compliant registry, what you think of as "an image" is actually three distinct things: **blobs**, **manifests**, and **tags**.

**Blobs** are the actual content — compressed filesystem layers, configuration data. Each blob is stored and addressed by its cryptographic digest, typically a SHA-256 hash. A blob with digest `sha256:a3ed95c...` is always and forever that exact sequence of bytes. If a single bit changes, the digest changes. This is content-addressable storage: the address *is* the content's identity.

A **manifest** is a JSON document that describes an artifact by listing the digests of its constituent blobs and their media types. The manifest itself also has a digest. When you "pull an image," you are first retrieving a manifest, and then using the blob digests within it to pull the actual data. For multi-platform images, there is an additional layer: an **index** (or manifest list) that maps platform/architecture combinations to individual manifests.

A **tag** is a human-readable name — `v1.4.2`, `latest`, `staging-verified` — that points to a manifest digest. This is the critical detail: **tags are mutable pointers to immutable content**. The tag `v1.4.2` points to a specific manifest digest right now, but someone with write access can re-push a different image under the same tag, and the pointer silently changes. The digest never lies. The tag can.

Package registries work on a similar conceptual model even when the implementation differs. An npm package at version `1.2.3` is a tarball with an integrity hash. A Maven artifact has coordinates (group, artifact, version) and a checksum. The fundamental pattern is the same: immutable content identified by hash, with human-friendly identifiers layered on top.

## How a Pull Actually Resolves

When a deployment system or container runtime requests an artifact, the resolution process follows a specific sequence that matters for understanding failure modes.

Given a reference like `registry.example.com/myapp:v1.4.2`, the client first resolves the tag. It issues an HTTP GET to the registry's API — for OCI registries, this is `GET /v2/myapp/manifests/v1.4.2`. The registry returns the manifest along with its content digest in a header. The client now has a complete description of what the artifact contains.

The client then walks the manifest's blob list and issues a GET for each blob it doesn't already have locally. This is where **deduplication** pays off. Container images are built in layers, and many images share base layers. If your local cache (or the registry's storage) already has a blob matching a given digest, it doesn't need to transfer it again. A 500MB image might only require 12MB of actual network transfer if the base layers are already cached.

This is also why **pull-through caches** and **registry mirrors** work. A pull-through cache sits between your infrastructure and an upstream registry. The first pull fetches from upstream and caches locally. Subsequent pulls serve from cache. Because content is addressed by digest, the cache can verify integrity without trusting the upstream — if the bytes don't hash to the expected digest, the pull fails. This is not just a performance optimization. It is a reliability boundary. When Docker Hub has a rate limit incident or a public registry goes down, your pull-through cache is the difference between "deploy continues" and "deploy blocked."

## Public Registries vs. Private Registries

The distinction between public and private registries is not just about access control. It is about trust boundaries, availability guarantees, and operational control.

A **public registry** (Docker Hub, npm's public registry, Maven Central) is a shared commons. You consume artifacts you did not build, from maintainers you do not control, on infrastructure you do not operate. The trust model is: you trust that the registry's integrity mechanisms (signatures, checksums) are intact, and you trust that the package maintainer hasn't published something malicious. The availability model is: you hope it's up when you need it.

A **private registry** (Artifactory, Nexus, AWS ECR, Google Artifact Registry, GitHub Packages) is infrastructure you operate or delegate to a cloud provider. It stores artifacts you built, and optionally proxies or mirrors artifacts from public registries. The trust model shifts — you control who can push, and you can enforce policies like vulnerability scanning gates before an artifact becomes pullable. The availability model becomes your responsibility.

The practical pattern most production systems use is a **private registry that proxies public registries**. This gives you a single pull endpoint for both your own artifacts and third-party dependencies, with the private registry acting as a cache and policy enforcement point. Your build system references `registry.internal/dockerhub-proxy/node:20-alpine` instead of `docker.io/node:20-alpine`. This insulates your builds from upstream availability issues, gives you a point to inject scanning policies, and provides an audit log of every artifact that enters your environment.

This proxy pattern also addresses a subtle operational risk. If your CI pipeline pulls a base image directly from a public registry at build time, and that base image tag gets updated between two builds, your "same source code" can produce different artifacts. Proxying through a private registry with tag immutability enforced — or better, pinning to a digest — closes this gap.

## Promotion: Moving Artifacts, Not Rebuilding Them

Promotion is the concept that most directly separates mature deployment pipelines from fragile ones. The principle is simple: **an artifact that passes testing in one environment should be the exact artifact deployed to the next environment, with zero modification**. In practice, implementing this correctly requires understanding registry mechanics.

The naive approach is to rebuild for each environment. Your CI pipeline builds from source, runs tests, and pushes to a dev registry. When you want to deploy to staging, you run the pipeline again and push to a staging registry. This is wrong for a specific reason: the artifact deployed to staging is not the artifact you tested. It was built from the same source (probably), but the build may not be reproducible — a transitive dependency may have updated, a build tool may have changed, a layer cache may have been invalidated. The only way to guarantee you are deploying what you tested is to deploy the same bytes, verified by digest.

Promotion in registry terms typically follows one of two patterns.

**Tag-based promotion** means adding tags to an existing manifest. After an artifact at `myapp@sha256:abc123` passes staging tests, you add the tag `production-approved` to that same digest. The content doesn't move. The bytes don't change. A new pointer is added to the same immutable content. This is cheap and fast, but it requires your registry to be accessible from all environments, and it means your staging and production infrastructure pull from the same registry instance.

**Copy-based promotion** means copying the artifact from one registry or repository to another. After staging validation, you copy `staging-registry.example.com/myapp@sha256:abc123` to `production-registry.example.com/myapp@sha256:abc123`. The digest is preserved across the copy, so you can verify that the production artifact is byte-identical to what was tested. This is necessary when environments are network-isolated (common in regulated industries or multi-cloud setups), but it introduces a copy step that must be managed, and you need tooling to verify digest consistency post-copy.

In both cases, the digest is the anchor. Configuration that varies between environments — database connection strings, feature flags, resource limits — lives outside the artifact, in environment-specific configuration that is injected at deploy time. The artifact is the constant. The configuration is the variable.

## Where Registries Break and Where Misunderstanding Costs You

**Tag mutability is the most common source of deployment non-determinism.** If your Kubernetes manifests reference `myapp:latest` or even `myapp:v1.4.2` by tag, and someone pushes a new image under that tag, your next pod restart pulls a different artifact than the one currently running. This is not a hypothetical — it is the default behavior. The fix is to reference artifacts by digest in deployment manifests (`myapp@sha256:abc123`), but this trades human readability for determinism. Most teams use a hybrid: tags for human communication, digests in deployment automation.

**Registry availability is a deployment dependency you may not have accounted for.** If your container runtime's image pull policy is `Always` (the Kubernetes default for the `latest` tag), every pod restart requires a registry round-trip. A registry outage means pods cannot start. Even with `IfNotPresent`, a node that hasn't cached the image yet — say, a new node added by autoscaling — will fail to pull. Pre-pulling images to nodes, using DaemonSets for critical images, or running a registry mirror per cluster are mitigations, each with operational cost.

**Garbage collection in content-addressable registries is non-trivial.** Because blobs are shared across manifests (via deduplication), you cannot delete a blob just because one manifest no longer references it — another manifest might. Registry garbage collection is a mark-and-sweep process: mark all blobs referenced by any current manifest, sweep everything else. Running this on a large registry with millions of layers is expensive and typically requires downtime or a read-only window in older implementations. If you never run garbage collection, storage costs grow without bound. If you run it incorrectly, you can delete blobs still in use by manifests, corrupting those artifacts.

**Promotion without environment-specific config separation leads to config leaking into artifacts.** If your artifact contains staging database credentials baked into a config file, promoting that artifact to production doesn't just fail — it connects your production system to your staging database. Promotion only works when the artifact is genuinely environment-agnostic, which requires disciplined separation of build-time concerns (code, dependencies, compiled output) from deploy-time concerns (configuration, secrets, resource allocation).

## The Model to Carry Forward

A registry is a content-addressed store with a mutable naming layer on top. The immutable layer — digests — gives you identity, integrity, and reproducibility. The mutable layer — tags — gives you human usability and workflow semantics like promotion. Every reliability property of your deployment pipeline depends on which layer you anchor to, and when.

The registry sits at the boundary between build and deploy. Everything before it (source, compilation, testing) produces an artifact. Everything after it (deployment, rollback, scaling) consumes one. The integrity of that boundary — the guarantee that what you tested is what you deploy — depends on treating the registry not as a file dump but as a system whose semantics you understand and deliberately use. Promotion is the practice that makes this real: one artifact, built once, verified progressively, deployed everywhere. The digest is the proof.

## Key Takeaways

- **Tags are mutable pointers; digests are immutable identifiers.** Referencing an artifact by tag in deployment automation introduces non-determinism. Reference by digest when determinism matters.

- **A container image is not a single file — it is a manifest pointing to content-addressed blobs.** Understanding this structure is necessary to reason about layer caching, deduplication, and garbage collection.

- **Promotion means moving (or retagging) a tested artifact to the next environment without rebuilding it.** If you rebuild for each environment, you are not deploying what you tested, regardless of whether the source code is the same.

- **Private registries that proxy public registries give you a cache, an availability buffer, and a policy enforcement point** — solving three problems at once.

- **Registry availability is a hidden deployment dependency.** If the registry is unreachable and the image is not locally cached, pods cannot start. Design for this, especially in autoscaling scenarios.

- **Garbage collection in content-addressable registries is a mark-and-sweep operation** that requires care. Mismanaging it either wastes storage or corrupts artifacts.

- **Promotion only works when artifacts are environment-agnostic.** Configuration that varies between environments must be injected at deploy time, not baked in at build time.

- **The digest is the single most reliable identifier in the entire pipeline.** It is the only mechanism that guarantees the bytes you deploy are the bytes you tested. Treat it as the source of truth.

[← Back to Home]({{ "/" | relative_url }})
