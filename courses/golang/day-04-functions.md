# Day 04 — Functions

## Learning Objectives
- Write functions with single and multiple return values
- Use named return values
- Understand variadic functions
- Treat functions as first-class values
- Write anonymous functions and closures

---

## Basic Function Syntax

```go
func add(a int, b int) int {
    return a + b
}

// Shorthand when params share a type
func multiply(a, b int) int {
    return a * b
}

// No return value
func greet(name string) {
    fmt.Println("Hello,", name)
}
```

---

## Multiple Return Values

This is one of Go's most-used features. The standard pattern for returning a result and an error:

```go
func divide(a, b float64) (float64, error) {
    if b == 0 {
        return 0, fmt.Errorf("cannot divide by zero")
    }
    return a / b, nil
}

// Calling it
result, err := divide(10, 3)
if err != nil {
    log.Fatal(err)
}
fmt.Println(result)  // 3.3333...
```

**Convention:** The error is always the last return value.

---

## Ignoring Return Values with `_`

```go
result, _ := divide(10, 2)  // ignore the error (only do this if you're sure)
```

---

## Named Return Values

Named returns let you declare what you're returning. Useful for short functions or documentation:

```go
func minMax(nums []int) (min, max int) {
    min, max = nums[0], nums[0]
    for _, n := range nums[1:] {
        if n < min { min = n }
        if n > max { max = n }
    }
    return  // "naked return" — returns min and max
}
```

**Warning:** Naked returns in long functions hurt readability. Prefer them only in short functions.

---

## Variadic Functions

Accept a variable number of arguments with `...`:

```go
func sum(nums ...int) int {
    total := 0
    for _, n := range nums {
        total += n
    }
    return total
}

sum(1, 2, 3)         // 6
sum(1, 2, 3, 4, 5)   // 15

// Spread a slice into a variadic function
nums := []int{1, 2, 3}
sum(nums...)          // spread operator
```

`fmt.Println` is variadic: `func Println(a ...any) (n int, err error)`.

---

## Functions as Values

Functions are first-class citizens in Go:

```go
// Assign a function to a variable
double := func(n int) int { return n * 2 }
fmt.Println(double(5))  // 10

// Pass a function as an argument
func apply(nums []int, f func(int) int) []int {
    result := make([]int, len(nums))
    for i, n := range nums {
        result[i] = f(n)
    }
    return result
}

doubled := apply([]int{1, 2, 3}, double)  // [2, 4, 6]
```

---

## Anonymous Functions

```go
// Immediately invoked
result := func(a, b int) int {
    return a + b
}(3, 4)
// result == 7

// Assigned to a variable
square := func(n int) int { return n * n }
```

---

## Closures

A closure captures variables from the surrounding scope:

```go
func makeCounter() func() int {
    count := 0
    return func() int {
        count++
        return count
    }
}

counter := makeCounter()
fmt.Println(counter())  // 1
fmt.Println(counter())  // 2
fmt.Println(counter())  // 3

// Each call to makeCounter creates an independent counter
other := makeCounter()
fmt.Println(other())    // 1 — independent from counter
```

---

## Function Types

You can declare a type for a function signature:

```go
type MathFunc func(int, int) int

func operate(a, b int, op MathFunc) int {
    return op(a, b)
}

add := MathFunc(func(a, b int) int { return a + b })
fmt.Println(operate(3, 4, add))  // 7
```

---

## Gotchas

1. **Unused return values don't cause compile errors** (unlike unused variables), but ignoring errors is a bad habit.
2. **Closures capture by reference** — the classic loop bug:
```go
// BUG: all closures capture the same 'i' variable
funcs := make([]func(), 3)
for i := 0; i < 3; i++ {
    funcs[i] = func() { fmt.Println(i) }
}
funcs[0]()  // prints 3, not 0 ❌

// FIX: capture by value
for i := 0; i < 3; i++ {
    i := i  // shadow 'i' with a new variable
    funcs[i] = func() { fmt.Println(i) }
}
funcs[0]()  // prints 0 ✅
```

---

## Practice

1. Write `divide(a, b float64) (float64, error)` with proper error handling.
2. Write a variadic `max(...int) int` function.
3. Write `makeAdder(n int) func(int) int` — a closure that adds `n` to its argument.
4. Use a function as an argument to filter a `[]int` slice.

---

## Key Takeaways

- Multiple returns + errors is the Go way — always return `(value, error)`.
- Use `_` to discard return values you genuinely don't need.
- Closures capture by reference — watch for the loop bug.
- Functions as values enable functional patterns without needing generics for simple cases.
