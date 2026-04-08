---
layout: post
title: "1.1 Networking Fundamentals"
author: "Glenn Lum"
date:   2026-01-01 11:00:00 +0800
categories: journal
tags: [Tier 1,Foundation Knowledge,Concept]
---

`[Tier 1, Foundation Knowledge, Concept]`

Networking is the most common blind spot for developers moving into operational work, and it is the most consequential one. When a developer thinks about their code, they tend to think in terms of function calls, objects, and data structures. When a request fails in production, however, the failure is almost never inside the code itself; it is almost always in the path the request takes to reach the code, or the path the response takes to return from it.

You need to develop a mental model of the **request path**: the sequence of hops a user's request makes from their browser or client all the way to your application and back. That path typically looks something like this: the user's device sends a request to a **DNS resolver**, which translates a human-readable domain name into an IP address. That IP address points to a **CDN or edge node**, which may serve a cached response immediately. If not cached, the request flows through to a **load balancer**, which distributes incoming traffic across multiple instances of your service and provides health checking (removing unhealthy instances from rotation). From the load balancer, the request reaches a **reverse proxy**, which may handle TLS termination (decrypting the encrypted HTTPS traffic), route requests based on URL patterns, and forward them to the appropriate backend service. From there, the request reaches your application, which may itself make calls to a **database**, a **cache**, or another **internal service**.

Every link in this chain is a potential failure point. "The service is down" is almost never the full picture. The service may be perfectly healthy but unreachable because a firewall rule is blocking the port. The service may be receiving the request but failing because it cannot reach its database through the internal network. The service may be slow because the DNS resolution is taking too long or because TLS renegotiation is happening on every request.

The concepts you need to understand concretely are as follows. **DNS** is the system that maps domain names to IP addresses; you need to understand TTLs (how long DNS records are cached) because they affect how quickly changes propagate. **Load balancers** operate at different layers: a layer 4 load balancer routes based on IP and TCP, while a layer 7 load balancer can route based on HTTP headers, paths, or cookies, which is more powerful but more complex. **TLS** is the encryption protocol used for HTTPS; you need to understand certificate management, expiry, and renewal because an expired certificate will take down your service as completely as any code bug. **Network segmentation** is the practice of placing services in different network zones based on their sensitivity, so that a public-facing web server cannot directly connect to a production database without passing through a controlled network boundary. **Firewalls and security groups** are the rules that enforce what traffic is permitted to flow between network zones; misconfiguring them is one of the most common causes of "the service can't reach the database" failures.

The practical skill this builds is the ability to trace a failing request through the network topology and identify at which layer the failure is occurring, long before you look at application code.