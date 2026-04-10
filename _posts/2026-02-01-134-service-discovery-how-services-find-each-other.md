---
layout: post
title: "1.3.4 Service Discovery: How Services Find Each Other"
author: "Glenn Lum"
date:   2026-02-01 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most engineers encounter service discovery as a configuration task. You set an environment variable, point at a hostname, maybe configure a registry URL, and move on. It works until it doesn't — and when it doesn't, it fails in ways that are baffling if you think of discovery as a lookup problem. A service that was working thirty seconds ago starts throwing connection errors. A deployment causes ten seconds of elevated 5xx rates even though every health check passes. A scaling event sends all traffic to a single new instance while the other nine sit idle.

These failures make sense once you understand that service discovery is not a lookup problem. It is a **consistency problem**. In a dynamic environment — containers being scheduled, instances scaling up and down, nodes failing — the set of network locations for any given service is constantly changing. Service discovery is the mechanism by which every client maintains a reasonably accurate view of that changing reality. The mechanics of how that view is constructed, propagated, and invalidated determine how your system behaves during the moments that matter most: deployments, scaling events, and partial failures.

## The Registration Lifecycle

Before any service can be discovered, it must be registered. This sounds simple, but the registration lifecycle has subtleties that directly affect reliability.

In **self-registration**, each service instance registers itself with a registry when it starts up and deregisters when it shuts down. The instance sends a message — typically an HTTP PUT or a gRPC call — containing its address, port, and metadata to a registry like Consul, Eureka, or etcd. The problem is obvious: what if the instance crashes without deregistering? It's now a ghost entry — clients will be routed to an address that accepts no connections.

This is why registries use **heartbeats** or **TTL-based leases**. The instance must periodically renew its registration. If it fails to renew within the TTL window, the registry removes it. Eureka defaults to a 30-second heartbeat interval with a 90-second eviction threshold. That means a crashed instance can remain in the registry for up to 90 seconds. During those 90 seconds, clients are being routed to a dead endpoint.

In **third-party registration**, something external to the service handles registration. Kubernetes does this: the kubelet and the control plane track pod lifecycle events and update the Endpoints (or EndpointSlice) objects accordingly. The service instance itself has no awareness of the registry. This eliminates the deregistration-on-crash problem because the platform detects the failure and removes the entry. But it introduces coupling to the platform — your discovery mechanism is now inseparable from your orchestrator.

The critical thing to internalize is that registration is not instantaneous and deregistration is not instantaneous. There is always a window — sometimes a few hundred milliseconds, sometimes tens of seconds — during which the registry's state does not match reality. Every design decision in service discovery is about managing the size and consequences of that window.

## How DNS-Based Discovery Actually Works

DNS is the most familiar discovery mechanism, and the most deceptive. Engineers reach for it because it feels simple: resolve a hostname, get an IP, connect. But DNS was designed for a world where IP addresses change rarely, and service discovery lives in a world where they change constantly.

When you configure a service in Kubernetes with a `ClusterIP` type, CoreDNS returns a single virtual IP. The kube-proxy (or eBPF, depending on your CNI) handles the actual routing to backend pods. The client resolves the name once, gets one IP, and doesn't need to know about individual instances. This is **server-side discovery masquerading as DNS** — the load balancing happens at the network layer, not in the DNS response.

**Headless services** (`clusterIP: None`) work differently. A DNS query returns multiple A records — one for each backing pod. The client receives the full set of IPs and must choose one. This is where DNS starts to strain.

The fundamental issue is **TTL and caching**. DNS responses include a time-to-live value that tells the resolver how long to cache the result. Set the TTL high and you get stale records when pods are rescheduled. Set it to zero and you're issuing a DNS query on every connection attempt — which works in some environments but breaks in others, because not every layer in the stack honors a zero TTL. The JVM, notoriously, caches DNS resolutions indefinitely by default in some security manager configurations. The `glibc` resolver has its own cache. Client HTTP libraries often resolve once and hold the connection. You can set your TTL to 5 seconds and still have clients hitting a dead IP because the resolution was cached three layers down the stack in something you don't control.

There's a further limitation: DNS A records return IP addresses but not port numbers. **SRV records** solve this by returning a host, port, priority, and weight, which gives the client enough information to do weighted routing. But most HTTP client libraries don't natively consume SRV records. You need either a specialized client or an intermediary that translates SRV responses into routable addresses.

DNS-based discovery works well when the set of instances changes infrequently and when the client infrastructure is well-understood enough that you can control caching behavior end to end. It becomes unreliable in highly dynamic environments where pods churn every few minutes.

## Client-Side Discovery and the Load Balancing Decision

In client-side discovery, the client queries a service registry (or watches it for changes), receives the full set of healthy instances, and decides which one to call. The load balancing logic lives in the client process.

This is what gRPC does natively. A gRPC channel is configured with a **resolver** that returns a list of backend addresses and a **load balancing policy** that selects among them. The default policy is `pick_first` — try the first address that works and stick with it. This is a common source of confusion: engineers deploy five instances of a service, configure gRPC, and find that all traffic goes to a single instance. The fix is switching to `round_robin` or a custom policy, but the failure reveals a deeper truth — client-side discovery means the client must understand load balancing, and the default behavior might not be what you expect.

The mechanics of client-side balancing interact with **connection pooling** in ways that matter. HTTP/1.1 clients typically open multiple short-lived connections, so round-robin across resolved IPs works naturally. HTTP/2 and gRPC multiplex many requests over a single long-lived connection. If the client opens one connection to one backend and multiplexes everything over it, load balancing at the connection level is meaningless — you need request-level balancing, which requires the client to maintain connections to multiple backends and distribute requests across them.

The advantage of client-side discovery is latency and control. There's no intermediary proxy adding a network hop. The client can implement sophisticated balancing strategies — least-outstanding-requests, consistent hashing for cache affinity, locality-aware routing. The cost is that every client language and framework needs a correct implementation. If your system has services in Go, Java, and Python, you need three working discovery and load balancing implementations, and they all need to handle edge cases like instance removal, connection draining, and retry behavior consistently.

## Server-Side Discovery and the Proxy Tradeoff

Server-side discovery puts a load balancer or reverse proxy between the client and the service instances. The client sends traffic to a single stable endpoint — a virtual IP, a DNS name pointing to a load balancer — and the proxy routes to an available backend.

This is the model behind Kubernetes `ClusterIP` services, AWS ALB target groups, and traditional HAProxy/NGINX setups. The client doesn't need to know about the registry. It doesn't need load balancing logic. It just connects to one address.

The proxy now owns two responsibilities: maintaining an up-to-date view of healthy backends, and distributing traffic across them. The propagation delay here is between the registry and the proxy's backend pool. When a new instance registers, there's a window before the proxy adds it. When an instance fails, there's a window before the proxy removes it. These windows are typically shorter than DNS TTLs because the proxy can watch the registry for changes rather than polling, but they still exist.

The operational cost is the proxy itself. It's an additional piece of infrastructure that needs to be deployed, monitored, and scaled. It adds a network hop — typically sub-millisecond within a data center, but it shows up under high throughput. And it's a chokepoint: if the proxy fails, all traffic to that service fails. You mitigate this with redundancy, but now you're running highly available proxies in front of every service, which is essentially what a service mesh does.

## Service Mesh: Discovery as Infrastructure

A service mesh moves discovery, load balancing, retries, and observability out of the application entirely and into a **sidecar proxy** — a process (typically Envoy) that runs alongside every service instance.

The mechanics work like this: outbound traffic from your application is intercepted by the sidecar (using iptables rules or eBPF) before it leaves the pod. The sidecar resolves the destination service name against its local configuration, which was pushed to it by the mesh's **control plane** (Istio's istiod, Linkerd's destination service). The control plane watches the service registry — usually the Kubernetes API — and pushes endpoint updates to all sidecars via a protocol like **xDS** (Envoy's discovery service API). The sidecar then routes the request to a specific backend instance, applying load balancing, retries, and timeouts as configured.

This is client-side discovery, architecturally. The balancing decision happens at the caller's side. But the implementation lives outside the application code, in the sidecar. Your Go service and your Python service get identical discovery and balancing behavior without either of them containing a single line of discovery logic.

The cost is real. Every pod now runs an additional process consuming CPU and memory. The sidecar adds latency to every request — typically 1–3ms per hop, but in a request that traverses six services, that's 12–36ms added. Debugging becomes harder because the network path is no longer direct; you're reasoning about application behavior and proxy behavior simultaneously. And the control plane is a critical dependency — if it can't push updates, sidecars operate on stale configuration.

## Where Discovery Breaks

The most common production failure in service discovery is **stale routing during deployment**. An old instance is being terminated, but the registry hasn't propagated the removal yet, and clients are still sending traffic to it. The connection is refused or times out. This is the staleness window made visible. The mitigation is **connection draining**: the instance stops accepting new connections, finishes in-flight requests, then shuts down, and you configure the deregistration delay to exceed the propagation delay. If the drain period is shorter than the time it takes for all clients to learn the instance is gone, you'll drop requests.

The second failure mode is **discovery during partition**. If the registry is split-brained — part of the cluster thinks an instance is healthy and part doesn't — different clients get different answers. Consul and etcd are CP systems (they sacrifice availability for consistency), so during a partition the registry may refuse to answer queries rather than return stale data. Eureka is AP (it sacrifices consistency for availability), so it will continue serving registrations that may be outdated. Neither is wrong. The choice determines whether your failure mode is "no discovery results" or "possibly stale discovery results," and your system needs to handle whichever one you've chosen.

The third failure mode is **health check mismatch**. The registry says the instance is healthy because it responded to a TCP check. But the instance is in a state where it accepts connections and then hangs — it's wedged on a downstream dependency, or it's in a garbage collection pause, or it's returned to service before its caches are warm. This is the gap between **liveness** (the process is running) and **readiness** (the process can serve traffic correctly). If your health check doesn't test what your clients actually need, your discovery mechanism will cheerfully route traffic to instances that can't handle it.

## The Mental Model

Service discovery is a distributed cache coherence problem. Every consumer of a service holds a local view of where that service's instances are. That view was accurate at some point in the past. The discovery mechanism determines how that view is updated, how much lag exists between reality and each client's understanding of reality, and what happens when the view is wrong.

The three approaches — DNS, client-side registry, service mesh — are not a progression from primitive to advanced. They are different answers to the same question: who is responsible for maintaining that view, and what is the acceptable staleness? DNS pushes it to the network's caching layer with coarse-grained TTLs. Client-side discovery pushes it to the application with fine-grained watches. Service mesh pushes it to infrastructure with proxy-level interception. Each shifts complexity to a different layer. None eliminates it.

The capability you should have after reading this post is the ability to look at any discovery configuration and answer: how long after an instance dies could a client still try to reach it? If you can answer that question for your system, you understand your discovery model. If you can't, you have a latent incident waiting for the right scaling event.

## Key Takeaways

- Service discovery is a consistency problem, not a lookup problem — every mechanism has a staleness window between reality and what clients believe, and the size of that window determines your failure behavior during deployments and scaling events.

- DNS-based discovery is limited by TTL caching at multiple layers (OS, language runtime, client library), and setting a low TTL does not guarantee clients will re-resolve promptly — you must understand every cache in the resolution path.

- Self-registration requires heartbeat-based eviction to handle crashes, which means a dead instance can remain discoverable for the duration of the eviction timeout — typically 30 to 90 seconds in default configurations.

- Client-side discovery gives you control over load balancing strategy but requires a correct implementation in every language and framework your system uses, and interacts with connection pooling in ways that can silently defeat round-robin balancing (especially with HTTP/2 and gRPC).

- Server-side discovery simplifies clients but introduces a proxy as a dependency that must be independently scaled, monitored, and made highly available.

- A service mesh is architecturally client-side discovery relocated to a sidecar proxy — it standardizes behavior across languages but adds per-request latency, per-pod resource overhead, and a critical dependency on the control plane.

- Connection draining during shutdown must exceed the discovery propagation delay; if instances terminate before all clients have learned they're gone, you will drop requests on every deployment.

- Your health check defines what "discoverable" means — if the check only verifies liveness (process is running) rather than readiness (process can serve correctly), discovery will route traffic to instances that accept connections but cannot handle requests.


[← Back to Home]({{ "/" | relative_url }})
