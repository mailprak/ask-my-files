# Day 27 — Generics (Go 1.18+)

## Learning Objectives
- Write generic functions with type parameters
- Use type constraints
- Build generic data structures
- Know when to use generics vs interfaces

---

## Why Generics?

Before Go 1.18, you needed either:
- A separate function per type: `SumInts`, `SumFloat64s`...
- Use `interface{}` and lose type safety

Generics let you write one function that works for multiple types with full type safety.

---

## Generic Functions

```go
// Without generics — works for int only
func SumInts(nums []int) int {
    total := 0
    for _, n := range nums {
        total += n
    }
    return total
}

// With generics — works for any numeric type
func Sum[T int | float64](nums []T) T {
    var total T
    for _, n := range nums {
        total += n
    }
    return total
}

fmt.Println(Sum([]int{1, 2, 3}))           // 6
fmt.Println(Sum([]float64{1.5, 2.5, 3.0})) // 7.0
```

---

## Type Parameters and Constraints

The syntax: `[TypeParam Constraint]`

```go
// any — no constraint (can be any type)
func Print[T any](v T) {
    fmt.Println(v)
}

// comparable — can be compared with == and !=
func Contains[T comparable](slice []T, item T) bool {
    for _, v := range slice {
        if v == item {
            return true
        }
    }
    return false
}

Contains([]int{1, 2, 3}, 2)         // true
Contains([]string{"a", "b"}, "c")   // false
```

---

## Custom Constraints

Define constraints as interfaces:

```go
type Number interface {
    int | int8 | int16 | int32 | int64 |
    float32 | float64
}

func Sum[T Number](nums []T) T {
    var total T
    for _, n := range nums {
        total += n
    }
    return total
}
```

---

## golang.org/x/exp/constraints Package

Common pre-defined constraints:

```go
import "golang.org/x/exp/constraints"

func Min[T constraints.Ordered](a, b T) T {
    if a < b {
        return a
    }
    return b
}

// constraints.Ordered includes all types that support <, >, <=, >=
// (integers, floats, strings)
```

---

## Generic Data Structures

```go
// Generic stack
type Stack[T any] struct {
    items []T
}

func (s *Stack[T]) Push(item T) {
    s.items = append(s.items, item)
}

func (s *Stack[T]) Pop() (T, bool) {
    if len(s.items) == 0 {
        var zero T
        return zero, false
    }
    last := s.items[len(s.items)-1]
    s.items = s.items[:len(s.items)-1]
    return last, true
}

func (s *Stack[T]) Len() int {
    return len(s.items)
}

// Usage
s := Stack[int]{}
s.Push(1)
s.Push(2)
v, _ := s.Pop()  // v == 2
```

---

## Generic Map/Filter/Reduce

```go
func Map[T, U any](slice []T, f func(T) U) []U {
    result := make([]U, len(slice))
    for i, v := range slice {
        result[i] = f(v)
    }
    return result
}

func Filter[T any](slice []T, pred func(T) bool) []T {
    var result []T
    for _, v := range slice {
        if pred(v) {
            result = append(result, v)
        }
    }
    return result
}

func Reduce[T, U any](slice []T, init U, f func(U, T) U) U {
    acc := init
    for _, v := range slice {
        acc = f(acc, v)
    }
    return acc
}

// Usage
nums := []int{1, 2, 3, 4, 5}
doubled := Map(nums, func(n int) int { return n * 2 })
evens   := Filter(nums, func(n int) bool { return n%2 == 0 })
total   := Reduce(nums, 0, func(acc, n int) int { return acc + n })
```

---

## Type Inference

Go infers type parameters from arguments — you rarely need to specify them explicitly:

```go
Contains([]int{1, 2, 3}, 2)   // T inferred as int
Min(3.14, 2.71)                 // T inferred as float64

// Explicit when inference can't figure it out
Map[int, string](nums, strconv.Itoa)
```

---

## Tilde (~) — Underlying Type Constraint

`~int` means "any type whose underlying type is int":

```go
type MyInt int

type Signed interface {
    ~int | ~int8 | ~int16 | ~int32 | ~int64
}

func Abs[T Signed](n T) T {
    if n < 0 {
        return -n
    }
    return n
}

Abs(MyInt(-5))  // works because MyInt's underlying type is int
```

---

## When to Use Generics vs Interfaces

| Use generics when... | Use interfaces when... |
|---|---|
| You need type safety with multiple concrete types | Behaviour varies, not just types |
| Working with collections (Map, Filter, Set) | Runtime polymorphism (different types doing different things) |
| Algorithms that work on ordered/numeric types | Dependency injection, mocking |
| Eliminating code duplication between similar typed functions | Unknown types at compile time |

---

## Gotchas

1. **Methods can't have type parameters** — only functions and types can be generic.
```go
// ❌ Not allowed
func (s *Stack[T]) Map[U any](f func(T) U) []U { ... }

// ✅ Use a top-level function instead
func StackMap[T, U any](s *Stack[T], f func(T) U) []U { ... }
```

2. **Can't use operators on unconstrained type parameters** — you need `constraints.Ordered` for `<`, or a specific constraint for `+`.
3. **Type inference doesn't always work** — when the return type is generic but no argument matches it.

---

## Practice

1. Write a generic `Keys[K comparable, V any](map[K]V) []K` function.
2. Implement a generic `Set[T comparable]` with Add/Contains/Remove.
3. Write `MapValues[K comparable, V, U any](m map[K]V, f func(V) U) map[K]U`.
4. Compare the generic `Min` vs interface-based approach for performance.

---

## Key Takeaways

- Generic syntax: `func Fn[T Constraint](arg T) T`
- Use `any` for unconstrained; `comparable` for equality; custom interface for operators.
- `~T` matches named types with T as the underlying type.
- Generics shine for collections and algorithms; interfaces shine for polymorphic behaviour.
