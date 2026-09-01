# Mechanism validation

The SafeMA tests establish that:

- legal RecSub email and portal effects invoke the raw adapter;
- wrong actual email and portal destinations are denied before the raw body;
- Base App letter registration cannot create a trusted resource binding;
- a forged Base App applicant cannot override control-plane attributes;
- misleading correlation does not authorize and garbage correlation does not
  prevent a valid effect;
- an API with no correlation field can be modeled and authorized;
- replacing only policy YAML `subset` with `eq` changes behavior;
- replacing bytes at a registered path changes identity and denies;
- trusted cancellation updates the generic Context `active` attribute;
- unknown YAML fields fail at startup;
- the external control plane and runtime preserve metadata across separate CLI
  processes.

The frozen Base App test suite remains an independent regression suite.
