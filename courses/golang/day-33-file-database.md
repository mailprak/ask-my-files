# Day 33 — File-Based Database & Complete Service

## Learning Objectives
- Implement a JSON file store with atomic writes and mutex locking
- Understand atomic file replacement to prevent corruption
- Wire the file store into the complete Task service
- Write integration tests against the real file store

---

## Why a File-Based Database?

For small microservices, a local JSON file is a perfectly valid persistence layer:
- Zero external dependencies (no Postgres, Redis, etc.)
- Human-readable — you can `cat data.json` to inspect state
- Works in constrained environments (edge, IoT, local tools)
- Easy to test — just point at a temp file

The key challenges: **concurrent access** (multiple goroutines) and **corruption prevention** (partial writes).

---

## store/filestore.go

```go
package store

import (
    "context"
    "encoding/json"
    "fmt"
    "os"
    "path/filepath"
    "sync"
    "time"

    "github.com/yourname/taskservice/model"
    "github.com/google/uuid"
)

// FileStore is a JSON file-backed implementation of Store.
// Writes are atomic (write-to-temp + rename) and protected by a RWMutex.
type FileStore struct {
    mu   sync.RWMutex
    path string
}

func NewFileStore(path string) (*FileStore, error) {
    fs := &FileStore{path: path}

    // Create the file with an empty task list if it doesn't exist
    if _, err := os.Stat(path); os.IsNotExist(err) {
        if err := fs.writeLocked([]model.Task{}); err != nil {
            return nil, fmt.Errorf("filestore: init %s: %w", path, err)
        }
    }
    return fs, nil
}

// ─── Store interface ──────────────────────────────────────────────────────────

func (fs *FileStore) List(_ context.Context) ([]model.Task, error) {
    fs.mu.RLock()
    defer fs.mu.RUnlock()
    return fs.readLocked()
}

func (fs *FileStore) Get(_ context.Context, id string) (model.Task, error) {
    fs.mu.RLock()
    defer fs.mu.RUnlock()

    tasks, err := fs.readLocked()
    if err != nil {
        return model.Task{}, err
    }
    for _, t := range tasks {
        if t.ID == id {
            return t, nil
        }
    }
    return model.Task{}, ErrNotFound
}

func (fs *FileStore) Create(_ context.Context, req model.CreateTaskRequest) (model.Task, error) {
    fs.mu.Lock()
    defer fs.mu.Unlock()

    tasks, err := fs.readLocked()
    if err != nil {
        return model.Task{}, err
    }

    now := time.Now().UTC()
    t := model.Task{
        ID:          uuid.NewString(),
        Title:       req.Title,
        Description: req.Description,
        Status:      model.StatusTodo,
        CreatedAt:   now,
        UpdatedAt:   now,
    }
    tasks = append(tasks, t)

    if err := fs.writeLocked(tasks); err != nil {
        return model.Task{}, err
    }
    return t, nil
}

func (fs *FileStore) Update(_ context.Context, id string, req model.UpdateTaskRequest) (model.Task, error) {
    fs.mu.Lock()
    defer fs.mu.Unlock()

    tasks, err := fs.readLocked()
    if err != nil {
        return model.Task{}, err
    }

    idx := -1
    for i, t := range tasks {
        if t.ID == id {
            idx = i
            break
        }
    }
    if idx == -1 {
        return model.Task{}, ErrNotFound
    }

    t := tasks[idx]
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
    tasks[idx] = t

    if err := fs.writeLocked(tasks); err != nil {
        return model.Task{}, err
    }
    return t, nil
}

func (fs *FileStore) Delete(_ context.Context, id string) error {
    fs.mu.Lock()
    defer fs.mu.Unlock()

    tasks, err := fs.readLocked()
    if err != nil {
        return err
    }

    idx := -1
    for i, t := range tasks {
        if t.ID == id {
            idx = i
            break
        }
    }
    if idx == -1 {
        return ErrNotFound
    }

    tasks = append(tasks[:idx], tasks[idx+1:]...)
    return fs.writeLocked(tasks)
}

// ─── Internal helpers (callers must hold the lock) ────────────────────────────

func (fs *FileStore) readLocked() ([]model.Task, error) {
    data, err := os.ReadFile(fs.path)
    if err != nil {
        return nil, fmt.Errorf("filestore: read %s: %w", fs.path, err)
    }

    var tasks []model.Task
    if err := json.Unmarshal(data, &tasks); err != nil {
        return nil, fmt.Errorf("filestore: parse %s: %w", fs.path, err)
    }
    return tasks, nil
}

// writeLocked writes atomically: write to a temp file, then rename over the target.
// rename is atomic on POSIX systems — readers always see a complete file.
func (fs *FileStore) writeLocked(tasks []model.Task) error {
    data, err := json.MarshalIndent(tasks, "", "  ")
    if err != nil {
        return fmt.Errorf("filestore: marshal: %w", err)
    }

    // Write to a temp file in the same directory (same filesystem → rename is atomic)
    dir := filepath.Dir(fs.path)
    tmp, err := os.CreateTemp(dir, ".tasks-*.tmp")
    if err != nil {
        return fmt.Errorf("filestore: create temp: %w", err)
    }
    tmpName := tmp.Name()

    // Ensure temp file is cleaned up on failure
    defer func() {
        tmp.Close()
        os.Remove(tmpName) // no-op if rename succeeded
    }()

    if _, err := tmp.Write(data); err != nil {
        return fmt.Errorf("filestore: write temp: %w", err)
    }
    if err := tmp.Sync(); err != nil { // flush to disk before rename
        return fmt.Errorf("filestore: sync temp: %w", err)
    }
    if err := tmp.Close(); err != nil {
        return fmt.Errorf("filestore: close temp: %w", err)
    }

    // Atomic rename — replaces the target file in one syscall
    if err := os.Rename(tmpName, fs.path); err != nil {
        return fmt.Errorf("filestore: rename: %w", err)
    }
    return nil
}
```

---

## Why Atomic Writes?

Without atomic writes, a crash mid-write leaves a partial (corrupt) JSON file:

```
// Without atomic write — crash here leaves a broken file:
os.WriteFile(path, data, 0644)
//             ↑ what if the process dies mid-write?

// With atomic write — file is always either old or new, never partial:
os.WriteFile(tmpPath, data, 0644)  // 1. write complete data to temp
os.Rename(tmpPath, path)           // 2. atomic swap — instantaneous
```

`os.Rename` is a single syscall — the OS swaps the directory entry atomically.

---

## Switching to FileStore in main.go

```go
func main() {
    dataPath := os.Getenv("DATA_PATH")
    if dataPath == "" {
        dataPath = "tasks.json"
    }

    var s store.Store
    var err error

    s, err = store.NewFileStore(dataPath)
    if err != nil {
        log.Fatalf("failed to open store: %v", err)
    }

    log.Printf("using file store: %s", dataPath)

    // rest of setup is identical — the Store interface hides the implementation
    taskHandler := handler.NewTaskHandler(s)
    // ...
}
```

Because the handlers depend on the `Store` interface, swapping MemoryStore for FileStore requires **no handler changes**.

---

## Integration Tests for FileStore

```go
// store/filestore_test.go
package store_test

import (
    "context"
    "os"
    "testing"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"
    "github.com/yourname/taskservice/model"
    "github.com/yourname/taskservice/store"
)

func newTestStore(t *testing.T) *store.FileStore {
    t.Helper()
    f, err := os.CreateTemp("", "tasks-test-*.json")
    require.NoError(t, err)
    f.Close()

    s, err := store.NewFileStore(f.Name())
    require.NoError(t, err)

    t.Cleanup(func() { os.Remove(f.Name()) })
    return s
}

func TestFileStore_CreateAndGet(t *testing.T) {
    s := newTestStore(t)
    ctx := context.Background()

    task, err := s.Create(ctx, model.CreateTaskRequest{
        Title:       "Buy groceries",
        Description: "Milk, eggs, bread",
    })
    require.NoError(t, err)
    assert.NotEmpty(t, task.ID)
    assert.Equal(t, "Buy groceries", task.Title)
    assert.Equal(t, model.StatusTodo, task.Status)

    got, err := s.Get(ctx, task.ID)
    require.NoError(t, err)
    assert.Equal(t, task, got)
}

func TestFileStore_Update(t *testing.T) {
    s   := newTestStore(t)
    ctx := context.Background()

    task, _ := s.Create(ctx, model.CreateTaskRequest{Title: "Write tests"})

    status := model.StatusInProgress
    updated, err := s.Update(ctx, task.ID, model.UpdateTaskRequest{Status: &status})
    require.NoError(t, err)
    assert.Equal(t, model.StatusInProgress, updated.Status)
    assert.True(t, updated.UpdatedAt.After(task.UpdatedAt))
}

func TestFileStore_Delete(t *testing.T) {
    s   := newTestStore(t)
    ctx := context.Background()

    task, _ := s.Create(ctx, model.CreateTaskRequest{Title: "Temporary"})

    err := s.Delete(ctx, task.ID)
    require.NoError(t, err)

    _, err = s.Get(ctx, task.ID)
    assert.ErrorIs(t, err, store.ErrNotFound)
}

func TestFileStore_NotFound(t *testing.T) {
    s := newTestStore(t)

    _, err := s.Get(context.Background(), "nonexistent-id")
    assert.ErrorIs(t, err, store.ErrNotFound)

    err = s.Delete(context.Background(), "nonexistent-id")
    assert.ErrorIs(t, err, store.ErrNotFound)
}

func TestFileStore_Persistence(t *testing.T) {
    // Create a task, close the store, reopen, verify data survived.
    f, _ := os.CreateTemp("", "tasks-persist-*.json")
    path := f.Name()
    f.Close()
    t.Cleanup(func() { os.Remove(path) })

    s1, _ := store.NewFileStore(path)
    task, _ := s1.Create(context.Background(), model.CreateTaskRequest{Title: "Persistent"})

    // Open a fresh store pointing at the same file
    s2, err := store.NewFileStore(path)
    require.NoError(t, err)

    got, err := s2.Get(context.Background(), task.ID)
    require.NoError(t, err)
    assert.Equal(t, "Persistent", got.Title)
}

func TestFileStore_Concurrent(t *testing.T) {
    s   := newTestStore(t)
    ctx := context.Background()

    // 50 goroutines each create a task concurrently
    done := make(chan struct{}, 50)
    for i := 0; i < 50; i++ {
        go func(n int) {
            _, err := s.Create(ctx, model.CreateTaskRequest{
                Title: fmt.Sprintf("task-%d", n),
            })
            assert.NoError(t, err)
            done <- struct{}{}
        }(i)
    }
    for i := 0; i < 50; i++ {
        <-done
    }

    tasks, err := s.List(ctx)
    require.NoError(t, err)
    assert.Len(t, tasks, 50)
}
```

---

## Complete Service: How the Layers Fit Together

```
HTTP Request
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  Global Middleware Stack                              │
│  Recovery → RequestID → Logger → CORS                │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  Route Middleware (selective)                         │
│  BearerAuth → RequireJSON                            │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  Handler (handler/task.go)                           │
│  1. Decode & validate request                        │
│  2. Call store method                                │
│  3. Map store error → HTTP status code               │
│  4. Write JSON response                              │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  Store (store/filestore.go)                          │
│  1. Acquire lock (RLock for reads, Lock for writes)  │
│  2. Read JSON file                                   │
│  3. Mutate in-memory slice                           │
│  4. Atomic write back to disk                        │
│  5. Release lock                                     │
└──────────────────────────────────────────────────────┘
    │
    ▼
  tasks.json  (human-readable, always-consistent file)
```

---

## Error Handling Flow

The full error journey from file to HTTP response:

```
os.ReadFile fails (disk full)
    → filestore returns: fmt.Errorf("filestore: read: %w", err)
    → store.List returns the wrapped error
    → handler receives the error
    → handler checks: errors.Is(err, store.ErrNotFound) → false
    → handler calls: writeError(w, 500, "internal_error", "failed to list tasks")
    → client receives: {"code":"internal_error","message":"failed to list tasks"}

store.Get, id not found
    → filestore returns: store.ErrNotFound
    → handler checks: errors.Is(err, store.ErrNotFound) → true
    → handler calls: writeError(w, 404, "not_found", "task not found")
    → client receives: {"code":"not_found","message":"task not found"}
```

---

## Running the Complete Service

```bash
# Build
go mod tidy
go build -o taskservice ./...

# Run (with file store)
DATA_PATH=./tasks.json API_TOKEN=mytoken ./taskservice

# Create a task
curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer mytoken" \
  -d '{"title":"Learn Go microservices","description":"Days 31-33"}'

# List tasks
curl http://localhost:8080/tasks \
  -H "Authorization: Bearer mytoken"

# Inspect the raw file — human readable!
cat tasks.json

# Run all tests with race detector
go test -race -cover ./...
```

---

## Gotchas

1. **Same-filesystem requirement for atomic rename** — the temp file and final file must be on the same filesystem/device. Always use `filepath.Dir(path)` as the temp directory.
2. **`tmp.Sync()` before rename** — without `fsync`, the data may still be in the OS page cache. A crash after rename but before sync can leave an empty file.
3. **`sync.RWMutex` is per-process** — if two processes share the same file, you need OS-level file locking (`syscall.Flock`).
4. **Large files** — this pattern reads and writes the entire file on every mutation. For files larger than ~10 MB, switch to a proper embedded database like `bbolt` or `sqlite`.

---

## Practice

1. Add `Search(ctx, query string) ([]Task, error)` to the Store interface and implement it in both MemoryStore and FileStore.
2. Add a `Backup(ctx)` endpoint that downloads the raw `tasks.json` file.
3. Simulate a crash mid-write (using `testing/iotest`) and verify the file is uncorrupted.
4. Add a `GET /tasks?status=in_progress` query parameter filter in the list handler.

---

## Key Takeaways

- Atomic writes (write temp → rename) prevent file corruption on crashes.
- `sync.RWMutex` makes the file store safe for concurrent goroutines within one process.
- Depend on the `Store` interface in handlers — swapping MemoryStore for FileStore requires no handler changes.
- Test persistence explicitly: create with store A, read with store B pointing at the same file.
