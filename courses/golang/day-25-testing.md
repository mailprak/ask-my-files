# Day 25 — Testing

## Learning Objectives
- Write unit tests with the `testing` package
- Use table-driven tests effectively
- Write subtests with `t.Run`
- Use test helpers, testify, and coverage tools

---

## Basic Test

Test files end in `_test.go`. Test functions start with `Test`:

```go
// math_test.go
package math

import "testing"

func TestAdd(t *testing.T) {
    result := Add(2, 3)
    if result != 5 {
        t.Errorf("Add(2, 3) = %d; want 5", result)
    }
}
```

Run: `go test ./...`

---

## Testing Functions

| Function | Purpose |
|---|---|
| `t.Error(args...)` | Log failure, continue test |
| `t.Errorf(fmt, args...)` | Log formatted failure, continue |
| `t.Fatal(args...)` | Log failure, stop test immediately |
| `t.Fatalf(fmt, args...)` | Log formatted failure, stop |
| `t.Log(args...)` | Log info (shown only on failure) |
| `t.Skip(args...)` | Skip this test |
| `t.Helper()` | Mark as helper — errors show caller line |

---

## Table-Driven Tests

The standard Go pattern for testing multiple cases:

```go
func TestAdd(t *testing.T) {
    tests := []struct {
        name     string
        a, b     int
        expected int
    }{
        {"positive", 2, 3, 5},
        {"negative", -1, -2, -3},
        {"zero", 0, 0, 0},
        {"mixed", -5, 5, 0},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            result := Add(tt.a, tt.b)
            if result != tt.expected {
                t.Errorf("Add(%d, %d) = %d; want %d", tt.a, tt.b, result, tt.expected)
            }
        })
    }
}
```

Run a specific subtest: `go test -run TestAdd/positive`

---

## Test Helpers

Mark helper functions with `t.Helper()` so error lines point to the caller:

```go
func assertEqual(t *testing.T, got, want int) {
    t.Helper()  // error message will show the caller's line
    if got != want {
        t.Errorf("got %d; want %d", got, want)
    }
}

func TestMultiply(t *testing.T) {
    assertEqual(t, Multiply(3, 4), 12)
}
```

---

## Test Setup and Teardown

```go
func TestMain(m *testing.M) {
    // Setup before all tests
    setup()

    code := m.Run()  // run all tests

    // Teardown after all tests
    teardown()

    os.Exit(code)
}
```

For per-test setup:
```go
func TestWithDB(t *testing.T) {
    db := setupTestDB(t)
    t.Cleanup(func() { db.Close() })  // runs when test ends

    // ... use db
}
```

---

## Using testify (Popular Third-Party)

```bash
go get github.com/stretchr/testify/assert
go get github.com/stretchr/testify/require
```

```go
import (
    "testing"
    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"
)

func TestUser(t *testing.T) {
    user, err := GetUser(1)

    require.NoError(t, err)           // Fatal if err != nil
    require.NotNil(t, user)           // Fatal if user == nil

    assert.Equal(t, "Alice", user.Name)
    assert.Equal(t, 30, user.Age)
    assert.Contains(t, user.Email, "@")
}
```

`require` stops the test on failure; `assert` continues.

---

## Mocking with Interfaces

Design code to depend on interfaces, then substitute test implementations:

```go
// Production code
type UserStore interface {
    Find(id int) (*User, error)
    Save(u *User) error
}

type UserService struct {
    store UserStore
}

// Test code
type mockStore struct {
    users map[int]*User
}

func (m *mockStore) Find(id int) (*User, error) {
    if u, ok := m.users[id]; ok {
        return u, nil
    }
    return nil, ErrNotFound
}

func TestUserService_GetProfile(t *testing.T) {
    store := &mockStore{users: map[int]*User{
        1: {ID: 1, Name: "Alice"},
    }}
    svc := UserService{store: store}

    profile, err := svc.GetProfile(1)
    require.NoError(t, err)
    assert.Equal(t, "Alice", profile.Name)
}
```

---

## Coverage

```bash
go test -cover ./...
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out  # open visual coverage report
```

Aim for meaningful coverage, not 100% — test behaviour, not lines.

---

## Running Specific Tests

```bash
go test ./...                   # all tests
go test ./pkg/...               # tests in pkg subdirectory
go test -run TestUser ./...     # tests matching regex "TestUser"
go test -run TestUser/delete    # specific subtest
go test -v ./...                # verbose output
go test -race ./...             # with race detector
go test -count=1 ./...          # disable test caching
```

---

## Benchmarks

Benchmark functions start with `Bench`:

```go
func BenchmarkAdd(b *testing.B) {
    for i := 0; i < b.N; i++ {
        Add(100, 200)
    }
}
```

```bash
go test -bench=. ./...
go test -bench=BenchmarkAdd -benchmem ./...
```

---

## Gotchas

1. **Test caching** — Go caches test results. Use `-count=1` to force re-run.
2. **Parallel tests** — call `t.Parallel()` inside a subtest to run it concurrently with others. Only safe if tests don't share state.
3. **t.Fatal in goroutines** — calling `t.Fatal` inside a goroutine panics. Use `t.Error` + return instead.
4. **Not calling `t.Helper()`** — without it, error messages point to the helper, not the test that called it.

---

## Practice

1. Write table-driven tests for a `fizzbuzz(n int) string` function covering 1, 3, 5, 15.
2. Mock a `WeatherAPI` interface and test a function that uses it.
3. Write a benchmark for sorting algorithms and compare with `-bench`.
4. Run `go test -race -cover ./...` and interpret the output.

---

## Key Takeaways

- Table-driven tests with `t.Run` subtests are the standard Go testing pattern.
- Mark helper functions with `t.Helper()` so error lines point to the test, not the helper.
- Design for testability: depend on interfaces, not concrete implementations.
- Always run with `-race` in CI — many concurrency bugs only appear under the race detector.
