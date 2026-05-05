# Day 13 — Defer, Panic & Recover

## Learning Objectives
- Use `defer` for cleanup and resource management
- Understand `defer` execution order and argument evaluation
- Know when `panic` is appropriate
- Use `recover` to handle panics gracefully

---

## defer

`defer` schedules a function call to run when the surrounding function returns — no matter how it returns (normal return, error return, or panic).

```go
func readFile(path string) error {
    f, err := os.Open(path)
    if err != nil {
        return err
    }
    defer f.Close()  // guaranteed to run when readFile returns

    // ... work with f
    return nil
}
```

---

## defer Execution Order: LIFO (Last In, First Out)

Multiple defers run in reverse order — the last `defer` runs first:

```go
func main() {
    defer fmt.Println("first deferred — runs last")
    defer fmt.Println("second deferred — runs second")
    defer fmt.Println("third deferred — runs first")

    fmt.Println("main body")
}
// Output:
// main body
// third deferred — runs first
// second deferred — runs second
// first deferred — runs last
```

This is useful for locking/unlocking: lock at the top, defer unlock immediately after.

---

## Argument Evaluation Happens Immediately

Defer captures the **argument values at the time of the defer call**, not when it executes:

```go
x := 10
defer fmt.Println("deferred x =", x)  // captures x=10 now
x = 20
fmt.Println("current x =", x)

// Output:
// current x = 20
// deferred x = 10
```

---

## Defer with Named Returns

Deferred functions can read AND modify named return values:

```go
func divide(a, b float64) (result float64, err error) {
    defer func() {
        if err != nil {
            err = fmt.Errorf("divide: %w", err)  // wrap on the way out
        }
    }()

    if b == 0 {
        err = errors.New("division by zero")
        return
    }
    result = a / b
    return
}
```

---

## Common defer Patterns

### Mutex unlock
```go
mu.Lock()
defer mu.Unlock()
```

### Database transaction
```go
tx, _ := db.Begin()
defer func() {
    if err != nil {
        tx.Rollback()
    } else {
        tx.Commit()
    }
}()
```

### Timing a function
```go
func timeIt(name string) func() {
    start := time.Now()
    return func() {
        fmt.Printf("%s took %v\n", name, time.Since(start))
    }
}

func expensiveOp() {
    defer timeIt("expensiveOp")()
    // ...
}
```

---

## panic

`panic` stops normal execution and unwinds the stack, running deferred functions along the way. It's for **truly unrecoverable situations**.

```go
func mustPositive(n int) int {
    if n <= 0 {
        panic(fmt.Sprintf("expected positive, got %d", n))
    }
    return n
}
```

**Use panic only when:**
- Programmer error that should never happen (invariant violation)
- Initialization failures that make the program useless

**Do NOT use panic** for ordinary error conditions — return an `error` instead.

---

## recover

`recover` is only useful inside a deferred function. It stops the panic and returns the panic value.

```go
func safeDiv(a, b int) (result int, err error) {
    defer func() {
        if r := recover(); r != nil {
            err = fmt.Errorf("caught panic: %v", r)
        }
    }()

    result = a / b  // panics if b == 0
    return
}

r, err := safeDiv(10, 0)
fmt.Println(r, err)  // 0 caught panic: runtime error: integer divide by zero
```

---

## The panic/recover Pattern for Parsers

A common pattern in recursive parsers: panic internally but recover at the boundary to return an error:

```go
type parseError struct{ msg string }

func parse(input string) (result AST, err error) {
    defer func() {
        if r := recover(); r != nil {
            if pe, ok := r.(parseError); ok {
                err = errors.New(pe.msg)
            } else {
                panic(r)  // re-panic if it's not our error
            }
        }
    }()

    return doParse(input), nil
}

func doParse(input string) AST {
    if bad(input) {
        panic(parseError{"unexpected token"})
    }
    // ...
}
```

---

## defer Loop Gotcha

Defer in a loop doesn't run until the **function** returns, not the loop iteration:

```go
// ❌ All files stay open until processAll returns
func processAll(paths []string) {
    for _, path := range paths {
        f, _ := os.Open(path)
        defer f.Close()  // deferred to end of processAll, not loop iteration
        process(f)
    }
}

// ✅ Use a helper function to scope the defer
func processAll(paths []string) {
    for _, path := range paths {
        processOne(path)
    }
}

func processOne(path string) {
    f, _ := os.Open(path)
    defer f.Close()  // runs when processOne returns
    process(f)
}
```

---

## Gotchas

1. **defer in a loop** — deferred calls pile up and run at function return, not loop end.
2. **Defer argument evaluation is immediate** — if you pass a changing value, capture it via pointer or closure.
3. **recover only works inside a deferred function** — calling it elsewhere returns nil.
4. **Don't use panic for control flow** — only for genuine invariant violations.

---

## Practice

1. Write a function that opens a file, defers Close, reads content, and returns it.
2. Demonstrate LIFO order with three defers that each print a number.
3. Write `safeCall(f func())` that calls `f` and converts any panic into an error.
4. Time a function using the `defer timeIt(name)()` pattern.

---

## Key Takeaways

- `defer` is for cleanup (Close, Unlock, Commit) — always defer immediately after acquiring a resource.
- `defer` runs LIFO — the last defer executes first.
- `panic` is for programmer errors and unrecoverable invariant violations — not for expected errors.
- `recover` only works inside a deferred function; re-panic if the value isn't yours.
