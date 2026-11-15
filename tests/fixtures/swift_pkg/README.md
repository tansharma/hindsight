# swift_pkg fixture

Two SwiftPM packages for `import_graph.py`'s Swift tests (never built).
Planted on purpose: one target cycle across the packages
(`PkgA/Sources/Core` imports `Storage`, `PkgB/Sources/Storage` imports
`Core`), and `Core` as a volatile hub (three importers plus a TODO
comment). `Networking` uses a custom `path:`; commented-out imports must
not become edges.
