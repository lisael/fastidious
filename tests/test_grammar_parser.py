from unittest import TestCase

from fastidious.bootstrap import _GrammarParserBootstraper
from fastidious.parser import _GrammarParser


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
        self.assertEquals(p.char_range_expr().chars, "ab")
        p = self.klass(r'[ab\]]')
        self.assertEquals(p.char_range_expr().chars, "ab]")
        p = self.klass(r'[a-c]')
        self.assertEquals(p.char_range_expr().chars, "abc")
        p = self.klass(r'[ab\n]')
        self.assertEquals(p.char_range_expr().chars, "ab\n")
        p = self.klass(r'[0-9\\]')
        self.assertEquals(p.char_range_expr().chars, "0123456789\\")


class TestGrammarParserBootstraper(TestCase, GrammarParserMixin):
    klass = _GrammarParserBootstraper


class TestGrammarParser(TestCase, GrammarParserMixin):
    klass = _GrammarParser