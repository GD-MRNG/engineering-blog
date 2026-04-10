---
layout: post
title: "1.1.8 NAT and Private Networking"
author: "Glenn Lum"
date:   2026-01-22 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most engineers working in cloud infrastructure know that workloads in private subnets need a NAT gateway to reach the internet. They've configured one, or seen one in a Terraform module, or been told it's required. But when connections from a private subnet start failing intermittently — when a batch job can't reach an external API, when Lambda functions in a VPC time out on outbound calls, when a fleet of containers behind a single NAT gateway starts dropping connections under load — the debugging requires understanding what NAT is actually doing to every packet that leaves your network. That understanding is what most engineers are missing.

The Level 1 post in this series described network segmentation: placing services in different network zones based on sensitivity. NAT is the mechanism that makes those private zones viable for workloads that still need to talk to the outside world. It's not a firewall. It's not a proxy. It's a packet-rewriting engine with a state table, and the constraints of that state table explain almost every surprising NAT-related failure in production.

## Why Private Addresses Can't Be Routed

RFC 1918 defines three address ranges reserved for private use: `10.0.0.0/8`, `172.16.0.0/12`, and `192.168.0.0/16`. "Reserved for private use" means something specific and mechanical: internet backbone routers are configured to drop packets with these source addresses. If a packet with source IP `10.0.4.17` somehow reached a public router, that router would have no route entry for it and would discard it. Even if it did forward it, the destination server would have no path to send a response back — there is no globally unique route to `10.0.4.17` because thousands of organizations all use that same address internally.

This is by design. Private address space exists because IPv4 only provides roughly 4.3 billion addresses. Without address reuse, the internet would have exhausted its address pool decades ago. Private ranges let every organization use the same addresses internally, as long as those addresses never appear on the public internet as-is.

The problem this creates: your workloads live in private address space for good security reasons, but they need to reach public endpoints — package registries, external APIs, SaaS services, certificate authorities for OCSP checks. Something has to rewrite those packets so that the source address is publicly routable. That something is NAT.

## What NAT Actually Does to a Packet

**Network Address Translation** operates on packet headers. When an instance at private IP `10.0.4.17` opens a TCP connection to a public server at `203.0.113.50:443`, the instance constructs a packet with source IP `10.0.4.17`, source port `49152` (an ephemeral port chosen by the OS), destination IP `203.0.113.50`, and destination port `443`.

This packet reaches the NAT gateway because the private subnet's route table has a default route — `0.0.0.0/0` — pointing to the NAT gateway. The NAT gateway rewrites the source fields: source IP becomes `52.14.88.3` (the NAT gateway's public IP, or **Elastic IP** in AWS terms), and source port becomes `24601` (a port chosen by the NAT gateway from its own ephemeral range). The destination fields are left untouched.

The NAT gateway then records a mapping in its **connection tracking table**:

```
Internal:  10.0.4.17:49152  ↔  NAT: 52.14.88.3:24601  →  Dest: 203.0.113.50:443
```

When the response packet comes back from `203.0.113.50:443` addressed to `52.14.88.3:24601`, the NAT gateway looks up port `24601` in its table, finds the mapping, rewrites the destination back to `10.0.4.17:49152`, and forwards the packet into the private subnet.

This is **Source NAT (SNAT)** — the source address is being translated. The external server never sees `10.0.4.17`. It sees `52.14.88.3`. It has no awareness that a translation occurred.

### The State Table Is the Whole Game

The critical insight is that NAT is **stateful**. The NAT gateway doesn't rewrite addresses according to a static rule. It maintains a per-connection entry in a state table, and that entry is what allows return traffic to be mapped back correctly. Without the entry, a packet arriving at `52.14.88.3:24601` is meaningless — the NAT gateway doesn't know where to send it.

This statefulness creates the fundamental asymmetry between outbound and inbound traffic. An outbound connection creates a state table entry as it passes through. Return traffic for that connection is permitted because the entry exists. But unsolicited inbound traffic — a packet arriving at the NAT gateway's public IP without a corresponding outbound connection — has no state table entry. There's no mapping. The packet is dropped.

This is not a firewall rule. It's a structural consequence of how translation works. The NAT gateway literally does not know which internal IP to forward an unsolicited packet to. This is why services in private subnets can initiate outbound connections but cannot receive inbound ones — and why inbound traffic requires a different mechanism entirely: a load balancer, an internet gateway with a public IP directly associated to the instance, or a reverse proxy in a public subnet.

### How Port Allocation Works

A single NAT gateway with one public IP has roughly 65,535 TCP ports available. Subtract well-known ports and reserved ranges, and you get approximately 64,000 usable ports. Each concurrent connection to a unique destination requires one port.

But there's an important subtlety. Most NAT implementations track connections by the full five-tuple: `(protocol, source IP, source port, destination IP, destination port)`. This means the same NAT-side port can be reused for connections to *different* destinations. A connection through NAT port `24601` to `203.0.113.50:443` and another through port `24601` to `198.51.100.10:443` are distinct table entries. The practical port limit is **per destination**, not global.

This distinction matters enormously. If your workloads connect to many different external services, you'll rarely hit port limits. But if hundreds of instances all connect to the *same* external endpoint — a single third-party API, a shared logging service, a package registry — those connections share the same destination IP and port, and each one requires a unique NAT port. This is where exhaustion happens. It's not total connection count that kills you; it's concentration of connections toward a single destination.

### Connection Lifecycle and Timeouts

NAT table entries have finite lifespans. For TCP, the entry persists as long as the connection is open and is cleaned up after a FIN/RST exchange, plus a brief grace period. For idle TCP connections, most NAT gateways impose an **idle timeout** — AWS NAT Gateways use 350 seconds. If no packets traverse the connection for 350 seconds, the mapping is silently removed.

When the mapping disappears, the next packet from the internal host — which still believes the connection is alive — arrives at a NAT gateway with no record of it. The gateway drops the packet. From the internal host's perspective, a previously working connection goes dead. No RST, no error, just silence followed eventually by a timeout.

This is the source of a specific and common class of production failures: long-lived, low-traffic connections through NAT. Database connections sitting in a pool that issue a query every few minutes. Persistent WebSocket connections with infrequent heartbeats. gRPC streams that go idle between bursts of messages. If the idle interval exceeds the NAT timeout, the connection silently breaks.

The fix is to ensure the application or transport layer sends keepalive packets more frequently than the NAT timeout. TCP keepalives must be configured with `tcp_keepalive_time` set well below the NAT idle timeout:

```
# For a 350-second NAT timeout, set keepalive at 60 seconds
sysctl -w net.ipv4.tcp_keepalive_time=60
sysctl -w net.ipv4.tcp_keepalive_intvl=10
sysctl -w net.ipv4.tcp_keepalive_probes=6
```

The application-side socket must also have `SO_KEEPALIVE` enabled, which many frameworks do not set by default.

## Destination NAT and the Inbound Side

The reverse operation — **Destination NAT (DNAT)** — rewrites the destination address of incoming packets. This is what happens when you attach a public IP to an instance behind an internet gateway, or when a load balancer forwards traffic to a backend in a private subnet. The incoming packet is addressed to the public IP; the gateway or load balancer rewrites the destination to the private IP of the target instance.

In cloud environments, DNAT is largely abstracted away. When you assign an Elastic IP to an EC2 instance, AWS performs one-to-one NAT transparently: outbound packets get their source rewritten to the Elastic IP, inbound packets to the Elastic IP get their destination rewritten to the private IP. The instance's OS never sees the public IP on any of its own interfaces — `ip addr` shows only the private address. This is a frequent source of confusion when applications try to bind to or advertise their public IP and fail because that address doesn't exist on any local interface. Any application that needs to know its own public IP must query an external source, such as the instance metadata service (`169.254.169.254` in AWS) or a public IP echo endpoint.

## NAT in Cloud Topologies

The standard production VPC architecture runs as follows: public subnets have a route to an **internet gateway** (which provides one-to-one NAT for instances with public IPs), while private subnets have a default route to a **NAT gateway** sitting in a public subnet. The NAT gateway itself has a public IP and routes outbound through the internet gateway.

This means there are two translation hops in the outbound path for private workloads: the instance sends to the NAT gateway, which translates and sends through the internet gateway. Inbound responses reverse the path. Understanding this chain matters when you're tracing packet flows or debugging MTU issues — each hop is a potential failure point.

A NAT gateway is a managed service with finite capacity. AWS NAT Gateways support up to 55,000 simultaneous connections to a single destination and can scale to 100 Gbps. Exceeding these limits requires multiple NAT gateways with traffic distributed across them — typically by deploying one per availability zone and routing each AZ's private subnets to its local NAT gateway. This pattern provides both capacity scaling and failure isolation: if one AZ's NAT gateway goes down, only that AZ's private workloads lose outbound internet access.

## Tradeoffs and Failure Modes

### Port Exhaustion Under Load

The most common NAT-related production failure is **port exhaustion**. When many workloads behind a single NAT gateway make connections to the same destination faster than old connections are released, the available port pool drains. New connection attempts fail with connection timeouts, not explicit errors. The application logs show timeouts reaching an external service; nothing in the application code is wrong. Only the NAT gateway's `ErrorPortAllocation` metric (in AWS) reveals the cause.

This hits hardest with bursty workloads: a fleet of Lambda functions in a VPC all calling the same external API concurrently, or a batch job that fans out hundreds of HTTP requests to a single endpoint. Mitigations include distributing traffic across multiple NAT gateways (each with its own public IP, doubling the port pool), attaching additional Elastic IPs to the NAT gateway (AWS supports up to 8, providing roughly 440,000 ports per destination), or re-architecting the application to reuse connections via HTTP/2 multiplexing or connection pooling — which dramatically reduces port consumption because many requests share a single connection.

### Silent Connection Death

As described above, idle connections exceeding the NAT timeout break silently. This failure is insidious because it is intermittent and timing-dependent. A connection pool that works perfectly under steady weekday load starts dropping connections on Sunday nights when traffic drops low enough for connections to sit idle. The symptom is a burst of errors when traffic picks back up Monday morning and the application attempts to use connections that the NAT gateway has already forgotten.

### Cost as an Architectural Force

NAT gateways are not free. They charge per hour of availability and per gigabyte of data processed. For workloads that move significant data through the NAT gateway — pulling large datasets from external sources, streaming logs to external collectors, downloading container images — the data processing charges become a meaningful budget line. This creates a real architectural tradeoff: you can eliminate NAT costs for specific traffic patterns by using **VPC endpoints** (for AWS services like S3, DynamoDB, or ECR), **PrivateLink** (for supported SaaS services), or by placing workloads with heavy internet needs in public subnets with their own public IPs and tighter security group rules. Ignoring NAT data processing costs is one of the most common causes of unexpectedly high cloud bills.

### Protocols That Break Through NAT

NAT rewrites IP headers, but some application-layer protocols embed IP addresses in the *payload*. FTP in active mode is the classic example: the client sends its private IP address inside the FTP control channel, telling the server where to open a data connection. If that IP is `10.0.4.17`, the server cannot reach it. SIP (used in VoIP) has the same problem. Modern systems generally avoid these protocols or use their passive modes, but integration with legacy systems that rely on them will fail in ways that are baffling if you don't know NAT is rewriting headers but not payloads.

## The Mental Model

NAT is a stateful packet-rewriting layer that maps private addresses to public addresses using a finite translation table. Every outbound connection consumes a slot in that table, identified by a port number. Return traffic works because the table entry exists; unsolicited inbound traffic fails because no entry exists. The table has finite capacity (bounded by available ports per destination) and finite retention (bounded by idle timeouts).

Every surprising NAT behavior follows from these two constraints. Port exhaustion is the capacity limit. Silent connection drops are the retention limit. The outbound/inbound asymmetry is the statefulness requirement. When you are reasoning about whether traffic will flow through a NAT gateway, ask two questions: was there an outbound connection that created a table entry, and is that entry still alive? If the answer to either is no, the traffic will not flow.

## Key Takeaways

- **NAT rewrites packet source addresses and ports on outbound traffic**, substituting a public IP for a private one, and uses a stateful translation table to reverse the substitution on return traffic.

- **The outbound/inbound asymmetry is structural, not policy-based.** Inbound traffic through a NAT gateway fails not because of a firewall rule, but because no translation table entry exists to tell the gateway which internal host to forward to.

- **Port exhaustion is a per-destination limit.** A NAT gateway can sustain roughly 64,000 simultaneous connections to a single destination IP:port pair per public IP; connections to different destinations can reuse the same NAT-side port.

- **Idle connections die silently when the NAT timeout expires.** The gateway removes the table entry and drops subsequent packets with no error signaled to the internal host. TCP keepalives must be configured shorter than the NAT idle timeout to prevent this.

- **NAT gateways are a throughput, port, and cost bottleneck.** They have bandwidth caps, connection limits, and per-GB data processing charges that compound at scale. VPC endpoints and PrivateLink eliminate NAT usage for specific traffic paths.

- **Deploy one NAT gateway per availability zone** to provide both horizontal port capacity and failure isolation — a single NAT gateway failure should not take out outbound connectivity for your entire VPC.

- **Some protocols break through NAT because they embed IP addresses in application-layer payloads**, not just packet headers. FTP active mode and SIP are the canonical examples.

- **Instances behind NAT never see their own public IP on a local interface.** Applications that need their public address must query the cloud metadata service or an external endpoint — binding to or advertising the public IP directly will fail.

[← Back to Home]({{ "/" | relative_url }})
