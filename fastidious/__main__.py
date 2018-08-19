import sys
import inspect


from fastidious.bootstrap import ParserMeta, Parser, ParserMixin


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


def generate(klass):
    module, classname = klass.rsplit(".", 1)
    mod = __import__(module, fromlist=classname)
    template = getattr(mod, classname)
    print("import re")
    print("import six\n\n")
    print("class _Expr:")
    print("    def __init__(self, **kwargs):")
    print("        for k, v in kwargs.items():")
    print("            self.__dict__[k] = v\n\n")
    tmpl_decl, tmpl_body = inspect.getsource(template).split("\n", 1)
    if issubclass(template, Parser):
        parser = template
        tmpl_decl = "class %s(object):" % template.__name__
    else:
        attrs = {}
        for k, v in template.__dict__.items():
            if k.startswith("__") and k not in FASTIDIOUS_MAGIC:
                continue
            attrs[k] = v
        parser = ParserMeta("ThrowawayParser", (Parser,), attrs)
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
        code = rule.gen_code(template)
        for line in code.splitlines():
            if line.strip().startswith("# --"):
                continue
            print("    " + line)
        print("")

    return parser


if __name__ == "__main__":
    generate(sys.argv[1])
