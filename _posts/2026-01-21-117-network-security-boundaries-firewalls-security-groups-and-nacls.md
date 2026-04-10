---
layout: post
title: "1.1.7 Network Security Boundaries: Firewalls, Security Groups, and NACLs"
author: "Glenn Lum"
date:   2026-01-21 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most engineers treat security groups, NACLs, and firewall rules as roughly the same thing: a list that says "allow traffic on port 443" or "block everything else." When traffic flows, they move on. When traffic doesn't flow, they start toggling rules until it does. This works until it doesn't — and when it doesn't, the failure is usually invisible and confusing, because the engineer is working from a mental model where all filtering works the same way. It does not. There are two fundamentally different filtering models operating simultaneously in most cloud environments, and they behave differently in ways that matter enormously for both security posture and debugging. The distinction is not academic. It is the difference between configuring one rule and having traffic flow, versus configuring one rule and watching packets vanish into silence on the return path.

## Two Filtering Models, Not One

Every packet that moves between resources in a cloud VPC passes through at least two independent filtering layers. In AWS, these are **security groups** and **network access control lists (NACLs)**. In other cloud providers the names differ, but the architectural pattern is consistent: one layer is stateful, the other is stateless. They evaluate traffic using entirely different logic, they attach at different points in the network topology, and they make different demands on the operator. Understanding what "stateful" and "stateless" actually mean at the packet level is the single most important conceptual prerequisite for working with network security boundaries.

### Stateful Filtering: Connection Tracking

A **stateful** filter — security groups in AWS, NSGs in Azure — maintains a **connection tracking table**. When a packet arrives and matches an allow rule, the filter records the connection tuple: source IP, source port, destination IP, destination port, and protocol. From that point forward, any packet that belongs to the same connection — including return traffic flowing in the opposite direction — is automatically permitted without being evaluated against the rules again.

Here's what that means concretely. You have an EC2 instance in a security group that allows inbound TCP on port 443 from `0.0.0.0/0`. A client sends a SYN packet to your instance on port 443. The security group evaluates the inbound rules, finds a match, and allows the packet through. It also creates a tracking entry for this connection. When your instance sends back its SYN-ACK — which is now *outbound* traffic from the instance, originating from port 443 and destined for the client's ephemeral port — the security group does not evaluate the outbound rules. It recognizes this packet as return traffic for a tracked connection and passes it through automatically.

This is why, with security groups, you can configure an inbound rule for port 443 and have a working HTTPS service without touching the outbound rules. The return path is implicit. The security group is not evaluating two independent rule sets for two directions; it is tracking connections and using that state to exempt return traffic from evaluation.

The tracking table is not infinite. Entries expire after a timeout — typically around 350 seconds for established TCP connections and shorter for UDP. If a connection is idle long enough for the tracking entry to expire, subsequent packets will be evaluated against the rules as if they were new. This is why you can sometimes see long-lived idle connections break through a security group: the SG dropped the tracking entry, and there is no rule to re-admit the packet.

### Stateless Filtering: Per-Packet Evaluation

A **stateless** filter — NACLs in AWS — has no memory. It does not track connections. Every single packet, whether it is the first SYN of a new connection or the ten-thousandth data packet of an ongoing transfer, is evaluated independently against the rule set. Inbound packets are evaluated against inbound rules. Outbound packets are evaluated against outbound rules. There is no concept of "return traffic."

This has a critical practical consequence: **ephemeral ports**. When your server responds to an HTTPS request, the return packets are not sent *from* port 443 *to* port 443. They are sent from port 443 to whatever ephemeral port the client's operating system chose when it opened the connection — typically a port in the range 1024–65535 (the exact range varies by OS). In a stateful filter, this is invisible to you; connection tracking handles it. In a stateless filter, you must explicitly allow outbound traffic to those ephemeral ports, or your response packets will be silently dropped.

A concrete example: you configure a NACL to allow inbound TCP on port 443 from `0.0.0.0/0`. Traffic arrives. Your application processes it and sends a response. That response is an outbound packet from port 443 to, say, port 52344 on the client. The NACL evaluates this outbound packet against the outbound rules. If there is no outbound rule permitting TCP traffic to the ephemeral port range, the packet is dropped. The client sees a timeout. Your application logs show a successful response. Everything looks fine on the server side, and the client gets nothing.

This is the single most common failure mode with NACLs, and it catches experienced engineers because it is counterintuitive if you've been working exclusively with security groups.

### Rule Evaluation: Order vs. Aggregate

The two models also differ in *how* rules are evaluated, and this difference changes what "adding a rule" means.

**Security groups** evaluate all rules as an aggregate. There are no rule numbers, no ordering, and no deny rules. Every rule is an allow rule. If any rule permits the traffic, the traffic is allowed. If no rule matches, the traffic is denied by the implicit default-deny. This means security groups are purely additive: adding a rule can only make the group *more* permissive, never less. You cannot create a security group rule that says "allow all of `10.0.0.0/16` except `10.0.0.47`." The model does not support it.

**NACLs** evaluate rules in order by rule number, lowest first. The first rule that matches determines the outcome — allow or deny — and evaluation stops. This means rule ordering is load-bearing. A deny rule at number 100 takes precedence over an allow rule at number 200, even if the allow rule is more specific. This gives NACLs more expressive power: you *can* block a specific IP within a broader allowed range. But it also means that a carelessly numbered rule can silently override rules that appear later in the list.

```
# NACL rules evaluated in order:
Rule 100: DENY  TCP  port 22  from 0.0.0.0/0
Rule 200: ALLOW TCP  port 22  from 10.0.0.0/16

# Result: ALL SSH is denied, including from 10.0.0.0/16.
# Rule 100 matches first and evaluation stops.
```

To get the intended behavior — block external SSH but allow internal — you'd need to reverse the order or renumber:

```
Rule 100: ALLOW TCP  port 22  from 10.0.0.0/16
Rule 200: DENY  TCP  port 22  from 0.0.0.0/0
```

### Where Each Layer Attaches

Security groups attach to **elastic network interfaces** (ENIs) — which in practice means they attach to individual instances, containers, Lambda functions, RDS instances, or any other resource with a network interface. A single ENI can have multiple security groups applied, and their rules are aggregated (union of all allow rules across all groups).

NACLs attach to **subnets**. Every packet entering or leaving a subnet passes through the NACL. A subnet has exactly one NACL at a time. This means NACLs operate as a perimeter control around a network segment, while security groups operate as a per-resource control.

The evaluation sequence for a packet moving between two instances in different subnets within the same VPC is: **outbound security group of the source → outbound NACL of the source subnet → inbound NACL of the destination subnet → inbound security group of the destination**. For two instances in the *same* subnet, NACLs are still evaluated if traffic crosses the subnet boundary, but the behavior depends on whether the traffic is routed through the VPC router or stays within the subnet — in AWS, even intra-subnet traffic passes through NACLs.

This layering means a packet must be permitted by *both* layers to flow. Security group allows it but NACL denies it? Blocked. NACL allows it but security group denies it? Blocked. They are independent, and the most restrictive layer wins.

### Security Group References: Filtering by Identity

One mechanism that is genuinely non-obvious and extremely powerful in practice is **security group referencing**. Instead of writing a rule that allows traffic from an IP range, you can write a rule that allows traffic from any resource that is a member of a specific security group.

```
# Instead of:
Allow TCP 5432 from 10.0.1.0/24

# You write:
Allow TCP 5432 from sg-0abc1234 (the "web-servers" security group)
```

This decouples your security rules from your IP topology. When you auto-scale your web tier and new instances launch with new IP addresses, they are automatically permitted to reach the database because they inherit the "web-servers" security group. You don't need to update any rules. The security group acts as an identity tag that the filtering layer understands natively.

This is the mechanism that makes security groups the primary tool for east-west traffic control within a VPC, and it is the main reason NACLs are often left at their permissive defaults for intra-VPC traffic. Managing IP-based NACL rules across a dynamic, auto-scaling fleet is operationally expensive and fragile. Security group references solve the same problem with zero ongoing maintenance.

## Where This Breaks

### The Ephemeral Port Trap

Already described above, but worth emphasizing as a failure mode: any time you tighten NACL outbound rules beyond "allow all," you risk breaking return traffic for every inbound service. This failure is silent on the server side, presents as a timeout on the client side, and does not appear in any application log. VPC Flow Logs will show the packet as `REJECT` on the outbound NACL evaluation, but only if you have flow logs enabled and know to look at the outbound direction for what appears to be an inbound connectivity problem.

### The "It Worked Yesterday" Problem

Security group connection tracking entries expire. An application that maintains a pool of long-lived database connections might work perfectly for days, then start failing after a deployment that restarts the connection pool — because the new connections are being established during a window when some other change (a modified security group rule, a briefly detached ENI) causes them to fail. Worse, if you modify a security group rule, existing tracked connections are *not* re-evaluated. The old connection continues to work under the old rule until it closes or its tracking entry expires. This means your rule change "takes effect" immediately for new connections but has no visible effect on existing ones, which makes testing changes in production misleading.

### Egress as a Blind Spot

Most engineers think about ingress: what traffic can reach my service? Egress — what traffic can leave — gets far less attention, and this creates two problems. First, the security problem: a compromised instance with unrestricted egress can exfiltrate data to any endpoint on the internet. Egress filtering is one of the most effective controls against data exfiltration and command-and-control communication. Second, the operational problem: when a service cannot reach an external API, DNS server, or package repository, the cause is often an egress rule that nobody thought to configure, because the mental model was entirely focused on "letting traffic in."

### Debugging Across Two Layers

When connectivity fails and both security groups and NACLs are in play, the debugging surface doubles. A common pattern is an engineer verifying that the security group allows the traffic, confirming it looks correct, and then spending hours reviewing application configuration — because they forgot NACLs exist. The inverse also happens: someone troubleshoots NACLs and forgets that security groups on the *destination* resource are a separate check. VPC Flow Logs help, but they report the *aggregate* verdict, not which layer caused the rejection. Isolating the layer requires methodically checking each one, or temporarily setting one layer to fully permissive to rule it out.

## The Mental Model

Think of network security boundaries as two concentric filtering systems with fundamentally different architectures. The outer layer (NACLs, or any stateless perimeter filter) is a packet-level gatekeeper: it inspects each packet in isolation, cares about both directions independently, and requires you to understand the full bidirectional flow of traffic including ephemeral ports. The inner layer (security groups, or any stateful instance-level filter) is a connection-level gatekeeper: it evaluates the first packet of a connection and then remembers it, freeing you from managing return traffic but binding you to the characteristics and limitations of connection tracking.

When traffic fails, your first question should be: which layer is rejecting it, and is the rejection happening on the forward path or the return path? Most connectivity problems that look mysterious stop being mysterious once you ask that question, because the answer forces you to reason about the specific filtering model — stateful or stateless — that applies at the point of failure.

## Key Takeaways

- **Stateful filters** (**security groups**) track connections and automatically permit return traffic; **stateless filters** (**NACLs**) evaluate every packet independently, including responses, and require explicit rules for both directions.

- With **NACLs**, forgetting to allow outbound traffic to the **ephemeral port range** (1024–65535) will silently drop your server's responses while the server itself logs no errors — the failure only manifests as a **client-side timeout**.

- **Security group rules** are unordered and purely additive (allow-only with implicit deny), while **NACL rules** are evaluated in **numeric order** with **first-match-wins** semantics, making rule numbering load-bearing.

- **Security group rule changes** apply immediately to new connections but do not re-evaluate **existing tracked connections**, which means the effect of a change may not be fully visible until old connections close or their **tracking entries** expire.

- **Security groups** attach to individual **network interfaces** (per-resource), **NACLs** attach to **subnets** (per-segment), and a packet must be permitted by both layers to flow — the **most restrictive layer** wins.

- **Security group references** allow rules based on **group membership** rather than IP addresses, making them the primary tool for **east-west traffic control** in dynamic, **auto-scaling environments** where IP-based rules are fragile.

- **Egress rules** are the most common blind spot: unrestricted egress is both a security liability (**data exfiltration**) and an operational debugging gap (**outbound connectivity failures** that nobody thought to check).

- When debugging connectivity failures across both layers, **VPC Flow Logs** report the **aggregate verdict** but not which layer caused the rejection — **isolating the responsible layer** requires methodical per-layer verification.

[← Back to Home]({{ "/" | relative_url }})
