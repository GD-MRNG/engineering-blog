---
layout: post
title: "2.7.6 Drift Detection: When Reality Diverges from Code"
author: "Glenn Lum"
date:   2026-03-14 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most teams adopt Infrastructure as Code believing it solves configuration drift. It does not. IaC gives you a mechanism for *detecting* drift and a mechanism for *correcting* it. But it has no ability to prevent drift from occurring. Your cloud provider does not know or care that you use Terraform, Pulumi, or CloudFormation. It exposes an API. Anyone with credentials—a developer in the console, a script in a CI pipeline, an incident responder using the CLI at 3 AM—can call that API and change your infrastructure. When they do, your IaC codebase and your actual infrastructure are no longer the same thing, and your IaC tool will not know this until someone explicitly asks it to check. Understanding exactly how that check works, what it can and cannot see, and how drift compounds when left unattended is the difference between an IaC practice that provides real control and one that provides the illusion of it.

## The Three-Way Comparison

The central mechanic behind drift detection is a **three-way comparison** between three distinct representations of your infrastructure:

**Desired state** is what your code declares. This is the `.tf` files, the Pulumi program, the CloudFormation template—whatever definition files you have committed to version control. It says: "There should be a VPC with this CIDR range, a security group with these rules, an RDS instance with this engine version."

**Stored state** is what the IaC tool believes reality looks like, based on the last time it interacted with the cloud provider. In Terraform, this is the state file. In CloudFormation, AWS maintains this internally as the stack's recorded resource states. The stored state is a snapshot—it represents reality as of the last successful apply or refresh, not reality right now.

**Actual state** is the real, current configuration of the resources as reported by the cloud provider's API. This is the ground truth.

Every plan operation involves reconciling all three. The tool cannot simply compare code to stored state, because stored state might be stale. It cannot compare code directly to actual state, because it needs stored state to know *which* real-world resources correspond to which declarations in the code. The stored state is the mapping layer: it holds the resource IDs that link a block in your code to a specific object in your cloud account.

## How a Plan Operation Actually Executes

When you run `terraform plan`, the sequence is concrete and worth understanding step by step.

First, Terraform reads your code and constructs a resource graph—the full set of resources you have declared, including their dependencies. Then it reads the state file to get the list of resources it currently tracks, along with their cloud provider resource IDs and the last-known attribute values for each.

Next comes the **refresh phase**. For every resource in the state file, Terraform makes an API call to the cloud provider: "Describe this security group. Describe this RDS instance. What are the current attributes of this S3 bucket?" The responses come back with the actual, current configuration of each resource. Terraform now holds the actual state in memory alongside the stored state.

Now Terraform performs two comparisons. It compares the refreshed actual state against the desired state declared in code. Every difference between these two becomes a line item in the plan output. If your code says the security group should allow inbound traffic on port 443 and the actual security group also allows port 22 (because someone added it through the console), the plan will show that port 22 rule being removed. If your code says the RDS instance should be `db.t3.medium` and someone scaled it up to `db.t3.large` through the console, the plan will show it being scaled back down.

The plan output is, in effect, a drift report fused with an intent report. It shows you both what has changed outside your control and what you have intentionally changed in your code, combined into a single set of proposed actions. This is powerful and dangerous in equal measure—because it does not visually distinguish between "reverting someone's emergency fix" and "applying your new feature."

### The Refresh Flag and Its Consequences

Terraform allows you to skip the refresh phase entirely with `terraform plan -refresh=false`. This compares your code against the stored state only, ignoring what has actually happened in the real world since the last apply. This is faster—significantly so when you manage thousands of resources, because it eliminates thousands of API calls—but it makes you blind to drift. Plans generated without refresh can propose changes that conflict with the current actual state of the infrastructure, and in some cases can produce destructive outcomes because the tool is operating on stale information.

## What Drift Detection Cannot See

This is where the model has a critical boundary that is easy to miss.

Your IaC tool can only detect drift on resources it tracks. If someone creates a new EC2 instance through the console, Terraform does not know about it. It is not in the state file. It will never appear in a plan. It will never be flagged. It simply exists outside the tool's field of vision.

This category of drift—**unmanaged resources**—is in many environments the more dangerous kind. Managed resources that drift will at least surface on the next plan. Unmanaged resources are invisible indefinitely. A security group created by hand, an IAM role provisioned by a one-off script, a DNS record added through the console during an incident—none of these will ever appear in a Terraform plan unless someone explicitly imports them into the state file.

There is a second blind spot. Some resource attributes are not returned by cloud provider APIs, or are returned inconsistently. Terraform's AWS provider, for example, cannot detect drift on certain nested block configurations within some resources because the AWS API does not round-trip those values reliably. The provider's documentation sometimes notes these cases; often it does not. The practical consequence is that drift detection coverage is not uniform—some attributes are tightly tracked, others are effectively invisible.

A third blind spot: resources with **lifecycle rules** that tell the tool to ignore certain changes. In Terraform, you might write:

```hcl
lifecycle {
  ignore_changes = [tags]
}
```

This is an intentional instruction to skip drift detection on that attribute. Teams use this as a workaround when external systems (auto-scaling policies, automated tagging tools) legitimately modify attributes that the IaC tool should not fight over. But it is also a common escape hatch that quietly expands the surface area of undetected drift. Every `ignore_changes` directive is a declaration that your code is not the source of truth for that attribute.

## How Drift Enters the System

Drift has a small number of entry paths, and understanding them concretely matters because each one requires a different organizational response.

**Console access during incidents** is the most common and most sympathetic. A production database is overloaded. An engineer scales up the instance class through the AWS console because it is the fastest path to resolution. The incident is resolved. The IaC code is not updated. The next `terraform plan` will propose scaling the instance back down, which is now the wrong thing to do.

**Parallel automation** is subtler. A security team runs a Lambda function that updates security group rules based on threat intelligence feeds. A compliance tool modifies S3 bucket policies. An auto-remediation system changes IAM policies in response to audit findings. All of these are making legitimate changes through the same cloud APIs, and all of them create drift relative to the IaC codebase.

**Partial adoption** is the most structural. Most organizations do not go from zero to 100% IaC coverage overnight. During the transition—which can last years—some resources are managed by code and some are not. The boundary between managed and unmanaged is often unclear, and resources frequently fall through the gap. Someone modifies a resource they believe is manually managed but which is actually tracked in a Terraform state file, or vice versa.

**Import failures** are the quiet variant. A team imports existing infrastructure into Terraform management but misses resources or gets attribute mappings wrong. The state file says one thing, reality says another, and nobody notices until a plan produces a surprising destructive action.

## The Accumulation Problem

The single most damaging property of drift is that it compounds. One drifted attribute is easy to reconcile. Fifty drifted attributes across twenty resources, accumulated over six months of console changes and emergency fixes, produces a plan output so large and so uncertain that no one is willing to approve it. The team cannot distinguish between safe corrections and destructive reversions. At this point, the IaC codebase has effectively lost its authority. Teams stop running plan. They stop applying. They start making more changes through the console because the IaC pathway feels broken. This is the drift spiral, and it is the primary way IaC adoptions fail in practice.

The insidious aspect is that the spiral is invisible until it is advanced. Every individual unreconciled change feels low-risk. The plan output grows by one or two lines each time. Nobody looks at it for a few weeks. Then someone runs a plan and gets 40 changes, half of which they do not recognize, and the trust is gone.

## Detection Is Not Remediation

Detecting that drift has occurred and deciding what to do about it are fundamentally different problems.

When a plan reveals drift, you have two directions. You can **reconcile forward**: apply the plan, which reverts reality to match your code. Or you can **reconcile backward**: update your code (and potentially your state) to match reality. The correct choice depends entirely on whether the drift represents an unauthorized deviation or a legitimate change that your code should incorporate.

Terraform provides `terraform apply -refresh-only`, which updates the state file to match current reality without making any infrastructure changes. This is "accept reality as the new baseline." But it leaves your code out of sync with the updated state—so the *next* plan will now try to revert reality back to what the code says, unless you also update the code. The full reconciliation path for legitimate drift is: refresh the state, update the code to match, and then confirm that the plan is clean.

For unauthorized drift, the path is simpler in theory but harder in practice: apply the plan and revert the change. The difficulty is in knowing whether the revert is safe. If someone widened a CIDR range on a security group to fix connectivity during an incident and you revert it, you may re-break production.

## Continuous Detection vs. Incidental Discovery

Most teams only discover drift when someone happens to run a plan. If nobody runs a plan for three weeks, drift accumulates undetected for three weeks. This is a design-level gap in how most teams use IaC tools.

**Continuous drift detection** means running a plan on a schedule—typically in CI—and alerting when the plan output is non-empty. The plan is never applied automatically; it is purely a detection mechanism. This turns drift from something you discover accidentally into something you detect systematically, while the scope is still small enough to reason about.

The cost is real: scheduled plans at scale hit cloud provider APIs heavily. Rate limiting, API costs, and execution time all become factors. For large estates, teams often run continuous detection on a per-workspace or per-module rotation rather than all at once.

## The Mental Model

Your IaC codebase is not a control plane. It is a *declaration of intent* paired with a *detection system*. The detection system only works when you run it, only covers resources you have explicitly brought under management, and only examines attributes the cloud provider API reliably exposes. Everything outside that envelope—unmanaged resources, ignored attributes, the time between plan runs—is a detection gap.

Drift is not a bug in IaC. It is an inherent property of any system where the managed infrastructure has an API that accepts changes from sources other than the IaC tool. Which is every system. The question is never "how do we prevent drift?" but "how do we detect drift early, keep the blast radius small, and maintain the discipline to reconcile it before it compounds?"

The teams that succeed with IaC long-term are not the ones that never experience drift. They are the ones that treat a non-empty plan as an operational signal with the same urgency as a monitoring alert—something to be investigated and resolved, not something to be deferred.

## Key Takeaways

- **Drift detection is a three-way comparison** between desired state (code), stored state (state file), and actual state (cloud API)—the stored state provides the mapping between code declarations and real-world resource IDs.

- **IaC tools can only detect drift on resources they track.** Resources created outside the tool are invisible to it indefinitely, making unmanaged resources a more dangerous form of drift than modified managed ones.

- **The plan output merges drift correction and intentional changes into a single list.** There is no built-in distinction between reverting unauthorized changes and applying your new code, which is why accumulated drift makes plans unreadable and unapprovable.

- **Every `ignore_changes` directive, every `-refresh=false` flag, and every skipped plan run is a deliberate expansion of your detection gap.** These are sometimes necessary, but they should be tracked as accepted risk, not treated as routine.

- **Drift compounds.** One drifted attribute is trivially fixable. Fifty drifted attributes across months of accumulated changes produce a plan that no one will approve, and this is how IaC adoptions lose authority and collapse.

- **Reconciliation has two directions—revert reality to match code, or update code to match reality—and choosing wrong can cause outages.** There is no safe default; every drifted attribute requires a judgment call about whether the real-world state or the declared state is correct.

- **Continuous drift detection (scheduled plan runs with alerting) converts drift from an incidental discovery into a systematic operational signal**, and is the single highest-leverage practice for preventing drift accumulation.

- **Your IaC codebase is authoritative only to the extent that you enforce the discipline to keep it so.** The tool provides detection. The authority comes from organizational practice.


[← Back to Home]({{ "/" | relative_url }})
