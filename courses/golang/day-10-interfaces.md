# Day 10 — Interfaces

## Learning Objectives
- Define and implement interfaces implicitly
- Understand interface values (type + value)
- Use the empty interface and `any`
- Write interface-driven code

---

## What Is an Interface?

An interface defines a **set of method signatures**. Any type that implements all those methods satisfies the interface — no `implements` keyword needed.

```go
type Shape interface {
    Area() float64
    Perimeter() float64
}
```

---

## Implicit Implementation

```go
type Rectangle struct {
    Width, Height float64
}

func (r Rectangle) Area() float64 {
    return r.Width * r.Height
}

func (r Rectangle) Perimeter() float64 {
    return 2 * (r.Width + r.Height)
}

type Circle struct {
    Radius float64
}

func (c Circle) Area() float64 {
    return math.Pi * c.Radius * c.Radius
}

func (c Circle) Perimeter() float64 {
    return 2 * math.Pi * c.Radius
}

// Both Rectangle and Circle satisfy Shape automatically
var s Shape = Rectangle{3, 4}
fmt.Println(s.Area())  // 12

s = Circle{5}
fmt.Println(s.Area())  // 78.53...
```

---

## Interface-Driven Functions

```go
func printShapeInfo(s Shape) {
    fmt.Printf("Area: %.2f, Perimeter: %.2f\n", s.Area(), s.Perimeter())
}

printShapeInfo(Rectangle{3, 4})
printShapeInfo(Circle{5})
```

This is polymorphism in Go — write code against the interface, not the concrete type.

---

## Interface Values

An interface value has two components: `(type, value)`.

```go
var s Shape               // (nil, nil)
s = Rectangle{3, 4}      // (*Rectangle, {3, 4}) or (Rectangle, {3, 4})
```

An interface is nil only when both the type and value are nil.

---

## The Stringer Interface

`fmt.Stringer` is the most common interface in Go:

```go
type Stringer interface {
    String() string
}
```

Implement it to control how your type prints:

```go
type Point struct{ X, Y int }

func (p Point) String() string {
    return fmt.Sprintf("(%d, %d)", p.X, p.Y)
}

p := Point{3, 4}
fmt.Println(p)  // (3, 4) — fmt calls String() automatically
```

---

## The error Interface

```go
type error interface {
    Error() string
}
```

Implement a custom error:

```go
type ValidationError struct {
    Field   string
    Message string
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation failed on %s: %s", e.Field, e.Message)
}

func validate(name string) error {
    if name == "" {
        return &ValidationError{Field: "name", Message: "cannot be empty"}
    }
    return nil
}
```

---

## The io.Reader and io.Writer Interfaces

These are the backbone of Go I/O:

```go
type Reader interface {
    Read(p []byte) (n int, err error)
}

type Writer interface {
    Write(p []byte) (n int, err error)
}
```

Any type implementing `Read` can be passed to functions that accept `io.Reader` — files, network connections, in-memory buffers, etc. This is why Go I/O is so composable.

---

## Small Interfaces Are Better

Go's philosophy: prefer small, focused interfaces.

```go
// ❌ Too big — hard to implement, hard to test
type Database interface {
    Find(id int) User
    Save(u User) error
    Delete(id int) error
    List() []User
    // ... 10 more methods
}

// ✅ Small, composable
type UserReader interface {
    Find(id int) (User, error)
}

type UserWriter interface {
    Save(u User) error
}
```

---

## Type Assertions

Extract the underlying concrete type from an interface:

```go
var s Shape = Circle{Radius: 5}

// Assert — panics if wrong type
c := s.(Circle)
fmt.Println(c.Radius)  // 5

// Safe assertion — comma-ok idiom
c, ok := s.(Circle)
if ok {
    fmt.Println("it's a Circle with radius", c.Radius)
} else {
    fmt.Println("not a Circle")
}
```

---

## Type Switch

```go
func describe(i interface{}) {
    switch v := i.(type) {
    case int:
        fmt.Printf("int: %d\n", v)
    case string:
        fmt.Printf("string: %q\n", v)
    case bool:
        fmt.Printf("bool: %t\n", v)
    default:
        fmt.Printf("unknown type: %T\n", v)
    }
}
```

---

## The Empty Interface: `any`

`any` (alias for `interface{}`) accepts any type:

```go
var v any = 42
v = "hello"
v = []int{1, 2, 3}

// Use sparingly — you lose type safety
func printAnything(v any) {
    fmt.Println(v)
}
```

Prefer concrete types or constrained generics over `any` where possible.

---

## Gotchas

1. **Nil interface vs nil concrete type** — a classic Go trap:
```go
var p *Person = nil
var i interface{} = p
fmt.Println(i == nil)  // false! ← the interface has a type (*Person), even though the value is nil
```

2. **Pointer receiver and interface satisfaction** — if a method uses a pointer receiver, only `*T` satisfies the interface, not `T`:
```go
type Greeter interface { Greet() string }
type Dog struct{}
func (d *Dog) Greet() string { return "woof" }

var g Greeter = &Dog{}  // ✅
var g2 Greeter = Dog{}  // ❌ compile error
```

---

## Practice

1. Define a `Speaker` interface with `Speak() string`. Implement it for `Dog` and `Cat`.
2. Write `func printAll(items []Shape)` that prints area/perimeter of each.
3. Implement `fmt.Stringer` on your `Rectangle` type.
4. Write a type switch that handles `int`, `string`, and `[]int`.

---

## Key Takeaways

- Interfaces are implemented implicitly — no `implements` keyword.
- Prefer small, focused interfaces (`io.Reader` is 1 method).
- Pointer receiver → only `*T` satisfies; value receiver → both `T` and `*T` satisfy.
- The nil interface gotcha: an interface with a typed-but-nil value is NOT nil.
