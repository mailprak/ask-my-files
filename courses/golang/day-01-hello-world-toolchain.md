# Day 01 — Hello World & the Go Toolchain

## Learning Objectives
- Install Go and verify the setup
- Understand the Go workspace and module system
- Write and run a Hello World program
- Learn the essential `go` CLI commands

---

## Setting Up

```bash
# Install on macOS
brew install go

# Verify
go version
# go version go1.22.0 darwin/arm64
```

Environment variables that matter:
- `GOPATH` — your workspace root (default: `~/go`)
- `GOROOT` — where Go is installed (don't touch this)
- `GOBIN` — where `go install` puts binaries

---

## Your First Program

```go
package main

import "fmt"

func main() {
    fmt.Println("Hello, World!")
}
```

Save as `main.go`, then:

```bash
go run main.go        # compile + run immediately
go build -o hello .   # compile to a binary
./hello               # run the binary
```

**Key rule:** Every runnable Go program must have `package main` and a `func main()`.

---

## Go Modules (go.mod)

Every Go project is a module. Initialize one with:

```bash
mkdir myproject && cd myproject
go mod init github.com/yourname/myproject
```

This creates `go.mod`:
```
module github.com/yourname/myproject

go 1.22
```

The module path is just a name — it doesn't need to match a real URL for local projects.

---

## Essential `go` Commands

| Command | What it does |
|---|---|
| `go run .` | Compile and run the package in current dir |
| `go build .` | Compile, produce a binary |
| `go test ./...` | Run all tests recursively |
| `go fmt ./...` | Format all Go files (do this always) |
| `go vet ./...` | Static analysis — catches common mistakes |
| `go get pkg` | Add a dependency |
| `go mod tidy` | Clean up unused deps in go.mod/go.sum |
| `go doc fmt.Println` | Show docs for any symbol |

---

## How Go Organizes Code

```
myproject/
├── go.mod
├── main.go          ← package main
├── utils/
│   └── helpers.go   ← package utils
└── models/
    └── user.go      ← package models
```

- One **package** per directory
- Package name == directory name (by convention)
- Files in the same directory share the same package

---

## Gotchas on Day 1

1. **Unused imports are a compile error** — Go won't compile if you import something you don't use.
2. **Unused variables are also a compile error** — declare a variable, use it.
3. **`go fmt` is not optional** — the entire Go community uses `gofmt`. Set your editor to run it on save.
4. **Semicolons are automatic** — never write them manually; `gofmt` handles it.

---

## Practice

1. Install Go, run `go version`.
2. Create a new module, write Hello World, run it with `go run`.
3. Build it to a binary and run the binary.
4. Try adding an unused import and see the compile error.

---

## Key Takeaways

- `go run` is for quick execution; `go build` is for producing binaries.
- Every project starts with `go mod init`.
- `go fmt` is mandatory — embrace it.
- Unused imports and variables are **compile errors**, not warnings.
