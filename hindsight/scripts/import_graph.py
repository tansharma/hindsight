#!/usr/bin/env python3
"""Deterministic dependency analysis behind the Dependency Health Scorecard
(SKILL.md Steps 2-3). Builds the internal import graph for Python and
JavaScript/TypeScript files and, for Swift, between build targets; finds
circular imports and volatile hub modules, and collects package facts that
are evidenced locally (manifests, lockfiles). It never touches the network
and never runs a language toolchain.

Usage:
    scripts/import_graph.py --root <path> --files-from <list.txt | ->
    scripts/import_graph.py --root <path> a.py src/b.ts ...

Paths are relative to --root (scripts/list_files.sh output works as-is).
Prints one JSON object to stdout:

    {
      "languages": {"python": 3, "javascript": 2},   # modules per language
      "unsupported_files": 4,          # listed files in other languages, or
                                       # Swift files outside every target
      "modules": [{"path", "language", "imports": [internal paths],
                   "fan_in", "markers", "churn"}],
      "deferred_imports": [{"path", "imports": [internal paths]}],
                                       # Python imports inside a function or
                                       # method body: real dependencies that
                                       # count toward fan_in, but not edges
                                       # for cycle detection
      "cycles": [["a.py", "b.py"]],    # each a set of mutually importing
                                       # modules (a strongly connected
                                       # component), sorted
      "volatile_hubs": [{"path", "fan_in", "markers", "churn"}],
      "external_packages": {"requests": ["orders/api.py"]},
      "declared_packages": {"requests": ">=2.0"},
      "lockfile_deprecations": [{"package", "version", "message"}],
      "parse_errors": ["path: reason"]
    }

Imports that never run at import time are not graph edges: Python imports
guarded by `if TYPE_CHECKING:` (or `typing.TYPE_CHECKING`; an `else:`
branch still counts), and TypeScript type-only imports (`import type`,
`export type`, or `import { type A, type B }` with every specifier
type-only), which the compiler erases. These are the standard ways to
break a cycle, so counting them would report cycles the code already broke.

Swift has no file-level imports, so a Swift module is a build target and
its "path" is the target's source directory. Targets come from every
Package.swift (SwiftPM: .target, .executableTarget, .testTarget, .macro,
.plugin with a literal name; `path:` or the Sources/<name>, Tests/<name>
defaults) and project.yml (XcodeGen: each target's `sources`) found in a
listed Swift file's directory or its ancestors up to --root, read with
regexes and line parsing. Each listed Swift file belongs to the target
whose source path is its longest prefix (Package.swift wins a tie); an
`import X` in it is an edge to target X, preferring a target declared in
the same manifest. For a target, "markers" sums its files' comment markers
and "churn" counts commits touching any of its files. Imports that match
no target and no Apple/toolchain module are reported in external_packages
(importing files listed), keyed by the package identity when a
`.product(name:, package:)` entry or a Package.resolved pin names it, else
by the module name. Package.resolved pins (next to a manifest, or inside
an .xcodeproj/.xcworkspace beside one) are added to declared_packages as
identity -> version (or branch/revision).

A volatile hub is a module imported by at least HUB_MIN_FAN_IN other
modules that also shows a volatility signal: a TODO/FIXME/HACK/XXX/
@deprecated marker in a comment, or churn (commits touching it in git
history) in the top quartile of the analyzed modules and at least
CHURN_MIN.

Exit codes:
    0  analysis printed
    1  bad arguments
"""

import argparse
import ast
import json
import os
import posixpath
import re
import io
import subprocess
import sys
import sysconfig
import tokenize

HUB_MIN_FAN_IN = 3
CHURN_MIN = 5

PY_EXTS = (".py",)
JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
SWIFT_EXTS = (".swift",)

MARKER = re.compile(r"\b(?:TODO|FIXME|HACK|XXX)\b|@deprecated")

JS_SPECIFIER = re.compile(
    r"""(?:\bimport\s+(?:[^'";]*?\s+from\s+)?|\bexport\s+[^'";]*?\s+from\s+|\brequire\s*\(\s*|\bimport\s*\(\s*)"""
    r"""['"]([^'"\n]+)['"]"""
)
JS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
JS_LINE_COMMENT = re.compile(r"(^|[^:\\'\"])//[^\n]*", re.M)

NODE_BUILTINS = {
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console", "constants",
    "crypto", "dgram", "diagnostics_channel", "dns", "domain", "events", "fs", "http", "http2",
    "https", "inspector", "module", "net", "os", "path", "perf_hooks", "process", "punycode",
    "querystring", "readline", "repl", "stream", "string_decoder", "sys", "timers", "tls",
    "trace_events", "tty", "url", "util", "v8", "vm", "wasi", "worker_threads", "zlib",
}

REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(.*)$")


def stdlib_modules():
    """Top-level standard-library module names for this interpreter."""
    names = set(getattr(sys, "stdlib_module_names", ())) | set(sys.builtin_module_names)
    if not getattr(sys, "stdlib_module_names", None):
        # Python < 3.10: list the stdlib directory itself.
        stdlib = sysconfig.get_paths().get("stdlib")
        for base in filter(None, [stdlib, stdlib and os.path.join(stdlib, "lib-dynload")]):
            for entry in os.listdir(base) if os.path.isdir(base) else []:
                name = entry.split(".")[0]
                if entry.endswith((".py", ".so", ".pyd")) or os.path.isdir(os.path.join(base, entry)):
                    if name and name != "site-packages":
                        names.add(name)
    names.update({"__future__", "__main__"})
    return names


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def comment_markers(path, source):
    """Count TODO/FIXME/HACK/XXX/@deprecated in comments only, so code or
    docs that merely mention the words (like this script) don't count."""
    if language(path) == "python":
        comments = []
        try:
            for tok in tokenize.generate_tokens(io.StringIO(source).readline):
                if tok.type == tokenize.COMMENT:
                    comments.append(tok.string)
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass
        text = "\n".join(comments)
    else:
        text = "\n".join(JS_BLOCK_COMMENT.findall(source) + [m.group(0) for m in JS_LINE_COMMENT.finditer(source)])
    return len(MARKER.findall(text))


def language(path):
    if path.endswith(PY_EXTS):
        return "python"
    if path.endswith(JS_EXTS):
        return "javascript"
    if path.endswith(SWIFT_EXTS):
        return "swift"
    return None


# --- Python -------------------------------------------------------------------

def py_module_name(path):
    parts = path[: -len(".py")].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def is_type_checking(test):
    """True for `if TYPE_CHECKING:` and `if typing.TYPE_CHECKING:` tests."""
    return ((isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
            or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"))


def python_imports(path, source):
    """Yield (dotted_name, level, names, deferred) for each import that runs
    at runtime; level > 0 is relative, deferred means it sits inside a
    function body. TYPE_CHECKING-guarded imports are skipped."""
    tree = ast.parse(source, filename=path)
    stack = [(tree, False)]
    while stack:
        node, deferred = stack.pop()
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, 0, None, deferred
        elif isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names if a.name != "*"]
            yield node.module or "", node.level, names, deferred
        if isinstance(node, ast.If) and is_type_checking(node.test):
            children = node.orelse
        else:
            children = list(ast.iter_child_nodes(node))
        inner = deferred or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
        stack.extend((child, inner) for child in children)


class PythonResolver:
    def __init__(self, py_files):
        self.files = set(py_files)
        self.by_name = {}
        for path in sorted(py_files):
            name = py_module_name(path)
            self.by_name.setdefault(name, path)
            # src/ and lib/ layouts: the package is importable without the prefix.
            for prefix in ("src.", "lib."):
                if name.startswith(prefix):
                    self.by_name.setdefault(name[len(prefix):], path)

    def lookup(self, dotted, importer):
        """Internal path for a dotted name (longest matching prefix), also
        trying the importer's own directory (script-dir-on-sys.path) and
        then each ancestor directory (a nested project root, as in a
        monorepo whose subproject imports its own top-level package)."""
        parts = dotted.split(".")
        here = posixpath.dirname(importer)
        bases = []
        while True:
            bases.append(here)
            if not here:
                break
            here = posixpath.dirname(here)
        for i in range(len(parts), 0, -1):
            name = ".".join(parts[:i])
            if name in self.by_name:
                return self.by_name[name]
            rel = "/".join(parts[:i])
            for base in bases:
                for candidate in (f"{rel}.py", f"{rel}/__init__.py"):
                    path = posixpath.join(base, candidate) if base else candidate
                    if path in self.files:
                        return path
        return None

    def nested_submodule(self, dotted, importer):
        """A dotted name that is exactly a module under some ancestor of
        the importer (no prefix fallback, unlike lookup)."""
        hit = self.lookup(dotted, importer)
        rel = dotted.replace(".", "/")
        if hit and (hit.endswith(f"{rel}.py") or hit.endswith(f"{rel}/__init__.py")):
            return hit
        return None

    def resolve(self, importer, dotted, level, names):
        """Return (internal_paths, external_top_level_names). For
        `from X import a, b`, each name that is a submodule of X resolves to
        that submodule; the others are attributes of X itself."""
        if level:
            package = py_module_name(importer).split(".")
            if not importer.endswith("__init__.py"):
                package = package[:-1]
            package = package[: len(package) - (level - 1)] if level > 1 else package
            base = ".".join(filter(None, package + ([dotted] if dotted else [])))
            found = set()
            for n in names or []:
                sub = self.by_name.get(f"{base}.{n}" if base else n)
                if sub:
                    found.add(sub)
                elif base in self.by_name:
                    found.add(self.by_name[base])
            if not names and base in self.by_name:
                found.add(self.by_name[base])
            return sorted(found), []
        found = set()
        attribute_import = not names
        for n in names or []:
            sub = self.by_name.get(f"{dotted}.{n}") or self.nested_submodule(f"{dotted}.{n}", importer)
            if sub:
                found.add(sub)
            else:
                attribute_import = True
        if attribute_import:
            hit = self.lookup(dotted, importer)
            if hit:
                found.add(hit)
            elif not found:
                return [], [dotted.split(".")[0]]
        return sorted(found), []


# --- JavaScript / TypeScript --------------------------------------------------

JS_TYPE_ONLY = re.compile(r"(?:import|export)\s+type\s+(?!from\b)")
JS_NAMED_CLAUSE = re.compile(r"import\s*\{([^}]*)\}\s*from\b")


def js_type_only(statement):
    """True if an import/export statement is erased by the TypeScript
    compiler: `import type ...`, `export type ...`, or a named import whose
    every specifier is marked `type`."""
    if JS_TYPE_ONLY.match(statement):
        return True
    m = JS_NAMED_CLAUSE.match(statement)
    if m:
        names = [n.strip() for n in m.group(1).split(",") if n.strip()]
        return bool(names) and all(re.match(r"type\s+\w", n) for n in names)
    return False


def js_specifiers(source):
    """Module specifiers imported at runtime (type-only imports excluded)."""
    source = JS_BLOCK_COMMENT.sub("", source)
    source = JS_LINE_COMMENT.sub(r"\1", source)
    return [m.group(1) for m in JS_SPECIFIER.finditer(source) if not js_type_only(m.group(0))]


def js_package(spec):
    if spec.startswith("node:"):
        return None
    if spec.startswith("@"):
        parts = spec.split("/")
        if len(parts) < 2 or parts[0] == "@":
            return None  # path alias such as "@/components"
        return "/".join(parts[:2])
    if spec.startswith("~"):
        return None
    top = spec.split("/")[0]
    return None if top in NODE_BUILTINS else top


def js_resolve(importer, spec, files):
    base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec))
    candidates = [base] + [base + ext for ext in JS_EXTS] + [f"{base}/index{ext}" for ext in JS_EXTS]
    if base.endswith(".js"):  # TS sources imported with a .js extension
        candidates += [base[:-3] + ext for ext in (".ts", ".tsx")]
    for c in candidates:
        if c in files:
            return c
    return None


# --- Swift --------------------------------------------------------------------

SWIFT_IMPORT = re.compile(
    r"^[ \t]*(?:@\w+(?:\([^)\n]*\))?[ \t]+)*import[ \t]+"
    r"(?:(?:typealias|struct|class|enum|protocol|let|var|func)[ \t]+)?([A-Za-z_]\w*)",
    re.M,
)
SPM_TARGET = re.compile(r"\.(target|executableTarget|testTarget|macro|plugin)\s*\(")
SPM_PRODUCT = re.compile(r'\.product\(\s*name:\s*"([^"]+)"\s*,\s*package:\s*"([^"]+)"')
SPM_SOURCE_DIRS = ("Sources", "Source", "src", "srcs")

# Modules shipped with the Swift toolchain or Apple's SDKs: never third-party.
SWIFT_SYSTEM_MODULES = frozenset("""
    Swift Foundation FoundationEssentials FoundationInternationalization FoundationNetworking
    FoundationXML Dispatch Darwin Glibc Musl Bionic Android WinSDK CRT ucrt WASILibc
    XCTest Testing PackageDescription PackagePlugin CompilerPluginSupport Synchronization
    Distributed Observation RegexBuilder Cxx CxxStdlib os OSLog simd ObjectiveC
    Accelerate Accessibility AccessorySetupKit Accounts ActivityKit AdServices AdSupport
    AddressBook AppIntents AppKit AppTrackingTransparency ARKit AssetsLibrary AudioToolbox
    AudioUnit AuthenticationServices AVFAudio AVFoundation AVKit BackgroundAssets BackgroundTasks
    BusinessChat CallKit CarPlay CFNetwork Charts ClockKit CloudKit Cocoa Combine CommonCrypto
    Compression Contacts ContactsUI CoreAudio CoreAudioKit CoreBluetooth CoreData CoreFoundation
    CoreGraphics CoreHaptics CoreImage CoreLocation CoreLocationUI CoreMedia CoreMIDI CoreML
    CoreMotion CoreNFC CoreServices CoreSpotlight CoreTelephony CoreText CoreTransferable
    CoreVideo CreateML CryptoKit CryptoTokenKit DeveloperToolsSupport DeviceActivity DeviceCheck
    EventKit EventKitUI ExtensionFoundation ExtensionKit ExternalAccessory FamilyControls
    FileProvider FileProviderUI Foundation GameController GameKit GameplayKit GLKit GroupActivities
    HealthKit HealthKitUI HomeKit IdentityLookup ImageIO Intents IntentsUI IOKit IOSurface
    JavaScriptCore LinkPresentation LocalAuthentication ManagedSettings MapKit MediaAccessibility
    MediaPlayer MediaToolbox MessageUI Messages Metal MetalKit MetalPerformanceShaders MetricKit
    MobileCoreServices ModelIO MultipeerConnectivity MusicKit NaturalLanguage NearbyInteraction
    Network NetworkExtension NotificationCenter OpenGLES PassKit PDFKit PencilKit Photos PhotosUI
    PushKit QuartzCore QuickLook QuickLookThumbnailing RealityKit ReplayKit SafariServices
    SceneKit ScreenCaptureKit ScreenTime Security SensorKit ServiceManagement SharedWithYou
    ShazamKit Social SoundAnalysis Speech SpriteKit StoreKit SwiftData SwiftUI SystemConfiguration
    TabularData Translation TipKit UIKit UniformTypeIdentifiers UserNotifications
    UserNotificationsUI VideoToolbox Vision VisionKit WatchConnectivity WatchKit WeatherKit
    WebKit WidgetKit XPC
""".split())


def strip_c_comments(source):
    source = JS_BLOCK_COMMENT.sub("", source)
    return JS_LINE_COMMENT.sub(r"\1", source)


def swift_imports(source):
    """Top-level module names imported by a Swift file (`import X`,
    `@testable import X`, `import struct X.Y`, `import X.Sub`), in order."""
    return [m.group(1) for m in SWIFT_IMPORT.finditer(strip_c_comments(source))]


def swift_module_name(target_name):
    """The module name the compiler gives a target (C99 identifier)."""
    return re.sub(r"\W", "_", target_name)


def scan_call(text, start):
    """From just after an opening paren, return (index of its closing paren
    or -1, the argument text with nested (...) and [...] contents removed)."""
    depth, i, top = 1, start, []
    while i < len(text):
        c = text[i]
        if c == '"':
            if text.startswith('"""', i):
                end = text.find('"""', i + 3)
                j = len(text) if end == -1 else end + 3
            else:
                j = i + 1
                while j < len(text) and text[j] not in '"\n':
                    j += 2 if text[j] == "\\" else 1
                j += 1
            if depth == 1:
                top.append(text[i:j])
            i = j
            continue
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
            if depth == 0:
                return i, "".join(top)
        elif depth == 1:
            top.append(c)
        i += 1
    return -1, "".join(top)


def swiftpm_targets(text):
    """(targets, products) declared in a Package.swift: targets as
    (name, is_test, path or None) in order, products as {module: package}
    from `.product(name:, package:)` dependencies."""
    text = strip_c_comments(text)
    targets, pos = [], 0
    while True:
        m = SPM_TARGET.search(text, pos)
        if not m:
            break
        end, top = scan_call(text, m.end())
        if end == -1:
            break
        pos = end + 1  # a nested `.target(name:)` dependency is not a declaration
        name = re.search(r'\bname:\s*"([^"]+)"', top)
        path = re.search(r'\bpath:\s*"([^"]*)"', top)
        if name:
            targets.append((name.group(1), m.group(1) == "testTarget", path.group(1) if path else None))
    return targets, dict(SPM_PRODUCT.findall(text))


def yaml_scalar(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    return value


def yaml_source_item(item):
    """The path named by one `sources` entry: a plain string, `path: X`, or
    `{path: X, ...}`; None for any other key."""
    item = item.strip()
    m = re.search(r"(?:^|[{,\s])path:\s*([^,}]+)", item)
    if m:
        return yaml_scalar(m.group(1))
    if not item or item.startswith("{") or re.match(r"[\w-]+:(\s|$)", item):
        return None
    return yaml_scalar(item)


def xcodegen_targets(text):
    """[(target name, [source paths])] from an XcodeGen project.yml, read
    line by line (block-style `targets:` mapping; `sources` as a string,
    an inline list, or a block list of strings / `path:` entries)."""
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"(^|\s)#.*$", "", raw).rstrip()
        if line.strip() and "\t" not in line[: len(line) - len(line.lstrip())]:
            lines.append((len(line) - len(line.lstrip(" ")), line.strip()))
    targets = []
    in_targets = in_sources = False
    target_indent = key_indent = None
    for indent, line in lines:
        if indent == 0:
            in_targets = line == "targets:"
            target_indent = key_indent = None
            in_sources = False
            continue
        if not in_targets:
            continue
        if target_indent is None:
            target_indent = indent
        if indent == target_indent:
            m = re.fullmatch(r"(.+?):", line)
            targets.append((yaml_scalar(m.group(1)) if m else None, []))
            key_indent = None
            in_sources = False
            continue
        if not targets or targets[-1][0] is None:
            continue
        sources = targets[-1][1]
        if key_indent is None:
            key_indent = indent
        is_item = line.startswith("- ") or line == "-"
        if indent == key_indent and not is_item:
            in_sources = False
            m = re.match(r"sources:\s*(.*)$", line)
            if m:
                value = m.group(1)
                if not value:
                    in_sources = True
                elif value.startswith("["):
                    sources.extend(filter(None, map(yaml_source_item, value.strip("[]").split(","))))
                else:
                    sources.append(yaml_scalar(value))
        elif in_sources and indent >= key_indent:
            found = yaml_source_item(line[1:] if is_item else line) if (is_item or line.startswith("path:")) else None
            if found:
                sources.append(found)
    return [(name, srcs) for name, srcs in targets if name]


def under(path, directory):
    return directory == "" or path == directory or path.startswith(directory + "/")


def swift_manifest_dirs(root, paths):
    """Directories (relative to root, "" for root itself) that hold a
    Package.swift or project.yml and contain, or are named by, a listed
    Swift file or manifest. Sorted."""
    seen, found = set(), set()
    for path in paths:
        if not (path.endswith(SWIFT_EXTS) or posixpath.basename(path) == "project.yml"):
            continue
        here = posixpath.dirname(path)
        while here not in seen:
            seen.add(here)
            if any(os.path.isfile(os.path.join(root, here, name)) for name in ("Package.swift", "project.yml")):
                found.add(here)
            if not here:
                break
            here = posixpath.dirname(here)
    return sorted(found)


def swift_targets(root, manifest_dirs, parse_errors):
    """Every target declared under the given manifest directories, as
    dicts {name, module, manifest, dirs}; `dirs` are source paths relative
    to root. Also returns the merged {module: package} product map."""
    targets, products = [], {}
    for base in manifest_dirs:
        def rel(sub):
            joined = posixpath.normpath(posixpath.join(base, sub))
            if joined == ".":
                return ""
            return None if joined.startswith("../") or joined == ".." or joined.startswith("/") else joined

        package = posixpath.join(base, "Package.swift")
        if os.path.isfile(os.path.join(root, package)):
            try:
                declared, found = swiftpm_targets(read_text(os.path.join(root, package)))
            except OSError as e:
                parse_errors.append(f"{package}: {e}")
                declared, found = [], {}
            for module, pkg in found.items():
                products.setdefault(module, pkg)
            for name, is_test, path in declared:
                if path is None:
                    parents = (("Tests",) if is_test else ()) + SPM_SOURCE_DIRS
                    path = next((f"{p}/{name}" for p in parents
                                 if os.path.isdir(os.path.join(root, base, p, name))), f"{parents[0]}/{name}")
                d = rel(path)
                targets.append({"name": name, "module": swift_module_name(name), "manifest": package,
                                "dirs": [] if d is None else [d]})
        project = posixpath.join(base, "project.yml")
        if os.path.isfile(os.path.join(root, project)):
            try:
                declared = xcodegen_targets(read_text(os.path.join(root, project)))
            except OSError as e:
                parse_errors.append(f"{project}: {e}")
                declared = []
            for name, sources in declared:
                dirs = [d for d in map(rel, sources) if d is not None]
                targets.append({"name": name, "module": swift_module_name(name), "manifest": project,
                                "dirs": dirs})
    return targets, products


def assign_swift_files(swift_files, targets):
    """Map each Swift file to its owning target (longest source-path
    prefix, earliest target on a tie) and name each owning target's node
    after the first of its source paths that owns a file. Returns
    ({file: node path}, {node path: target})."""
    owner_dir = {}
    for path in swift_files:
        best = None
        for index, target in enumerate(targets):
            for d in target["dirs"]:
                if under(path, d) and (best is None or len(d) > len(best[1])):
                    best = (index, d)
        if best:
            owner_dir[path] = best
    nodes, node_of_target = {}, {}
    for index, target in enumerate(targets):
        owned = {d for (i, d) in owner_dir.values() if i == index}
        first = next((d for d in target["dirs"] if d in owned), None)
        if first is not None:
            node_of_target[index] = first or "."
            nodes[first or "."] = target
    return {path: node_of_target[i] for path, (i, _) in owner_dir.items()}, nodes


def swift_pins(root, dirs, parse_errors):
    """{package identity: version} from every Package.resolved in `dirs` or
    in an .xcodeproj/.xcworkspace directly inside one of them."""
    pins = {}
    for base in dirs:
        candidates = [posixpath.join(base, "Package.resolved")]
        full = os.path.join(root, base)
        for entry in sorted(os.listdir(full)) if os.path.isdir(full) else []:
            if entry.endswith(".xcodeproj"):
                candidates.append(posixpath.join(base, entry, "project.xcworkspace/xcshareddata/swiftpm/Package.resolved"))
            elif entry.endswith(".xcworkspace"):
                candidates.append(posixpath.join(base, entry, "xcshareddata/swiftpm/Package.resolved"))
        for candidate in candidates:
            if not os.path.isfile(os.path.join(root, candidate)):
                continue
            try:
                data = json.loads(read_text(os.path.join(root, candidate)))
                entries = data.get("pins")
                if entries is None:
                    entries = (data.get("object") or {}).get("pins")  # format version 1
                for pin in entries or []:
                    name = str(pin.get("identity") or pin.get("package") or "").lower()
                    state = pin.get("state") or {}
                    version = state.get("version") or state.get("branch") or state.get("revision") or ""
                    if name:
                        pins.setdefault(name, str(version))
            except (ValueError, AttributeError, TypeError) as e:
                parse_errors.append(f"{candidate}: {e}")
    return pins


def analyze_swift(root, paths, graph, markers, external, parse_errors):
    """Add Swift target nodes and edges to `graph`, their marker counts to
    `markers` and third-party imports to `external`. Returns
    ({swift file: node path}, {package identity: version})."""
    swift_files = [p for p in paths if language(p) == "swift"]
    manifest_dirs = swift_manifest_dirs(root, paths)
    if not swift_files and not manifest_dirs:
        return {}, {}
    targets, products = swift_targets(root, manifest_dirs, parse_errors)
    owner, nodes = assign_swift_files(swift_files, targets)
    pins = swift_pins(root, sorted(set(manifest_dirs) | {""}), parse_errors)

    by_module = {}
    for node, target in sorted(nodes.items()):
        by_module.setdefault(target["module"], []).append(node)
    declared_modules = {t["module"] for t in targets}

    for node in nodes:
        graph[node] = set()
        markers[node] = 0
    for path in sorted(owner):
        node = owner[path]
        try:
            source = read_text(os.path.join(root, path))
        except OSError as e:
            parse_errors.append(f"{path}: {e}")
            continue
        markers[node] += comment_markers(path, source)
        for module in swift_imports(source):
            candidates = by_module.get(module)
            if candidates:
                same = [c for c in candidates if nodes[c]["manifest"] == nodes[node]["manifest"]]
                target = (same or candidates)[0]
                if target != node:
                    graph[node].add(target)
            elif module in declared_modules or module in SWIFT_SYSTEM_MODULES or module.startswith("_"):
                continue
            else:
                package = products.get(module, module)
                package = package.lower() if package.lower() in pins else package
                external.setdefault(package, set()).add(path)
    return owner, pins


# --- Graph analysis -----------------------------------------------------------

def strongly_connected(graph):
    """Tarjan's algorithm, iterative. Returns components with > 1 member or
    a self-import, each sorted, the list sorted."""
    index, low, on_stack, stack, result = {}, {}, set(), [], []
    counter = [0]
    for start in sorted(graph):
        if start in index:
            continue
        work = [(start, iter(sorted(graph[start])))]
        index[start] = low[start] = counter[0]
        counter[0] += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter[0]
                    counter[0] += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(graph.get(child, ())))))
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1 or node in graph.get(node, ()):
                    result.append(sorted(component))
    return sorted(result)


def git_churn(root, groups=None):
    """Commits touching each path (relative to root); empty without git
    history. `groups` maps paths to a group key (a Swift target): each
    group also gets the number of commits touching any of its paths."""
    try:
        out = subprocess.run(
            ["git", "-C", root, "log", "--format=%x01", "--name-only", "--relative", "--", "."],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if out.returncode != 0:
        return {}
    churn = {}
    touched = set()  # groups already counted for the current commit
    for line in out.stdout.splitlines():
        line = line.strip()
        if line == "\x01":
            touched = set()
        elif line:
            churn[line] = churn.get(line, 0) + 1
            group = (groups or {}).get(line)
            if group is not None and group not in touched:
                touched.add(group)
                churn[group] = churn.get(group, 0) + 1
    return churn


def volatile_hubs(modules):
    churn_values = sorted(m["churn"] for m in modules)
    top_quartile = churn_values[(3 * (len(churn_values) - 1)) // 4] if churn_values else 0
    churn_bar = max(CHURN_MIN, top_quartile)
    hubs = []
    for m in modules:
        if m["fan_in"] >= HUB_MIN_FAN_IN and (m["markers"] > 0 or m["churn"] >= churn_bar):
            hubs.append({k: m[k] for k in ("path", "fan_in", "markers", "churn")})
    return sorted(hubs, key=lambda h: (-h["fan_in"], h["path"]))


# --- Manifests ----------------------------------------------------------------

def declared_packages(root, parse_errors):
    declared = {}

    package_json = os.path.join(root, "package.json")
    if os.path.isfile(package_json):
        try:
            data = json.loads(read_text(package_json))
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                for name, version in (data.get(key) or {}).items():
                    declared.setdefault(name, str(version))
        except (ValueError, AttributeError) as e:
            parse_errors.append(f"package.json: {e}")

    for entry in sorted(os.listdir(root)):
        if re.fullmatch(r"requirements.*\.txt", entry) and os.path.isfile(os.path.join(root, entry)):
            for line in read_text(os.path.join(root, entry)).splitlines():
                line = line.split("#", 1)[0].strip()
                if not line or line.startswith("-"):
                    continue
                m = REQUIREMENT_NAME.match(line)
                if m:
                    declared.setdefault(m.group(1).lower(), m.group(2).split(";")[0].strip())

    pyproject = os.path.join(root, "pyproject.toml")
    if os.path.isfile(pyproject):
        for name, spec in pyproject_dependencies(read_text(pyproject)):
            declared.setdefault(name.lower(), spec)

    return dict(sorted(declared.items()))


def pyproject_dependencies(text):
    """Minimal pyproject.toml reading (no tomllib before Python 3.11):
    [project] dependencies = [...] and [tool.poetry.dependencies] keys."""
    section = None
    in_list = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if in_list:
            for item in re.findall(r"""['"]([^'"]+)['"]""", line):
                m = REQUIREMENT_NAME.match(item)
                if m:
                    yield m.group(1), m.group(2).strip()
            if "]" in line:
                in_list = False
            continue
        header = re.fullmatch(r"\[([^\]]+)\]", line)
        if header:
            section = header.group(1).strip()
            continue
        if section == "project" and re.match(r"dependencies\s*=\s*\[", line):
            rest = line.split("[", 1)[1]
            for item in re.findall(r"""['"]([^'"]+)['"]""", rest):
                m = REQUIREMENT_NAME.match(item)
                if m:
                    yield m.group(1), m.group(2).strip()
            in_list = "]" not in rest
        elif section == "tool.poetry.dependencies":
            m = re.match(r"""['"]?([A-Za-z0-9][A-Za-z0-9._-]*)['"]?\s*=\s*(.+)""", line)
            if m and m.group(1).lower() != "python":
                yield m.group(1), m.group(2).strip().strip("'\"")


def lockfile_deprecations(root, parse_errors):
    path = os.path.join(root, "package-lock.json")
    if not os.path.isfile(path):
        return []
    try:
        data = json.loads(read_text(path))
    except ValueError as e:
        parse_errors.append(f"package-lock.json: {e}")
        return []
    found = {}
    for key, info in (data.get("packages") or {}).items():  # lockfileVersion 2/3
        if key and isinstance(info, dict) and info.get("deprecated"):
            name = key.rsplit("node_modules/", 1)[-1]
            found[(name, str(info.get("version", "")))] = str(info["deprecated"])

    def walk(deps):  # lockfileVersion 1
        for name, info in (deps or {}).items():
            if isinstance(info, dict):
                if info.get("deprecated"):
                    found.setdefault((name, str(info.get("version", ""))), str(info["deprecated"]))
                walk(info.get("dependencies"))

    walk(data.get("dependencies"))
    return [{"package": n, "version": v, "message": msg} for (n, v), msg in sorted(found.items())]


# --- Main ---------------------------------------------------------------------

def clean_path(p):
    p = p.strip()
    while p.startswith("./"):
        p = p[2:]
    return p


def analyze(root, paths):
    """Build the import-graph report (the JSON object in this module's
    docstring) for `paths`, relative to `root`. Paths that aren't files are
    ignored; files that don't parse are listed in parse_errors."""
    paths = sorted({clean_path(p) for p in paths if clean_path(p)})
    paths = [p for p in paths if os.path.isfile(os.path.join(root, p))]
    stdlib = stdlib_modules()
    parse_errors = []

    py_files = [p for p in paths if language(p) == "python"]
    js_files = set(p for p in paths if language(p) == "javascript")
    resolver = PythonResolver(py_files)

    graph = {p: set() for p in paths if language(p) in ("python", "javascript")}
    source_files = len(graph)
    deferred = {p: set() for p in graph}
    external = {}
    markers = {}

    for path in sorted(graph):
        try:
            source = read_text(os.path.join(root, path))
        except OSError as e:
            parse_errors.append(f"{path}: {e}")
            continue
        markers[path] = comment_markers(path, source)
        if language(path) == "python":
            try:
                imports = list(python_imports(path, source))
            except (SyntaxError, ValueError) as e:
                parse_errors.append(f"{path}: {e.__class__.__name__}: {e}")
                continue
            for dotted, level, names, is_deferred in imports:
                internal, packages = resolver.resolve(path, dotted, level, names)
                targets = deferred[path] if is_deferred else graph[path]
                targets.update(i for i in internal if i != path or level == 0)
                for pkg in packages:
                    if pkg not in stdlib:
                        external.setdefault(pkg, set()).add(path)
        else:
            for spec in js_specifiers(source):
                if spec.startswith((".", "/")):
                    target = js_resolve(path, spec, js_files)
                    if target:
                        graph[path].add(target)
                else:
                    pkg = js_package(spec)
                    if pkg:
                        external.setdefault(pkg, set()).add(path)

    swift_owner, swift_pinned = analyze_swift(root, paths, graph, markers, external, parse_errors)
    lang = {p: language(p) if p in deferred else "swift" for p in graph}
    for p in graph:
        deferred.setdefault(p, set())

    churn = git_churn(root, swift_owner)
    fan_in = {p: 0 for p in graph}
    for importer in graph:
        for t in graph[importer] | deferred[importer]:
            if t != importer:
                fan_in[t] += 1

    modules = [{
        "path": p,
        "language": lang[p],
        "imports": sorted(graph[p]),
        "fan_in": fan_in[p],
        "markers": markers.get(p, 0),
        "churn": churn.get(p, 0),
    } for p in sorted(graph)]

    counts = {}
    for p in graph:
        counts[lang[p]] = counts.get(lang[p], 0) + 1

    declared = declared_packages(root, parse_errors)
    for name, version in swift_pinned.items():
        declared.setdefault(name, version)

    return {
        "languages": dict(sorted(counts.items())),
        "unsupported_files": len(paths) - source_files - len(swift_owner),
        "modules": modules,
        "deferred_imports": [{"path": p, "imports": sorted(deferred[p] - graph[p] - {p})}
                             for p in sorted(deferred) if deferred[p] - graph[p] - {p}],
        "cycles": strongly_connected(graph),
        "volatile_hubs": volatile_hubs(modules),
        "external_packages": {k: sorted(v) for k, v in sorted(external.items())},
        "declared_packages": dict(sorted(declared.items())),
        "lockfile_deprecations": lockfile_deprecations(root, parse_errors),
        "parse_errors": parse_errors,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--files-from")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        print(f"Error: --root '{args.root}' is not a directory.", file=sys.stderr)
        return 1
    paths = list(args.files)
    if args.files_from:
        if args.files_from == "-":
            paths += sys.stdin.read().splitlines()
        elif os.path.isfile(args.files_from):
            paths += read_text(args.files_from).splitlines()
        else:
            print(f"Error: --files-from '{args.files_from}' not found.", file=sys.stderr)
            return 1
    if not paths:
        print("Error: give files as arguments or with --files-from.", file=sys.stderr)
        return 1

    result = analyze(args.root, paths)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    for e in result["parse_errors"]:
        print(f"Warning: could not parse {e}", file=sys.stderr)
    print(
        f"Analyzed {len(result['modules'])} module(s) "
        f"({', '.join(f'{n} {lang}' for lang, n in result['languages'].items()) or 'none'}); "
        f"{len(result['cycles'])} cycle(s), {len(result['volatile_hubs'])} volatile hub(s), "
        f"{len(result['external_packages'])} external package(s) imported.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
