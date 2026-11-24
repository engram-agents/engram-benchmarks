# Attribution: the BEAM dataset

This study uses the BEAM benchmark dataset:

- Mohammad Tavakoli, Alireza Salemi, Carrie Ye, Mohamed Abdalla, Hamed Zamani and J Ross Mitchell, *Beyond a Million
  Tokens: Benchmarking and Enhancing Long-Term Memory in LLMs*, arXiv:2510.27246 (2025),
  https://arxiv.org/abs/2510.27246
- Dataset: Hugging Face `Mohammadta/BEAM`, released under the Creative Commons Attribution-ShareAlike 4.0 International
  License (CC BY-SA 4.0), https://creativecommons.org/licenses/by-sa/4.0/

The repository's own code and documents are Apache-2.0 (see `LICENSE`). Material derived from the BEAM dataset is not
covered by that licence: it remains under CC BY-SA 4.0, with the attribution above.

Earlier commits in this repository's history contain excerpts derived from the BEAM dataset: a key-fact list with
questions and answers about one conversation, and lines of an analysis output quoting that conversation. Ten commits
introduce file versions carrying them (ef2697c, 2c5d903a, 64c8cfe, 27bcea8, ab4928f, 3f4441d, 79b186f, acae6fb,
d667bd9, 69ea84b; the list and how it was counted are in studies/beam-2026-11/data/tuning-log.md). They were removed
from the current files on 2026-11-19; the copies in history remain under CC BY-SA 4.0 with this attribution. The P1
question file (studies/beam-2026-11/data/p1-questions.json, team-written questions without answers) stays public and
quotes a few words of the conversation in two items, also under CC BY-SA 4.0. The study's rule since then:
benchmark-derived question, answer and conversation text is committed by sha256 only and held privately while any
study using that conversation is open; tools/public-text-check.py enforces it.
