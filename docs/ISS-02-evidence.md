# ISS-02 Manual Evidence Record

## Issue

The PD2 report did not include manual screenshots or verified evaluation-account
details.

## Local checks completed

| Check | Result | Environment |
|---|---|---|
| Empty registration form | Required-field validation messages displayed | Localhost |
| Member sign-in | Test Member reached the Member dashboard | Localhost test database |
| Admin sign-in | Admin dashboard loaded using an account supplied by the project owner | Localhost |
| Role access control | Admin was denied access to a Member-only page | Localhost |
| Custom 404 | Branded 404 page displayed with `DEBUG=False` | Localhost |

These are local checks only. They do not verify accounts on a publicly hosted
evaluation site.

## Still required for the PD3 report

- Insert the original screenshots into Section 5 of the completed PD3 report.
- List disposable test-account details in Section 8. Do not reuse production
  passwords or commit credentials with access to real data.
- Verify the evaluation accounts on the environment the instructor will use, if
  that environment is different from localhost.
- Save the completed report in the required submission location.

## Status

Evidence checks have been performed locally, but ISS-02 remains open until the
screenshots and appropriate test-account details are included in the submitted
PD3 report. No hosted evaluation accounts have been verified as part of this
record.
