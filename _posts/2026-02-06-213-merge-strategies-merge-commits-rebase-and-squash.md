---
layout: post
title: "2.1.3 Merge Strategies: Merge Commits, Rebase, and Squash"
author: "Glenn Lum"
date:   2026-02-06 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most teams pick a merge strategy the way they pick a code formatter: someone has a preference, it gets encoded into the repository settings, and nobody revisits it. The conversation, when it happens at all, tends to center on aesthetics — "I like a clean history" or "merge commits are noisy." This framing misses the point entirely. Each merge strategy produces a fundamentally different graph structure, and that structure determines what information your history retains, what diagnostic tools remain available to you, and what operations become safe or dangerous after the fact. Choosing a merge strategy is not a style preference. It is a decision about what you will be able to learn from your repository six months from now when something is broken and you need to understand why.

The Level 1 post established that commit history is a debugging tool and that atomic commits make tools like `git bisect` effective. This post explains the mechanics that sit underneath that claim: what each strategy does to the commit graph, what exactly is preserved or destroyed, and why those structural differences matter when you need to actually use your history.

## The Graph You Are Shaping

A Git repository is a directed acyclic graph (DAG) of commit objects. Every commit stores a snapshot of the repository, a pointer to one or more parent commits, an author, a committer, a timestamp, and a message. The SHA-1 hash that identifies a commit is derived from all of this — including the parent pointer. This means two commits with identical file changes but different parents are different commits with different hashes.

When you choose a merge strategy, you are choosing how to integrate one line of commits into another. The resulting graph topology — how many parents each commit has, whether original commits are preserved or replaced, whether branch structure is visible — is the thing that varies. Everything downstream (what `git log` shows, what `git bisect` can traverse, what `git blame` reports, what `git revert` can undo) follows from that topology.

## Merge Commits: Preserving the Full Topology

A **merge commit** is a commit with two (or more) parents. When you merge a feature branch into main with a merge commit, Git creates a new commit on main whose first parent is the previous tip of main and whose second parent is the tip of the feature branch. The feature branch's commits remain exactly as they were — same hashes, same parent relationships, same authorship.

Suppose main has commits A → B → C, and your feature branch diverged at B with commits D → E. After a merge, main looks like this:

```
A → B → C → M
         \     ↗
          D → E
```

M is the merge commit. It has two parents: C and E. The commits D and E still exist with their original SHAs and their original parent pointers. The entire branch topology is recorded in the graph.

This preservation has a concrete consequence that most engineers underappreciate: `git log --first-parent main` will show you A, B, C, M — just the merge points on main, one per feature. This gives you a clean, scannable history of integrations. Meanwhile, `git log main` (without `--first-parent`) will show you every commit, including D and E, with full detail. You get both views from the same graph. The "merge commits are noisy" complaint is almost always a `git log` configuration problem, not a merge strategy problem.

Merge commits also mean that `git bisect` can traverse into the feature branch. If the regression was introduced in commit D, bisect will find it. Every atomic commit the developer made is individually testable.

The cost is real, though. The graph is more complex. Tools that render history linearly (many GUI clients, some CI dashboards) can make a merge-heavy history look tangled. And merge commits can produce confusing diffs when the merge itself resolved conflicts — the merge commit's diff shows the conflict resolution, which is new code that does not appear in any individual feature commit.

## Rebase: Rewriting Lineage

A **rebase** takes a series of commits and replays them onto a new base, producing new commits with new parent pointers and therefore new SHA hashes. The diffs are the same. The messages are the same. The authorship metadata is preserved. But they are, from Git's perspective, entirely different commits.

Starting from the same example — main at A → B → C, feature branch at B → D → E — a rebase of the feature branch onto main produces:

```
A → B → C → D' → E'
```

D' and E' have the same diffs and messages as D and E, but different SHAs because their parent pointers changed. D' points to C instead of B. The original D and E still exist in the repository's object store (until garbage collection), but nothing references them.

After rebasing, the feature branch can be fast-forward merged into main, producing a perfectly linear history with no merge commit. This is what people mean when they say rebase gives you a "clean" history.

What is actually happening is a trade: you gain linearity and lose topology. The resulting graph does not record that D' and E' were developed together as a unit, or that they were developed in parallel with C. The history looks as if the developer wrote D' and E' sequentially after C, which is not what happened.

The more important mechanical consequence is the SHA rewrite. Any system or person that referenced the original commit D by its hash — a comment in a code review, a CI build record, a link in an issue tracker, a tag — now holds a dangling reference. The commit exists in the reflog temporarily, but for practical purposes, the identity of that commit has been destroyed and replaced.

This also creates a hazard for shared branches. If another developer branched off your feature branch at commit D, and you rebase your feature branch (rewriting D to D'), their branch still points to the original D. When they try to merge or rebase onto your updated branch, Git sees divergent histories with duplicated changes. This is the origin of the well-known rule: **do not rebase commits that other people have based work on.** It is not a convention. It is a consequence of how commit identity works.

## Squash: Compressing a Branch Into a Single Commit

A **squash merge** takes all the commits on a feature branch and produces a single new commit on the target branch. That commit's diff is the cumulative diff of the entire feature branch, its message is typically a combination (or replacement) of the individual commit messages, and it has a single parent: the tip of the target branch.

From the same starting point, a squash merge produces:

```
A → B → C → S
```

S contains all the changes from D and E combined. Commits D and E are not reachable from main. The feature branch, if not deleted, still points to E, but Git has no record that S is related to D or E. There is no parent pointer connecting them.

This is the most aggressive compression of the three strategies. What is preserved: the cumulative code change, the final state. What is lost: every intermediate step, the individual commit authorship (if multiple people committed to the branch), the ability to attribute specific lines to specific commits within the feature, and — critically — **Git's awareness that this work was integrated at all**.

That last point has a subtle but real consequence. If you squash-merge a feature branch into main and then later try to merge that same feature branch (or another branch derived from it) into main again, Git does not know that the work is already present. It will attempt to apply those changes again, likely producing conflicts. This makes squash merging hazardous for workflows involving long-lived branches, release branches, or any pattern where the same line of work might be integrated into multiple targets.

## Diagnostic Consequences: Bisect, Blame, and Revert

The choice of merge strategy directly determines the resolution at which your diagnostic tools operate.

### Bisect

`git bisect` performs a binary search across commits to find the one that introduced a bug. Its effectiveness is a function of how many individually testable commits exist between "known good" and "known bad." With merge commits, bisect can traverse into feature branches and test individual commits — if the developer made atomic commits, bisect can pinpoint the exact change. With rebase, the commits are linear and bisect works the same way, testing each replayed commit. With squash, the entire feature is one commit. If a feature touched 40 files across 15 commits that were squashed, bisect can only tell you "the bug is somewhere in this 2,000-line change." You are back to manual inspection.

### Blame

`git blame` maps each line of a file to the commit that last modified it. With merge commits or rebase, blame traces through to individual commits with their original messages and authorship. With squash, every line touched by the feature is attributed to a single commit with a single author, even if multiple engineers contributed. The individual "why" behind each line change is gone.

### Revert

`git revert` creates a new commit that undoes the changes of a previous commit. Reverting a squash commit is mechanically simple — one commit, one revert. Reverting a merge commit requires you to specify which parent to follow (typically `-m 1` to revert relative to the mainline), and it has a well-known gotcha: if you revert a merge commit and later try to re-merge the same branch, Git considers those commits already integrated and will not apply them. You have to "revert the revert" first. This is not a bug; it follows directly from how Git tracks merge ancestry. But it surprises engineers regularly.

Reverting individual commits from a rebased history is straightforward, but because the commits are linear, reverting one mid-sequence commit can conflict with later commits that depend on it, whereas reverting an entire merge commit cleanly removes the whole unit of work.

## Where Teams Get Into Trouble

The most common failure mode is **squash-by-default without understanding what it destroys**. Many teams adopt squash merging because it makes the main branch history look tidy — one commit per PR, easy to scan. This works fine for small, single-commit features. It becomes a real problem when a PR contains meaningful intermediate steps. A developer who carefully structured their work into atomic commits — separating the refactor from the behavior change from the test update — watches all of that structure get collapsed into a single blob. The effort invested in commit hygiene yields zero diagnostic return.

The second failure mode is **rebasing shared branches**. A developer rebases a branch that a colleague has already pulled and branched from. The colleague's history diverges from the rewritten branch. The resulting merge conflicts are confusing because they involve changes the developer has already seen. The fix is painful and error-prone. This happens most often on teams that enforce rebase workflows without ensuring that every engineer understands the SHA-rewriting mechanic.

The third failure mode is **treating merge strategy as uniform policy when branch types differ**. A short-lived, single-purpose branch with one commit benefits from squash — nothing is lost. A long-running integration branch with a dozen carefully structured commits benefits from merge commits — everything is preserved. A solo developer's local feature branch benefits from rebase before merging — the local messy history is cleaned up and the public history stays linear. Applying one strategy to all three situations guarantees a poor fit in at least two of them.

A subtler issue is **losing the ability to understand the evolution of a design**. When a feature branch records the sequence "add interface, implement for case A, implement for case B, refactor shared logic," that sequence tells a story about how the design emerged. Squashing collapses that into "add feature X." Twelve months later, when someone is trying to understand why the abstraction boundary is where it is, the information that would explain it no longer exists.

## The Model to Carry Forward

Every merge strategy is a lossy transform applied to your commit graph. The question is never "which one produces the cleanest history" — that framing reduces a structural decision to an aesthetic one. The question is: **what information does my team need to recover from this history, and which strategy preserves it?**

Merge commits preserve everything — full topology, original commits, branch relationships — at the cost of a more complex graph. Rebase preserves individual commit detail but destroys topology, commit identity, and the evidence that work happened in parallel. Squash destroys almost everything except the cumulative result.

The right choice depends on what you are integrating. It depends on how your team works, how large your changes tend to be, and what you expect to need from your history when something goes wrong. The engineer who understands the graph mechanics can make that choice deliberately. The engineer who does not is making it by accident.

## Key Takeaways

- A merge commit creates a commit with two parents, preserving the full branch topology and every original commit hash; `git log --first-parent` gives you a clean integration-level view while the full graph retains all detail.

- Rebase replays commits onto a new base, producing new commits with new SHA hashes; any external references to the original commit hashes become dangling, and rebasing commits that others have branched from will cause divergent histories.

- Squash merge compresses an entire branch into a single new commit with no parent-pointer connection to the original branch, meaning Git has no record the integration occurred — re-merging the same branch will cause conflicts.

- `git bisect` effectiveness is directly proportional to the number of individually testable commits in your history; squash merging collapses a feature to a single commit, eliminating any ability to binary-search within it.

- `git blame` after a squash merge attributes every changed line to a single commit and a single author, destroying the per-line provenance that would otherwise explain why each change was made.

- Reverting a merge commit requires specifying a parent (`-m 1`) and creates a state where re-merging the same branch will silently skip the changes unless the revert itself is reverted first.

- The strongest workflow is not a single strategy applied uniformly but a deliberate choice per branch type: squash for trivial single-purpose branches, rebase for cleaning up local work before sharing, merge commits for preserving the structure of meaningful multi-commit features.

- History is not a log to be kept tidy; it is a diagnostic instrument whose resolution is determined by the merge strategy you choose at integration time.

[← Back to Home]({{ "/" | relative_url }})
