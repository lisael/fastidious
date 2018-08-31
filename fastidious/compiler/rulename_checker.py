from fastidious.compiler.astutils import Visitor


class DuplicateRule(Exception):
    pass


class UnknownRule(Exception):
    pass


class RuleNameChecker(Visitor):
    def __init__(self):
        self.current_rule = None
        self.rulenames = []
        self.rule_refs = {}

    def visit_rule(self, node):
        self.current_rule = node.name
        self.visit(node.expr)

    def visit_ruleexpr(self, node):
        self.rule_refs.setdefault(node.rulename, []).append(self.current_rule)

    def check_rules(self, rules):
        for r in rules:
            if r.name in self.rulenames:
                raise DuplicateRule("Rule `%s` is defined twice." % r.name)
            self.rulenames.append(r.name)
            self.visit(r)
        for name, locations in self.rule_refs.items():
            if name not in self.rulenames:
                locs = ", ".join(locations)[::-1].replace(",", "dna ", 1)[::-1]
                raise UnknownRule(
                    "Rule `%s` referenced in %s is not defined" % (name,
                                                                   locs))


def check_rulenames(rules):
    """
    Given a set of rules, check if:
        - there's no duplication of rulnames
        - referenced rules do exist in the set
    """
    RuleNameChecker().check_rules(rules)
