# Day 19 — Context Package

## Learning Objectives
- Understand what a context carries and why it matters
- Use `context.WithCancel`, `WithTimeout`, `WithDeadline`
- Pass context through call chains
- Use `context.WithValue` correctly (and sparingly)

---

## Why context?

When a request comes in to a server, it may spawn many goroutines for DB queries, downstream calls, etc. When the client cancels (or a timeout fires), all those goroutines need to stop. `context.Context` is how that cancellation signal flows through the call chain.

---

## The context.Context Interface

```go
type Context interface {
    Deadline() (deadline time.Time, ok bool)  // when will it expire?
    Done() <-chan struct{}                     // closed when cancelled/expired
    Err() error                               // why was it cancelled?
    Value(key any) any                        // request-scoped values
}
```

---

## Background and TODO

```go
ctx := context.Background()  // root context — use at program entry points, tests
ctx := context.TODO()        // placeholder — use when you'll add a real context later
```

Never pass `nil` as a context — use `context.Background()`.

---

## WithCancel — Manual Cancellation

```go
ctx, cancel := context.WithCancel(context.Background())
defer cancel()  // always defer cancel to avoid context leak

go func(ctx context.Context) {
    for {
        select {
        case <-ctx.Done():
            fmt.Println("goroutine cancelled:", ctx.Err())
            return
        default:
            doWork()
        }
    }
}(ctx)

time.Sleep(2 * time.Second)
cancel()  // signal all goroutines using this context to stop
```

**Always `defer cancel()`** — even if you call cancel manually, the defer ensures cleanup.

---

## WithTimeout — Automatic Cancellation After Duration

```go
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()

result, err := fetchData(ctx)
if err != nil {
    if errors.Is(err, context.DeadlineExceeded) {
        fmt.Println("request timed out")
    }
}
```

---

## WithDeadline — Cancel at Specific Time

```go
deadline := time.Now().Add(5 * time.Second)
ctx, cancel := context.WithDeadline(context.Background(), deadline)
defer cancel()
```

`WithTimeout(ctx, d)` is shorthand for `WithDeadline(ctx, time.Now().Add(d))`.

---

## Passing Context Through Functions

**The first parameter convention:** every function that does I/O, calls a service, or might be cancelled should accept a `context.Context` as its first parameter named `ctx`.

```go
func fetchUser(ctx context.Context, id int) (*User, error) {
    req, _ := http.NewRequestWithContext(ctx, "GET", userURL(id), nil)
    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return nil, fmt.Errorf("fetchUser: %w", err)
    }
    defer resp.Body.Close()
    // ...
}

func getProfile(ctx context.Context, id int) (*Profile, error) {
    user, err := fetchUser(ctx, id)
    if err != nil {
        return nil, err
    }
    // ...
}
```

---

## Checking Cancellation

```go
func processItems(ctx context.Context, items []Item) error {
    for _, item := range items {
        // Check before each expensive operation
        select {
        case <-ctx.Done():
            return ctx.Err()
        default:
        }

        if err := process(ctx, item); err != nil {
            return err
        }
    }
    return nil
}
```

---

## context.WithValue — Request-Scoped Values

Attach request-scoped values (request ID, user ID, auth token) to a context:

```go
type contextKey string

const RequestIDKey contextKey = "requestID"

// Set
ctx = context.WithValue(ctx, RequestIDKey, "abc-123")

// Get
if id, ok := ctx.Value(RequestIDKey).(string); ok {
    fmt.Println("request ID:", id)
}
```

**Rules for `WithValue`:**
- Always use a custom unexported key type (not string/int) to avoid collisions.
- Only for request-scoped data (request ID, auth token, tracing span).
- Never for optional parameters — use function arguments instead.

---

## Using Context with Standard Library

```go
// database/sql
rows, err := db.QueryContext(ctx, "SELECT * FROM users WHERE id = $1", id)

// net/http
req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
resp, err := client.Do(req)

// exec
cmd := exec.CommandContext(ctx, "git", "status")
out, err := cmd.Output()
```

All standard library I/O functions have a `Context` variant.

---

## Context Propagation Pattern (HTTP Server)

```go
func handler(w http.ResponseWriter, r *http.Request) {
    ctx := r.Context()  // HTTP server already provides a context

    // Add request ID
    ctx = context.WithValue(ctx, RequestIDKey, generateID())

    // Set operation timeout
    ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
    defer cancel()

    result, err := businessLogic(ctx)
    if err != nil {
        http.Error(w, err.Error(), 500)
        return
    }
    json.NewEncoder(w).Encode(result)
}
```

---

## Gotchas

1. **Never store a context in a struct** — pass it as the first function parameter.
2. **Always `defer cancel()`** — failing to cancel leaks the goroutine that monitors the parent.
3. **`context.WithValue` key type must be unexported** — use `type myKey struct{}` not `"string"` to prevent collisions across packages.
4. **Cancelled context means stop, not retry** — if `ctx.Err() != nil`, don't retry; propagate the error.

---

## Practice

1. Write a `fetchWithTimeout(url string, timeout time.Duration) ([]byte, error)` using `context.WithTimeout`.
2. Write a loop that processes items but checks `ctx.Done()` before each item.
3. Implement request ID propagation through 3 nested function calls using `context.WithValue`.
4. Show what happens when a parent context is cancelled — all children are cancelled too.

---

## Key Takeaways

- `context.Context` is Go's standard mechanism for cancellation, deadlines, and request-scoped values.
- Pass context as the **first parameter** to every function that does I/O or long work.
- Always `defer cancel()` to avoid goroutine leaks.
- Use `context.WithValue` sparingly and only with custom unexported key types.
