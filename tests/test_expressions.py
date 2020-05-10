import re  # noqa
from unittest import TestCase

import six

from fastidious.expressions import *  # noqa
from fastidious.bootstrap import ParserMixin
from fastidious import Parser


class ParserMock(ParserMixin):
    pass


class ExprTestMixin(object):
    NoMatch = ParserMixin.NoMatch

    def expect(self, args, input, res):
        # test the expression class __call__ method
        l = self.ExprKlass(*args)
        p = ParserMock(input)
        r = l(p)
        self.assertEquals(r, res)
        if isinstance(res, six.string_types):
            self.assertEquals(input[len(res):], p.p_suffix())

        # test the generated code
        grammar = "rule <- %s" % l.as_grammar()

        class TestParser(Parser):
            __grammar__ = grammar

        r = TestParser(input).rule()
        self.assertEquals(r, res)
        if isinstance(res, six.string_types):
            self.assertEquals(input[len(res):], p.p_suffix())
        return TestParser


class LiteralExprTests(TestCase, ExprTestMixin):
    ExprKlass = LiteralExpr

    def test_literal(self):
        self.expect(("a",), "ab", "a")
        self.expect(("",), "ab", "")
        self.expect(("b",), "Bb", self.NoMatch)
        self.expect(("\\",), '\\rest', '\\')
        self.expect(("a", True), "ab", "a")
        self.expect(("a", True), "Ab", "A")
        self.expect(("b", True), "ab", self.NoMatch)
        self.expect(("\\", True), '\\rest', '\\')


class RegexExprTest(TestCase, ExprTestMixin):
    ExprKlass = RegexExpr

    def test_regex(self):
        self.expect(("a*",), "aab", "aa")
        self.expect(("a*", "i"), "Aabc", "Aa")
        self.expect(("\t",), "\ta", "\t")
        self.expect(("\\" +"u0042",), "Ba", "B")
        self.expect(("a+",), "b", self.NoMatch)


class CharRangeExprTest(TestCase, ExprTestMixin):
    ExprKlass = CharRangeExpr

    def test_char_range(self):
        self.expect(("ab",), "add", "a")
        self.expect(("ab",), "bdd", "b")
        self.expect(("ab",), "cab", self.NoMatch)


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
        self.expect(
            (
                LiteralExpr("aa"),
                AnyCharExpr(),
                LiteralExpr("bb"),
            ), "bb", self.NoMatch
        )


class OneOrMoreExprTest(TestCase, ExprTestMixin):
    ExprKlass = OneOrMoreExpr

    def test_one_or_more(self):
        self.expect(
            (LiteralExpr("a"),),
            "aab", ["a", "a"]
        )
        self.expect(
            (LiteralExpr("a"),),
            "aaa", ["a", "a", "a"]
        )
        self.expect(
            (LiteralExpr("a"),),
            "bbb", self.NoMatch
        )


class ZeroOrMoreExprTest(TestCase, ExprTestMixin):
    ExprKlass = ZeroOrMoreExpr

    def test_zero_or_more(self):
        self.expect(
            (LiteralExpr("a"),),
            "aab", ["a", "a"]
        )
        self.expect(
            (LiteralExpr("a"),),
            "aaa", ["a", "a", "a"]
        )
        self.expect(
            (LiteralExpr("a"),),
            "bbb", []
        )


class ChoiceExprTest(TestCase, ExprTestMixin):
    ExprKlass = ChoiceExpr

    def test_seq(self):
        choices = (
            LiteralExpr("aa"),
            LiteralExpr("bb"),
        )
        self.expect(choices, "aa cc", "aa")
        self.expect(choices, "cc aa", self.NoMatch)


class AnyCharExprTest(TestCase, ExprTestMixin):
    ExprKlass = AnyCharExpr

    def test_any_char(self):
        self.expect(tuple(), "aa", "a")
        self.expect(tuple(), "", self.NoMatch)


class MaybeExprTest(TestCase, ExprTestMixin):
    ExprKlass = MaybeExpr

    def test_maybe(self):
        self.expect((LiteralExpr("aa"),), "aa bb", "aa")
        self.expect((LiteralExpr("aa"),), "bb aa", "")


class NotTest(TestCase, ExprTestMixin):
    ExprKlass = Not

    def test_not(self):
        self.expect((LiteralExpr("aa"),), "bb aa", "")
        self.expect((LiteralExpr("aa"),), "aa bb", self.NoMatch)


class LookAheadTest(TestCase, ExprTestMixin):
    ExprKlass = LookAhead

    def test_lookahead(self):
        self.expect((LiteralExpr("aa"),), "aa bb", "")
        self.expect((LiteralExpr("aa"),), "bb aa", self.NoMatch)
