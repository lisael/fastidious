from unittest import TestCase

from fastidious.parser import parse_grammar
from fastidious.compiler import check_rulenames, gendot
from fastidious.compiler.rulename_checker import DuplicateRule, UnknownRule


class TestRulesChecker(TestCase):
    def test_good_check(self):
        grammar = """
        a <- '1'/'2'
        """
        rules = parse_grammar(grammar)
        check_rulenames(rules)

    def test_duplicate_rule(self):
        grammar = """
        a <- '1'/'2'
        a <- '1'/'3'
        """
        rules = parse_grammar(grammar)
        with self.assertRaisesRegexp(DuplicateRule,
                                     "Rule `a` is defined twice."):
            check_rulenames(rules)

    def test_undefined_rule(self):
        grammar = """
        a <- b / c
        """
        rules = parse_grammar(grammar)
        with self.assertRaisesRegexp(
                UnknownRule,
                "Rule `c` referenced in a is not defined"):
            check_rulenames(rules)


class TestGendot(TestCase):
    def test_gendot(self):
        grammar = """
        a <- '1' / foo:('2'+ 'bar'*)
        """
        rules = parse_grammar(grammar)
        gendot(rules)
