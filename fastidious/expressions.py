import re
from types import UnboundMethodType, MethodType


class NoMatch(object):
    pass


class ExprMixin(object):
    last_id = 0

    def __init__(self, *args, **kwargs):
        self.is_syntaxic_terminal = kwargs.pop("terminal", False)
        self.report_errors = True

    @property
    def expected(self):
        return [self.as_grammar()]

    def visit(self, func):
        func(self)
        [child.visit(func) for child in getattr(self, "exprs", [])]
        if hasattr(self, "expr"):
            getattr(self, "expr").visit(func)

    def debug(self, parser, message):
        if parser.__debug___:
            print("{}{} `{}`".format(parser._debug_indent * " ",
                                     message, parser.input[
                                         parser.pos:parser.pos+5]))

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

    def report_error(self, indent=0):
        if not self.report_errors:
            code = "pass"
        else:
            code = """
if self._p_error_stack:
    head = self._p_error_stack[0]
else:
    head = (0,0)
if self.pos <= head[0]:
    self._p_error_stack.append((self.pos, {0}))
elif self.pos > head[0]:
    self._p_error_stack = [(self.pos, {0})]
# print self._p_error_stack
        """.format(self.id).strip()
        return self._indent(code, indent)

    def _indent(self, code, space):
        ind = " " * space * 4
        return ind + ("\n" + ind).join([l for l in code.splitlines()])

    def memoize(self, code):
        # I first memoized ALL expressions, but it was actually slower,
        # cache hit ratio was 1/30. Caching only rules has a cache hit ratio
        # of 1/7 and is ~1.3 faster. The test data is fastidious PEG grammar,
        # a real life datum :)
        if not isinstance(self, RuleExpr):
            return code
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


class AtomicExpr(object):
    """Marker class for atomic expressions"""


class Expression(object):
    def __init__(self, rule, pos, argname=None):
        self.argname = argname
        self.pos = pos
        self.rule = rule

    def method_name(self):
        return "_expr_{}_{}".format(self.rule.name, self.pos)


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
            return NoMatch
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

    def as_code(self, memoize=False, globals_=None):
        globals_.append("regex=re.compile({})".format(
            repr(self._full_regexp())))
        return """
# {0}
m = regex.match(self.p_suffix())
if m:
    result = self.p_suffix(m.end())
    self.pos += m.end()
else:
{1}
    result = NoMatch
        """.format(
            self.as_grammar(),
            self.report_error(1),
        )


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
            if res is NoMatch:
                parser.p_restore()
                parser.p_nomatch(self.id)
                parser._debug_indent -= 1
                return NoMatch
            results.append(res)
        parser._debug_indent -= 1
        parser.p_discard()
        return results

    def as_grammar(self, atomic=False):
        g = " ".join([e.as_grammar(True) for e in self.exprs])
        if atomic and len(self.exprs) > 1:
            return "( {} )".format(g)
        return g

    def as_code(self, memoize=False, globals_=None):
        def expressions():
            exprs = []
            for i, expr in enumerate(self.exprs):
                expr_code = """
{0}
if result is NoMatch:
    results_{1} = NoMatch
    self.p_restore()
{2}
else:
    results_{1}.append(result)
                    """.format(expr.as_code(memoize), self.id,
                               self.report_error(1)).strip()
                exprs.append(self._indent(expr_code, i))
            return "\n".join(exprs)

        code = """
# {0}
self.p_save()
results_{1} = []
{2}
if results_{1} is not NoMatch:
    self.p_discard()
result = results_{1}
        """.format(
            self.as_grammar(),
            self.id,
            expressions()
        )
        if memoize:
            code = self.memoize(code.strip())
        return code.strip()


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
            if res is not NoMatch:
                parser._debug_indent -= 1
                parser.p_discard()
                return res
        parser._debug_indent -= 1
        parser.p_restore()
        parser.p_nomatch(self.id)
        return NoMatch

    def as_grammar(self, atomic=False):
        g = " / ".join([e.as_grammar(True) for e in self.exprs])
        if atomic and len(self.exprs) > 1:
            return "( {} )".format(g)
        return g

    def as_code(self, memoize=False, globals_=None):
        def expressions():
            exprs = []
            for i, expr in enumerate(self.exprs):
                expr_code = """
{}
if result is NoMatch:
                """.format(expr.as_code(memoize)).strip()
                exprs.append(self._indent(expr_code, i))
            exprs.append(self._indent("pass", i+1))
            return "\n".join(exprs)

        code = """
# {1}
self.p_save()
result = NoMatch
{0}
if result is NoMatch:
    self.p_restore()
{2}
else:
    self.p_discard()
        """.format(
            expressions(),
            self.as_grammar(),
            self.report_error(1)
        )
        if memoize:
            code = self.memoize(code.strip())
        return code.strip()


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
        return NoMatch

    def as_grammar(self, atomic=False):
        return "."

    def as_code(self, memoize=False, globals_=None):
        code = """
# .
self.p_save()
n = self.p_next()
if n is not None:
    self.p_discard()
    result = n
else:
    self.p_restore()
{}
    result = NoMatch
        """.format(self.report_error(1))
        if memoize:
            code = self.memoize(code.strip())
        return code.strip()


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
            return NoMatch
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
        if lit != '"':
            return '"{}"'.format(lit)
        return """'"'"""

    def as_code(self, memoize=False, globals_=None):
        if self.lit == "":
            return "result = ''"
        code = """
# {2}
result = self.p_startswith({0}, {1})
if not result:
{3}
    result = NoMatch
        """.format(
            repr(self.lit),
            repr(self.ignorecase),
            self.as_grammar(),
            self.report_error(1)
        )
        if memoize:
            code = self.memoize(code.strip())
        return code.strip()


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
        return NoMatch

    def as_grammar(self, atomic=False):
        chars = self.chars.replace("0123456789", "0-9")
        chars = chars.replace("\t", r"\t")
        chars = chars.replace("\n", r"\n")
        chars = chars.replace("\r", r"\r")
        chars = chars.replace("abcdefghijklmnopqrstuvwxyz", "a-z")
        chars = chars.replace("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "A-Z")
        chars = chars.replace("0123456789", "0-9")
        return "[{}]".format(chars)

    def as_code(self, memoize=False, globals_=None):
        code = """
# {0}
self.p_save()
n = self.p_next()
if n is not None and n in {1}:
    self.p_discard()
    result = n
else:
    self.p_restore()
{2}
    result = NoMatch
        """.format(
                self.as_grammar(),
                repr(self.chars),
                self.report_error(1),
            )
        if memoize:
            code = self.memoize(code.strip())
        return code.strip()


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
            if r is not NoMatch:
                results.append(r)
            else:
                break
        parser._debug_indent -= 1
        if not results:
            parser.p_restore()
            parser.p_nomatch(self.id)
            return NoMatch
        if isinstance(self.expr, (CharRangeExpr, AnyCharExpr)):
            results = "".join(results)
        parser.p_discard()
        return results

    def as_grammar(self, atomic=False):
        return "{}+".format(self.expr.as_grammar(True))

    def as_code(self, memoize=False, globals_=None):
        if isinstance(self.expr, (CharRangeExpr, AnyCharExpr)):
            result_line = 'result = "".join(results_{})'.format(self.id)
        else:
            result_line = 'result = results_{}'.format(self.id)
        code = """
# {0}
self.p_save()
results_{3} = []
while 42:
{1}
    if result is not NoMatch:
        results_{3}.append(result)
    else:
        break
if not results_{3}:
    self.p_restore()
{4}
    result = NoMatch
else:
    self.p_discard()
    {2}
        """.format(
            self.as_grammar(),
            self._indent(self.expr.as_code(memoize), 1),
            result_line,
            self.id,
            self.report_error(1)
        )
        if memoize:
            code = self.memoize(code.strip())
        return code.strip()


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
            if r is not NoMatch:
                results.append(r)
            else:
                break
        if isinstance(self.expr, (CharRangeExpr, AnyCharExpr)):
            results = "".join(results)
        parser._debug_indent -= 1
        return results

    def as_grammar(self, atomic=False):
        return "{}*".format(self.expr.as_grammar(True))

    def as_code(self, memoize=False, globals_=None):
        if isinstance(self.expr, (CharRangeExpr, AnyCharExpr)):
            result_line = 'result = "".join(results_{})'.format(self.id)
        else:
            result_line = 'result = results_{}'.format(self.id)
        code = """
# {0}
results_{3} = []
while 42:
{1}
    if result is not NoMatch:
        results_{3}.append(result)
    else:
        break
# print self._p_error_stack
{2}
        """.format(
            self.as_grammar(),
            self._indent(self.expr.as_code(memoize), 1),
            result_line,
            self.id,
        )
        if memoize:
            code = self.memoize(code.strip())
        return code.strip()


class RuleExpr(ExprMixin, AtomicExpr):
    def __init__(self, rulename):
        ExprMixin.__init__(self, rulename)
        self.rulename = rulename

    def __call__(self, parser):
        self.debug(parser, "RuleExpr `{}`".format(self.rulename))
        rule_method = getattr(parser, self.rulename, None)
        if rule_method is None:
            parser.parse_error("Rule `%s` not found" % self.rulename)
        return rule_method()

    def as_grammar(self, atomic=False):
        return self.rulename

    def as_code(self, memoize=False, globals_=None):
        code = "result = self.{}()".format(self.rulename)
        if memoize:
            code = self.memoize(code.strip())
        return code.strip()


class MaybeExpr(ExprMixin):
    def __init__(self, expr):
        ExprMixin.__init__(self, expr)
        self.expr = expr

    def __call__(self, parser):
        self.debug(parser, "MaybeExpr")
        parser._debug_indent += 1
        result = self.expr(parser)
        parser._debug_indent -= 1
        if result is NoMatch:
            result = ""
        return result

    def as_grammar(self, atomic=False):
        return "{}?".format(self.expr.as_grammar(True))

    def as_code(self, memoize=False, globals_=None):
        code = """
# {}
{}
result = "" if result is NoMatch else result
if result is NoMatch:
    # print self._p_error_stack
    self._p_error_stack.pop()
        """.format(self.as_grammar(), self.expr.as_code(memoize))
        if memoize:
            code = self.memoize(code.strip())
        return code.strip()


class LookAhead(ExprMixin):
    def __init__(self, expr):
        ExprMixin.__init__(self, expr)
        self.expr = expr

    def __call__(self, parser):
        self.debug(parser, "LookAhead")
        parser._debug_indent += 1
        parser.p_save()
        if self.expr(parser) is not NoMatch:
            result = ""
        else:
            parser.p_nomatch(self.id)
            result = NoMatch
        parser.p_restore()
        parser._debug_indent -= 1
        return result

    def as_grammar(self, atomic=False):
        return "&{}".format(self.expr.as_grammar(True))

    def as_code(self, memoize=False, globals_=None):
        code = """
# {1}
self.p_save()
{0}
result = result if result is NoMatch else ""
self.p_restore()
if result is NoMatch:
{2}
        """.format(
            self.expr.as_code(memoize),
            self.as_grammar(),
            self.report_error(1)
        )
        if memoize:
            code = self.memoize(code.strip())
        return code.strip()


class Not(ExprMixin):
    def __init__(self, expr, terminal=False):
        ExprMixin.__init__(self, expr, terminal=terminal)
        self.expr = expr

    def __call__(self, parser):
        self.debug(parser, "Not")
        parser._debug_indent += 1
        parser.p_save()
        if self.expr(parser) is not NoMatch:
            parser.p_nomatch(self.id)
            result = NoMatch
        else:
            result = ""
        parser.p_restore()
        parser._debug_indent -= 1
        return result

    def as_grammar(self, atomic=False):
        return "!{}".format(self.expr.as_grammar(True))

    def as_code(self, memoize=False, globals_=None):
        code = """
# {1}
self.p_save()
{0}
result = "" if result is NoMatch else NoMatch
self.p_restore()
if result is NoMatch:
{2}
#else:
    ## print self._p_error_stack
    #self._p_error_stack.pop()
        """.format(
            self.expr.as_code(memoize),
            self.as_grammar(),
            self.report_error(1)
        )
        if memoize:
            code = self.memoize(code.strip())
        return code.strip()


class LabeledExpr(ExprMixin, AtomicExpr):
    def __init__(self, name, expr, rulename=None, terminal=False):
        ExprMixin.__init__(self, name, expr, rulename=rulename,
                           terminal=terminal)
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

    def as_code(self, memoize=False, globals_=None):
        code = """
# {}
{}
self.args_stack[{}][-1][{}] = result
        """.format(
            self.as_grammar(),
            self.expr.as_code(memoize),
            repr(self.rulename),
            repr(self.name)
        )
        return code.strip()


class Rule(ExprMixin):
    def __init__(self, name, expr, action=None, alias=None, terminal=False):
        ExprMixin.__init__(self, name, expr, action=action, alias=alias,
                           terminal=terminal)
        self.name = name
        self.expr = expr
        self.action = action
        self.args_stack = []
        if alias is NoMatch:
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

        if result is not NoMatch:
            if self.action is not None:
                if isinstance(self.action, basestring):
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
        m = UnboundMethodType(self, None, parser)
        setattr(parser, self.name, m)
        if not self.action and hasattr(parser, "on_{}".format(self.name)):
            self.action = "on_{}".format(self.name)
        return m

    def _action(self):
        if self.action is not None:
            if isinstance(self.action, basestring):
                if self.action.startswith("@"):
                    return "result = args['{}']".format(self.action[1:])
                if self.action.strip() != "":
                    return "result = self.{}(result, **args)".format(
                        self.action
                    )
        return "pass"

    @property
    def expected(self):
        if self.alias:
            return [self.alias]
        else:
            return self.expr.expected

    def as_method(self, parser):
        memoize = parser.__memoize__
        debug = parser.__debug___
        globals_ = []
        if not self.action:
            default_action = "on_{}".format(self.name)
            if hasattr(parser, default_action):
                self.action = default_action

        code = """
    # {3}
    # -- self.p_debug("{0}({5})")
    # -- self._debug_indent += 1
    self.args_stack.setdefault("{0}",[]).append(dict())
{1}
    args = self.args_stack["{0}"].pop()
    if result is not NoMatch:
        {2}
        # -- self._debug_indent -= 1
        # -- self.p_debug("{0}({5}) -- MATCH " + repr(result) )
    else:
{4}
        # -- self._debug_indent -= 1
        # -- self.p_debug("{0}({5}) -- NO MATCH")
    return result
        """.format(self.name,
                   self._indent(self.expr.as_code(memoize, globals_), 1),
                   self._action(),
                   self.as_grammar(),
                   self.report_error(2),
                   self.id,
                   )
        defline = "def new_method(self, {}):".format(", ".join(globals_))
        code = "\n".join([defline, code])
        if debug:
            code = code.replace("# -- ", "")
        code = code.strip()
        exec(code)
        code = code.replace("new_method", self.name)
        new_method._code = code  # noqa
        new_method.func_name = self.name  # noqa
        if isinstance(parser, type):
            meth = UnboundMethodType(new_method, None, parser)  # noqa
        else:
            meth = MethodType(new_method, parser, type(parser))  # noqa
        setattr(parser, self.name, meth)

    def as_grammar(self):
        if self.action == "on_{}".format(self.name):
            action = ""
        elif isinstance(self.action, basestring) and len(self.action.strip()):
            action = " {%s}" % self.action
        else:
            action = ""
        return "{} <- {}{}".format(
            self.name,
            self.expr.as_grammar(),
            action
        )
