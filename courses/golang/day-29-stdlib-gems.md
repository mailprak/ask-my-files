# Day 29 — Standard Library Gems

## Learning Objectives
- Use `strings` and `strconv` effectively
- Work with `time` and durations
- Use `sort`, `slices`, and `maps` (Go 1.21+)
- Understand `log/slog` for structured logging

---

## strings Package

```go
import "strings"

s := "Hello, World!"

strings.Contains(s, "World")         // true
strings.HasPrefix(s, "Hello")        // true
strings.HasSuffix(s, "!")            // true
strings.Count(s, "l")                // 3
strings.Index(s, "World")            // 7

strings.ToUpper(s)                   // "HELLO, WORLD!"
strings.ToLower(s)                   // "hello, world!"
strings.TrimSpace("  hello  ")       // "hello"
strings.Trim("---hello---", "-")     // "hello"
strings.TrimPrefix("foo/bar", "foo/") // "bar"

strings.Replace(s, "World", "Go", 1) // "Hello, Go!"
strings.ReplaceAll(s, "l", "L")      // "HeLLo, WorLd!"

strings.Split("a,b,c", ",")          // ["a", "b", "c"]
strings.Join([]string{"a", "b"}, "-") // "a-b"

strings.Fields("  one two  three  ") // ["one", "two", "three"]

strings.Builder usage:
var b strings.Builder
b.WriteString("hello")
b.WriteRune(' ')
b.WriteByte('!')
fmt.Println(b.String())  // "hello !"
```

---

## strconv Package

```go
import "strconv"

// Int ↔ String
strconv.Itoa(42)                // "42"
strconv.Atoi("42")              // 42, nil

// ParseXxx — more control
n, err := strconv.ParseInt("0xff", 0, 64)   // auto-detect base: 255
n, err  = strconv.ParseInt("100", 10, 64)   // decimal: 100
f, err := strconv.ParseFloat("3.14", 64)    // 3.14

// FormatXxx
strconv.FormatInt(255, 16)      // "ff"
strconv.FormatFloat(3.14, 'f', 2, 64)  // "3.14"
strconv.FormatBool(true)        // "true"

// ParseBool
b, err := strconv.ParseBool("true")  // true, nil
```

---

## time Package

```go
import "time"

now := time.Now()
fmt.Println(now.Year(), now.Month(), now.Day())

// Duration literals
d := 2*time.Hour + 30*time.Minute + 45*time.Second
fmt.Println(d)  // 2h30m45s

// Add/Sub
tomorrow := now.Add(24 * time.Hour)
yesterday := now.Add(-24 * time.Hour)
diff := tomorrow.Sub(now)  // 24h0m0s

// Comparison
now.Before(tomorrow)  // true
now.After(yesterday)  // true
now.Equal(now)        // true

// Formatting — Go uses a reference time: Mon Jan 2 15:04:05 MST 2006
t := time.Date(2024, 1, 15, 10, 30, 0, 0, time.UTC)
fmt.Println(t.Format("2006-01-02"))          // 2024-01-15
fmt.Println(t.Format(time.RFC3339))          // 2024-01-15T10:30:00Z
fmt.Println(t.Format("02 Jan 2006 15:04"))   // 15 Jan 2024 10:30

// Parsing
t2, err := time.Parse("2006-01-02", "2024-06-15")

// Unix timestamp
unix := t.Unix()             // seconds since epoch
t3   := time.Unix(unix, 0)  // back to time.Time

// Timers
timer := time.NewTimer(5 * time.Second)
<-timer.C  // blocks for 5 seconds
timer.Stop()
```

---

## sort Package

```go
import "sort"

// Sort a slice of ints (in place)
nums := []int{5, 2, 8, 1}
sort.Ints(nums)        // [1 2 5 8]
sort.Sort(sort.Reverse(sort.IntSlice(nums)))  // [8 5 2 1]

// Sort strings
words := []string{"banana", "apple", "cherry"}
sort.Strings(words)    // [apple banana cherry]

// Custom sort with sort.Slice
people := []struct{ Name string; Age int }{
    {"Alice", 30},
    {"Bob", 25},
    {"Carol", 35},
}
sort.Slice(people, func(i, j int) bool {
    return people[i].Age < people[j].Age  // sort by age ascending
})

// Sort stability
sort.SliceStable(people, func(i, j int) bool {
    return people[i].Name < people[j].Name
})

// Binary search
idx, found := sort.Find(len(nums), func(i int) int {
    return cmp.Compare(5, nums[i])
})
```

---

## slices and maps Packages (Go 1.21+)

```go
import (
    "slices"
    "maps"
    "cmp"
)

// slices
nums := []int{3, 1, 4, 1, 5}
slices.Sort(nums)                               // [1 1 3 4 5]
slices.Contains(nums, 4)                        // true
slices.Index(nums, 3)                           // 2
slices.Equal([]int{1, 2}, []int{1, 2})          // true
slices.Reverse(nums)                            // in place
slices.Max(nums)                                // 5
slices.Min(nums)                                // 1
unique := slices.Compact(nums)                  // remove adjacent duplicates

// Sorted with custom comparator
slices.SortFunc(people, func(a, b Person) int {
    return cmp.Compare(a.Age, b.Age)
})

// maps
m := map[string]int{"a": 1, "b": 2}
keys := slices.Collect(maps.Keys(m))   // []string
vals := slices.Collect(maps.Values(m)) // []int
maps.Copy(dst, src)                    // merge src into dst
maps.DeleteFunc(m, func(k string, v int) bool { return v < 2 })
```

---

## log/slog — Structured Logging (Go 1.21+)

```go
import "log/slog"

// Default logger
slog.Info("server started", "port", 8080)
slog.Warn("high memory", "usage_mb", 512)
slog.Error("request failed", "err", err, "path", r.URL.Path)

// Structured output (JSON)
logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
    Level: slog.LevelInfo,
}))
logger.Info("user login", "user_id", 42, "ip", "192.168.1.1")
// {"time":"...","level":"INFO","msg":"user login","user_id":42,"ip":"192.168.1.1"}

// With attributes
logger = logger.With("service", "auth", "version", "1.0")
logger.Info("ready")  // always includes service and version
```

---

## math Package

```go
import "math"

math.Abs(-5.0)         // 5.0
math.Sqrt(16.0)        // 4.0
math.Pow(2, 10)        // 1024.0
math.Log(math.E)       // 1.0
math.Log2(1024)        // 10.0
math.Round(3.7)        // 4.0
math.Floor(3.7)        // 3.0
math.Ceil(3.2)         // 4.0
math.MaxInt64          // 9223372036854775807
math.Pi                // 3.141592653589793

// Integer math — use math/bits
import "math/bits"
bits.OnesCount(0b1010)  // 2 (count set bits)
bits.Len(42)            // 6 (bits needed to represent)
```

---

## Practice

1. Parse a date string in multiple formats, trying each until one succeeds.
2. Sort a slice of structs by multiple fields (primary: age, secondary: name).
3. Use `slog` with JSON output to log request duration and status in an HTTP handler.
4. Use `slices.SortFunc` and `slices.BinarySearchFunc` to implement a sorted insert.

---

## Key Takeaways

- `strings.Builder` is the right tool for building strings iteratively.
- Go's time format uses the reference time `2006-01-02 15:04:05` — memorize it.
- `slices` and `maps` packages (Go 1.21+) have generic versions of common operations.
- `log/slog` is the modern structured logging API — prefer it over `log` and third-party loggers.
