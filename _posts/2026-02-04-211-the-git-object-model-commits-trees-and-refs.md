---
layout: post
title: "2.1.1 The Git Object Model: Commits, Trees, and Refs"
author: "Glenn Lum"
date:   2026-02-04 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers interact with Git as if it were a timeline. You make changes, you commit them, the log shows a sequence of events. Branches feel like parallel timelines. Merging feels like combining timelines. This metaphor works right up until it doesn't — and then everything becomes confusing at once. Why does rebasing "rewrite history" when you didn't change any files? Why does `git cherry-pick` sometimes produce a commit with a different hash even though the code diff is identical? Why does checking out a tag put you in "detached HEAD" state, and what exactly is detached about it?

The confusion is never about the commands. It is about the data model underneath. Git is not a timeline system. It is a content-addressed object store that forms a directed acyclic graph, with a thin layer of mutable pointers on top. Once you see that structure clearly, every Git behavior becomes mechanical and predictable. This post is about seeing that structure.

## The Four Object Types

Git's entire storage model is built from four kinds of objects: **blobs**, **trees**, **commits**, and **annotated tags**. Every object is immutable, identified by the SHA-1 hash of its contents, and stored in the `.git/objects` directory. That's it. There is no other storage mechanism for your repository's content.

### Blobs: Content Without Identity

A **blob** (binary large object) stores the contents of a single file. Not the filename. Not the permissions. Not the path. Just the raw bytes, prefixed with a header indicating the object type and size, then hashed.

This means if two files in your repository have identical contents — say, two different `LICENSE` files in two different directories — Git stores one blob. The hash is derived from content alone, so identical content always produces the same object. You can verify this:

```bash
echo "hello" | git hash-object --stdin
# ce013625030ba8dba906f756967f9e9ca394464a
```

Run that on any machine, any repository. Same input, same hash. This is content-addressing: the address (hash) is derived from the content itself.

### Trees: Directory Snapshots

A **tree** object represents a single directory. It contains a list of entries, where each entry has a mode (file permissions), a type (blob or tree), a hash, and a filename. A tree entry pointing to another tree is how Git represents subdirectories.

A simplified tree might look like:

```
100644 blob a1b2c3d4...  README.md
100644 blob e5f6a7b8...  main.py
040000 tree 9c8d7e6f...  src/
```

The tree does not know where it lives in the hierarchy. It does not know its own name. Its parent tree is the one that holds an entry pointing to it with a name like `src/`. This is the same principle as blobs — trees are defined entirely by their contents, so two directories with identical structures and identical files produce the same tree hash.

Here's the critical insight: a tree object is a **complete snapshot** of a directory at a point in time. Git does not store diffs between versions of files. It stores whole snapshots. When you change one file and commit, Git creates a new blob for that file, new tree objects for every directory in the path from root to that file, and reuses every other existing blob and tree object unchanged. This structural sharing is what makes snapshots storage-efficient despite being conceptually complete.

### Commits: Snapshots With Context

A **commit** object contains exactly five things:

```
tree 4b825dc642cb6eb9a060e54bf899d15643e26f72
parent 8e4f0c9d... (zero, one, or more)
author Jane Doe <jane@example.com> 1700000000 -0500
committer Jane Doe <jane@example.com> 1700000000 -0500
<blank line>
Refactor authentication middleware
```

The `tree` line points to the root tree object — the complete snapshot of the entire repository at this commit. The `parent` line points to the commit(s) that this commit was based on. The first commit in a repository has no parent. A regular commit has one parent. A merge commit has two or more.

This is the core of the model. A commit is not a diff. It is a pointer to a full snapshot (via the tree), combined with pointers to the previous state(s) (via parents), combined with metadata. The diff you see in `git log -p` or `git show` is *computed* at display time by comparing the commit's tree against its parent's tree. It is not stored.

Because a commit's hash is derived from all of its contents — the tree hash, parent hash(es), author, committer, timestamp, and message — changing any of these produces a different commit hash. This is why rebasing "changes history": it creates new commit objects with different parent pointers, which means different hashes, even if the tree snapshots are identical.

## The Directed Acyclic Graph

The parent pointers form a **directed acyclic graph (DAG)**. Each commit points backward to its parent(s). The direction is always backward in time. There are no cycles — a commit cannot be its own ancestor.

For a linear history, the graph is a simple chain:

```
A <-- B <-- C <-- D
```

Each letter is a commit. `D`'s parent is `C`, `C`'s parent is `B`, and so on. When you create a branch and make commits on it, the graph forks:

```
A <-- B <-- C <-- D       (main)
            \
             E <-- F      (feature)
```

`D` and `F` both have `C` as an ancestor. When you merge `feature` into `main`, Git creates a merge commit with two parents:

```
A <-- B <-- C <-- D <-- G  (main)
            \          /
             E <-- F
```

`G` points to both `D` and `F` as parents. Its tree is the merged snapshot. The entire history of your repository is this graph of commit objects, stored as immutable content-addressed objects in `.git/objects`.

The DAG structure is why Git can answer questions like "what is the common ancestor of these two branches?" efficiently. It walks the graph backward from both commits until it finds where the paths converge. This operation — finding the **merge base** — is what drives both `git merge` and `git rebase`.

## Refs: The Mutable Layer

Everything described so far is immutable. Once an object is written, it never changes. So how does Git know what `main` is? How does it know where you are in the graph?

**Refs** (references) are the answer, and they are shockingly simple. A ref is a file that contains a 40-character commit hash. That's all.

```bash
cat .git/refs/heads/main
# 9f4d3b2a1e8c7f6d5a4b3c2d1e0f9a8b7c6d5e4f
```

A branch is a ref that lives in `.git/refs/heads/`. A tag (a lightweight tag, specifically) is a ref in `.git/refs/tags/`. When you "create a branch," Git creates a 41-byte file. When you commit on a branch, Git moves that file's contents to point to the new commit. That is the entire mechanism.

**HEAD** is a special ref stored in `.git/HEAD`. Usually, it contains a symbolic reference to a branch:

```
ref: refs/heads/main
```

This means "I am currently on the `main` branch." When you make a commit, Git creates the new commit object, then updates the ref that HEAD points to so it contains the new commit's hash.

**Detached HEAD** state occurs when `.git/HEAD` contains a raw commit hash instead of a symbolic reference:

```
9f4d3b2a1e8c7f6d5a4b3c2d1e0f9a8b7c6d5e4f
```

You are no longer "on" any branch. If you make commits in this state, they are perfectly valid commit objects in the graph, but no branch ref is being updated to track them. Once you check out a branch, there is no named pointer leading to those commits. They become **unreachable** — still in the object store but not discoverable by walking from any ref. Eventually, `git gc` will delete them.

**Annotated tags** differ from lightweight tags. A lightweight tag is just a ref pointing to a commit. An annotated tag is a ref pointing to a **tag object**, which in turn points to a commit and also stores a tagger, date, and message. This is why annotated tags are preferred for releases — they carry their own metadata and are themselves content-addressed objects.

## How Operations Map to the Object Model

With this model in hand, Git operations become mechanical:

`git commit` creates a new blob for each changed file, creates new tree objects for affected directories (reusing unchanged subtrees), creates a commit object pointing to the new root tree and the current HEAD commit as parent, then updates the current branch ref to point to the new commit.

`git branch feature` creates a new file at `.git/refs/heads/feature` containing the same commit hash as the current HEAD. No objects are created. No copies are made. It is a 41-byte file creation.

`git merge feature` (assuming a non-fast-forward) finds the merge base of the current branch and `feature`, computes a three-way merge of the trees, creates a new commit with two parents and the merged tree, and advances the current branch ref.

`git rebase main` (from a feature branch) finds the merge base, takes each commit unique to the feature branch, and **replays** each one on top of `main`. "Replays" means computing the diff each commit introduced against its parent, applying that diff to the new base, and creating a **new commit object** with a new parent (the previous replayed commit or `main`'s tip) and a new tree. The new commits have different hashes. The old commits still exist in the object store but are no longer reachable from any branch ref.

`git cherry-pick abc123` does exactly what rebase does for a single commit: computes the diff that `abc123` introduced relative to its parent, applies it to the current HEAD, and creates a new commit. The new commit has a different hash because it has a different parent and likely a different tree, even though the diff is semantically identical.

## Where the Model Bites You

### The Rebase-and-Force-Push Problem

When you rebase commits that have already been pushed to a shared branch, you create new commit objects and need to force-push (`git push --force`) to overwrite the remote ref. Anyone who had the old commits checked out now has a local history that diverges from the remote — not because of content differences but because the commit objects themselves are different. Their `git pull` will try to merge two histories that share identical code changes but have different graph structures. This is the root cause of every "rebase vs. merge" team conflict, and it is entirely predictable from the object model: rebase creates new objects, and sharing objects that others have already based work on creates divergence.

### Unreachable Objects and the Illusion of Deletion

Engineers sometimes believe that `git reset --hard` or a force-push deletes commits. It does not. It moves a pointer. The commit objects remain in the object store. The **reflog** (`.git/logs/`) records every ref update, which means `git reflog` will show you the "deleted" commits for at least 90 days by default. This is your safety net — but it is a local safety net. The reflog exists only in the repository where the operation happened. A force-push to a remote does not preserve the remote's reflog for you.

### Large Files and the Snapshot Model

Because Git stores blobs of full file content (not diffs), committing a 100MB binary file means that object exists in your repository forever, even if you delete the file in the next commit. The old blob is still referenced by the old commit's tree. This is why Git repositories grow permanently when large binaries are committed, and why tools like Git LFS exist — they replace the blob with a small pointer file and store the actual content externally.

## The Model You Should Carry

Git is two layers. The bottom layer is an immutable, content-addressed object store where blobs, trees, commits, and tags are identified by hashes and linked into a directed acyclic graph. This layer only grows; nothing in it changes. The top layer is a set of mutable pointers — branches, tags, HEAD — that give human-readable names to specific points in the graph.

Every Git operation is either creating new objects in the bottom layer, moving pointers in the top layer, or both. When you internalize this, you stop thinking about Git as a timeline with magical commands and start thinking about it as a graph with named positions. Rebase does not "rewrite history" — it writes *new* history (new commit objects) and moves a pointer to it. Reset does not "delete commits" — it moves a pointer backward. A branch is not a container for your work — it is a pointer that advances as you add commits.

This two-layer model is the conceptual foundation for everything that follows: interactive rebase, the reflog, recovery workflows, the mechanics of merge conflicts, and the design of Git-based deployment pipelines. If you can reason about objects and refs, you can reason about any Git operation from first principles.

## Key Takeaways

- Git stores snapshots, not diffs — each commit points to a tree that represents the complete state of the repository, and diffs are computed at display time by comparing trees.
- Every object (blob, tree, commit, tag) is immutable and identified by the SHA-1 hash of its contents, which means identical content always produces the same hash regardless of when or where it is created.
- A branch is a 41-byte file containing a commit hash — creating a branch creates no copies, allocates no storage beyond the pointer, and costs nothing.
- Detached HEAD means `.git/HEAD` contains a raw commit hash instead of a symbolic reference to a branch, so new commits have no branch ref tracking them and will become unreachable when you switch away.
- Rebase creates entirely new commit objects with new hashes because the parent pointers change — this is why rebasing shared commits causes divergence for anyone else working from those commits.
- `git reset --hard` and force-push do not delete commits; they move pointers, and the unreachable objects remain in the object store until garbage collection runs (at least 90 days by default via the reflog).
- Git's snapshot model means large binary files permanently inflate repository size even if deleted in subsequent commits, because the blob remains referenced by the old commit's tree.
- Every Git operation reduces to creating immutable objects, moving mutable pointers, or both — if you can identify which, the operation's behavior becomes fully predictable.


[← Back to Home]({{ "/" | relative_url }})
