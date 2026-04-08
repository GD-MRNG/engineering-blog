---
layout: page
title: "Archive"
permalink: /archive
---

<img src="{{ site.github.url }}/assets/img/tier_1.jpg">

## Tier 1: Foundation Knowledge

These are the mental models that must be in place before the rest of the map makes sense. Gaps here manifest not as "I don't know how to configure Kubernetes" but as "I don't understand why anything is failing and I don't know where to start."

`CONCEPT` [1.1 Networking Fundamentals]({{ "/11-networking-fundamentals" | relative_url }})

`CONCEPT` [1.2 Compute Abstractions]({{ "/12-compute-abstractions" | relative_url }})

`CONCEPT` [1.3 Service Architecture Awareness]({{ "/13-service-architecture-awareness" | relative_url }})

<img src="{{ site.github.url }}/assets/img/tier_2.jpg">

## Tier 2: Core Lifecycle Stages

This is the assembly line. Code enters on one end as text in a developer's editor and exits on the other end as a running, validated, observable process in a production environment. Every station in this assembly line is a potential bottleneck, quality gate, or failure point.

`CONCEPT` [2.1 Source Control and Collaboration]({{ "/21-source-control-and-collaboration" | relative_url }})

`CONCEPT` [2.2 Testing Strategy]({{ "/22-testing-strategy" | relative_url }})

`CONCEPT` [2.3 Continuous Integration (CI)]({{ "/23-continuous-integration-ci" | relative_url }})

`CONCEPT` [2.4 Artifact and Dependency Management]({{ "/24-artifact-and-dependency-management" | relative_url }})

`CONCEPT` [2.5 Continuous Delivery and Deployment (CD)]({{ "/25-continuous-delivery-and-deployment-cd" | relative_url }})

`CONCEPT` [2.6 Configuration and Feature Management]({{ "/26-configuration-and-feature-management" | relative_url }})

`CONCEPT` [2.7 Infrastructure as Code (IaC)]({{ "/27-infrastructure-as-code-iac" | relative_url }})

<img src="{{ site.github.url }}/assets/img/tier_3.jpg">

## Tier 3: Cross-Cutting Disciplines

These practices don't belong to any single stage of the lifecycle; they apply across all of them, all the time. They are the difference between a system that works and a system that is reliable, secure, and sustainable.

`CONCEPT` [3.1 Observability and Monitoring]({{ "/31-observability-and-monitoring" | relative_url }})

`CONCEPT` [3.2 Security (DevSecOps)]({{ "/32-security-devsecops" | relative_url }})

`CONCEPT` [3.3 Reliability Engineering]({{ "/33-reliability-engineering" | relative_url }})

`CONCEPT` [3.4 Cost Awareness (FinOps Thinking)]({{ "/34-cost-awareness-finops-thinking" | relative_url }})

[← Back to Home]({{ "/" | relative_url }})