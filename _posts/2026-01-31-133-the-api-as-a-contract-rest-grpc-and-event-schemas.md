---
layout: post
title: "1.3.3 The API as a Contract: REST, gRPC, and Event Schemas"
author: "Glenn Lum"
date:   2026-01-31 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most engineers treat API design as a UI problem — pick clean resource names, use the right HTTP verbs, return sensible status codes, and you're done. The real difficulty has almost nothing to do with aesthetics. The moment a second system starts consuming your API, you have made a commitment. Not a commitment you signed or agreed to in a meeting — a commitment that now exists in deployed code, running in production, operated by a team that may not talk to you. That commitment is the contract, and the mechanics of how different API technologies encode and enforce that contract determine how much freedom you retain to evolve your system without breaking theirs.

The Level 1 post established that microservices and event-driven architectures turn every inter-service boundary into a network call or an asynchronous message. This post is about what crosses that boundary — the shape, the semantics, the promises — and why the choice of REST, gRPC, or event schema isn't a style preference. It's a decision about how much of your contract is machine-enforced versus convention-enforced, and that distinction has consequences you'll live with for years.

## What a Contract Actually Promises

An API contract is more than a data shape. It consists of several layers, and the ones people forget about are the ones that cause production incidents.

The **structural contract** is the most visible: the fields, their names, their types, and their nesting. When you return a JSON object with a field `"total_price": 42.99`, consumers write code that reaches into that path and expects a number.

The **semantic contract** is what those fields mean. If `created_at` returns a UTC timestamp today and someone changes it to return local time next month, the structural contract is identical — still a string, still ISO 8601 — but every consumer interpreting it as UTC is now silently wrong. Semantic breaking changes are the most dangerous kind because no schema validator, type checker, or linter will catch them.

The **behavioral contract** includes everything outside the payload: expected latency ranges, idempotency guarantees, error response formats, pagination behavior, rate limiting semantics. When your consumer retries a `POST` because they believe it's idempotent and it isn't, the broken contract was behavioral — and it was never written down.

The **error contract** is often the most neglected. What does a `400` response body look like? Is there a machine-readable error code, or just a human string? Can a consumer programmatically distinguish "invalid email format" from "email already taken"? If you've ever had to parse error messages with string matching in production code, you've experienced what happens when the error contract is undefined.

These layers stack. REST, gRPC, and event schemas each formalize different layers and leave the rest to convention.

## How REST Encodes the Contract

REST APIs over HTTP with JSON bodies are the most common form of service interface. Their contract model is **implicit by default**. Nothing in the technology itself forces you to define a schema, version your API, or specify what happens when a field is missing. This is REST's superpower and its central risk.

JSON's type system is thin: strings, numbers, booleans, nulls, arrays, objects. There is no native distinction between an integer and a float, no date type, no enum type. A field that should only ever contain `"pending"`, `"active"`, or `"cancelled"` is, at the wire level, just a string. The structural constraint exists only in documentation or in validation code that someone remembered to write.

**OpenAPI** (formerly Swagger) exists to formalize REST contracts, and it helps — but the level of enforcement depends entirely on how it's used. If OpenAPI specs are generated from code after the fact, they document what exists; they don't constrain what's allowed. If they're written first and used to generate server stubs and client SDKs, they function closer to a real contract. Most teams fall somewhere in between, which means the spec drifts from reality on a timeline measured in weeks.

REST's flexibility makes additive changes low-friction. Adding a new field to a response body is generally non-breaking because well-behaved JSON parsers ignore unknown fields. But "generally" is doing real work in that sentence. If a consumer is using strict deserialization — a typed language that maps JSON to a struct and rejects unknown keys — your additive change just broke them. You won't know this until they page you at 2 AM. The contract was implicit, so neither side knew they disagreed about what was allowed.

Versioning in REST is convention, not mechanism. You can put the version in the URL path (`/v2/orders`), in a header (`Accept: application/vnd.myapi.v2+json`), or in a query parameter. None of these is enforced by HTTP itself. And none of them solves the hard problem, which is: what does "v2" mean? Does it mean every endpoint changed? Just one? Is v1 still supported? For how long?

## How gRPC Encodes the Contract

gRPC uses **Protocol Buffers (protobuf)** as its interface definition language, and this single decision changes the contract model fundamentally. The contract is defined in a `.proto` file before any code is written, and both server and client generate code from that file. The schema is not documentation — it's the source of truth.

```protobuf
message Order {
  string order_id = 1;
  int64 total_cents = 2;
  OrderStatus status = 3;
  string created_at = 4;
}

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_CONFIRMED = 2;
}
```

The numbers assigned to each field (`= 1`, `= 2`) are **field tags**, and they matter far more than the names. On the wire, protobuf doesn't transmit field names at all — it transmits tag numbers and values in a binary encoding. This means renaming a field is a non-breaking change (it only affects generated code, not the wire format), but reusing or changing a tag number is catastrophic. If you delete field `2` and later assign tag `2` to a new field with a different type, any old message still in a queue or a cache will have its `total_cents` bytes silently reinterpreted as the new type. Protobuf provides the `reserved` keyword specifically to prevent this:

```protobuf
message Order {
  reserved 2;
  reserved "total_cents";
  // tag 2 and name total_cents can never be reused
}
```

**Backward compatibility** means new code can read old messages. **Forward compatibility** means old code can read new messages. Protobuf achieves both for additive changes: if you add a new field with a new tag, old consumers simply skip the unknown tag when deserializing, and new consumers handle the absence of new fields with default values (zero for numbers, empty for strings, the first enum value for enums). This works reliably because the compatibility rules are built into the wire format, not left to convention.

The tradeoff is rigidity. Changing a field's type — even something that feels safe like `int32` to `int64` — has specific wire-format implications because they use different encodings. gRPC forces you to think about compatibility at design time, which costs more up front and pays off over the lifetime of the contract.

gRPC also formalizes the service interface itself, not just the message shapes:

```protobuf
service OrderService {
  rpc GetOrder(GetOrderRequest) returns (Order);
  rpc ListOrders(ListOrdersRequest) returns (stream Order);
}
```

This means the set of operations, their request/response types, and whether they're unary or streaming are all part of the machine-enforced contract. In REST, whether `GET /orders` returns a paginated list or a stream is a convention documented in prose.

## How Event Schemas Encode the Contract

Event-driven interfaces have a contract problem that synchronous APIs don't: **the producer has no direct relationship with its consumers**. When a service publishes an `OrderPlaced` event to a message broker, it doesn't know which services subscribe. It can't coordinate a migration. It can't even tell if anyone is still consuming an old format.

This makes event schema evolution the hardest contract problem of the three. Add the fact that events are often persisted — in Kafka, event sourcing systems, or replay-capable queues — and you have multiple schema versions coexisting not just across deployments but across time. A consumer replaying events from six months ago must be able to deserialize events from a schema version that no running producer has used in weeks.

**Schema registries** (Confluent Schema Registry, AWS Glue Schema Registry) exist to address this. They store versioned schemas and enforce compatibility rules at the broker level. When a producer tries to register a new schema version, the registry checks it against the previous version and rejects it if the change is incompatible with the configured compatibility mode — backward, forward, full, or none. This is the only one of the three paradigms where compatibility enforcement happens at the infrastructure layer rather than at the code layer.

**Apache Avro**, commonly used with Kafka, handles compatibility differently from protobuf. Avro serialization doesn't include field identifiers in each message — instead, the reader uses both the writer's schema (embedded or referenced by ID) and the reader's schema, and resolves differences between them at deserialization time. This makes new fields safe only if they have default values, because the reader's schema needs to supply a value when reading old messages that lack the field. If you add a field without a default, the reader will fail when encountering any message written before the change.

The critical distinction is that in synchronous APIs, you have a request-response loop that makes contract mismatches visible immediately (a 400 error, a type mismatch, a failed deserialization). In event-driven systems, a contract mismatch might surface as a consumer silently dropping messages, writing corrupted data to its own store, or falling behind on its consumer group because deserialization exceptions are accumulating in a dead-letter queue. The feedback loop is longer and the blast radius is wider.

## The Spectrum from Flexibility to Enforcement

These three approaches represent points on a spectrum, and the axis isn't "which is better." It's **how much contract enforcement is structural versus social**.

| Dimension | REST + JSON | gRPC + Protobuf | Events + Schema Registry |
|---|---|---|---|
| Schema enforcement | Optional (OpenAPI) | Required (`.proto` files) | Configurable (registry rules) |
| Type safety on the wire | Weak (JSON types only) | Strong (binary encoding) | Varies (Avro, Protobuf, JSON Schema) |
| Compatibility checking | Manual/CI-based | Compile-time + wire-format rules | Registry-enforced per write |
| Consumer visibility | Known (direct calls) | Known (direct calls) | Unknown (pub/sub decoupling) |
| Version coexistence | Explicit (URL/header) | Implicit (wire-compatible fields) | Mandatory (persisted events) |

Moving right on this spectrum buys you safety and costs you flexibility. A REST API can evolve quickly and informally when you have two consumers and a shared Slack channel. That same informality becomes a liability when you have forty consumers across six teams and an event stream replayed daily for analytics.

## Tradeoffs and Failure Modes

**The semantic break that no schema catches.** A payments service returns `amount` as cents (integer). A new developer, seeing no documentation, starts returning dollars (float). The schema change from `int` to `float` might cause a type error in some consumers — but in loosely typed consumers (JavaScript, Python with permissive deserialization), the value simply starts being interpreted as 100x its actual magnitude. Orders worth $1 are charged $100. The schema didn't break. The contract did.

**The accidental tight coupling of flexible APIs.** REST's lack of a formal schema means consumers will depend on whatever your API actually returns, not what you intended it to return. If your API returns fields in alphabetical order because of your serializer's default behavior, some consumer will eventually depend on that ordering. If you include a `debug_info` field in development that leaks into production, someone will build a dashboard on it. This is **Hyrum's Law**: with enough consumers, every observable behavior of your system becomes a de facto contract, regardless of what you documented. gRPC's code generation narrows this surface because consumers interact through generated types, not raw payloads — but it doesn't eliminate it entirely.

**The protobuf field number reuse.** This is catastrophic and not hypothetical. A team removes a field, months later a new developer adds a field and picks the vacated tag number. Old messages in caches, logs, or event stores are now silently corrupted when read by new code. The failure mode isn't an error — it's wrong data. This is why `reserved` isn't a nice-to-have; it's a safety mechanism.

**The event schema migration nobody coordinates.** In synchronous APIs, you can deploy the server first with a new optional field, then update clients. In event-driven systems, you may need all consumers to tolerate the new schema before the producer starts emitting it — but you don't control the consumers, and you may not know who they are. Without a schema registry enforcing compatibility modes, any producer change is a unilateral decision with unknown downstream consequences.

**Versioning as a strategy for avoidance.** Teams sometimes reach for a new API version (`/v2/`) every time a change feels risky, deferring the real work of understanding their compatibility constraints. This leads to a proliferation of versions that all need to be maintained, documented, and tested. Each active version multiplies the surface area of the contract. Versioning is a necessary tool, but using it to avoid understanding wire compatibility is expensive.

## The Mental Model

An API contract is not the schema you wrote — it's the set of expectations your consumers have encoded into their running systems. Some of those expectations match your schema. Some match undocumented behavior. Some match behavior you didn't know you had.

The choice between REST, gRPC, and event schemas is a choice about where contract enforcement lives. In REST, it lives in conventions, documentation, and discipline. In gRPC, it lives in the wire format and generated code. In event-driven systems with a schema registry, it lives in infrastructure that gates writes. None of these eliminate the need to think about compatibility — they determine how early and how loudly you find out when you've broken it.

The single most important conceptual shift: **a non-breaking change is defined by what consumers can tolerate, not by what the producer intended**. If you understand this, you can reason about any versioning strategy, any migration plan, and any contract testing approach from first principles.

## Key Takeaways

- An API contract has four layers — structural, semantic, behavioral, and error — and most tooling only validates the first. The other three are where the hardest bugs live.

- REST's flexibility is a double-edged property: it makes rapid evolution easy when consumer coordination is cheap, and makes silent breakage easy when it isn't.

- Protobuf field tags, not field names, define wire identity. Reusing a tag number doesn't cause an error — it causes silent data corruption, which is worse.

- Backward compatibility (new code reads old data) and forward compatibility (old code reads new data) are distinct properties with distinct design requirements. Additive-only changes with sensible defaults satisfy both in protobuf and Avro.

- Event schemas are the hardest contract problem because the producer cannot identify its consumers, events persist across schema versions, and contract mismatches surface as silent data corruption rather than immediate errors.

- Hyrum's Law applies to every API style: consumers depend on observable behavior, not documented behavior. The only way to narrow that gap is to minimize what's observable beyond the formal contract — which is exactly what code generation and binary wire formats do.

- Schema registries are the only common mechanism that enforces compatibility at the infrastructure level, rejecting incompatible schema changes before they reach any consumer. This makes them uniquely valuable in event-driven systems where coordination is impractical.

- Versioning is a tool for managing contract evolution, not a substitute for understanding wire compatibility. Every active version is a contract you're maintaining whether you acknowledge it or not.

[← Back to Home]({{ "/" | relative_url }})
