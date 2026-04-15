# Rust workspace example

Minimal Rust workspace fixture with one member crate.

## Try it

```bash
cp -r examples/stacks/rust /tmp/rust-demo
cd /tmp/rust-demo
git init -q
cargo build    # populates target/ — the noise Context OS hides
bash /path/to/context-os/setup.sh --measure
bash /path/to/context-os/setup.sh
```

## What happens

1. Stack detection sees `Cargo.toml` → stack is `rust`.
2. `.claudeignore` blocks `target/debug/`, `target/release/`, `.cargo/`, `Cargo.lock` — Rust targets are massive noise sources (thousands of `.rlib`, `.o`, `.d` artifacts per clean build).
3. Hook compression catches `cargo test`, `cargo check`, `cargo build`, `cargo clippy` output — typical savings 27-70%.
4. Explorer subagent on Haiku avoids burning Opus tokens on `rg`-style symbol lookups.
