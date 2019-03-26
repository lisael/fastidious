"""
Fastidious parser compiler and utils.
"""
import sys
import re
import string
import inspect

import six

from fastidious.expressions import CharRangeExpr, AnyCharExpr, ExprMixin
from fastidious.compiler.astutils import Visitor, Mutator
from fastidious.compilers import check_rulenames, check_left_recursion
from fastidious.compiler.action.pyclass import SimplePyAction
from fastidious.compiler.pyutils import indent

if six.PY3:
    from types import FunctionType
    UPPERCASE = string.ascii_uppercase
    LOWERCASE = string.ascii_lowercase
else:
    from types import UnboundMethodType
    UPPERCASE = string.uppercase
    LOWERCASE = string.lowercase


class _RuleNameToCaptures(Visitor):
    def __init__(self, rules):
        self.rulename = None
        for r in rules:
            self.visit(r)

    def visit_rule(self, node):
        self.rulename = node.name
        self.visit(node.expr)

    def visit_labeledexpr(self, node):
        if not hasattr(node, "rulename"):
            node.rulename = self.rulename
        self.visit(node.expr)


class _register_expressions(Visitor):
    def __init__(self, klass):
        self.klass = klass
        if not hasattr(klass, "_p_expressions"):
            klass._p_expressions = dict()
        for rule in self.klass.__rules__:
            self.visit(rule)

    def generic_action(self, node):
        self.klass._p_expressions[node.id] = node


class PySetConstants(Visitor):
    def __init__(self, parser):
        self.parser = parser
        self.parser._p_py_constants = dict()
        for rule in parser.__rules__:
            self.visit(rule)

    def node_consts(self, node):
        return self.parser._p_py_constants.setdefault(node.id, dict())

    def visit_regexexpr(self, node):
        consts = self.node_consts(node)
        consts["regex"] = re.compile(node._full_regexp())


class PyCodeGen(Visitor):
    def __init__(self, debug):
        self.debug = debug

    def __call__(self, parser):
        parser.__rules__ = [self.visit(r) for r in parser.__rules__]

    def report_error(self, id):
        return """
if self._p_error_stack:
    head = self._p_error_stack[0]
else:
    head = (0, 0)
if self.pos <= head[0]:
    self._p_error_stack.append((self.pos, {0}))
elif self.pos > head[0]:
    self._p_error_stack = [(self.pos, {0})]
# print self._p_error_stack
        """.format(id).strip()

    def _action(self, action):
        from fastidious.compiler.action.pyclass import SimplePyAction
        if action is not None:
            if isinstance(action, SimplePyAction):
                return action.as_code()
        return "pass"

    def visit_rule(self, node):
        self.visit(node.expr)
        code = """    '''{3}'''
    # -- self.p_debug("{0}({5})")
    # -- self._debug_indent += 1
    args = dict()
{1}
    # -- self._debug_indent -= 1
    if result is not self.NoMatch:
        {2}
        # -- self.p_debug("{0}({5}) -- MATCH " + repr(result) )
    else:
{4}
        # -- self.p_debug("{0}({5}) -- NO MATCH")
    return result
        """.format(node.name,
                   indent(node.expr._py_code, 1),
                   self._action(node.action),
                   node.as_grammar().replace("'", "\\'"),
                   indent(self.report_error(node.id), 2),
                   node.id,
                   )
        defline = "def {}(self):".format(node.name)
        code = "\n".join([defline, code])
        if self.debug:
            code = code.replace("# -- ", "")
        else:
            lines = code.splitlines(True)
            code = ""
            for line in lines:
                if line.strip().startswith("# --"):
                    continue
                else:
                    code += line
        node._py_code = code.strip()
        return node

    def visit_ruleexpr(self, node):
        code = "result = self.{}()".format(node.rulename).strip()
        node._py_code = code.strip()

    def visit_regexexpr(self, node):
        code = """
# {0}
regex = self._p_py_constants[{2}]["regex"]
m = regex.match(self.p_suffix())
if m:
    result = self.p_suffix(m.end())
    self.pos += m.end()
else:
{1}
    result = self.NoMatch
        """.format(
            node.as_grammar(),
            indent(self.report_error(node.id), 1),
            node.id,
        )
        node._py_code = code.strip()

    def visit_seqexpr(self, node):

        def expressions():
            exprs = []
            for i, expr in enumerate(node.exprs):
                self.visit(expr)
                expr_code = """
{0}
if result is self.NoMatch:
    results_{1} = self.NoMatch
    self.p_restore()
{2}
else:
    results_{1}.append(result)
                    """.format(expr._py_code, node.id,
                               indent(self.report_error(node.id).strip(), 1))
                exprs.append(indent(expr_code, i))
            return "\n".join(exprs)

        code = """
# {0}
self.p_save()
results_{1} = []
{2}
if results_{1} is not self.NoMatch:
    self.p_discard()
result = results_{1}
        """.format(
            node.as_grammar(),
            node.id,
            expressions()
        )
        node._py_code = code.strip()

    def visit_labeledexpr(self, node):
        self.visit(node.expr)
        code = """
# {}
{}
args[{}] = result
        """.format(
            node.as_grammar(),
            node.expr._py_code,
            repr(node.name)
        )
        node._py_code = code.strip()

    def visit_oneormoreexpr(self, node):
        self.visit(node.expr)
        if isinstance(node.expr, (CharRangeExpr, AnyCharExpr)):
            result_line = 'result = "".join(results_{})'.format(node.id)
        else:
            result_line = 'result = results_{}'.format(node.id)
        code = """
# {0}
self.p_save()
results_{3} = []
while 42:
{1}
    if result is not self.NoMatch:
        results_{3}.append(result)
    else:
        break
if not results_{3}:
    self.p_restore()
{4}
    result = self.NoMatch
else:
    self.p_discard()
    {2}
        """.format(
            node.as_grammar(),
            indent(node.expr._py_code, 1),
            result_line,
            node.id,
            indent(self.report_error(node.id), 1)
        )
        node._py_code = code.strip()

    def visit_maybeexpr(self, node):
        self.visit(node.expr)
        code = """
# {}
{}
result = "" if result is self.NoMatch else result
if result is self.NoMatch:
    # print self._p_error_stack
    self._p_error_stack.pop()
        """.format(node.as_grammar(), node.expr._py_code)
        node._py_code = code.strip()

    def visit_literalexpr(self, node):

        if node.lit == "":
            node._py_code = "result = ''"
            return
        code = """
# {2}
result = self.p_startswith({0}, {1})
if not result:
{3}
    result = self.NoMatch
        """.format(
            repr(node.lit),
            repr(node.ignorecase),
            node.as_grammar(),
            indent(self.report_error(node.id), 1)
        )
        node._py_code = code.strip()

    def visit_not(self, node):
        self.visit(node.expr)
        code = """
# {1}
self.p_save()
{0}
result = "" if result is self.NoMatch else self.NoMatch
self.p_restore()
if result is self.NoMatch:
{2}
#else:
    #print self._p_error_stack
    #self._p_error_stack.pop()
        """.format(
            node.expr._py_code,
            node.as_grammar(),
            indent(self.report_error(node.id), 1)
        )
        node._py_code = code.strip()

    def visit_charrangeexpr(self, node):
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
    result = self.NoMatch
        """.format(
            node.as_grammar(),
            repr(node.chars),
            indent(self.report_error(node.id), 1)
        )
        node._py_code = code.strip()

    def visit_zeroormoreexpr(self, node):
        self.visit(node.expr)
        if isinstance(node.expr, (CharRangeExpr, AnyCharExpr)):
            result_line = 'result = "".join(results_{})'.format(node.id)
        else:
            result_line = 'result = results_{}'.format(node.id)
        code = """
# {0}
results_{3} = []
while 42:
{1}
    if result is not self.NoMatch:
        results_{3}.append(result)
    else:
        break
# print self._p_error_stack
{2}
        """.format(
            node.as_grammar(),
            indent(node.expr._py_code, 1),
            result_line,
            node.id,
        )
        node._py_code = code.strip()

    def visit_choiceexpr(self, node):
        if not node.exprs:
            node._py_code = "result = self.NoMatch"
            return

        def expressions():
            exprs = []
            for i, expr in enumerate(node.exprs):
                self.visit(expr)
                expr_code = """
{}
if result is self.NoMatch:
                """.format(expr._py_code).strip()
                exprs.append(indent(expr_code, i))
            exprs.append(indent("pass", i + 1))
            return "\n".join(exprs)

        code = """
# {1}
self.p_save()
{0}
if result is self.NoMatch:
    self.p_restore()
{2}
else:
    self.p_discard()
        """.format(
            expressions(),
            node.as_grammar(),
            indent(self.report_error(node.id), 1)
        )
        node._py_code = code.strip()

    def visit_anycharexpr(self, node):
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
    result = self.NoMatch
        """.format(indent(self.report_error(node.id), 1))
        node._py_code = code.strip()

    def visit_lookahead(self, node):
        self.visit(node.expr)
        code = """
# {1}
self.p_save()
{0}
result = result if result is self.NoMatch else ""
self.p_restore()
if result is self.NoMatch:
{2}
        """.format(
            node.expr._py_code,
            node.as_grammar(),
            indent(self.report_error(node.id), 1)
        )
        node._py_code = code.strip()


class MemoizedExpr(ExprMixin):
    def __init__(self, expr, debug):
        self.expr = expr
        self.debug = debug

    @property
    def _py_code(self):
        PyCodeGen(self.debug).visit(self.expr)
        pk = hash(self.expr.as_grammar())
        code = """
start_pos_{2}= self.pos
if ({0}, start_pos_{2}) in self._p_memoized:
    result, self.pos = self._p_memoized[({0}, self.pos)]
else:
{1}
    self._p_memoized[({0}, start_pos_{2})] = result, self.pos
    """.format(
            pk,
            indent(self.expr._py_code, 1),
            self.expr.id,
        )
        return code.strip()

    def as_grammar(self, *args, **kwargs):
        return self.expr.as_grammar(*args, **kwargs)


class Memoizer(Mutator):
    def __init__(self, debug):
        self.debug = debug

    def __call__(self, parser):
        parser.__rules__ = [self.visit(r) for r in parser.__rules__]

    def visit_ruleexpr(self, node):
        self.generic_visit(node)
        return MemoizedExpr(node, self.debug)


class MethodBuilder(Visitor):
    def __init__(self, parser):
        self.parser = parser
        parser.__rules__ = [self.visit(r) for r in parser.__rules__]

    def visit_rule(self, node):
        locals_ = dict()
        exec(node._py_code, None, locals_)
        new_method = locals_[node.name]
        if six.PY3:
            new_method.__name__ = node.name
            meth = FunctionType(new_method.__code__, globals(), node.name)
        else:
            new_method._code = node._py_code  # noqa
            new_method.func_name = node.name  # noqa
            meth = UnboundMethodType(new_method, None, self.parser)  # noqa
        setattr(self.parser, node.name, meth)
        return node


class MethodWriter(Visitor):
    def __init__(self, output, indent=1):
        self.output = output
        self.indent = indent

    def __call__(self, parser):
        for r in parser.__rules__:
            self.visit(r)

    def visit_rule(self, node):
        self.output.write(indent(node._py_code, self.indent))
        self.output.write("\n\n")

_SRE_Pattern = type(re.compile("."))

def _repr (obj) :
    # actually only needed for Py2 that does not produce evaluable repr from regexps
    if isinstance(obj, dict) :
        return "{%s}" % (", ".join("%s: %s" % (_repr(k), _repr(v))
                                   for k, v in obj.items()))
    elif isinstance(obj, _SRE_Pattern) :
        return "re.compile(%r, %s)" % (obj.pattern, obj.flags)
    else :
        return repr(obj)

class FastidiousCompiler(object):
    def __init__(self, gen_code=True, memoize=True, debug=False):
        self.gen_code = gen_code
        self.memoize = memoize
        self.debug = debug

    def __call__(self, parser):
        rules = parser.__rules__
        # sanity check. Any compiler should
        check_rulenames(rules)
        check_left_recursion(rules)

        # set the default rule
        if parser.__default__ is None and rules:
            parser.__default__ = rules[0].name

        # for error reporting, register all expressions on the parser
        _register_expressions(parser)

        # parse the actions
        SimplePyAction.update_rules(parser)

        # add the methods to the class
        if self.gen_code:
            # add constants to the class (pre-compile regexes, ...)
            PySetConstants(parser)
            # generate the python code
            if self.memoize:
                Memoizer(self.debug)(parser)
            PyCodeGen(self.debug)(parser)
            # add the methods
            MethodBuilder(parser)
        else:
            for rule in parser.__rules__:
                # the captures must know their parent rule name
                _RuleNameToCaptures(rules)
                rule._attach_to(parser)
        return parser

    def _get_expr_kwargs(self, e):
        kwargs = dict(
            is_syntaxic_terminal=e.is_syntaxic_terminal,
            expected=repr(e.expected)
        )
        if hasattr(e, "expr"):
            kwargs["expr"] = True
        if hasattr(e, "exprs"):
            kwargs["exprs"] = True
        return ", ".join(["%s=%s" % (k, v) for k, v in kwargs.items()])

    def gen_py_code(self, parser, out):
        cmd = " ".join(sys.argv)
        out.write('''"""
This module was generated by fastidious:

    {0}

DO NOT EDIT BY HAND unless you know what you do.

More info at https://github.com/lisael/fastidious
"""
'''.format(cmd))
        out.write("""
import re

if not hasattr(__builtins__, 'basestring'):
    basestring = str

""")

        out.write("""
class _Expr:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            self.__dict__[k] = v


""")
        # print the user's methods
        _, body = inspect.getsource(parser).split("\n", 1)
        out.write("class %s(object):\n" % parser.__name__)
        out.write("    __default__ = '%s'\n" % parser.__default__)
        out.write("    class ParserError(Exception):\n        pass\n\n")
        out.write(body)

        # print _p_py_constants
        out.write("    _p_py_constants = %r\n" % _repr(parser._p_py_constants))

        # print parsr methods and attributes
        from fastidious.parser_base import ParserMixin
        _, mixin_body = inspect.getsource(ParserMixin).split("\n", 1)
        mixin_body = mixin_body.replace("ParserError", "self.ParserError")
        out.write(mixin_body)

        # print the fastidious methods
        MethodWriter(out)(parser)

        # print the expression registry (for error handling)
        out.write("""
    _p_expressions = {
""")
        for k, v in parser._p_expressions.items():
            out.write(
                "        %s: %s,\n" % (
                    k, "_Expr(%s)" % self._get_expr_kwargs(v)
                )
            )
        out.write("    }\n")
