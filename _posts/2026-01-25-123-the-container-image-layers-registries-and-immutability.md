---
layout: post
title: "1.2.3 The Container Image: Layers, Registries, and Immutability"
author: "Glenn Lum"
date:   2026-01-23 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most engineers can tell you that a container image is "a stack of layers" and that it's "immutable." They can say this accurately without it being useful. The surface understanding holds up fine right until a build takes fifteen minutes instead of thirty seconds, a security audit finds credentials that were supposedly deleted, or a production deployment silently diverges from what passed testing — all with no version number changing anywhere. These aren't edge cases. They're direct consequences of the layer model, the registry protocol, and the specific way immutability does and doesn't hold. The mechanics are what matter.

## How Layers Are Constructed

Each instruction in a Dockerfile that modifies the filesystem produces a new **layer**. A layer is not a snapshot of the entire filesystem — it is a **filesystem diff**, recording exactly what changed relative to the cumulative state of all layers beneath it. Files added, files modified, files marked as deleted.

```dockerfile
FROM ubuntu:22.04                          # Base image layers (pulled, not built)
RUN apt-get update && apt-get install -y python3  # Layer: adds python3 and dependencies
COPY requirements.txt /app/                       # Layer: adds one file
RUN pip install -r /app/requirements.txt          # Layer: adds installed packages
COPY . /app/                                      # Layer: adds application code
```

The build tool executes each instruction against the current filesystem state, computes the diff, serializes it as a compressed tar archive, and hashes that archive with SHA256 to produce a **content digest**. That digest is the layer's identity. It is derived entirely from the layer's contents, which means two layers with identical contents will always produce the same digest regardless of when, where, or by whom they were built. This is **content-addressable storage** — the address *is* the content — and it's the property that makes layer sharing, caching, and deduplication work.

Not every Dockerfile instruction creates a layer. `ENV`, `EXPOSE`, `LABEL`, and `CMD` modify only the image's configuration metadata, not the filesystem. They alter the **config object** but produce no layer diff.

## The Union Filesystem at Runtime

When a container starts, the runtime does not unpack all layers into a single merged directory. Instead, a **union filesystem** — typically OverlayFS on Linux — mounts the layers as a stack. All image layers are mounted read-only. A thin, ephemeral read-write layer is placed on top for the container's runtime modifications.

When a process reads a file, the union filesystem searches downward from the topmost layer and returns the first match. When a process writes to a file that exists in a lower layer, the file is first **copied up** to the read-write layer before the write occurs. The lower layer's copy is untouched. This **copy-on-write** mechanism is why image layers can be safely shared across hundreds of running containers simultaneously — the shared data is never modified.

File deletion works through **whiteout files**. If layer 3 needs to remove `/tmp/cache.db` created in layer 2, it doesn't reach down and modify layer 2. It places a special whiteout marker in layer 3 that tells the union filesystem to hide that path. The actual data remains fully intact in layer 2. This is not an implementation quirk — it is the direct consequence of layers being immutable. Once a layer is written, its contents never change. Everything that follows is additive.

## Manifests, Configs, and What "An Image" Actually Is

A container image is not a file. It is a **manifest** — a JSON document defined by the OCI Image Specification — that points to other content-addressed blobs.

The manifest lists the content digest and size of each layer in order from bottom to top, plus a reference to a **config blob**:

```json
{
  "schemaVersion": 2,
  "mediaType": "application/vnd.oci.image.manifest.v1+json",
  "config": {
    "digest": "sha256:a1b2c3...",
    "size": 1470
  },
  "layers": [
    { "digest": "sha256:d4e5f6...", "size": 29210839 },
    { "digest": "sha256:g7h8i9...", "size": 847291 },
    { "digest": "sha256:j0k1l2...", "size": 5765432 }
  ]
}
```

The config blob contains runtime metadata: environment variables, the entrypoint command, the working directory, the user, exposed ports, and the ordered build history. It is also stored by its content digest.

The manifest itself is content-addressed. Its SHA256 digest is the **image digest** — the globally unique identifier for that exact combination of layers and configuration. When you see `myapp@sha256:a3ed95caeb02...`, that's the digest of the manifest. It is the only truly immutable reference to the image.

For multi-architecture images, a **manifest list** (or OCI **image index**) adds one more level of indirection: a JSON document that maps platform identifiers (like `linux/amd64` or `linux/arm64`) to platform-specific manifests. When you pull `node:18` on an ARM machine, the client fetches the manifest list first, finds the entry matching its architecture, then fetches the appropriate platform manifest and its layers.

## How Registries Store and Serve Images

A **registry** is a content-addressable blob store with an HTTP API. It stores three kinds of objects independently: layer blobs, config blobs, and manifests. Each is keyed by its content digest.

When you `docker push`, the client checks which layers the registry already has by issuing HEAD requests against each layer's digest endpoint. Only missing layers are uploaded. Then the config blob is uploaded, followed by the manifest. Optionally, a **tag** is associated with the manifest's digest — this is simply a mutable pointer stored by the registry.

When you `docker pull`, the process reverses: resolve the tag (or use the digest directly) to get the manifest, read the layer list from the manifest, download only the layers not already present in the local store. This is why pulling a new version of an image that shares a base with something already cached locally transfers only the changed layers.

This architecture gives registries natural **deduplication**. If every team in your organization builds from `python:3.11-slim`, the registry stores that base image's layers once. Every manifest referencing those layers points to the same blobs. Storage costs scale with unique content, not with the number of images.

### Tags vs. Digests

This is where the promise of immutability either holds or collapses.

A **tag** is a mutable human-readable name — `latest`, `v2.1.0`, `stable` — that the registry maps to a manifest digest. Anyone with push access can overwrite that mapping at any time. Push a new build with the same tag, and the tag now points to a completely different manifest. The old manifest and its layers still exist in the registry (until garbage collection), but the name resolves to new content.

A **digest** is immutable by construction. `myapp@sha256:a3ed95caeb02...` always resolves to the exact same manifest, which always points to the exact same layers. If the content were different, the hash would be different. There is no mechanism to change what a digest points to.

If your deployment spec says `myapp:v1.2.3`, you have a mutable deployment. If it says `myapp@sha256:a3ed95caeb02...`, you have an immutable one. The difference is not stylistic.

## The Build Cache and Why Instruction Order Matters

The layer model creates a caching mechanism that is both powerful and easy to accidentally defeat. During a build, the tool checks whether it can reuse an existing layer for each instruction. For `RUN` instructions, the cache key is the instruction text plus the digest of the layer below. For `COPY` and `ADD`, the key also incorporates a hash of the source files' contents and metadata.

Cache invalidation is **sequential and cascading**. If layer N is invalidated — because its instruction changed, or the files it copies changed — every layer above N must also be rebuilt. This isn't a limitation of the tooling; it's a consequence of what a layer is. Each layer is a diff against the cumulative state below it. If the state below changes, the diff cannot be reused even if the instruction is identical.

This makes Dockerfile instruction ordering a performance decision with real impact:

```dockerfile
# Every code change rebuilds dependencies (~2-5 minutes)
COPY . /app/
RUN pip install -r /app/requirements.txt

# Only requirements.txt changes rebuild dependencies
COPY requirements.txt /app/
RUN pip install -r /app/requirements.txt
COPY . /app/
```

In the first form, any source file change invalidates the `COPY` layer, which forces a rebuild of the `pip install` layer. In the second form, the expensive installation step is only re-executed when `requirements.txt` itself changes. Same instructions, same final filesystem state, dramatically different build times. The difference comes entirely from understanding the cache invalidation model.

## Where the Model Breaks

### Secrets That Can't Be Deleted

Because layers are immutable and the model is append-only, data written to the filesystem during any build step is permanently embedded in the corresponding layer. "Deleting" it later creates a whiteout that hides it from the union filesystem view. The data is still there.

```dockerfile
COPY credentials.json /tmp/
RUN ./configure --credentials /tmp/credentials.json
RUN rm /tmp/credentials.json
```

The file `credentials.json` exists, fully recoverable, in the layer created by the `COPY` instruction. Extracting it requires only standard tooling — `docker save` and `tar`. This isn't theoretical; it's a routine finding in container security audits.

The mitigation: BuildKit's `--mount=type=secret` mounts sensitive data into a build step without writing it to a layer. Multi-stage builds offer another path — the final image contains only layers from the last `FROM` stage, so intermediate layers with secrets never make it into the shipped artifact.

### Tag Mutability as a Deployment Gap

If your CI pipeline builds an image, tags it `v1.2.3`, pushes it, and your Kubernetes deployment references `myapp:v1.2.3`, you might believe you've pinned the deployment to a specific artifact. You haven't. Anyone with push access — including a misconfigured CI job, a compromised dependency, or a well-meaning colleague — can overwrite that tag with different content. Your next pod restart pulls the new artifact silently. No version change appears in any log or diff.

This is the mechanism behind supply chain attacks that target public registries, and it's also how teams accidentally deploy untested code when a CI job retags an image. The defense is **digest pinning**: referencing `myapp@sha256:...` in deployment manifests. Some organizations enforce this through admission controllers that reject pod specs containing tag-only references.

### Base Image Drift

`FROM node:18` doesn't pin a specific base image. It resolves to whatever `node:18` points to at build time. If the upstream maintainers publish an update — a new OpenSSL patch, a glibc bump — your next build silently incorporates it. Most of the time this is desirable. Occasionally it introduces a binary incompatibility or behavioral change that only manifests at runtime, in production, under specific conditions.

Pinning by digest (`FROM node@sha256:abc123...`) eliminates drift but creates a maintenance obligation: you must explicitly update the digest to receive security patches. This tradeoff has no resolution, only a choice — between reproducibility and automatic patching — that should be made consciously.

### Image Size and the Additive Trap

Because layers only add, a common pattern inflates image size without any visible indication:

```dockerfile
RUN apt-get update && apt-get install -y build-essential
RUN make && make install
RUN apt-get remove -y build-essential && rm -rf /var/lib/apt/lists/*
```

The removal in the third instruction creates whiteouts but does not reduce the image's transfer size. All three layers ship in full. The 300MB of `build-essential` and the package lists are still in the image — they're just hidden from the filesystem view. The fix is either to combine installation, compilation, and cleanup into a single `RUN` instruction (one layer diff, net result only) or to use multi-stage builds where you compile in a builder stage and copy only the output to a minimal final stage.

## The Mental Model

A container image is a **content-addressed, layered, append-only data structure**. Each layer is an immutable filesystem diff identified by the hash of its contents. A manifest binds layers into a logical artifact and is itself identified by its own content hash — the image digest. A registry stores these pieces independently, deduplicates at the layer level, and maps mutable names (tags) to immutable identifiers (digests).

The consequence for CI/CD is this: **the image digest is the unit of trust.** It is the single value that answers "what exactly are we deploying?" If your pipeline produces an image, records its digest, and every downstream system — testing, approval gates, deployment — references that digest, you have a verifiable chain from build to production. If any link in that chain references a tag, you have a gap where the artifact can change without anyone noticing. Understanding the layer model doesn't just explain how images work — it explains *where the guarantees are* and where they aren't.

## Key Takeaways

- A container image is not a single binary — it is a manifest pointing to an ordered stack of content-addressed, immutable filesystem diffs, each identified by the SHA256 hash of its contents.
- The union filesystem presents stacked read-only layers as a single coherent filesystem at runtime, using copy-on-write for modifications and whiteout files for deletions — meaning "deleted" data still exists in earlier layers.
- Registries store layers, configs, and manifests as independent content-addressed blobs, enabling natural deduplication: shared base layers are stored once regardless of how many images reference them.
- Tags are mutable pointers that can be overwritten by anyone with push access; digests are immutable by construction. Only digest references provide actual deployment immutability.
- Build cache invalidation cascades sequentially: changing one layer forces a rebuild of every subsequent layer, making Dockerfile instruction ordering a direct determinant of build performance.
- Secrets written to the filesystem during any build step are permanently embedded in the layer — deleting them afterward only hides them from the runtime view. Use BuildKit secret mounts or multi-stage builds to avoid baking credentials into images.
- `FROM <image>:<tag>` introduces silent base image drift between builds; pinning by digest guarantees reproducibility but requires manual updates for security patches.
- The image digest is the only reliable unit of trust across a CI/CD pipeline — every system that references a tag instead of a digest introduces a point where the deployed artifact can silently diverge from what was tested.

[← Back to Home]({{ "/" | relative_url }})
