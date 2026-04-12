---
layout: post
title: "2.3.5 The CI/CD Boundary: What CI Produces and Where It Goes"
author: "Glenn Lum"
date:   2026-02-20 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most teams have a CI/CD pipeline. Few can point to the exact place where CI ends and CD begins. Ask where the boundary is and you'll get vague gestures toward "after the tests pass" or "when it deploys to staging." This ambiguity is not just semantic — it is architectural. The slash in "CI/CD" has collapsed two fundamentally different operations into what feels like a single flow, and that conflation is the root cause of a specific class of operational problems: rollbacks that don't work, environment configurations that drift silently, and deployments where no one can say with certainty what artifact is running or where it came from.

The Level 1 post established the principle: build once, deploy many. This post is about the machinery that makes that principle hold — what CI actually produces, where that output goes, how it gets from "verified" to "deployed," and what breaks when the boundary between those two phases is missing or misdrawn.

## What CI Actually Produces

CI's job terminates in two outputs: a **verdict** and an **artifact**.

The verdict is binary: this commit either integrates cleanly with the mainline or it does not. The test suite passes, the linter passes, the build compiles. The verdict gates whether the commit is eligible for merge. This is the part most engineers are familiar with — the green check or the red X.

The artifact is the less obvious but more important output. When CI succeeds, it should produce an **immutable, versioned object** — a Docker image, a JAR file, a compiled binary, a tarball — that is stored somewhere durable and addressable. This artifact is the thing that will eventually be deployed. Not the source code. Not a future rebuild from the same commit. This specific artifact.

The artifact must carry enough metadata to be traceable back to its origin. At minimum, that means: the commit SHA it was built from, the build ID or pipeline run that produced it, and the digest or checksum of the artifact itself. Many teams also attach the test results, the dependency manifest, and the signature of the build system. This metadata is not decorative — it is the chain of evidence that connects a running process in production back to a specific state of the source code and a specific set of verified properties.

Here's a concrete example. A CI pipeline for a Go service runs on commit `a1b2c3d`. It compiles the binary, runs unit and integration tests, builds a Docker image, and pushes it to a container registry tagged as `myservice:a1b2c3d` with a SHA256 digest of `sha256:9f3e...`. That digest is the artifact's true identity. The tag is a convenience label. From this moment forward, every environment that runs this service should run exactly `sha256:9f3e...`. Not `myservice:latest`. Not a rebuild. That specific image.

## The Artifact Registry as the Boundary

The boundary between CI and CD is not a stage in a YAML file. It is a **storage layer** — the artifact registry.

CI's responsibility ends when the artifact is written to the registry with its metadata. CD's responsibility begins when it reads from the registry to decide what to deploy and where. The registry is the handoff point. It is also the source of truth about what artifacts exist, what their provenance is, and which ones have been promoted to which environments.

This is why the registry is architecturally critical, not just operationally convenient. It decouples the build process from the deployment process in time, in tooling, and in authorization. CI can be driven by GitHub Actions while CD is driven by Argo CD. CI can run on a developer's merge event while CD runs on an operator's approval. The registry is what makes this separation possible without losing traceability.

When this boundary does not exist — when the pipeline builds and deploys in a single uninterrupted flow — CI and CD become temporally and operationally coupled. You cannot deploy without building. You cannot redeploy a previous version without re-running a previous build. You lose the ability to answer the question "what exact thing is running in production right now?" without reverse-engineering it from pipeline logs.

## The Difference Between "Passed" and "Deployable"

CI passing means one thing: the artifact meets the integration criteria defined by the test suite and build checks at the time of merge. It does not mean the artifact is ready for production. These are different assertions with different evidence.

An artifact that passes CI has been verified against unit tests, maybe integration tests, maybe a linter and a static analysis check. An artifact that is **deployable** has additionally survived a promotion process: it has been deployed to a staging or pre-production environment, it has passed acceptance tests or smoke tests that run against a realistic configuration, and it may have been reviewed by a human or approved by a policy gate.

The promotion process is a sequence of assertions, each one narrowing the gap between "this code compiles and passes isolated tests" and "this code behaves correctly in an environment that resembles production." Each assertion is applied to the **same artifact**. The artifact does not change. What changes is the set of properties that have been verified about it.

Concretely, promotion often looks like this: CI produces `myservice:a1b2c3d` and writes it to the registry. A CD process picks it up and deploys it to a `dev` environment. Automated smoke tests run. If they pass, the artifact is marked as eligible for `staging`. A CD process deploys the same image to `staging`. A more comprehensive acceptance suite runs. If it passes, the artifact is marked as eligible for `production`. An operator or automated policy approves the promotion. CD deploys the same image to `production`.

At no point is the artifact rebuilt. At no point is the source code checked out again. The image digest `sha256:9f3e...` is the same in every environment. What differs is the **configuration** applied to it.

## Configuration as a Separate Channel

This is the piece most teams get wrong at the boundary: the artifact is immutable, but its behavior must vary across environments. Different database connection strings, different feature flags, different resource limits, different TLS certificates. How do you reconcile immutability with environment-specific behavior?

The answer is that **configuration is not part of the artifact**. Configuration is injected at deployment time, externally, through environment variables, mounted config files, secret managers, or a configuration service. The artifact contains the code and its dependencies. The configuration tells that code how to behave in a specific context.

This separation is what makes "build once, deploy many" mechanically possible. If database credentials were baked into the Docker image at build time, you would need a different image for every environment, which means you would need a different build, which means you are no longer deploying what you tested. The environment-specific configuration must travel through a different channel than the artifact itself.

In practice, this means your CD system needs to manage two things in concert: which artifact version to deploy, and which configuration to apply. These are often stored in different places — the artifact in a container registry, the configuration in a Git repository (in the GitOps model), a secrets manager, or a configuration management database. The CD system's job is to bind the right artifact to the right config for the right environment and apply the result.

```yaml
# GitOps-style environment config — artifact version pinned, config separate
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myservice
spec:
  template:
    spec:
      containers:
        - name: myservice
          image: registry.example.com/myservice@sha256:9f3e...
          envFrom:
            - configMapRef:
                name: myservice-staging-config
            - secretRef:
                name: myservice-staging-secrets
```

The image reference is a digest — immutable. The config and secrets are environment-specific. This is the separation in action.

## Tradeoffs and Failure Modes

### The Coupled Pipeline

The most common failure mode is a pipeline that builds and deploys in one continuous job. It usually starts innocently: the team has a single CI workflow file that compiles, tests, builds a Docker image, and then `kubectl apply`s it to a cluster. It works fine on day one.

The problems emerge over time. You cannot roll back to a previous artifact without re-running a previous pipeline. If the build tooling has changed, or a transient dependency has shifted, the "rollback" produces a different artifact than the original. You cannot deploy to a new environment without wiring it into the CI configuration, which means your deployment topology is coupled to your build system. And when the deployment fails, the pipeline failure is ambiguous — did the code fail to build, or did the cluster fail to accept the deployment? These are different categories of failure with different remediation paths, and the coupled pipeline obscures which one you're dealing with.

### The Configuration Leak

The second failure mode is configuration that bleeds into the artifact. This shows up as build-time environment variables that change per environment, config files that are copied into the Docker image during build, or feature flags that are compiled into the binary. The symptom is usually that staging works but production doesn't, even though "it's the same code." It is the same code — but it's not the same artifact, because the build baked in staging-specific configuration.

A subtler version of this leak occurs with dependency resolution at build time. If your `Dockerfile` runs `npm install` without a lockfile, or resolves `latest` tags for base images, the artifact produced today is not the artifact produced tomorrow, even from the same commit. The build process itself has become a source of configuration drift.

### The "Deploy on Green" Trap

Some teams set up their pipeline so that a green CI run on the main branch automatically triggers a production deployment. This conflates the verdict ("this code integrates correctly") with the promotion decision ("this code should serve production traffic"). It eliminates the space where acceptance testing, canary analysis, and human judgment operate.

Deploy-on-green works for small teams with high test confidence and low blast radius. It breaks when the test suite has gaps (all suites do), when production has failure modes that staging cannot reproduce, or when you need to coordinate a deployment with an external dependency like a database migration or a partner API change. The problem isn't automation — it's the elimination of the promotion boundary as a distinct, governable decision point.

## The Mental Model

CI is a factory. Its input is source code. Its outputs are a verdict and an artifact. Once the artifact leaves the factory, CI's job is done. CD is a logistics operation. Its job is to take an artifact that has already been built and move it through a series of environments, applying environment-specific configuration at each stop and verifying that the artifact behaves correctly in each context.

The artifact registry sits between them. It is the loading dock — the place where CI drops off what it produced and CD picks up what it needs. The registry is the single source of truth about what has been built, what has been tested, and what is eligible for deployment to which environment.

If you can draw a clean line in your system at the registry — CI writes to it, CD reads from it, nothing crosses that line in both directions — you have a pipeline that supports independent rollbacks, reproducible deployments, and clear operational boundaries. If you cannot draw that line, every deployment carries implicit uncertainty about what was actually built, what was actually tested, and whether the thing running in production is the thing you think it is.

## Key Takeaways

- **CI produces two things: a verdict (pass/fail) and an artifact (the immutable, versioned object that will be deployed).** The artifact is the more important output.

- **The boundary between CI and CD is the artifact registry.** CI writes to it; CD reads from it. If your pipeline does not have this boundary, your build process and deployment process are coupled in ways that will eventually cause operational pain.

- **"CI passed" and "this artifact is deployable" are different assertions.** Promotion is the process of applying progressively more rigorous verification to the same artifact across environments, not rebuilding the artifact for each one.

- **Configuration must travel through a separate channel from the artifact.** If environment-specific values are baked into the build, you do not have an immutable artifact — you have a different artifact for every environment, and you are deploying untested builds.

- **A pipeline that builds and deploys in one continuous job cannot roll back cleanly**, because rollback requires deploying a previous artifact, not re-running a previous build.

- **Artifact identity is a digest, not a tag.** Tags like `latest` or `v1.2.3` are mutable labels. The SHA256 digest is the only reliable way to guarantee that the artifact running in production is the one that was tested.

- **Deploy-on-green eliminates the promotion boundary.** This is a deliberate tradeoff, not a best practice. It works when blast radius is small and test confidence is high. It fails when either condition is not met.

- **If you cannot answer "what exact artifact is running in production right now?" from the registry alone, your CI/CD boundary is missing or broken.**

[← Back to Home]({{ "/" | relative_url }})
