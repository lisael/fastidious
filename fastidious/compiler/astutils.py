class VisitorBase(object):
    def visit(self, node):
        clsname = node.__class__.__name__
        method = "visit_%s" % clsname.lower()
        if hasattr(self, method):
            return getattr(self, method)(node)
        else:
            return self.generic_visit(node)

    def generic_visit(self, node):
        raise NotImplementedError(node)


class Visitor(VisitorBase):
    def generic_action(self, node):
        return node

    def generic_visit(self, node):
        for child in node._children():
            self.visit(child)
        return self.generic_action(node)
