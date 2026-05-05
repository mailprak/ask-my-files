# Day 18 — sync Package (Mutex, RWMutex, Once, Map)

## Learning Objectives
- Protect shared data with `sync.Mutex` and `sync.RWMutex`
- Use `sync.Once` for one-time initialization
- Understand `sync.Map` for concurrent-safe maps
- Know when to use mutex vs channels

---

## sync.Mutex

A `Mutex` provides mutual exclusion — only one goroutine holds the lock at a time.

```go
import "sync"

type SafeCounter struct {
    mu    sync.Mutex
    count int
}

func (c *SafeCounter) Increment() {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.count++
}

func (c *SafeCounter) Value() int {
    c.mu.Lock()
    defer c.mu.Unlock()
    return c.count
}

// Usage
counter := &SafeCounter{}
var wg sync.WaitGroup

for i := 0; i < 1000; i++ {
    wg.Add(1)
    go func() {
        defer wg.Done()
        counter.Increment()
    }()
}
wg.Wait()
fmt.Println(counter.Value())  // 1000 (always)
```

**Always `defer mu.Unlock()`** immediately after `Lock()` — ensures unlock even on panic or early return.

---

## sync.RWMutex — Read/Write Lock

Multiple readers can hold the lock simultaneously. Writers get exclusive access.

```go
type SafeMap struct {
    mu   sync.RWMutex
    data map[string]string
}

func (m *SafeMap) Set(k, v string) {
    m.mu.Lock()         // exclusive write lock
    defer m.mu.Unlock()
    m.data[k] = v
}

func (m *SafeMap) Get(k string) (string, bool) {
    m.mu.RLock()        // shared read lock
    defer m.mu.RUnlock()
    v, ok := m.data[k]
    return v, ok
}
```

Use `RWMutex` when reads vastly outnumber writes — it dramatically improves read throughput.

---

## sync.Once — Run Exactly Once

`sync.Once` ensures a function runs only once, even when called from multiple goroutines:

```go
var (
    instance *Database
    once     sync.Once
)

func GetDatabase() *Database {
    once.Do(func() {
        instance = &Database{
            conn: openConnection(),
        }
    })
    return instance
}
```

This is the idiomatic lazy singleton in Go. Thread-safe, no double-check needed.

---

## sync.Map — Concurrent-Safe Map

`sync.Map` is optimized for two specific use cases:
1. Keys are written once but read many times (caches)
2. Multiple goroutines operate on disjoint key sets

```go
var m sync.Map

// Store
m.Store("key", "value")

// Load
if v, ok := m.Load("key"); ok {
    fmt.Println(v.(string))  // need type assertion — sync.Map stores interface{}
}

// LoadOrStore — atomic: load if exists, store if not
actual, loaded := m.LoadOrStore("key", "default")
if loaded {
    fmt.Println("already had:", actual)
}

// Delete
m.Delete("key")

// Iterate
m.Range(func(k, v any) bool {
    fmt.Println(k, v)
    return true  // return false to stop iteration
})
```

**Limitation:** `sync.Map` stores `any`, so you lose type safety. For most cases, `map` + `sync.RWMutex` is clearer.

---

## sync.WaitGroup — Revisited

```go
var wg sync.WaitGroup

wg.Add(3)
go func() { defer wg.Done(); work1() }()
go func() { defer wg.Done(); work2() }()
go func() { defer wg.Done(); work3() }()
wg.Wait()
```

Key point: `wg.Add` must happen **before** the goroutine starts, not inside it.

---

## sync.Cond — Condition Variable

`sync.Cond` is for when goroutines need to wait for a condition to be true:

```go
var mu sync.Mutex
cond := sync.NewCond(&mu)
ready := false

// Waiter goroutine
go func() {
    mu.Lock()
    for !ready {
        cond.Wait()  // atomically unlocks mu and suspends
    }
    fmt.Println("condition met")
    mu.Unlock()
}()

// Notifier
time.Sleep(time.Second)
mu.Lock()
ready = true
cond.Signal()   // wake one waiter (or Broadcast to wake all)
mu.Unlock()
```

`sync.Cond` is rarely needed — channels usually express this better.

---

## Mutex vs Channels: When to Use Which

| Use mutex when... | Use channels when... |
|---|---|
| Protecting a shared data structure | Passing data between goroutines |
| Critical section is short and local | Signaling completion or events |
| Cache or counter | Pipeline / producer-consumer |
| Implementing a thread-safe type | Coordinating goroutine lifecycle |

Rob Pike's rule: **"Don't communicate by sharing memory; share memory by communicating."** But for simple counters and caches, a mutex is clearer.

---

## Gotchas

1. **Copying a mutex** — mutexes must not be copied after first use. Embed or use a pointer:
```go
// ❌ Copying a mutex
type Bad struct {
    mu sync.Mutex
}
b1 := Bad{}
b2 := b1   // mutex is copied — b2.mu is in an inconsistent state

// ✅ Use pointer
b3 := &Bad{}
```

2. **Holding a lock across a blocking operation** — if you hold a lock and then block on I/O or a channel, you're starving other goroutines.

3. **Double unlock** — calling `Unlock` twice panics. Always use `defer`.

4. **Re-entrant locks don't exist** — calling `Lock()` from the same goroutine that holds the lock deadlocks.

---

## Practice

1. Write a `SafeCache` with `Get(key)` and `Set(key, value)` using `sync.RWMutex`.
2. Implement a lazy-initialized global connection pool using `sync.Once`.
3. Run a concurrent word-frequency counter on a slice of strings, protecting the map.
4. Run `go test -race` and confirm the mutex removes the data race.

---

## Key Takeaways

- `sync.Mutex` for exclusive access; `sync.RWMutex` for read-heavy concurrent access.
- `defer mu.Unlock()` immediately after `Lock()` — never forget the unlock.
- `sync.Once` for one-time initialization (singletons, lazy loading).
- Never copy a mutex — pass by pointer or embed in a struct used by pointer.
