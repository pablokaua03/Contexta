# Contexta 1.6 Dependency Proposal

This proposal reframes Contexta from "zero runtime dependencies" to "small, high-leverage dependencies that materially improve project understanding, token control, and pack quality".

The goal is not to add libraries for convenience. The goal is to add the smallest set of dependencies that makes Contexta better at:

- recognizing real stacks and frameworks
- understanding symbols and file responsibilities with less guesswork
- estimating token budgets more accurately
- reading real-world repositories more robustly
- producing better onboarding, review, and risk packs

## Recommended Direction

The best path for `1.6.x` is:

1. Add a small foundation layer of robust utilities.
2. Add syntax-aware parsing with Tree-sitter.
3. Use token-aware compression instead of character heuristics alone.
4. Keep packaging simple for Linux and move Windows toward an installer if distribution becomes more professional.

## Priority Order

### Tier 1: Add First

These give strong gains with relatively low product risk.

#### `pathspec`

Why:

- Replaces the current hand-rolled `.gitignore` matching logic with Git-style pattern handling.
- Improves scan correctness in real repositories.
- Reduces noise before the engine even starts scoring files.

Best use inside Contexta:

- `contexta_app/scanner.py`
- replace or wrap `matches_gitignore()`
- improve exclusions for monorepos, nested vendor folders, generated outputs, and edge-case negation rules

Expected gain:

- fewer wrong files in the tree
- better diffs
- smaller and cleaner packs

Why it is worth it:

- scanning correctness is upstream of every pack

Official source:

- [pathspec on PyPI](https://pypi.org/project/pathspec/)

#### `charset-normalizer`

Why:

- The current file reading logic tries a few encodings manually.
- Real projects often contain mixed encodings, especially older PHP, Java, XML, or Windows-heavy repos.
- Better decoding means fewer unreadable files and better excerpts.

Best use inside Contexta:

- `contexta_app/scanner.py`
- improve `read_file_safe()`

Expected gain:

- better support for legacy projects
- fewer false "binary/unreadable" omissions
- better domain extraction from real codebases

Official source:

- [charset-normalizer on GitHub](https://github.com/jawah/charset_normalizer)

#### `tiktoken`

Why:

- Contexta currently estimates tokens heuristically.
- Token-aware packs are one of the most valuable things Contexta can improve.
- More accurate token counting means better compression choices and safer payload sizing.

Best use inside Contexta:

- `contexta_app/renderer.py`
- replace or augment `estimate_tokens()`
- improve pack sizing, section trimming, excerpt clipping, and "roughly fits model" hints

Expected gain:

- much better token estimates
- more reliable pack sizing
- better compression behavior

Official source:

- [openai/tiktoken](https://github.com/openai/tiktoken)

### Tier 2: Highest Intelligence Upgrade

These are the dependencies that most strongly improve Contexta's actual understanding of code.

#### `tree-sitter`

Why:

- This is the biggest jump in intelligence per dependency.
- It lets Contexta move from regex-heavy heuristics toward structural parsing.
- It is especially valuable for:
  - symbol extraction
  - route/page detection
  - class/function boundaries
  - imports
  - controllers/services/providers/repositories
  - risk analysis by real code structure

Best use inside Contexta:

- new syntax-aware parsing layer, likely under `contexta_app/`
- consumed mainly by:
  - `contexta_app/context_engine.py`
  - `contexta_app/scanner.py`

Recommended initial language focus:

- Python
- JavaScript
- TypeScript
- TSX/JSX
- PHP
- Java
- C#
- Go
- Rust
- Ruby
- XML

Expected gain:

- better file roles
- better relationship map
- better core file selection
- better risk analysis
- better onboarding excerpts
- much less reliance on "string coincidence"

Official sources:

- [py-tree-sitter docs](https://tree-sitter.github.io/py-tree-sitter/)
- [tree-sitter Python bindings](https://github.com/tree-sitter/py-tree-sitter)

#### `tree-sitter-language-pack`

Why:

- Using raw `tree-sitter` alone is not enough; Contexta needs language grammars.
- A language pack simplifies multi-language adoption a lot.
- This is especially useful because Contexta must understand many ecosystems, not just Python or frontend stacks.

Best use inside Contexta:

- grammar provisioning for the parsing layer
- central language registry so the engine can ask for "python", "tsx", "php", "java", etc.

Caution:

- this adds packaging complexity and should be tested on Windows and Linux builds early

Official sources:

- [tree-sitter-language-pack on GitHub](https://github.com/Goldziher/tree-sitter-language-pack)
- [tree-sitter-language-pack on PyPI](https://pypi.org/project/tree-sitter-language-pack/)

### Tier 3: Precision Helpers

These are strong additions after the parser layer is in place.

#### `rapidfuzz`

Why:

- Contexta already tries to infer related files and "where to change what".
- Rapid fuzzy matching can help rank related files, route families, test proximity, module naming similarity, and likely change surfaces.

Best use inside Contexta:

- `contexta_app/context_engine.py`
- relationship scoring
- related test detection
- change recommendation buckets
- "adjacent to current working context" style ranking

Expected gain:

- better nearby-file selection
- better related test suggestions
- better "Where To Change What"

Official sources:

- [RapidFuzz on GitHub](https://github.com/rapidfuzz/RapidFuzz)
- [RapidFuzz docs](https://rapidfuzz.github.io/RapidFuzz/)

#### `lxml`

Why:

- XML matters a lot for Java, .NET, Android, Maven, MSBuild, Spring config, and some enterprise repos.
- The standard library XML support is serviceable, but `lxml` gives stronger XPath/query ergonomics and more robust parsing.

Best use inside Contexta:

- improve `pom.xml`, `.csproj`, Android XML, and config parsing
- only worth adding if XML-heavy projects remain a pain point after the current improvements

Caution:

- this is lower priority than Tree-sitter
- packaging/build complexity is higher than the Tier 1 libraries

Official source:

- [lxml](https://lxml.de/index.html)

## What I Would Not Add Yet

These are not bad libraries, but they do not look like first-wave wins for Contexta.

### `GitPython`

Why not yet:

- Contexta already gets useful value from plain `git` CLI calls.
- Replacing working subprocess logic with an abstraction layer is not the highest-value use of dependency budget.

### Heavy NLP / embeddings libraries

Examples:

- spaCy
- sentence-transformers
- torch-backed semantic stacks

Why not yet:

- big footprint
- bigger packaging burden
- more difficult Windows distribution
- not needed before structural parsing is improved

### Multiple XML/YAML helpers at once

Why not yet:

- Contexta should not accumulate parser sprawl before proving where the pain actually is

## Concrete 1.6 Plan

### Phase 1: Foundation Upgrade

Add:

- `pathspec`
- `charset-normalizer`
- `tiktoken`

Work:

- `scanner.py`: replace `.gitignore` matching and improve decoding
- `renderer.py`: use token-aware estimation
- `context_engine.py`: keep current heuristics, but benefit from cleaner inputs

Expected result:

- better scan quality
- better pack sizing
- no huge architecture rewrite yet

### Phase 2: Syntax-Aware Intelligence

Add:

- `tree-sitter`
- `tree-sitter-language-pack`

Work:

- create a parser adapter layer
- parse symbols/imports/routes per language
- use structural signals for:
  - roles
  - file relevance
  - domain detection
  - risk scoring
  - related files

Expected result:

- biggest jump in Contexta quality

### Phase 3: Ranking Refinement

Add:

- `rapidfuzz`

Work:

- improve fuzzy relationships between:
  - routes and related tests
  - services and repositories
  - modules with naming variants
  - selected files and likely impact surfaces

Expected result:

- smarter "Where To Change What"
- better test suggestions
- better onboarding and review focus

### Phase 4: Packaging and Distribution

Recommended direction:

- Windows:
  - prefer a professional installer if the dependency footprint grows
  - keep single-file experiments if they behave well, but do not let packaging constraints block product quality
- Linux:
  - keep `contexta-linux.tar.gz`

## Best First Set

If I had to choose the strongest first set for `1.6`, I would add exactly these in this order:

1. `pathspec`
2. `charset-normalizer`
3. `tiktoken`
4. `tree-sitter`
5. `tree-sitter-language-pack`
6. `rapidfuzz`

## Suggested Product Repositioning

Instead of saying Contexta is "zero dependency", it would be stronger to say:

- syntax-aware
- stack-aware
- token-aware
- better at multi-language repositories
- improved for real-world projects and AI handoff quality

That is a much more meaningful product story than "runs with only stdlib".

## Recommendation Summary

For Contexta `1.6`, the best technical investment is:

- foundation reliability first
- parsing intelligence second
- packaging convenience third

If only one big bet is made, it should be:

- Tree-sitter integration

If only one low-risk win is made first, it should be:

- `tiktoken` plus `pathspec`
