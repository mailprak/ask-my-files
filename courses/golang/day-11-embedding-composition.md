# Day 11 — Embedding & Composition

## Learning Objectives
- Use struct embedding to compose behaviour
- Understand promoted fields and methods
- Distinguish embedding from inheritance
- Embed interfaces in structs and in other interfaces

---

## Why Composition Over Inheritance

Go has no class hierarchy. Instead, you build types by composing smaller pieces. This avoids the fragile base-class problem and leads to clearer code.

---

## Struct Embedding

When you embed a type (no field name), its fields and methods are **promoted** to the outer struct:

```go
type Animal struct {
    Name string
}

func (a Animal) Breathe() string {
    return a.Name + " breathes"
}

type Dog struct {
    Animal       // embedded — promoted
    Breed string
}

d := Dog{
    Animal: Animal{Name: "Rex"},
    Breed:  "Labrador",
}

fmt.Println(d.Name)      // Rex    — promoted field
fmt.Println(d.Breathe()) // Rex breathes — promoted method
fmt.Println(d.Breed)     // Labrador
```

---

## Overriding Promoted Methods

The outer struct can define a method with the same name — it takes priority:

```go
func (d Dog) Breathe() string {
    return d.Name + " pants"  // Dog's own version
}

fmt.Println(d.Breathe())        // Rex pants (Dog's version)
fmt.Println(d.Animal.Breathe()) // Rex breathes (explicitly call Animal's version)
```

---

## Multiple Embeddings

```go
type Logger struct{}

func (l Logger) Log(msg string) {
    fmt.Println("[LOG]", msg)
}

type Metrics struct{}

func (m Metrics) Record(event string) {
    fmt.Println("[METRIC]", event)
}

type Service struct {
    Logger
    Metrics
    Name string
}

svc := Service{Name: "auth"}
svc.Log("started")     // promoted from Logger
svc.Record("request")  // promoted from Metrics
```

---

## Embedding vs Named Field

```go
// Embedding — fields/methods are promoted
type A struct {
    Base
}

// Named field — no promotion, must access explicitly
type B struct {
    base Base
}

a := A{}
a.Field   // promoted
a.Method()

b := B{}
b.base.Field   // must qualify
b.base.Method()
```

Choose named fields when you want the relationship to be explicit and non-promoted.

---

## Embedding Interfaces in Structs

You can embed an interface in a struct. This is used to create **wrapper types** or **mocks**:

```go
type ReadWriter interface {
    io.Reader
    io.Writer
}

// Partial implementation with embedding — useful in tests
type MockWriter struct {
    io.Reader  // embed to satisfy the interface partially
    // implement Writer yourself
}
```

A more practical pattern — wrapping a concrete type to override one method:

```go
type LoggingWriter struct {
    io.Writer  // promotes all Writer methods
}

func (lw LoggingWriter) Write(p []byte) (int, error) {
    fmt.Printf("Writing %d bytes\n", len(p))
    return lw.Writer.Write(p)  // delegate to the real writer
}
```

---

## Embedding Interfaces in Interfaces

This is the standard way to compose interfaces:

```go
type Reader interface {
    Read(p []byte) (n int, err error)
}

type Writer interface {
    Write(p []byte) (n int, err error)
}

type ReadWriter interface {
    Reader   // embed Reader
    Writer   // embed Writer
}
```

Any type satisfying `ReadWriter` automatically satisfies `Reader` and `Writer` too.

---

## The "Mixin" Pattern

Give shared behaviour to multiple types without a base class:

```go
type Timestamps struct {
    CreatedAt time.Time
    UpdatedAt time.Time
}

func (t *Timestamps) Touch() {
    t.UpdatedAt = time.Now()
}

type User struct {
    Timestamps
    Name string
}

type Post struct {
    Timestamps
    Title string
}

u := User{Name: "Alice"}
u.Touch()  // from Timestamps
```

---

## When Embedding Causes Ambiguity

If two embedded types have the same method name and neither is closer, it's a compile error:

```go
type A struct{}
func (A) Hello() {}

type B struct{}
func (B) Hello() {}

type C struct {
    A
    B
}

c := C{}
c.Hello()    // ❌ ambiguous selector c.Hello
c.A.Hello()  // ✅ disambiguate explicitly
```

---

## Gotchas

1. **Embedding is not subtyping** — a `Dog` is not an `Animal` in the type system; it just has Animal's methods promoted.
2. **Interface satisfaction via embedding** — if `Animal` satisfies an interface and `Dog` embeds `Animal`, then `Dog` also satisfies that interface (via promotion).
3. **Nil embedded pointer** — if the embedded type is a pointer and it's nil, calling its promoted methods panics.

```go
type Logger struct {
    *log.Logger  // pointer embedding
}

l := Logger{}   // Logger.Logger is nil
l.Println("hi") // ❌ panic — nil pointer
```

---

## Practice

1. Create `Engine` with a `Start()` method. Embed it in `Car` and `Boat`. Verify `Start()` is promoted to both.
2. Override `Start()` in `Car` and show that `Car.Engine.Start()` still reaches the original.
3. Create a `Timestamped` struct with `CreatedAt`/`UpdatedAt` and embed it in two domain types.
4. Compose `io.Reader` + `io.Writer` into a custom `io.ReadWriter` interface.

---

## Key Takeaways

- Embedding promotes fields and methods — it's composition, not inheritance.
- The outer type can override any promoted method; use `Type.Method()` to reach the embedded version.
- Interface embedding composes interfaces — the standard library relies on this heavily (`io.ReadWriter`, `io.ReadWriteCloser`).
- Ambiguity (two embeddings with the same method name) is a compile error — resolve it by being explicit.
