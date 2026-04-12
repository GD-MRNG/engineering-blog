---
layout: post
title: "2.2.4 Contract Testing: How Services Agree on Interfaces"
author: "Glenn Lum"
date:   2026-02-13 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers, when they first hear about contract testing, mentally file it as "schema validation between services." They picture something that checks whether Service A sends a JSON body that matches the shape Service B expects. That understanding is close enough to pass a conversation but wrong enough to produce a broken implementation. Contract testing is not about validating schemas. It is about capturing what a consumer actually does with a provider's API — the specific requests it makes and the specific parts of the response it relies on — and turning those expectations into independently verifiable tests on both sides. The directionality matters. The specificity matters. The independence matters. Getting any of those wrong produces a test suite that either catches nothing useful or becomes so brittle it gets abandoned.

## Why the Consumer Drives the Contract

The defining mechanic of contract testing — the thing that separates it from API schema validation or integration tests with mocks — is that **the consumer defines the contract, not the provider**.

This is counterintuitive. In most testing paradigms, the provider is the source of truth. The provider publishes an API spec. Consumers conform to it. If a consumer sends a malformed request, that is the consumer's problem. Contract testing inverts this. The consumer says: "Here are the specific API calls I make and the specific fields I read from the response." That declaration becomes the contract.

Why invert it? Because in a microservices system, the failure you are trying to prevent is not "the provider changed its API spec." That is visible. The failure you are trying to prevent is "the provider changed something it did not realize a consumer depended on." A provider might add a field, rename an internal enum value that leaks into a response, change a date format from ISO 8601 to Unix timestamps, or start returning `null` where it previously returned an empty array. None of these necessarily violate the provider's own API documentation. All of them can break a consumer in production.

Consumer-driven contracts make the implicit explicit. If Service A reads the `email` and `status` fields from a `/users/{id}` response, the contract says exactly that — and nothing more. Service A does not care about the other fifteen fields in the response. It does not care about the provider's internal data model. It cares about two fields and their types. This precision is the mechanism that allows contracts to be both stable and useful: they are narrow enough to avoid breaking on irrelevant changes and specific enough to catch the changes that actually matter.

## What a Contract Actually Contains

A contract is a collection of **interactions**. Each interaction is a pair: a request the consumer makes and the minimum response the consumer needs to function.

In Pact — the most widely adopted contract testing framework — an interaction looks roughly like this:

```json
{
  "description": "a request for user 42",
  "request": {
    "method": "GET",
    "path": "/users/42",
    "headers": {
      "Accept": "application/json"
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "body": {
      "id": 42,
      "email": "user@example.com",
      "status": "active"
    }
  }
}
```

But the values in the body are not meant literally. The contract is not asserting that the email is literally `"user@example.com"`. It is asserting that there is a field called `email` and that its value is a string. This is where **matchers** do their work. In practice, the consumer test specifies matching rules:

```json
{
  "$.body.id": { "match": "type" },
  "$.body.email": { "match": "type" },
  "$.body.status": { "match": "regex", "regex": "^(active|inactive|suspended)$" }
}
```

This distinction between exact values and matching rules is critical. Exact-value contracts break on every provider change, even harmless ones. Matcher-based contracts break only when the structural expectations are violated — the field disappears, the type changes, or the value falls outside the expected range. Getting the matcher granularity right is one of the most consequential design decisions in a contract testing implementation. Too loose (everything is `"match": "type"`) and you miss real breakage. Too tight (exact string matching on dynamic values) and you get false failures on every test run.

## The Two-Phase Verification Workflow

Contract testing splits into two completely independent phases that run in separate codebases, in separate CI pipelines, at separate times.

### Phase 1: Consumer Side

The consumer team writes a test. In this test, the consumer's HTTP client code runs against a **mock provider** — a local stub server that the contract testing framework spins up. The test declares: "When I make this request, I expect this response." The framework records this expectation. If the consumer's code actually makes the declared request and correctly handles the declared response, the test passes. As a side effect, the framework serializes the interaction into a **contract file** (sometimes called a pact file).

The important thing here is that the consumer test is not testing the provider. It is testing the consumer's own code against its own stated expectations. The contract file is the artifact — the exportable, portable record of what the consumer needs.

### Phase 2: Provider Side

The provider team takes the contract file and replays it. The provider's real API (running locally or in a test environment) receives each request from the contract. The framework then checks: does the actual response satisfy the matchers defined in the contract? If the consumer expected a 200 with an `email` field of type string and the provider returns a 200 with an `email_address` field, the verification fails.

The provider does not need the consumer's code. It does not need the consumer to be running. It only needs the contract file. This is the independence that makes contract testing scalable: each side runs its own tests in its own pipeline on its own schedule.

### The Broker Connects the Two

In practice, the contract file moves from consumer to provider through a **contract broker** — a central service (Pact Broker or Pactflow being the most common) that stores contracts and verification results. The consumer publishes its contract after a successful consumer-side test. The provider fetches the latest contracts for all its consumers and verifies against them. The broker tracks which versions of which services have been verified against which contracts, creating a matrix of compatibility.

This matrix is what enables the **can-i-deploy** check: before deploying a new version of Service B, you query the broker: "Has this version of Service B been verified against the contracts of all consumers currently in production?" If yes, deploy. If not, stop. This is where contract testing connects directly to your deployment pipeline, and it is where most of the operational value actually lives.

## Provider States: The Complexity That Surprises Everyone

Consider a contract interaction that says: "When I request `GET /users/42`, I expect a 200 with user data." For the provider to satisfy this during verification, user 42 must exist in whatever data store the provider is using during the test. The contract does not create this data. Something else has to.

This is where **provider states** come in. Each interaction can declare a precondition: "Given that user 42 exists and is active." The provider's verification harness must include a state setup mechanism — a hook that runs before each interaction replay and puts the provider's data store into the required state.

```ruby
provider_state "user 42 exists and is active" do
  set_up do
    User.create(id: 42, email: "test@test.com", status: "active")
  end
  tear_down do
    User.delete(42)
  end
end
```

Provider state management is the part of contract testing that scales worst. For a provider with three consumers and a handful of interactions, it is manageable. For a provider with twenty consumers and hundreds of interactions, the state setup harness becomes a substantial piece of test infrastructure that must be maintained alongside the provider's actual code. When provider state setup breaks or drifts, verification failures become ambiguous: is the contract actually violated, or is the test data wrong?

## How This Differs from Schema Validation

OpenAPI specs, JSON Schema, gRPC protobuf definitions — these all define what a provider's API looks like. Contract tests define what a consumer actually uses. The distinction matters in both directions.

Schema validation is provider-centric and exhaustive. It describes every endpoint, every field, every possible response code. A contract is consumer-centric and minimal. It describes only the interactions one specific consumer cares about. A provider can have an OpenAPI spec with fifty endpoints, and a contract from Consumer A might cover three of them.

Schema validation catches "the response body does not conform to the published spec." Contract testing catches "the response body no longer contains what Consumer A is actually reading." These are different failure classes. A provider can ship a response that is perfectly valid according to its OpenAPI spec and still break a consumer, because the spec allows `null` for a field that the consumer's code does not handle. A contract for that consumer would encode the expectation that the field is non-null.

The two approaches are complementary, not competing. Schema validation protects the provider's structural commitments. Contract tests protect the consumer's operational assumptions.

## Where Contract Testing Breaks Down

**Contracts test structure, not semantics.** A contract can verify that a `status` field returns a string matching `active|inactive|suspended`. It cannot verify that the meaning of `suspended` has not changed. If the provider starts using `suspended` to mean "temporarily paused" instead of "permanently banned," every consumer that makes authorization decisions based on status will break, and the contract test will pass. Contract tests catch interface drift, not behavioral drift.

**Organizational friction is the real bottleneck.** Contract testing requires consumer and provider teams to share a contract format, share a broker, and coordinate on provider state naming conventions. In organizations where teams have strong autonomy and weak coordination, getting provider teams to run consumer contracts in their pipeline is a political problem, not a technical one. The framework is easy. The adoption is hard.

**Thin contracts give false confidence.** If the consumer test only declares a single interaction with a single field using a type matcher, the contract is technically valid but operationally useless. It will pass even when the provider has made breaking changes to every other aspect of the response. Contract quality depends entirely on how thoroughly the consumer team encodes their actual dependencies. There is no automated way to verify that a contract is complete — it requires discipline and review.

**Async interactions add complexity.** Contract testing originated in HTTP request-response contexts. Extending it to message-based systems (Kafka, RabbitMQ, SNS) is possible — Pact supports message pacts — but the model is less natural. There is no request-response pair to capture. Instead, you are verifying that a published message conforms to the shape the consumer expects. The provider verification step becomes "generate a message using my real code and check it against the contract," which requires different test harness infrastructure.

**Provider state explosion.** As the number of consumers grows, the number of distinct provider states grows combinatorially. Consumer A needs user 42 to be active. Consumer B needs user 42 to be suspended. Consumer C needs user 42 to not exist at all. The provider's state setup harness becomes a matrix of scenarios that must be maintained independently of the provider's own test suite. This is where contract testing's maintenance cost concentrates, and it is the primary reason teams abandon it.

## The Mental Model

Think of contract testing as a protocol for encoding and verifying assumptions across a service boundary. In any distributed system, every service call carries implicit assumptions: the consumer assumes certain fields will be present, certain types will be stable, certain status codes will mean certain things. These assumptions are invisible until they break. Contract testing makes them explicit, portable, and verifiable.

The key conceptual shift is that the unit of testing is not the provider's API and not the consumer's code — it is the **relationship between them**. A contract is an artifact of that relationship. It is generated by one side and verified by the other. It encodes not the full capability of the API but the subset that one specific consumer depends on. This is why it catches failures that unit tests (which never cross the boundary) and E2E tests (which cross it but too late and too slowly) cannot.

If you remember one thing: a contract test does not prove the provider works correctly. It does not prove the consumer works correctly. It proves that the two can still talk to each other. That narrow, specific guarantee is precisely what makes it valuable.

## Key Takeaways

- **Consumer-driven means the consumer defines the contract.** The consumer declares the requests it makes and the response fields it depends on; the provider verifies it can still satisfy those expectations. The directionality is the mechanism that catches unintentional breaking changes.

- **A contract is a collection of interactions, not a schema.** Each interaction is a specific request-response pair with matchers that define acceptable response shapes, not exact values.

- **The two phases — consumer test and provider verification — run independently in separate pipelines.** This independence is what makes contract testing fast and scalable compared to integration or E2E tests.

- **The contract broker and the can-i-deploy check are where contract testing connects to deployment safety.** Without them, contracts are just documentation. With them, they become deployment gates.

- **Provider state management is the primary maintenance cost.** Every interaction that requires specific test data creates a setup obligation on the provider side, and this grows with each new consumer.

- **Contract tests catch structural drift, not semantic drift.** If a field's type and name stay the same but its meaning changes, the contract will still pass. Contracts protect interfaces, not business logic.

- **Schema validation and contract testing solve different problems.** Schema validation ensures the provider conforms to its own spec. Contract testing ensures the provider still satisfies what specific consumers actually use.

- **The most common failure mode is thin contracts that test almost nothing.** A contract is only as useful as the assumptions it encodes. Incomplete contracts create false confidence that the integration is safe.

[← Back to Home]({{ "/" | relative_url }})
