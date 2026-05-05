# Day 21 — File I/O

## Learning Objectives
- Read and write files using `os` and `bufio`
- Use `io.Reader` and `io.Writer` interfaces
- Walk directory trees
- Handle file operations safely

---

## Reading a Whole File

```go
// Simple: read entire file into memory
data, err := os.ReadFile("input.txt")
if err != nil {
    return fmt.Errorf("reading file: %w", err)
}
fmt.Println(string(data))
```

---

## Writing a Whole File

```go
content := []byte("Hello, Go!\n")
err := os.WriteFile("output.txt", content, 0644)
if err != nil {
    return fmt.Errorf("writing file: %w", err)
}
```

`0644` = owner read/write, group/others read-only. Use `0600` for sensitive files.

---

## Open, Read, Close

For more control (streaming large files, seeking):

```go
f, err := os.Open("input.txt")  // read-only
if err != nil {
    return err
}
defer f.Close()

buf := make([]byte, 1024)
for {
    n, err := f.Read(buf)
    if n > 0 {
        process(buf[:n])
    }
    if err == io.EOF {
        break
    }
    if err != nil {
        return err
    }
}
```

---

## Buffered Reading (line by line)

`bufio.Scanner` is the idiomatic way to read line by line:

```go
f, err := os.Open("input.txt")
if err != nil {
    return err
}
defer f.Close()

scanner := bufio.NewScanner(f)
for scanner.Scan() {
    line := scanner.Text()
    fmt.Println(line)
}
if err := scanner.Err(); err != nil {
    return err
}
```

For files with very long lines, set a larger buffer:
```go
scanner.Buffer(make([]byte, 1024*1024), 1024*1024)  // 1MB buffer
```

---

## Buffered Reading with bufio.Reader

```go
reader := bufio.NewReader(f)

// Read one line (includes '\n')
line, err := reader.ReadString('\n')

// Peek without consuming
bytes, err := reader.Peek(10)
```

---

## Writing with bufio.Writer

Always flush when done:

```go
f, err := os.Create("output.txt")  // create/truncate
if err != nil {
    return err
}
defer f.Close()

w := bufio.NewWriter(f)
fmt.Fprintln(w, "line 1")
fmt.Fprintln(w, "line 2")
if err := w.Flush(); err != nil {
    return err
}
```

---

## Append to a File

```go
f, err := os.OpenFile("log.txt", os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
if err != nil {
    return err
}
defer f.Close()

fmt.Fprintln(f, time.Now().Format(time.RFC3339), "event happened")
```

---

## File Info and stat

```go
info, err := os.Stat("file.txt")
if err != nil {
    if os.IsNotExist(err) {
        fmt.Println("file does not exist")
    }
    return err
}

fmt.Println("size:", info.Size())
fmt.Println("modified:", info.ModTime())
fmt.Println("is dir:", info.IsDir())
fmt.Println("permissions:", info.Mode())
```

---

## Working with Directories

```go
// Create directory (and parents)
os.MkdirAll("path/to/dir", 0755)

// List directory contents
entries, err := os.ReadDir(".")
for _, e := range entries {
    fmt.Printf("%s (dir: %v)\n", e.Name(), e.IsDir())
}

// Remove
os.Remove("file.txt")         // remove file or empty dir
os.RemoveAll("dir/")          // remove dir and all contents
```

---

## Walking a Directory Tree

```go
import "path/filepath"

err := filepath.WalkDir(".", func(path string, d fs.DirEntry, err error) error {
    if err != nil {
        return err
    }
    if !d.IsDir() {
        fmt.Println(path)
    }
    return nil
})
```

---

## Temp Files

```go
// Create a temp file
f, err := os.CreateTemp("", "myapp-*.tmp")
if err != nil {
    return err
}
defer os.Remove(f.Name())  // clean up
defer f.Close()

fmt.Fprintln(f, "temporary data")
```

---

## io.Copy — Efficient Copying

Don't read everything into memory:

```go
src, _ := os.Open("input.txt")
defer src.Close()

dst, _ := os.Create("output.txt")
defer dst.Close()

n, err := io.Copy(dst, src)
fmt.Printf("copied %d bytes\n", n)
```

`io.Copy` uses a small internal buffer — efficient for large files.

---

## Path Manipulation

```go
import "path/filepath"

filepath.Join("dir", "sub", "file.txt")  // dir/sub/file.txt
filepath.Base("/path/to/file.txt")       // file.txt
filepath.Dir("/path/to/file.txt")        // /path/to
filepath.Ext("file.txt")                 // .txt
filepath.Abs("relative/path")            // absolute path
```

Use `filepath.Join` instead of string concatenation — handles OS path separators.

---

## Gotchas

1. **Always `defer f.Close()`** right after the nil-check on `Open`.
2. **Check `scanner.Err()` after the scan loop** — it may have stopped due to an error, not EOF.
3. **`bufio.Writer` must be flushed** — data in the buffer is lost if you don't call `Flush`.
4. **`os.Create` truncates existing files** — use `os.OpenFile` with `O_APPEND` if you don't want to overwrite.

---

## Practice

1. Read a CSV file line by line and parse each line with `strings.Split`.
2. Write a program that counts the number of lines in a file.
3. Copy a file using `io.Copy` (not `os.ReadFile`).
4. Walk a directory tree and list all `.go` files.

---

## Key Takeaways

- `os.ReadFile`/`os.WriteFile` for small files; `bufio.Scanner` for large files line by line.
- Always `defer f.Close()` immediately after a successful open.
- `io.Copy` is efficient — never buffer an entire file just to copy it.
- `filepath.Join` for path building — never use `+` or `fmt.Sprintf` for paths.
