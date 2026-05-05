# Day 30 — Capstone: Build a CLI Tool

## Learning Objectives
- Apply 29 days of Go knowledge to a real project
- Structure a CLI tool properly
- Use `flag` or `cobra` for argument parsing
- Combine file I/O, JSON, HTTP, concurrency, and testing

---

## The Project: `gocheck`

A CLI tool that:
1. Takes a list of URLs from a file or stdin
2. Concurrently checks if each URL is reachable
3. Reports status code, latency, and any errors
4. Outputs results as a table or JSON

---

## Project Structure

```
gocheck/
├── go.mod
├── main.go
├── checker/
│   ├── checker.go       ← core logic
│   └── checker_test.go  ← tests
└── output/
    └── output.go        ← formatting
```

---

## main.go — Entry Point & Flags

```go
package main

import (
    "bufio"
    "context"
    "flag"
    "fmt"
    "os"
    "time"

    "github.com/yourname/gocheck/checker"
    "github.com/yourname/gocheck/output"
)

func main() {
    var (
        file        = flag.String("f", "", "file with URLs (one per line)")
        workers     = flag.Int("w", 10, "number of concurrent workers")
        timeout     = flag.Duration("t", 5*time.Second, "request timeout")
        jsonOutput  = flag.Bool("json", false, "output as JSON")
    )
    flag.Parse()

    urls, err := readURLs(*file, flag.Args())
    if err != nil {
        fmt.Fprintln(os.Stderr, "error:", err)
        os.Exit(1)
    }

    if len(urls) == 0 {
        fmt.Fprintln(os.Stderr, "no URLs provided")
        flag.Usage()
        os.Exit(1)
    }

    ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
    defer cancel()

    results := checker.CheckAll(ctx, urls, *workers, *timeout)

    if *jsonOutput {
        output.JSON(os.Stdout, results)
    } else {
        output.Table(os.Stdout, results)
    }
}

func readURLs(file string, args []string) ([]string, error) {
    if len(args) > 0 {
        return args, nil
    }
    if file == "" {
        return nil, nil
    }
    f, err := os.Open(file)
    if err != nil {
        return nil, err
    }
    defer f.Close()

    var urls []string
    scanner := bufio.NewScanner(f)
    for scanner.Scan() {
        if line := strings.TrimSpace(scanner.Text()); line != "" {
            urls = append(urls, line)
        }
    }
    return urls, scanner.Err()
}
```

---

## checker/checker.go — Core Logic

```go
package checker

import (
    "context"
    "fmt"
    "net/http"
    "sync"
    "time"
)

type Result struct {
    URL      string
    Status   int
    Latency  time.Duration
    Error    string
}

func CheckAll(ctx context.Context, urls []string, workers int, timeout time.Duration) []Result {
    jobs := make(chan string, len(urls))
    for _, u := range urls {
        jobs <- u
    }
    close(jobs)

    results := make([]Result, 0, len(urls))
    var (
        mu sync.Mutex
        wg sync.WaitGroup
    )

    client := &http.Client{Timeout: timeout}

    for i := 0; i < workers; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for url := range jobs {
                r := checkOne(ctx, client, url)
                mu.Lock()
                results = append(results, r)
                mu.Unlock()
            }
        }()
    }

    wg.Wait()
    return results
}

func checkOne(ctx context.Context, client *http.Client, url string) Result {
    start := time.Now()

    req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
    if err != nil {
        return Result{URL: url, Error: err.Error()}
    }

    resp, err := client.Do(req)
    latency := time.Since(start)

    if err != nil {
        return Result{URL: url, Latency: latency, Error: err.Error()}
    }
    defer resp.Body.Close()

    return Result{
        URL:     url,
        Status:  resp.StatusCode,
        Latency: latency,
    }
}
```

---

## checker/checker_test.go

```go
package checker

import (
    "context"
    "net/http"
    "net/http/httptest"
    "testing"
    "time"

    "github.com/stretchr/testify/assert"
)

func TestCheckOne_OK(t *testing.T) {
    server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.WriteHeader(http.StatusOK)
    }))
    defer server.Close()

    client := &http.Client{Timeout: 2 * time.Second}
    result := checkOne(context.Background(), client, server.URL)

    assert.Equal(t, http.StatusOK, result.Status)
    assert.Empty(t, result.Error)
    assert.Greater(t, result.Latency, time.Duration(0))
}

func TestCheckOne_Timeout(t *testing.T) {
    server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        time.Sleep(2 * time.Second)  // slow server
    }))
    defer server.Close()

    client := &http.Client{Timeout: 100 * time.Millisecond}
    result := checkOne(context.Background(), client, server.URL)

    assert.NotEmpty(t, result.Error)
}

func TestCheckAll_Concurrent(t *testing.T) {
    server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.WriteHeader(http.StatusOK)
    }))
    defer server.Close()

    urls := []string{server.URL, server.URL, server.URL}
    results := CheckAll(context.Background(), urls, 3, 2*time.Second)

    assert.Len(t, results, 3)
    for _, r := range results {
        assert.Equal(t, http.StatusOK, r.Status)
    }
}
```

---

## output/output.go

```go
package output

import (
    "encoding/json"
    "fmt"
    "io"
    "sort"

    "github.com/yourname/gocheck/checker"
)

func Table(w io.Writer, results []checker.Result) {
    // Sort by URL for consistent output
    sort.Slice(results, func(i, j int) bool {
        return results[i].URL < results[j].URL
    })

    fmt.Fprintf(w, "%-50s %6s %10s  %s\n", "URL", "STATUS", "LATENCY", "ERROR")
    fmt.Fprintf(w, "%s\n", strings.Repeat("-", 80))

    for _, r := range results {
        status := fmt.Sprintf("%d", r.Status)
        if r.Error != "" {
            status = "ERR"
        }
        fmt.Fprintf(w, "%-50s %6s %10s  %s\n",
            truncate(r.URL, 50),
            status,
            r.Latency.Round(time.Millisecond),
            r.Error,
        )
    }
}

func JSON(w io.Writer, results []checker.Result) {
    enc := json.NewEncoder(w)
    enc.SetIndent("", "  ")
    enc.Encode(results)
}

func truncate(s string, n int) string {
    if len(s) <= n {
        return s
    }
    return s[:n-3] + "..."
}
```

---

## Building and Running

```bash
# Build
go build -o gocheck ./...

# Check a list of URLs
./gocheck https://google.com https://github.com https://nonexistent.invalid

# From a file
./gocheck -f urls.txt -w 20 -t 3s

# JSON output
./gocheck -json https://google.com https://api.github.com

# Run tests
go test -race -cover ./...
```

---

## What You Applied in This Project

| Concept | Where Used |
|---|---|
| Packages & modules (Day 14) | Project structure, go.mod |
| Functions + error handling (Day 04, 12) | All functions return errors |
| Structs + methods (Day 08) | `Result` struct |
| Goroutines + channels (Day 15, 16) | Worker pool pattern |
| sync.WaitGroup + Mutex (Day 18) | Concurrent result collection |
| Context (Day 19) | Timeout propagation |
| HTTP client (Day 23) | `http.Client` with timeout |
| File I/O (Day 21) | Reading URL list from file |
| JSON (Day 22) | JSON output mode |
| Testing (Day 25) | `httptest` server, table tests |
| flag package (Day 29) | CLI argument parsing |

---

## Extensions to Try

1. **Retry on failure** — retry failed URLs up to 3 times with exponential backoff
2. **Color output** — use a library like `github.com/fatih/color` for status indicators
3. **Progress bar** — show progress as URLs are checked
4. **DNS lookup timing** — break latency into DNS + connect + TTFB
5. **Export to CSV** — add a `-csv` output format

---

## Key Takeaways

- A real project integrates all the pieces: CLI parsing, concurrency, I/O, testing.
- The worker pool pattern (Day 15-16) is the right model for bounded concurrency.
- `httptest.NewServer` makes HTTP handler tests self-contained.
- Structure code by concern (`checker`, `output`) — keep `main` thin and focused on wiring.

---

## Congratulations!

You've completed 30 days of Go. You now know:
- The full type system (types, interfaces, generics)
- Concurrency (goroutines, channels, sync, context)
- The HTTP stack (client and server)
- Testing, benchmarking, and profiling
- The standard library essentials

**What's next:**
- Build something real that solves a problem you have
- Read the Go standard library source — it's excellent Go
- Explore: `database/sql`, `grpc`, `cobra`, `ent` (ORM)
- Read: *The Go Programming Language* (Donovan & Kernighan)
