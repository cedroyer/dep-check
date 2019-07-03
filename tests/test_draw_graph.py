"""
Test graph use case
"""
from typing import Iterator
from unittest.mock import Mock, patch

from dep_check.infra.io import Graph, GraphDrawer
from dep_check.models import Module, SourceFile
from dep_check.use_cases.draw_graph import DrawGraphUC, _fold_dep

from .fakefile import GLOBAL_DEPENDENCIES, SIMPLE_FILE


def test_empty_source_files() -> None:
    """
    Test result with no source files given.
    """
    # Given
    source_files: Iterator[SourceFile] = iter([])
    drawer = Mock()
    use_case = DrawGraphUC(drawer, source_files)

    # When
    use_case.run()

    # Then
    drawer.write.assert_called_with({})


def test_nominal(get_source_file_iterator) -> None:
    """
    Test result with a set source files.
    """
    # Given
    source_files = get_source_file_iterator
    drawer = Mock()
    use_case = DrawGraphUC(drawer, source_files)

    # When
    use_case.run()

    # Then
    drawer.write.assert_called()  # type: ignore
    global_dep = drawer.write.call_args[0][0]

    assert global_dep == {
        "simple_module": set(
            (Module("module"), Module("module.inside.module"), Module("amodule"))
        ),
        "amodule.local_module": set(
            (
                Module("module"),
                Module("module.inside.module"),
                Module("amodule"),
                Module("amodule.inside"),
            )
        ),
        "amodule.std_module": set((Module("module"), Module("module.inside.module"))),
    }


def test_dot() -> None:
    """
    Test that the dot file is well generated
    """
    # Given
    source_files: Iterator[SourceFile] = iter([SIMPLE_FILE])
    drawer = GraphDrawer(Graph("graph.svg"))
    use_case = DrawGraphUC(drawer, source_files)

    # When
    use_case.run()

    # Then
    with open("/tmp/graph.dot") as dot:
        lines = sorted(dot.readlines())

    assert lines == sorted(
        [
            "digraph G {\n",
            "splines=true;\n",
            "node[shape=box fontname=Arial style=filled fillcolor={}];\n".format(
                drawer.graph.node_color
            ),
            "bgcolor={}\n".format(drawer.graph.background_color),
            '"simple_module" -> "module"\n',
            '"simple_module" -> "module.inside.module"\n',
            '"simple_module" -> "amodule"\n',
            "}\n",
        ]
    )


@patch.object(GraphDrawer, "_write_svg")
def test_not_svg_with_dot(mock_method) -> None:
    """
    Test that no svg file is created when .dot in argument
    """
    # Given
    source_files: Iterator[SourceFile] = iter([SIMPLE_FILE])
    drawer = GraphDrawer(Graph("graph.dot"))
    use_case = DrawGraphUC(drawer, source_files)

    # When
    use_case.run()

    # Then
    mock_method.assert_not_called()


def test_fold_dep_empty_dict() -> None:
    """
    Test result of _fold_dep function with an empty dictionary
    """
    # Given
    global_dep = {}
    fold_module = Module("module")

    # When
    global_dep = _fold_dep(global_dep, fold_module)

    # Then
    global_dep = {}


def test_fold_dep_empty_module() -> None:
    """
    Test result of _fold_dep function with an empty fold module
    """
    # Given
    global_dep = GLOBAL_DEPENDENCIES
    fold_module = Module("")

    # When
    global_dep = _fold_dep(global_dep, fold_module)

    # Then
    global_dep = GLOBAL_DEPENDENCIES


def test_fold_dep() -> None:
    """
    Test result of _fold_dep function with an empty fold module
    """
    # Given
    global_dep = GLOBAL_DEPENDENCIES
    fold_module = Module("amodule")

    # When
    global_dep = _fold_dep(global_dep, fold_module)

    # Then
    assert global_dep == {
        "simple_module": set(
            (Module("module"), Module("module.inside.module"), Module("amodule"))
        ),
        "amodule": set(
            (Module("module"), Module("module.inside.module"), Module("amodule"))
        ),
    }


def test_fold_module(get_source_file_iterator) -> None:
    """
    Test result with a set source files and a module to fold.
    """
    # Given
    source_files = get_source_file_iterator
    conf_graph = {"fold_modules": ["amodule"]}
    drawer = Mock()
    use_case = DrawGraphUC(drawer, source_files, conf_graph)

    # When
    use_case.run()

    # Then
    drawer.write.assert_called()  # type: ignore
    global_dep = drawer.write.call_args[0][0]

    assert global_dep == {
        "simple_module": set(
            (Module("module"), Module("module.inside.module"), Module("amodule"))
        ),
        "amodule": set(
            (Module("module"), Module("module.inside.module"), Module("amodule"))
        ),
    }
