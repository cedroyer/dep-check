"""
Implementations of IDependenciesPrinter
"""
from dataclasses import asdict, dataclass
from pathlib import Path
from subprocess import check_output
from sys import stdin, stdout
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

import yaml
from jinja2 import Template

from dep_check.models import GlobalDependencies, Module, Rules, iter_all_modules
from dep_check.use_cases.build import IConfigurationWriter
from dep_check.use_cases.check import DependencyError, IReportPrinter
from dep_check.use_cases.draw_graph import IGraphDrawer
from dep_check.use_cases.interfaces import Configuration


@dataclass
class Format:
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    INFO = "\033[94m"


class YamlConfigurationIO(IConfigurationWriter):
    """
    Configuration yaml serialization.
    """

    def __init__(self, config_path: str):
        self.config_path = config_path

    def write(self, configuration: Configuration) -> None:
        if self.config_path == "-":
            stream = stdout
            stream.write("---\n\n")
            yaml.safe_dump(asdict(configuration), stream)
        else:
            with open(self.config_path, "w") as stream:
                stream.write("---\n\n")
                yaml.safe_dump(asdict(configuration), stream)

    def read(self) -> Configuration:
        if self.config_path == "-":
            return Configuration(**yaml.safe_load(stdin))

        with open(self.config_path) as stream:
            return Configuration(**yaml.safe_load(stream))


class ReportPrinter(IReportPrinter):
    """
    Print the report after checking the files
    """

    def _error(self, dep_errors: List[DependencyError]) -> None:
        """
        Log errors.
        """
        module_errors = {
            error.module: [e for e in dep_errors if e.module == error.module]
            for error in dep_errors
        }

        for module, errors in sorted(module_errors.items()):
            print("\nModule " + Format.BOLD + module + Format.ENDC + ":")
            print(" \u2022 " + Format.FAIL + "Unauthorized modules:" + Format.ENDC)

            for error in errors:
                print(f"\t- {error.dependency}")
            print("\n \u2022 " + Format.INFO + "Rules:" + Format.ENDC)

            for rule in errors[0].rules:
                print(f"\t- {rule}")

    def _warning(self, unused_rules: Rules) -> None:
        """
        Log warnings
        """
        previous_wildcard = ""
        for wildcard, rule in sorted(unused_rules):
            if wildcard != previous_wildcard:
                print("\nWildcard " + Format.BOLD + wildcard + Format.ENDC + ":")
                print(" \u2022 " + Format.WARNING + "Unused rules:" + Format.ENDC)
                previous_wildcard = wildcard
            print(f"\t- {wildcard}: {rule}")

    def print_report(
        self, errors: List[DependencyError], unused_rules: Rules, nb_files: int
    ) -> None:
        """
        Print report
        """
        if errors:
            print(
                "\n\n"
                + Format.BOLD
                + Format.FAIL
                + "IMPORT ERRORS".center(30)
                + Format.ENDC
            )
            self._error(errors)

        if unused_rules:
            print(
                "\n\n"
                + Format.BOLD
                + Format.WARNING
                + "UNUSED RULES".center(30)
                + Format.ENDC
            )
            self._warning(unused_rules)

        if not errors and not unused_rules:
            print(Format.OKGREEN + "\nEverything is in order! " + Format.ENDC)
        print(
            "\n * "
            + Format.FAIL
            + f"{len(errors)} errors"
            + Format.ENDC
            + " and "
            + Format.WARNING
            + f"{len(unused_rules)} warnings"
            + Format.ENDC
            + f" in {nb_files} files."
        )


def read_graph_config(conf_path: str) -> Dict:
    """
    Used to read the graph configuration file, and make it a Dictionary
    """
    with open(conf_path) as stream:
        return yaml.safe_load(stream)


@dataclass(init=False)
class Graph:
    """
    Dataclass representing the information to draw a graph
    """

    def __init__(self, svg_file_name: str, graph_config: Optional[Dict] = None):
        self.svg_file_name = svg_file_name
        self.graph_config = graph_config or {}
        self.dot_file_name: str = "/tmp/graph.dot"
        self.node_color: str = self.graph_config.get("node_color", "white")
        self.background_color: str = self.graph_config.get("bgcolor", "transparent")
        self.layers: dict = self.graph_config.get("layers", {})


class GraphDrawer(IGraphDrawer):
    """
    Write dot / svg files corresponding to the project dependencies
    """

    def __init__(self, graph: Graph):
        self.graph = graph
        self.header = Template(
            "digraph G {\n"
            "splines=true;\n"
            "node[shape=box fontname=Arial style=filled fillcolor={{nodecolor}}];\n"
            "bgcolor={{bgcolor}}\n\n\n"
        ).render(nodecolor=self.graph.node_color, bgcolor=self.graph.background_color)
        self.body = ""
        self.footer = "}\n"

        self.subgraph = Template(
            "subgraph cluster_{{subgraph_name}} {\n"
            "node [style=filled fillcolor={{color}}];\n"
            "{{list_modules}};\n"
            'label="{{subgraph_name}}";\n'
            "color={{color}};\n"
            "penwidth=2;\n"
            "}\n\n\n"
        )

    def _iter_layer_modules(
        self, global_dep: GlobalDependencies
    ) -> Iterator[Tuple[str, Iterable[Module]]]:

        for layer in self.graph.layers:
            yield layer, [
                m
                for m in iter_all_modules(global_dep)
                if m.startswith(tuple(self.graph.layers[layer]["modules"]))
            ]

    def _write_dot(self, global_dep: GlobalDependencies) -> bool:
        if not global_dep:
            return False

        for layer, modules in self._iter_layer_modules(global_dep):

            self.body += self.subgraph.render(
                subgraph_name=layer,
                color=self.graph.layers[layer].get("color", self.graph.node_color),
                list_modules=str(modules)[1:-1].replace("'", '"'),
            )

        for module, deps in global_dep.items():
            for dep in deps:
                self.body += '"{}" -> "{}"\n'.format(module, dep.main_import)

        with open(self.graph.dot_file_name, "w") as out:
            out.write(self.header)
            out.write(self.body)
            out.write(self.footer)

        return True

    def _write_svg(self) -> None:
        svg_string = check_output(["dot", "-Tsvg", self.graph.dot_file_name]).decode()
        if self.graph.svg_file_name == "-":
            stdout.write(svg_string)
        else:
            with open(self.graph.svg_file_name, "w") as stream:
                stream.write(svg_string)

    def write(self, global_dep: GlobalDependencies):
        if Path(self.graph.svg_file_name).suffix == ".dot":
            self.graph.dot_file_name = self.graph.svg_file_name
            self._write_dot(global_dep)
        else:
            if self._write_dot(global_dep):
                self._write_svg()
