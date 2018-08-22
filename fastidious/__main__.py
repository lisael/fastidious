import sys
import argparse

import inspect

import six


from fastidious.bootstrap import ParserMeta, Parser, ParserMixin
from fastidious.expressions import (Not, ZeroOrMoreExpr, RuleExpr, LabeledExpr, SeqExpr, ChoiceExpr, MaybeExpr, OneOrMoreExpr)


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


class Visitor(object):
    def visit(self, node):
        clsname = node.__class__.__name__
        method = "visit_%s" % clsname.lower()
        if hasattr(self, method):
            getattr(self, method)(node)
        else:
            self.generic_visit(node)

    def generic_visit(self, node):
        raise NotImplementedError(node)


class ParserGraphVisitor(Visitor):
    def __init__(self):
        self.content = six.StringIO()
        self.content.write("""digraph astgraph {
  node [fontsize=12, fontname="Courier", height=.1];
  ranksep=.3;
  rankdir=LR;
  edge [arrowsize=.5, fontname="Courier"]
  """)
        self.current_id = 0
        self.nodes = {}
        self.bypasses = {}
        self.missing_bypasses = []

    def node_name(self, node):
        if node not in self.nodes:
            self.current_id += 1
            self.nodes[node] = self.current_id
        return "node%s" % self.nodes[node]

    def link(self, node1, node2, label=None):
        if isinstance(node1, LabeledExpr):
            node1 = node1.expr
            return self.link(node1, node2, label)
        if isinstance(node2, LabeledExpr):
            node2 = node2.expr
            return self.link(node1, node2, label)
        if isinstance(node1, Not):
            node1 = node1.expr
            return self.link(node1, node2, label)
        if isinstance(node2, Not):
            node2 = node2.expr
            return self.link(node1, node2, "!")
        if isinstance(node1, OneOrMoreExpr):
            node1 = node1.expr
            return self.link(node1, node2, label)
        if isinstance(node2, OneOrMoreExpr):
            node2 = node2.expr
            return self.link(node1, node2, label)
        if isinstance(node1, ZeroOrMoreExpr):
            node1 = node1.expr
            self.link(self.bypasses[node1], node2)
            return self.link(node1, node2, label)
        if isinstance(node2, ZeroOrMoreExpr):
            node2 = node2.expr
            self.bypasses[node2] = node1
            return self.link(node1, node2, label)
        if isinstance(node1, SeqExpr):
            node1 = node1.exprs[-1]
            return self.link(node1, node2, label)
        if isinstance(node2, SeqExpr):
            node2 = node2.exprs[0]
            return self.link(node1, node2, label)
        if isinstance(node1, ChoiceExpr):
            for n in node1.exprs:
                self.link(n, node2, label)
            return
        if isinstance(node2, ChoiceExpr):
            for n in node2.exprs:
                self.link(node1, n, label)
            return
        if isinstance(node1, MaybeExpr):
            node1 = node1.expr
            try:
                self.link(self.bypasses[node1], node2, label="?")
            except KeyError:
                self.missing_bypasses.append((node1, node2, "?"))
            return self.link(node1, node2, label)
        if isinstance(node2, MaybeExpr):
            node2 = node2.expr
            self.bypasses[node2] = node1
            return self.link(node1, node2, label)
        if node1 not in self.nodes:
            raise Exception(node1)
        if node2 not in self.nodes:
            raise Exception(node2)
        if label is not None:
            label = ' [label="%s"]' % label
        else:
            label = ""
        self.content.write(
                "  %s -> %s%s\n" % (self.node_name(node1), self.node_name(node2), label))

    def visit_rule(self, node):
        s = '  %s [label="%s", shape="doublecircle"]\n' % (self.node_name(node), node.name)
        self.content.write(s)
        self.visit(node.expr)
        self.link(node, node.expr)
        label = node.action if node.action else " "
        dummy = object()
        s = ' %s [label="%s", shape="box"]\n' % (self.node_name(dummy), label)
        self.content.write(s)
        self.link(node.expr, dummy)
        for n1, n2, label in self.missing_bypasses:
            self.link(self.bypasses[n1], n2, "?")
        self.missing_bypasses = []


    def visit_seqexpr(self, node):
        lastnode = None
        for i, expr in enumerate(node.exprs):
            self.visit(expr)
            if lastnode is not None:
                self.link(lastnode, expr)
            lastnode = expr

    def visit_ruleexpr(self, node):
        return self.add_generic_node(node)
        s = '  %s [label="%s"]\n' % (self.node_name(node), node.rulename)
        self.content.write(s)

    def visit_choiceexpr(self, node):
        for e in node.exprs:
            self.visit(e)

    def visit_labeledexpr(self, node):
        self.visit(node.expr)

    def visit_oneormoreexpr(self, node):
        self.visit(node.expr)
        self.link(node.expr, node.expr, "+")

    def visit_zeroormoreexpr(self, node):
        self.visit(node.expr)
        self.link(node.expr, node.expr, "*")

    def add_generic_node(self, node):
        label = node.as_grammar()
        label = label.replace("\\'", "'")
        label = label.replace("\\", "\\\\")
        label = label.replace('"', '\\"')
        s = '  %s [label="%s"]\n' % (self.node_name(node), label)
        self.content.write(s)

    def visit_charrangeexpr(self, node):
        return self.add_generic_node(node)
        s = '  %s [label="%s"]\n' % (self.node_name(node), node.as_grammar().replace("\\", "\\\\"))
        self.content.write(s)

    def visit_literalexpr(self, node):
        return self.add_generic_node(node)
        s = '  %s [label="\'%s\'"]\n' % (self.node_name(node), node.lit)
        self.content.write(s)

    def visit_anycharexpr(self, node):
        return self.add_generic_node(node)
        s = '  %s [label="."]\n' % self.node_name(node)
        self.content.write(s)

    def visit_not(self, node):
        self.visit(node.expr)

    def visit_maybeexpr(self, node):
        self.visit(node.expr)

    def generate_dot(self, nodes):
        for node in nodes:
            self.visit(node)
        self.content.write("}\n")
        return self.content.getvalue()


def graph(klass):
    parser = load_parser(klass)
    v = ParserGraphVisitor()
    dot = v.generate_dot(parser.__rules__[:9][::-1])
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
