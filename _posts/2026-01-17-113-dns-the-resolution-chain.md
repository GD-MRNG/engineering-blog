---
layout: post
title: "1.1.3 DNS: The Resolution Chain"
author: "Glenn Lum"
date:   2026-01-17 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most engineers think of DNS as a single lookup: you ask for `api.example.com` and you get back `93.184.216.34`. A black box with a domain going in and an IP coming out. This mental model works fine right up until you're staring at an incident where half your users can reach your new service and the other half are still hitting the old IP, or where a domain you just registered returns `NXDOMAIN` for some clients but resolves perfectly from your laptop. The problem is not that DNS is complicated in the way distributed consensus is complicated. It's that DNS is a **delegation chain with caching at every layer**, and if you don't understand which layer is holding stale data or which server is authoritative for what, you cannot reason about what's happening. You can only guess and wait.

## The Query Lifecycle

When your application calls `getaddrinfo()` or your browser needs to resolve a hostname, the first thing that happens is not a network request. Your operating system checks its local DNS cache. If it finds a valid, unexpired record, the answer comes back in microseconds with no network activity at all. If it doesn't, your OS hands the query to a **stub resolver** — a deliberately simple piece of code whose only job is to forward the question to a **recursive resolver** and wait for the answer.

The stub resolver is not doing DNS resolution. It is asking someone else to do it. That someone else — the recursive resolver — is the workhorse of the entire system. This is typically a server operated by your ISP, your cloud provider, or a public service like `8.8.8.8` (Google) or `1.1.1.1` (Cloudflare). The recursive resolver is the one that actually walks the delegation chain on your behalf.

Here is what that walk looks like for a cold query — one where the recursive resolver has nothing cached — for `api.example.com`:

The recursive resolver starts by querying a **root nameserver**. There are 13 root server addresses (designated `a.root-servers.net` through `m.root-servers.net`), though behind those addresses sit hundreds of anycast instances distributed globally. The root server does not know the IP address of `api.example.com`. It doesn't even know who's responsible for `example.com`. What it knows is which nameservers are authoritative for the `.com` **top-level domain (TLD)**. It returns a **referral**: a set of NS records pointing to the `.com` TLD nameservers, along with their IP addresses.

The recursive resolver takes that referral and queries one of the `.com` TLD nameservers. That server also doesn't know the IP of `api.example.com`. But it does know which nameservers are authoritative for `example.com`. It returns another referral: NS records for `example.com`'s nameservers — something like `ns1.example.com` and `ns2.example.com` — and their corresponding IP addresses.

The recursive resolver now queries one of `example.com`'s **authoritative nameservers**. This server actually has the answer. It holds the zone file for `example.com`, and it returns an **A record** (or AAAA for IPv6) with the IP address of `api.example.com` and a **TTL** value.

The recursive resolver caches that answer, marks it with the TTL, and returns it to the stub resolver, which returns it to your application. The entire process — three to four network round trips across different servers operated by entirely different organizations — happens in tens of milliseconds for a cold lookup.

### Referrals, Not Forwarding

A critical distinction: root servers and TLD servers do not answer your query. They **refer** you to someone who might. Each step in the chain is a delegation — "I don't know, but this server is responsible for the next piece." The recursive resolver follows these referrals iteratively, one hop at a time, assembling the final answer itself.

This is why the recursive resolver is called "recursive" even though its behavior is technically iterative. From the stub resolver's perspective, it makes one request and gets back a complete answer — that's the recursion. Internally, the recursive resolver is performing an iterative walk through the delegation hierarchy.

### Glue Records and the Bootstrap Problem

There's a subtle chicken-and-egg problem in this chain. If the authoritative nameserver for `example.com` is `ns1.example.com`, how do you find the IP address of `ns1.example.com`? You'd need to query the authoritative nameserver for `example.com`, which is `ns1.example.com`, which you can't reach because you don't know its IP.

This is solved by **glue records** — A/AAAA records for nameservers that are included in the parent zone's delegation response. When the `.com` TLD server refers you to `ns1.example.com`, it also includes an additional section in the response containing `ns1.example.com → 198.51.100.1`. These glue records are maintained at the registrar level and are essential for the resolution chain to function. If your glue records point to an outdated IP, resolution for your entire domain breaks — and the error will look nothing like a "wrong IP" problem. It will look like your domain doesn't exist.

## How TTL Actually Works

TTL is an integer in a DNS response, expressed in seconds, that says: "you may cache this answer for this many seconds." When a recursive resolver caches a record with a TTL of 3600, it starts a countdown. After 3600 seconds, the record is evicted, and the next query for that name triggers a fresh walk through the delegation chain (or at least a query to the authoritative server, since the resolver likely still has the TLD and root referrals cached).

The important thing to understand is that TTL is **per-cache, per-record, and starts at cache insertion time**. There is no global clock. There is no coordination between resolvers. If Cloudflare's resolver caches your record at 14:00:00 and Google's resolver caches it at 14:02:30, those two caches will expire at different times. This is why the notion of DNS "propagation" is misleading — nothing is propagating. Independent caches are expiring at independent times, and when they do, they independently discover whatever the current authoritative answer is.

### TTL Does Not Mean What You Think During Migrations

Suppose your A record for `api.example.com` has a TTL of 86400 (24 hours) and points to `93.184.216.34`. You update it to point to `198.51.100.10`. The new TTL you set on the new record is irrelevant for the next 24 hours. Every recursive resolver that cached the old record will continue serving `93.184.216.34` until its local countdown expires. The TTL on your new record only governs how long the new answer gets cached after a resolver fetches it.

This is why the standard practice for DNS migrations is to **lower the TTL well in advance**. If you know you're going to change an IP address on Thursday, drop the TTL to 300 (five minutes) on Monday or Tuesday. By Thursday, all caches will have either expired their old long-TTL records and fetched the short-TTL version, or they'll expire within a few minutes. After the migration stabilizes, raise the TTL back up to reduce query load on your authoritative servers.

### Negative Caching

When a recursive resolver queries a name that doesn't exist, the authoritative server returns an **NXDOMAIN** response. This response is also cached, governed by the **SOA record's minimum TTL field** (sometimes called the negative TTL). If your SOA has a minimum TTL of 3600 and someone queries `typo.example.com` before you've created that record, resolvers will cache the "this doesn't exist" answer for up to an hour. If you create the record during that hour, those resolvers won't see it until the negative cache expires.

This bites hardest during initial service deployments. You set up a new subdomain, test it immediately from a machine that already queried it (and got NXDOMAIN), and conclude the DNS is broken. It isn't. Your resolver cached the negative response.

## Caching Beyond the Resolver

The recursive resolver is the most important cache in the chain, but it is not the only one. Your operating system maintains a DNS cache (visible on macOS with `sudo dscacheutil -flushcache`, on Linux it depends on whether `systemd-resolved` or `nscd` is running). Your browser maintains its own DNS cache (Chrome's is viewable at `chrome://net-internals/#dns`). Some application runtimes cache DNS results internally — the JVM, notoriously, caches DNS lookups indefinitely by default when a security manager is installed, controlled by `networkaddress.cache.ttl` in `java.security`.

Each of these caches operates independently with its own expiry logic. When you're debugging a resolution issue, you have to think about which cache you're actually testing. Running `dig @8.8.8.8 api.example.com` bypasses your OS cache and your browser cache — it queries Google's recursive resolver directly. Running `nslookup api.example.com` uses your OS's configured resolver. Curling the endpoint uses whatever your OS and potentially your runtime decide. These can all return different answers at the same point in time, and that's not a bug — it's the system working as designed.

## Tradeoffs and Failure Modes

### The TTL Tension

Low TTLs give you fast failover and migration agility. High TTLs reduce query volume against your authoritative servers and improve resolution latency for end users (cached answers are fast). There is no universally correct value. A TTL of 300 seconds is common for records that might change during incident response. A TTL of 86400 is reasonable for records that almost never change, like MX records. The cost of a low TTL is real: more queries hit your authoritative nameservers, more cold lookups add latency for users, and if your authoritative servers become unreachable, caches drain within minutes and your domain effectively vanishes. With a high TTL, an authoritative outage is invisible for hours because the world is still serving cached answers.

### Resolver Misbehavior

Not all recursive resolvers honor TTL faithfully. Some ISP resolvers impose a minimum TTL floor — even if you set a TTL of 60, they'll cache for 300. Some impose a maximum cap. Some enterprise resolvers serve stale records beyond their TTL if the authoritative server is unreachable (this is actually codified in RFC 8767 as "serve-stale"). You cannot assume that your TTL will be respected exactly. You can only set it and understand that it's a request, not a command.

### The Authoritative/Recursive Misconfiguration

One of the more insidious DNS failures happens when a server is configured to be both authoritative and recursive. It answers authoritatively for some zones and recursively for everything else. This creates cache poisoning vulnerabilities and unpredictable behavior. If you're running your own DNS infrastructure, your authoritative servers and your recursive resolvers should be separate systems with separate roles.

### CNAME Chains and Hidden Latency

A CNAME record doesn't resolve to an IP — it resolves to another domain name, which itself needs to be resolved. If `api.example.com` is a CNAME to `loadbalancer.cdn.example.net`, the resolver now has to resolve `loadbalancer.cdn.example.net` separately, potentially walking a different branch of the delegation tree. Stacking CNAMEs (a CNAME that points to another CNAME) multiplies this cost. Each link adds a potential cache miss and additional round trips. In latency-sensitive paths, an unnecessary CNAME chain is measurable overhead.

## The Mental Model

DNS is not a lookup. It is a hierarchical delegation system with independent caches at every layer. When you query a domain, you're walking a tree from the root to the specific zone that holds the answer, with each node in the tree only knowing the identity of the next node down. Every answer in this system has a shelf life (TTL), and that shelf life is enforced independently by every cache that holds a copy.

The practical consequence is that DNS changes are not atomic and not instant. They are **eventually consistent** across an unknowable number of independent caches, each running its own expiry clock. When you change a DNS record, you haven't changed what the world sees — you've changed what the world will *eventually* see, governed by TTLs you set in the past. Reasoning about DNS correctly means reasoning about cache state across time, not about the current value of a record.

## Key Takeaways

- DNS resolution is a delegation chain: stub resolver → recursive resolver → root server → TLD server → authoritative nameserver, with each step returning a referral to the next authority, not the final answer.

- The recursive resolver does all the real work. Your application's stub resolver just asks the recursive resolver and waits.

- TTL governs how long each independent cache holds a record. There is no coordination between caches — "DNS propagation" is actually independent caches expiring at different times.

- When preparing for a DNS migration, lower the TTL days in advance. The TTL on your *new* record doesn't help flush the *old* record from caches.

- Negative responses (NXDOMAIN) are cached too, governed by the SOA record's minimum TTL. Querying a name before the record exists will cause it to appear missing even after you create it.

- Multiple layers cache DNS results independently: browser, OS, application runtime (especially the JVM), and recursive resolver. When debugging, know which cache you're actually testing.

- Low TTLs buy agility but cost resilience: if your authoritative servers go down, low-TTL caches drain fast and your domain disappears. High TTLs are a buffer against authoritative outages.

- Not all resolvers honor your TTL. ISP resolvers may impose floors or caps, and some will serve stale records beyond TTL expiry. Your TTL is a request, not a guarantee.

[← Back to Home]({{ "/" | relative_url }})
