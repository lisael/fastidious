from unittest import TestCase
from fastidious.expressions import *
from fastidious.bootstrap import ParserMixin


class ParserMock(ParserMixin):
    pass


class ExprTestMixin(object):
    def expect(self, args, input, res):
        # test the expression class __call__ meth
        l = self.ExprKlass(*args)
        p = ParserMock(input)
        r = l(p)
        self.assertEquals(r, res)
        if isinstance(res, basestring):
            self.assertEquals(input[len(res):], p.p_suffix())

        # test the generated method
        oldself = self
        le = self.ExprKlass(*args)
        self = ParserMock(input)
        exec(le.as_code())
        oldself.assertEquals(result, res)
        if isinstance(res, basestring):
            oldself.assertEquals(input[len(res):], self.p_suffix())


class LiteralExprTests(TestCase, ExprTestMixin):
    ExprKlass = LiteralExpr

    def test_literal(self):
        self.expect(("a",), "ab", "a")
        self.expect(("b",), "Bb", False)
        self.expect(("\\",), '\\rest', '\\')
        self.expect(("a", True), "ab", "a")
        self.expect(("a", True), "Ab", "A")
        self.expect(("b", True), "ab", False)
        self.expect(("\\",True), '\\rest', '\\')


class CharRangeExprTest(TestCase, ExprTestMixin):
    ExprKlass = CharRangeExpr

    def test_char_range(self):
        self.expect(("ab",), "add", "a")
        self.expect(("ab",), "bdd", "b")
        self.expect(("ab",), "cab", False)


class SeqExprTest(TestCase, ExprTestMixin):
    ExprKlass = SeqExpr

    def test_seq(self):
        self.expect(
            (
                LiteralExpr("aa"),
                AnyCharExpr(),
                LiteralExpr("bb"),
            ), "aa bb", ["aa", " ", "bb"]
        )


class ChoiceExprTest(TestCase, ExprTestMixin):
    ExprKlass = ChoiceExpr

    def test_seq(self):
        choices = (
                LiteralExpr("aa"),
                LiteralExpr("bb"),
            )
        self.expect(choices, "aa cc", "aa")


class AnyCharExprTest(TestCase, ExprTestMixin):
    ExprKlass = AnyCharExpr

    def test_any_char(self):
        self.expect(tuple(), "aa", "a")
        self.expect(tuple(), "", False)


class TestRule(TestCase):
    def test_method(self):
        class TestRuleParser(ParserMixin):
            def on_rulename(self, content, argname):
                return content, argname
        rule = Rule(
            "rulename",
            SeqExpr(
                LabeledExpr(
                    "argname",
                    LiteralExpr("hello"),
                    "rulename",
                ),
                LiteralExpr(" world")
            ), "on_rulename"
        )
        pm = TestRuleParser("hello world")
        rule.as_method(pm)
        res = pm.rulename()
        self.assertEquals(res, (['hello', ' world'], 'hello'))
