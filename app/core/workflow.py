# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Directed acyclic graph validation, caching and execution for SignalDojo."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
import tracemalloc
from typing import Any, Callable, Iterable

from .blocks import BlockError, ProcessingBlock
from .models import ScalarResult, SignalData, SpectrogramData, SpectrumData, TableResult, result_signature


@dataclass(slots=True)
class WorkflowNode:
    node_id: str
    block: ProcessingBlock
    position: tuple[float, float] = (0.0, 0.0)
    label: str = ""
    last_outputs: list[Any] = field(default_factory=list)
    state: str = "idle"
    cache_key: str | None = None
    execution_seconds: float = 0.0
    warning: str = ""


@dataclass(frozen=True, slots=True)
class Connection:
    source_id: str
    source_port: int
    target_id: str
    target_port: int


@dataclass(slots=True)
class ExecutionReport:
    duration_seconds: float
    executed_nodes: list[str]
    outputs: dict[str, list[Any]]
    cached_nodes: list[str] = field(default_factory=list)
    skipped_nodes: list[str] = field(default_factory=list)
    peak_memory_bytes: int = 0
    warnings: list[str] = field(default_factory=list)


_TYPE_COMPATIBILITY = {
    "any": {"any", "signal", "scalar", "table", "spectrum", "spectrogram"},
    "signal": {"signal"},
    "scalar": {"scalar"},
    "table": {"table"},
    "spectrum": {"spectrum"},
    "spectrogram": {"spectrogram"},
}


class WorkflowGraph:
    """A validated deterministic block-processing graph with incremental caching."""

    def __init__(self) -> None:
        self.nodes: dict[str, WorkflowNode] = {}
        self.connections: list[Connection] = []

    def add_node(self, node: WorkflowNode) -> None:
        if node.node_id in self.nodes:
            raise BlockError(f"Duplicate node id: {node.node_id}")
        self.nodes[node.node_id] = node

    @staticmethod
    def _port_type(types: tuple[str, ...], index: int) -> str:
        if not types:
            return "any"
        if index < len(types):
            return types[index]
        return types[-1]

    def validate_connection(self, connection: Connection, *, already_present: bool = False) -> None:
        if connection.source_id == connection.target_id:
            raise BlockError("A block cannot connect to itself.")
        if connection.source_id not in self.nodes or connection.target_id not in self.nodes:
            raise BlockError("Connection references a missing block.")
        source = self.nodes[connection.source_id].block
        target = self.nodes[connection.target_id].block
        if not 0 <= connection.source_port < source.output_count:
            raise BlockError("Source port does not exist.")
        if not 0 <= connection.target_port < target.input_count:
            raise BlockError("Target port does not exist.")
        occupied = [
            c for c in self.connections
            if c.target_id == connection.target_id and c.target_port == connection.target_port
        ]
        # Validation of an existing graph record ignores exactly that one record.
        # Adding a new record never ignores an equal value, which prevents duplicates.
        if already_present and connection in occupied:
            occupied.remove(connection)
        if occupied:
            raise BlockError("That input port is already connected.")
        source_type = self._port_type(source.output_types, connection.source_port)
        target_type = self._port_type(target.input_types, connection.target_port)
        if source_type not in _TYPE_COMPATIBILITY.get(target_type, {target_type}):
            raise BlockError(
                f"Incompatible ports: {source.display_name} output is '{source_type}', "
                f"but {target.display_name} expects '{target_type}'."
            )

    def add_connection(self, connection: Connection) -> None:
        self.validate_connection(connection)
        self.connections.append(connection)
        try:
            self.topological_order()
        except BlockError:
            self.connections.pop()
            raise

    def remove_connection(self, connection: Connection) -> None:
        if connection in self.connections:
            self.connections.remove(connection)
            self.invalidate_downstream({connection.target_id}, include_roots=True)

    def topological_order(self, node_subset: set[str] | None = None) -> list[str]:
        subset = set(self.nodes) if node_subset is None else set(node_subset)
        unknown = subset - set(self.nodes)
        if unknown:
            raise BlockError(f"Unknown workflow node(s): {', '.join(sorted(unknown))}")
        indegree = {node_id: 0 for node_id in subset}
        downstream: dict[str, list[str]] = defaultdict(list)
        for connection in self.connections:
            if connection.source_id in subset and connection.target_id in subset:
                indegree[connection.target_id] += 1
                downstream[connection.source_id].append(connection.target_id)
        queue = deque(sorted(node_id for node_id, degree in indegree.items() if degree == 0))
        ordered: list[str] = []
        while queue:
            node_id = queue.popleft()
            ordered.append(node_id)
            for target_id in sorted(downstream[node_id]):
                indegree[target_id] -= 1
                if indegree[target_id] == 0:
                    queue.append(target_id)
        if len(ordered) != len(subset):
            raise BlockError("The workflow contains a circular dependency.")
        return ordered

    def ancestors(self, node_ids: Iterable[str]) -> set[str]:
        selected = set(node_ids)
        incoming: dict[str, list[str]] = defaultdict(list)
        for connection in self.connections:
            incoming[connection.target_id].append(connection.source_id)
        queue = deque(selected)
        while queue:
            node_id = queue.popleft()
            for parent in incoming[node_id]:
                if parent not in selected:
                    selected.add(parent)
                    queue.append(parent)
        return selected

    def descendants(self, node_ids: Iterable[str]) -> set[str]:
        selected = set(node_ids)
        downstream: dict[str, list[str]] = defaultdict(list)
        for connection in self.connections:
            downstream[connection.source_id].append(connection.target_id)
        queue = deque(selected)
        while queue:
            node_id = queue.popleft()
            for child in downstream[node_id]:
                if child not in selected:
                    selected.add(child)
                    queue.append(child)
        return selected

    def invalidate_downstream(self, node_ids: Iterable[str], *, include_roots: bool = True) -> None:
        roots = set(node_ids)
        affected = self.descendants(roots)
        if not include_roots:
            affected -= roots
        for node_id in affected:
            node = self.nodes[node_id]
            node.cache_key = None
            node.last_outputs = []
            node.state = "idle"
            node.warning = ""

    def clear_cache(self) -> None:
        for node in self.nodes.values():
            node.cache_key = None
            node.last_outputs = []
            node.state = "idle"
            node.warning = ""

    def validate(self, node_subset: set[str] | None = None) -> list[str]:
        subset = set(self.nodes) if node_subset is None else set(node_subset)
        order = self.topological_order(subset)
        incoming = {(c.target_id, c.target_port) for c in self.connections if c.target_id in subset and c.source_id in subset}
        for connection in self.connections:
            if connection.source_id in subset and connection.target_id in subset:
                self.validate_connection(connection, already_present=True)
        for node_id in subset:
            node = self.nodes[node_id]
            connected = sum((node_id, port) in incoming for port in range(node.block.input_count))
            required = node.block.input_count if node.block.minimum_inputs is None else node.block.minimum_inputs
            if connected < required:
                raise BlockError(f"'{node.block.display_name}' requires at least {required} connected input(s).")
        return order

    @staticmethod
    def _source_file_token(block: ProcessingBlock) -> dict[str, Any]:
        raw = str(block.params.get("file_path", "")).strip()
        if not raw:
            return {}
        path = Path(raw).expanduser()
        if not path.exists():
            return {"file_path": str(path), "missing": True}
        stat = path.stat()
        return {"file_path": str(path.resolve()), "file_size": stat.st_size, "file_mtime_ns": stat.st_mtime_ns}

    def _cache_key(self, node: WorkflowNode, inputs: list[Any]) -> str:
        payload = {
            "block": node.block.type_name,
            "params": node.block.serialise_params(),
            "source": self._source_file_token(node.block),
            "inputs": [result_signature(value) for value in inputs],
        }
        return sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_output_count(node: WorkflowNode, outputs: list[Any]) -> None:
        if not isinstance(outputs, list):
            raise BlockError(f"{node.block.display_name} returned a non-list output.")
        if len(outputs) != node.block.output_count:
            raise BlockError(
                f"{node.block.display_name} declared {node.block.output_count} output(s) "
                f"but returned {len(outputs)}."
            )
        expected_types: dict[str, tuple[type[Any], ...]] = {
            "signal": (SignalData,),
            "scalar": (ScalarResult,),
            "table": (TableResult,),
            "spectrum": (SpectrumData,),
            "spectrogram": (SpectrogramData,),
        }
        for index, value in enumerate(outputs):
            if value is None:
                continue  # Optional output ports, such as unused Import channels.
            declared = WorkflowGraph._port_type(node.block.output_types, index)
            accepted = expected_types.get(declared)
            if accepted is not None and not isinstance(value, accepted):
                raise BlockError(
                    f"{node.block.display_name} output {index + 1} declared type '{declared}' "
                    f"but returned {type(value).__name__}."
                )

    def execute(
        self,
        *,
        targets: Iterable[str] | None = None,
        progress: Callable[[str, int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        use_cache: bool = True,
    ) -> ExecutionReport:
        subset = self.ancestors(targets) if targets is not None else set(self.nodes)
        order = self.validate(subset)
        outputs: dict[str, list[Any]] = {}
        executed: list[str] = []
        cached: list[str] = []
        skipped = sorted(set(self.nodes) - subset)
        warnings: list[str] = []
        started = perf_counter()

        incoming_by_node: dict[str, list[Connection]] = defaultdict(list)
        for connection in self.connections:
            if connection.source_id in subset and connection.target_id in subset:
                incoming_by_node[connection.target_id].append(connection)

        tracemalloc.start()
        try:
            for index, node_id in enumerate(order, start=1):
                if is_cancelled and is_cancelled():
                    raise BlockError("Workflow execution was cancelled.")
                node = self.nodes[node_id]
                ordered_inputs: list[Any] = [None] * node.block.input_count
                for connection in incoming_by_node[node_id]:
                    source_outputs = outputs.get(connection.source_id, self.nodes[connection.source_id].last_outputs)
                    try:
                        ordered_inputs[connection.target_port] = source_outputs[connection.source_port]
                    except IndexError as exc:
                        raise BlockError("A connected upstream output is unavailable.") from exc
                cache_key = self._cache_key(node, ordered_inputs)
                can_reuse = (
                    use_cache
                    and node.block.cacheable
                    and node.cache_key == cache_key
                    and len(node.last_outputs) == node.block.output_count
                )
                if can_reuse:
                    outputs[node_id] = node.last_outputs
                    node.state = "cached"
                    cached.append(node_id)
                    if node.warning: warnings.append(f"{node.block.display_name}: {node.warning}")
                    if progress:
                        progress(node_id, index, len(order))
                    continue
                node.warning = ""
                node.state = "processing"
                if progress:
                    progress(node_id, index, len(order))
                node_started = perf_counter()
                try:
                    result = node.block.execute(ordered_inputs)
                    self._validate_output_count(node, result)
                except BlockError as exc:
                    node.state = "failed"
                    raise BlockError(f"{node.block.display_name}: {exc}") from exc
                except MemoryError as exc:
                    node.state = "failed"
                    raise BlockError(f"{node.block.display_name}: insufficient memory for this operation.") from exc
                except Exception as exc:
                    node.state = "failed"
                    raise BlockError(f"{node.block.display_name} failed unexpectedly: {exc}") from exc
                node.execution_seconds = perf_counter() - node_started
                node.last_outputs = result
                node.cache_key = cache_key if node.block.cacheable else None
                runtime_warnings: list[str] = []
                for value in result:
                    if not isinstance(value, SignalData): continue
                    quality = value.attributes.get("import_quality", {})
                    if isinstance(quality, dict):
                        invalid = int(quality.get("invalid_values", 0) or 0); missing = int(quality.get("missing_values_before_policy", 0) or 0); removed = int(quality.get("rows_removed", 0) or 0)
                        if invalid or missing or removed:
                            runtime_warnings.append(f"import handled {invalid} invalid value(s), {missing} missing value(s), and removed {removed} row(s)")
                    if value.contains_non_finite and not value.attributes.get("intentional_non_finite_markers", False):
                        runtime_warnings.append("output contains NaN or infinite values")
                node.warning = "; ".join(dict.fromkeys(runtime_warnings))
                node.state = "warning" if node.warning else "completed"
                if node.warning: warnings.append(f"{node.block.display_name}: {node.warning}")
                outputs[node_id] = result
                executed.append(node_id)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            if tracemalloc.is_tracing():
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()

        return ExecutionReport(
            duration_seconds=perf_counter() - started,
            executed_nodes=executed,
            outputs=outputs,
            cached_nodes=cached,
            skipped_nodes=skipped,
            peak_memory_bytes=peak,
            warnings=warnings,
        )
