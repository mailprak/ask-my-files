# Day 08 — Structs & Methods

## Learning Objectives
- Define and initialize structs
- Attach methods to types
- Understand value receivers vs pointer receivers
- Use struct embedding for composition

---

## Defining Structs

```go
type Person struct {
    Name string
    Age  int
    Email string
}
```

---

## Creating Struct Values

```go
// Named fields (preferred — order-independent)
p1 := Person{Name: "Alice", Age: 30, Email: "alice@example.com"}

// Positional (fragile — don't use for exported structs)
p2 := Person{"Bob", 25, "bob@example.com"}

// Zero-value struct
var p3 Person  // {Name:"", Age:0, Email:""}

// Pointer to struct
p4 := &Person{Name: "Carol", Age: 28}
```

---

## Accessing Fields

```go
fmt.Println(p1.Name)  // Alice
p1.Age = 31           // modify directly

// Through a pointer — same syntax (Go auto-dereferences)
fmt.Println(p4.Name)  // Carol (not (*p4).Name — though that works too)
p4.Age = 29
```

---

## Methods

A method is a function with a **receiver** — it's attached to a type.

```go
// Value receiver — works on a copy
func (p Person) Greet() string {
    return fmt.Sprintf("Hi, I'm %s", p.Name)
}

// Pointer receiver — works on the original
func (p *Person) Birthday() {
    p.Age++
}

// Usage
p := Person{Name: "Alice", Age: 30}
fmt.Println(p.Greet())  // Hi, I'm Alice
p.Birthday()
fmt.Println(p.Age)      // 31
```

---

## Value Receiver vs Pointer Receiver

| Use value receiver when... | Use pointer receiver when... |
|---|---|
| Method doesn't modify the struct | Method needs to modify the struct |
| Struct is small (cheap to copy) | Struct is large (copying is expensive) |
| Consistency doesn't require pointer | Most other methods use pointer receivers |

**Rule of thumb:** If ANY method on a type uses a pointer receiver, ALL methods should use pointer receivers (for consistency).

```go
type Counter struct {
    count int
}

func (c *Counter) Increment() { c.count++ }  // modifies — needs pointer
func (c *Counter) Value() int { return c.count }  // could be value, but use pointer for consistency
```

---

## Methods on Non-Struct Types

You can add methods to any type defined in the same package:

```go
type Celsius float64
type Fahrenheit float64

func (c Celsius) ToFahrenheit() Fahrenheit {
    return Fahrenheit(c*9/5 + 32)
}

temp := Celsius(100)
fmt.Println(temp.ToFahrenheit())  // 212
```

---

## Anonymous Structs

Useful for one-off data shapes or test fixtures:

```go
point := struct {
    X, Y int
}{X: 3, Y: 4}

// Slice of anonymous structs — common in tests
cases := []struct {
    input    int
    expected int
}{
    {2, 4},
    {3, 9},
}
```

---

## Struct Tags

Tags add metadata to fields, used by encoding/JSON, ORMs, validators, etc.:

```go
type User struct {
    ID       int    `json:"id"`
    Name     string `json:"name"`
    Password string `json:"-"`           // omit from JSON
    Email    string `json:"email,omitempty"`  // omit if empty
}
```

---

## Struct Embedding (Composition)

Go favors composition over inheritance. Embedding one struct inside another promotes its fields and methods:

```go
type Animal struct {
    Name string
}

func (a Animal) Speak() string {
    return a.Name + " makes a sound"
}

type Dog struct {
    Animal        // embedded — no field name
    Breed string
}

func (d Dog) Speak() string {  // override the promoted method
    return d.Name + " says Woof!"
}

d := Dog{Animal: Animal{Name: "Rex"}, Breed: "Labrador"}
fmt.Println(d.Name)    // Rex  — promoted field
fmt.Println(d.Speak()) // Rex says Woof!
```

---

## Comparing Structs

Structs are comparable if all their fields are comparable (no maps, slices, or functions):

```go
type Point struct{ X, Y int }

p1 := Point{1, 2}
p2 := Point{1, 2}
fmt.Println(p1 == p2)  // true
```

---

## Gotchas

1. **Modifying a struct via a value receiver doesn't affect the original** — a very common bug.
2. **`nil` pointer receiver** — calling a method on a nil pointer is valid IF the method handles nil:
```go
func (p *Person) Name() string {
    if p == nil { return "" }
    return p.Name
}
```
3. **Struct is a value type** — when you pass a struct to a function, it's copied. Pass a pointer to avoid copying large structs.

---

## Practice

1. Define a `Rectangle` struct with `Width` and `Height`. Add `Area()` and `Perimeter()` methods.
2. Define a `BankAccount` struct with a private `balance`. Add `Deposit`, `Withdraw`, and `Balance` methods using pointer receivers.
3. Embed `Address` inside `Person` and access the promoted `City` field.

---

## Key Takeaways

- Use pointer receivers when a method modifies the struct or the struct is large.
- If one method uses a pointer receiver, make all of them use pointer receivers.
- Embedding is Go's composition — it promotes fields and methods, but is not inheritance.
- Struct tags drive encoding/decoding — use `json:` tags on any struct that goes to/from JSON.
