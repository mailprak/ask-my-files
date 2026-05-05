# Day 14 — Packages & Modules

## Learning Objectives
- Understand Go's package and module system
- Export and unexport identifiers
- Organize code into multiple packages
- Manage dependencies with `go.mod` and `go.sum`

---

## Packages

A package is a directory of `.go` files that share the same `package` declaration.

```
myapp/
├── go.mod
├── main.go           ← package main
├── user/
│   └── user.go       ← package user
└── db/
    ├── db.go         ← package db
    └── migrate.go    ← package db (same package, different file)
```

Rules:
- All files in the same directory must have the same package name.
- The directory name and package name should match (by convention).
- `package main` + `func main()` = the entry point.

---

## Exported vs Unexported

**Capitalized = exported (public)**
**Lowercase = unexported (package-private)**

```go
// user/user.go
package user

type User struct {          // exported — visible to other packages
    Name  string            // exported field
    Email string            // exported field
    hash  string            // unexported — only accessible within the 'user' package
}

func New(name, email string) *User {  // exported function
    return &User{Name: name, Email: email}
}

func (u *User) SetPassword(pw string) {  // exported method
    u.hash = hashPassword(pw)            // calls unexported function
}

func hashPassword(pw string) string {    // unexported
    // ...
}
```

---

## Importing Packages

```go
package main

import (
    "fmt"
    "os"

    // Standard library uses bare names
    // Third-party and internal use full module paths
    "github.com/myname/myapp/user"
)

func main() {
    u := user.New("Alice", "alice@example.com")
    fmt.Println(u.Name)
}
```

### Import Aliases

```go
import (
    "math/rand"
    crand "crypto/rand"    // alias to avoid collision
    _ "image/png"          // blank import — side effects only (init runs)
    . "fmt"                // dot import — brings names into current scope (avoid this)
)
```

---

## Package Initialization: `init`

Each package can have one or more `init()` functions. They run automatically before `main()` in dependency order.

```go
package db

var pool *sql.DB

func init() {
    var err error
    pool, err = sql.Open("postgres", os.Getenv("DATABASE_URL"))
    if err != nil {
        log.Fatal("db init failed:", err)
    }
}
```

- `init` cannot be called manually.
- Multiple `init` functions in one file are allowed (run top to bottom).
- Blank imports `_` are used to trigger `init` without using any exported names (e.g., database drivers).

---

## go.mod — Module Definition

```
module github.com/yourname/myapp

go 1.22

require (
    github.com/gin-gonic/gin v1.9.1
    golang.org/x/crypto v0.21.0
)
```

- `module` — the module's import path
- `go` — minimum Go version
- `require` — direct dependencies

---

## Managing Dependencies

```bash
# Add a dependency
go get github.com/some/package@v1.2.3

# Add latest version
go get github.com/some/package@latest

# Remove unused deps & add missing ones
go mod tidy

# Download all deps to local cache
go mod download

# Vendor (copy deps into ./vendor)
go mod vendor
```

---

## go.sum — Integrity File

`go.sum` is auto-managed. It contains cryptographic hashes of every dependency. Commit it to version control — it ensures reproducible, tamper-proof builds.

---

## Internal Packages

The `internal` directory restricts imports to the parent module only:

```
myapp/
├── internal/
│   └── auth/
│       └── auth.go    ← only importable by myapp/* packages
└── api/
    └── api.go         ← can import internal/auth
```

External modules cannot import `internal/` packages — enforced by the compiler.

---

## Package Naming Conventions

| Convention | Example |
|---|---|
| Short, lowercase | `user`, `db`, `http` |
| No underscores | `userservice` not `user_service` |
| Singular | `user` not `users` |
| Doc says what it provides | Package `user` provides user management |
| Avoid generic names | Not `util`, `common`, `helpers` |

---

## init Order

1. All imported packages initialize first (recursively)
2. Package-level variables initialize in declaration order
3. `init()` functions run (all of them, in source order)
4. `main()` runs

---

## Gotchas

1. **Circular imports are not allowed** — if package A imports B and B imports A, it won't compile. Restructure with a shared interface or a third package.
2. **`init` side effects can be hard to test** — keep `init` minimal.
3. **Blank imports for side effects** — always comment why: `_ "github.com/lib/pq" // register postgres driver`
4. **`go mod tidy` before committing** — removes unused deps, adds missing ones.

---

## Practice

1. Create a `calculator` package with `Add`, `Subtract`, `Multiply` functions. Use it from `main`.
2. Add an `internal/config` package and verify external packages cannot import it.
3. Add a third-party dependency (e.g., `github.com/fatih/color`), run `go mod tidy`, and use it.
4. Write an `init()` function that pre-loads a lookup table.

---

## Key Takeaways

- Capital = exported, lowercase = unexported — this is the only access control mechanism.
- Every project has a `go.mod`; always commit `go.sum`.
- Use `internal/` to restrict packages to your module only.
- Avoid circular imports by extracting shared types to a third package.
