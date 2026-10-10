# v5 rescore — parity-fixed scorer on frozen 360 replies

- embedded scorer sha256: `39b7307850f1f39d71ce97aa0ce425cf65ccef67c571a692fc91f3a611190f96`
- relevance verdicts: frozen from v4 (subscription judge, GPT-6.1-sol)
- overall mean: v4 0.8890 -> v5 0.8908
- replies with changed combined: 22/360
- max abs per-reply delta: 0.3750

| model | mean_v5 | relevant+adherent |
|---|---:|---:|
| mlx-community/Qwen3.5-2B-4bit | 0.8321 | 113/180 |
| mlx-community/Qwen3.5-9B-4bit | 0.9495 | 148/180 |
