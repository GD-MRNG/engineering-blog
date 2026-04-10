---
layout: post
title: "1.2.1 Virtual Machines and the Hypervisor Model"
author: "Glenn Lum"
date:   2026-01-21 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most engineers understand that a hypervisor "runs multiple operating systems on one machine." That sentence is accurate and almost entirely useless. It tells you nothing about *why* a VM guest running an identical workload to a bare-metal host might show 2% overhead in one benchmark and 40% in another. It does not explain why a VM can safely run untrusted code from a stranger's AWS account on the same physical CPU as yours. And it gives you no basis for reasoning about when virtualization overhead actually matters versus when it is a rounding error your team is over-indexing on. The mechanics beneath that one-sentence description are what separate "I use VMs" from "I understand what the machine is actually doing when I use them."

## The Privilege Problem That Started Everything

Operating systems expect to be in charge. When Linux boots on bare metal, the kernel runs in the CPU's most privileged execution mode — **ring 0** on x86 — where it can manipulate page tables, handle interrupts, and talk directly to hardware. Every VM guest contains a full operating system kernel that also expects ring 0 access. The fundamental problem of virtualization is: you cannot give two kernels simultaneous unrestricted access to the same physical hardware without them destroying each other.

The hypervisor's entire job is to solve this problem — to let each guest kernel *believe* it has full control of the hardware while the hypervisor retains actual control. How it accomplishes this has changed substantially over the decades, and the specific mechanism matters because it directly determines the performance overhead you pay.

## Trap-and-Emulate: The Original Mechanism

The classical approach is **trap-and-emulate**. The hypervisor runs guest kernel code at a reduced privilege level (ring 1 or ring 3 instead of ring 0). When the guest attempts a **privileged instruction** — anything that would modify hardware state, like writing to a control register or modifying page tables — the CPU generates a trap (a hardware exception). Execution transfers to the hypervisor, which inspects the instruction, emulates its intended effect on the guest's *virtual* hardware state, and returns control to the guest.

This works cleanly on architectures where every sensitive instruction is also a privileged one — meaning every instruction that could observe or modify the machine's true state will trap when executed outside ring 0. The problem is that x86 was not such an architecture. x86 had **sensitive but unprivileged instructions** — instructions that behaved differently in ring 0 versus ring 3 but did *not* trap when executed in ring 3. They just silently returned wrong results. The `POPF` instruction, for example, would quietly ignore changes to interrupt flags when called from ring 3 instead of faulting. A guest kernel executing `POPF` would think it had disabled interrupts. It had not.

This is not an obscure historical footnote. It is the reason VMware's early products had to use **binary translation** — scanning guest kernel code before execution and rewriting problematic instructions with safe equivalents. Binary translation worked, but it added latency and complexity. It is also why **paravirtualization** (the Xen approach) required modifying guest kernels to replace sensitive instructions with explicit hypervisor calls (**hypercalls**) — the guest knew it was virtualized and cooperated.

## Hardware-Assisted Virtualization: The Modern Foundation

Intel VT-x (2005) and AMD-V fundamentally changed the game by adding a new, *more* privileged execution mode below ring 0. Intel calls these **VMX root mode** (where the hypervisor runs) and **VMX non-root mode** (where the guest runs). The guest kernel runs in ring 0 of non-root mode — it genuinely executes at ring 0 privilege from its own perspective — but the CPU itself is aware of the virtualization boundary.

When the guest executes a sensitive instruction, the CPU performs a **VM exit**: it saves the guest's entire processor state into a memory structure called the **Virtual Machine Control Structure (VMCS)**, loads the hypervisor's state, and transfers control to the hypervisor. The hypervisor handles the event, then performs a **VM entry** to restore guest state and resume execution.

This is the model running underneath essentially every production hypervisor today — KVM, ESXi, Hyper-V, Xen HVM. What matters for your mental model is that a VM exit is not free. Each exit involves saving and restoring registers, flushing certain CPU pipeline state, and executing hypervisor logic. A single VM exit costs roughly 500–2000 CPU cycles depending on the processor generation and what triggered it. For workloads that trigger exits rarely (pure computation, memory-local access), overhead is near zero. For workloads that trigger frequent exits (heavy I/O, frequent system calls that touch virtualized devices), exits accumulate.

This is the direct mechanical explanation for why "VM overhead" is not a single number. It is a function of *how often your workload triggers transitions between guest and hypervisor*.

## Memory Virtualization: Two Layers of Translation

On bare metal, the OS kernel maintains **page tables** that map virtual addresses (what your process sees) to physical addresses (actual RAM locations). The hardware **Memory Management Unit (MMU)** walks these tables on every memory access.

In a virtualized environment, there is a second translation layer. The guest OS maintains page tables mapping guest virtual addresses to what it believes are physical addresses — but those are actually **guest physical addresses**, an abstraction. The hypervisor must map guest physical addresses to true **host physical addresses** (the actual RAM on the machine).

Early hypervisors handled this with **shadow page tables**: the hypervisor maintained a merged page table combining both translations, intercepting every guest page table modification to keep the shadow copy in sync. This worked but generated enormous numbers of VM exits — every time the guest updated a page table entry, the hypervisor had to intervene.

Modern CPUs solve this with **Extended Page Tables (EPT)** on Intel or **Nested Page Tables (NPT)** on AMD. The hardware MMU natively understands both levels of translation. On a TLB miss, the CPU walks the guest page table, then walks the host page table for each level of the guest walk, resolving the final host physical address. No VM exit required.

The cost is that a TLB miss is now significantly more expensive. A four-level guest page table walk where each level requires a four-level host walk means up to 24 memory accesses in the worst case, compared to 4 on bare metal. This is why **TLB pressure** is disproportionately expensive in virtualized environments. Large working sets that cause frequent TLB misses will hit this nested walk penalty repeatedly. This is also why **huge pages** (2MB or 1GB instead of 4KB) are more impactful inside VMs than on bare metal — they reduce TLB miss frequency, and each avoided miss skips an expensive nested walk.

If your team has ever seen a workload perform notably worse in a VM than bare metal despite having identical CPU and memory allocations, and the workload involves large, sparse memory access patterns — this is often the reason.

## I/O Virtualization: The Expensive Part

CPU and memory virtualization have gotten remarkably efficient. I/O is where the overhead concentrates. A guest OS expects to talk to hardware devices — a network card, a disk controller. In a VM, those devices do not exist as the guest expects them. The hypervisor has three broad strategies:

**Full device emulation** means the hypervisor presents a software model of a familiar hardware device (often a legacy one like the Intel e1000 NIC). Every register read or write from the guest triggers a VM exit, the hypervisor translates it into operations on the real host device, and returns results. This is maximally compatible — the guest needs no special drivers — and maximally slow. Each I/O operation involves multiple exits.

**Paravirtual I/O** (virtio in the Linux/KVM world, VMware's PVSCSI and VMXNET3) takes a different approach. The guest runs a driver that *knows* it is virtualized and communicates with the hypervisor through shared memory ring buffers rather than emulating hardware register access. The guest writes a batch of I/O requests into a **vring** (a shared memory descriptor ring), then performs a single notification (one VM exit) to tell the hypervisor there is work. The hypervisor processes the batch, writes completions to the ring, and injects a virtual interrupt. This amortizes the exit cost over many operations. The throughput improvement over full emulation is substantial — often 2x to 10x depending on the workload.

**Hardware passthrough** (using **SR-IOV** or VFIO) assigns a physical hardware function directly to a guest. The guest's I/O operations go directly to hardware with no hypervisor involvement on the data path. This approaches bare-metal performance but sacrifices live migration (the guest is pinned to specific hardware) and reduces the hypervisor's ability to overcommit or multiplex that device.

In practice, most cloud VM instances use paravirtual drivers, and the ones offering "enhanced networking" or "bare-metal adjacent" performance are using SR-IOV or similar passthrough under the hood. When you select an AWS instance type that advertises "ENA" (Elastic Network Adapter), you are getting a paravirtual device backed by custom hardware designed for exactly this model.

## The Type 1 and Type 2 Distinction, Mechanically

The Level 1 distinction — Type 1 runs on bare metal, Type 2 runs on a host OS — is correct but obscures what actually matters. The real question is: *what is in the critical path between a VM exit and its resolution?*

A **Type 1 hypervisor** (ESXi, Xen, Hyper-V) *is* the operating system. When a VM exit occurs, the CPU transitions directly into hypervisor code that has unmediated access to hardware. The exit-to-resolution path is short.

A **Type 2 hypervisor** (VirtualBox, VMware Workstation) runs as a process on a host OS. A VM exit still goes to the hypervisor's kernel module (this part uses the same VT-x/AMD-V hardware), but I/O handling often routes through the host OS kernel and userspace components. The resolution path is longer and shares scheduling priority with other host processes.

**KVM** blurs this line intentionally. It is a kernel module that turns the Linux kernel itself into a Type 1 hypervisor. VM exits land in kernel code (KVM module) with direct hardware access, but it reuses Linux's scheduler, memory manager, and device drivers. The QEMU userspace process handles device emulation. This is why KVM benchmarks closer to Type 1 for CPU/memory workloads but can show Type 2-like characteristics for I/O-heavy workloads where QEMU's userspace emulation is in the path. It is also why virtio matters even more with KVM — it keeps the hot path in kernel space.

## Where the Model Breaks and What It Costs

**Overcommit failures are invisible until they are catastrophic.** Hypervisors can allocate more virtual CPUs and virtual RAM to guests than physically exist, relying on the assumption that not all guests peak simultaneously. Memory overcommit uses techniques like **ballooning** (a driver inside the guest that the hypervisor tells to "inflate," forcing the guest to page internally and release memory) and **transparent page sharing** (deduplicating identical memory pages across guests). When the assumption holds, you get higher density. When it breaks — when guests actually need the memory they were promised — the hypervisor starts swapping to disk at the host level. Guest performance does not degrade gracefully. It falls off a cliff, and the guest OS has no visibility into why. The guest sees high latency on operations that should be memory-speed. This is the most common "mystery performance problem" in overcommitted virtualized environments.

**Temporal side channels exist because isolation is logical, not physical.** Guests sharing a physical CPU share caches, branch predictors, and execution units. Spectre and Meltdown demonstrated that these shared microarchitectural resources can leak information across the hypervisor boundary. Mitigations (retpolines, IBRS, L1TF flushing) have real performance costs — Intel estimated 5-30% depending on workload after initial Spectre patches. When a cloud provider says your VM is "isolated," they mean the hypervisor enforces a memory and privilege boundary. They do not mean the physical substrate is unshared, and they cannot make microarchitectural side channels fully disappear without hardware changes.

**Clock and time drift is a constant battle.** A guest OS expects to own a hardware clock. When the hypervisor deschedules a vCPU (because it is sharing a physical core), the guest's notion of elapsed time diverges from wall-clock time. This causes cascading problems: TCP retransmission timers fire incorrectly, distributed consensus protocols (Raft, Paxos) make wrong leader-election decisions, and cron jobs pile up. Hypervisors provide paravirtual clock sources (kvm-clock, Hyper-V TSC) to mitigate this, but the guest must be configured to use them. Misconfigurations here produce subtle, intermittent bugs that are notoriously difficult to diagnose.

## The Model to Carry Forward

A virtual machine is not a "lightweight simulation" of a computer. It is a real computer whose privileged operations are *intercepted* at the hardware level and *mediated* by a software layer that maintains per-guest illusions. The CPU genuinely executes guest code at near-native speed — it is not interpreting it. The cost of virtualization is concentrated almost entirely in the transitions between guest and hypervisor (VM exits) and in the second layer of memory translation (EPT/NPT walks).

This means virtualization overhead is not a flat tax. It is a function of your workload's interaction pattern with virtualized resources. Compute-bound work pays almost nothing. I/O-bound work pays based on how the I/O path is implemented. Memory-intensive work with large, sparse access patterns pays based on TLB miss rate. When someone tells you "VMs have X% overhead," the only correct response is "doing what?"

Carrying this model forward, you can now reason about container performance differences (containers skip the nested memory translation and I/O indirection entirely because they share the host kernel), about why live migration works (the hypervisor can serialize and transfer guest state because it controls the VMCS and all guest physical memory), and about where cloud instance types actually differ (not just in allocated resources but in which layers of the I/O virtualization stack they use).

## Key Takeaways

- VM overhead is not a fixed percentage — it is a function of how frequently your workload triggers VM exits and TLB misses in the nested page table structure.
- Hardware-assisted virtualization (VT-x/AMD-V) lets guest kernels run at ring 0 in a separate CPU mode, with the hardware itself enforcing the boundary — the hypervisor is not interpreting guest instructions.
- Extended Page Tables (EPT/NPT) eliminate VM exits for memory translation but make TLB misses up to 6x more expensive, which is why huge pages have disproportionate impact inside VMs.
- Paravirtual I/O (virtio) amortizes VM exit costs by batching operations through shared memory rings, and the difference versus emulated devices is often an order of magnitude in throughput.
- Memory overcommit works until it doesn't — when host-level swapping begins, guest performance degrades catastrophically with no visibility from inside the guest.
- KVM turns Linux into a hypervisor by handling VM exits in kernel space but delegates device emulation to userspace QEMU, which is why the I/O path and driver choice (virtio vs. emulated) matters more than the "Type 1 vs. Type 2" label.
- Microarchitectural side channels (Spectre, L1TF) are a fundamental consequence of sharing physical CPU resources across trust boundaries, and their mitigations carry measurable performance costs that vary by workload.
- When evaluating whether virtualization overhead matters for a specific workload, measure exit frequency and TLB miss rates — not generic benchmarks — because the overhead model is workload-shaped, not uniform.


[← Back to Home]({{ "/" | relative_url }})
