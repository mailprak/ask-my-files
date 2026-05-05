# Day 16 — Channels

## Learning Objectives
- Create and use buffered and unbuffered channels
- Send and receive values between goroutines
- Close channels and range over them
- Use channels for synchronization and data pipelines

---

## What Is a Channel?

A channel is a typed conduit for communication between goroutines. It handles both **data passing** and **synchronization** in one construct.

```go
ch := make(chan int)       // unbuffered channel of int
bch := make(chan string, 5) // buffered channel of string, capacity 5
```

---

## Send and Receive

```go
ch <- 42      // send 42 to channel ch (blocks until someone receives)
v := <-ch    // receive from ch (blocks until someone sends)
```

Send and receive block until the other side is ready — this is how goroutines synchronize.

---

## Simple Producer/Consumer

```go
func main() {
    ch := make(chan int)

    // Producer goroutine
    go func() {
        for i := 0; i < 5; i++ {
            ch <- i       // send each value
        }
        close(ch)         // signal: no more values
    }()

    // Consumer (main goroutine)
    for v := range ch {   // receives until ch is closed
        fmt.Println(v)
    }
}
// Output: 0 1 2 3 4
```

---

## Closing a Channel

```go
close(ch)
```

Rules:
- Only the **sender** should close a channel (never the receiver).
- Sending to a closed channel panics.
- Receiving from a closed, empty channel returns the zero value.
- Use the comma-ok idiom to detect a closed channel:

```go
v, ok := <-ch
if !ok {
    fmt.Println("channel closed")
}
```

---

## Buffered Channels

A buffered channel has a queue of capacity N. Send doesn't block until the buffer is full.

```go
ch := make(chan int, 3)
ch <- 1  // doesn't block
ch <- 2  // doesn't block
ch <- 3  // doesn't block
ch <- 4  // BLOCKS — buffer is full

fmt.Println(<-ch)  // 1 (FIFO)
fmt.Println(<-ch)  // 2
```

---

## Directional Channels

Functions can specify channel direction to restrict usage:

```go
func producer(ch chan<- int) {  // send-only
    for i := 0; i < 5; i++ {
        ch <- i
    }
    close(ch)
}

func consumer(ch <-chan int) {  // receive-only
    for v := range ch {
        fmt.Println(v)
    }
}

func main() {
    ch := make(chan int)
    go producer(ch)
    consumer(ch)
}
```

Directional channels document intent and catch bugs at compile time.

---

## Channels as Semaphores

A buffered channel of `struct{}` acts as a semaphore to limit concurrency:

```go
sem := make(chan struct{}, 3)  // at most 3 concurrent operations

for _, url := range urls {
    sem <- struct{}{}  // acquire
    go func(u string) {
        defer func() { <-sem }()  // release
        fetch(u)
    }(url)
}
```

---

## Done Channel Pattern (Signal Completion)

A channel of size 0 carrying `struct{}` is a pure signal:

```go
done := make(chan struct{})

go func() {
    doWork()
    close(done)  // signal completion
}()

<-done  // wait for completion
```

---

## Pipeline Pattern

Chain goroutines where the output channel of one is the input of the next:

```go
func generate(nums ...int) <-chan int {
    out := make(chan int)
    go func() {
        for _, n := range nums {
            out <- n
        }
        close(out)
    }()
    return out
}

func square(in <-chan int) <-chan int {
    out := make(chan int)
    go func() {
        for n := range in {
            out <- n * n
        }
        close(out)
    }()
    return out
}

func main() {
    nums := generate(2, 3, 4)
    squares := square(nums)
    for v := range squares {
        fmt.Println(v)  // 4, 9, 16
    }
}
```

---

## Fan-out / Fan-in

**Fan-out:** distribute work across multiple goroutines from one channel.
**Fan-in:** merge multiple channels into one.

```go
func fanIn(cs ...<-chan int) <-chan int {
    var wg sync.WaitGroup
    out := make(chan int)

    output := func(c <-chan int) {
        for v := range c {
            out <- v
        }
        wg.Done()
    }

    wg.Add(len(cs))
    for _, c := range cs {
        go output(c)
    }

    go func() {
        wg.Wait()
        close(out)
    }()
    return out
}
```

---

## Gotchas

1. **Deadlock** — if all goroutines are blocked, Go detects it at runtime:
```
fatal error: all goroutines are asleep - deadlock!
```
2. **Sending to a closed channel panics** — only the sender closes; close once.
3. **Goroutine leak from abandoned channel** — a goroutine blocked on a channel no one reads from leaks forever.
4. **Unbuffered vs buffered confusion** — an unbuffered channel requires a goroutine on both ends simultaneously.

---

## Practice

1. Write a producer/consumer pipeline: producer sends integers 1-10, consumer prints them.
2. Use a buffered channel of capacity 5 as a task queue.
3. Implement a `merge(a, b <-chan int) <-chan int` fan-in function.
4. Use a done channel to cancel a long-running goroutine.

---

## Key Takeaways

- Channels combine communication and synchronization — they're Go's preferred coordination tool.
- Close channels from the sender side; detect closure with `v, ok := <-ch`.
- Use directional channels (`chan<-`, `<-chan`) to document and enforce intent.
- Deadlock = all goroutines blocked — the runtime detects it immediately.
