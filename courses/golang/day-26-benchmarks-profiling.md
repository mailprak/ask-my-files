# Day 26 — Benchmarks & Profiling

## Learning Objectives
- Write and run benchmarks
- Interpret benchmark output
- Profile CPU and memory with `pprof`
- Use the `-race` detector for concurrency bugs

---

## Writing Benchmarks

Benchmark functions start with `Benchmark` and take `*testing.B`:

```go
func BenchmarkStringConcat(b *testing.B) {
    for i := 0; i < b.N; i++ {  // b.N is set by the framework
        s := ""
        for j := 0; j < 100; j++ {
            s += "x"
        }
        _ = s  // prevent compiler from optimizing away
    }
}

func BenchmarkStringBuilder(b *testing.B) {
    for i := 0; i < b.N; i++ {
        var sb strings.Builder
        for j := 0; j < 100; j++ {
            sb.WriteByte('x')
        }
        _ = sb.String()
    }
}
```

---

## Running Benchmarks

```bash
go test -bench=. ./...                    # all benchmarks
go test -bench=BenchmarkString ./...      # matching benchmarks
go test -bench=. -benchmem ./...          # include memory allocation stats
go test -bench=. -count=5 ./...           # run each 5 times (more stable)
go test -bench=. -benchtime=5s ./...      # run for 5 seconds instead of default 1s
```

---

## Interpreting Benchmark Output

```
BenchmarkStringConcat-8     50000    25432 ns/op    4176 B/op    99 allocs/op
BenchmarkStringBuilder-8   2000000     623 ns/op      96 B/op     2 allocs/op
```

| Field | Meaning |
|---|---|
| `-8` | GOMAXPROCS (8 CPUs) |
| `50000` | Number of iterations run |
| `25432 ns/op` | Nanoseconds per operation |
| `4176 B/op` | Bytes allocated per operation |
| `99 allocs/op` | Heap allocations per operation |

**Conclusion:** `strings.Builder` is ~40x faster and allocates 50x less.

---

## Benchmark Setup (b.ResetTimer)

Don't include setup time in the benchmark:

```go
func BenchmarkSort(b *testing.B) {
    data := generateLargeSlice()   // setup — not part of measurement
    b.ResetTimer()                 // reset the timer

    for i := 0; i < b.N; i++ {
        sort.Ints(data)
    }
}
```

---

## Comparing Benchmarks with benchstat

```bash
go install golang.org/x/perf/cmd/benchstat@latest

# Run both and compare
go test -bench=. -count=10 . > before.txt
# make your change
go test -bench=. -count=10 . > after.txt

benchstat before.txt after.txt
```

---

## CPU Profiling with pprof

```bash
go test -bench=BenchmarkSort -cpuprofile cpu.out ./...
go tool pprof cpu.out
```

Inside pprof interactive mode:
```
(pprof) top           # top functions by CPU time
(pprof) list FuncName # show line-level for a function
(pprof) web           # open in browser (requires graphviz)
```

Or generate a web report directly:
```bash
go tool pprof -http=:8080 cpu.out
```

---

## Memory Profiling

```bash
go test -bench=. -memprofile mem.out ./...
go tool pprof mem.out
```

```
(pprof) top -cum       # cumulative allocations
(pprof) alloc_objects  # number of allocations
(pprof) alloc_space    # bytes allocated
```

---

## Adding pprof to a Running Server

```go
import _ "net/http/pprof"  // blank import registers /debug/pprof endpoints

func main() {
    go http.ListenAndServe(":6060", nil)  // separate debug port
    // ...
}
```

Access: `http://localhost:6060/debug/pprof/`

```bash
# Profile running server for 30 seconds
go tool pprof http://localhost:6060/debug/pprof/profile?seconds=30
```

---

## Trace (Goroutine Scheduling)

```bash
go test -trace trace.out ./...
go tool trace trace.out
```

Shows goroutine scheduling, GC pauses, and blocking events — essential for diagnosing latency spikes.

---

## Memory Escape Analysis

```bash
go build -gcflags="-m" ./...
```

Shows what escapes to the heap vs stays on the stack:
```
./main.go:15:14: &User{} escapes to heap
./main.go:20:12: s does not escape
```

Heap allocations are more expensive — use this to guide optimization.

---

## Common Performance Patterns

```go
// ❌ String concatenation in loop — O(n²)
s := ""
for _, item := range items {
    s += item + ", "
}

// ✅ strings.Builder — O(n), pre-allocated
var b strings.Builder
b.Grow(estimatedSize)
for _, item := range items {
    b.WriteString(item)
    b.WriteString(", ")
}
s := b.String()

// ✅ strings.Join — even simpler
s := strings.Join(items, ", ")

// ❌ Reallocating slice in loop
var results []int
for _, n := range nums {
    results = append(results, n*2)
}

// ✅ Pre-allocate
results := make([]int, 0, len(nums))
for _, n := range nums {
    results = append(results, n*2)
}
```

---

## Gotchas

1. **Micro-benchmarks can mislead** — the compiler may optimize away unused results. Use `_ = result` or `b.Run` sinks.
2. **Benchmark warmup** — Go runs benchmarks until they stabilize. Use `-count=5` for stable comparisons.
3. **GC pauses affect benchmarks** — if your benchmark allocates a lot, GC will affect results inconsistently.
4. **Profile in production conditions** — a benchmark of an isolated function may not reflect real workload performance.

---

## Practice

1. Benchmark two ways to convert `[]int` to `[]string` — using `fmt.Sprintf` vs `strconv.Itoa`.
2. Profile a sort-heavy function and identify the hot path with `pprof`.
3. Add `_ "net/http/pprof"` to a server and capture a CPU profile.
4. Use escape analysis to move a hot-path allocation from heap to stack.

---

## Key Takeaways

- Benchmarks use `b.N` — always structure the loop as `for i := 0; i < b.N; i++`.
- `-benchmem` reveals allocations — often the key optimization target.
- `pprof` is the standard profiler — CPU, memory, goroutine profiles all work the same way.
- Measure before optimizing — intuition about hot paths is often wrong.
