"""
Define actions used in generated python fastidious parser classes.
"""

from six import string_types

from fastidious.compiler.astutils import Visitor
from .base import Action, ActionError


class SimpleAction(Action):

    class Visitor(Visitor):
        def __init__(self, parser_class):
            self.parser = parser_class
            self.labels = []

        def visit_labeledexpr(self, node):
            self.labels.append(node.name)
            self.visit(node.expr)

        def visit_rule(self, node):
            if isinstance(node.action, string_types):
                actionstr = node.action.strip()
                if actionstr.startswith("@"):
                    argname = actionstr[1:]
                    self.labels = []
                    self.visit(node.expr)
                    if argname not in self.labels:
                        raise ActionError(
                            "`%s`: label not found in rule `%s`" % (
                                argname, node.name))
                    node.action = _SimpleArgAction(argname)
                    return
                meth = getattr(self.parser, actionstr, None)
                if meth is None:
                    raise ActionError("Unknown method `%s`" % actionstr)
                node.action = _SimpleMethAction(
                    getattr(self.parser, actionstr))
                return
            if node.action is None:
                meth = getattr(self.parser, "on_%s" % node.name, None)
                if meth is not None:
                    node.action = _SimpleMethAction(meth)
                    return

    @classmethod
    def update_rules(cls, parser_class, rules):
        v = cls.Visitor(parser_class)
        for r in rules:
            v.visit(r)


class _SimpleArgAction(SimpleAction):
    def __init__(self, argname):
        self.argname = argname

    def __call__(self, parser, result, **args):
        return args[self.argname]


class _SimpleMethAction(SimpleAction):
    def __init__(self, meth):
        self.meth = meth

    def __call__(self, parser, result, **args):
        return self.meth(parser, result, **args)


class SimplePyAction(Action):

    class Visitor(Visitor):
        def visit_rule(self, node):
            if isinstance(node.action, _SimpleArgAction):
                node.action = _SimplePyArgAction(node.action.argname)
            if isinstance(node.action, _SimpleMethAction):
                node.action = _SimplePyMethAction(node.action.meth)

    @classmethod
    def update_rules(cls, parser_class, rules):
        SimpleAction.update_rules(parser_class, rules)
        v = cls.Visitor()
        for r in rules:
            v.visit(r)


class _SimplePyArgAction(_SimpleArgAction, SimplePyAction):
    def as_code(self):
        return "result = args['%s']" % self.argname


class _SimplePyMethAction(_SimpleMethAction, SimplePyAction):
    def as_code(self):
        return "result = self.%s(result, **args)" % self.meth.__name__
