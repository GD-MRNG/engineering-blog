---
layout: post
title: "2.7.4 The Plan/Apply Cycle: Preview as a Safety Mechanism"
author: "Glenn Lum"
date:   2026-03-12 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers treat the plan step as a preflight check — a gate that answers "is this going to work?" That framing misses the point. The plan step does not tell you whether an operation will succeed. It tells you what the operation intends to do, and there is an enormous difference between those two things. A plan can show a clean, valid set of changes that will still destroy your production database if you didn't realize a rename forces a resource replacement. The plan was accurate. The operator's reading of it was not. Understanding the mechanics of how a plan is generated — what inputs it reads, what comparisons it makes, what its output actually encodes — is what turns the plan step from a rubber stamp into the primary risk management tool for infrastructure changes.

## The Three Inputs to a Plan

A plan is a diff, but it is not a simple two-way diff between "old config" and "new config" the way a `git diff` works. It is a **three-way reconciliation** between three distinct sources of truth:

**The desired state** is what your configuration files declare. This is the set of `.tf` files (in Terraform's case), the CloudFormation template, the Pulumi program — whatever declarative definition you have written. It represents what you want the infrastructure to look like.

**The state file** is the IaC tool's last known record of what it believes the infrastructure looks like. The Level 1 post covered state management. What matters here is that the state file is not a live view. It is a snapshot from the last time the tool successfully applied changes or explicitly refreshed. It can be stale.

**The real infrastructure** is what actually exists in the target environment right now. The plan step queries the cloud provider APIs (or whatever backend manages the resources) to determine the current state of each resource the tool is tracking.

The plan algorithm works roughly like this: first, refresh the state file by reading the real infrastructure. Then, compare the refreshed state to the desired state declared in configuration. For every resource, determine what action (if any) is needed to move from current to desired. The output is the set of those actions.

This three-way model is why a plan can surface changes you did not make. If someone manually modified a security group rule through the AWS console, the refresh step will detect the discrepancy between the state file and reality, and the plan will show a change to bring that resource back in line with your declared configuration. You changed nothing in your config. The plan still shows a diff. This is not a bug — it is the tool doing exactly what it should: resolving drift.

## The Refresh Step and Why It Costs Money

The refresh is the most mechanically expensive part of a plan. For every resource tracked in your state file, the tool makes an API call to the cloud provider to read the resource's current attributes. If your state file tracks 500 resources, that is at minimum 500 API calls before the diff computation even starts.

This has practical consequences. Plans against large state files are slow — sometimes minutes. They can hit API rate limits, especially in AWS accounts that are already under heavy automation load. And because the refresh reads every tracked resource, it can fail if a resource has been deleted outside of the tool's knowledge, or if the credentials being used lack read permissions on a resource that was provisioned by a different role.

Terraform exposes a `-refresh=false` flag that skips this step and plans against the stale state file. This is faster but dangerous: you are now computing a diff against what the tool last saw, not what actually exists. If someone manually deleted a resource, the plan will not know. If someone manually changed a resource's attributes, the plan will not account for it. The resulting apply can fail or, worse, produce unexpected results. The flag exists for speed in CI pipelines where you have high confidence nothing has changed externally, but using it as a default is trading safety for convenience.

## The Action Taxonomy: What a Plan Actually Proposes

Every resource in a plan output gets one of a small number of action designations. Understanding these is not optional — they encode the risk profile of the entire operation.

**Create** (`+`): A resource exists in configuration but not in state. The tool will provision it. Risk is generally low — you are adding something new, not touching anything existing.

**Update in-place** (`~`): A resource exists in both configuration and state, but some attributes differ. The tool will modify the existing resource. Risk depends entirely on what is being changed. Updating a tag is trivial. Updating a security group's ingress rules is operationally significant. The plan output shows which specific attributes are changing, and reading those attributes is where the real risk assessment happens.

**Destroy** (`-`): A resource exists in state but not in configuration. The tool will delete it. This is where blast radius becomes real. Deleting a resource might seem contained, but if other resources depend on it — instances in a subnet, records in a DNS zone — the cascading effects can be severe.

**Replace** (destroy then create, or create then delete): This is the action that catches people off guard. Some attribute changes on some resource types cannot be applied in-place. The cloud provider's API does not support modifying that attribute on a live resource. The only path is to destroy the existing resource and create a new one with the updated attributes. In Terraform's plan output, this shows as a resource being both destroyed and created, often annotated with `# forces replacement` next to the specific attribute that triggered it.

Replace is where the most dangerous plan misreadings happen. An engineer changes an EC2 instance's AMI ID, expecting an in-place update. The plan shows a replacement. If the engineer does not read the plan carefully, they approve what is functionally a full instance teardown and rebuild — losing any ephemeral state, changing the private IP, disrupting active connections. The plan told them exactly what would happen. They just did not parse the output.

```
# aws_db_instance.main must be replaced
-/+ resource "aws_db_instance" "main" {
      ~ engine_version = "14.7" -> "15.3" # forces replacement
      ~ id             = "mydb-abc123" -> (known after apply)
        name           = "production"
        # ... other attributes unchanged
    }
```

That `-/+` prefix is the signal. The `# forces replacement` annotation tells you which attribute caused it. For a database, this means the existing instance is destroyed and a new one is created. If you are not restoring from a snapshot in the new configuration, your data is gone.

## The Dependency Graph and Change Cascades

Resources in an IaC configuration are not isolated. They form a **dependency graph** — the VPC must exist before the subnet, the subnet before the instance, the instance before the DNS record pointing to it. The plan respects this graph when computing the order of operations.

This matters for risk assessment because a single change to a foundational resource can cascade. If the plan shows that a VPC is being replaced, every resource that depends on that VPC is also being replaced: subnets, route tables, security groups, instances, load balancers, NAT gateways. The plan will show all of these changes, but if you are scanning quickly, you might see the VPC replacement and miss that it implies rebuilding your entire network stack.

The dependency graph also determines parallelism during apply. Resources with no dependency relationship to each other can be created or modified concurrently. This means that a plan with 30 resource changes might execute much faster than you expect, but it also means failures can be partial — the apply might succeed on some branches of the graph and fail on others, leaving your infrastructure in a state that matches neither the old configuration nor the new one.

## Reading a Plan for Risk

A plan output is not a checklist to approve. It is a risk assessment document. The skill of reading a plan is pattern-matching for signals of high blast radius:

**Resource count.** A plan that touches 3 resources is categorically different from one that touches 150. If you expected a small change and the plan shows dozens of modifications, something is wrong — either your change has unexpected dependencies, or drift has accumulated.

**Replaces and destroys on stateful resources.** Any replacement of a database, a persistent volume, or a storage bucket should trigger deep review. These are resources where destruction means data loss.

**Changes to identity-bearing attributes.** If the plan modifies a resource's name, ARN, or unique identifier, downstream resources that reference that identity may break — even ones not managed by the same IaC configuration.

**The `(known after apply)` marker.** Some attribute values cannot be computed until the resource actually exists — like an IP address assigned by the cloud provider. When the plan shows this marker on an attribute that other resources reference, it means the plan is making assumptions about the apply-time resolution. Most of the time this is fine. When it is not fine, you will not know until apply.

## Where Plan Fails to Protect You

The plan step has real limits, and overconfidence in it causes real incidents.

**The time-of-check to time-of-use gap.** A plan is computed at a point in time. Between the moment you run `plan` and the moment you run `apply`, the real infrastructure can change. Another engineer applies their own changes. An autoscaler adds instances. A cloud provider modifies a resource's attributes as part of maintenance. The apply operates on the assumption that the world still looks like it did during the plan. If it doesn't, the apply can fail partway through or produce unexpected results. Terraform partially mitigates this by re-reading resource state during apply, but it does not re-run the full plan — it will attempt the planned actions even if the preconditions have shifted.

**Provider-level validation gaps.** The plan computes a diff based on the resource schema known to the provider plugin. It does not execute the cloud API call. This means it cannot catch errors that only the API would catch: invalid parameter combinations, quota limits, permission denials on specific operations, or regional service availability. You can get a perfectly clean plan and have the apply fail on the first resource because your account hit its VPC limit.

**Cross-state blind spots.** Most real infrastructure is split across multiple state files (by team, by environment, by service). A plan only considers the resources in its own state. If your change modifies a shared resource — say, a DNS zone entry that another team's service also depends on — the plan has no mechanism to warn you about the cross-boundary impact. The blast radius extends beyond what the plan can see.

**The false confidence loop.** The most insidious failure mode is cultural. Teams that have run plan-and-apply hundreds of times without incident start reviewing plans less carefully. The plan becomes a formality — glance at the resource count, approve. This is when the dangerous change gets through. Plan review is a skill that degrades without deliberate practice, and the consequences of a missed signal are asymmetric: you review a hundred plans correctly and nothing happens, you miss one and an outage occurs.

## The Mental Model

Think of the plan step as a structured, machine-generated risk disclosure — not a guarantee. It tells you the tool's intent: what it will try to create, modify, destroy, and replace, based on the three-way diff between your configuration, its last known state, and the live infrastructure. It is comprehensive within its scope and blind outside of it.

The critical conceptual shift is understanding that the plan is not asking you "should I proceed?" It is telling you "here is what I will do" and asking you "is this what you meant?" Answering that question correctly requires understanding the action taxonomy, recognizing which resources are stateful, knowing which attribute changes force replacements, and being alert to unexpectedly large diffs that signal drift or dependency cascades. The plan cannot protect you from changes you approve without understanding.

## Key Takeaways

- A plan is a three-way diff between your declared configuration, the tool's recorded state, and the live infrastructure — not a two-way diff between old and new config.

- The refresh step queries every tracked resource via API before computing the diff, which is why plans on large state files are slow and why skipping refresh trades safety for speed.

- Replace actions (destroy-then-create) are the highest-risk operations in a plan because they can cause data loss on stateful resources, and they are triggered by attribute changes that cannot be applied in-place.

- Changes to foundational resources cascade through the dependency graph — a single VPC replacement can imply the destruction and recreation of every resource inside it.

- The plan cannot catch errors that only the cloud API would surface at apply time: quota limits, permission denials, invalid parameter combinations, and service availability constraints.

- A clean plan does not guarantee a clean apply because the infrastructure can change between plan and apply (the time-of-check to time-of-use gap).

- Plans are scoped to a single state file and cannot warn you about cross-boundary impacts on resources managed in separate states.

- The most common plan-related incident is not a tool failure — it is an engineer approving a plan they did not read carefully enough, particularly one containing unexpected replacements of stateful resources.

[← Back to Home]({{ "/" | relative_url }})
