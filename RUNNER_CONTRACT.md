# Runner Contract

Judges invoke one documented command with an input directory and output directory.

```text
your-command --input <input-directory> --output <output-directory>
```

The input directory is structurally identical to the released `data/` directory. It may contain room IDs and catalog values not present in this public pack.

For every `rooms/<room_id>.json`, write:

```text
<output-directory>/<room_id>/layout.json
<output-directory>/<room_id>/quote.json
```

Requirements:

- Exit code `0` means every output was written and validated.
- A genuinely unsatisfiable room is still a successful run: write `layout.json` with `status: unsatisfiable`, structured violations and customer-readable trade-offs; write a blocked quote if no valid priced layout exists.
- Never use timestamps, random IDs, unordered serialization, machine paths or network-dependent values in committed output.
- Serialize JSON as UTF-8, sorted keys, two-space indentation and a trailing newline.
- The same inputs and code must yield byte-identical output on two consecutive runs.
- No LLM, external model API or probabilistic call may execute inside the pricing path.
