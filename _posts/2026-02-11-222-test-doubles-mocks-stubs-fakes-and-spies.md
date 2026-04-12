---
layout: post
title: "2.2.2 Test Doubles: Mocks, Stubs, Fakes, and Spies"
author: "Glenn Lum"
date:   2026-02-11 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers use the word "mock" to mean "any fake thing I put in place of a real dependency during a test." This imprecision is not just a vocabulary problem. Each type of test double substitutes something different, verifies something different, and fails in a different way when misused. When you reach for a mock but the situation calls for a fake, or when you verify interactions with a mock when you should be verifying state with a stub, you get tests that are tightly coupled to implementation details, that pass when the real system is broken, and that break when you refactor code that still works. The choice of test double *is* a design decision about what your test actually measures. Getting it wrong means your test suite is confidently asserting things that don't matter.

## What a Test Double Actually Substitutes

A **test double** is any object that stands in for a real dependency during a test. The Level 1 post described unit tests as "fast, isolated tests that validate behavior in complete isolation from external dependencies." Test doubles are the mechanism that makes that isolation possible. But "standing in" for a dependency is not one thing. There are at least four meaningfully different ways to do it, and they differ along two axes.

The first axis is **what the double provides to the system under test**. Some doubles control the *indirect inputs* — the data your code receives from its dependencies. Others provide a *working alternative implementation* that behaves like the real thing but is cheaper to run.

The second axis is **what the double allows you to verify**. Some doubles exist purely to keep your code running during the test; you never inspect the double itself. Others exist specifically so you can assert things about how your code interacted with them.

These two axes produce the four types that matter in practice.

## Stubs: Controlling Indirect Inputs

A **stub** provides predetermined responses to method calls. Its job is to control what your system under test *receives* from its dependencies, so you can test how your code behaves under specific conditions. You never assert anything about the stub itself.

Consider an order service that depends on a payment gateway:

```python
# The stub
class AlwaysSuccessfulPaymentGateway:
    def charge(self, customer_id, amount):
        return ChargeResult(success=True, transaction_id="txn-stub-123")

# The test
def test_order_confirmation_includes_transaction_id():
    gateway = AlwaysSuccessfulPaymentGateway()
    service = OrderService(payment_gateway=gateway, inventory=real_or_other_double)
    
    confirmation = service.place_order(some_order)
    
    assert confirmation.transaction_id == "txn-stub-123"
```

The stub answers the question: "Given that the payment succeeds, does my order service do the right thing with the result?" You are testing your code's logic. The stub is scenery, not the subject.

Stubs are the right choice when you need to put the system under test into a specific state or condition — successful payment, failed payment, network timeout, empty response — and then verify the *output or state* of the thing you're actually testing. This is **state verification**: you check what your system produced, not how it talked to its dependencies.

## Mocks: Verifying Indirect Outputs

A **mock** is pre-programmed with expectations about how it will be called, and the test fails if those expectations aren't met. Its job is to verify that your code sends the right messages to its collaborators. This is **behavior verification**.

```python
def test_order_service_charges_correct_amount():
    gateway = Mock()
    gateway.charge.return_value = ChargeResult(success=True, transaction_id="txn-1")
    
    service = OrderService(payment_gateway=gateway, inventory=stub_inventory)
    service.place_order(Order(customer_id="cust-42", total=99.99, ...))
    
    gateway.charge.assert_called_once_with("cust-42", 99.99)
```

Here, the assertion is *about the mock itself*. You're verifying that your order service called `charge` with the right customer ID and the right amount. The mock isn't just scenery — it's the measurement instrument.

Mocks are the right choice when the *interaction itself is the behavior you care about*. Sending an email after order placement, publishing an event to a message bus, writing an audit log — these are cases where the side effect is the whole point, and there's no meaningful return value to check.

The critical distinction: stubs answer "given this input from my dependency, does my code produce the right output?" Mocks answer "does my code talk to its dependency in the right way?" These are different questions. Confusing them is the root cause of most test double misuse.

## Fakes: Lightweight Working Implementations

A **fake** is a real, working implementation that takes a shortcut that makes it unsuitable for production. An in-memory database instead of PostgreSQL. A local filesystem store instead of S3. A hash map pretending to be a cache server.

```python
class InMemoryInventoryService:
    def __init__(self):
        self.stock = {}
    
    def add_stock(self, item_id, quantity):
        self.stock[item_id] = self.stock.get(item_id, 0) + quantity
    
    def check_stock(self, item_id, quantity):
        return self.stock.get(item_id, 0) >= quantity
    
    def reserve(self, item_id, quantity):
        if not self.check_stock(item_id, quantity):
            raise OutOfStockError()
        self.stock[item_id] -= quantity
```

Unlike a stub, this fake has *real behavior*. You can add stock, check stock, reserve items, and the internal state changes accordingly. Unlike a mock, you don't assert how it was called — you use it as a working dependency and verify the outcome of the whole operation.

Fakes are the right choice when your test needs a dependency that *behaves realistically* but where the real thing is too slow, too expensive, or too difficult to set up. They shine in scenarios where the interaction between your code and the dependency is complex enough that a stub's canned responses would be too simplistic to exercise the real logic paths.

The cost of fakes is that they are real code. They need to be written, maintained, and — ideally — validated against the real implementation they replace. A fake that behaves differently from the real system is a lie that your tests tell you.

## Spies: Recording What Happened

A **spy** wraps an object (real or not) and silently records every interaction, letting you inspect those interactions after the fact. The difference from a mock is timing and coupling: a mock's expectations are declared *before* the act, and the test fails immediately if the expectation isn't met. A spy records everything and you query it *after* the act, asserting only on the interactions you care about.

```python
def test_order_service_publishes_event():
    event_bus = SpyEventBus(real_event_bus)
    service = OrderService(event_bus=event_bus, ...)
    
    service.place_order(some_order)
    
    assert event_bus.was_called_with("OrderPlaced", order_id=some_order.id)
    # We don't care about other calls to event_bus — only this one
```

Spies are less prescriptive than mocks. A mock that expects exactly two calls in a specific order will fail if your refactored code makes three calls or changes the order. A spy lets you assert on the things that matter and ignore the rest. This makes spy-based tests marginally less brittle, though they still couple you to interaction patterns.

In practice, many modern mocking frameworks (Mockito, unittest.mock, Jest) blur the line between mocks and spies. When you use `unittest.mock.Mock()` in Python and call `assert_called_with` after the fact, you're using it as a spy even though the class is called `Mock`. The conceptual distinction matters more than the framework's naming.

## The Substitution Boundary

Every time you use a test double, you are drawing an invisible line around the system under test. Everything inside the line runs as real code. Everything outside the line is replaced with a double. **Where you draw this line determines what your test actually tests.**

Draw the boundary too tightly — replace every collaborator of a class with a mock — and your test verifies only that the class calls its collaborators in the right order with the right arguments. It tests *wiring*, not *behavior*. You can refactor the internal logic of the class, maintaining identical external behavior, and every test breaks because the call sequence changed.

Draw the boundary too loosely — use all real dependencies — and you're writing an integration test. That's not wrong, but it's not a unit test, and it comes with integration test costs: slower execution, infrastructure requirements, harder failure diagnosis.

The skill is in drawing the boundary at the level where your test verifies something you genuinely care about. For a function that transforms data, you probably don't need any doubles — pass data in, check data out. For a service that orchestrates calls to three external systems, you need doubles for those external systems, but you might let the internal helper classes run as real code. The boundary should follow the architectural seam, not the class hierarchy.

## Where Test Doubles Break

### Mock-Heavy Tests That Test Implementation

The most common failure mode is overusing mocks for behavior verification when state verification would suffice. You see this in codebases where every test constructs five mocks, wires them together, calls the method under test, and then asserts that each mock was called exactly once with specific arguments. These tests are exhausting to read, break every time someone refactors, and tell you almost nothing about whether the system works correctly.

The symptom is: your tests break when you change *how* code works but not *what* it does. If you refactor a method to batch two database calls into one for performance, and a dozen tests break because they expected two calls instead of one, those tests were testing implementation details. They provided negative value — they cost time to fix and never could have caught a real bug.

### Stubs That Encode Stale Assumptions

Every stub contains a hardcoded assumption about what the real dependency returns. If the real dependency changes — a new required field in the response, a different error format, a changed status code — your stubs still return the old structure. Your tests pass. Production breaks.

This is the fundamental limitation of stubs: they freeze a dependency's behavior at the time you wrote the stub. They don't keep up with reality. Contract tests (as described in the Level 1 post) exist specifically to close this gap, but many teams use stubs without contract tests and silently accumulate incorrect assumptions.

### Fakes That Diverge

A fake is a parallel implementation of a real system. Two implementations of the same behavior will eventually diverge. Your in-memory database fake doesn't enforce the same constraint semantics as PostgreSQL. Your fake S3 doesn't replicate eventual consistency or the exact error behavior of the real service. Tests pass against the fake and fail in production because the fake was a simplification, and the behavior that matters was in the part that was simplified away.

The discipline required: fakes should be tested against the same interface contract as the real implementation. Some teams run their test suite against both the fake and the real dependency in CI, using the real dependency run to validate that the fake hasn't drifted. This is expensive but it's the only reliable way to maintain a fake long-term.

### The Green Suite, Broken Integration

The deepest failure mode is structural, not specific to any one type of double. A team with 95% unit test coverage, all using test doubles for external dependencies, can have a perfectly green test suite and a completely broken system. Every class works perfectly against its doubles. No class works correctly against the real dependencies.

This happens because test doubles verify that your code works *given your assumptions about the outside world*. They cannot verify that your assumptions are correct. Only integration tests against real dependencies — or contract tests that formalize those assumptions and verify them independently — close the loop.

## The Mental Model

Test doubles are not interchangeable. Each type controls a different axis of the test. Stubs and fakes control the *environment* — they shape what your code sees, so you can test your logic under specific conditions. Mocks and spies verify the *interactions* — they check that your code communicates correctly with its collaborators. The choice between them is a choice about what your test measures.

The question to ask before reaching for any test double is: "Am I testing what my code *does*, or am I testing how my code *talks*?" If the answer is what it does, use stubs or fakes and verify state. If the answer is how it talks — because the communication *is* the behavior — use mocks or spies and verify interactions. If you can't clearly articulate which one, you don't yet know what your test is for.

## Key Takeaways

- **Stubs control indirect inputs** — they provide canned responses so you can test how your code behaves under specific conditions, and you verify the output of your code, not the stub itself.
- **Mocks verify indirect outputs** — they assert that your code called the right methods with the right arguments, making them appropriate only when the interaction itself is the behavior you care about.
- **Fakes are working implementations with shortcuts** — they have real behavior (unlike stubs) but are unsuitable for production, and they require ongoing maintenance to prevent divergence from the real system.
- **Spies record interactions for after-the-fact verification**, making them less prescriptive and less brittle than mocks, though most modern frameworks blur the distinction between the two.
- **The substitution boundary — where you draw the line between real code and test doubles — determines what your test actually tests.** Drawing it too tight tests wiring; drawing it too loose tests integration.
- **Overusing mocks for behavior verification produces tests that break on every refactor** without catching real bugs, because they assert *how* code works rather than *what* it does.
- **Every stub and fake encodes assumptions about real dependencies that go stale over time.** Without contract tests or validation against real implementations, a green test suite can mask broken integrations.
- **Before choosing a test double, ask whether you are testing what your code does or how your code talks** — that question determines whether you need state verification (stubs/fakes) or behavior verification (mocks/spies).


[← Back to Home]({{ "/" | relative_url }})
