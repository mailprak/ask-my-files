# Day 22 — JSON Encoding & Decoding

## Learning Objectives
- Marshal and unmarshal JSON with `encoding/json`
- Use struct tags to control JSON field names
- Handle unknown or dynamic JSON with `map[string]any`
- Stream large JSON with `json.Encoder`/`json.Decoder`

---

## Basic Marshalling (Go → JSON)

```go
import "encoding/json"

type User struct {
    ID    int    `json:"id"`
    Name  string `json:"name"`
    Email string `json:"email"`
}

u := User{ID: 1, Name: "Alice", Email: "alice@example.com"}
data, err := json.Marshal(u)
if err != nil {
    return err
}
fmt.Println(string(data))
// {"id":1,"name":"Alice","email":"alice@example.com"}
```

---

## Basic Unmarshalling (JSON → Go)

```go
jsonData := `{"id":1,"name":"Alice","email":"alice@example.com"}`

var u User
if err := json.Unmarshal([]byte(jsonData), &u); err != nil {
    return err
}
fmt.Println(u.Name)  // Alice
```

---

## Struct Tags

```go
type Product struct {
    ID          int     `json:"id"`
    Name        string  `json:"name"`
    Price       float64 `json:"price"`
    Description string  `json:"description,omitempty"` // omit if empty
    Internal    string  `json:"-"`                     // never include in JSON
    CreatedAt   time.Time `json:"created_at"`
}
```

Tag options:
- `json:"name"` — use "name" as the JSON key
- `json:"name,omitempty"` — omit if zero value
- `json:"-"` — always exclude this field
- `json:",string"` — marshal number as JSON string

---

## Pretty-Printing

```go
data, err := json.MarshalIndent(u, "", "  ")
fmt.Println(string(data))
// {
//   "id": 1,
//   "name": "Alice",
//   "email": "alice@example.com"
// }
```

---

## Unknown / Dynamic JSON with map

When the JSON structure is unknown at compile time:

```go
var result map[string]any
if err := json.Unmarshal(data, &result); err != nil {
    return err
}

// Access fields with type assertions
name, ok := result["name"].(string)
id, ok := result["id"].(float64)  // JSON numbers are float64 by default
```

---

## json.Number — Avoid float64 for Large Numbers

```go
d := json.NewDecoder(strings.NewReader(jsonStr))
d.UseNumber()  // numbers become json.Number instead of float64

var m map[string]any
d.Decode(&m)

n := m["id"].(json.Number)
id, _ := n.Int64()  // exact integer
```

---

## Streaming with Encoder/Decoder

For HTTP handlers and large files — avoids buffering the whole payload:

```go
// Writing to an http.ResponseWriter
func handler(w http.ResponseWriter, r *http.Request) {
    w.Header().Set("Content-Type", "application/json")
    users := getUsers()
    if err := json.NewEncoder(w).Encode(users); err != nil {
        log.Println("encode error:", err)
    }
}

// Reading from an http.Request
func createHandler(w http.ResponseWriter, r *http.Request) {
    var u User
    if err := json.NewDecoder(r.Body).Decode(&u); err != nil {
        http.Error(w, "invalid JSON", http.StatusBadRequest)
        return
    }
    // use u
}
```

---

## Handling Null Values

```go
type Config struct {
    Timeout *int `json:"timeout"` // pointer — can distinguish null from 0
}

// null in JSON → nil pointer in Go
// 30 in JSON → pointer to 30
```

---

## Custom Marshalling

Implement `json.Marshaler` / `json.Unmarshaler` for custom encoding:

```go
type Duration time.Duration

func (d Duration) MarshalJSON() ([]byte, error) {
    return json.Marshal(time.Duration(d).String())  // e.g., "5s"
}

func (d *Duration) UnmarshalJSON(b []byte) error {
    var s string
    if err := json.Unmarshal(b, &s); err != nil {
        return err
    }
    dur, err := time.ParseDuration(s)
    if err != nil {
        return err
    }
    *d = Duration(dur)
    return nil
}
```

---

## Decoding an Array of Objects

```go
jsonArray := `[{"name":"Alice"},{"name":"Bob"}]`

var users []User
json.Unmarshal([]byte(jsonArray), &users)
for _, u := range users {
    fmt.Println(u.Name)
}
```

---

## Gotchas

1. **JSON numbers are `float64`** when decoded into `any` — use `json.Number` or typed structs to avoid precision loss.
2. **Unexported fields are ignored** — `json.Marshal` and `json.Unmarshal` skip fields without a capital letter.
3. **Nil slice vs empty slice** — `nil` slice marshals to `null`; `[]T{}` marshals to `[]`. Use `omitempty` or initialize the slice.
4. **Unmarshal into a pointer** — always pass a pointer to `Unmarshal`: `json.Unmarshal(data, &u)` not `json.Unmarshal(data, u)`.

---

## Practice

1. Marshal a struct with `omitempty` tags and verify empty fields are excluded.
2. Decode a JSON API response into a struct with nested structs.
3. Write an HTTP handler that reads a JSON body and writes a JSON response.
4. Implement custom `MarshalJSON`/`UnmarshalJSON` for a time.Time field that uses Unix timestamps.

---

## Key Takeaways

- Use struct tags (`json:"name,omitempty"`) to control JSON serialization.
- Use `json.NewEncoder`/`json.NewDecoder` for streaming (HTTP handlers, files).
- JSON numbers decode to `float64` when using `map[string]any` — use typed structs or `json.Number`.
- `json.Unmarshal` needs a pointer — `&value`, not `value`.
