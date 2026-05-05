# Day 12 — Error Handling

## Learning Objectives
- Understand Go's error-as-value philosophy
- Create and wrap errors with `fmt.Errorf`
- Use `errors.Is` and `errors.As` for inspection
- Define sentinel errors and custom error types

---

## Errors Are Values

Go does not have exceptions. Errors are just values of type `error` returned like any other value.

```go
f, err := os.Open("file.txt")
if err != nil {
    log.Fatal(err)
}
defer f.Close()
```

**The pattern:** always check `err != nil` immediately after a call that returns one.

---

## Creating Errors

```go
import "errors"

// Simple string error
err := errors.New("something went wrong")

// Formatted error
err = fmt.Errorf("user %d not found", userID)
```

---

## The error Interface

```go
type error interface {
    Error() string
}
```

Any type with `Error() string` is an error. You can carry extra context in a custom error type.

---

## Custom Error Types

```go
type NotFoundError struct {
    Resource string
    ID       int
}

func (e *NotFoundError) Error() string {
    return fmt.Sprintf("%s with id %d not found", e.Resource, e.ID)
}

func findUser(id int) (*User, error) {
    if id <= 0 {
        return nil, &NotFoundError{Resource: "user", ID: id}
    }
    // ...
}
```

---

## Sentinel Errors

A sentinel is a pre-declared error value that callers can compare against:

```go
var ErrNotFound = errors.New("not found")
var ErrPermission = errors.New("permission denied")

func getItem(id int) (*Item, error) {
    if id == 0 {
        return nil, ErrNotFound
    }
    // ...
}

// Caller checks with ==
item, err := getItem(0)
if err == ErrNotFound {
    fmt.Println("item doesn't exist")
}
```

---

## Error Wrapping (Go 1.13+)

Wrap errors to add context while preserving the original:

```go
func readConfig(path string) error {
    _, err := os.ReadFile(path)
    if err != nil {
        return fmt.Errorf("readConfig: %w", err)  // %w wraps the error
    }
    return nil
}
```

---

## errors.Is — Check Error Identity

`errors.Is` unwraps error chains to check if any error in the chain matches a target:

```go
err := readConfig("/missing.yaml")

if errors.Is(err, os.ErrNotExist) {
    fmt.Println("config file missing — using defaults")
}
```

---

## errors.As — Extract Typed Error

`errors.As` unwraps the chain looking for an error of a specific type:

```go
var notFound *NotFoundError
if errors.As(err, &notFound) {
    fmt.Printf("could not find %s id=%d\n", notFound.Resource, notFound.ID)
}
```

---

## Error Wrapping Chain

```go
// Layer 1
var ErrDB = errors.New("database error")

// Layer 2
func query() error {
    return fmt.Errorf("query failed: %w", ErrDB)
}

// Layer 3
func loadUser() error {
    return fmt.Errorf("loadUser: %w", query())
}

err := loadUser()
fmt.Println(err)           // loadUser: query failed: database error
errors.Is(err, ErrDB)      // true — unwraps through the chain
```

---

## Multiple Error Handling Patterns

### Early Return
```go
func process() error {
    if err := stepOne(); err != nil {
        return fmt.Errorf("stepOne: %w", err)
    }
    if err := stepTwo(); err != nil {
        return fmt.Errorf("stepTwo: %w", err)
    }
    return nil
}
```

### Collecting Errors (with `errors.Join` in Go 1.20+)
```go
import "errors"

func validateAll(items []Item) error {
    var errs []error
    for _, item := range items {
        if err := validate(item); err != nil {
            errs = append(errs, err)
        }
    }
    return errors.Join(errs...)  // returns nil if errs is empty
}
```

---

## When to Use log.Fatal vs return err

```go
// In main() or top-level setup — it's OK to Fatal
func main() {
    cfg, err := loadConfig()
    if err != nil {
        log.Fatalf("failed to load config: %v", err)
    }
}

// In library code — ALWAYS return the error, never Fatal
func parseConfig(data []byte) (*Config, error) {
    // ...
    return nil, fmt.Errorf("parseConfig: %w", err)
}
```

---

## Gotchas

1. **Ignoring errors** — `result, _ = riskyCall()` should only be done when you are certain the error is impossible or irrelevant.
2. **`if err != nil` but wrong variable** — easy to shadow err with a new `:=` assignment.
3. **Returning a typed nil** — a nil `*MyError` returned as `error` is not nil (same as the nil interface trap from Day 10):
```go
func bad() error {
    var err *MyError = nil
    return err   // ❌ interface wraps the type — not nil!
}

// Fix:
func good() error {
    return nil   // return untyped nil
}
```

---

## Practice

1. Write `openFile(path string) (*os.File, error)` that wraps the underlying error with context.
2. Define a `ValidationError` type. Return it from a `validate` function and extract it with `errors.As`.
3. Create a sentinel `ErrTimeout` and check for it with `errors.Is` after wrapping.
4. Implement `errors.Join` to collect all validation errors from a slice.

---

## Key Takeaways

- Errors are values — always check, always propagate with context using `%w`.
- Use `errors.Is` for sentinel/identity checks; `errors.As` for typed extraction.
- Never return `(*MyType)(nil)` as `error` — return untyped `nil`.
- Library code returns errors; `main` may Fatal. Never Fatal inside a library.
