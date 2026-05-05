# Day 03 — Constants & iota

## Learning Objectives
- Understand untyped vs typed constants
- Use `iota` to create enumeration-like sequences
- Apply `iota` with expressions and bitmasks

---

## Constants Basics

```go
const Pi = 3.14159265358979   // untyped float constant
const AppVersion = "1.0.0"    // untyped string constant
const MaxItems = 100          // untyped int constant

// Typed constant — less flexible
const TypedPi float64 = 3.14
```

Constants must be known at compile time. These are NOT allowed:
```go
// ❌ Cannot use a function call as a constant
const Now = time.Now()
const Rand = rand.Int()
```

---

## Untyped Constants Are Flexible

Untyped constants take the type they need at point of use:

```go
const n = 1000

var x int    = n   // n becomes int
var y float64 = n  // n becomes float64
var z int64  = n   // n becomes int64
```

This is why you can write `time.Sleep(5 * time.Second)` — `5` is an untyped constant that becomes `time.Duration`.

---

## iota — Auto-incrementing Values

`iota` is a special counter that resets to 0 in every `const` block and increments by 1 for each constant spec.

```go
const (
    Sunday = iota  // 0
    Monday         // 1
    Tuesday        // 2
    Wednesday      // 3
    Thursday       // 4
    Friday         // 5
    Saturday       // 6
)

fmt.Println(Monday)    // 1
fmt.Println(Saturday)  // 6
```

---

## Skipping Values with `_`

```go
const (
    _           = iota  // 0 — skip zero value (common pattern)
    StatusSmall         // 1
    StatusMedium        // 2
    StatusLarge         // 3
)
```

---

## iota with Expressions

```go
// Powers of 2
const (
    KB = 1 << (10 * (iota + 1))  // 1 << 10 = 1024
    MB                            // 1 << 20
    GB                            // 1 << 30
    TB                            // 1 << 40
)

fmt.Println(KB)  // 1024
fmt.Println(MB)  // 1048576
fmt.Println(GB)  // 1073741824
```

---

## Bitmask Flags with iota

```go
type Permission uint

const (
    Read    Permission = 1 << iota  // 1  (001)
    Write                           // 2  (010)
    Execute                         // 4  (100)
)

// Combine permissions
userPerm := Read | Write  // 3 (011)

// Check permission
if userPerm & Read != 0 {
    fmt.Println("Can read")
}
if userPerm & Execute == 0 {
    fmt.Println("Cannot execute")
}
```

---

## Stringer Pattern — iota with Named Types

A common Go pattern: create a named type with iota and add a `String()` method:

```go
type Direction int

const (
    North Direction = iota
    East
    South
    West
)

func (d Direction) String() string {
    return [...]string{"North", "East", "South", "West"}[d]
}

func main() {
    d := North
    fmt.Println(d)         // "North" — calls String() automatically
    fmt.Println(d == East) // false
}
```

---

## Multiple iota in One Spec (Rare)

```go
const (
    a, b = iota, iota * 10  // a=0, b=0
    c, d                     // c=1, d=10
    e, f                     // e=2, f=20
)
```

Each **line** increments iota, not each identifier.

---

## Gotchas

1. `iota` resets to 0 at the start of each `const` block — not per file.
2. If you add a constant in the middle of an `iota` block, all values after it shift — this is a **breaking change** if the values are stored or serialized.
3. Typed constants are strict: `const x float32 = 1.0` cannot be used where `float64` is expected without conversion.

---

## Practice

1. Create a `Weekday` type with `iota` and a `String()` method.
2. Define `FilePermission` flags using bitmask iota for Read/Write/Execute.
3. Create `ByteSize` constants KB, MB, GB, TB using `iota` expressions.

---

## Key Takeaways

- Untyped constants are more flexible than typed ones — prefer them when possible.
- `iota` auto-increments per line within a `const` block, resetting to 0 per block.
- Use `iota` with bit shifts for bitmask flags.
- Adding values in the middle of an iota block shifts all following values — document and version carefully.
