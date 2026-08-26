# Pending registrations

Measurements that have been **specified but not run**. They live apart from
`docs/measurement-log.md` for one reason: that log records what happened, and these are commitments
about what will happen.

Keeping them as separate committed files is what makes them work. A registration is only evidence if
its commit precedes the results commit, so folding one into a document that will later carry its own
results destroys the property it exists for.

| file | what it registers | blocked on |
|---|---|---|
| `print-agreement.md` | skip a name when the two IV estimators disagree by more than that name's median daily move | nothing — costs 34.3% of name-days, needs a decision |
| `cost-composition.md` | how cost is charged in a sweep | **its own addendum.** The regime probe broke the imputation rule; a response must be chosen before it is usable |
| `test-a-directional-ic.md` | whether the signal carries directional information | nothing |
| `delta-sweep.md` | delta × structure sweep | the widened NBBO capture, which is the only thing that can settle its load-bearing claim |

**None of these has run.** Anything citing a result from them is citing something that does not exist.
