# Day 20 — Concurrency Patterns

## Learning Objectives
- Apply real-world concurrency patterns
- Implement fan-out/fan-in, worker pools, rate limiting
- Use errgroup for concurrent error propagation
- Understand when concurrency helps vs hurts

---

## Worker Pool

A fixed number of goroutines process jobs from a shared queue:

```go
func workerPool(numWorkers int, jobs <-chan Job) <-chan Result {
    results := make(chan Result)

    var wg sync.WaitGroup
    for i := 0; i < numWorkers; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for job := range jobs {
                results <- process(job)
            }
        }()
    }

    // Close results when all workers are done
    go func() {
        wg.Wait()
        close(results)
    }()

    return results
}

// Usage
jobs := make(chan Job, 100)
results := workerPool(5, jobs)

for _, j := range myJobs {
    jobs <- j
}
close(jobs)

for r := range results {
    fmt.Println(r)
}
```

---

## errgroup — Concurrent Calls with Error Propagation

`golang.org/x/sync/errgroup` is the standard for running goroutines where any failure should cancel the rest:

```go
import "golang.org/x/sync/errgroup"

func fetchAll(ctx context.Context, urls []string) ([][]byte, error) {
    g, ctx := errgroup.WithContext(ctx)
    results := make([][]byte, len(urls))

    for i, url := range urls {
        i, url := i, url  // capture for goroutine
        g.Go(func() error {
            data, err := fetchURL(ctx, url)
            if err != nil {
                return fmt.Errorf("fetchURL %s: %w", url, err)
            }
            results[i] = data
            return nil
        })
    }

    if err := g.Wait(); err != nil {
        return nil, err
    }
    return results, nil
}
```

`errgroup.WithContext` cancels the derived context when any goroutine returns an error.

---

## Rate Limiting

Use `time.Ticker` or `golang.org/x/time/rate` to control throughput:

```go
// Simple rate limiter with ticker
limiter := time.NewTicker(200 * time.Millisecond)  // 5 requests/second
defer limiter.Stop()

for _, req := range requests {
    <-limiter.C  // wait for the next tick
    go handle(req)
}
```

For token bucket (burst support):
```go
import "golang.org/x/time/rate"

limiter := rate.NewLimiter(rate.Every(200*time.Millisecond), 5)  // 5 req/s, burst 5

ctx := context.Background()
for _, req := range requests {
    if err := limiter.Wait(ctx); err != nil {
        return err
    }
    go handle(req)
}
```

---

## Pipeline with Cancellation

A production-grade pipeline that propagates cancellation:

```go
func pipeline(ctx context.Context, source <-chan int) <-chan int {
    out := make(chan int)

    go func() {
        defer close(out)
        for v := range source {
            select {
            case out <- v * v:
            case <-ctx.Done():
                return
            }
        }
    }()

    return out
}
```

---

## Or-Done Channel

Wrap any channel to make it respect cancellation:

```go
func orDone(ctx context.Context, c <-chan int) <-chan int {
    out := make(chan int)
    go func() {
        defer close(out)
        for {
            select {
            case <-ctx.Done():
                return
            case v, ok := <-c:
                if !ok {
                    return
                }
                select {
                case out <- v:
                case <-ctx.Done():
                    return
                }
            }
        }
    }()
    return out
}
```

---

## Scatter/Gather (Fan-out then Fan-in)

Distribute work and collect results:

```go
func scatterGather(ctx context.Context, inputs []Input) ([]Output, error) {
    type result struct {
        idx int
        out Output
        err error
    }

    results := make(chan result, len(inputs))

    for i, inp := range inputs {
        i, inp := i, inp
        go func() {
            out, err := process(ctx, inp)
            results <- result{i, out, err}
        }()
    }

    outputs := make([]Output, len(inputs))
    for range inputs {
        r := <-results
        if r.err != nil {
            return nil, r.err
        }
        outputs[r.idx] = r.out
    }
    return outputs, nil
}
```

---

## Bounded Parallelism

Limit concurrency to N at a time using a semaphore channel:

```go
const maxConcurrent = 10

func processAll(ctx context.Context, items []Item) error {
    sem := make(chan struct{}, maxConcurrent)
    g, ctx := errgroup.WithContext(ctx)

    for _, item := range items {
        item := item
        sem <- struct{}{}  // acquire
        g.Go(func() error {
            defer func() { <-sem }()  // release
            return process(ctx, item)
        })
    }
    return g.Wait()
}
```

---

## When Concurrency Helps vs Hurts

**Helps when:**
- I/O-bound work (network calls, file reads) — goroutines wait, not CPU-spin
- Embarrassingly parallel tasks (batch processing, map-reduce)
- Fan-out calls to independent services

**Hurts when:**
- CPU-bound with heavy locking — contention slows everything
- Simple sequential logic — concurrency adds complexity for no gain
- Short tasks — goroutine startup + channel overhead exceeds task time

---

## Gotchas

1. **errgroup vs WaitGroup** — prefer `errgroup` for goroutines that return errors; it aggregates and propagates them.
2. **Closing a results channel too early** — use a goroutine that waits for all workers, then closes.
3. **Shared mutable slice from concurrent goroutines** — safe if each goroutine writes to its own index; not safe otherwise.
4. **Context not checked in tight loops** — always `select` on `ctx.Done()` inside long-running work.

---

## Practice

1. Build a worker pool with 4 workers that downloads URLs concurrently.
2. Use `errgroup` to make 3 API calls concurrently and fail fast on any error.
3. Implement a rate limiter that allows at most 5 requests per second.
4. Implement scatter/gather to sum sub-ranges of a large slice concurrently.

---

## Key Takeaways

- Worker pool = fixed goroutines + shared job channel — controls memory and resource usage.
- `errgroup` is the right tool when concurrent goroutines need to propagate errors.
- Rate limiting prevents overwhelming external services — use ticker or `x/time/rate`.
- Check `ctx.Done()` in tight loops to make work cancellable.
