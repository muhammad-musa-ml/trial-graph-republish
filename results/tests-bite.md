| Change made to a copy | Tests | Failing test files |
|---|---|---|
| republish rewrites no trials | 31 failed | test_cli.py, test_republish.py |
| republish ignores a changed rule id | 1 failed | test_republish.py |
| republish keeps a concept that lost its last edge | 21 failed | test_cli.py, test_republish.py |
| republish does not rename a concept | 13 failed | test_cli.py, test_republish.py |
| republish does not remove the old edges of a trial | 32 failed | test_cli.py, test_republish.py |
| republish leaves the stored rules as they were | 37 failed | test_cli.py, test_republish.py |
| republish does not check that the data is unchanged | 1 failed | test_republish.py |
| an excluded label still gets an edge | 28 failed | test_cli.py, test_interpret.py, test_publish.py, test_republish.py |
| unbalanced parentheses are not reported | 2 failed | test_cli.py, test_quality.py |
| curly and acute apostrophes are not unified | 1 failed | test_quality.py |
| a repeated id is not quarantined | 2 failed | test_publish.py, test_quality.py |

Unmodified copy: all tests pass. Changes the tests missed or that did not run: 0 of 11.
