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


class RuleVisitor(Visitor):
    def generic_action(self, node):
        pass

    def generic_visit(self, node):
        self.generic_action(node)
        if hasattr(node, "expr"):
            self.visit(node.expr)
        if hasattr(node, "exprs"):
            for e in node.exprs:
                self.visit(e)
