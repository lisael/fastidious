import re

import six


if six.PY2:
    from types import UnboundMethodType


class ExprMixin(object):
    last_id = 0

    def __init__(self, *args, **kwargs):
        self.is_syntaxic_terminal = kwargs.pop("terminal", False)
        self.report_errors = True

    @property
    def expected(self):
        return [self.as_grammar()]

    def debug(self, parser, message):
        if parser.__debug___:
            print("{}{} `{}`".format(parser._debug_indent * " ",
                                     message, parser.input[
                                         parser.pos:parser.pos + 5]))

    def disable_errors(self):
        self.report_errors = False
        for child in getattr(self, "exprs", []):
            child.disable_errors()
        if hasattr(self, "expr"):
            self.expr.disable_errors()

    @property
    def id(self):
        if not hasattr(self, "_id"):
            self._id = ExprMixin.last_id
            ExprMixin.last_id += 1
        return self._id

    def get_children(self):
        if hasattr(self, "expr"):
            return [self.expr]
        if hasattr(self, "exprs"):
            return self.exprs
        return []

    def set_children(self, children):
        if hasattr(self, "expr"):
            self.expr = children[0]
        if hasattr(self, "exprs"):
            self.exprs = children


class AtomicExpr(object):
    """Marker class for atomic expressions"""


class RegexExpr(ExprMixin):
    def __init__(self, regexp, flags=None):
        ExprMixin.__init__(self, regexp, flags=flags)
        self.lit = regexp
        self.flags = flags or None
        self.re = re.compile(self._full_regexp())

    def __call__(self, parser):
        self.debug(parser, "RegexExpr `{}`".format(self.lit))
        m = self.re.match(parser.p_suffix())
        if m is None:
            parser.p_nomatch(self.id)
            return parser.NoMatch
        end = m.end()
        result = parser.p_suffix(end)
        parser.pos += end
        return result

    def as_grammar(self, atomic=False):
        return "~{}{}".format(repr(self.lit), self.flags or "")

    def _full_regexp(self):
        if self.flags is not None:
            return "(?{}){}".format(self.flags, self.lit)
        return self.lit


class SeqExpr(ExprMixin):
    def __init__(self, *exprs, **kwargs):
        ExprMixin.__init__(self, *exprs, **kwargs)
        self.exprs = exprs

    def __call__(self, parser):
        self.debug(parser, "SeqExpr")
        parser._debug_indent += 1
        parser.p_save()
        results = []
        for expr in self.exprs:
            res = expr(parser)
            if res is parser.NoMatch:
                parser.p_restore()
                parser.p_nomatch(self.id)
                parser._debug_indent -= 1
                return parser.NoMatch
            results.append(res)
        parser._debug_indent -= 1
        parser.p_discard()
        return results

    def as_grammar(self, atomic=False):
        g = " ".join([e.as_grammar(True) for e in self.exprs])
        if atomic and len(self.exprs) > 1:
            return "( {} )".format(g)
        return g


class ChoiceExpr(ExprMixin):
    def __init__(self, *exprs, **kwargs):
        ExprMixin.__init__(self, *exprs, **kwargs)
        self.exprs = exprs

    def __call__(self, parser):
        self.debug(parser, "ChoiceExpr")
        parser._debug_indent += 1
        parser.p_save()
        for expr in self.exprs:
            res = expr(parser)
            if res is not parser.NoMatch:
                parser._debug_indent -= 1
                parser.p_discard()
                return res
        parser._debug_indent -= 1
        parser.p_restore()
        parser.p_nomatch(self.id)
        return parser.NoMatch

    def as_grammar(self, atomic=False):
        g = " / ".join([e.as_grammar(True) for e in self.exprs])
        if atomic and len(self.exprs) > 1:
            return "( {} )".format(g)
        return g


class AnyCharExpr(ExprMixin, AtomicExpr):
    def __call__(self, parser):
        self.debug(parser, "AnyCharExpr")
        parser.p_save()
        n = parser.p_next()
        if n is not None:
            parser.p_discard()
            return n
        parser.p_restore()
        parser.p_nomatch(self.id)
        return parser.NoMatch

    def as_grammar(self, atomic=False):
        return "."


class LiteralExpr(ExprMixin, AtomicExpr):
    def __init__(self, lit, ignore=False, terminal=False):
        ExprMixin.__init__(self, lit, ignore=ignore, terminal=terminal)
        self.lit = lit
        self.ignorecase = ignore

    def __call__(self, parser):
        self.debug(parser, "LiteralExpr `{}`".format(self.lit))
        if self.lit == "":
            return ""
        result = parser.p_startswith(self.lit,
                                     self.ignorecase)
        if not result:
            parser.p_nomatch(self.id)
            return parser.NoMatch
        return result

    def as_grammar(self, atomic=False):
        lit = self.lit.replace("\\", "\\\\")
        lit = lit.replace("\a", r"\a")
        lit = lit.replace("\b", r"\b")
        lit = lit.replace("\t", r"\t")
        lit = lit.replace("\n", r"\n")
        lit = lit.replace("\f", r"\f")
        lit = lit.replace("\r", r"\r")
        lit = lit.replace("\v", r"\v")
        ignore = self.ignorecase and "i" or ""
        if lit != '"':
            return '"{}"{}'.format(lit, ignore)
        return """'"'%s""" % ignore


class CharRangeExpr(ExprMixin, AtomicExpr):
    def __init__(self, chars, terminal=False):
        ExprMixin.__init__(self, chars, terminal=terminal)
        self.chars = chars

    def __call__(self, parser):
        self.debug(parser, "CharRangeExpr `{}`".format(self.chars))
        parser.p_save()
        n = parser.p_next()
        if n is not None and n in self.chars:
            parser.p_discard()
            return n
        parser.p_restore()
        parser.p_nomatch(self.id)
        return parser.NoMatch

    def as_grammar(self, atomic=False):
        chars = self.chars.replace("0123456789", "0-9")
        chars = chars.replace("\t", r"\t")
        chars = chars.replace("\n", r"\n")
        chars = chars.replace("\r", r"\r")
        chars = chars.replace("abcdefghijklmnopqrstuvwxyz", "a-z")
        chars = chars.replace("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "A-Z")
        chars = chars.replace("0123456789", "0-9")
        return "[{}]".format(chars)


class OneOrMoreExpr(ExprMixin):
    def __init__(self, expr):
        ExprMixin.__init__(self, expr)
        self.expr = expr

    def __call__(self, parser):
        self.debug(parser, "OneOrMoreExpr")
        parser._debug_indent += 1
        parser.p_save()
        results = []
        while 42:
            r = self.expr(parser)
            if r is not parser.NoMatch:
                results.append(r)
            else:
                break
        parser._debug_indent -= 1
        if not results:
            parser.p_restore()
            parser.p_nomatch(self.id)
            return parser.NoMatch
        if isinstance(self.expr, (CharRangeExpr, AnyCharExpr)):
            results = "".join(results)
        parser.p_discard()
        return results

    def as_grammar(self, atomic=False):
        return "{}+".format(self.expr.as_grammar(True))


class ZeroOrMoreExpr(ExprMixin):
    def __init__(self, expr):
        ExprMixin.__init__(self, expr)
        self.expr = expr
        self.expr.disable_errors()

    def __call__(self, parser):
        self.debug(parser, "ZeroOrMoreExpr")
        parser._debug_indent += 1
        results = []
        while 42:
            r = self.expr(parser)
            if r is not parser.NoMatch:
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
        ExprMixin.__init__(self, rulename)
        self.rulename = rulename

    def __call__(self, parser):
        self.debug(parser, "RuleExpr `{}`".format(self.rulename))
        rule_method = getattr(parser, self.rulename, None)
        if rule_method is None:
            parser.p_parse_error("Rule `%s` not found" % self.rulename)
        return rule_method()

    def as_grammar(self, atomic=False):
        return self.rulename

    def memoize(self, code):
        pk = hash(self.as_grammar())
        return"""
start_pos_{2}= self.pos
if ({0}, start_pos_{2}) in self._p_memoized:
    result, self.pos = self._p_memoized[({0}, self.pos)]
else:
{1}
    self._p_memoized[({0}, start_pos_{2})] = result, self.pos
        """.format(
            pk,
            self._indent(code, 1),
            self.id,
            repr(self.rulename)
        )


class MaybeExpr(ExprMixin):
    def __init__(self, expr):
        ExprMixin.__init__(self, expr)
        self.expr = expr

    def __call__(self, parser):
        self.debug(parser, "MaybeExpr")
        parser._debug_indent += 1
        result = self.expr(parser)
        parser._debug_indent -= 1
        if result is parser.NoMatch:
            result = ""
        return result

    def as_grammar(self, atomic=False):
        return "{}?".format(self.expr.as_grammar(True))


class LookAhead(ExprMixin):
    def __init__(self, expr):
        ExprMixin.__init__(self, expr)
        self.expr = expr

    def __call__(self, parser):
        self.debug(parser, "LookAhead")
        parser._debug_indent += 1
        parser.p_save()
        if self.expr(parser) is not parser.NoMatch:
            result = ""
        else:
            parser.p_nomatch(self.id)
            result = parser.NoMatch
        parser.p_restore()
        parser._debug_indent -= 1
        return result

    def as_grammar(self, atomic=False):
        return "&{}".format(self.expr.as_grammar(True))


class Not(ExprMixin):
    def __init__(self, expr, terminal=False):
        ExprMixin.__init__(self, expr, terminal=terminal)
        self.expr = expr

    def __call__(self, parser):
        self.debug(parser, "Not")
        parser._debug_indent += 1
        parser.p_save()
        if self.expr(parser) is not parser.NoMatch:
            parser.p_nomatch(self.id)
            result = parser.NoMatch
        else:
            result = ""
        parser.p_restore()
        parser._debug_indent -= 1
        return result

    def as_grammar(self, atomic=False):
        return "!{}".format(self.expr.as_grammar(True))


class LabeledExpr(ExprMixin, AtomicExpr):
    def __init__(self, name, expr, terminal=False):
        ExprMixin.__init__(self, name, expr, terminal=terminal)
        self.name = name
        self.expr = expr

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
    def __init__(self, name, expr, action=None, alias=None, terminal=False):
        ExprMixin.__init__(self, name, expr, action=action, alias=alias,
                           terminal=terminal)
        self.name = name
        self.expr = expr
        self.action = action
        self.args_stack = []
        if alias is not None and not isinstance(
                alias, six.string_types) and alias.__name__ == "NoMatch":
            alias = None
        if alias:
            terminal = True
        elif terminal and name.isupper():
            alias = name
        self.alias = alias
        self.is_syntaxic_terminal = terminal

    def __call__(self, parser):
        self.args_stack.append({})
        result = self.expr(parser)
        args = self.args_stack.pop()

        if result is not parser.NoMatch:
            if self.action is not None:
                if callable(self.action):
                    return self.action(parser, result, **args)
                if isinstance(self.action, six.string_types):
                    if self.action.startswith("@"):
                        return args.get(self.action[1:])
                    action = getattr(parser, self.action)
                    return action(result, **args)
                return self.action(parser, result, **args)
            else:
                return result
        parser.p_nomatch(self.id)
        return result

    def _attach_to(self, parser):
        if six.PY3:
            m = self
        else:
            m = UnboundMethodType(self, None, parser)
        setattr(parser, self.name, m)
        if not self.action and hasattr(parser, "on_{}".format(self.name)):
            self.action = "on_{}".format(self.name)
        return m

    @property
    def expected(self):
        if self.alias:
            return [self.alias]
        else:
            return self.expr.expected

    def as_grammar(self):
        if self.action == "on_{}".format(self.name):
            action = ""
        elif isinstance(self.action, six.string_types) and len(
                self.action.strip()):
            action = " {%s}" % self.action
        else:
            action = ""
        return "{} <- {}{}".format(
            self.name,
            self.expr.as_grammar(),
            action
        )
