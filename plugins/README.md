# Plugins

Drop custom tracker plugins here as `.py` files; the bot loads them at startup
(sub-directories included). This directory is git-ignored except for this file,
and Docker mounts it read-only into the container.

Each file defines a `Tracker` class that subclasses `AbstractTracker` (or
`Track17BackedTracker` to fetch through 17track). See
[docs/plugins.md](../docs/plugins.md) for the contract and two complete examples.

```
plugins/
├── README.md        (the only committed file)
└── it/
    ├── brt.py
    └── sda.py
```
