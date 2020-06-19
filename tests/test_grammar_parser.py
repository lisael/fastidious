from unittest import TestCase

from fastidious.bootstrap import _FastidiousParserBootstraper
from fastidious.parser import FastidiousParser


class GrammarParserMixin(object):
    def test_string_literals(self):
        p = self.klass(r'"\n"')
        self.assertEqual(p.string_literal()[0], "\n")
        p = self.klass(r'"\""')
        self.assertEqual(p.string_literal()[0], '"')
        p = self.klass(r"'\n'")
        self.assertEqual(p.string_literal()[0], "\n")
        p = self.klass(r'"\\"')
        self.assertEquals(p.string_literal()[0], '\\')

    def test_class_char(self):
        p = self.klass(r'[ab]')
        self.assertEquals(p.char_range_expr().singles, "ab")
        p = self.klass(r'[ab\]]')
        self.assertEquals(p.char_range_expr().singles, "ab]")
        p = self.klass(r'[a-c]')
        expr = p.char_range_expr()
        self.assertEquals(expr.singles, "")
        self.assertEquals(expr.ranges, [(97, 99)])
        p = self.klass(r'[ab\n]')
        self.assertEquals(p.char_range_expr().singles, "ab\n")
        p = self.klass(r'[0-9\\]')
        expr = p.char_range_expr()
        self.assertEquals(expr.singles, "\\")
        self.assertEquals(expr.ranges, [(48, 57)])

    def test_rule(self):
        parser = self.klass("rulename <- 'literal' {on_rulename}")
        result = parser.rule()
        self.assertEquals(result.name, "rulename")
        self.assertEquals(result.expr.lit, "literal")
        self.assertEquals(result.action, "on_rulename")

    def test_code_block(self):
        parser = self.klass("{on_rulename}")
        result = parser.code_block()
        self.assertEquals(result, "on_rulename")


class TestFastidiousParserBootstraper(TestCase, GrammarParserMixin):
    klass = _FastidiousParserBootstraper


class TestFastidiousParser(TestCase, GrammarParserMixin):
    klass = FastidiousParser
