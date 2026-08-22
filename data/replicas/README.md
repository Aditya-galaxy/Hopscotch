# Attack replicas

Hand-authored replicas of published attack *patterns*, used to exercise the
capability gate. **No live malware, no downloaded payloads, nothing executable.**
Every file here is inert text.

`credential-helper/` reproduces the shape reported in the ClawHub supply-chain
research: a skill whose stated purpose is ordinary and whose body instructs the
agent to read credentials and attach them to outbound requests. It carries no
shell, no binary, and no regex-matchable signature — which is the point. It is
here to prove the intent reviewer earns its model call, because static analysis
correctly finds nothing wrong with it.
