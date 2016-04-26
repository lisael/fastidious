from types import UnboundMethodType, MethodType



class ExprMixin(object):
    last_id = 0
    def _attach_to(self, parser):
        m = UnboundMethodType(self, None, parser)
        if hasattr(self, "name"):
            setattr(parser, self.name, m)
            if not self.action and hasattr(parser, "on_{}".format(self.name)):
                self.action = "on_{}".format(self.name)
        # self._attach_children_to(parser)
        return m

    def _attach_children_to(self, parser):
        for name, value in self.__dict__:
            if isinstance(value, ExprMixin):
                parser

    def visit(self, func):
        func(self)
        [child.visit(func) for child in getattr(self, "exprs", [])]
        if hasattr(self, "expr"):
            getattr(self, "expr").visit(func)

    def debug(self, parser, message):
        if parser._debug:
            print("{}{} `{}`".format(parser._debug_indent * " ",
                                     message, parser.input[
                                         parser.pos:parser.pos+5]))

    @property
    def id(self):
        if not hasattr(self, "_id"):
            self._id = self.last_id
            self.last_id += 1
        return self._id

    def _indent(self, code, space):
        ind = " " * space * 4
        return ind + ("\n" + ind).join([l for l in code.splitlines()])


class AtomicExpr(object):
    """Marker class for atomic expressions"""


class Expression(object):
    def __init__(self, rule, pos, argname=None):
        self.argname = argname
        self.pos = pos
        self.rule = rule

    def method_name(self):
        return "_expr_{}_{}".format(self.rule.name, self.pos)


class SeqExpr(ExprMixin):
    def __init__(self, *exprs):
        self.exprs = exprs

    def __call__(self, parser):
        self.debug(parser, "SeqExpr")
        parser._debug_indent += 1
        parser.p_save()
        results = []
        for expr in self.exprs:
            res = expr(parser)
            if res is False:
                parser.p_restore()
                parser._debug_indent -= 1
                return False
            results.append(res)
        parser._debug_indent -= 1
        parser.p_discard()
        return results

    def as_grammar(self, atomic=False):
        g = " ".join([e.as_grammar(True) for e in self.exprs])
        if atomic and len(self.exprs) > 1:
            return "( {} )".format(g)
        return g

    def as_code(self):
        def expressions():
            exprs = []
            for i, expr in enumerate(self.exprs):
                expr_code = """
{}
if result is False:
    self.p_restore()
else:
    results.append(result)
                    """.format(expr.as_code()).strip()
                exprs.append(self._indent(expr_code, i))
            return "\n".join(exprs)


        code = """
# {}
self.p_save()
results = []
{}
self.p_discard()
result = results
        """.format(
            self.as_grammar(),
            expressions()
        )
        return code.strip()


class ChoiceExpr(ExprMixin):
    def __init__(self, *exprs):
        self.exprs = exprs

    def __call__(self, parser):
        self.debug(parser, "ChoiceExpr")
        parser._debug_indent += 1
        parser.p_save()
        for expr in self.exprs:
            res = expr(parser)
            if res is not False:
                parser._debug_indent -= 1
                parser.p_discard()
                return res
        parser._debug_indent -= 1
        parser.p_restore()
        return False

    def as_grammar(self, atomic=False):
        g = " / ".join([e.as_grammar(True) for e in self.exprs])
        if atomic and len(self.exprs) > 1:
            return "( {} )".format(g)
        return g

    def as_code(self):
        def expressions():
            exprs = []
            if len(self.exprs):
                for i, expr in enumerate(self.exprs):
                    expr_code = """
{}
if result is False:
                    """.format(expr.as_code()).strip()
                    exprs.append(self._indent(expr_code, i ))
                exprs.append(self._indent("pass", i+1))
            return "\n".join(exprs)

        code = """
# {1}
self.p_save()
result = False
{0}
if result is False:
    self.p_restore()
else:
    self.p_discard()
        """.format(
            expressions(),
            self.as_grammar()
        )
        print code
        return code.strip()


class AnyCharExpr(ExprMixin, AtomicExpr):
    def __call__(self, parser):
        self.debug(parser, "AnyCharExpr")
        parser.p_save()
        n = parser.next()
        if n is not None:
            parser.p_discard()
            return n
        parser.p_restore()
        return False

    def as_grammar(self, atomic=False):
        return "."

    def as_code(self):
        code = """
# .
self.p_save()
n = self.next()
if n is not None:
    self.p_discard()
    result = n
else:
    self.p_restore()
    result = False
        """
        return code.strip()


class LiteralExpr(ExprMixin, AtomicExpr):
    def __init__(self, lit, ignore=False):
        self.lit = lit
        self.ignorecase = ignore

    def __call__(self, parser):
        self.debug(parser, "LiteralExpr `{}`".format(self.lit))
        if self.lit == "":
            return ""
        return parser.startswith(self.lit,
                                 self.ignorecase)

    def as_grammar(self, atomic=False):
        lit = self.lit.replace("\\", "\\\\")
        lit = lit.replace("\a", r"\a")
        lit = lit.replace("\b", r"\b")
        lit = lit.replace("\t", r"\t")
        lit = lit.replace("\n", r"\n")
        lit = lit.replace("\f", r"\f")
        lit = lit.replace("\r", r"\r")
        lit = lit.replace("\v", r"\v")
        if lit != '"':
            return '"{}"'.format(lit)
        return """'"'"""

    def as_code(self):
        if self.lit == "":
            return "result = ''"
        code = """
# {2}
result = self.startswith({0}, {1})
        """.format(
            repr(self.lit),
            repr(self.ignorecase),
            self.as_grammar()
        )
        return code.strip()


class CharRangeExpr(ExprMixin, AtomicExpr):
    def __init__(self, chars):
        self.chars = chars

    def __call__(self, parser):
        self.debug(parser, "CharRangeExpr `{}`".format(self.chars))
        parser.p_save()
        n = parser.next()
        if n is not None and n in self.chars:
            parser.p_discard()
            return n
        parser.p_restore()
        return False

    def as_grammar(self, atomic=False):
        chars = self.chars.replace("0123456789", "0-9")
        chars = chars.replace("\t", r"\t")
        chars = chars.replace("\n", r"\n")
        chars = chars.replace("\r", r"\r")
        chars = chars.replace("abcdefghijklmnopqrstuvwxyz", "a-z")
        chars = chars.replace("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "A-Z")
        chars = chars.replace("0123456789", "0-9")
        return "[{}]".format(chars)

    def as_code(self):
        code = """
# {0}
self.p_save()
n = self.next()
if n is not None and n in {1}:
    self.p_discard()
    result = n
else:
    self.p_restore()
    result = False
        """.format(
                self.as_grammar(),
                repr(self.chars),
            )
        return code.strip()


class OneOrMoreExpr(ExprMixin):
    def __init__(self, expr):
        self.expr = expr

    def __call__(self, parser):
        self.debug(parser, "OneOrMoreExpr")
        parser._debug_indent += 1
        parser.p_save()
        results = []
        while 42:
            r = self.expr(parser)
            if r is not False:
                results.append(r)
            else:
                break
        parser._debug_indent -= 1
        if not results:
            parser.p_restore()
            return False
        if isinstance(self.expr, (CharRangeExpr, AnyCharExpr)):
            results = "".join(results)
        parser.p_discard()
        return results

    def as_grammar(self, atomic=False):
        return "{}+".format(self.expr.as_grammar(True))


class ZeroOrMoreExpr(ExprMixin):
    def __init__(self, expr):
        self.expr = expr

    def __call__(self, parser):
        self.debug(parser, "ZeroOrMoreExpr")
        parser._debug_indent += 1
        results = []
        while 42:
            r = self.expr(parser)
            if r is not False:
                results.append(r)
            else:
                break
        if isinstance(self.expr, (CharRangeExpr, AnyCharExpr)):
            results = "".join(results)
        parser._debug_indent -= 1
        return results

    def as_grammar(self, atomic=False):
        return "{}*".format(self.expr.as_grammar(True))


class RuleExpr(ExprMixin, AtomicExpr):
    def __init__(self, rulename):
        self.rulename = rulename

    def __call__(self, parser):
        self.debug(parser, "RuleExpr `{}`".format(self.rulename))
        rule_method = getattr(parser, self.rulename, None)
        if rule_method is None:
            parser.parse_error("Rule `%s` not found" % self.rulename)
        return rule_method()

    def as_grammar(self, atomic=False):
        return self.rulename

    def as_code(self):
        return "result = self.{}".format(self.rulename)


class MaybeExpr(ExprMixin):
    def __init__(self, expr=None):
        self.expr = expr

    def __call__(self, parser):
        self.debug(parser, "MaybeExpr")
        parser._debug_indent += 1
        result = self.expr(parser)
        parser._debug_indent -= 1
        if result is False:
            return ""
        return result

    def as_grammar(self, atomic=False):
        return "{}?".format(self.expr.as_grammar(True))


class FollowedBy(ExprMixin):
    def __init__(self, expr=None):
        self.expr = expr

    def __call__(self, parser):
        self.debug(parser, "FollowedBy")
        parser._debug_indent += 1
        parser.p_save()
        result = self.expr(parser) is not False
        parser.p_restore()
        parser._debug_indent -= 1
        return result

    def as_grammar(self, atomic=False):
        return "&{}".format(self.expr.as_grammar(True))


class NotFollowedBy(ExprMixin):
    def __init__(self, expr=None):
        self.expr = expr

    def __call__(self, parser):
        self.debug(parser, "NotFollowedBy")
        parser._debug_indent += 1
        parser.p_save()
        result = self.expr(parser) is False and ""
        parser.p_restore()
        parser._debug_indent -= 1
        return result

    def as_grammar(self, atomic=False):
        return "!{}".format(self.expr.as_grammar(True))

    def as_code(self):
        code = """
# {1}
self.p_save()
{0}
result = result is Falsa and ""
self.p_restore()
        """.format(
            self.expr.as_code(),
            self.as_grammar(),
        )


class LabeledExpr(ExprMixin, AtomicExpr):
    def __init__(self, name, expr, rulename=None):
        self.name = name
        self.expr = expr
        self.rulename = rulename

    def __call__(self, parser):
        self.debug(parser, "LabeledExpr `{}`".format(self.name))
        parser._debug_indent += 1
        rule = getattr(parser, self.rulename)
        result = self.expr(parser)
        rule.args_stack[-1][self.name] = result
        parser._debug_indent -= 1
        return result

    def as_grammar(self, atomic=False):
        return "{}:{}".format(self.name, self.expr.as_grammar(True))

    def as_code(self):
        code = """
# {}
{}
self.args_stack[{}][-1][{}] = result
        """.format(
            self.as_grammar(),
            self.expr.as_code(),
            repr(self.rulename),
            repr(self.name)
        )
        return code.strip()


class Rule(ExprMixin):
    def __init__(self, name, expr, action=None):
        self.name = name
        self.expr = expr
        self.action = action
        self.args_stack = []

    def __call__(self, parser):
        self.args_stack.append({})
        result = self.expr(parser)
        args = self.args_stack.pop()
        if result is not False:
            if self.action is not None:
                if isinstance(self.action, basestring):
                    if self.action.startswith("@"):
                        return args.get(self.action[1:])
                    action = getattr(parser, self.action)
                    return action(result, **args)
                return self.action(parser, result, **args)
            else:
                return result
        return False

    def _action(self):
        if self.action is not None:
            if isinstance(self.action, basestring):
                if self.action.startswith("@"):
                    return "return args[{}]".format(self.action[1:])
                return "return self.{}(result, **args)".format(
                    self.action
                )
        else:
            return "return result"

    def as_method(self, parser):

        code = """
def new_method(self):
    # {3}
    self.args_stack.setdefault("{0}",[]).append(dict())
{1}
    args = self.args_stack["{0}"].pop()
    if result is not None:
        {2}
    return result
        """.format(self.name,
                   self._indent(self.expr.as_code(), 1),
                   self._action(),
                   self.as_grammar()
                   )
        code = code.strip()
        print code
        exec(code)
        code = code.replace("new_method", self.name)
        new_method._code = code  # noqa
        if isinstance(parser, type):
            meth = UnboundMethodType(new_method, None, parser)  # noqa
        else:
            meth = MethodType(new_method, parser, type(parser))  # noqa
        setattr(parser, self.name, meth)

    def as_grammar(self):
        if self.action == "on_{}".format(self.name):
            action = ""
        elif isinstance(self.action, basestring):
            action = " {%s}" % self.action
        else:
            action = ""
        return "{} <- {}{}".format(
            self.name,
            self.expr.as_grammar(),
            action
        )
