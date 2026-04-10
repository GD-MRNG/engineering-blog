---
layout: post
title: "1.2.2 Containers: Namespaces, cgroups, and the Isolation Model"
author: "Glenn Lum"
date:   2026-01-22 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most engineers work with containers daily and understand them as "lightweight, isolated environments for running applications." That understanding is sufficient for pulling images and writing Dockerfiles, but it breaks down the moment you need to answer harder questions: Why can a process inside a container sometimes see the host's process tree? Why does a container with no memory limit set consume all available host memory and get killed? Why is a container escape a fundamentally different class of vulnerability than a VM escape? The answers live in the actual kernel mechanics underneath the container abstraction — mechanics that most practitioners have never had reason to examine. Without them, you're operating containers on faith rather than understanding, and faith is a poor foundation for security and reliability decisions.

## A Container Is a Process, Not a Machine

The single most important conceptual shift is this: a container is not a lightweight virtual machine. A VM runs a full guest operating system on emulated or virtualized hardware, with its own kernel. A container is a **regular Linux process** (or group of processes) that the host kernel has been told to lie to.

When you run `docker run nginx`, the Docker daemon asks the kernel to start a process with specific isolation constraints applied. The nginx process runs directly on the host kernel, uses the host's CPU scheduler, and makes syscalls to the same kernel as every other process on the machine. There is no guest kernel. There is no hypervisor. The "isolation" comes from the kernel selectively restricting what the process can see and how much it can consume.

Two kernel subsystems do the heavy lifting: **namespaces** control visibility (what the process can see), and **cgroups** control resources (what the process can consume). Everything else — union filesystems, capability dropping, seccomp filters — is layered on top of these two primitives.

## Namespaces: The Visibility Boundary

A **namespace** wraps a global system resource in an abstraction that makes it appear to the processes inside the namespace that they have their own isolated instance of that resource. The host kernel maintains the real, global state; namespaces provide filtered views of it.

Linux currently implements eight namespace types. The ones doing the most work in container isolation are these:

### PID Namespace

Each container gets its own PID namespace. The first process started inside the container sees itself as PID 1. It and its children see a process table that contains only processes in their namespace. From the host's perspective, these are ordinary processes with ordinary host-level PIDs — the container's PID 1 might be PID 48372 on the host. The kernel maintains a mapping between the two views.

This is why `ps aux` inside a container shows only that container's processes, while the same command on the host shows everything, including all container processes. The isolation is cosmetic from the kernel's perspective, but operationally meaningful: processes in one container cannot send signals to processes in another container by default, because they can't address them.

### Mount Namespace

Each container gets its own view of the filesystem hierarchy. When a container runtime sets up a container, it creates a new mount namespace, mounts the container image's filesystem as the root (`/`), and mounts specific paths like `/proc` and `/dev` with appropriate filtering. The container process sees its image's filesystem as the entire world.

This is where **union filesystems** (OverlayFS being the most common) enter the picture. A container image is composed of stacked read-only layers. The runtime adds a thin writable layer on top. When a process in the container reads a file, OverlayFS searches downward through the layers until it finds the file. When a process writes, the write goes to the top writable layer using a **copy-on-write** strategy — the original layer is untouched, and a modified copy is placed in the writable layer. This is how multiple containers can share the same base image layers in memory and on disk while each maintaining their own modifications. It's also why container filesystems are ephemeral by default: the writable layer is discarded when the container stops.

### Network Namespace

Each container gets its own network stack: its own interfaces, its own routing table, its own iptables rules, its own port space. This is why two containers can both bind to port 80 without conflict — they each have their own port 80 in their own network namespace.

The container runtime creates a **veth pair** — a virtual ethernet cable with one end inside the container's network namespace and the other end attached to a bridge on the host. Traffic from the container traverses this virtual link to the host bridge, where the host's network stack routes it. This is the machinery behind Docker's default bridge networking, and it's why container-to-container networking has slightly higher latency than host networking — packets cross the veth pair and the bridge, adding a few microseconds of overhead.

### UTS, IPC, and User Namespaces

The **UTS namespace** gives each container its own hostname. The **IPC namespace** isolates System V IPC resources and POSIX message queues, preventing one container from accessing another's shared memory segments. The **user namespace** is the most security-relevant of the three: it allows mapping UID 0 (root) inside the container to an unprivileged UID on the host, so a process that believes it's running as root inside the container has no root privileges if it escapes to the host.

User namespaces are powerful but historically underused. Many container runtimes ran containers as real root on the host for years because user namespace support was immature and introduced compatibility issues with volume mounts and certain syscalls. This is improving, and **rootless containers** — where the entire container runtime runs without host root privileges — are now viable in both Docker and Podman. But the default configuration in many production environments still maps container root to host root, which matters enormously for security.

## Cgroups: The Resource Boundary

If namespaces are about what a process can *see*, **cgroups** (control groups) are about what a process can *use*. Cgroups allow the kernel to allocate, limit, and account for CPU, memory, I/O bandwidth, and other resources on a per-process-group basis.

When a container runtime starts a container, it creates a cgroup for that container's processes and writes resource constraints into the cgroup's control files. These are literal files in a virtual filesystem (typically mounted at `/sys/fs/cgroup`).

### CPU Constraints

CPU limits in cgroups work through the **Completely Fair Scheduler (CFS) bandwidth control**. When you set a container to 0.5 CPU, the runtime translates this into a quota and period: for example, 50ms of CPU time per 100ms period. If the container's processes exhaust their 50ms quota within a period, the kernel **throttles** them — they are descheduled and cannot run until the next period begins.

This throttling is invisible from inside the container. The process doesn't receive a signal or an error. It simply stops getting scheduled. From the process's perspective, the CPU just got very slow. This is why CPU throttling can cause latency spikes that are extremely difficult to diagnose from application-level metrics alone — the application doesn't know it's being throttled, it just sees operations taking longer than expected. Tools like `cat /sys/fs/cgroup/cpu/cpu.stat` (cgroups v1) or the `nr_throttled` and `throttled_time` fields reveal what's actually happening.

### Memory Constraints

Memory limits are enforced hard. When a container's processes collectively exceed the cgroup's memory limit, the kernel invokes the **OOM killer** and terminates a process in the cgroup. There is no graceful degradation, no swap-to-disk by default, no warning. The process is killed with SIGKILL.

This creates a critical operational distinction: a container without a memory limit set can consume all available host memory, potentially starving other containers and system processes. A container with a memory limit set will be killed when it exceeds that limit. Neither failure mode is good, but only the second one is *contained* — the blast radius is limited to the offending container rather than the entire host.

A common operational mistake is setting memory limits equal to memory requests (common in Kubernetes) without understanding that this creates a system with zero headroom. A brief memory spike — a large request, a garbage collection pause, a burst of log buffering — triggers an OOM kill rather than being absorbed by available memory.

### Cgroups v1 vs. v2

Cgroups v1 uses a per-resource hierarchy — CPU, memory, and I/O each have separate directory trees, and a process can be in different groups for different resources. Cgroups v2 unifies this into a single hierarchy where each process belongs to exactly one group, and all resource controllers apply to that group. V2 also adds **Pressure Stall Information (PSI)**, which provides metrics on how much time processes spend waiting for CPU, memory, or I/O resources — a much more actionable signal than raw utilization numbers. Most modern distributions and container runtimes have migrated to v2, but v1 compatibility layers persist in many production environments.

## What `docker run` Actually Does

To make this concrete: when you execute `docker run -it --memory=512m --cpus=1 ubuntu /bin/bash`, the following sequence occurs. The Docker daemon instructs the container runtime (typically `runc`) to create a new process. Before executing `/bin/bash`, `runc` calls `clone()` with flags requesting new PID, mount, network, UTS, IPC, and user namespaces. It then sets up the mount namespace by mounting the ubuntu image's layers via OverlayFS at the container's root. It configures the network namespace by creating a veth pair and attaching one end to the Docker bridge. It creates a new cgroup, writes `512m` to the memory limit file and the appropriate CFS quota for one CPU to the CPU control files, and places the new process into that cgroup. It drops Linux capabilities the container shouldn't have, applies a default seccomp profile that blocks approximately 44 dangerous syscalls, and finally calls `exec` to replace the setup process with `/bin/bash`.

The result is a process that believes it is PID 1 on its own machine, with its own filesystem, its own network, and its own hostname. But it is one process on the host, governed by the host kernel, constrained by cgroup limits, and visible in the host's process table to anyone with access.

## The Shared Kernel Boundary and Its Consequences

The performance advantage of containers comes directly from their architecture: no hardware emulation, no second kernel, no boot sequence. A container starts in milliseconds because it's just a process fork with some namespace and cgroup setup. You can run hundreds of containers on a single host because they share the kernel and the base OS libraries (via image layer deduplication).

But sharing the kernel is also the fundamental security limitation. Every container on a host makes syscalls to the same kernel. A kernel vulnerability is a vulnerability for every container on that host. A **container escape** — where a process breaks out of its namespace constraints and gains access to the host — is a kernel-level exploit. This is categorically different from a VM escape, which requires breaking through a hypervisor that provides hardware-level isolation.

This is why defense in depth matters for containers: seccomp profiles restrict which syscalls a container can make, capability dropping removes dangerous Linux capabilities like `CAP_SYS_ADMIN`, and AppArmor or SELinux profiles constrain file and network access patterns. Each layer reduces the attack surface independently. In practice, many production deployments run with default seccomp profiles and no mandatory access control, which means they're relying entirely on namespace isolation — the thinnest layer.

Another consequence of the shared kernel: `/proc` and `/sys` inside a container expose host-level information by default. Files like `/proc/meminfo` report the *host's* total memory, not the cgroup's limit. An application that reads available memory from `/proc/meminfo` to size its heap or thread pool will make decisions based on the host's 64GB of RAM, not the 512MB the container is actually allowed to use. This is the source of a large category of OOM kills in containerized Java, Python, and Node.js applications. The **LXCFS** project and runtime-level patches address this by intercepting reads to these files and returning cgroup-aware values, but it's not universal.

## The Mental Model

Think of a container as a process in a box. The box has tinted windows (namespaces) that control what the process can see — its own PID tree, its own filesystem, its own network stack. The box has a meter (cgroups) that enforces a strict budget on CPU time, memory, and I/O. But the floor of the box is the host kernel. Every container on the machine stands on the same floor. The box is strong enough to isolate well-behaved processes from each other, and with proper hardening (seccomp, capability dropping, user namespaces), it can resist many deliberate escape attempts. But it is not a separate machine. The isolation is constructed from policies enforced by a shared kernel, not from physical or virtual hardware boundaries.

This is the reasoning framework you need before building anything on containers: the speed and density come from the shared kernel, and so do the security constraints. Every operational decision — whether to run as root, whether to set resource limits, whether to apply seccomp profiles, whether to use a VM-level isolation boundary like Firecracker or gVisor for untrusted workloads — follows from understanding where the box is strong and where the floor is exposed.

## Key Takeaways

- A container is a regular Linux process with namespace and cgroup constraints applied by the host kernel; there is no guest kernel, no hypervisor, and no hardware emulation.
- Namespaces control visibility — what a process can see (its own PID tree, filesystem, network stack, hostname) — while cgroups control resources — what a process can consume (CPU time, memory, I/O bandwidth).
- CPU throttling is invisible to the throttled process; it manifests as unexplained latency spikes that are only visible through cgroup-level metrics like `nr_throttled` and `throttled_time`.
- A container without explicit memory limits can consume all host memory; a container with memory limits is OOM-killed without warning when it exceeds them. Neither is safe by default — both require deliberate configuration.
- `/proc/meminfo` and similar files inside a container report host-level values, not cgroup limits, which causes applications to over-allocate memory and get OOM-killed.
- The shared kernel is both the source of containers' performance advantage and their fundamental security boundary — a kernel exploit compromises every container on the host.
- Running containers as root inside the container typically means root on the host unless user namespaces are explicitly configured; most production defaults still map container root to host root.
- For workloads running untrusted code, namespace isolation alone is insufficient — VM-level isolation (Firecracker, gVisor) or aggressive seccomp and capability restriction is necessary to compensate for the shared-kernel attack surface.

[← Back to Home]({{ "/" | relative_url }})
