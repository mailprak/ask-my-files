# Day 07 — Maps

## Learning Objectives
- Create and use maps
- Safely check for key existence
- Iterate, delete, and combine maps
- Understand map gotchas around nil and concurrency

---

## Creating Maps

```go
// map literal
ages := map[string]int{
    "Alice": 30,
    "Bob":   25,
}

// make — preferred when you know the approximate size
scores := make(map[string]float64)

// nil map — can read from it, but NOT write to it
var m map[string]int  // nil
fmt.Println(m["key"]) // 0 — safe to read
m["key"] = 1          // ❌ panic: assignment to entry in nil map
```

---

## Read, Write, Delete

```go
m := map[string]int{"a": 1, "b": 2}

// Write
m["c"] = 3

// Read
v := m["a"]  // 1
missing := m["z"]  // 0 — zero value, no error

// Check existence (the comma-ok idiom)
v, ok := m["a"]
if ok {
    fmt.Println("found:", v)
} else {
    fmt.Println("not found")
}

// Delete
delete(m, "b")
fmt.Println(m)  // map[a:1 c:3]

// Delete a non-existent key — no error
delete(m, "nonexistent")
```

---

## Iterating

```go
m := map[string]int{"x": 10, "y": 20, "z": 30}

for k, v := range m {
    fmt.Printf("%s = %d\n", k, v)
}

// Keys only
for k := range m {
    fmt.Println(k)
}
```

**Map iteration order is not guaranteed.** Go randomizes it. Never rely on order.

---

## Sorted Map Iteration

```go
import "sort"

m := map[string]int{"banana": 2, "apple": 5, "cherry": 1}

keys := make([]string, 0, len(m))
for k := range m {
    keys = append(keys, k)
}
sort.Strings(keys)

for _, k := range keys {
    fmt.Printf("%s: %d\n", k, m[k])
}
```

---

## Map of Slices

```go
groups := make(map[string][]string)
groups["fruits"] = append(groups["fruits"], "apple")
groups["fruits"] = append(groups["fruits"], "banana")
groups["vegs"]   = append(groups["vegs"], "carrot")

fmt.Println(groups["fruits"])  // [apple banana]
```

This works because reading a missing key returns the zero value (nil slice), and `append` handles nil slices.

---

## Counting Frequencies

```go
words := []string{"go", "is", "go", "great", "go"}

freq := make(map[string]int)
for _, w := range words {
    freq[w]++  // zero value of int is 0, so this is always safe
}

fmt.Println(freq)  // map[go:3 great:1 is:1]
```

---

## Set Pattern

Go has no built-in set type. Use `map[T]struct{}`:

```go
set := make(map[string]struct{})
set["apple"] = struct{}{}
set["banana"] = struct{}{}

// Check membership
_, exists := set["apple"]
fmt.Println(exists)  // true

// Remove
delete(set, "apple")
```

`struct{}` takes zero bytes — it's purely a presence marker.

---

## Nested Maps

```go
config := map[string]map[string]string{
    "db": {
        "host": "localhost",
        "port": "5432",
    },
    "cache": {
        "host": "redis",
        "port": "6379",
    },
}

fmt.Println(config["db"]["host"])  // localhost
```

---

## Maps Are Reference Types

```go
original := map[string]int{"a": 1}
copy := original  // this is NOT a copy — both point to the same map

copy["b"] = 2
fmt.Println(original)  // map[a:1 b:2] — original was also modified
```

To copy a map, copy it manually:
```go
clone := make(map[string]int, len(original))
for k, v := range original {
    clone[k] = v
}
```

---

## Gotchas

1. **Writing to a nil map panics** — always initialize with `make` or a literal.
2. **Maps are not safe for concurrent use** — if multiple goroutines read and write, use `sync.RWMutex` or `sync.Map`.
3. **Comparison** — maps cannot be compared with `==` (only `== nil` is allowed). Use `reflect.DeepEqual` or compare manually.
4. **Zero value on read** — reading a missing key returns the zero value silently. Use the comma-ok idiom when absence matters.

---

## Practice

1. Count character frequencies in a string using a `map[rune]int`.
2. Implement a word grouper: group words by their first letter using `map[rune][]string`.
3. Build a `Set[string]` using `map[string]struct{}` and write Add/Contains/Remove operations.
4. Sort a map by its values (reverse the key-value roles).

---

## Key Takeaways

- Always initialize maps — never write to a nil map.
- The comma-ok idiom `v, ok := m[k]` distinguishes "zero value stored" from "key absent".
- Map iteration order is random — sort keys explicitly if order matters.
- Maps are reference types — assigning doesn't copy, it aliases.
