# Day 05 — Control Flow

## Learning Objectives
- Use `if/else` with init statements
- Master Go's `for` loop (the only loop in Go)
- Write expressive `switch` statements
- Understand `break`, `continue`, and labeled statements

---

## if / else

```go
x := 10

if x > 5 {
    fmt.Println("big")
} else if x == 5 {
    fmt.Println("five")
} else {
    fmt.Println("small")
}
```

### Init Statement in if

Go's `if` can have an initialization statement before the condition. The variable is scoped to the `if` block:

```go
if n, err := strconv.Atoi("42"); err == nil {
    fmt.Println("Parsed:", n)  // n is only visible here
} else {
    fmt.Println("Error:", err)
}
// n is not accessible here
```

This is idiomatic for error checks — keeps the error variable close to where it's used.

---

## for — The Only Loop

Go has one loop construct: `for`. It covers all looping patterns.

### C-style for loop
```go
for i := 0; i < 5; i++ {
    fmt.Println(i)  // 0, 1, 2, 3, 4
}
```

### While-style (condition only)
```go
n := 1
for n < 100 {
    n *= 2
}
```

### Infinite loop
```go
for {
    // runs forever; use break to exit
    if done {
        break
    }
}
```

### Range — iterate over slices, maps, strings, channels
```go
nums := []int{10, 20, 30}

// index and value
for i, v := range nums {
    fmt.Printf("nums[%d] = %d\n", i, v)
}

// index only
for i := range nums {
    fmt.Println(i)
}

// value only (discard index)
for _, v := range nums {
    fmt.Println(v)
}

// Map
m := map[string]int{"a": 1, "b": 2}
for k, v := range m {
    fmt.Printf("%s: %d\n", k, v)
}

// String — iterates over runes (Unicode characters), not bytes
for i, ch := range "Hello, 世界" {
    fmt.Printf("%d: %c\n", i, ch)
}
```

---

## break and continue

```go
for i := 0; i < 10; i++ {
    if i == 3 {
        continue  // skip to next iteration
    }
    if i == 7 {
        break     // exit the loop
    }
    fmt.Println(i)  // prints 0, 1, 2, 4, 5, 6
}
```

---

## Labeled break/continue (for nested loops)

```go
outer:
    for i := 0; i < 3; i++ {
        for j := 0; j < 3; j++ {
            if i == 1 && j == 1 {
                break outer   // breaks the OUTER loop
            }
            fmt.Printf("(%d,%d) ", i, j)
        }
    }
// Output: (0,0) (0,1) (0,2) (1,0)
```

---

## switch

Go's `switch` is more powerful than C's:
- No automatic fallthrough (no `break` needed)
- Cases can have multiple values
- Cases can have conditions (no value needed)

```go
day := "Monday"

switch day {
case "Saturday", "Sunday":
    fmt.Println("Weekend")
case "Monday":
    fmt.Println("Back to work")
default:
    fmt.Println("Weekday")
}
```

### Expression-less switch (replaces if-else chains)
```go
score := 85

switch {
case score >= 90:
    fmt.Println("A")
case score >= 80:
    fmt.Println("B")
case score >= 70:
    fmt.Println("C")
default:
    fmt.Println("F")
}
```

### switch with init statement
```go
switch n := len(s); {
case n < 10:
    fmt.Println("short")
case n < 100:
    fmt.Println("medium")
default:
    fmt.Println("long")
}
```

### Explicit fallthrough
```go
switch x {
case 1:
    fmt.Println("one")
    fallthrough   // explicitly fall to next case
case 2:
    fmt.Println("one or two")
}
```

---

## goto (exists but avoid it)

Go has `goto` but it's rarely used and considered bad practice. Labeled `break`/`continue` is almost always the right tool instead.

---

## Gotchas

1. **No parentheses around conditions** — `if (x > 0)` compiles but `gofmt` removes the parens.
2. **`range` on a nil slice** is safe — it just doesn't iterate.
3. **`range` gives a copy** of each value — modifying the range variable doesn't modify the original slice element.
4. **`switch` cases don't fall through by default** — this is the opposite of C/Java.
5. **Map iteration order is randomized** — Go intentionally randomizes it to prevent code depending on a specific order.

```go
// Gotcha: modifying range value doesn't affect slice
nums := []int{1, 2, 3}
for _, n := range nums {
    n = n * 2  // only modifies local copy
}
// nums is still [1, 2, 3]

// Fix: use index
for i := range nums {
    nums[i] *= 2
}
// nums is now [2, 4, 6]
```

---

## Practice

1. Print all even numbers from 0 to 20 using a `for` loop.
2. Use a range loop to find the sum of a `[]float64` slice.
3. Use an expression-less `switch` to print a letter grade for a score.
4. Use a labeled break to exit a nested loop when a condition is met.

---

## Key Takeaways

- `for` is the only loop — it handles while, do-while, and range patterns.
- `range` on strings gives runes (Unicode), not bytes.
- `switch` doesn't fall through by default — use `fallthrough` explicitly if needed.
- The `if init; condition` pattern is idiomatic for scoping error checks.
