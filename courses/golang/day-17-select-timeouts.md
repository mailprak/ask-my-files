# Day 17 — Select & Timeouts

## Learning Objectives
- Use `select` to handle multiple channels
- Implement timeouts with `time.After`
- Use non-blocking channel operations
- Combine `select` with `context` for cancellation

---

## select Statement

`select` waits on multiple channel operations simultaneously, picking whichever is ready first. If multiple are ready, one is chosen at random.

```go
select {
case v := <-ch1:
    fmt.Println("received from ch1:", v)
case v := <-ch2:
    fmt.Println("received from ch2:", v)
case ch3 <- 42:
    fmt.Println("sent to ch3")
}
```

---

## select Blocks Until One Case Is Ready

```go
func main() {
    c1 := make(chan string)
    c2 := make(chan string)

    go func() {
        time.Sleep(1 * time.Second)
        c1 <- "one"
    }()

    go func() {
        time.Sleep(2 * time.Second)
        c2 <- "two"
    }()

    for i := 0; i < 2; i++ {
        select {
        case msg := <-c1:
            fmt.Println("received:", msg)
        case msg := <-c2:
            fmt.Println("received:", msg)
        }
    }
}
// Prints "received: one" after 1s, "received: two" after 2s
```

---

## Timeout with time.After

`time.After(d)` returns a channel that receives after duration `d`:

```go
select {
case result := <-doWork():
    fmt.Println("got result:", result)
case <-time.After(2 * time.Second):
    fmt.Println("timed out")
}
```

---

## Non-blocking Channel Operations (default)

A `select` with a `default` case never blocks — it takes `default` immediately if no channel is ready:

```go
ch := make(chan int, 1)

// Non-blocking send
select {
case ch <- 42:
    fmt.Println("sent")
default:
    fmt.Println("channel full, dropped")
}

// Non-blocking receive
select {
case v := <-ch:
    fmt.Println("got:", v)
default:
    fmt.Println("nothing to receive")
}
```

---

## Polling Loop with Timeout

```go
func pollUntilReady(ready <-chan bool, timeout time.Duration) bool {
    deadline := time.After(timeout)
    tick := time.NewTicker(100 * time.Millisecond)
    defer tick.Stop()

    for {
        select {
        case <-ready:
            return true
        case <-deadline:
            return false
        case <-tick.C:
            fmt.Println("still waiting...")
        }
    }
}
```

---

## Quit Channel Pattern

A common pattern to stop a goroutine from outside:

```go
func worker(jobs <-chan Job, quit <-chan struct{}) {
    for {
        select {
        case job := <-jobs:
            process(job)
        case <-quit:
            fmt.Println("worker stopping")
            return
        }
    }
}

// Usage
quit := make(chan struct{})
go worker(jobs, quit)

// Later, to stop the worker:
close(quit)  // unblocks every goroutine waiting on <-quit
```

---

## select with nil Channels

A nil channel blocks forever in a select — useful for disabling a case dynamically:

```go
var ch1 chan int = nil
ch2 := make(chan int)

// The case `<-ch1` never fires — effectively disabled
select {
case v := <-ch1:     // never selected (nil channel)
    fmt.Println(v)
case v := <-ch2:
    fmt.Println("ch2:", v)
}
```

Pattern: set a channel to nil to disable a case after it fires once.

```go
for {
    select {
    case v, ok := <-ch1:
        if !ok {
            ch1 = nil  // disable this case
        } else {
            handle(v)
        }
    case v, ok := <-ch2:
        if !ok {
            ch2 = nil
        } else {
            handle(v)
        }
    }
    if ch1 == nil && ch2 == nil {
        break
    }
}
```

---

## time.Ticker — Repeated Intervals

```go
ticker := time.NewTicker(500 * time.Millisecond)
defer ticker.Stop()  // always stop to release resources

for {
    select {
    case t := <-ticker.C:
        fmt.Println("tick at", t)
    case <-done:
        fmt.Println("stopping")
        return
    }
}
```

---

## Gotchas

1. **`time.After` leaks if the channel is never received** — in a loop, use `time.NewTimer` and reset, or `time.NewTicker` for periodic ticks.
2. **Random selection** — when multiple cases are ready simultaneously, selection is random. Don't rely on ordering.
3. **`default` makes select non-blocking** — be careful; a hot loop with `default` burns CPU.
4. **Forgetting `defer ticker.Stop()`** — tickers allocate resources; always stop them.

```go
// ❌ time.After in a loop leaks timers
for {
    select {
    case <-ch:
        // ...
    case <-time.After(1 * time.Second):  // new timer every iteration — leaked!
        // ...
    }
}

// ✅ Use a timer outside the loop
timer := time.NewTimer(1 * time.Second)
defer timer.Stop()
for {
    select {
    case <-ch:
        // ...
    case <-timer.C:
        // ...
    }
}
```

---

## Practice

1. Write a function that returns the result of whichever of two channels sends first.
2. Wrap a slow operation with a 500ms timeout using `time.After`.
3. Implement a ticker that prints every second but stops after 5 ticks.
4. Write a non-blocking cache check: return from cache if available, else fetch.

---

## Key Takeaways

- `select` is Go's multi-channel wait — it blocks until one case is ready.
- `default` makes it non-blocking — useful for try-send/try-receive patterns.
- `time.After` for one-shot timeouts; `time.NewTicker` for periodic events (always stop it).
- A nil channel in a select is disabled — use this to turn cases on/off dynamically.
