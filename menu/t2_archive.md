---
layout: page
title: "T2 Archive"
permalink: /t2-archive
---

<img src="{{ site.github.url }}/assets/img/tier_2.jpg">

## Tier 2: Core Lifecycle Stages

This is the assembly line. Code enters on one end as text in a developer's editor and exits on the other end as a running, validated, observable process in a production environment. Every station in this assembly line is a potential bottleneck, quality gate, or failure point.

---

## Source Control and Collaboration

### L1

`CONCEPT` [2.1 Source Control and Collaboration]({{ "/21-source-control-and-collaboration" | relative_url }})

### L2

`DEPTH` [2.1.1 The Git Object Model: Commits, Trees, and Refs]({{ "/211-the-git-object-model-commits-trees-and-refs" | relative_url }})

`DEPTH` [2.1.2 Branching Strategies: Trunk-Based Development vs GitFlow]({{ "/212-branching-strategies-trunk-based-development-vs-gitflow" | relative_url }})

`DEPTH` [2.1.3 Merge Strategies: Merge Commits, Rebase, and Squash]({{ "/213-merge-strategies-merge-commits-rebase-and-squash" | relative_url }})

`DEPTH` [2.1.4 The Pull Request as a Quality Gate]({{ "/214-the-pull-request-as-a-quality-gate" | relative_url }})

`DEPTH` [2.1.5 Conflict Resolution: Textual vs Semantic Conflicts]({{ "/215-conflict-resolution-textual-vs-semantic-conflicts" | relative_url }})

`DEPTH` [2.1.6 Monorepo vs Polyrepo: Repository Structure as an Architectural Decision]({{ "/216-monorepo-vs-polyrepo-repository-structure-as-an-architectural-decision" | relative_url }})

---

## Testing Strategy

### L1

`CONCEPT` [2.2 Testing Strategy]({{ "/22-testing-strategy" | relative_url }})

### L2

`DEPTH` [2.2.1 The Testing Pyramid: Cost, Speed, and Coverage as a Design Constraint]({{ "/221-the-testing-pyramid-cost-speed-and-coverage-as-a-design-constraint" | relative_url }})

`DEPTH` [2.2.2 Test Doubles: Mocks, Stubs, Fakes, and Spies]({{ "/222-test-doubles-mocks-stubs-fakes-and-spies" | relative_url }})

`DEPTH` [2.2.3 What Test Coverage Measures and What It Misses]({{ "/223-what-test-coverage-measures-and-what-it-misses" | relative_url }})

`DEPTH` [2.2.4 Contract Testing: How Services Agree on Interfaces]({{ "/224-contract-testing-how-services-agree-on-interfaces" | relative_url }})

`DEPTH` [2.2.5 Testing in Production: Feature Flags, Canary Analysis, and Observability as Tests]({{ "/225-testing-in-production-feature-flags-canary-analysis-and-observability-as-tests" | relative_url }})

`DEPTH` [2.2.6 The Cost of Flaky Tests]({{ "/226-the-cost-of-flaky-tests" | relative_url }})

---

## Continuous Integration (CI)

### L1

`CONCEPT` [2.3 Continuous Integration (CI)]({{ "/23-continuous-integration-ci" | relative_url }})

### L2

`DEPTH` [2.3.1 What CI Actually Means: The Discipline vs the Tool]({{ "/231-what-ci-actually-means-the-discipline-vs-the-tool" | relative_url }})

`DEPTH` [2.3.2 The Anatomy of a CI Pipeline: Triggers, Stages, and Feedback Loops]({{ "/232-the-anatomy-of-a-ci-pipeline-triggers-stages-and-feedback-loops" | relative_url }})

`DEPTH` [2.3.3 Build Reproducibility: Why the Same Source Should Always Produce the Same Artifact]({{ "/233-build-reproducibility-why-the-same-source-should-always-produce-the-same-artifact" | relative_url }})

`DEPTH` [2.3.4 Fast Feedback as a Design Constraint]({{ "/234-fast-feedback-as-a-design-constraint" | relative_url }})

`DEPTH` [2.3.5 The CI/CD Boundary: What CI Produces and Where It Goes]({{ "/235-the-cicd-boundary-what-ci-produces-and-where-it-goes" | relative_url }})

---

## Artifact and Dependency Management

### L1

`CONCEPT` [2.4 Artifact and Dependency Management]({{ "/24-artifact-and-dependency-management" | relative_url }})

### L2

`DEPTH` [2.4.1 What an Artifact Is: The Unit of Deployment]({{ "/241-what-an-artifact-is-the-unit-of-deployment" | relative_url }})

`DEPTH` [2.4.2 Semantic Versioning: What a Version Number Communicates]({{ "/242-semantic-versioning-what-a-version-number-communicates" | relative_url }})

`DEPTH` [2.4.3 Dependency Graphs and Transitive Dependencies]({{ "/243-dependency-graphs-and-transitive-dependencies" | relative_url }})

`DEPTH` [2.4.4 Artifact Registries: Storage, Distribution, and Promotion]({{ "/244-artifact-registries-storage-distribution-and-promotion" | relative_url }})

`DEPTH` [2.4.5 Dependency Pinning vs Version Ranges: The Reproducibility Tradeoff]({{ "/245-dependency-pinning-vs-version-ranges-the-reproducibility-tradeoff" | relative_url }})

`DEPTH` [2.4.6 Supply Chain Security: Why Your Dependencies Are Your Attack Surface]({{ "/246-supply-chain-security-why-your-dependencies-are-your-attack-surface" | relative_url }})

---

## Continuous Delivery and Deployment (CD)

### L1

`CONCEPT` [2.5 Continuous Delivery and Deployment (CD)]({{ "/25-continuous-delivery-and-deployment-cd" | relative_url }})

### L2

`DEPTH` [2.5.1 Delivery vs Deployment: The Most Important Distinction in CD]({{ "/251-delivery-vs-deployment-the-most-important-distinction-in-cd" | relative_url }})

`DEPTH` [2.5.2 Deployment Strategies: Blue/Green, Canary, Rolling, and Recreate]({{ "/252-deployment-strategies-bluegreen-canary-rolling-and-recreate" | relative_url }})

`DEPTH` [2.5.3 The Environment Pipeline: Promoting an Artifact Through Stages]({{ "/253-the-environment-pipeline-promoting-an-artifact-through-stages" | relative_url }})

`DEPTH` [2.5.4 Rollback vs Roll Forward: Two Philosophies for Handling Bad Releases]({{ "/254-rollback-vs-roll-forward-two-philosophies-for-handling-bad-releases" | relative_url }})

`DEPTH` [2.5.5 The Release as a Decoupled Event: Feature Flags and Dark Launches]({{ "/255-the-release-as-a-decoupled-event-feature-flags-and-dark-launches" | relative_url }})

---

## Configuration and Feature Management

### L1

`CONCEPT` [2.6 Configuration and Feature Management]({{ "/26-configuration-and-feature-management" | relative_url }})

### L2

`DEPTH` [2.6.1 The Twelve-Factor Config Principle: Why Configuration Is Not Code]({{ "/261-the-twelve-factor-config-principle-why-configuration-is-not-code" | relative_url }})

`DEPTH` [2.6.2 Configuration Hierarchy and Override Models]({{ "/262-configuration-hierarchy-and-override-models" | relative_url }})

`DEPTH` [2.6.3 Secrets Management: Why Secrets Are Different from Configuration]({{ "/263-secrets-management-why-secrets-are-different-from-configuration" | relative_url }})

`DEPTH` [2.6.4 Feature Flags: The Full Operational Model]({{ "/264-feature-flags-the-full-operational-model" | relative_url }})

`DEPTH` [2.6.5 Configuration Drift: How Reality Diverges from Declared State]({{ "/265-configuration-drift-how-reality-diverges-from-declared-state" | relative_url }})

---

## Infrastructure as Code (IaC)

### L1

`CONCEPT` [2.7 Infrastructure as Code (IaC)]({{ "/27-infrastructure-as-code-iac" | relative_url }})

---

[← Back to Home]({{ "/" | relative_url }})