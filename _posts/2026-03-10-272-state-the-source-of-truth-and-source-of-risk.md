---
layout: post
title: "2.7.2 State: The Source of Truth and Source of Risk"
author: "Glenn Lum"
date:   2026-03-10 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers who have used Terraform or a similar IaC tool understand that a state file exists. They know it should be stored remotely, that it should be locked during operations, and that losing it is bad. What they often lack is a precise understanding of what the state file *is* — not as a storage artifact, but as a conceptual layer in the system. This misunderstanding is the root cause of most serious IaC incidents: resources destroyed because someone refactored a module without understanding how identity works in state, infrastructure stuck in limbo because a partial apply left state half-written, teams locked out of their own environments because a crashed CI runner held a lock that no one knew how to safely release. State is not a cache. It is not a log. It is the binding layer between your code and reality, and the mechanics of that binding are what this post is about.

## The Three-Way Relationship

The Level 1 post described state as "a representation of the infrastructure as the IaC tool understands it." That is accurate, but it undersells the structural role state plays. To reason about state correctly, you need to hold three distinct things in your head simultaneously:

**Desired state** is what your code declares. A `.tf` file that says `resource "aws_s3_bucket" "logs"` with a particular configuration is a declaration of intent. It says: a bucket with these properties should exist.

**Recorded state** is what the state file contains. It is a structured mapping that says: the resource you call `aws_s3_bucket.logs` in your code corresponds to the real-world bucket with ARN `arn:aws:s3:::my-app-logs-20240301`, and the last time I checked, it had these properties.

**Actual state** is what exists in the real world right now — the actual configuration of that S3 bucket as the cloud provider's API would report it.

Every IaC operation is fundamentally a negotiation between these three. The tool's job is to bring actual state in line with desired state, using recorded state as its map of what currently exists. When all three are in agreement, operations are clean and predictable. When any two diverge, you are in a situation that requires understanding which two diverged and why.

## The Reconciliation Loop

When you run `terraform plan`, the sequence is not "compare code to state file." It is more involved than that, and the additional steps are where most of the operational subtlety lives.

First, the tool performs a **refresh**. It takes every resource tracked in the state file and makes an API call to the provider to check the resource's current actual properties. If someone manually changed the bucket's versioning configuration through the AWS console, the refresh step discovers this. The refresh updates the in-memory representation of state to reflect reality — what the tool now believes to be true about the world.

Second, the tool performs a **diff**. It compares the refreshed actual state against the desired state declared in your code. The output of this diff is the plan: a set of create, update, or destroy operations that would bring reality into alignment with your declarations.

Third, when you run `terraform apply`, the tool executes those operations and, critically, **writes the results back to the state file**. If it creates a new resource, it records the new resource's real-world identifier and properties. If it modifies a resource, it records the new properties. If it destroys one, it removes the entry.

This loop — refresh, diff, apply, write — is the heartbeat of IaC. Every operational concern about state maps back to a failure or complication in one of these steps.

## Resource Identity and the Binding Problem

The single most important thing the state file does is maintain **bindings** between logical identifiers in your code and physical identifiers in the real world. When your code says:

```hcl
resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.medium"
}
```

The state file records something like: "The resource at address `aws_instance.web` is bound to EC2 instance `i-0a1b2c3d4e5f67890`." This binding is the mechanism by which the tool knows that applying your code should *update* that existing instance rather than *create* a new one.

This has a consequence that catches people by surprise: **renaming a resource in code severs the binding.** If you refactor `aws_instance.web` to `aws_instance.application_server`, the tool sees a resource at the old address that exists in state but not in code (conclusion: destroy it) and a resource at the new address that exists in code but not in state (conclusion: create it). The result is destruction of your running server and creation of a new one, even though you intended only a cosmetic rename.

This is why IaC tools provide **state manipulation commands** — `terraform state mv`, `terraform import`, `terraform state rm`. These are not convenience features. They are the only way to perform certain kinds of code refactoring without destroying infrastructure. `terraform state mv aws_instance.web aws_instance.application_server` updates the binding without touching the real resource. `terraform import` creates a new binding from a real-world resource that was created outside your IaC code (or whose binding was lost). `terraform state rm` deletes a binding without destroying the resource, which is what you want when you are moving management of a resource to a different state file or taking it out of IaC management entirely.

These operations are surgery. They modify the binding layer directly, bypassing the normal reconciliation loop. There is no plan preview. If you move a resource to the wrong address, or import with the wrong configuration, the next plan will propose changes you did not intend. Treat state manipulation the way you would treat a manual database migration: with backups, peer review, and a clear understanding of what the expected outcome looks like before you execute.

## State Splitting and Blast Radius

A single state file that manages your entire infrastructure is a liability that grows with your organization. The reasons are both operational and structural.

**Operationally**, every `plan` and `apply` refreshes every resource in the state file. If your state contains 500 resources, every operation makes 500 API calls before it can even show you a plan. This is slow. More importantly, the lock is held for the entire duration. A single state file means only one infrastructure change can be in progress at a time across your entire organization.

**Structurally**, a single state file means any operation has the blast radius of your entire infrastructure. A bug in your Terraform code, a provider error, a partial apply — any of these can potentially affect every resource you manage. This is the IaC equivalent of deploying all your microservices from a single deployment pipeline with no isolation.

The solution is **state decomposition**: splitting infrastructure into multiple state files, each managed independently. The natural boundaries depend on your context, but common patterns include splitting by environment (production, staging, dev each have their own state), by layer (networking, compute, data stores), or by team ownership. A good heuristic: if two groups of resources have independent change lifecycles and minimal cross-references, they should probably be in separate state files.

This creates a new problem: **cross-state dependencies.** Your compute layer needs to know the subnet IDs created by your networking layer. Terraform handles this with **remote state data sources** — one state file can read outputs from another. But this creates a coupling that has its own operational implications. If someone destroys and recreates the networking layer, the compute layer's state still references the old subnet IDs. The data source will return the new values on the next plan, but until that plan is applied, there is a window of inconsistency. Design your state boundaries so that the cross-references flow in one direction (layers depend downward, never upward) and minimize the number of values that cross the boundary.

## Tradeoffs and Failure Modes

### Partial Applies

An `apply` that fails midway is the most common source of state trouble. Suppose your code creates a security group and an EC2 instance that references it. Terraform creates the security group successfully and writes it to state. The EC2 instance creation then fails — maybe an API rate limit, maybe an invalid AMI. Your state now records the security group but not the instance. Your code still declares both. The next `plan` will correctly propose creating only the instance, because the security group is already tracked. This is the happy case — partial applies are usually recoverable by re-running.

The unhappy case is when a resource is created in reality but the state write fails — a network interruption at exactly the wrong moment, a backend storage error. Now you have a real resource that exists but is not tracked in state. You cannot manage it, update it, or destroy it through your normal IaC workflow. You must either `import` it back into state or clean it up manually. This is rare but not negligible at scale, and it is why state backends with strong consistency guarantees (S3 with DynamoDB locking, GCS, Terraform Cloud) exist.

### Stuck Locks

When an apply starts, the tool acquires a lock on the state backend. If the process crashes — a CI runner dies, a laptop loses network — the lock may not be released. Every subsequent operation fails with a lock error. The fix is `terraform force-unlock <LOCK_ID>`, but this command must be used with extreme care. If the lock is held because another operation is genuinely still running (not crashed, just slow), force-unlocking can result in two concurrent writes to the same state file. The correct response to a stuck lock is: verify that the holding process is actually dead, take a backup of the current state, then force-unlock.

### Drift and the Limits of Refresh

The refresh step catches most manual changes to managed resources, but it has limits. It can only detect drift on resources it knows about. If someone creates a resource manually that has the same functional role as something in your code but is not tracked in state, the tool has no way to detect it. You might end up with two load balancers, two DNS records, or two security groups where you intended one. The tool's view of the world is only as complete as its state file.

Additionally, not all resource attributes are returned by provider APIs. Some cloud resources have properties that are write-only — they can be set at creation time but are not readable afterward. The tool cannot detect drift on these properties because it has no way to query their current value. The state file records the value that was set, but cannot verify it still holds.

### Secrets in State

The state file stores the full attributes of every managed resource, which often includes values you would prefer to keep out of a JSON file on disk: database master passwords, API keys generated at creation time, TLS private keys. This is not a design flaw — the tool needs these values to detect drift and to provide them as outputs to dependent resources. But it means your state file is a security-sensitive artifact. Encrypting the backend at rest, restricting access with IAM policies, and avoiding state files in version control are not best practices — they are requirements. Any compromise of the state file is a potential compromise of every secret it contains.

## The Mental Model

State is not a cache that can be regenerated. It is not a log of past operations. It is a **live binding table** that maps every logical resource in your code to a specific physical resource in the real world, along with the properties the tool believes that resource currently has. This binding is what makes declarative IaC possible: without it, the tool cannot distinguish "this resource needs to be created" from "this resource already exists and needs to be updated." Every operation reads from, reasons about, and writes to this binding table.

When you understand state this way, the operational rules stop being arbitrary. Store it remotely because the binding table must be shared. Lock it because concurrent writes to a binding table corrupt it. Split it because a smaller binding table means a smaller blast radius. Back it up because recreating bindings by hand — reimporting hundreds of resources — is one of the most painful recovery operations in infrastructure engineering. Protect it because it contains the real-world identifiers and secrets of everything you manage.

The question you should always be able to answer is: for any given resource in my code, what real-world thing does the state file think it corresponds to, and is that still true?

## Key Takeaways

- **State is a binding table, not a cache.** It maps logical resource addresses in your code to physical resource identifiers in the real world. Losing it does not just lose a record — it severs your tool's ability to manage existing infrastructure.

- **Every IaC operation is a three-way negotiation** between desired state (your code), recorded state (the state file), and actual state (what the cloud provider's API reports). Trouble starts when any two of these diverge.

- **Renaming a resource in code is not a rename — it is a destroy and create** unless you explicitly update the binding in state using `terraform state mv` or an equivalent `moved` block. Refactoring IaC code is fundamentally different from refactoring application code.

- **Partial applies are the most common source of state inconsistency.** A resource can exist in reality but not in state if the write-back fails. The recovery path is `import`, not re-creation.

- **State splitting is not optional at scale.** A monolithic state file creates a blast radius equal to your entire infrastructure, serializes all changes behind a single lock, and makes every operation slower as the resource count grows.

- **Force-unlocking state without verifying the holding process is dead can cause concurrent state writes and corruption.** Always confirm the lock holder has actually crashed before releasing.

- **The state file is a security-sensitive artifact** that contains the full attributes of managed resources, including secrets. Treat it with the same access controls you would apply to a production database backup.

- **Drift detection only works on resources the state file knows about.** Manually created resources that duplicate the function of a managed resource are invisible to the tool and will not trigger a diff.

[← Back to Home]({{ "/" | relative_url }})
