# Day 24 — HTTP Server & REST API

## Learning Objectives
- Build an HTTP server with `net/http`
- Define routes and handlers
- Read request bodies and write JSON responses
- Add middleware for logging and auth
- Use `http.ServeMux` for routing

---

## Minimal HTTP Server

```go
package main

import (
    "fmt"
    "net/http"
)

func helloHandler(w http.ResponseWriter, r *http.Request) {
    fmt.Fprintln(w, "Hello, World!")
}

func main() {
    http.HandleFunc("/hello", helloHandler)
    fmt.Println("listening on :8080")
    if err := http.ListenAndServe(":8080", nil); err != nil {
        log.Fatal(err)
    }
}
```

---

## http.Handler Interface

The core interface of Go HTTP:

```go
type Handler interface {
    ServeHTTP(ResponseWriter, *Request)
}
```

Any type with `ServeHTTP` is a handler. `http.HandlerFunc` is a function type that implements it:

```go
// http.HandlerFunc turns a function into an http.Handler
var h http.Handler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
    fmt.Fprintln(w, "hello")
})
```

---

## Using ServeMux

```go
mux := http.NewServeMux()

mux.HandleFunc("GET /users", listUsersHandler)
mux.HandleFunc("POST /users", createUserHandler)
mux.HandleFunc("GET /users/{id}", getUserHandler)  // Go 1.22+ pattern routing
mux.HandleFunc("DELETE /users/{id}", deleteUserHandler)

server := &http.Server{
    Addr:         ":8080",
    Handler:      mux,
    ReadTimeout:  5 * time.Second,
    WriteTimeout: 10 * time.Second,
    IdleTimeout:  120 * time.Second,
}

log.Fatal(server.ListenAndServe())
```

**Go 1.22+** supports method+path patterns like `"GET /users/{id}"`. For earlier versions, check `r.Method` inside the handler.

---

## Reading Path Parameters (Go 1.22+)

```go
func getUserHandler(w http.ResponseWriter, r *http.Request) {
    id := r.PathValue("id")  // extracts {id} from the path
    // ...
}
```

---

## Writing JSON Responses

```go
func writeJSON(w http.ResponseWriter, status int, v any) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(status)
    json.NewEncoder(w).Encode(v)
}

func listUsersHandler(w http.ResponseWriter, r *http.Request) {
    users := getUsers()
    writeJSON(w, http.StatusOK, users)
}
```

---

## Reading JSON Request Body

```go
func createUserHandler(w http.ResponseWriter, r *http.Request) {
    var req struct {
        Name  string `json:"name"`
        Email string `json:"email"`
    }

    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
        return
    }

    if req.Name == "" {
        writeJSON(w, http.StatusBadRequest, map[string]string{"error": "name required"})
        return
    }

    user := createUser(req.Name, req.Email)
    writeJSON(w, http.StatusCreated, user)
}
```

---

## Middleware

Middleware wraps a handler to add cross-cutting behaviour:

```go
// Logging middleware
func logging(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        start := time.Now()
        next.ServeHTTP(w, r)
        log.Printf("%s %s %v", r.Method, r.URL.Path, time.Since(start))
    })
}

// Auth middleware
func requireAuth(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        token := r.Header.Get("Authorization")
        if !isValidToken(token) {
            writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
            return
        }
        next.ServeHTTP(w, r)
    })
}

// Chain middleware
mux := http.NewServeMux()
mux.HandleFunc("GET /users", listUsersHandler)

handler := logging(requireAuth(mux))
http.ListenAndServe(":8080", handler)
```

---

## Reading Query Parameters

```go
func searchHandler(w http.ResponseWriter, r *http.Request) {
    q := r.URL.Query().Get("q")
    page := r.URL.Query().Get("page")
    if page == "" {
        page = "1"
    }
    // ...
}
```

---

## Graceful Shutdown

```go
server := &http.Server{Addr: ":8080", Handler: mux}

// Run in goroutine
go func() {
    if err := server.ListenAndServe(); err != http.ErrServerClosed {
        log.Fatal(err)
    }
}()

// Wait for interrupt signal
quit := make(chan os.Signal, 1)
signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
<-quit

ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
defer cancel()

if err := server.Shutdown(ctx); err != nil {
    log.Fatal("shutdown error:", err)
}
log.Println("server stopped gracefully")
```

---

## Complete REST API Example

```go
type UserHandler struct {
    store UserStore
}

func NewUserHandler(store UserStore) *UserHandler {
    return &UserHandler{store: store}
}

func (h *UserHandler) Routes(mux *http.ServeMux) {
    mux.HandleFunc("GET /users", h.list)
    mux.HandleFunc("POST /users", h.create)
    mux.HandleFunc("GET /users/{id}", h.get)
    mux.HandleFunc("DELETE /users/{id}", h.delete)
}

func (h *UserHandler) list(w http.ResponseWriter, r *http.Request) {
    users, err := h.store.List(r.Context())
    if err != nil {
        writeJSON(w, http.StatusInternalServerError, errorResponse(err))
        return
    }
    writeJSON(w, http.StatusOK, users)
}
```

---

## Gotchas

1. **Always set ReadTimeout and WriteTimeout** on `http.Server` — without them, a slow client can hold a connection forever.
2. **`w.Header().Set(...)` must be called before `w.WriteHeader(...)`** — headers can't be set after the status code is written.
3. **`http.ListenAndServe` returns immediately if bound to an already-used port** — check the error.
4. **Don't ignore the return of `WriteHeader`** — once called, headers are sent; you can't change them.

---

## Practice

1. Build a CRUD REST API for a `Todo` resource (in-memory store).
2. Add logging middleware that logs method, path, and duration.
3. Add a `Content-Type: application/json` middleware.
4. Implement graceful shutdown with a 30-second timeout.

---

## Key Takeaways

- `http.Handler` interface is the building block — middleware is just a function that wraps handlers.
- Go 1.22+ `ServeMux` supports method+path routing natively.
- Always configure timeouts on `http.Server`.
- Graceful shutdown with `server.Shutdown(ctx)` drains in-flight requests before closing.
