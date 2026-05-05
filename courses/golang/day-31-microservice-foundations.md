# Day 31 — Microservice Foundations: Project Structure, Endpoints & HTTP Status Codes

## Learning Objectives
- Structure a Go microservice project correctly
- Define a domain model and wire up CRUD endpoints
- Return the right HTTP status codes for every scenario
- Build a consistent JSON error response format

---

## Project: Task Service

We'll build a complete **Task microservice** across Days 31–33. By the end you'll have:
- RESTful endpoints (Day 31)
- Middleware for logging, auth, recovery (Day 32)
- A file-backed JSON database with locking (Day 33)

---

## Project Structure

```
taskservice/
├── go.mod
├── main.go               ← wiring: server, routes, shutdown
├── handler/
│   └── task.go           ← HTTP handlers
├── store/
│   └── store.go          ← storage interface + in-memory impl (Day 31)
│   └── filestore.go      ← file-backed impl (Day 33)
├── model/
│   └── task.go           ← domain types
└── middleware/
    └── middleware.go      ← logging, auth, recovery (Day 32)
```

**Rule:** Keep handlers thin. A handler reads the request, calls a store/service method, and writes the response. No business logic in handlers.

---

## model/task.go

```go
package model

import (
    "time"
    "errors"
)

type Status string

const (
    StatusTodo       Status = "todo"
    StatusInProgress Status = "in_progress"
    StatusDone       Status = "done"
)

type Task struct {
    ID          string    `json:"id"`
    Title       string    `json:"title"`
    Description string    `json:"description,omitempty"`
    Status      Status    `json:"status"`
    CreatedAt   time.Time `json:"created_at"`
    UpdatedAt   time.Time `json:"updated_at"`
}

type CreateTaskRequest struct {
    Title       string `json:"title"`
    Description string `json:"description"`
}

type UpdateTaskRequest struct {
    Title       *string `json:"title"`       // pointer — nil means "not provided"
    Description *string `json:"description"`
    Status      *Status `json:"status"`
}

// Validate checks that the request is well-formed.
func (r CreateTaskRequest) Validate() error {
    if r.Title == "" {
        return errors.New("title is required")
    }
    if len(r.Title) > 200 {
        return errors.New("title must be 200 characters or fewer")
    }
    return nil
}

func (r UpdateTaskRequest) Validate() error {
    if r.Title != nil && *r.Title == "" {
        return errors.New("title cannot be empty")
    }
    if r.Status != nil {
        switch *r.Status {
        case StatusTodo, StatusInProgress, StatusDone:
            // valid
        default:
            return errors.New("status must be one of: todo, in_progress, done")
        }
    }
    return nil
}
```

---

## store/store.go — Storage Interface + In-Memory Implementation

```go
package store

import (
    "context"
    "errors"
    "sync"
    "time"

    "github.com/yourname/taskservice/model"
    "github.com/google/uuid"
)

// Sentinel errors — callers use errors.Is() to check these.
var (
    ErrNotFound = errors.New("task not found")
    ErrConflict = errors.New("task already exists")
)

// Store is the interface every storage backend must implement.
type Store interface {
    List(ctx context.Context) ([]model.Task, error)
    Get(ctx context.Context, id string) (model.Task, error)
    Create(ctx context.Context, req model.CreateTaskRequest) (model.Task, error)
    Update(ctx context.Context, id string, req model.UpdateTaskRequest) (model.Task, error)
    Delete(ctx context.Context, id string) error
}

// MemoryStore is a thread-safe in-memory implementation.
type MemoryStore struct {
    mu    sync.RWMutex
    tasks map[string]model.Task
}

func NewMemoryStore() *MemoryStore {
    return &MemoryStore{tasks: make(map[string]model.Task)}
}

func (s *MemoryStore) List(_ context.Context) ([]model.Task, error) {
    s.mu.RLock()
    defer s.mu.RUnlock()

    tasks := make([]model.Task, 0, len(s.tasks))
    for _, t := range s.tasks {
        tasks = append(tasks, t)
    }
    return tasks, nil
}

func (s *MemoryStore) Get(_ context.Context, id string) (model.Task, error) {
    s.mu.RLock()
    defer s.mu.RUnlock()

    t, ok := s.tasks[id]
    if !ok {
        return model.Task{}, ErrNotFound
    }
    return t, nil
}

func (s *MemoryStore) Create(_ context.Context, req model.CreateTaskRequest) (model.Task, error) {
    s.mu.Lock()
    defer s.mu.Unlock()

    now := time.Now().UTC()
    t := model.Task{
        ID:          uuid.NewString(),
        Title:       req.Title,
        Description: req.Description,
        Status:      model.StatusTodo,
        CreatedAt:   now,
        UpdatedAt:   now,
    }
    s.tasks[t.ID] = t
    return t, nil
}

func (s *MemoryStore) Update(_ context.Context, id string, req model.UpdateTaskRequest) (model.Task, error) {
    s.mu.Lock()
    defer s.mu.Unlock()

    t, ok := s.tasks[id]
    if !ok {
        return model.Task{}, ErrNotFound
    }

    if req.Title != nil {
        t.Title = *req.Title
    }
    if req.Description != nil {
        t.Description = *req.Description
    }
    if req.Status != nil {
        t.Status = *req.Status
    }
    t.UpdatedAt = time.Now().UTC()
    s.tasks[id] = t
    return t, nil
}

func (s *MemoryStore) Delete(_ context.Context, id string) error {
    s.mu.Lock()
    defer s.mu.Unlock()

    if _, ok := s.tasks[id]; !ok {
        return ErrNotFound
    }
    delete(s.tasks, id)
    return nil
}
```

---

## HTTP Status Codes — The Contract

Every endpoint must return a precise status code. Consistency is critical for API consumers.

| Scenario | Status Code | Meaning |
|---|---|---|
| GET/PUT/DELETE success | `200 OK` | Resource returned |
| POST success (created) | `201 Created` | New resource created |
| DELETE with no body | `204 No Content` | Deleted, nothing to return |
| Bad JSON / validation fail | `400 Bad Request` | Client sent invalid data |
| Missing/invalid auth token | `401 Unauthorized` | Not authenticated |
| Valid auth but no permission | `403 Forbidden` | Authenticated but not allowed |
| Resource not found | `404 Not Found` | ID doesn't exist |
| Business rule violation | `409 Conflict` | e.g., duplicate |
| Server bug / unexpected panic | `500 Internal Server Error` | Our fault |

---

## Error Response Format

A consistent error envelope means clients can always parse errors the same way:

```go
// model/task.go — add to model package
type ErrorResponse struct {
    Code    string `json:"code"`    // machine-readable: "not_found", "validation_error"
    Message string `json:"message"` // human-readable
}
```

Example responses:
```json
// 400
{"code": "validation_error", "message": "title is required"}

// 404
{"code": "not_found", "message": "task not found"}

// 500
{"code": "internal_error", "message": "an unexpected error occurred"}
```

---

## handler/task.go — HTTP Handlers

```go
package handler

import (
    "encoding/json"
    "errors"
    "net/http"

    "github.com/yourname/taskservice/model"
    "github.com/yourname/taskservice/store"
)

type TaskHandler struct {
    store store.Store
}

func NewTaskHandler(s store.Store) *TaskHandler {
    return &TaskHandler{store: s}
}

// Routes registers all task endpoints on the given mux.
func (h *TaskHandler) Routes(mux *http.ServeMux) {
    mux.HandleFunc("GET /tasks",          h.list)
    mux.HandleFunc("POST /tasks",         h.create)
    mux.HandleFunc("GET /tasks/{id}",     h.get)
    mux.HandleFunc("PUT /tasks/{id}",     h.update)
    mux.HandleFunc("DELETE /tasks/{id}",  h.delete)
}

// list handles GET /tasks
func (h *TaskHandler) list(w http.ResponseWriter, r *http.Request) {
    tasks, err := h.store.List(r.Context())
    if err != nil {
        writeError(w, http.StatusInternalServerError, "internal_error", "failed to list tasks")
        return
    }
    // Return empty array, never null
    if tasks == nil {
        tasks = []model.Task{}
    }
    writeJSON(w, http.StatusOK, tasks)
}

// get handles GET /tasks/{id}
func (h *TaskHandler) get(w http.ResponseWriter, r *http.Request) {
    id := r.PathValue("id")

    task, err := h.store.Get(r.Context(), id)
    if err != nil {
        if errors.Is(err, store.ErrNotFound) {
            writeError(w, http.StatusNotFound, "not_found", "task not found")
            return
        }
        writeError(w, http.StatusInternalServerError, "internal_error", "failed to get task")
        return
    }
    writeJSON(w, http.StatusOK, task)
}

// create handles POST /tasks
func (h *TaskHandler) create(w http.ResponseWriter, r *http.Request) {
    var req model.CreateTaskRequest
    if err := decodeJSON(w, r, &req); err != nil {
        return // decodeJSON already wrote the error response
    }

    if err := req.Validate(); err != nil {
        writeError(w, http.StatusBadRequest, "validation_error", err.Error())
        return
    }

    task, err := h.store.Create(r.Context(), req)
    if err != nil {
        writeError(w, http.StatusInternalServerError, "internal_error", "failed to create task")
        return
    }
    writeJSON(w, http.StatusCreated, task)
}

// update handles PUT /tasks/{id}
func (h *TaskHandler) update(w http.ResponseWriter, r *http.Request) {
    id := r.PathValue("id")

    var req model.UpdateTaskRequest
    if err := decodeJSON(w, r, &req); err != nil {
        return
    }

    if err := req.Validate(); err != nil {
        writeError(w, http.StatusBadRequest, "validation_error", err.Error())
        return
    }

    task, err := h.store.Update(r.Context(), id, req)
    if err != nil {
        if errors.Is(err, store.ErrNotFound) {
            writeError(w, http.StatusNotFound, "not_found", "task not found")
            return
        }
        writeError(w, http.StatusInternalServerError, "internal_error", "failed to update task")
        return
    }
    writeJSON(w, http.StatusOK, task)
}

// delete handles DELETE /tasks/{id}
func (h *TaskHandler) delete(w http.ResponseWriter, r *http.Request) {
    id := r.PathValue("id")

    if err := h.store.Delete(r.Context(), id); err != nil {
        if errors.Is(err, store.ErrNotFound) {
            writeError(w, http.StatusNotFound, "not_found", "task not found")
            return
        }
        writeError(w, http.StatusInternalServerError, "internal_error", "failed to delete task")
        return
    }
    w.WriteHeader(http.StatusNoContent) // 204 — no body
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

func writeJSON(w http.ResponseWriter, status int, v any) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(status)
    if err := json.NewEncoder(w).Encode(v); err != nil {
        // headers already sent — best we can do is log
        _ = err
    }
}

func writeError(w http.ResponseWriter, status int, code, message string) {
    writeJSON(w, status, model.ErrorResponse{Code: code, Message: message})
}

func decodeJSON(w http.ResponseWriter, r *http.Request, dst any) error {
    r.Body = http.MaxBytesReader(w, r.Body, 1<<20) // 1 MB limit
    dec := json.NewDecoder(r.Body)
    dec.DisallowUnknownFields() // reject unknown JSON fields

    if err := dec.Decode(dst); err != nil {
        writeError(w, http.StatusBadRequest, "invalid_json", "request body is not valid JSON")
        return err
    }
    return nil
}
```

---

## main.go — Wiring It Together

```go
package main

import (
    "context"
    "fmt"
    "log"
    "net/http"
    "os"
    "os/signal"
    "syscall"
    "time"

    "github.com/yourname/taskservice/handler"
    "github.com/yourname/taskservice/store"
)

func main() {
    s := store.NewMemoryStore()
    taskHandler := handler.NewTaskHandler(s)

    mux := http.NewServeMux()
    taskHandler.Routes(mux)

    // Health check endpoint
    mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        fmt.Fprintln(w, `{"status":"ok"}`)
    })

    server := &http.Server{
        Addr:         ":8080",
        Handler:      mux,
        ReadTimeout:  5 * time.Second,
        WriteTimeout: 10 * time.Second,
        IdleTimeout:  120 * time.Second,
    }

    // Start server in a goroutine so we can listen for signals
    go func() {
        log.Printf("server listening on %s", server.Addr)
        if err := server.ListenAndServe(); err != http.ErrServerClosed {
            log.Fatalf("server error: %v", err)
        }
    }()

    // Graceful shutdown on SIGINT / SIGTERM
    quit := make(chan os.Signal, 1)
    signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
    <-quit

    log.Println("shutting down...")
    ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()

    if err := server.Shutdown(ctx); err != nil {
        log.Fatalf("forced shutdown: %v", err)
    }
    log.Println("server stopped")
}
```

---

## Testing the Endpoints

```bash
# Health check
curl http://localhost:8080/health

# Create a task
curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Learn Go","description":"30 day plan"}'
# → 201 {"id":"...","title":"Learn Go","status":"todo",...}

# List tasks
curl http://localhost:8080/tasks
# → 200 [{"id":"...","title":"Learn Go",...}]

# Get by ID
curl http://localhost:8080/tasks/TASK_ID

# Update status
curl -X PUT http://localhost:8080/tasks/TASK_ID \
  -H "Content-Type: application/json" \
  -d '{"status":"in_progress"}'

# Delete
curl -X DELETE http://localhost:8080/tasks/TASK_ID
# → 204 (no body)

# 404 case
curl http://localhost:8080/tasks/nonexistent
# → 404 {"code":"not_found","message":"task not found"}

# Validation error
curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":""}'
# → 400 {"code":"validation_error","message":"title is required"}
```

---

## Gotchas

1. **`w.WriteHeader` can only be called once** — after that, headers are committed. Always call it last, or use `writeJSON`/`writeError` helpers that do it for you.
2. **Return after writing an error** — forgetting `return` after `writeError` means the handler continues and tries to write a second response.
3. **Nil slice in JSON** — `nil` slice encodes as `null`, not `[]`. Always return an initialized (possibly empty) slice.
4. **`r.PathValue` requires Go 1.22+** — on older versions, extract path params manually or use a router library.

---

## Key Takeaways

- Keep handlers thin: decode → validate → call store → encode response.
- Sentinel errors (`ErrNotFound`, `ErrConflict`) let handlers map domain errors to HTTP status codes cleanly with `errors.Is`.
- Always return `204 No Content` for successful deletes — no body needed.
- A consistent `ErrorResponse` struct means API consumers always know how to read errors.
