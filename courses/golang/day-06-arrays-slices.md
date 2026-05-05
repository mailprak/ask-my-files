# Day 06 — Arrays & Slices

## Learning Objectives
- Understand arrays and their limitations
- Create, grow, and slice slices
- Understand the slice header: pointer, length, capacity
- Use `append`, `copy`, and `make` correctly

---

## Arrays

Arrays have a **fixed size** that is part of their type. `[3]int` and `[4]int` are different types.

```go
var a [3]int           // [0, 0, 0] — zero-initialized
b := [3]int{1, 2, 3}  // literal
c := [...]int{4, 5, 6} // compiler counts the elements

fmt.Println(len(b))    // 3
fmt.Println(b[0])      // 1

// Arrays are values — copying an array copies all elements
d := b
d[0] = 99
fmt.Println(b[0]) // still 1 — b is unaffected
```

**In practice:** Arrays are rarely used directly. Use slices.

---

## Slices

A slice is a **dynamic window into an array**. It has:
- A pointer to an underlying array
- A length (`len`)
- A capacity (`cap`)

```go
// Create from a literal
s := []int{1, 2, 3, 4, 5}

// Create with make(type, len, cap)
s2 := make([]int, 5)      // len=5, cap=5, all zeros
s3 := make([]int, 3, 10)  // len=3, cap=10

// nil slice (no underlying array)
var s4 []int
fmt.Println(s4 == nil)  // true
fmt.Println(len(s4))    // 0 — safe to use
```

---

## Slicing (Sub-slices)

```go
s := []int{10, 20, 30, 40, 50}

// s[low:high] — elements from index low to high-1
fmt.Println(s[1:3])   // [20, 30]
fmt.Println(s[:3])    // [10, 20, 30]  — low defaults to 0
fmt.Println(s[2:])    // [30, 40, 50]  — high defaults to len
fmt.Println(s[:])     // [10, 20, 30, 40, 50]

// Sub-slices SHARE the underlying array
a := s[1:3]
a[0] = 99
fmt.Println(s)  // [10, 99, 30, 40, 50] — s is modified!
```

---

## append

`append` adds elements to a slice. If there's not enough capacity, it allocates a new, larger array.

```go
s := []int{1, 2, 3}
s = append(s, 4)           // [1, 2, 3, 4]
s = append(s, 5, 6, 7)    // [1, 2, 3, 4, 5, 6, 7]

// Append another slice using ...
other := []int{8, 9}
s = append(s, other...)   // [1, 2, 3, 4, 5, 6, 7, 8, 9]
```

**Always reassign:** `s = append(s, ...)` — `append` may return a new slice.

---

## copy

`copy` copies elements between slices. It returns the number of elements copied (min of src and dst lengths).

```go
src := []int{1, 2, 3}
dst := make([]int, len(src))
n := copy(dst, src)
fmt.Println(dst, n)  // [1 2 3] 3

// copy prevents shared-array issues
dst[0] = 99
fmt.Println(src)  // [1 2 3] — unchanged
```

---

## Understanding len and cap

```go
s := make([]int, 3, 5)
fmt.Println(len(s), cap(s))  // 3 5

s = append(s, 10)
fmt.Println(len(s), cap(s))  // 4 5 — still using same array

s = append(s, 20)
fmt.Println(len(s), cap(s))  // 5 5

s = append(s, 30)
fmt.Println(len(s), cap(s))  // 6 10 — new array allocated, cap doubled
```

Go roughly doubles capacity on reallocation (the exact formula varies).

---

## Three-index Slicing (Limiting Capacity)

```go
s := []int{1, 2, 3, 4, 5}
// s[low:high:max] — cap of result = max - low
t := s[1:3:4]
fmt.Println(len(t), cap(t))  // 2 3
```

Useful for preventing appends to a sub-slice from affecting the original.

---

## 2D Slices

```go
// Create a 3x3 matrix
matrix := make([][]int, 3)
for i := range matrix {
    matrix[i] = make([]int, 3)
}
matrix[1][2] = 5
```

---

## Gotchas

1. **Modifying a sub-slice modifies the original** until `append` triggers reallocation.
2. **`append` may or may not allocate** — never assume the original array is unchanged after appending to a sub-slice.
3. **nil slice vs empty slice** — both have `len == 0`, but `json.Marshal` treats them differently:
   - `nil` slice → `null`
   - empty slice `[]int{}` → `[]`
4. **Passing a slice to a function** — the function gets a copy of the slice header (pointer + len + cap), but modifications to elements affect the original.

```go
// Gotcha: append to sub-slice can clobber original
s := []int{1, 2, 3, 4, 5}
t := s[:3]         // shares underlying array
t = append(t, 99) // overwrites s[3]!
fmt.Println(s)     // [1 2 3 99 5] ← s[3] clobbered
```

---

## Practice

1. Create a slice of 5 strings, append 3 more, then print len and cap.
2. Write a function that reverses a `[]int` in place.
3. Use `copy` to safely duplicate a slice without sharing the array.
4. Demonstrate that modifying a sub-slice affects the original, then fix it with `copy`.

---

## Key Takeaways

- Slices are views into arrays — sub-slices share memory until an `append` reallocates.
- Always `s = append(s, ...)` — reassign the result.
- Prefer `make([]T, len, cap)` to pre-allocate when size is known.
- `copy` to isolate — prevents the surprise of a sub-slice modification affecting the parent.
