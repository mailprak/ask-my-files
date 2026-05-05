# Day 09 — Pointers

## Learning Objectives
- Understand what a pointer is and when to use one
- Use `&` (address-of) and `*` (dereference) operators
- Pass pointers to functions for mutation
- Know when Go passes by value vs by reference

---

## What Is a Pointer?

A pointer holds the **memory address** of a value rather than the value itself.

```go
x := 42
p := &x      // p is a *int, holds the address of x

fmt.Println(x)   // 42    — the value
fmt.Println(p)   // 0xc000... — the address
fmt.Println(*p)  // 42    — dereference: value at the address

*p = 100         // modify x through the pointer
fmt.Println(x)   // 100
```

---

## Pointer Operators

| Operator | Name | Meaning |
|---|---|---|
| `&x` | address-of | get the address of x |
| `*p` | dereference | get the value at address p |

---

## `new` — Allocating a Zero-Value Pointer

```go
p := new(int)    // allocates an int, initializes to 0, returns *int
*p = 7
fmt.Println(*p)  // 7

// Equivalent manual approach
x := 0
p2 := &x
```

`new` is less common than `&` with a struct literal in practice.

---

## Passing Pointers to Functions

Go is always **pass by value**. When you pass a pointer, you're passing the address (a value), and the function can modify what that address points to.

```go
// Modifies the caller's variable
func increment(n *int) {
    *n++
}

x := 5
increment(&x)
fmt.Println(x)  // 6
```

Compare with passing by value:
```go
func incrementCopy(n int) {
    n++  // modifies a local copy — caller unchanged
}

x := 5
incrementCopy(x)
fmt.Println(x)  // still 5
```

---

## When to Use Pointers

1. **Mutation** — you need the function to modify the caller's value
2. **Large structs** — avoid expensive copies by passing `*BigStruct`
3. **Optional values** — a `*string` can be `nil` (absent), while `string` always has a value
4. **Polymorphism** — pointer receivers on interfaces (covered in Day 10)

---

## nil Pointers

```go
var p *int   // nil pointer — doesn't point to anything
fmt.Println(p)   // <nil>

*p = 5  // ❌ panic: nil pointer dereference
```

Always check before dereferencing:
```go
if p != nil {
    fmt.Println(*p)
}
```

---

## Pointer to Struct

```go
type Point struct{ X, Y int }

p := &Point{X: 1, Y: 2}
p.X = 10  // Go auto-dereferences: same as (*p).X = 10
fmt.Println(*p)  // {10 2}
```

---

## Returning Pointers from Functions

It's perfectly safe to return a pointer to a local variable in Go. The Go compiler uses **escape analysis** to allocate it on the heap when necessary:

```go
func newPerson(name string) *Person {
    p := Person{Name: name}  // allocated on heap if returned
    return &p                // ✅ safe in Go
}
```

This would be a dangling pointer in C, but not in Go.

---

## Pointer to Interface (Usually Wrong)

```go
// ❌ Almost never correct
var w *io.Writer

// ✅ The interface value itself already holds a pointer internally
var w io.Writer
```

Pointer to interface is almost always a mistake. An interface value already contains a type and a value (or pointer).

---

## Double Pointers (`**T`)

Rare, but used when you need to modify the pointer itself:

```go
func setToFive(p **int) {
    x := 5
    *p = &x
}

var p *int
setToFive(&p)
fmt.Println(*p)  // 5
```

---

## Gotchas

1. **Nil pointer dereference** is a runtime panic — check for nil before dereferencing.
2. **Pointer to a loop variable** captures the address, not the value. By the time you use it, the loop variable has moved on.
3. **Don't over-use pointers** — small types (int, bool, small structs) are cheaper to copy than to indirect.
4. **String and slice are already "reference-like"** — passing them by value is usually fine since they contain a pointer internally.

```go
// Gotcha: pointer to loop variable
ptrs := make([]*int, 3)
for i := 0; i < 3; i++ {
    ptrs[i] = &i  // all point to the same 'i'
}
fmt.Println(*ptrs[0])  // 3 (loop ended at 3)

// Fix: capture by value
for i := 0; i < 3; i++ {
    v := i
    ptrs[i] = &v  // each points to its own copy
}
```

---

## Practice

1. Write a `swap(a, b *int)` function that swaps two integers.
2. Write a function that takes a `*[]int` and appends a value (modify the slice header).
3. Create a `*Person` and modify its fields through the pointer.
4. Demonstrate nil pointer panic and fix it with a nil check.

---

## Key Takeaways

- `&x` gets the address, `*p` dereferences. These are inverses.
- Go is pass-by-value — pass a pointer when the function needs to mutate.
- Returning `&localVar` is safe — Go heap-allocates when needed.
- Never dereference a nil pointer — always check.
