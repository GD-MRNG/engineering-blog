---
layout: post
title: "1.1.2 IP Addressing and Subnetting (CIDR)"
author: "Glenn Lum"
date:   2026-01-16 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most engineers can read CIDR notation. They see `10.0.1.0/24` in a Terraform file or a VPC console and they have a rough sense that it means "a block of addresses." They can usually guess that `/24` is smaller than `/16`. But when it comes time to actually design a network — to decide how many subnets, how large, whether two VPCs can peer, whether there's room to grow — they are guessing. They are guessing because they never learned what the `/24` actually *does* at the bit level, and without that, every subnetting decision is a coin flip dressed up as engineering.

The gap is this: an IP address is not just an identifier. It is a *structured* identifier that encodes two separate pieces of information — which network a host belongs to, and which host within that network it is. The CIDR prefix is the dividing line between those two pieces. Everything about network design flows from understanding where that line sits and what moving it costs you.

## The Binary Structure You Cannot Skip

An IPv4 address is 32 bits. When you see `10.0.1.5`, you are looking at four decimal numbers (octets) that each represent 8 bits. The address in binary is:

```
10.0.1.5 → 00001010.00000000.00000001.00000101
```

Every operation in subnetting is a bitwise operation. If you try to reason about subnetting purely in decimal, you will eventually get confused, because the boundaries that matter are bit boundaries, and they do not always land neatly on octet boundaries.

The CIDR prefix — the number after the slash — tells you how many of those 32 bits identify the **network**. The remaining bits identify the **host** within that network.

A `/24` means the first 24 bits are the network portion and the last 8 bits are the host portion. A `/16` means the first 16 bits are network, the last 16 are host. A `/20` means the first 20 bits are network and the last 12 are host — and now the boundary falls in the middle of the third octet, which is where most people's intuition breaks down.

### What the Prefix Mask Actually Does

The prefix length corresponds to a **subnet mask**: a 32-bit value where the first N bits are 1 and the rest are 0.

```
/24 → 11111111.11111111.11111111.00000000 → 255.255.255.0
/16 → 11111111.11111111.00000000.00000000 → 255.255.0.0
/20 → 11111111.11111111.11110000.00000000 → 255.255.240.0
```

To determine the **network address** (the base of the block), you perform a bitwise AND between the IP address and the mask. To determine the **broadcast address** (the top of the block), you set all the host bits to 1. Every address between those two — exclusive of the network and broadcast addresses themselves — is a usable host address.

For `10.0.1.5/24`:

```
Address:    00001010.00000000.00000001.00000101  (10.0.1.5)
Mask:       11111111.11111111.11111111.00000000  (255.255.255.0)
AND result: 00001010.00000000.00000001.00000000  (10.0.1.0) ← network address

Broadcast:  00001010.00000000.00000001.11111111  (10.0.1.255)
Usable range: 10.0.1.1 through 10.0.1.254 → 254 hosts
```

The general formula: a `/N` block contains **2^(32-N)** total addresses. Subtract 2 (network and broadcast) to get usable host addresses in a traditional networking context. In cloud environments, the provider typically reserves additional addresses — AWS reserves 5 per subnet, for example — so the real usable count is lower.

### The Sizes That Matter in Practice

You do not need to memorize a table, but you need to be able to derive these quickly:

```
/32 →   1 address  (a single host; used in routing tables and security rules)
/28 →  16 addresses (14 usable, ~11 in AWS; small utility subnets)
/24 → 256 addresses (254 usable, 251 in AWS; the default "comfortable" subnet)
/20 → 4,096 addresses (common for larger subnets in cloud VPCs)
/16 → 65,536 addresses (a typical VPC-level CIDR in AWS)
```

Each step in prefix length doubles or halves the block. Going from `/24` to `/23` doubles the size to 512 addresses. Going from `/24` to `/25` halves it to 128. This exponential scaling is why small changes in prefix length have large consequences.

## How Addresses Get Carved Into Subnets

A VPC or network CIDR block is the total address space you have to work with. Subnetting is the act of dividing that space into smaller, non-overlapping blocks that serve different purposes — public subnets, private subnets, database subnets, subnets per availability zone.

This is pure arithmetic, but the constraint is rigid: **subnets within a network must not overlap, and they must align to power-of-two boundaries.**

If your VPC is `10.0.0.0/16`, you have 65,536 addresses to divide. A common approach is to carve it into `/24` subnets, giving you up to 256 subnets of 256 addresses each. But you could also use `/20` subnets (16 subnets of 4,096 addresses) or mix sizes — as long as no two blocks overlap.

Here is where bit-level understanding pays off. Suppose you allocate `10.0.0.0/20` as your first subnet. That covers `10.0.0.0` through `10.0.15.255` — the first 20 bits are fixed, and the remaining 12 bits span all combinations. Your next `/20` block must start at `10.0.16.0/20`. If you mistakenly try to allocate `10.0.8.0/20`, it overlaps with the first block because `10.0.8.0` falls within the range `10.0.0.0 – 10.0.15.255`.

The way to think about it: a `/20` block must start at an address where the last 12 bits are all zero. The valid starting points within a `/16` are `10.0.0.0`, `10.0.16.0`, `10.0.32.0`, `10.0.48.0`, and so on — incrementing by 16 in the third octet each time (because 2^12 = 4096, which is 16 × 256).

### The Relationship Between VPC CIDRs and Subnet CIDRs

The subnet CIDR must be a subset of the VPC CIDR. This sounds obvious, but it has a non-obvious implication: **the subnet prefix must be longer (more specific) than the VPC prefix.** If your VPC is a `/16`, your subnets must be `/17` or longer. A subnet cannot be the same size as or larger than the VPC that contains it.

In practice, you are choosing two numbers when you design a network: the VPC prefix length (which determines your total address budget) and the subnet prefix length (which determines how many hosts fit in each subnet and, by division, how many subnets you can have). If the VPC is `/16` and subnets are `/24`, you get 256 subnets with 251 usable addresses each (in AWS). If the VPC is `/16` and subnets are `/20`, you get 16 subnets with 4,091 usable addresses each. These are hard tradeoffs: more subnets means more granular segmentation but fewer hosts per segment. Fewer, larger subnets means less flexibility in network topology.

## How Routing Uses CIDR: Longest Prefix Match

When a packet needs to reach a destination, the routing table is consulted. A routing table contains entries like:

```
10.0.1.0/24  → local
10.0.0.0/16  → vpc-router
0.0.0.0/0    → internet-gateway
```

If the destination is `10.0.1.17`, multiple entries might match: it matches `10.0.1.0/24`, it matches `10.0.0.0/16`, and it matches `0.0.0.0/0` (which matches everything). The router selects the **longest prefix match** — the most specific route. In this case, `/24` wins, so the packet is delivered locally.

This mechanism is why CIDR works at all. It allows hierarchical aggregation: you can advertise a single `/16` to the outside world while internally routing to specific `/24` subnets. It also means that route specificity is a tool you can use deliberately — for example, adding a `/32` route to send traffic for a single host through a specific path, overriding the broader subnet route.

## Private Address Space and Why Overlaps Are Poison

RFC 1918 defines three private address ranges that are not routable on the public internet:

```
10.0.0.0/8      (16,777,216 addresses)
172.16.0.0/12   (1,048,576 addresses)
192.168.0.0/16  (65,536 addresses)
```

Every VPC, every corporate network, every home router uses addresses from these ranges. This works fine in isolation. It breaks when you need to connect two networks.

**VPC peering**, **transit gateways**, and **VPN connections** all require that the connected networks have non-overlapping CIDR blocks. If your production VPC uses `10.0.0.0/16` and your staging VPC also uses `10.0.0.0/16`, you cannot peer them. The routers would have no way to determine which network a packet destined for `10.0.5.20` should be sent to.

This is not a theoretical concern. It is the single most common networking mistake in organizations that grow from one environment to many. The first VPC gets `10.0.0.0/16` because that is what the tutorial used. The second VPC gets the same range because a different team set it up. Six months later, someone needs cross-VPC connectivity and discovers the ranges overlap. The remediation is re-addressing one of the VPCs, which means recreating subnets, updating security groups, modifying application configurations, and potentially redeploying every resource in that network. It is the networking equivalent of a database migration on a live system, and it is entirely preventable with upfront planning.

## Tradeoffs and Failure Modes

### Allocating Too Large

Giving every VPC a `/16` feels safe — you will never run out of addresses. But the `10.0.0.0/8` space only contains 256 non-overlapping `/16` blocks. If you are building across multiple environments, regions, and accounts, 256 is not a large number. Over-allocating address space is borrowing from your future self. The pressure compounds when you need to peer networks or establish VPN connectivity, because every connected network must have a unique range.

### Allocating Too Small

A `/24` subnet with 251 usable addresses (in AWS) sounds generous until you are running an auto-scaling group that spins up 80 instances during peak load across three availability zones. That is roughly 27 instances per AZ per subnet — fine for now, but you have consumed over 10% of the subnet and you have not accounted for ENIs from Lambda functions, ECS tasks, or load balancer nodes, all of which consume IP addresses from the subnet. Container workloads on EKS are particularly aggressive consumers: each pod gets its own IP address from the subnet CIDR, and a single node can host dozens of pods.

Running out of IP addresses in a subnet manifests as new instances or pods failing to launch with opaque errors about "insufficient IP addresses" or ENI creation failures. The fix requires either migrating workloads to a new, larger subnet or adding secondary CIDR blocks — both of which involve downtime or significant operational complexity.

### The Mid-Octet Boundary Mistake

When the prefix length does not land on an octet boundary — `/20`, `/22`, `/27` — the valid block boundaries are not intuitive in decimal. Engineers who reason only in dotted decimal frequently create overlapping allocations. `10.0.48.0/20` and `10.0.52.0/22` look like they should not overlap, but they do: the `/20` block covers `10.0.48.0` through `10.0.63.255`, and `10.0.52.0` falls squarely within that range. The only reliable way to verify is to check the binary, or use a CIDR calculator — but you should understand *why* the calculator gives the answer it does.

## The Mental Model

An IP address is a 32-bit number that encodes a position in a hierarchy. The CIDR prefix draws a line through those 32 bits: everything to the left of the line is the network identity, everything to the right is the host identity. Moving that line left gives you more hosts per network but fewer possible networks. Moving it right gives you more networks but fewer hosts each. Every subnetting decision is an act of placing that dividing line, and the consequences are governed by powers of two — which means small changes in the prefix length produce large changes in capacity.

The skill this builds is not arithmetic. It is the ability to look at a network design — a VPC CIDR, a set of subnets, a routing table — and immediately reason about capacity, reachability, and growth constraints. When someone proposes a `/24` for a Kubernetes subnet, you should be able to feel the tension without reaching for a calculator. When two teams pick overlapping ranges, you should understand why that is not a configuration problem but an architectural one that gets harder to fix the longer it exists.

## Key Takeaways

- The CIDR prefix length specifies how many of the 32 bits in an IPv4 address identify the network; the remaining bits identify hosts within that network. A `/24` means 24 network bits and 8 host bits, yielding 256 addresses.

- Every increase of 1 in prefix length halves the address block. Every decrease of 1 doubles it. This exponential relationship means the difference between `/24` (256 addresses) and `/20` (4,096 addresses) is only 4 bits but a 16x difference in capacity.

- Subnet boundaries must align to power-of-two addresses in binary. When the prefix does not fall on an octet boundary (e.g., `/20`, `/22`), overlaps are easy to create accidentally and must be verified at the bit level.

- Cloud providers reserve addresses within each subnet beyond the standard network and broadcast addresses. In AWS, 5 addresses per subnet are unavailable, which matters significantly in small subnets like `/28`.

- Overlapping CIDR blocks between VPCs or networks prevent peering, transit gateway attachment, and VPN connectivity. This is the most expensive subnetting mistake in cloud environments because remediation requires re-addressing live infrastructure.

- Routing tables resolve ambiguity through longest prefix match: when multiple CIDR entries match a destination, the most specific (longest prefix) wins. This is the mechanism that makes hierarchical subnetting and route overrides work.

- Container and serverless workloads consume IP addresses at a much higher rate than traditional VM-based architectures. Subnet sizing must account for per-pod and per-ENI address consumption, not just instance count.

- Plan your address space allocation across all environments, regions, and accounts before creating your first VPC. Treating CIDR allocation as a global constraint rather than a per-VPC decision avoids the overlapping-range problem that becomes exponentially harder to fix over time.

[← Back to Home]({{ "/" | relative_url }})
