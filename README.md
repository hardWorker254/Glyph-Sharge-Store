# Glyph Sharge Store

The community catalogue for [Glyph Sharge](https://github.com/hardWorker254/Glyph-Sharge-fork): animations (`.glyphlua`) and service rules (`.servicelua`) that the app can browse, verify and install.

## Layout

```
animations/   .glyphlua — scripts that draw on the Glyph strip
services/     .servicelua — rules that decide WHEN an animation fires
index.json    generated catalogue the app fetches (do not hand-edit)
build_index.py
```

## Adding a script

1. Put the file in `animations/` or `services/` with the right suffix.
2. Give it a complete header. The indexer refuses an entry that is missing an `id`, an `author` or a `license`, or whose `id` is not `[a-zA-Z0-9_-]{1,64}`.
3. Rebuild the index and commit **both** the script and `index.json`:

```sh
python3 build_index.py
```

CI-style check (fails if the index is out of date):

```sh
python3 build_index.py --check
```

## Header format

Animations (`-- Glyph Sharge animation`):

```lua
-- Glyph Sharge animation
-- format: 1
-- name: My Animation
-- id: my-animation
-- author: Your Name
-- license: MIT
-- description: What it does, in one line
-- devices: PHONE1,PHONE2,PHONE2A,PHONE3A
-- created: 1773072000000
-- updated: 1773072000000
-- version: 1
```

Service rules (`-- Glyph Sharge service rule`) use the same fields. A service says *when* to fire (it subscribes to triggers and calls `glyph.playAnimation()`); it cannot draw on the strip.

```lua
-- Glyph Sharge service rule
-- format: 1
-- name: Night Quiet
-- id: night-quiet
-- author: Your Name
-- license: MIT
-- description: Plays the rule's animation on screen off, but stays dark at night
-- devices: PHONE1,PHONE2,PHONE2A,PHONE3A
-- created: 1773072000000
-- updated: 1773072000000
-- version: 1

glyph.on("screen_off", function()
  if glyph.isNight then return end
  glyph.playAnimation()
end)
```

`devices` names the models the script claims to work on. An empty or unknown list means "every model".

## How the index works

`build_index.py` reads every header, computes a SHA-256 over the **raw bytes** of each file, and writes `index.json`. The app verifies the hash before it saves anything, so the catalogue cannot install a file it did not describe. That is why the index is generated and never hand-edited.

## License

The catalogue tooling and the example scripts in this repository are released under the MIT License (see `LICENSE`). Each script carries its own `-- license:` line — that line is the license of that script.
