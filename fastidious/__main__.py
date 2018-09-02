import sys
import argparse


from fastidious.parser import ParserMeta, Parser
from fastidious.compilers import gendot


FASTIDIOUS_MAGIC = ["__grammar__", "__default__"]


def load_class(klass):
    module, classname = klass.rsplit(".", 1)
    mod = __import__(module, fromlist=classname)
    template = getattr(mod, classname)
    return template


def parser_from_template(tmpl):
    if issubclass(tmpl, Parser):
        return tmpl
    else:
        attrs = {}
        for k, v in tmpl.__dict__.items():
            if k.startswith("__") and k not in FASTIDIOUS_MAGIC:
                continue
            attrs[k] = v
        return ParserMeta("ThrowawayParser", (Parser,), attrs)


def load_parser(klass):
    return parser_from_template(load_class(klass))


def generate(klass, executable):
    template = load_class(klass)
    if not hasattr(template.p_compiler, "gen_py_code"):
        raise NotImplementedError(
            "%s's compiler doesn't expose gen_py_code capability" % template)

    if executable:
        sys.stdout.write("#! /usr/bin/python\n")

    template.p_compiler.gen_py_code(template, sys.stdout)

    if executable:
        sys.stdout.write("""
import sys
res = Calculator.p_parse(" ".join(sys.argv[1:]))
print(res)
""")


def graph(klass):
    parser = load_parser(klass)
    dot = gendot(parser.__rules__[::-1])
    return dot


# pragma: nocover
if __name__ == "__main__":
    def _generate(args):
        generate(args.classname, args.executable)

    def _graph(args):
        print(graph(args.classname))

    # Global parser
    parser = argparse.ArgumentParser(
        prog="fastidious",
        description="Fastidious utils"
    )
    subparsers = parser.add_subparsers(title="subcommands")

    # generate subparser
    parser_generate = subparsers.add_parser(
        'generate',
        help="Generate a standalone parser")
    parser_generate.add_argument("--executable", "-e",
                                 default=False,
                                 action="store_true",
                                 help="Name of the parser class to generate")
    parser_generate.add_argument("classname",
                                 help="Name of the parser class to generate")
    parser_generate.set_defaults(func=_generate)

    # graph subparser
    parser_graph = subparsers.add_parser(
        'graph',
        help="generate a .dot representation of the parsing rules")
    parser_graph.add_argument('classname')
    parser_graph.set_defaults(func=_graph)

    # run the subcommand
    args = parser.parse_args()
    args.func(args)
