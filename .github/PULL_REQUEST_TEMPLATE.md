## What and why

<!-- Explain the user/research impact and keep the scope focused. -->

## Verification

- [ ] `ruff format --check .`
- [ ] `ruff check .`
- [ ] `mypy src`
- [ ] `pytest`
- [ ] `python -m build`
- [ ] Offline installed-artifact demo if public behavior changed

## Scientific and security checks

- [ ] Claims stay within `paper/claims.md` and the frozen research contract.
- [ ] Tool access and budgets are matched or explicitly reported.
- [ ] New model/verifier/config input is treated as untrusted.
- [ ] No secret, personal information, unsafe execution, or generated private reasoning was added.
