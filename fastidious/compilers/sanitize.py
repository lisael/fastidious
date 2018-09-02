from fastidious.compiler.astutils import Visitor


class DuplicateRule(Exception):
    pass


class UnknownRule(Exception):
    pass


class LeftRecursion(Exception):
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


def _dedup(lst):
    for i in list(lst):
        if lst.count(i) > 1:
            lst.reverse()
            lst.remove(i)
            lst.reverse()
    return lst


class LeftRecursionChecker(Visitor):
    def __init__(self):
        self.leftmosts = {}

    def visit_rule(self, node):
        self.leftmosts[node.name] = _dedup(self.visit(node.expr))

    def visit_seqexpr(self, node):
        left = node.exprs[0]
        return self.visit(left)

    def visit_choiceexpr(self, node):
        leftmosts = []
        for e in node.exprs:
            leftmosts += self.visit(e)
        return leftmosts

    def visit_ruleexpr(self, node):
        return [node.rulename]

    def visit_labeledexpr(self, node):
        return self.visit(node.expr)

    def generic_action(self, node):
        return []

    def check_rules(self, rules):
        for r in rules:
            self.visit(r)

        # expand the found left expressions to their own left expressions too
        changed = True
        while changed:
            changed = False
            for rule, lefts in list(self.leftmosts.items()):
                expanded = list(lefts)
                for left in lefts:
                    expanded += self.leftmosts[left]
                _dedup(expanded)
                if expanded != lefts:
                    changed = True
                    self.leftmosts[rule] = expanded

        # find the recursions
        for rule, lefts in self.leftmosts.items():
            for l in lefts:
                if rule in self.leftmosts.get(l, []):
                    raise LeftRecursion(
                        "rule `%s` and `%s` are left recursive"
                        " (maybe through another rule)" % (rule, l))


def check_left_recursion(rules):
    LeftRecursionChecker().check_rules(rules)
