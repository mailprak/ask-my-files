# Day 32 — Middleware & Routing

## Learning Objectives
- Understand the middleware pattern in Go's `net/http`
- Write reusable middleware: logging, request ID, auth, panic recovery
- Chain middleware cleanly
- Group routes and apply middleware selectively

---

## The Middleware Pattern

Middleware is a function that wraps an `http.Handler` to add behaviour before and/or after it:

```go
type Middleware func(http.Handler) http.Handler
```

This is the entire pattern. A middleware receives a handler and returns a new handler.

```go
func myMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        // Before the handler
        doSomethingBefore(r)

        next.ServeHTTP(w, r) // call the next handler

        // After the handler
        doSomethingAfter(w)
    })
}
```

---

## middleware/middleware.go

```go
package middleware

import (
    "context"
    "encoding/json"
    "fmt"
    "log/slog"
    "net/http"
    "runtime/debug"
    "time"

    "github.com/google/uuid"
)

// ─── Request ID ───────────────────────────────────────────────────────────────

type contextKey string

const RequestIDKey contextKey = "requestID"

// RequestID injects a unique request ID into every request context and response header.
func RequestID(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        id := r.Header.Get("X-Request-ID")
        if id == "" {
            id = uuid.NewString()
        }
        ctx := context.WithValue(r.Context(), RequestIDKey, id)
        w.Header().Set("X-Request-ID", id)
        next.ServeHTTP(w, r.WithContext(ctx))
    })
}

func GetRequestID(ctx context.Context) string {
    if id, ok := ctx.Value(RequestIDKey).(string); ok {
        return id
    }
    return ""
}

// ─── Structured Logging ───────────────────────────────────────────────────────

// responseWriter wraps http.ResponseWriter to capture the status code.
type responseWriter struct {
    http.ResponseWriter
    status      int
    wroteHeader bool
}

func wrapResponseWriter(w http.ResponseWriter) *responseWriter {
    return &responseWriter{ResponseWriter: w}
}

func (rw *responseWriter) WriteHeader(code int) {
    if rw.wroteHeader {
        return
    }
    rw.status = code
    rw.ResponseWriter.WriteHeader(code)
    rw.wroteHeader = true
}

func (rw *responseWriter) Status() int {
    if rw.status == 0 {
        return http.StatusOK // default if WriteHeader was never called
    }
    return rw.status
}

// Logger logs method, path, status code, duration, and request ID for every request.
func Logger(logger *slog.Logger) func(http.Handler) http.Handler {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            start := time.Now()
            wrapped := wrapResponseWriter(w)

            next.ServeHTTP(wrapped, r)

            logger.Info("request",
                "method",     r.Method,
                "path",       r.URL.Path,
                "status",     wrapped.Status(),
                "duration_ms", time.Since(start).Milliseconds(),
                "request_id", GetRequestID(r.Context()),
                "remote_addr", r.RemoteAddr,
            )
        })
    }
}

// ─── Panic Recovery ───────────────────────────────────────────────────────────

// Recovery catches panics, logs the stack trace, and returns 500.
func Recovery(logger *slog.Logger) func(http.Handler) http.Handler {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            defer func() {
                if rec := recover(); rec != nil {
                    logger.Error("panic recovered",
                        "panic",      fmt.Sprintf("%v", rec),
                        "stack",      string(debug.Stack()),
                        "request_id", GetRequestID(r.Context()),
                    )
                    w.Header().Set("Content-Type", "application/json")
                    w.WriteHeader(http.StatusInternalServerError)
                    json.NewEncoder(w).Encode(map[string]string{
                        "code":    "internal_error",
                        "message": "an unexpected error occurred",
                    })
                }
            }()
            next.ServeHTTP(w, r)
        })
    }
}

// ─── Authentication ───────────────────────────────────────────────────────────

// BearerAuth validates a static Bearer token.
// In production, validate a JWT instead.
func BearerAuth(validToken string) func(http.Handler) http.Handler {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            auth := r.Header.Get("Authorization")
            expected := "Bearer " + validToken

            if auth != expected {
                w.Header().Set("Content-Type", "application/json")
                w.WriteHeader(http.StatusUnauthorized)
                json.NewEncoder(w).Encode(map[string]string{
                    "code":    "unauthorized",
                    "message": "missing or invalid Authorization header",
                })
                return
            }
            next.ServeHTTP(w, r)
        })
    }
}

// ─── Content-Type enforcement ─────────────────────────────────────────────────

// RequireJSON rejects requests whose Content-Type is not application/json.
// Only applies to methods that carry a body.
func RequireJSON(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        if r.Method == http.MethodPost || r.Method == http.MethodPut || r.Method == http.MethodPatch {
            ct := r.Header.Get("Content-Type")
            if ct != "application/json" {
                w.Header().Set("Content-Type", "application/json")
                w.WriteHeader(http.StatusUnsupportedMediaType)
                json.NewEncoder(w).Encode(map[string]string{
                    "code":    "unsupported_media_type",
                    "message": "Content-Type must be application/json",
                })
                return
            }
        }
        next.ServeHTTP(w, r)
    })
}

// ─── CORS ─────────────────────────────────────────────────────────────────────

// CORS adds permissive CORS headers (tighten for production).
func CORS(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Access-Control-Allow-Origin", "*")
        w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Request-ID")

        if r.Method == http.MethodOptions {
            w.WriteHeader(http.StatusNoContent)
            return
        }
        next.ServeHTTP(w, r)
    })
}
```

---

## Chaining Middleware

Write a simple `Chain` helper so middleware stacks are readable:

```go
// middleware/middleware.go — add this

// Chain applies middleware in order: Chain(a, b, c)(handler)
// runs a → b → c → handler → c → b → a
func Chain(middlewares ...func(http.Handler) http.Handler) func(http.Handler) http.Handler {
    return func(final http.Handler) http.Handler {
        for i := len(middlewares) - 1; i >= 0; i-- {
            final = middlewares[i](final)
        }
        return final
    }
}
```

Usage:
```go
stack := middleware.Chain(
    middleware.Recovery(logger),   // outermost — catches panics from everything below
    middleware.RequestID,
    middleware.Logger(logger),
    middleware.CORS,
    middleware.RequireJSON,
)

mux := http.NewServeMux()
taskHandler.Routes(mux)

server := &http.Server{
    Addr:    ":8080",
    Handler: stack(mux),
}
```

---

## Applying Middleware Selectively

Some routes need auth, others don't (e.g., `/health`, `/metrics`).

```go
func main() {
    logger := slog.Default()
    token  := os.Getenv("API_TOKEN")

    s            := store.NewMemoryStore()
    taskHandler  := handler.NewTaskHandler(s)

    mux := http.NewServeMux()

    // Public routes — no auth
    mux.HandleFunc("GET /health", healthHandler)

    // Protected routes — wrap individually with auth
    protected := middleware.BearerAuth(token)

    taskMux := http.NewServeMux()
    taskHandler.Routes(taskMux)
    mux.Handle("/tasks", protected(taskMux))
    mux.Handle("/tasks/", protected(taskMux))

    // Global middleware applied to everything
    global := middleware.Chain(
        middleware.Recovery(logger),
        middleware.RequestID,
        middleware.Logger(logger),
        middleware.CORS,
    )

    server := &http.Server{
        Addr:         ":8080",
        Handler:      global(mux),
        ReadTimeout:  5 * time.Second,
        WriteTimeout: 10 * time.Second,
        IdleTimeout:  120 * time.Second,
    }

    // ... graceful shutdown (see Day 31)
}
```

---

## Reading Request ID in Handlers

Handlers can pull the request ID from context for logging:

```go
func (h *TaskHandler) create(w http.ResponseWriter, r *http.Request) {
    reqID := middleware.GetRequestID(r.Context())

    var req model.CreateTaskRequest
    if err := decodeJSON(w, r, &req); err != nil {
        slog.Error("decode failed", "request_id", reqID, "err", err)
        return
    }
    // ...
}
```

---

## Testing Middleware

Middleware is easy to test with `httptest`:

```go
func TestBearerAuth(t *testing.T) {
    handler := middleware.BearerAuth("secret-token")(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.WriteHeader(http.StatusOK)
    }))

    tests := []struct {
        name   string
        token  string
        status int
    }{
        {"valid token",   "Bearer secret-token", http.StatusOK},
        {"wrong token",   "Bearer wrong",        http.StatusUnauthorized},
        {"no auth header", "",                   http.StatusUnauthorized},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            req  := httptest.NewRequest("GET", "/", nil)
            if tt.token != "" {
                req.Header.Set("Authorization", tt.token)
            }
            rec  := httptest.NewRecorder()
            handler.ServeHTTP(rec, req)
            assert.Equal(t, tt.status, rec.Code)
        })
    }
}

func TestLogger_CapturesStatus(t *testing.T) {
    var buf bytes.Buffer
    logger := slog.New(slog.NewJSONHandler(&buf, nil))

    handler := middleware.Logger(logger)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.WriteHeader(http.StatusTeapot)
    }))

    req := httptest.NewRequest("GET", "/test", nil)
    rec := httptest.NewRecorder()
    handler.ServeHTTP(rec, req)

    assert.Contains(t, buf.String(), "418")  // status captured in log
}
```

---

## Middleware Execution Order

```
Request  →  Recovery → RequestID → Logger → CORS → Auth → Handler
Response ←  Recovery ← RequestID ← Logger ← CORS ← Auth ← Handler
```

Order matters:
- `Recovery` must be outermost to catch panics from all other middleware.
- `RequestID` must be before `Logger` so the log includes the ID.
- `Auth` should be close to the handler — only protect what needs protecting.

---

## Gotchas

1. **Writing headers after `next.ServeHTTP`** — headers are already sent by the time `next` returns. You can read the response status (via the wrapped writer) but you can't change it.
2. **Calling `next.ServeHTTP` twice** — sends the response body twice. Use `return` after writing an error.
3. **Panic in middleware** — only `Recovery` handles panics. Middleware that runs after `Recovery` in the stack is not protected.
4. **`responseWriter` wrapper must embed the original** — otherwise `http.Flusher`, `http.Hijacker`, etc. stop working.

---

## Practice

1. Write a `RateLimit(n int, per time.Duration)` middleware using a token bucket.
2. Write a `Timeout(d time.Duration)` middleware that cancels the context if the handler takes too long.
3. Add request size limiting middleware (reject bodies over 10 KB).
4. Write a test for `Recovery` that confirms a panic returns a 500 JSON response.

---

## Key Takeaways

- Middleware is just `func(http.Handler) http.Handler` — compose it with `Chain`.
- `Recovery` goes outermost; auth goes closest to the handler.
- Wrap `http.ResponseWriter` to capture status codes for logging and metrics.
- Middleware is trivially testable with `httptest.NewRequest` + `httptest.NewRecorder`.
