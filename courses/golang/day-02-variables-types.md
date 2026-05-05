# Day 02 — Variables & Basic Types

## Learning Objectives
- Declare variables using all three styles
- Understand Go's built-in types and their zero values
- Use type inference correctly
- Know when to use each declaration style

---

## Variable Declaration

Go has three ways to declare variables:

```go
// 1. Full declaration (explicit type)
var name string = "Alice"
var age int = 30

// 2. Type inference (Go figures out the type)
var score = 95.5  // float64

// 3. Short declaration — only inside functions
greeting := "Hello"   // string
count := 0            // int
pi := 3.14            // float64
```

**Rule:** Use `:=` inside functions (most common). Use `var` at package level or when you need a specific type.

---

## Multiple Assignment

```go
// Declare multiple variables at once
var x, y, z int = 1, 2, 3

// Short form
a, b := 10, "hello"

// Swap values — no temp variable needed
a, b = b, a  // won't compile here (types differ), but works with same types
x, y = y, x  // ✅ swap two ints
```

---

## Zero Values

In Go, every variable has a **zero value** — it's always initialized, never garbage.

| Type | Zero Value |
|---|---|
| `int`, `int8`, `int16`, `int32`, `int64` | `0` |
| `float32`, `float64` | `0.0` |
| `string` | `""` (empty string) |
| `bool` | `false` |
| `pointer`, `slice`, `map`, `channel`, `func` | `nil` |

```go
var count int     // count == 0
var name string   // name == ""
var flag bool     // flag == false
var ptr *int      // ptr == nil
```

---

## Built-in Types

### Integers

```go
var a int     = 42          // platform-dependent: 64-bit on 64-bit OS
var b int8    = 127         // -128 to 127
var c int16   = 32767
var d int32   = 2147483647
var e int64   = 9223372036854775807
var f uint    = 42          // unsigned
var g byte    = 255         // alias for uint8
var h rune    = 'A'         // alias for int32, represents a Unicode code point
```

**Tip:** Use `int` unless you have a specific reason for a sized type.

### Floats

```go
var f32 float32 = 3.14
var f64 float64 = 3.141592653589793  // prefer float64 — more precision
```

### Strings

```go
s := "Hello, 世界"       // UTF-8 encoded by default
length := len(s)         // byte length, NOT character count
runeCount := len([]rune(s))  // actual character count

// Raw string literal (no escape processing)
raw := `line one
line two
\n is literally backslash-n here`
```

### Booleans

```go
t := true
f := false
result := t && f   // false
other  := t || f   // true
neg    := !t       // false
```

---

## Type Conversion

Go does **not** do implicit type conversion. You must convert explicitly.

```go
var i int = 42
var f float64 = float64(i)   // must convert explicitly
var u uint = uint(f)

// String conversions
import "strconv"
n := 42
s := strconv.Itoa(n)       // int → string: "42"
n2, err := strconv.Atoi(s) // string → int: 42
```

**Common trap:**
```go
var x int = 5
var y float64 = 2.5
// z := x + y  ← compile error: mismatched types
z := float64(x) + y  // ✅
```

---

## Constants

```go
const Pi = 3.14159
const MaxRetries = 3
const AppName = "myapp"

// Multiple constants
const (
    StatusOK  = 200
    StatusNotFound = 404
)
```

Constants are **not typed** until used — this gives them more flexibility than variables.

---

## Gotchas

1. `:=` only works inside functions. At package level, use `var`.
2. `len()` on a string returns bytes, not characters — matters for Unicode.
3. No implicit type conversion — even `int` and `int32` are different types.
4. `rune` is just `int32`; use it when you care about Unicode characters.

---

## Practice

1. Declare variables of 5 different types using all declaration styles.
2. Print the zero value of `int`, `string`, `bool`, and a pointer.
3. Write a snippet that swaps two integers without a temp variable.
4. Convert the integer `2024` to a string and back.

---

## Key Takeaways

- `:=` is for function scope; `var` is for package scope.
- Every variable starts with a meaningful zero value — use this.
- Go never implicitly converts types — always be explicit.
- `string` length in bytes ≠ number of characters (use `rune` for Unicode).
