# Day 28 — Reflection

## Learning Objectives
- Use `reflect.TypeOf` and `reflect.ValueOf`
- Inspect and set struct fields at runtime
- Understand when reflection is appropriate
- Know the performance and safety trade-offs

---

## What Is Reflection?

Reflection lets you inspect and manipulate values at **runtime** when you don't know the types at **compile time**. It's used internally by `encoding/json`, `fmt`, ORMs, and test assertion libraries.

---

## reflect.TypeOf and reflect.ValueOf

```go
import "reflect"

x := 42
fmt.Println(reflect.TypeOf(x))   // int
fmt.Println(reflect.ValueOf(x))  // 42

s := "hello"
fmt.Println(reflect.TypeOf(s))   // string

type Point struct{ X, Y int }
p := Point{1, 2}
fmt.Println(reflect.TypeOf(p))   // main.Point
fmt.Println(reflect.TypeOf(p).Kind())  // struct
```

---

## Kind vs Type

`Type` is the specific type (`main.Point`).
`Kind` is the category (`struct`, `ptr`, `slice`, `map`, `int`, etc.).

```go
type MyInt int
var n MyInt = 5

fmt.Println(reflect.TypeOf(n))        // main.MyInt
fmt.Println(reflect.TypeOf(n).Kind()) // int
```

---

## Inspecting Struct Fields

```go
type User struct {
    Name  string `json:"name"`
    Age   int    `json:"age"`
    Email string `json:"email,omitempty"`
}

u := User{Name: "Alice", Age: 30}

t := reflect.TypeOf(u)
v := reflect.ValueOf(u)

for i := 0; i < t.NumField(); i++ {
    field := t.Field(i)
    value := v.Field(i)
    tag := field.Tag.Get("json")
    fmt.Printf("Name: %s, Value: %v, Tag: %s\n", field.Name, value, tag)
}
// Name: Name,  Value: Alice, Tag: name
// Name: Age,   Value: 30,    Tag: age
// Name: Email, Value: ,      Tag: email,omitempty
```

---

## Setting Values via Reflection

To set a value, you need an **addressable** (pointer) value:

```go
p := &User{Name: "Alice"}
v := reflect.ValueOf(p).Elem()  // dereference the pointer

nameField := v.FieldByName("Name")
if nameField.CanSet() {
    nameField.SetString("Bob")
}

fmt.Println(p.Name)  // Bob
```

---

## Calling Methods via Reflection

```go
type Greeter struct{ Name string }

func (g Greeter) Greet(msg string) string {
    return fmt.Sprintf("%s, %s!", msg, g.Name)
}

g := Greeter{Name: "Alice"}
v := reflect.ValueOf(g)
method := v.MethodByName("Greet")

result := method.Call([]reflect.Value{
    reflect.ValueOf("Hello"),
})
fmt.Println(result[0].String())  // Hello, Alice!
```

---

## Type Switching vs Reflection

For a **known, finite set of types** — use a type switch (faster, clearer):

```go
func describe(v any) {
    switch val := v.(type) {
    case int:
        fmt.Println("int:", val)
    case string:
        fmt.Println("string:", val)
    default:
        // use reflect for everything else
        fmt.Printf("unknown: %T\n", v)
    }
}
```

Use reflection when you need to handle **arbitrary, unknown** types.

---

## Building a Simple Struct-to-Map Converter

```go
func structToMap(v any) map[string]any {
    result := make(map[string]any)

    rv := reflect.ValueOf(v)
    if rv.Kind() == reflect.Ptr {
        rv = rv.Elem()
    }
    if rv.Kind() != reflect.Struct {
        return result
    }

    rt := rv.Type()
    for i := 0; i < rt.NumField(); i++ {
        field := rt.Field(i)
        if !field.IsExported() {
            continue
        }
        result[field.Name] = rv.Field(i).Interface()
    }
    return result
}
```

---

## DeepEqual

`reflect.DeepEqual` compares two values recursively — useful in tests:

```go
a := []int{1, 2, 3}
b := []int{1, 2, 3}

fmt.Println(a == b)                   // ❌ compile error — slices aren't comparable
fmt.Println(reflect.DeepEqual(a, b))  // true
```

In tests, prefer `assert.Equal` from testify — it gives better error messages.

---

## Performance

Reflection is **10-100x slower** than direct code. Avoid in hot paths.

```go
// ❌ Reflection in a hot loop
for _, item := range millionItems {
    v := reflect.ValueOf(item).FieldByName("ID")  // slow
}

// ✅ Direct field access
for _, item := range millionItems {
    _ = item.ID  // fast
}
```

One pattern: use reflection once at startup to build a lookup table, then use the table at runtime.

---

## Gotchas

1. **Panics are common** — `ValueOf(nil).Field(0)` panics; `FieldByName` on a non-struct panics. Always check Kind first.
2. **CanSet check** — setting an unexported field or a non-addressable value panics. Check `CanSet()` before setting.
3. **Interface extraction** — `v.Interface()` panics on unexported fields. Check `field.IsExported()`.
4. **Reflection bypasses type safety** — use sparingly and only where the generic/interface approach doesn't fit.

---

## When to Use Reflection

✅ **Appropriate uses:**
- Serialization/deserialization (JSON, YAML, XML)
- ORM field mapping
- Dependency injection containers
- Test assertion libraries
- Generic template/code generation tools

❌ **Avoid reflection:**
- Performance-critical code
- When generics or interfaces solve the problem
- Anything you call in a tight loop

---

## Practice

1. Write a function `PrintFields(v any)` that prints all exported fields of any struct.
2. Write a `Set(v any, fieldName string, value any)` function using reflection.
3. Implement a simple struct validator that checks `required` struct tags.
4. Benchmark direct field access vs reflection field access.

---

## Key Takeaways

- `reflect.TypeOf` gives the type; `reflect.ValueOf` gives the value; `.Kind()` gives the category.
- To set values via reflection, you need an addressable value (pointer) — check `CanSet()`.
- Reflection is 10-100x slower than direct access — avoid in hot paths.
- Use reflection for frameworks and infrastructure code; use generics/interfaces for application code.
