# Day 23 — HTTP Client

## Learning Objectives
- Make GET and POST requests with `net/http`
- Set headers, timeouts, and context
- Parse JSON responses
- Use a custom `http.Client` for production use

---

## Simple GET Request

```go
import "net/http"

resp, err := http.Get("https://api.example.com/users")
if err != nil {
    return err
}
defer resp.Body.Close()  // always close the body

body, err := io.ReadAll(resp.Body)
if err != nil {
    return err
}
fmt.Println(string(body))
```

**Never use `http.DefaultClient` in production** — it has no timeout.

---

## Always Check Status Code

```go
if resp.StatusCode != http.StatusOK {
    return fmt.Errorf("unexpected status: %d", resp.StatusCode)
}
```

---

## POST Request with JSON Body

```go
type CreateUserRequest struct {
    Name  string `json:"name"`
    Email string `json:"email"`
}

func createUser(name, email string) error {
    payload := CreateUserRequest{Name: name, Email: email}

    data, err := json.Marshal(payload)
    if err != nil {
        return err
    }

    resp, err := http.Post(
        "https://api.example.com/users",
        "application/json",
        bytes.NewReader(data),
    )
    if err != nil {
        return err
    }
    defer resp.Body.Close()

    if resp.StatusCode != http.StatusCreated {
        return fmt.Errorf("create user failed: %d", resp.StatusCode)
    }
    return nil
}
```

---

## Custom http.Client (Production)

Always configure timeouts:

```go
client := &http.Client{
    Timeout: 10 * time.Second,  // total request timeout
    Transport: &http.Transport{
        DialContext: (&net.Dialer{
            Timeout:   5 * time.Second,   // TCP connect timeout
            KeepAlive: 30 * time.Second,
        }).DialContext,
        TLSHandshakeTimeout:   5 * time.Second,
        ResponseHeaderTimeout: 5 * time.Second,
        MaxIdleConns:          100,
        MaxIdleConnsPerHost:   10,
        IdleConnTimeout:       90 * time.Second,
    },
}
```

---

## Request with Headers and Context

```go
func fetchWithAuth(ctx context.Context, url, token string) ([]byte, error) {
    req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
    if err != nil {
        return nil, err
    }

    req.Header.Set("Authorization", "Bearer "+token)
    req.Header.Set("Accept", "application/json")
    req.Header.Set("User-Agent", "myapp/1.0")

    resp, err := client.Do(req)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()

    if resp.StatusCode >= 400 {
        return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, url)
    }

    return io.ReadAll(resp.Body)
}
```

---

## Decode JSON Response Directly

```go
type User struct {
    ID   int    `json:"id"`
    Name string `json:"name"`
}

func getUser(ctx context.Context, id int) (*User, error) {
    url := fmt.Sprintf("https://api.example.com/users/%d", id)
    req, _ := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)

    resp, err := client.Do(req)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()

    if resp.StatusCode != http.StatusOK {
        return nil, fmt.Errorf("GET %s: %d", url, resp.StatusCode)
    }

    var user User
    if err := json.NewDecoder(resp.Body).Decode(&user); err != nil {
        return nil, fmt.Errorf("decode: %w", err)
    }
    return &user, nil
}
```

---

## Sending Form Data

```go
form := url.Values{}
form.Set("username", "alice")
form.Set("password", "secret")

resp, err := client.Post(
    "https://example.com/login",
    "application/x-www-form-urlencoded",
    strings.NewReader(form.Encode()),
)
```

---

## Query Parameters

```go
base, _ := url.Parse("https://api.example.com/search")
params := url.Values{}
params.Set("q", "golang")
params.Set("page", "1")
base.RawQuery = params.Encode()

req, _ := http.NewRequestWithContext(ctx, http.MethodGet, base.String(), nil)
// URL: https://api.example.com/search?page=1&q=golang
```

---

## Retry with Backoff (Simple)

```go
func withRetry(n int, fn func() error) error {
    var err error
    for i := 0; i < n; i++ {
        err = fn()
        if err == nil {
            return nil
        }
        time.Sleep(time.Duration(i+1) * 200 * time.Millisecond)
    }
    return fmt.Errorf("after %d retries: %w", n, err)
}
```

---

## Gotchas

1. **`http.DefaultClient` has no timeout** — hanging server = hanging goroutine. Always use a custom client.
2. **Always `defer resp.Body.Close()`** — even if you don't read the body. Leaking bodies exhausts connections.
3. **Always read and close the body** before reusing the connection — not reading the body prevents keep-alive.
4. **Context cancellation** — use `http.NewRequestWithContext` so the request is cancelled when the context is.

```go
// Read and discard body to enable connection reuse
io.Copy(io.Discard, resp.Body)
resp.Body.Close()
```

---

## Practice

1. Write `fetchJSON[T any](ctx context.Context, url string, dest *T) error` using generics.
2. Build a client struct with a configured `http.Client` and methods for GET/POST.
3. Make a paginated request: keep fetching until no next page is returned.
4. Implement retry with exponential backoff for network errors.

---

## Key Takeaways

- Never use `http.DefaultClient` in production — always set a `Timeout`.
- `http.NewRequestWithContext` is the right way to make requests — enables cancellation.
- Always `defer resp.Body.Close()` and read the body completely before closing.
- Build a reusable `*http.Client` once and share it — it manages a connection pool.
