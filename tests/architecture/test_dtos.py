"""Architecture test: every ``msgspec.Struct`` in every ``backend/<module>/models.py`` is
declared ``frozen=True, kw_only=True, gc=False`` (STORY-001-AC-3, extended to every backend
module by STORY-003 so this gate is not silently scoped to ``backend/domain/`` alone).

Two complementary techniques are used together: an AST walk over each source file catches the
declaration-site keyword arguments (structural, cannot be faked by runtime behaviour alone),
and a runtime construction/mutation check on every discovered Struct proves the declared flags
actually take effect (behavioural, catches a msgspec version regression an AST check alone
would miss).
"""

import ast
from enum import StrEnum
import importlib
import inspect
from pathlib import Path
from types import ModuleType, UnionType
from typing import Annotated, TypeAliasType, get_args, get_origin

import msgspec
import pytest

from ollama_llm_bench import backend

_BACKEND_PACKAGE_ROOT = Path(inspect.getfile(backend)).parent
_MIN_EXPECTED_STRUCT_COUNT = 30


def _discover_models_modules() -> list[ModuleType]:
    """Import every ``backend/<module>/models.py`` file discovered on disk."""
    return [
        importlib.import_module(f"{backend.__name__}.{models_path.parent.name}.models")
        for models_path in sorted(_BACKEND_PACKAGE_ROOT.glob("*/models.py"))
    ]


_MODELS_MODULES = _discover_models_modules()


def _iter_struct_class_defs(module: ModuleType) -> list[ast.ClassDef]:
    """Return every class definition in ``module`` whose bases include ``msgspec.Struct``."""
    source_path = inspect.getfile(module)
    with open(source_path, encoding="utf-8") as source_file:
        tree = ast.parse(source_file.read(), filename=source_path)
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(
            (isinstance(base, ast.Attribute) and base.attr == "Struct")
            or (isinstance(base, ast.Name) and base.id == "Struct")
            for base in node.bases
        )
    ]


def _struct_defs_and_ids() -> tuple[list[tuple[ModuleType, ast.ClassDef]], list[str]]:
    pairs: list[tuple[ModuleType, ast.ClassDef]] = []
    ids: list[str] = []
    for module in _MODELS_MODULES:
        for struct_def in _iter_struct_class_defs(module):
            pairs.append((module, struct_def))
            ids.append(f"{module.__name__}.{struct_def.name}")
    return pairs, ids


_STRUCT_DEFS, _STRUCT_IDS = _struct_defs_and_ids()


def test_at_least_one_struct_discovered() -> None:
    """Proves: STORY-001-AC-3

    Sanity guard for the AST walker itself: the discovered ``models.py`` files declare at
    least one ``msgspec.Struct`` subclass, so the parametrized checks below are not
    vacuously true.
    """
    # Assert
    assert len(_STRUCT_DEFS) >= _MIN_EXPECTED_STRUCT_COUNT


@pytest.mark.parametrize("module_and_struct_def", _STRUCT_DEFS, ids=_STRUCT_IDS)
def test_dtos_are_frozen_kw_only(module_and_struct_def: tuple[ModuleType, ast.ClassDef]) -> None:
    """Proves: STORY-001-AC-3

    Every ``msgspec.Struct`` subclass declared in any ``backend/<module>/models.py`` carries
    the ``frozen=True, kw_only=True, gc=False`` class keyword arguments at its declaration
    site.
    """
    # Act
    _module, struct_def = module_and_struct_def
    declared_kwargs = {kw.arg: kw.value for kw in struct_def.keywords if kw.arg is not None}

    # Assert
    assert declared_kwargs.keys() >= {"frozen", "kw_only", "gc"}
    assert _is_ast_true(declared_kwargs["frozen"])
    assert _is_ast_true(declared_kwargs["kw_only"])
    assert _is_ast_false(declared_kwargs["gc"])


def _is_ast_true(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _is_ast_false(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _discover_struct_classes(module: ModuleType) -> list[type[msgspec.Struct]]:
    """Return every ``msgspec.Struct`` subclass actually defined in ``module`` at runtime."""
    return [
        obj
        for _, obj in inspect.getmembers(module, inspect.isclass)
        if issubclass(obj, msgspec.Struct)
        and obj is not msgspec.Struct
        and obj.__module__ == module.__name__
    ]


def _runtime_structs_and_ids() -> tuple[list[type[msgspec.Struct]], list[str]]:
    structs: list[type[msgspec.Struct]] = []
    ids: list[str] = []
    for module in _MODELS_MODULES:
        for struct_cls in _discover_struct_classes(module):
            structs.append(struct_cls)
            ids.append(f"{module.__name__}.{struct_cls.__name__}")
    return structs, ids


_RUNTIME_STRUCTS, _RUNTIME_STRUCT_IDS = _runtime_structs_and_ids()


@pytest.mark.parametrize("struct_cls", _RUNTIME_STRUCTS, ids=_RUNTIME_STRUCT_IDS)
def test_struct_rejects_positional_construction(struct_cls: type[msgspec.Struct]) -> None:
    """Proves: STORY-001-AC-3

    Every backend ``msgspec.Struct`` rejects positional construction because it is declared
    ``kw_only=True`` — passing any positional argument raises ``TypeError``.
    """
    # Arrange
    field_count = len(struct_cls.__struct_fields__)
    dummy_positional_args = (None,) * max(field_count, 1)

    # Act / Assert
    with pytest.raises(TypeError):
        struct_cls(*dummy_positional_args)


@pytest.mark.parametrize("struct_cls", _RUNTIME_STRUCTS, ids=_RUNTIME_STRUCT_IDS)
def test_struct_instance_is_immutable(struct_cls: type[msgspec.Struct]) -> None:
    """Proves: STORY-001-AC-3

    Every backend ``msgspec.Struct`` is immutable because it is declared ``frozen=True`` —
    assigning to any field of a constructed instance raises ``AttributeError``.
    """
    # Arrange
    instance = msgspec.convert(_zero_valued_payload(struct_cls), type=struct_cls, strict=False)
    first_field = struct_cls.__struct_fields__[0]

    # Act / Assert
    with pytest.raises(AttributeError):
        setattr(instance, first_field, None)


def _zero_valued_payload(struct_cls: type[msgspec.Struct]) -> dict[str, object]:
    """Build a minimally-valid decode payload so ``msgspec.convert`` can construct an instance
    of any Struct in this module regardless of its required-field shape, using each field's
    declared default where one exists and a type-appropriate placeholder otherwise."""
    payload: dict[str, object] = {}
    for field_info in msgspec.structs.fields(struct_cls):
        if field_info.default is not msgspec.NODEFAULT:
            continue
        if field_info.default_factory is not msgspec.NODEFAULT:
            continue
        payload[field_info.encode_name] = _placeholder_for_type(field_info.type)
    return payload


_SCALAR_PLACEHOLDERS: dict[object, object] = {bool: False, int: 1, float: 0.0, str: "x"}
_VALID_UUID4_PLACEHOLDER = "a3b8c1d2-7f04-4b8e-9c1d-2e5f0a1b3c4d"


_ORIGIN_PLACEHOLDER_BUILDERS: dict[object, object] = {
    tuple: lambda _field_type: (),
    dict: lambda _field_type: {},
}


def _placeholder_for_type(field_type: object) -> object:
    """Return a permissive placeholder value msgspec can decode for a required field's
    resolved type. Good enough to construct an instance for the immutability check — the
    DTO's own field-level constraint tests live in ``test_constrained_types.py``."""
    if isinstance(field_type, TypeAliasType):
        return _placeholder_for_type(field_type.__value__)
    origin = get_origin(field_type)
    if origin is Annotated:
        return _placeholder_for_annotated(field_type)
    if origin is UnionType:
        return _placeholder_for_optional(field_type)
    if origin in _ORIGIN_PLACEHOLDER_BUILDERS:
        return _ORIGIN_PLACEHOLDER_BUILDERS[origin](field_type)  # type: ignore[operator]  # dispatch table
    return _placeholder_for_class(field_type)


def _placeholder_for_class(field_type: object) -> object:
    if isinstance(field_type, type) and issubclass(field_type, StrEnum):
        return next(iter(field_type)).value
    if isinstance(field_type, type) and issubclass(field_type, msgspec.Struct):
        return _zero_valued_payload(field_type)
    if field_type is Path:
        # msgspec has no builtin str -> Path coercion (even under strict=False), so the
        # placeholder must already be a Path instance rather than a string.
        return Path("x")
    return _SCALAR_PLACEHOLDERS.get(field_type, "x")


def _placeholder_for_annotated(field_type: object) -> object:
    meta_args = get_args(field_type)
    base_type = meta_args[0]
    has_pattern_constraint = any(
        isinstance(arg, msgspec.Meta) and arg.pattern is not None for arg in meta_args[1:]
    )
    if base_type is str and has_pattern_constraint:
        return _VALID_UUID4_PLACEHOLDER
    return _placeholder_for_type(base_type)


def _placeholder_for_optional(field_type: object) -> object:
    non_none_args = [arg for arg in get_args(field_type) if arg is not type(None)]
    return _placeholder_for_type(non_none_args[0]) if non_none_args else None
