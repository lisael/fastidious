from .sanitize import check_rulenames, check_left_recursion
from .gendot import gendot


def sanitize_rules(rules):
    check_rulenames()
    check_left_recursion()


__all__ = [check_rulenames, gendot, sanitize_rules]
