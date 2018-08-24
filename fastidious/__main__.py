import argparse

import inspect

from fastidious.bootstrap import ParserMeta, Parser, ParserMixin
from fastidious.gendot import ParserGraphVisitor


FASTIDIOUS_MAGIC = ["__grammar__", "__default__"]


def _get_expr_kwargs(e):
    kwargs = dict(
        is_syntaxic_terminal=e.is_syntaxic_terminal,
        expected=repr(e.expected)
    )
    if hasattr(e, "expr"):
        kwargs["expr"] = True
    if hasattr(e, "exprs"):
        kwargs["exprs"] = True
    return ", ".join(["%s=%s" % (k, v) for k, v in kwargs.items()])


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


def generate(klass):
    template = load_class(klass)
    print("import re")
    print("import six\n\n")
    print("class _Expr:")
    print("    def __init__(self, **kwargs):")
    print("        for k, v in kwargs.items():")
    print("            self.__dict__[k] = v\n\n")
    tmpl_decl, tmpl_body = inspect.getsource(template).split("\n", 1)
    parser = parser_from_template(template)
    if parser is template:
        tmpl_decl = "class %s(object):" % template.__name__
    print(tmpl_decl)
    print(tmpl_body)
    print("    __expressions__ = {")
    for k, v in parser.__expressions__.items():
        print("        %s: %s," % (k, "_Expr(%s)" % _get_expr_kwargs(v)))
    print("    }")
    print("    __default__ = '%s'" % parser.__default__)
    print("    class ParserError(Exception): pass")
    mixin_def, mixin_body = inspect.getsource(ParserMixin).split("\n", 1)
    mixin_body = mixin_body.replace("ParserError", "self.ParserError")
    print(mixin_body)

    for rule in parser.__rules__:
        code = rule.as_code(template)
        for line in code.splitlines():
            if line.strip().startswith("# --"):
                continue
            print("    " + line)
        print("")

    return parser


def graph(klass):
    parser = load_parser(klass)
    v = ParserGraphVisitor()
    dot = v.generate_dot(parser.__rules__[::-1])
    return dot


if __name__ == "__main__":
    def _generate(args):
        generate(args.classname)

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
