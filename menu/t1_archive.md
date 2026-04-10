---
layout: page
title: "T1 Archive"
permalink: /t1-archive
---

<img src="{{ site.github.url }}/assets/img/tier_1.jpg">

## Tier 1: Foundation Knowledge

These are the mental models that must be in place before the rest of the map makes sense. Gaps here manifest not as "I don't know how to configure Kubernetes" but as "I don't understand why anything is failing and I don't know where to start."

---

## Networking Fundamentals

### L1

`CONCEPT` [1.1 Networking Fundamentals]({{ "/11-networking-fundamentals" | relative_url }})

### L2

`DEPTH` [1.1.1 The OSI Model and TCP/IP Stack]({{ "/111-the-osi-model-and-tcpip-stack" | relative_url }})

`DEPTH` [1.1.2 IP Addressing and Subnetting (CIDR)]({{ "/112-ip-addressing-and-subnetting-cidr" | relative_url }})

`DEPTH` [1.1.3 DNS: The Resolution Chain]({{ "/113-dns-the-resolution-chain" | relative_url }})

`DEPTH` [1.1.4 TCP vs UDP: The Reliability Tradeoff]({{ "/114-tcp-vs-udp-the-reliability-tradeoff" | relative_url }})

`DEPTH` [1.1.5 HTTP and TLS: The Application Layer in Detail]({{ "/115-http-and-tls-the-application-layer-in-detail" | relative_url }})

`DEPTH` [1.1.6 Load Balancing: Layer 4 vs Layer 7]({{ "/116-load-balancing-layer-4-vs-layer-7" | relative_url }})

`DEPTH` [1.1.7 Network Security Boundaries: Firewalls, Security Groups, and NACLs]({{ "/117-network-security-boundaries-firewalls-security-groups-and-nacls" | relative_url }})

`DEPTH` [1.1.8 NAT and Private Networking]({{ "/118-nat-and-private-networking" | relative_url }})

---

## Compute Abstractions

### L1

`CONCEPT` [1.2 Compute Abstractions]({{ "/12-compute-abstractions" | relative_url }})

### L2

`DEPTH` [1.2.1 Virtual Machines and the Hypervisor Model]({{ "/121-virtual-machines-and-the-hypervisor-model" | relative_url }})

`DEPTH` [1.2.2 Containers: Namespaces, cgroups, and the Isolation Model]({{ "/122-containers-namespaces-cgroups-and-the-isolation-model" | relative_url }})

`DEPTH` [1.2.3 The Container Image: Layers, Registries, and Immutability]({{ "/123-the-container-image-layers-registries-and-immutability" | relative_url }})

`DEPTH` [1.2.4 Container Orchestration: The Scheduling Problem]({{ "/124-container-orchestration-the-scheduling-problem" | relative_url }})

`DEPTH` [1.2.5 Serverless and the Event-Driven Compute Model]({{ "/125-serverless-and-the-event-driven-compute-model" | relative_url }})

`DEPTH` [1.2.6 Compute Resource Models: CPU, Memory, and I/O as First-Class Constraints]({{ "/126-compute-resource-models-cpu-memory-and-io-as-first-class-constraints" | relative_url }})

---

##  Service Architecture Awareness

### L1

`CONCEPT` [1.3 Service Architecture Awareness]({{ "/13-service-architecture-awareness" | relative_url }})

### L2

`DEPTH` [1.3.1 The Monolith vs Microservices Spectrum]({{ "/131-the-monolith-vs-microservices-spectrum" | relative_url }})

`DEPTH` [1.3.2 Synchronous vs Asynchronous Communication]({{ "/132-synchronous-vs-asynchronous-communication" | relative_url }})

`DEPTH` [1.3.3 The API as a Contract: REST, gRPC, and Event Schemas]({{ "/133-the-api-as-a-contract-rest-grpc-and-event-schemas" | relative_url }})

`DEPTH` [1.3.4 Service Discovery: How Services Find Each Other]({{ "/134-service-discovery-how-services-find-each-other" | relative_url }})

`DEPTH` [1.3.5 Idempotency and Distributed State]({{ "/135-idempotency-and-distributed-state" | relative_url }})

`DEPTH` [1.3.6 The Data Ownership Problem: Why Shared Databases Break Service Independence]({{ "/136-the-data-ownership-problem-why-shared-databases-break-service-independence" | relative_url }})

`DEPTH` [1.3.7 Failure Modes in Distributed Systems: Partial Failure and Cascading Failure]({{ "/137-failure-modes-in-distributed-systems-partial-failure-and-cascading-failure" | relative_url }})

---

[← Back to Home]({{ "/" | relative_url }})