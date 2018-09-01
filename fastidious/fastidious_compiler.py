"""
Fastidious parser compiler and utils.
"""

import re
import string

import six

from fastidious.expressions import CharRangeExpr, AnyCharExpr
from fastidious.compiler.astutils import Visitor
from fastidious.compilers import check_rulenames
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



class _RuleNameToLabels(Visitor):
    def __init__(self, rules):
        self.rulename = None
        for r in rules:
            self.visit(r)

    def visit_rule(self, node):
        self.rulename = node.name
        self.visit(node.expr)

    def visit_labeledexpr(self, node):
        if node.rulename is None:
            node.rulename = self.rulename
        self.visit(node.expr)


class _register_expressions(Visitor):
    def __init__(self, klass):
        self.klass = klass
        if not hasattr(klass, "__expressions__"):
            klass.__expressions__ = dict()
        for rule in self.klass.__rules__:
            self.visit(rule)

    def generic_action(self, node):
        self.klass.__expressions__[node.id] = node


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
    def __init__(self, memoize, debug):
        self.memoize = memoize
        self.debug = debug

    def _action(self, action):
        from fastidious.compiler.action.pyclass import SimplePyAction
        if action is not None:
            if isinstance(action, SimplePyAction):
                return action.as_code()
        return "pass"

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

    def visit_rule(self, node):
        self.visit(node.expr)
        code = """    '''{3}'''
    # -- self.p_debug("{0}({5})")
    # -- self._debug_indent += 1
    self.args_stack.setdefault("{0}",[]).append(dict())
{1}
    args = self.args_stack["{0}"].pop()
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

    def visit_ruleexpr(self, node):
        code = "result = self.{}()".format(node.rulename).strip()
        if self.memoize:
            pk = hash(node.as_grammar())
            code = """
start_pos_{2}= self.pos
if ({0}, start_pos_{2}) in self._p_memoized:
    result, self.pos = self._p_memoized[({0}, self.pos)]
else:
{1}
    self._p_memoized[({0}, start_pos_{2})] = result, self.pos
    """.format(
                pk,
                indent(code, 1),
                node.id,
            )
        node._py_code = code.strip()

    def visit_labeledexpr(self, node):
        self.visit(node.expr)
        code = """
# {}
{}
self.args_stack[{}][-1][{}] = result
        """.format(
            node.as_grammar(),
            node.expr._py_code,
            repr(node.rulename),
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
            return "result = ''"
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
result = self.NoMatch
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


class MethodBuilder(Visitor):
    def __init__(self, parser, memoize):
        self.parser = parser
        self.memoize = memoize

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


class FastidiousCompiler(object):
    def __init__(self, gen_code=True, memoize=True, debug=False):
        self.parser = None
        self.gen_code = gen_code
        self.memoize = memoize
        self.debug = debug

    def process_rules(self):
        rules = self.parser.__rules__
        check_rulenames(rules)
        if self.parser.__default__ is None and self.parser.__rules__:
            self.parser.__default__ = rules[0].name
        _RuleNameToLabels(rules)
        _register_expressions(self.parser)

    def process_actions(self):
        rules = self.parser.__rules__
        SimplePyAction.update_rules(self.parser, rules)

    def output(self):
        if self.gen_code:
            PySetConstants(self.parser)
            code_gen = PyCodeGen(self.memoize, self.debug)
            builder = MethodBuilder(self.parser, self.memoize)
            for rule in self.parser.__rules__:
                code_gen.visit(rule)
                builder.visit(rule)
        else:
            for rule in self.parser.__rules__:
                rule._attach_to(self.parser)
        return self.parser

    def __call__(self, parser):
        self.parser = parser
        return self



