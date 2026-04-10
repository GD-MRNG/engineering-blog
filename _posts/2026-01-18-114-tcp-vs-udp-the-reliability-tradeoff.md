---
layout: post
title: "1.1.4 TCP vs UDP: The Reliability Tradeoff"
author: "Glenn Lum"
date:   2026-01-18 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most engineers carry a one-line mental model of TCP and UDP: TCP is reliable, UDP is fast. That mental model is not wrong, but it is dangerously incomplete. It tells you which to pick for a textbook quiz. It does not tell you why your service is leaking sockets in `TIME_WAIT`, why a 0.1% packet loss rate is doubling your P99 latency, why your connection pool is exhausted even though your backend is healthy, or why a single dropped packet can stall an entire HTTP/2 stream. The reliability that TCP provides is not free. It is implemented by specific mechanisms — state machines, timers, retransmission queues, congestion windows — each of which has behavior that shows up in your production metrics whether or not you understand it. And the simplicity that UDP provides is not laziness. It is a deliberate architectural choice that pushes decisions to the application layer, where they can be made with context that the transport layer does not have.

This post is about what those mechanisms actually are, how they behave, and where they bite.

## What TCP Actually Does

TCP is not a single feature. It is a collection of cooperating mechanisms layered on top of IP, each solving a different problem. IP gives you best-effort delivery of individual packets between hosts. TCP adds four things on top of that: **connection establishment**, **reliable ordered delivery**, **flow control**, and **congestion control**. Each one has a cost.

### Connection Establishment: The Three-Way Handshake

Before any data moves, TCP requires a handshake. The client sends a `SYN` segment with an initial sequence number. The server responds with a `SYN-ACK` — its own initial sequence number plus an acknowledgment of the client's. The client then sends an `ACK` confirming the server's sequence number. Only after this exchange can data flow.

This costs one full round trip before any payload is transmitted. On a network with 50ms RTT, that is 50ms of pure overhead before the first byte of your HTTP request leaves the client. For a short-lived request to a service across the internet, this handshake latency can dominate the total request time. This is why connection reuse and connection pooling are not performance optimizations — they are architectural necessities. Every new TCP connection is a round trip you are choosing to pay.

The handshake also means both sides allocate state. The kernel creates a socket data structure, allocates send and receive buffers (typically 64KB–256KB each, tunable via `net.ipv4.tcp_rmem` and `net.ipv4.tcp_wmem` on Linux), and begins tracking sequence numbers. A server handling tens of thousands of concurrent connections is holding tens of thousands of these state structures in kernel memory.

### Sequence Numbers, Acknowledgments, and Retransmission

Every byte sent over a TCP connection is assigned a sequence number. The receiver acknowledges data by sending back the sequence number of the next byte it expects. If the sender does not receive an acknowledgment within a timeout window (**retransmission timeout**, or RTO), it resends the data.

This is where ordered delivery comes from, and it is also where **head-of-line blocking** comes from. TCP guarantees that the application sees bytes in order. If segments 1, 2, and 3 are sent and segment 2 is lost, the receiver holds segment 3 in a buffer and does not deliver it to the application until segment 2 has been retransmitted and received. The application is stalled waiting for one lost packet, even though subsequent data has already arrived.

For a single HTTP/1.1 request-response, this is rarely noticeable. For multiplexed protocols like HTTP/2 running over a single TCP connection, it is severe. A packet loss affecting one stream stalls every stream on that connection, because TCP has no concept of streams — it sees one ordered byte sequence. This is the specific problem that motivated QUIC, which implements its own reliability on top of UDP with per-stream ordering.

The retransmission timeout itself is adaptive. TCP estimates the round-trip time using an exponentially weighted moving average and sets the RTO based on that estimate plus a variance factor. But the minimum RTO on most Linux systems is 200ms (`net.ipv4.tcp_rto_min`), and after a retransmission fails, the RTO doubles — 200ms, 400ms, 800ms, 1.6s. A burst of packet loss on a connection can produce multi-second stalls that look like application hangs to the caller.

### Flow Control: The Receive Window

TCP includes a mechanism to prevent a fast sender from overwhelming a slow receiver. Each side advertises a **receive window** — the amount of buffer space it currently has available. The sender will not transmit more data than the receiver's window allows.

This is straightforward in concept but has a practical consequence: if your application is slow to read from the socket (because it is blocked on disk I/O, garbage collection, or downstream calls), the receive buffer fills, the window shrinks to zero, and the sender stalls. From the sender's perspective, the connection appears slow or stuck. From the application's perspective, everything is fine — it just has not gotten around to reading yet. This is one of the mechanisms behind **backpressure** in TCP-based systems, and it is why a slow consumer can degrade an entire pipeline.

### Congestion Control: The Network's Perspective

Flow control protects the receiver. **Congestion control** protects the network. TCP assumes that packet loss is a signal of network congestion and responds by reducing its sending rate.

The mechanism works through a **congestion window** (cwnd) maintained by the sender, separate from the receiver's advertised window. The actual amount of data in flight is limited by the minimum of the two windows. When a connection starts, the congestion window is small — typically 10 segments (about 14KB). This is **slow start**: the window doubles every round trip until it hits a threshold or encounters loss. On a 100ms RTT link, it takes several hundred milliseconds for TCP to ramp up to full throughput on a fresh connection, even if the link has plenty of bandwidth.

When loss is detected, the response depends on the congestion control algorithm. The classic behavior (Reno, Cubic) is to cut the congestion window in half and recover slowly. On a lossy network — wireless links, congested data center fabric — this means TCP throughput oscillates: ramp up, detect loss, cut back, ramp up again.

For short-lived connections, this matters enormously. A connection that sends a small request and receives a moderate response may never leave slow start. It pays the handshake cost, starts with a tiny window, and finishes the transfer before the window has grown large enough to use the available bandwidth. This is another reason persistent connections are critical: a long-lived connection has already completed slow start and has an accurate estimate of the available bandwidth.

## What UDP Actually Is

UDP is almost aggressively simple. A UDP datagram has an 8-byte header: source port, destination port, length, and checksum. That is it. There is no connection establishment, no sequence numbers, no acknowledgments, no retransmission, no flow control, no congestion control.

When your application sends a UDP datagram, the kernel hands it to the network stack, which wraps it in an IP packet and sends it. If it arrives, the receiving application gets it. If it does not arrive, nothing happens. If datagrams arrive out of order, the application receives them in whatever order they showed up. If the network is congested, UDP will keep sending at whatever rate the application asks for, because there is no congestion window to constrain it.

This is not negligence. It is a design choice. UDP provides **multiplexing** (via port numbers) and **integrity checking** (via checksum) on top of IP, and nothing else. Everything above that is the application's responsibility.

DNS uses UDP because a lookup is a single request and a single response — the overhead of a TCP handshake would often exceed the time for the lookup itself. Game servers use UDP because a stale position update is worse than a missing one — retransmitting a player's position from 200ms ago is pointless when you already have their position from 100ms ago. Video streaming uses UDP (via RTP) because a dropped video frame should be skipped, not retransmitted after the moment has passed.

QUIC, the protocol under HTTP/3, uses UDP as its substrate but implements its own connection establishment (with 0-RTT resumption), its own reliability (with per-stream retransmission), and its own congestion control. It chose UDP not because it wanted unreliable delivery, but because it wanted to implement reliability differently than TCP does — specifically, without head-of-line blocking across streams — and doing so required getting out from under TCP's guarantees.

## Where the Mechanics Bite

### TIME_WAIT Exhaustion

When a TCP connection closes, the side that initiates the close enters the `TIME_WAIT` state for twice the maximum segment lifetime (typically 60 seconds on Linux). During this time, the socket's source IP, source port, destination IP, and destination port tuple is reserved. If your service opens and closes many short-lived connections to the same destination — say, a microservice making HTTP calls without connection pooling — you can exhaust the available ephemeral port range (roughly 28,000 ports by default). New connections will fail with `EADDRNOTAVAIL`. The fix is connection reuse, but the failure mode is non-obvious: the service is healthy, the destination is healthy, and the network is fine. You are simply out of ports because of a TCP state machine transition that happens invisibly.

### Nagle's Algorithm and Delayed ACKs

TCP includes **Nagle's algorithm**, which buffers small writes and combines them into larger segments to reduce overhead. The receiver may use **delayed acknowledgments**, waiting up to 40ms before sending an ACK in case it can piggyback it on a response. When a sender using Nagle interacts with a receiver using delayed ACKs, you get a worst case: the sender is waiting for an ACK before sending more data, and the receiver is waiting before sending the ACK. The result is unexplained 40ms latency on small messages. This is why nearly every RPC framework and database driver sets `TCP_NODELAY` — it disables Nagle's algorithm — but if you are writing a custom protocol or using raw sockets, this interaction will surprise you.

### Congestion Control on Lossy Links

TCP interprets packet loss as congestion. On a wireless network or a transoceanic link where packet loss is caused by signal degradation rather than buffer overflow, TCP's response — cutting throughput — is exactly wrong. The network has capacity, but TCP is backing off because it cannot distinguish congestion loss from random loss. This is why TCP performance over high-latency lossy links (satellite, mobile) is historically poor, and why protocols like BBR (a congestion control algorithm that estimates bandwidth and RTT directly rather than inferring congestion from loss) were developed.

### The "TCP Is Reliable" Misconception

TCP guarantees that data is delivered in order or the connection is broken. It does not guarantee that data is delivered promptly. A connection experiencing heavy retransmission may deliver data with seconds of delay. TCP does not surface this to the application — the `read()` call simply blocks until data is available or the connection times out. If your application does not set its own timeouts at the socket level or the HTTP client level, TCP will happily wait through minutes of retransmission attempts before giving up. "TCP is reliable" means the kernel handles retransmission so you do not have to. It does not mean your request will complete in any bounded time.

## The Mental Model

Think of TCP as a stateful protocol engine running in the kernel, maintaining a per-connection state machine with its own timers, buffers, and rate control. Every connection has a lifecycle, a memory cost, and a throughput ramp-up curve. The reliability it provides is real, but it is implemented through mechanisms — retransmission, ordering, congestion response — that each have latency and resource costs. Those costs are invisible when things are working and dominant when things are degraded.

Think of UDP as a thin addressing layer. It gets your datagram to the right process on the right host, and that is all. Any guarantee beyond that — ordering, acknowledgment, retransmission, rate control — is yours to build or yours to explicitly decide you do not need.

The choice between them is not "reliable vs. fast." It is: do the kernel's built-in reliability mechanisms match the failure semantics your application needs, or do you need to implement different tradeoffs at the application layer? For most request-response services, TCP's mechanisms are correct and the engineering cost of reimplementing them would be absurd. For real-time media, high-frequency telemetry, or multiplexed protocols that need per-stream control, TCP's guarantees create problems that are harder to work around than building reliability yourself.

## Key Takeaways

- TCP's three-way handshake adds one full RTT of latency before any data transfer, making connection reuse and pooling essential for performance — not optional optimizations.

- Head-of-line blocking means a single lost TCP segment stalls delivery of all subsequent data on that connection, which is particularly destructive for multiplexed protocols like HTTP/2.

- TCP's congestion window starts small and grows over time, so short-lived connections may never reach full link utilization — another reason persistent connections matter.

- `TIME_WAIT` sockets accumulate when short-lived connections are opened and closed rapidly to the same destination, and can exhaust ephemeral ports even when the service and network are otherwise healthy.

- TCP guarantees ordered delivery, not timely delivery — without application-level timeouts, a degraded connection can stall for seconds or minutes during retransmission backoff.

- Nagle's algorithm and delayed ACKs can interact to add ~40ms latency to small messages; setting `TCP_NODELAY` is effectively mandatory for RPC and database protocols.

- UDP does not provide reliability, ordering, or congestion control — it provides multiplexing and integrity checking, and delegates everything else to the application.

- The TCP vs. UDP decision is not "reliable vs. fast" but "are the kernel's reliability semantics the right ones for this application, or do I need different tradeoffs that I can only get by handling reliability myself?"

[← Back to Home]({{ "/" | relative_url }})
