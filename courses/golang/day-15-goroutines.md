# Day 15 — Goroutines

## Learning Objectives
- Launch goroutines with `go`
- Understand the goroutine scheduler
- Know why you need synchronization
- Use `sync.WaitGroup` to wait for goroutines to finish

---

## What Is a Goroutine?

A goroutine is a **lightweight thread** managed by the Go runtime — not an OS thread. You can run thousands (even millions) of goroutines simultaneously.

```go
func sayHello(name string) {
    fmt.Println("Hello,", name)
}

func main() {
    go sayHello("Alice")  // launches a goroutine
    go sayHello("Bob")
    go sayHello("Carol")

    time.Sleep(100 * time.Millisecond)  // wait for goroutines (not the real solution — see below)
}
```

The `go` keyword before a function call launches it as a goroutine. Execution of the calling code continues immediately.

---

## The Problem with time.Sleep

`time.Sleep` is not a reliable way to wait for goroutines — too short and goroutines don't finish; too long and you waste time. Use `sync.WaitGroup`.

---

## sync.WaitGroup

`WaitGroup` waits for a collection of goroutines to finish:

```go
import "sync"

func main() {
    var wg sync.WaitGroup

    for i := 0; i < 5; i++ {
        wg.Add(1)          // increment counter before launching
        go func(id int) {
            defer wg.Done()  // decrement counter when done
            fmt.Println("worker", id)
        }(i)
    }

    wg.Wait()  // block until counter reaches 0
    fmt.Println("all workers done")
}
```

Rules:
- Call `wg.Add(n)` **before** launching the goroutine, not inside it.
- Call `wg.Done()` via `defer` — ensures it runs even if the goroutine panics.
- `wg.Wait()` blocks the caller until the counter hits 0.

---

## Anonymous Goroutines

```go
go func() {
    fmt.Println("I'm an anonymous goroutine")
}()  // note the () — immediately invoked
```

---

## Goroutine Lifecycle

- Goroutines are garbage-collected when they finish — no need to close them.
- A goroutine that leaks (blocks forever) is a **goroutine leak** — it stays in memory until the program exits.
- The `main` goroutine exiting terminates ALL other goroutines.

---

## Race Conditions

Without synchronization, concurrent access to shared data causes data races:

```go
// ❌ DATA RACE — don't do this
counter := 0
var wg sync.WaitGroup

for i := 0; i < 1000; i++ {
    wg.Add(1)
    go func() {
        defer wg.Done()
        counter++  // read-modify-write: not atomic
    }()
}
wg.Wait()
fmt.Println(counter)  // will NOT print 1000 — result is unpredictable
```

---

## Detecting Races: `-race` Flag

```bash
go run -race main.go
go test -race ./...
```

The race detector finds races at runtime — use it in tests and CI always.

---

## GOMAXPROCS — Parallel Execution

By default, Go uses all available CPUs:

```go
runtime.GOMAXPROCS(4)  // use 4 CPU cores (default is runtime.NumCPU())
```

---

## Goroutine vs OS Thread

| | OS Thread | Goroutine |
|---|---|---|
| Stack size | ~1-8 MB | ~2 KB (grows as needed) |
| Startup cost | Expensive | Very cheap |
| Scheduling | Kernel | Go runtime (M:N scheduling) |
| Typical count | Hundreds | Hundreds of thousands |

---

## The M:N Scheduler

Go multiplexes M goroutines onto N OS threads (N ≈ GOMAXPROCS). When a goroutine blocks on I/O, the thread switches to another goroutine — no wasted threads waiting.

---

## Common Pattern: Worker Pool

Limit concurrent goroutines to avoid overwhelming resources:

```go
func workerPool(jobs []Job, concurrency int) {
    var wg sync.WaitGroup
    sem := make(chan struct{}, concurrency)  // semaphore (covered more in Day 17)

    for _, job := range jobs {
        wg.Add(1)
        sem <- struct{}{}  // acquire slot
        go func(j Job) {
            defer wg.Done()
            defer func() { <-sem }()  // release slot
            process(j)
        }(job)
    }
    wg.Wait()
}
```

---

## Gotchas

1. **Loop variable capture** — the classic goroutine loop bug:
```go
// ❌ All goroutines may see the same value of i
for i := 0; i < 3; i++ {
    go func() {
        fmt.Println(i)  // captures i by reference
    }()
}

// ✅ Pass i as an argument
for i := 0; i < 3; i++ {
    go func(n int) {
        fmt.Println(n)
    }(i)
}
```

2. **Goroutine leak** — a goroutine blocked on a channel no one will send to is leaked. Always have a way to unblock/cancel.
3. **main exits too early** — if main returns, all goroutines are killed. Always wait with WaitGroup or a channel.

---

## Practice

1. Launch 5 goroutines that each print their ID. Wait for all to finish with `WaitGroup`.
2. Use `-race` flag to detect a race in a counter incremented by multiple goroutines.
3. Write a `workerPool` that processes a slice of integers concurrently, squaring each.
4. Demonstrate the loop variable capture bug and its fix.

---

## Key Takeaways

- `go f()` launches a goroutine — the cheapest unit of concurrency in Go.
- Always use `WaitGroup` (or channels) instead of `time.Sleep` to synchronize.
- Run tests with `-race` — the race detector is your best friend.
- The loop variable capture bug is the #1 goroutine gotcha.
