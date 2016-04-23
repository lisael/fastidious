from types import UnboundMethodType


class ExprMixin(object):
    def _attach_to(self, parser):
        m = UnboundMethodType(self, None, parser)
        if hasattr(self, "name"):
            setattr(parser, self.name, m)
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
                                     message, parser.input[parser.pos:parser.pos+5]))


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
        savepoint = parser.save()
        results = []
        for expr in self.exprs:
            res = expr(parser)
            if res is False:
                parser.restore(savepoint)
                parser._debug_indent -= 1
                return False
            results.append(res)
        parser._debug_indent -= 1
        return results

    def as_grammar(self, atomic=False):
        g = " ".join([e.as_grammar(True) for e in self.exprs])
        if atomic and len(self.exprs) > 1:
            return "( {} )".format(g)
        return g


class ChoiceExpr(ExprMixin):
    def __init__(self, *exprs):
        self.exprs = exprs

    def __call__(self, parser):
        self.debug(parser, "ChoiceExpr")
        parser._debug_indent += 1
        savepoint = parser.save()
        for expr in self.exprs:
            res = expr(parser)
            if res is not False:
                parser._debug_indent -= 1
                return res
            parser.restore(savepoint)
        parser._debug_indent -= 1
        return False

    def as_grammar(self, atomic=False):
        g = " / ".join([e.as_grammar(True) for e in self.exprs])
        if atomic and len(self.exprs) > 1:
            return "( {} )".format(g)
        return g


class AnyCharExpr(ExprMixin, AtomicExpr):
    def __call__(self, parser):
        self.debug(parser, "AnyCharExpr")
        sp = parser.save()
        n = parser.next()
        if n is not None:
            return n
        parser.restore(sp)
        return False

    def as_grammar(self, atomic=False):
        return "."


class LiteralExpr(ExprMixin, AtomicExpr):
    def __init__(self, lit, ignore=False):
        self.lit = lit
        self.ignorecase = ignore

    def __call__(self, parser):
        self.debug(parser, "LiteralExpr `{}`".format(self.lit))
        return parser.startswith(self.lit,
                                 self.ignorecase) and self.lit or False

    def as_grammar(self, atomic=False):
        lit = self.lit.replace("\n", r"\n")
        lit = lit.replace("\t", r"\t")
        return '"{}"'.format(lit)


class CharRangeExpr(ExprMixin, AtomicExpr):
    def __init__(self, chars):
        self.chars = chars

    def __call__(self, parser):
        self.debug(parser, "CharRangeExpr `{}`".format(self.chars))
        sp = parser.save()
        n = parser.next()
        if n is not None and n in self.chars:
            return n
        parser.restore(sp)
        return False

    def as_grammar(self, atomic=False):
        chars = self.chars.replace("0123456789", "0-9")
        chars = chars.replace("\t", r"\t")
        chars = chars.replace("\n", r"\n")
        chars = chars.replace("\r", r"\r")
        chars = chars.replace("abcdefghijklmnopqrstuvwxyz", "a-z")
        chars = chars.replace("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "A-Z")
        return "[{}]".format(chars)


class OneOrMoreExpr(ExprMixin):
    def __init__(self, expr):
        self.expr = expr

    def __call__(self, parser):
        self.debug(parser, "OneOrMoreExpr")
        parser._debug_indent += 1
        sp = parser.save()
        results = []
        while 42:
            r = self.expr(parser)
            if r is not False:
                results.append(r)
            else:
                break
        parser._debug_indent -= 1
        if not results:
            parser.restore(sp)
            return False
        if isinstance(self.expr, (CharRangeExpr, AnyCharExpr)):
            results = "".join(results)
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
        savepoint = parser.save()
        result = self.expr(parser) is not False
        parser.restore(savepoint)
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
        savepoint = parser.save()
        result = self.expr(parser) is False and ""
        parser.restore(savepoint)
        parser._debug_indent -= 1
        return result

    def as_grammar(self, atomic=False):
        return "!{}".format(self.expr.as_grammar(True))


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

    def as_grammar(self):
        return "{} <- {}".format(self.name, self.expr.as_grammar())
