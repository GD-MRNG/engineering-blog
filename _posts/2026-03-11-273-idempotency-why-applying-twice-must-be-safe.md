---
layout: post
title: "2.7.3 Idempotency: Why Applying Twice Must Be Safe"
author: "Glenn Lum"
date:   2026-03-11 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers, when asked about idempotency in infrastructure, will say something like "it means you can run it twice and nothing bad happens." That sentence is correct the way saying "airplanes fly because of their wings" is correct — true, not useful, and dangerously incomplete when you need to debug why something went wrong at altitude. The real question is not *whether* an operation is idempotent. It is *what specific mechanism makes it idempotent*, which operations quietly violate that mechanism even inside tools that claim to provide it, and what actually happens to your infrastructure when idempotency breaks halfway through an apply. That is where the failures live, and it is where most practitioners have a gap.

## The Mathematical Property and the Operational Reality

Idempotency has a precise mathematical definition: an operation *f* is idempotent if applying it twice produces the same result as applying it once. Formally, *f(f(x)) = f(x)*. Setting a value to 5 is idempotent — do it ten times and you still have 5. Incrementing a value by 1 is not — do it ten times and you have shifted by 10.

This is useful as a foundation, but infrastructure operations are not pure functions. They execute against remote systems with latency, partial failure, concurrent actors, and side effects. The property you actually need is not the mathematical one. It is the operational one: **re-applying the same infrastructure definition to the same environment must converge to the same end state regardless of how many times you apply it, and without creating duplicate resources, corrupted configurations, or unintended side effects.** That is a much harder property to guarantee, and understanding how tools attempt to guarantee it — and where they fail — is the substance of this post.

## The Read-Diff-Apply Loop

Declarative IaC tools achieve idempotency through a single core mechanism. Every tool in this category — Terraform, Pulumi, CloudFormation, Crossplane — implements some version of the same loop:

**Read** the current state of the infrastructure. This might come from the state file, from a live API query to the cloud provider, or both. The tool needs to know what exists right now.

**Diff** the current state against the desired state declared in your configuration files. For every resource, the tool asks: does this resource exist? If it exists, do its attributes match what the configuration says they should be? If it does not exist, it needs to be created.

**Apply** only the changes necessary to close the gap. If a resource exists and matches, the tool does nothing — this is the **no-op** path, and it is where idempotency lives. If a resource exists but its attributes differ, the tool updates it in place or destroys and recreates it. If a resource does not exist, the tool creates it.

This loop is why running `terraform apply` twice in a row with no configuration changes produces no infrastructure changes on the second run. The read phase finds everything already matches, the diff is empty, and there is nothing to apply. That is not magic. That is the direct mechanical consequence of comparing desired state to current state and only acting on the delta.

The critical insight: **idempotency in declarative IaC is not a property of the apply step. It is a property of the entire loop.** If the read is wrong, or the diff is wrong, or the apply has side effects the tool does not track, idempotency breaks — even though the tool is still "declarative."

## What the State File Actually Does for Idempotency

The Level 1 post covered state management from an operational perspective. Here is why the state file is specifically load-bearing for idempotency.

When Terraform creates an AWS EC2 instance, the cloud provider returns an instance ID — say, `i-0a1b2c3d4e5f`. Terraform writes that ID into the state file, binding the logical resource in your configuration (`aws_instance.web`) to the physical resource in the real world (`i-0a1b2c3d4e5f`). On the next apply, Terraform does not ask AWS "is there an instance that matches this configuration?" It asks "what is the current state of `i-0a1b2c3d4e5f`?" and compares the answer to your configuration.

This binding is what prevents duplicate resource creation. Without it, the tool has no way to distinguish between "this resource does not exist yet and needs to be created" and "this resource exists but I have lost track of it." Lose the state file, and your next apply will attempt to create every resource from scratch — colliding with the existing infrastructure, creating duplicates, or failing on uniqueness constraints depending on the resource type and provider.

This also explains why **importing** existing infrastructure into state is not just an operational convenience — it is a prerequisite for idempotent management of resources that were created outside the tool. Until a resource is tracked in state, the tool cannot perform the read-diff-apply loop against it.

## Why Specific Operations Are Not Naturally Idempotent

Not all infrastructure operations fit cleanly into the declarative convergence model. Understanding which ones resist idempotency and why is essential.

**Resource creation with server-generated values.** When you create a resource, the provider often generates values that become part of the resource's identity: randomly assigned IPs, auto-generated names, UUIDs. If the creation succeeds but the state file write fails (network error, process killed, state lock timeout), you have a resource that exists in the real world but is not tracked. The next apply sees the resource as missing from state and attempts to create it again. This is the **orphaned resource** problem, and it is the most common way idempotency breaks in practice.

**Operations with external side effects.** Consider a Terraform resource that provisions an AWS RDS database. The database creation itself is idempotent through the state-tracking mechanism. But if your configuration also uses a `provisioner` block to run a SQL script that seeds initial data, that script runs every time the resource is created. If the resource gets tainted and recreated, the script runs again. If the script is not itself idempotent (e.g., it uses `INSERT` rather than `INSERT ... ON CONFLICT DO NOTHING`), your second apply corrupts your data. The IaC tool's idempotency does not extend to the code it shells out to.

**Append-only or cumulative operations.** Some cloud resources have attributes that accumulate rather than converge. Adding an inline IAM policy statement, appending a CIDR block to a security group rule list, or adding a tag — if the tool models these as "add this item" rather than "ensure this exact set exists," repeated application grows the list. Most mature providers model these correctly as the full desired set, but edge cases exist, particularly with less-maintained providers or modules that use imperative escape hatches.

**`null_resource` and local-exec provisioners.** These are explicit escape hatches from the declarative model. A `null_resource` with a `local-exec` provisioner runs an arbitrary shell command. The tool has no way to determine whether the effect of that command already exists. It runs it every time (or when triggered). Idempotency of these operations is entirely your responsibility.

```hcl
resource "null_resource" "run_migration" {
  triggers = {
    schema_version = var.schema_version
  }
  provisioner "local-exec" {
    command = "python run_migrations.py --version ${var.schema_version}"
  }
}
```

If `run_migrations.py` is not itself idempotent, this resource is a landmine in your pipeline. The IaC tool has no opinion about what that script does. It runs it when the trigger changes. Everything beyond that is on you.

## The Partial Apply Problem

Idempotency is often discussed as if applies are atomic — they either fully succeed or fully fail. They are not. A `terraform apply` that provisions fifteen resources might succeed on the first twelve and fail on the thirteenth. You now have a partially applied state. The state file reflects the twelve resources that were created. Your configuration declares fifteen.

The next apply picks up from where it failed: it sees the twelve resources exist and match (no-op), and attempts to create the remaining three. **This is idempotency working correctly under partial failure** — and it is one of the most practically important properties of the state-tracking model. The tool does not re-create the first twelve resources. It converges toward the full desired state.

But this only works because the state file was updated incrementally as each resource was created. If the state file update fails (the state backend is unavailable, the lock is broken), you get a divergence between the state file and reality. The tool thinks the resource does not exist; the cloud provider knows it does. Now your next apply will either fail with a conflict or, worse, create a duplicate.

This is why state locking is not an operational nicety. **State locking is a correctness requirement for idempotency.** Without it, two concurrent applies can each read the same initial state, each decide to create the same resource, and produce duplicates that neither state file knows about.

## Idempotency at the Pipeline Level

Individual resource-level idempotency is necessary but not sufficient. In a real IaC pipeline, you often have multiple stages: perhaps one that provisions networking, another that provisions compute, another that configures DNS. Each stage might be idempotent in isolation, but the pipeline as a whole has ordering dependencies.

If stage two fails and you re-run the entire pipeline, stage one runs again. If stage one is truly idempotent, this is a no-op and the pipeline proceeds to retry stage two. If stage one has any non-idempotent side effects — say, it rotates an API key as part of its apply — then re-running the pipeline from the top invalidates the work that stage two partially completed in its first attempt. You now have infrastructure that references a key that no longer exists.

**Pipeline-level idempotency requires that every stage is idempotent, and that the side effects of each stage do not invalidate the completed work of downstream stages on re-execution.** This is a design constraint that must be intentional. It does not emerge automatically from using declarative tools.

## Where Drift Breaks the Contract

Idempotency assumes that the tool's model of reality is accurate. Configuration drift — changes made outside the tool — breaks this assumption. If someone manually changes a security group rule through the AWS console, the state file still reflects the old rule. On the next apply, the tool's diff will detect the discrepancy and attempt to revert the manual change back to the declared state. This is actually idempotency working as intended — the system converges to the declared state.

But it is only safe if the declared state is actually correct. If the manual change was a critical hotfix for an active incident, reverting it automatically could re-open the vulnerability. The tool is not wrong — it is doing exactly what it was designed to do. The failure is in the process that allowed a change to be made outside the tool without updating the configuration. This is a human-systems problem that the tool's idempotency guarantee actively surfaces rather than hides.

## The Mental Model

Idempotency in infrastructure is not a feature you get for free by choosing a declarative tool. It is the emergent property of a correctly functioning read-diff-apply loop. The loop requires three things to hold: the tool must accurately know current state (the read), it must correctly compute the difference against desired state (the diff), and the operations it executes must not produce effects outside what the tool tracks (the apply). When any of these break — lost state, concurrent modification, untracked side effects, imperative escape hatches — idempotency degrades.

The practical question to carry into every IaC design decision is not "is this tool idempotent?" but "**does every operation in this pipeline preserve the read-diff-apply loop?**" Any provisioner, any external script, any manual change, any untracked side effect is a place where the loop can break. Idempotency is not binary. It is the degree to which your entire system — tool, configuration, pipeline, and operational discipline — maintains the integrity of that loop.

## Key Takeaways

- Idempotency in IaC is mechanically produced by the read-diff-apply loop: read current state, diff against desired state, apply only the delta — which makes a second apply a no-op when nothing has changed.

- The state file is the binding between logical resources in your configuration and physical resources in the real world; losing it breaks the tool's ability to distinguish "needs to be created" from "already exists," which directly breaks idempotency.

- State locking is not an operational convenience — it is a correctness requirement, because concurrent applies against the same state can produce duplicate resources that neither run tracks.

- Provisioners, `local-exec` blocks, and arbitrary scripts are escape hatches from the declarative model, and their idempotency is entirely your responsibility — the tool cannot verify or enforce it.

- Partial applies are the normal failure mode in infrastructure operations; idempotency means the next apply picks up where the last one failed, but only if the state file accurately reflects what was actually created.

- Pipeline-level idempotency requires more than idempotent stages — it requires that re-running an earlier stage does not invalidate the completed work of later stages through side effects like key rotation or credential regeneration.

- Configuration drift does not break idempotency — it triggers convergence back to declared state, which is only safe if the declared state is actually the correct state, making out-of-band changes a process problem that the tool will faithfully enforce.

- The right question is never "is this tool idempotent?" but "does every operation in this pipeline preserve the integrity of the read-diff-apply loop?"

[← Back to Home]({{ "/" | relative_url }})
