"""honda-diag: free OBD-II diagnostic tooling for Honda vehicles on ISO 9141-2.

v0.1 is a *discovery instrument* for 2000s Hondas (e.g. the 2007 Accord
with the K24A8): it probes the car's diagnostic port with every init
sequence the community knows about, logs every byte exchanged, and
decodes whatever generic OBD-II the ECU happens to speak. Honda's
proprietary responses (mode $22, Honda-specific mode $06 test IDs) are
captured raw so decoding tables can be built from real probe logs
(see README roadmap).

v0.1 is deliberately READ-ONLY: it never sends code-clear,
actuator-test, or reprogramming commands. It cannot brick your ECU.
"""

__version__ = "0.1.0"
