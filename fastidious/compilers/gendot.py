import six

from fastidious.expressions import (Not, ZeroOrMoreExpr, LabeledExpr, SeqExpr,
                                    ChoiceExpr, MaybeExpr, OneOrMoreExpr,
                                    ExprProxi)
from fastidious.compiler.astutils import Visitor

from fastidious.compiler.action.base import Action


class LinkError(Exception):
    pass


class ParserGraphVisitor(Visitor):
    def __init__(self, vertical=False):
        self.content = six.StringIO()
        rankdir = "TB" if vertical else "LR"
        self.content.write("""digraph astgraph {
  node [fontsize=12, fontname="Courier", height=.1];
  ranksep=.3;
  rankdir=%s;
  edge [arrowsize=.5, fontname="Courier"]
  """ % rankdir)
        self.current_id = 0
        self.nodes = {}
        self.bypasses = {}
        self.missing_bypasses = set()
        self.links = set()

    def node_name(self, node):
        if node not in self.nodes:
            self.current_id += 1
            self.nodes[node] = self.current_id
        return "node_%s" % self.nodes[node]

    def cluster_name(self, node):
        if node not in self.nodes:
            self.current_id += 1
            self.nodes[node] = self.current_id
        return "cluster_%s" % self.nodes[node]

    def link(self, node1, node2, label=None):
        if isinstance(node1, ExprProxi):
            node1 = node1.proxied
            return self.link(node1, node2, label)
        elif isinstance(node2, ExprProxi):
            node2 = node2.expr
            return self.link(node1, node2, label)

        elif isinstance(node1, (LabeledExpr, Not, OneOrMoreExpr)):
            node1 = node1.expr
            return self.link(node1, node2, label)
        elif isinstance(node2, (LabeledExpr, Not, OneOrMoreExpr)):
            node2 = node2.expr
            return self.link(node1, node2, label)

        elif isinstance(node1, ZeroOrMoreExpr):
            node1 = node1.expr
            try:
                self.link(self.bypasses[node1], node2)
            except KeyError:
                self.missing_bypasses.add((node1, node2, None))
            return self.link(node1, node2, label)
        elif isinstance(node1, MaybeExpr):
            node1 = node1.expr
            try:
                self.link(self.bypasses[node1], node2, label="?")
            except KeyError:
                self.missing_bypasses.add((node1, node2, "?"))
            return self.link(node1, node2, label)
        elif isinstance(node2, (MaybeExpr, ZeroOrMoreExpr)):
            node2 = node2.expr
            self.bypasses[node2] = node1
            return self.link(node1, node2, label)

        elif isinstance(node1, SeqExpr):
            node1 = node1.exprs[-1]
            return self.link(node1, node2, label)
        elif isinstance(node2, SeqExpr):
            node2 = node2.exprs[0]
            return self.link(node1, node2, label)

        elif isinstance(node1, ChoiceExpr):
            for n in node1.exprs:
                self.link(n, node2, label)
            return
        elif isinstance(node2, ChoiceExpr):
            for n in node2.exprs:
                self.link(node1, n, label)
            return

        if node1 not in self.nodes:
            raise LinkError(node1)
        if node2 not in self.nodes:
            raise LinkError(node2)
        if (node1, node2, label) in self.links:
            return
        if label is not None:
            labelstr = ' [label="%s"]' % label
        else:
            labelstr = ""
        self.content.write(
            "  %s -> %s%s\n" % (self.node_name(node1),
                                self.node_name(node2), labelstr))
        self.links.add((node1, node2, label))

    def visit_rule(self, node):
        s = '  %s [label="%s", shape="rect", style=bold]\n' % (
            self.node_name(node), node.name)
        self.content.write(s)
        self.visit(node.expr)
        self.link(node, node.expr)
        if isinstance(node.action, Action):
            label = node.action.__string__()
        else:
            label = node.action if node.action else " "
        dummy = object()
        s = ' %s [label="%s", shape="box"]\n' % (self.node_name(dummy), label)
        self.content.write(s)
        self.link(node.expr, dummy)
        for n1, n2, label in self.missing_bypasses:
            self.link(self.bypasses[n1], n2, label)
        self.missing_bypasses = set()

    def visit_seqexpr(self, node):
        lastnode = None
        for expr in node.exprs:
            self.visit(expr)
            if lastnode is not None:
                self.link(lastnode, expr)
            lastnode = expr

    def visit_choiceexpr(self, node):
        for e in node.exprs:
            self.visit(e)

    def visit_labeledexpr(self, node):
        self.content.write("""  subgraph %s {
    label="%s";
    color=grey;
""" % (self.cluster_name(node), node.name))
        self.visit(node.expr)
        self.content.write("  }\n")

    def visit_oneormoreexpr(self, node):
        self.visit(node.expr)
        self.link(node.expr, node.expr, "+")

    def visit_zeroormoreexpr(self, node):
        self.visit(node.expr)
        self.link(node.expr, node.expr, "*")

    def generic_visit(self, node):
        label = node.as_grammar()
        label = label.replace("\\'", "'")
        label = label.replace("\\", "\\\\")
        label = label.replace('"', '\\"')
        s = '  %s [label="%s"]\n' % (self.node_name(node), label)
        self.content.write(s)

    def visit_not(self, node):
        self.content.write("""  subgraph %s {
    label="!";
    style="dashed";
""" % (self.cluster_name(node), ))
        self.visit(node.expr)
        self.content.write("  }\n")

    def visit_maybeexpr(self, node):
        self.visit(node.expr)

    def generate_dot(self, nodes):
        for node in nodes[::-1]:
            self.visit(node)
        self.content.write("}\n")
        return self.content.getvalue()


class ParserGraphVisitorExpander(ParserGraphVisitor):
    def __init__(self, start_node):
        super(ParserGraphVisitorExpander, self).__init__(vertical=True)
        self.start_node = start_node


def gendot(nodes, expand_nodes=False, start_node=None):
    if not expand_nodes:
        v = ParserGraphVisitor()
        return v.generate_dot(nodes)
    else:
        return ParserGraphVisitorExpander(start_node).generate_dot(nodes)
