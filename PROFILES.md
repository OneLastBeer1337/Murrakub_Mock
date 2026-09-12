# PROFILES.md -- provenance ledger

**GENERATED FILE. Do not edit by hand.**
Regenerate with `python -m optimization.profiles.ledger`; `tests/test_profiles_md_generated.py` asserts this file matches the data byte for byte.

> **Read this before quoting any number below.**
>
> This is a REPRODUCTION of a paper that has no source release. Every value here is either
> transcribed from the paper, digitized from one of its figures, derived from those by stated
> arithmetic, or recorded as *unavailable*. Nothing is invented: the only invented numbers in
> Milestone 3 are seven tool service times, which live in `optimization/profiles/critique/` and
> which a test proves the optimizer cannot reach.
>
> Three consequences a casual reader will otherwise miss. **First**, a large minority of values
> are `Unavailable` -- the paper simply does not report them -- so any total computed from this
> set is a LOWER BOUND, and unequally so between the two workflows. **Second**, digitized values
> carry bands, and the bands are wide where the figure is dense; a point estimate quoted without
> its band overstates what the source supports. **Third**, tier values depend on the whole
> population, so they are NOT comparable across profile sets, and every number must be quoted
> together with the set that produced it.
>
> Where this reproduction disagrees with the paper, the paper's reading is kept and the
> disagreement is recorded rather than repaired. See `PROGRESS.md` for the numbered gap list.


Profile set: `baseline`. 401 MILP-facing values: 368 sourced, 33 unavailable (8.2%), 0 invented.

## 1. Coverage summary

| Field | DERIVED | EXTERNAL | PAPER_FIGURE_LABEL | PAPER_FIGURE_READ | PAPER_TABLE | PAPER_TEXT | UNAVAILABLE | Total |
|---|---|---|---|---|---|---|---|---|
| `B_g` | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 2 |
| `a_c` | 0 | 0 | 0 | 34 | 0 | 0 | 10 | 44 |
| `alpha` | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 |
| `c_g` | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 2 |
| `e_m` | 20 | 0 | 0 | 0 | 0 | 0 | 0 | 20 |
| `g_m` | 0 | 0 | 8 | 0 | 12 | 0 | 0 | 20 |
| `l_tpot_m` | 0 | 0 | 0 | 8 | 12 | 0 | 0 | 20 |
| `l_ttft_m` | 0 | 0 | 0 | 18 | 0 | 0 | 2 | 20 |
| `lambda_avg` | 0 | 0 | 0 | 96 | 0 | 0 | 0 | 96 |
| `lambda_peak` | 0 | 0 | 0 | 96 | 0 | 0 | 0 | 96 |
| `prompt_tokens` | 0 | 0 | 0 | 0 | 0 | 0 | 44 | 44 |
| `t_c` | 0 | 0 | 0 | 30 | 0 | 0 | 14 | 44 |
| `tau` | 8 | 0 | 8 | 0 | 0 | 0 | 0 | 16 |
| `theta_m` | 0 | 0 | 0 | 8 | 12 | 0 | 0 | 20 |

## 2. The `Unavailable` register

What this reproduction does not know, and which expression each gap blocks.

| Owner | Field | Blocks | Reason |
|---|---|---|---|
| `code_generation(D=2, R=2, model=DeepSeek-Llama-70B)` | `a_c` | eq4, eq8, eq13 | Figure 2c plots only three Code Gen models and Figure 4b plots exactly ONE DeepSeek-Llama-70B marker against the 32 its legend implies (A54), so three of its four (D,R) configurations have no accuracy reading anywhere and the fourth cannot be attributed to a specific (D,R). Corroborated by Section 7.3: admitting this model on an aliased value breaks two of the four printed tiers |
| `code_generation(D=2, R=2, model=DeepSeek-Llama-70B)` | `t_c (p90)` | eq3, eq5, eq6 | Figure 2d plots no generated-token CDF for DeepSeek-Llama-70B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `code_generation(D=2, R=2, model=NVLM-D-72B)` | `t_c (p90)` | eq3, eq5, eq6 | Figure 2d plots no generated-token CDF for NVLM-D-72B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `code_generation(D=2, R=4, model=DeepSeek-Llama-70B)` | `a_c` | eq4, eq8, eq13 | Figure 2c plots only three Code Gen models and Figure 4b plots exactly ONE DeepSeek-Llama-70B marker against the 32 its legend implies (A54), so three of its four (D,R) configurations have no accuracy reading anywhere and the fourth cannot be attributed to a specific (D,R). Corroborated by Section 7.3: admitting this model on an aliased value breaks two of the four printed tiers |
| `code_generation(D=2, R=4, model=DeepSeek-Llama-70B)` | `t_c (p90)` | eq3, eq5, eq6 | Figure 2d plots no generated-token CDF for DeepSeek-Llama-70B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `code_generation(D=2, R=4, model=NVLM-D-72B)` | `t_c (p90)` | eq3, eq5, eq6 | Figure 2d plots no generated-token CDF for NVLM-D-72B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `code_generation(D=4, R=2, model=DeepSeek-Llama-70B)` | `a_c` | eq4, eq8, eq13 | Figure 2c plots only three Code Gen models and Figure 4b plots exactly ONE DeepSeek-Llama-70B marker against the 32 its legend implies (A54), so three of its four (D,R) configurations have no accuracy reading anywhere and the fourth cannot be attributed to a specific (D,R). Corroborated by Section 7.3: admitting this model on an aliased value breaks two of the four printed tiers |
| `code_generation(D=4, R=2, model=DeepSeek-Llama-70B)` | `t_c (p90)` | eq3, eq5, eq6 | Figure 2d plots no generated-token CDF for DeepSeek-Llama-70B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `code_generation(D=4, R=2, model=NVLM-D-72B)` | `t_c (p90)` | eq3, eq5, eq6 | Figure 2d plots no generated-token CDF for NVLM-D-72B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `code_generation(D=4, R=4, model=DeepSeek-Llama-70B)` | `a_c` | eq4, eq8, eq13 | Figure 2c plots only three Code Gen models and Figure 4b plots exactly ONE DeepSeek-Llama-70B marker against the 32 its legend implies (A54), so three of its four (D,R) configurations have no accuracy reading anywhere and the fourth cannot be attributed to a specific (D,R). Corroborated by Section 7.3: admitting this model on an aliased value breaks two of the four printed tiers |
| `code_generation(D=4, R=4, model=DeepSeek-Llama-70B)` | `t_c (p90)` | eq3, eq5, eq6 | Figure 2d plots no generated-token CDF for DeepSeek-Llama-70B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `code_generation(D=4, R=4, model=NVLM-D-72B)` | `t_c (p90)` | eq3, eq5, eq6 | Figure 2d plots no generated-token CDF for NVLM-D-72B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `video_qa(F=1, model=Llama-3.2-90B, dag=stt_off)` | `a_c` | eq4, eq8, eq13 | Figure 2a omits Llama-3.2-90B entirely, and Figure 4a -- its only other appearance -- separates it at just three accuracy levels, where marker SIZE gives F but the HATCHING that encodes STT is below the resolution of a 1.3 pp marker (A55). Assigning STT by the 'Y beats N at equal F' pattern would be an inference from a pattern, not a reading |
| `video_qa(F=1, model=Llama-3.2-90B, dag=stt_off)` | `t_c (p90)` | eq3, eq5, eq6 | Figure 2b plots no generated-token CDF for Llama-3.2-90B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `video_qa(F=1, model=Llama-3.2-90B, dag=stt_on)` | `a_c` | eq4, eq8, eq13 | Figure 2a omits Llama-3.2-90B entirely, and Figure 4a -- its only other appearance -- separates it at just three accuracy levels, where marker SIZE gives F but the HATCHING that encodes STT is below the resolution of a 1.3 pp marker (A55). Assigning STT by the 'Y beats N at equal F' pattern would be an inference from a pattern, not a reading |
| `video_qa(F=1, model=Llama-3.2-90B, dag=stt_on)` | `t_c (p90)` | eq3, eq5, eq6 | Figure 2b plots no generated-token CDF for Llama-3.2-90B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `video_qa(F=10, model=Llama-3.2-90B, dag=stt_off)` | `a_c` | eq4, eq8, eq13 | Figure 2a omits Llama-3.2-90B entirely, and Figure 4a -- its only other appearance -- separates it at just three accuracy levels, where marker SIZE gives F but the HATCHING that encodes STT is below the resolution of a 1.3 pp marker (A55). Assigning STT by the 'Y beats N at equal F' pattern would be an inference from a pattern, not a reading |
| `video_qa(F=10, model=Llama-3.2-90B, dag=stt_off)` | `t_c (p90)` | eq3, eq5, eq6 | Figure 2b plots no generated-token CDF for Llama-3.2-90B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `video_qa(F=10, model=Llama-3.2-90B, dag=stt_on)` | `a_c` | eq4, eq8, eq13 | Figure 2a omits Llama-3.2-90B entirely, and Figure 4a -- its only other appearance -- separates it at just three accuracy levels, where marker SIZE gives F but the HATCHING that encodes STT is below the resolution of a 1.3 pp marker (A55). Assigning STT by the 'Y beats N at equal F' pattern would be an inference from a pattern, not a reading |
| `video_qa(F=10, model=Llama-3.2-90B, dag=stt_on)` | `t_c (p90)` | eq3, eq5, eq6 | Figure 2b plots no generated-token CDF for Llama-3.2-90B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `video_qa(F=5, model=Llama-3.2-90B, dag=stt_off)` | `a_c` | eq4, eq8, eq13 | Figure 2a omits Llama-3.2-90B entirely, and Figure 4a -- its only other appearance -- separates it at just three accuracy levels, where marker SIZE gives F but the HATCHING that encodes STT is below the resolution of a 1.3 pp marker (A55). Assigning STT by the 'Y beats N at equal F' pattern would be an inference from a pattern, not a reading |
| `video_qa(F=5, model=Llama-3.2-90B, dag=stt_off)` | `t_c (p90)` | eq3, eq5, eq6 | Figure 2b plots no generated-token CDF for Llama-3.2-90B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `video_qa(F=5, model=Llama-3.2-90B, dag=stt_on)` | `a_c` | eq4, eq8, eq13 | Figure 2a omits Llama-3.2-90B entirely, and Figure 4a -- its only other appearance -- separates it at just three accuracy levels, where marker SIZE gives F but the HATCHING that encodes STT is below the resolution of a 1.3 pp marker (A55). Assigning STT by the 'Y beats N at equal F' pattern would be an inference from a pattern, not a reading |
| `video_qa(F=5, model=Llama-3.2-90B, dag=stt_on)` | `t_c (p90)` | eq3, eq5, eq6 | Figure 2b plots no generated-token CDF for Llama-3.2-90B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `Gemma-3-27B/A100/TP=8` | `l_ttft_m` | eq5 | Figure 3 plots no TTFT point for Gemma-3-27B/A100/TP=8 at 1348 tokens/s; the TTFT panel's y-limit is 2 s and the saturation tail is clipped above it, so this is right-censored, not missing |
| `Llama-3.1-70B/A100/TP=8` | `l_ttft_m` | eq5 | Figure 3 plots no TTFT point for Llama-3.1-70B/A100/TP=8 at 555 tokens/s; the TTFT panel's y-limit is 2 s and the saturation tail is clipped above it, so this is right-censored, not missing |
| `Llama-3.1-70B/H100/TP=8` | `l_ttft_m` | eq5 | Figure 3 plots no TTFT point for Llama-3.1-70B/H100/TP=8 at 1523 tokens/s; the TTFT panel's y-limit is 2 s and the saturation tail is clipped above it, so this is right-censored, not missing |
| `Llava-OneVision-7B/A100/TP=4` | `l_ttft_m` | eq5 | no Figure 3 panel exists for Llava-OneVision-7B (A35); TTFT is reported in no table in either version (A36), so eq. (5) cannot be evaluated for this profile |
| `Llava-OneVision-7B/H100/TP=4` | `l_ttft_m` | eq5 | no Figure 3 panel exists for Llava-OneVision-7B (A35); TTFT is reported in no table in either version (A36), so eq. (5) cannot be evaluated for this profile |
| `NVLM-D-72B/A100/TP=8` | `l_ttft_m` | eq5 | Figure 3 plots no TTFT point for NVLM-D-72B/A100/TP=8 at 613 tokens/s; the TTFT panel's y-limit is 2 s and the saturation tail is clipped above it, so this is right-censored, not missing |
| `Phi-4/A100/TP=1` | `l_ttft_m` | eq5 | Figure 3 plots no TTFT point for Phi-4/A100/TP=1 at 355 tokens/s; the TTFT panel's y-limit is 2 s and the saturation tail is clipped above it, so this is right-censored, not missing |
| `A100` | `B_g` | eq7 | Sections 4.2 and 4.3 state no resource budget, so eq. (7) is inactive for the headline experiments. Section 4.5 (p.578) sweeps 2,000 A100 with 0-500 H100, but that budget belongs to that experiment and is not a profile (A43) |
| `H100` | `B_g` | eq7 | Sections 4.2 and 4.3 state no resource budget, so eq. (7) is inactive for the headline experiments. Section 4.5 (p.578) sweeps 2,000 A100 with 0-500 H100, but that budget belongs to that experiment and is not a profile (A43) |

## 3. Validation

| Check | Result |
|---|---|
| Section 6.2, Tables 5/6 vs Figure 3 curves | 17/17 tabled points lie on their own curve; worst residual 3.6% (tolerance 20%) |
| Section 5.2, Figure 2c bars vs printed tier labels | 4/4 tiers agree; worst residual 0.82 pp (tolerance 1.0 pp); every residual is positive, i.e. the chosen configuration CLEARS its tier rather than equalling it |
| Section 7.3 tier reconstruction, code_generation (8a, n=16) | worst residual 0.33 pp; within band: True |
| Section 7.3 tier reconstruction, video_qa (7a, n=18) | worst residual 0.30 pp; within band: True |
| A37b operating-point collapse | 18 rows discarded and recorded |
| Configuration space | 20 code generation + 24 video Q/A = 44 |
| Citation registry | 47 loci, all resolved |

## 4. Paper-version concordance

| Item | [OSDI] | [ARXIV] | Note |
|---|---|---|---|
| Chosen configurations, Video Q/A | Table 5 | Table 4 | A44: the `STT` column exists only in [OSDI] (True vs False) |
| Chosen configurations, Code Gen | Table 6 | Table 5 | A45: column headed `Agents` vs `Debaters`; the column is `D`, which resolves M2's A14 |
| p90 allocation rule | p.576 | *absent* | A46: the sentence that binds `t_c` to the p90 exists in one version only |

## 5. Named profile sets

| Set | Purpose |
|---|---|
| `baseline` | the default: every value at its point estimate |
| `paper_only` | values with PAPER_* provenance only; everything derived becomes `Unavailable`, so M4 can report what the paper alone supports |
| `pessimistic` | every band at its unfavourable end |
| `optimistic` | every band at its favourable end |
| `derived_tiers` | tiers recomputed from our population instead of the printed labels |

## 6. External sources

`c_g` is the only parameter with a non-paper source (A40).

| SKU | Hourly (whole VM, 8 GPUs) | Per GPU-second | Retrieved |
|---|---|---|---|
| A100 | $27.197 | $0.00094434 | 2026-09-12 |
| H100 | $98.320 | $0.00341389 | 2026-09-12 |

## 7. Arrival traces

| Trace | Workflow | Samples | Min rpm | Mean rpm | Max rpm | Peak/mean |
|---|---|---|---|---|---|---|
| chat | video_qa | 1316 | 1510.1 | 3149.5 | 4758.1 | 1.511 |
| coding | code_generation | 1314 | 352.1 | 2229.9 | 5704.1 | 2.558 |

Optimization epochs per trace: 24.

## 8. The ledger

One row per MILP-facing value (401 rows).

| Owner | Field | Value | Unit | Provenance | Citation | Band | Assumption / anchors |
|---|---|---|---|---|---|---|---|
| `code_generation(D=2, R=2, model=DeepSeek-Llama-70B)` | `a_c` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 4b, p.571 | - | Figure 2c plots only three Code Gen models and Figure 4b plots exactly ONE DeepSeek-Llama-70B marker against the 32 its legend implies (A54), so three of its four (D,R) configurations have no accuracy reading anywhere and the fourth cannot be attributed to a specific (D,R). Corroborated by Section 7.3: admitting this model on an aliased value breaks two of the four printed tiers |
| `code_generation(D=2, R=2, model=DeepSeek-Llama-70B)` | `t_c (p90)` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 2d, p.570 | - | Figure 2d plots no generated-token CDF for DeepSeek-Llama-70B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `code_generation(D=2, R=2, model=DeepSeek-Qwen-32B)` | `a_c` | 81.85 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2c, p.570 | [81.35, 82.35] | - |
| `code_generation(D=2, R=2, model=DeepSeek-Qwen-32B)` | `t_c (p90)` | 13270.5 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2d, p.570 | [12528, 14013] | - |
| `code_generation(D=2, R=2, model=Gemma-3-27B)` | `a_c` | 86.73 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2c, p.570 | [86.23, 87.23] | - |
| `code_generation(D=2, R=2, model=Gemma-3-27B)` | `t_c (p90)` | 1754 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2d, p.570 | [1564, 2259] | - |
| `code_generation(D=2, R=2, model=NVLM-D-72B)` | `a_c` | 53.1 | percent | PAPER_FIGURE_READ | [BOTH] Figure 4b, p.571 | [51.6, 54.6] | - |
| `code_generation(D=2, R=2, model=NVLM-D-72B)` | `t_c (p90)` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 2d, p.570 | - | Figure 2d plots no generated-token CDF for NVLM-D-72B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `code_generation(D=2, R=2, model=Phi-4)` | `a_c` | 66.61 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2c, p.570 | [66.11, 67.11] | - |
| `code_generation(D=2, R=2, model=Phi-4)` | `t_c (p90)` | 2070 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2d, p.570 | [1880, 3144] | - |
| `code_generation(D=2, R=4, model=DeepSeek-Llama-70B)` | `a_c` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 4b, p.571 | - | Figure 2c plots only three Code Gen models and Figure 4b plots exactly ONE DeepSeek-Llama-70B marker against the 32 its legend implies (A54), so three of its four (D,R) configurations have no accuracy reading anywhere and the fourth cannot be attributed to a specific (D,R). Corroborated by Section 7.3: admitting this model on an aliased value breaks two of the four printed tiers |
| `code_generation(D=2, R=4, model=DeepSeek-Llama-70B)` | `t_c (p90)` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 2d, p.570 | - | Figure 2d plots no generated-token CDF for DeepSeek-Llama-70B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `code_generation(D=2, R=4, model=DeepSeek-Qwen-32B)` | `a_c` | 85.54 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2c, p.570 | [85.04, 86.04] | - |
| `code_generation(D=2, R=4, model=DeepSeek-Qwen-32B)` | `t_c (p90)` | 20537.5 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2d, p.570 | [18721, 22354] | - |
| `code_generation(D=2, R=4, model=Gemma-3-27B)` | `a_c` | 87.92 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2c, p.570 | [87.42, 88.42] | - |
| `code_generation(D=2, R=4, model=Gemma-3-27B)` | `t_c (p90)` | 2069 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2d, p.570 | [1564, 2259] | - |
| `code_generation(D=2, R=4, model=NVLM-D-72B)` | `a_c` | 57.37 | percent | PAPER_FIGURE_READ | [BOTH] Figure 4b, p.571 | [55.87, 58.87] | - |
| `code_generation(D=2, R=4, model=NVLM-D-72B)` | `t_c (p90)` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 2d, p.570 | - | Figure 2d plots no generated-token CDF for NVLM-D-72B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `code_generation(D=2, R=4, model=Phi-4)` | `a_c` | 75.77 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2c, p.570 | [75.27, 76.27] | - |
| `code_generation(D=2, R=4, model=Phi-4)` | `t_c (p90)` | 2954 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2d, p.570 | [1880, 3144] | - |
| `code_generation(D=4, R=2, model=DeepSeek-Llama-70B)` | `a_c` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 4b, p.571 | - | Figure 2c plots only three Code Gen models and Figure 4b plots exactly ONE DeepSeek-Llama-70B marker against the 32 its legend implies (A54), so three of its four (D,R) configurations have no accuracy reading anywhere and the fourth cannot be attributed to a specific (D,R). Corroborated by Section 7.3: admitting this model on an aliased value breaks two of the four printed tiers |
| `code_generation(D=4, R=2, model=DeepSeek-Llama-70B)` | `t_c (p90)` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 2d, p.570 | - | Figure 2d plots no generated-token CDF for DeepSeek-Llama-70B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `code_generation(D=4, R=2, model=DeepSeek-Qwen-32B)` | `a_c` | 86.73 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2c, p.570 | [86.23, 87.23] | - |
| `code_generation(D=4, R=2, model=DeepSeek-Qwen-32B)` | `t_c (p90)` | 29305 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2d, p.570 | [26967, 31643] | - |
| `code_generation(D=4, R=2, model=Gemma-3-27B)` | `a_c` | 87.32 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2c, p.570 | [86.82, 87.82] | - |
| `code_generation(D=4, R=2, model=Gemma-3-27B)` | `t_c (p90)` | 3555 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2d, p.570 | [3365, 4376] | - |
| `code_generation(D=4, R=2, model=NVLM-D-72B)` | `a_c` | 72.63 | percent | PAPER_FIGURE_READ | [BOTH] Figure 4b, p.571 | [71.13, 74.13] | - |
| `code_generation(D=4, R=2, model=NVLM-D-72B)` | `t_c (p90)` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 2d, p.570 | - | Figure 2d plots no generated-token CDF for NVLM-D-72B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `code_generation(D=4, R=2, model=Phi-4)` | `a_c` | 67.2 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2c, p.570 | [66.7, 67.7] | - |
| `code_generation(D=4, R=2, model=Phi-4)` | `t_c (p90)` | 4929 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2d, p.570 | [4597, 5261] | - |
| `code_generation(D=4, R=4, model=DeepSeek-Llama-70B)` | `a_c` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 4b, p.571 | - | Figure 2c plots only three Code Gen models and Figure 4b plots exactly ONE DeepSeek-Llama-70B marker against the 32 its legend implies (A54), so three of its four (D,R) configurations have no accuracy reading anywhere and the fourth cannot be attributed to a specific (D,R). Corroborated by Section 7.3: admitting this model on an aliased value breaks two of the four printed tiers |
| `code_generation(D=4, R=4, model=DeepSeek-Llama-70B)` | `t_c (p90)` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 2d, p.570 | - | Figure 2d plots no generated-token CDF for DeepSeek-Llama-70B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `code_generation(D=4, R=4, model=DeepSeek-Qwen-32B)` | `a_c` | 91.61 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2c, p.570 | [91.11, 92.11] | - |
| `code_generation(D=4, R=4, model=DeepSeek-Qwen-32B)` | `t_c (p90)` | 39969 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2d, p.570 | [35056, 44882] | - |
| `code_generation(D=4, R=4, model=Gemma-3-27B)` | `a_c` | 89.23 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2c, p.570 | [88.73, 89.73] | - |
| `code_generation(D=4, R=4, model=Gemma-3-27B)` | `t_c (p90)` | 4186 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2d, p.570 | [3365, 4376] | - |
| `code_generation(D=4, R=4, model=NVLM-D-72B)` | `a_c` | 72.02 | percent | PAPER_FIGURE_READ | [BOTH] Figure 4b, p.571 | [70.52, 73.52] | - |
| `code_generation(D=4, R=4, model=NVLM-D-72B)` | `t_c (p90)` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 2d, p.570 | - | Figure 2d plots no generated-token CDF for NVLM-D-72B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `code_generation(D=4, R=4, model=Phi-4)` | `a_c` | 67.2 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2c, p.570 | [66.7, 67.7] | - |
| `code_generation(D=4, R=4, model=Phi-4)` | `t_c (p90)` | 9099.5 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2d, p.570 | [8610, 9589] | - |
| `video_qa(F=1, model=Gemma-3-27B, dag=stt_off)` | `a_c` | 50.3 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [49.8, 50.8] | - |
| `video_qa(F=1, model=Gemma-3-27B, dag=stt_off)` | `t_c (p90)` | 454 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [445, 492] | - |
| `video_qa(F=1, model=Gemma-3-27B, dag=stt_on)` | `a_c` | 54.82 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [54.32, 55.32] | - |
| `video_qa(F=1, model=Gemma-3-27B, dag=stt_on)` | `t_c (p90)` | 483 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [445, 492] | - |
| `video_qa(F=1, model=Llama-3.2-90B, dag=stt_off)` | `a_c` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 4a, p.571 | - | Figure 2a omits Llama-3.2-90B entirely, and Figure 4a -- its only other appearance -- separates it at just three accuracy levels, where marker SIZE gives F but the HATCHING that encodes STT is below the resolution of a 1.3 pp marker (A55). Assigning STT by the 'Y beats N at equal F' pattern would be an inference from a pattern, not a reading |
| `video_qa(F=1, model=Llama-3.2-90B, dag=stt_off)` | `t_c (p90)` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 2b, p.570 | - | Figure 2b plots no generated-token CDF for Llama-3.2-90B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `video_qa(F=1, model=Llama-3.2-90B, dag=stt_on)` | `a_c` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 4a, p.571 | - | Figure 2a omits Llama-3.2-90B entirely, and Figure 4a -- its only other appearance -- separates it at just three accuracy levels, where marker SIZE gives F but the HATCHING that encodes STT is below the resolution of a 1.3 pp marker (A55). Assigning STT by the 'Y beats N at equal F' pattern would be an inference from a pattern, not a reading |
| `video_qa(F=1, model=Llama-3.2-90B, dag=stt_on)` | `t_c (p90)` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 2b, p.570 | - | Figure 2b plots no generated-token CDF for Llama-3.2-90B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `video_qa(F=1, model=Llava-OneVision-7B, dag=stt_off)` | `a_c` | 33.75 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [33.25, 34.25] | - |
| `video_qa(F=1, model=Llava-OneVision-7B, dag=stt_off)` | `t_c (p90)` | 309 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [206, 318] | - |
| `video_qa(F=1, model=Llava-OneVision-7B, dag=stt_on)` | `a_c` | 50.77 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [50.27, 51.27] | - |
| `video_qa(F=1, model=Llava-OneVision-7B, dag=stt_on)` | `t_c (p90)` | 215 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [206, 318] | - |
| `video_qa(F=1, model=NVLM-D-72B, dag=stt_off)` | `a_c` | 39.7 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [39.2, 40.2] | - |
| `video_qa(F=1, model=NVLM-D-72B, dag=stt_off)` | `t_c (p90)` | 193.5 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [188, 199] | - |
| `video_qa(F=1, model=NVLM-D-72B, dag=stt_on)` | `a_c` | 56.25 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [55.75, 56.75] | - |
| `video_qa(F=1, model=NVLM-D-72B, dag=stt_on)` | `t_c (p90)` | 193.5 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [188, 199] | - |
| `video_qa(F=10, model=Gemma-3-27B, dag=stt_off)` | `a_c` | 61.37 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [60.87, 61.87] | - |
| `video_qa(F=10, model=Gemma-3-27B, dag=stt_off)` | `t_c (p90)` | 768 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [759, 818] | - |
| `video_qa(F=10, model=Gemma-3-27B, dag=stt_on)` | `a_c` | 66.49 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [65.99, 66.99] | - |
| `video_qa(F=10, model=Gemma-3-27B, dag=stt_on)` | `t_c (p90)` | 809 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [759, 818] | - |
| `video_qa(F=10, model=Llama-3.2-90B, dag=stt_off)` | `a_c` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 4a, p.571 | - | Figure 2a omits Llama-3.2-90B entirely, and Figure 4a -- its only other appearance -- separates it at just three accuracy levels, where marker SIZE gives F but the HATCHING that encodes STT is below the resolution of a 1.3 pp marker (A55). Assigning STT by the 'Y beats N at equal F' pattern would be an inference from a pattern, not a reading |
| `video_qa(F=10, model=Llama-3.2-90B, dag=stt_off)` | `t_c (p90)` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 2b, p.570 | - | Figure 2b plots no generated-token CDF for Llama-3.2-90B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `video_qa(F=10, model=Llama-3.2-90B, dag=stt_on)` | `a_c` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 4a, p.571 | - | Figure 2a omits Llama-3.2-90B entirely, and Figure 4a -- its only other appearance -- separates it at just three accuracy levels, where marker SIZE gives F but the HATCHING that encodes STT is below the resolution of a 1.3 pp marker (A55). Assigning STT by the 'Y beats N at equal F' pattern would be an inference from a pattern, not a reading |
| `video_qa(F=10, model=Llama-3.2-90B, dag=stt_on)` | `t_c (p90)` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 2b, p.570 | - | Figure 2b plots no generated-token CDF for Llama-3.2-90B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `video_qa(F=10, model=Llava-OneVision-7B, dag=stt_off)` | `a_c` | 51.25 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [50.75, 51.75] | - |
| `video_qa(F=10, model=Llava-OneVision-7B, dag=stt_off)` | `t_c (p90)` | 1406.5 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [1290, 1523] | - |
| `video_qa(F=10, model=Llava-OneVision-7B, dag=stt_on)` | `a_c` | 57.2 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [56.7, 57.7] | - |
| `video_qa(F=10, model=Llava-OneVision-7B, dag=stt_on)` | `t_c (p90)` | 1100.5 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [1061, 1140] | - |
| `video_qa(F=10, model=NVLM-D-72B, dag=stt_off)` | `a_c` | 52.68 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [52.18, 53.18] | - |
| `video_qa(F=10, model=NVLM-D-72B, dag=stt_off)` | `t_c (p90)` | 209 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [195, 223] | - |
| `video_qa(F=10, model=NVLM-D-72B, dag=stt_on)` | `a_c` | 62.56 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [62.06, 63.06] | - |
| `video_qa(F=10, model=NVLM-D-72B, dag=stt_on)` | `t_c (p90)` | 209 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [195, 223] | - |
| `video_qa(F=5, model=Gemma-3-27B, dag=stt_off)` | `a_c` | 58.99 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [58.49, 59.49] | - |
| `video_qa(F=5, model=Gemma-3-27B, dag=stt_off)` | `t_c (p90)` | 612 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [603, 648] | - |
| `video_qa(F=5, model=Gemma-3-27B, dag=stt_on)` | `a_c` | 64.7 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [64.2, 65.2] | - |
| `video_qa(F=5, model=Gemma-3-27B, dag=stt_on)` | `t_c (p90)` | 639 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [603, 648] | - |
| `video_qa(F=5, model=Llama-3.2-90B, dag=stt_off)` | `a_c` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 4a, p.571 | - | Figure 2a omits Llama-3.2-90B entirely, and Figure 4a -- its only other appearance -- separates it at just three accuracy levels, where marker SIZE gives F but the HATCHING that encodes STT is below the resolution of a 1.3 pp marker (A55). Assigning STT by the 'Y beats N at equal F' pattern would be an inference from a pattern, not a reading |
| `video_qa(F=5, model=Llama-3.2-90B, dag=stt_off)` | `t_c (p90)` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 2b, p.570 | - | Figure 2b plots no generated-token CDF for Llama-3.2-90B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `video_qa(F=5, model=Llama-3.2-90B, dag=stt_on)` | `a_c` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 4a, p.571 | - | Figure 2a omits Llama-3.2-90B entirely, and Figure 4a -- its only other appearance -- separates it at just three accuracy levels, where marker SIZE gives F but the HATCHING that encodes STT is below the resolution of a 1.3 pp marker (A55). Assigning STT by the 'Y beats N at equal F' pattern would be an inference from a pattern, not a reading |
| `video_qa(F=5, model=Llama-3.2-90B, dag=stt_on)` | `t_c (p90)` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 2b, p.570 | - | Figure 2b plots no generated-token CDF for Llama-3.2-90B, and no table in either version reports token counts. Section 2.5 (p.570) reports an ~8x spread between a reasoning and a non-reasoning model of similar size ('~20,000 tokens versus ~2,500'), so interpolating from parameter count would carry an 8x error bar |
| `video_qa(F=5, model=Llava-OneVision-7B, dag=stt_off)` | `a_c` | 48.75 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [48.25, 49.25] | - |
| `video_qa(F=5, model=Llava-OneVision-7B, dag=stt_off)` | `t_c (p90)` | 712 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [593, 721] | - |
| `video_qa(F=5, model=Llava-OneVision-7B, dag=stt_on)` | `a_c` | 57.2 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [56.7, 57.7] | - |
| `video_qa(F=5, model=Llava-OneVision-7B, dag=stt_on)` | `t_c (p90)` | 602 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [593, 721] | - |
| `video_qa(F=5, model=NVLM-D-72B, dag=stt_off)` | `a_c` | 47.8 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [47.3, 48.3] | - |
| `video_qa(F=5, model=NVLM-D-72B, dag=stt_off)` | `t_c (p90)` | 179 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [163, 195] | - |
| `video_qa(F=5, model=NVLM-D-72B, dag=stt_on)` | `a_c` | 61.73 | percent | PAPER_FIGURE_READ | [BOTH] Figure 2a, p.570 | [61.23, 62.23] | - |
| `video_qa(F=5, model=NVLM-D-72B, dag=stt_on)` | `t_c (p90)` | 179 | tokens | PAPER_FIGURE_READ | [BOTH] Figure 2b, p.570 | [163, 195] | - |
| `DeepSeek-Qwen-32B/A100/TP=4` | `theta_m` | 653 | tokens/s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `DeepSeek-Qwen-32B/A100/TP=4` | `l_ttft_m` | 0.50316 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.488065, 0.518255] | - |
| `DeepSeek-Qwen-32B/A100/TP=4` | `l_tpot_m` | 0.0767 | s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `DeepSeek-Qwen-32B/A100/TP=4` | `g_m` | 4 | gpus | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `DeepSeek-Qwen-32B/A100/TP=4` | `e_m` | 0.796569 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.637255, 0.955882] | anchors: Table3/A100-only-row.energy_mwh. Table 3 row with 1292 A100 GPUs and no other type: 24.7 MWh / 24 h / 1292 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `DeepSeek-Qwen-32B/A100/TP=8` | `theta_m` | 1006.93 | tokens/s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [976.722, 1037.14] | - |
| `DeepSeek-Qwen-32B/A100/TP=8` | `l_ttft_m` | 0.62915 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.610275, 0.648025] | - |
| `DeepSeek-Qwen-32B/A100/TP=8` | `l_tpot_m` | 0.06483 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.0628851, 0.0667749] | - |
| `DeepSeek-Qwen-32B/A100/TP=8` | `g_m` | 8 | gpus | PAPER_FIGURE_LABEL | [BOTH] Figure 3, p.570 | exact | - |
| `DeepSeek-Qwen-32B/A100/TP=8` | `e_m` | 0.796569 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.637255, 0.955882] | anchors: Table3/A100-only-row.energy_mwh. Table 3 row with 1292 A100 GPUs and no other type: 24.7 MWh / 24 h / 1292 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `DeepSeek-Qwen-32B/H100/TP=4` | `theta_m` | 1390 | tokens/s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `DeepSeek-Qwen-32B/H100/TP=4` | `l_ttft_m` | 0.21613 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.209646, 0.222614] | - |
| `DeepSeek-Qwen-32B/H100/TP=4` | `l_tpot_m` | 0.0387 | s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `DeepSeek-Qwen-32B/H100/TP=4` | `g_m` | 4 | gpus | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `DeepSeek-Qwen-32B/H100/TP=4` | `e_m` | 0.925926 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.740741, 1.11111] | anchors: Table3/H100-only-row.energy_mwh. Table 3 row with 495 H100 GPUs and no other type: 11.0 MWh / 24 h / 495 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `DeepSeek-Qwen-32B/H100/TP=8` | `theta_m` | 2419.37 | tokens/s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [2346.79, 2491.95] | - |
| `DeepSeek-Qwen-32B/H100/TP=8` | `l_ttft_m` | 0.32332 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.31362, 0.33302] | - |
| `DeepSeek-Qwen-32B/H100/TP=8` | `l_tpot_m` | 0.04489 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.0435433, 0.0462367] | - |
| `DeepSeek-Qwen-32B/H100/TP=8` | `g_m` | 8 | gpus | PAPER_FIGURE_LABEL | [BOTH] Figure 3, p.570 | exact | - |
| `DeepSeek-Qwen-32B/H100/TP=8` | `e_m` | 0.925926 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.740741, 1.11111] | anchors: Table3/H100-only-row.energy_mwh. Table 3 row with 495 H100 GPUs and no other type: 11.0 MWh / 24 h / 495 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `Gemma-3-27B/A100/TP=4` | `theta_m` | 700 | tokens/s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Gemma-3-27B/A100/TP=4` | `l_ttft_m` | 0.39916 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.387185, 0.411135] | - |
| `Gemma-3-27B/A100/TP=4` | `l_tpot_m` | 0.0624 | s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Gemma-3-27B/A100/TP=4` | `g_m` | 4 | gpus | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Gemma-3-27B/A100/TP=4` | `e_m` | 0.796569 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.637255, 0.955882] | anchors: Table3/A100-only-row.energy_mwh. Table 3 row with 1292 A100 GPUs and no other type: 24.7 MWh / 24 h / 1292 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `Gemma-3-27B/A100/TP=8` | `theta_m` | 1348.45 | tokens/s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [1308, 1388.9] | - |
| `Gemma-3-27B/A100/TP=8` | `l_ttft_m` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 3, p.570 | - | Figure 3 plots no TTFT point for Gemma-3-27B/A100/TP=8 at 1348 tokens/s; the TTFT panel's y-limit is 2 s and the saturation tail is clipped above it, so this is right-censored, not missing |
| `Gemma-3-27B/A100/TP=8` | `l_tpot_m` | 0.0978 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.094866, 0.100734] | - |
| `Gemma-3-27B/A100/TP=8` | `g_m` | 8 | gpus | PAPER_FIGURE_LABEL | [BOTH] Figure 3, p.570 | exact | - |
| `Gemma-3-27B/A100/TP=8` | `e_m` | 0.796569 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.637255, 0.955882] | anchors: Table3/A100-only-row.energy_mwh. Table 3 row with 1292 A100 GPUs and no other type: 24.7 MWh / 24 h / 1292 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `Gemma-3-27B/H100/TP=4` | `theta_m` | 1709 | tokens/s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Gemma-3-27B/H100/TP=4` | `l_ttft_m` | 0.17129 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.166151, 0.176429] | - |
| `Gemma-3-27B/H100/TP=4` | `l_tpot_m` | 0.0496 | s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Gemma-3-27B/H100/TP=4` | `g_m` | 4 | gpus | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Gemma-3-27B/H100/TP=4` | `e_m` | 0.925926 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.740741, 1.11111] | anchors: Table3/H100-only-row.energy_mwh. Table 3 row with 495 H100 GPUs and no other type: 11.0 MWh / 24 h / 495 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `Gemma-3-27B/H100/TP=8` | `theta_m` | 2417.22 | tokens/s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [2344.7, 2489.74] | - |
| `Gemma-3-27B/H100/TP=8` | `l_ttft_m` | 0.26104 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.253209, 0.268871] | - |
| `Gemma-3-27B/H100/TP=8` | `l_tpot_m` | 0.04225 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.0409825, 0.0435175] | - |
| `Gemma-3-27B/H100/TP=8` | `g_m` | 8 | gpus | PAPER_FIGURE_LABEL | [BOTH] Figure 3, p.570 | exact | - |
| `Gemma-3-27B/H100/TP=8` | `e_m` | 0.925926 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.740741, 1.11111] | anchors: Table3/H100-only-row.energy_mwh. Table 3 row with 495 H100 GPUs and no other type: 11.0 MWh / 24 h / 495 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `Llama-3.1-70B/A100/TP=8` | `theta_m` | 554.66 | tokens/s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [538.02, 571.3] | - |
| `Llama-3.1-70B/A100/TP=8` | `l_ttft_m` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 3, p.570 | - | Figure 3 plots no TTFT point for Llama-3.1-70B/A100/TP=8 at 555 tokens/s; the TTFT panel's y-limit is 2 s and the saturation tail is clipped above it, so this is right-censored, not missing |
| `Llama-3.1-70B/A100/TP=8` | `l_tpot_m` | 0.09418 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.0913546, 0.0970054] | - |
| `Llama-3.1-70B/A100/TP=8` | `g_m` | 8 | gpus | PAPER_FIGURE_LABEL | [BOTH] Figure 3, p.570 | exact | - |
| `Llama-3.1-70B/A100/TP=8` | `e_m` | 0.796569 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.637255, 0.955882] | anchors: Table3/A100-only-row.energy_mwh. Table 3 row with 1292 A100 GPUs and no other type: 24.7 MWh / 24 h / 1292 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `Llama-3.1-70B/H100/TP=8` | `theta_m` | 1522.7 | tokens/s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [1477.02, 1568.38] | - |
| `Llama-3.1-70B/H100/TP=8` | `l_ttft_m` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 3, p.570 | - | Figure 3 plots no TTFT point for Llama-3.1-70B/H100/TP=8 at 1523 tokens/s; the TTFT panel's y-limit is 2 s and the saturation tail is clipped above it, so this is right-censored, not missing |
| `Llama-3.1-70B/H100/TP=8` | `l_tpot_m` | 0.07075 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.0686275, 0.0728725] | - |
| `Llama-3.1-70B/H100/TP=8` | `g_m` | 8 | gpus | PAPER_FIGURE_LABEL | [BOTH] Figure 3, p.570 | exact | - |
| `Llama-3.1-70B/H100/TP=8` | `e_m` | 0.925926 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.740741, 1.11111] | anchors: Table3/H100-only-row.energy_mwh. Table 3 row with 495 H100 GPUs and no other type: 11.0 MWh / 24 h / 495 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `Llava-OneVision-7B/A100/TP=4` | `theta_m` | 2244 | tokens/s | PAPER_TABLE | [BOTH] Table 5, p.585 | exact | - |
| `Llava-OneVision-7B/A100/TP=4` | `l_ttft_m` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 3, p.570 | - | no Figure 3 panel exists for Llava-OneVision-7B (A35); TTFT is reported in no table in either version (A36), so eq. (5) cannot be evaluated for this profile |
| `Llava-OneVision-7B/A100/TP=4` | `l_tpot_m` | 0.0224 | s | PAPER_TABLE | [BOTH] Table 5, p.585 | exact | - |
| `Llava-OneVision-7B/A100/TP=4` | `g_m` | 4 | gpus | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Llava-OneVision-7B/A100/TP=4` | `e_m` | 0.796569 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.637255, 0.955882] | anchors: Table3/A100-only-row.energy_mwh. Table 3 row with 1292 A100 GPUs and no other type: 24.7 MWh / 24 h / 1292 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `Llava-OneVision-7B/H100/TP=4` | `theta_m` | 2836 | tokens/s | PAPER_TABLE | [BOTH] Table 5, p.585 | exact | - |
| `Llava-OneVision-7B/H100/TP=4` | `l_ttft_m` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 3, p.570 | - | no Figure 3 panel exists for Llava-OneVision-7B (A35); TTFT is reported in no table in either version (A36), so eq. (5) cannot be evaluated for this profile |
| `Llava-OneVision-7B/H100/TP=4` | `l_tpot_m` | 0.007 | s | PAPER_TABLE | [BOTH] Table 5, p.585 | exact | - |
| `Llava-OneVision-7B/H100/TP=4` | `g_m` | 4 | gpus | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Llava-OneVision-7B/H100/TP=4` | `e_m` | 0.925926 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.740741, 1.11111] | anchors: Table3/H100-only-row.energy_mwh. Table 3 row with 495 H100 GPUs and no other type: 11.0 MWh / 24 h / 495 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `NVLM-D-72B/A100/TP=4` | `theta_m` | 325 | tokens/s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `NVLM-D-72B/A100/TP=4` | `l_ttft_m` | 1.13809 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [1.10395, 1.17223] | - |
| `NVLM-D-72B/A100/TP=4` | `l_tpot_m` | 0.0966 | s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `NVLM-D-72B/A100/TP=4` | `g_m` | 4 | gpus | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `NVLM-D-72B/A100/TP=4` | `e_m` | 0.796569 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.637255, 0.955882] | anchors: Table3/A100-only-row.energy_mwh. Table 3 row with 1292 A100 GPUs and no other type: 24.7 MWh / 24 h / 1292 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `NVLM-D-72B/A100/TP=8` | `theta_m` | 613.35 | tokens/s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [594.95, 631.75] | - |
| `NVLM-D-72B/A100/TP=8` | `l_ttft_m` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 3, p.570 | - | Figure 3 plots no TTFT point for NVLM-D-72B/A100/TP=8 at 613 tokens/s; the TTFT panel's y-limit is 2 s and the saturation tail is clipped above it, so this is right-censored, not missing |
| `NVLM-D-72B/A100/TP=8` | `l_tpot_m` | 0.10391 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.100793, 0.107027] | - |
| `NVLM-D-72B/A100/TP=8` | `g_m` | 8 | gpus | PAPER_FIGURE_LABEL | [BOTH] Figure 3, p.570 | exact | - |
| `NVLM-D-72B/A100/TP=8` | `e_m` | 0.796569 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.637255, 0.955882] | anchors: Table3/A100-only-row.energy_mwh. Table 3 row with 1292 A100 GPUs and no other type: 24.7 MWh / 24 h / 1292 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `NVLM-D-72B/H100/TP=4` | `theta_m` | 766 | tokens/s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `NVLM-D-72B/H100/TP=4` | `l_ttft_m` | 0.37385 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.362635, 0.385066] | - |
| `NVLM-D-72B/H100/TP=4` | `l_tpot_m` | 0.065 | s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `NVLM-D-72B/H100/TP=4` | `g_m` | 4 | gpus | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `NVLM-D-72B/H100/TP=4` | `e_m` | 0.925926 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.740741, 1.11111] | anchors: Table3/H100-only-row.energy_mwh. Table 3 row with 495 H100 GPUs and no other type: 11.0 MWh / 24 h / 495 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `NVLM-D-72B/H100/TP=8` | `theta_m` | 84 | tokens/s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `NVLM-D-72B/H100/TP=8` | `l_ttft_m` | 0.24169 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.234439, 0.248941] | - |
| `NVLM-D-72B/H100/TP=8` | `l_tpot_m` | 0.0129 | s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `NVLM-D-72B/H100/TP=8` | `g_m` | 8 | gpus | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `NVLM-D-72B/H100/TP=8` | `e_m` | 0.925926 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.740741, 1.11111] | anchors: Table3/H100-only-row.energy_mwh. Table 3 row with 495 H100 GPUs and no other type: 11.0 MWh / 24 h / 495 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `Phi-4/A100/TP=1` | `theta_m` | 355.16 | tokens/s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [344.505, 365.815] | - |
| `Phi-4/A100/TP=1` | `l_ttft_m` | *unavailable* | - | UNAVAILABLE | [BOTH] Figure 3, p.570 | - | Figure 3 plots no TTFT point for Phi-4/A100/TP=1 at 355 tokens/s; the TTFT panel's y-limit is 2 s and the saturation tail is clipped above it, so this is right-censored, not missing |
| `Phi-4/A100/TP=1` | `l_tpot_m` | 0.10956 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.106273, 0.112847] | - |
| `Phi-4/A100/TP=1` | `g_m` | 1 | gpus | PAPER_FIGURE_LABEL | [BOTH] Figure 3, p.570 | exact | - |
| `Phi-4/A100/TP=1` | `e_m` | 0.796569 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.637255, 0.955882] | anchors: Table3/A100-only-row.energy_mwh. Table 3 row with 1292 A100 GPUs and no other type: 24.7 MWh / 24 h / 1292 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `Phi-4/A100/TP=2` | `theta_m` | 623 | tokens/s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Phi-4/A100/TP=2` | `l_ttft_m` | 0.69135 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.670609, 0.712091] | - |
| `Phi-4/A100/TP=2` | `l_tpot_m` | 0.0609 | s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Phi-4/A100/TP=2` | `g_m` | 2 | gpus | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Phi-4/A100/TP=2` | `e_m` | 0.796569 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.637255, 0.955882] | anchors: Table3/A100-only-row.energy_mwh. Table 3 row with 1292 A100 GPUs and no other type: 24.7 MWh / 24 h / 1292 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `Phi-4/H100/TP=1` | `theta_m` | 757 | tokens/s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Phi-4/H100/TP=1` | `l_ttft_m` | 0.26796 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.259921, 0.275999] | - |
| `Phi-4/H100/TP=1` | `l_tpot_m` | 0.0373 | s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Phi-4/H100/TP=1` | `g_m` | 1 | gpus | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Phi-4/H100/TP=1` | `e_m` | 0.925926 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.740741, 1.11111] | anchors: Table3/H100-only-row.energy_mwh. Table 3 row with 495 H100 GPUs and no other type: 11.0 MWh / 24 h / 495 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `Phi-4/H100/TP=2` | `theta_m` | 1185 | tokens/s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Phi-4/H100/TP=2` | `l_ttft_m` | 0.16596 | s | PAPER_FIGURE_READ | [BOTH] Figure 3, p.570 | [0.160981, 0.170939] | - |
| `Phi-4/H100/TP=2` | `l_tpot_m` | 0.0218 | s | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Phi-4/H100/TP=2` | `g_m` | 2 | gpus | PAPER_TABLE | [BOTH] Table 6, p.586 | exact | - |
| `Phi-4/H100/TP=2` | `e_m` | 0.925926 | kW/GPU | DERIVED | [BOTH] Table 3, p.578 | [0.740741, 1.11111] | anchors: Table3/H100-only-row.energy_mwh. Table 3 row with 495 H100 GPUs and no other type: 11.0 MWh / 24 h / 495 GPUs, ASSUMING the allocation was constant over the 24 h (Figure 11 p.578 shows it was not; the band is +/-20% to cover it). Per GPU because eq. (11) multiplies e_m by g_m (A57). |
| `A100` | `c_g` | 0.00094434 | $/GPU-s | EXTERNAL | EXTERNAL azure-retail-prices-api:Standard_ND96asr_v4 (retrieved 2026-09-12) | [0.00047217, 0.00141651] | Section 4.1 (p.575) describes the A100 host as 8xA100 80GB with an AMD EPYC 7V12 64-core processor, which identifies Standard_ND96asr_v4 uniquely in Azure's catalogue; list price is assumed (the paper's implied prices are roughly half list -- see `table_3_implied_cost_per_gpu_hour()` -- consistent with reserved or internal rates that are not published); c_g is per GPU because eqs. (6) and (12) multiply it by g_m. |
| `A100` | `B_g` | *unavailable* | - | UNAVAILABLE | [BOTH] Section 4.5, p.578 | - | Sections 4.2 and 4.3 state no resource budget, so eq. (7) is inactive for the headline experiments. Section 4.5 (p.578) sweeps 2,000 A100 with 0-500 H100, but that budget belongs to that experiment and is not a profile (A43) |
| `H100` | `c_g` | 0.00341389 | $/GPU-s | EXTERNAL | EXTERNAL azure-retail-prices-api:Standard_ND96isr_H100_v5 (retrieved 2026-09-12) | [0.00170694, 0.00512083] | Section 4.1 (p.575) describes the H100 host as 8xH100 80GB with an Intel Xeon (Sapphire Rapids) processor, which identifies Standard_ND96isr_H100_v5 uniquely in Azure's catalogue; list price is assumed (the paper's implied prices are roughly half list -- see `table_3_implied_cost_per_gpu_hour()` -- consistent with reserved or internal rates that are not published); c_g is per GPU because eqs. (6) and (12) multiply it by g_m. |
| `H100` | `B_g` | *unavailable* | - | UNAVAILABLE | [BOTH] Section 4.5, p.578 | - | Sections 4.2 and 4.3 state no resource budget, so eq. (7) is inactive for the headline experiments. Section 4.5 (p.578) sweeps 2,000 A100 with 0-500 H100, but that budget belongs to that experiment and is not a profile (A43) |
| `code_generation/accuracy/basic` | `tau` | 75.77 | percent | DERIVED | [BOTH] Section 3.4, p.575 | [75.27, 76.27] | anchors: code_generation(D=2, R=4, model=Phi-4).a_c. Section 3.4's rule applied to this set's own accuracy population with the `lower` percentile convention; reproduces the printed Figure 7a/8a labels to within the digitization band (Section 7.3) |
| `code_generation/accuracy/best` | `tau` | 91.61 | percent | DERIVED | [BOTH] Section 3.4, p.575 | [91.11, 92.11] | anchors: code_generation(D=4, R=4, model=DeepSeek-Qwen-32B).a_c. Section 3.4's rule applied to this set's own accuracy population with the `lower` percentile convention; reproduces the printed Figure 7a/8a labels to within the digitization band (Section 7.3) |
| `code_generation/accuracy/fair` | `tau` | 87.32 | percent | DERIVED | [BOTH] Section 3.4, p.575 | [86.82, 87.82] | anchors: code_generation(D=4, R=2, model=Gemma-3-27B).a_c. Section 3.4's rule applied to this set's own accuracy population with the `lower` percentile convention; reproduces the printed Figure 7a/8a labels to within the digitization band (Section 7.3) |
| `code_generation/accuracy/good` | `tau` | 89.23 | percent | DERIVED | [BOTH] Section 3.4, p.575 | [88.73, 89.73] | anchors: code_generation(D=4, R=4, model=Gemma-3-27B).a_c. Section 3.4's rule applied to this set's own accuracy population with the `lower` percentile convention; reproduces the printed Figure 7a/8a labels to within the digitization band (Section 7.3) |
| `code_generation/latency/basic` | `tau` | 78.2 | s | PAPER_FIGURE_LABEL | [BOTH] Figure 7b, p.575 | exact | - |
| `code_generation/latency/best` | `tau` | 11.3 | s | PAPER_FIGURE_LABEL | [BOTH] Figure 7b, p.575 | exact | - |
| `code_generation/latency/fair` | `tau` | 35.3 | s | PAPER_FIGURE_LABEL | [BOTH] Figure 7b, p.575 | exact | - |
| `code_generation/latency/good` | `tau` | 25.5 | s | PAPER_FIGURE_LABEL | [BOTH] Figure 7b, p.575 | exact | - |
| `video_qa/accuracy/basic` | `tau` | 54.82 | percent | DERIVED | [BOTH] Section 3.4, p.575 | [54.32, 55.32] | anchors: video_qa(F=1, model=Gemma-3-27B, dag=stt_on).a_c. Section 3.4's rule applied to this set's own accuracy population with the `lower` percentile convention; reproduces the printed Figure 7a/8a labels to within the digitization band (Section 7.3) |
| `video_qa/accuracy/best` | `tau` | 66.49 | percent | DERIVED | [BOTH] Section 3.4, p.575 | [65.99, 66.99] | anchors: video_qa(F=10, model=Gemma-3-27B, dag=stt_on).a_c. Section 3.4's rule applied to this set's own accuracy population with the `lower` percentile convention; reproduces the printed Figure 7a/8a labels to within the digitization band (Section 7.3) |
| `video_qa/accuracy/fair` | `tau` | 61.37 | percent | DERIVED | [BOTH] Section 3.4, p.575 | [60.87, 61.87] | anchors: video_qa(F=10, model=Gemma-3-27B, dag=stt_off).a_c. Section 3.4's rule applied to this set's own accuracy population with the `lower` percentile convention; reproduces the printed Figure 7a/8a labels to within the digitization band (Section 7.3) |
| `video_qa/accuracy/good` | `tau` | 64.7 | percent | DERIVED | [BOTH] Section 3.4, p.575 | [64.2, 65.2] | anchors: video_qa(F=5, model=Gemma-3-27B, dag=stt_on).a_c. Section 3.4's rule applied to this set's own accuracy population with the `lower` percentile convention; reproduces the printed Figure 7a/8a labels to within the digitization band (Section 7.3) |
| `video_qa/latency/basic` | `tau` | 5.8 | s | PAPER_FIGURE_LABEL | [BOTH] Figure 7b, p.575 | exact | - |
| `video_qa/latency/best` | `tau` | 0.5 | s | PAPER_FIGURE_LABEL | [BOTH] Figure 7b, p.575 | exact | - |
| `video_qa/latency/fair` | `tau` | 3 | s | PAPER_FIGURE_LABEL | [BOTH] Figure 7b, p.575 | exact | - |
| `video_qa/latency/good` | `tau` | 0.9 | s | PAPER_FIGURE_LABEL | [BOTH] Figure 7b, p.575 | exact | - |
| `code_generation/good/epoch 0` | `lambda_peak` | 7.94617 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [7.70778, 8.18455] | - |
| `code_generation/good/epoch 0` | `lambda_avg` | 6.21064 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [6.02432, 6.39696] | - |
| `code_generation/good/epoch 1` | `lambda_peak` | 7.0595 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [6.84771, 7.27128] | - |
| `code_generation/good/epoch 1` | `lambda_avg` | 5.64974 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [5.48025, 5.81923] | - |
| `code_generation/good/epoch 2` | `lambda_peak` | 9.6145 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [9.32606, 9.90293] | - |
| `code_generation/good/epoch 2` | `lambda_avg` | 6.73629 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [6.5342, 6.93838] | - |
| `code_generation/good/epoch 3` | `lambda_peak` | 14.3628 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [13.9319, 14.7937] | - |
| `code_generation/good/epoch 3` | `lambda_avg` | 9.76742 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [9.47439, 10.0604] | - |
| `code_generation/good/epoch 4` | `lambda_peak` | 26.7645 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [25.9616, 27.5674] | - |
| `code_generation/good/epoch 4` | `lambda_avg` | 17.8685 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [17.3324, 18.4045] | - |
| `code_generation/good/epoch 5` | `lambda_peak` | 43.3662 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [42.0652, 44.6672] | - |
| `code_generation/good/epoch 5` | `lambda_avg` | 30.4047 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [29.4926, 31.3169] | - |
| `code_generation/good/epoch 6` | `lambda_peak` | 51.9178 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [50.3603, 53.4754] | - |
| `code_generation/good/epoch 6` | `lambda_avg` | 41.1923 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [39.9565, 42.428] | - |
| `code_generation/good/epoch 7` | `lambda_peak` | 54.6828 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [53.0423, 56.3233] | - |
| `code_generation/good/epoch 7` | `lambda_avg` | 46.3866 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [44.995, 47.7782] | - |
| `code_generation/good/epoch 8` | `lambda_peak` | 51.7195 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [50.1679, 53.2711] | - |
| `code_generation/good/epoch 8` | `lambda_avg` | 46.5242 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [45.1285, 47.9199] | - |
| `code_generation/good/epoch 9` | `lambda_peak` | 58.7078 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [56.9466, 60.4691] | - |
| `code_generation/good/epoch 9` | `lambda_avg` | 51.1879 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [49.6523, 52.7236] | - |
| `code_generation/good/epoch 10` | `lambda_peak` | 64.5062 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [62.571, 66.4414] | - |
| `code_generation/good/epoch 10` | `lambda_avg` | 57.1035 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [55.3903, 58.8166] | - |
| `code_generation/good/epoch 11` | `lambda_peak` | 66.5478 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [64.5514, 68.5443] | - |
| `code_generation/good/epoch 11` | `lambda_avg` | 59.1382 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [57.3641, 60.9123] | - |
| `code_generation/good/epoch 12` | `lambda_peak` | 65.8478 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [63.8724, 67.8233] | - |
| `code_generation/good/epoch 12` | `lambda_avg` | 57.5111 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [55.7858, 59.2364] | - |
| `code_generation/good/epoch 13` | `lambda_peak` | 53.1312 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [51.5372, 54.7251] | - |
| `code_generation/good/epoch 13` | `lambda_avg` | 40.8475 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [39.6221, 42.0729] | - |
| `code_generation/good/epoch 14` | `lambda_peak` | 33.1228 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [32.1291, 34.1165] | - |
| `code_generation/good/epoch 14` | `lambda_avg` | 26.6932 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [25.8924, 27.494] | - |
| `code_generation/good/epoch 15` | `lambda_peak` | 25.1662 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [24.4112, 25.9212] | - |
| `code_generation/good/epoch 15` | `lambda_avg` | 21.9504 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [21.2919, 22.6089] | - |
| `code_generation/good/epoch 16` | `lambda_peak` | 22.0862 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [21.4236, 22.7488] | - |
| `code_generation/good/epoch 16` | `lambda_avg` | 18.0851 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [17.5426, 18.6277] | - |
| `code_generation/good/epoch 17` | `lambda_peak` | 20.3362 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [19.7261, 20.9463] | - |
| `code_generation/good/epoch 17` | `lambda_avg` | 16.5074 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [16.0122, 17.0026] | - |
| `code_generation/good/epoch 18` | `lambda_peak` | 21.2578 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [20.6201, 21.8956] | - |
| `code_generation/good/epoch 18` | `lambda_avg` | 17.4111 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [16.8887, 17.9334] | - |
| `code_generation/good/epoch 19` | `lambda_peak` | 17.5478 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [17.0214, 18.0743] | - |
| `code_generation/good/epoch 19` | `lambda_avg` | 13.2276 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [12.8307, 13.6244] | - |
| `code_generation/good/epoch 20` | `lambda_peak` | 13.3595 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [12.9587, 13.7603] | - |
| `code_generation/good/epoch 20` | `lambda_avg` | 10.3556 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [10.045, 10.6663] | - |
| `code_generation/good/epoch 21` | `lambda_peak` | 13.1028 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [12.7097, 13.4959] | - |
| `code_generation/good/epoch 21` | `lambda_avg` | 9.05405 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [8.78243, 9.32567] | - |
| `code_generation/good/epoch 22` | `lambda_peak` | 10.7112 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [10.3898, 11.0325] | - |
| `code_generation/good/epoch 22` | `lambda_avg` | 8.38636 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [8.13477, 8.63795] | - |
| `code_generation/good/epoch 23` | `lambda_peak` | 8.7045 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [8.44337, 8.96563] | - |
| `code_generation/good/epoch 23` | `lambda_avg` | 6.77929 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [6.57591, 6.98267] | - |
| `code_generation/good/epoch 0` | `lambda_peak` | 3.4055 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [3.30334, 3.50767] | - |
| `code_generation/good/epoch 0` | `lambda_avg` | 2.6617 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [2.58185, 2.74155] | - |
| `code_generation/good/epoch 1` | `lambda_peak` | 3.0255 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [2.93473, 3.11627] | - |
| `code_generation/good/epoch 1` | `lambda_avg` | 2.42132 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [2.34868, 2.49396] | - |
| `code_generation/good/epoch 2` | `lambda_peak` | 4.1205 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [3.99688, 4.24411] | - |
| `code_generation/good/epoch 2` | `lambda_avg` | 2.88698 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [2.80037, 2.97359] | - |
| `code_generation/good/epoch 3` | `lambda_peak` | 6.1555 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [5.97084, 6.34016] | - |
| `code_generation/good/epoch 3` | `lambda_avg` | 4.18604 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [4.06045, 4.31162] | - |
| `code_generation/good/epoch 4` | `lambda_peak` | 11.4705 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [11.1264, 11.8146] | - |
| `code_generation/good/epoch 4` | `lambda_avg` | 7.65791 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [7.42817, 7.88764] | - |
| `code_generation/good/epoch 5` | `lambda_peak` | 18.5855 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [18.0279, 19.1431] | - |
| `code_generation/good/epoch 5` | `lambda_avg` | 13.0306 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [12.6397, 13.4215] | - |
| `code_generation/good/epoch 6` | `lambda_peak` | 22.2505 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [21.583, 22.918] | - |
| `code_generation/good/epoch 6` | `lambda_avg` | 17.6538 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [17.1242, 18.1834] | - |
| `code_generation/good/epoch 7` | `lambda_peak` | 23.4355 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [22.7324, 24.1386] | - |
| `code_generation/good/epoch 7` | `lambda_avg` | 19.88 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [19.2836, 20.4764] | - |
| `code_generation/good/epoch 8` | `lambda_peak` | 22.1655 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [21.5005, 22.8305] | - |
| `code_generation/good/epoch 8` | `lambda_avg` | 19.9389 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [19.3408, 20.5371] | - |
| `code_generation/good/epoch 9` | `lambda_peak` | 25.1605 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [24.4057, 25.9153] | - |
| `code_generation/good/epoch 9` | `lambda_avg` | 21.9377 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [21.2796, 22.5958] | - |
| `code_generation/good/epoch 10` | `lambda_peak` | 27.6455 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [26.8161, 28.4749] | - |
| `code_generation/good/epoch 10` | `lambda_avg` | 24.4729 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [23.7387, 25.2071] | - |
| `code_generation/good/epoch 11` | `lambda_peak` | 28.5205 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [27.6649, 29.3761] | - |
| `code_generation/good/epoch 11` | `lambda_avg` | 25.3449 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [24.5846, 26.1053] | - |
| `code_generation/good/epoch 12` | `lambda_peak` | 28.2205 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [27.3739, 29.0671] | - |
| `code_generation/good/epoch 12` | `lambda_avg` | 24.6476 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [23.9082, 25.387] | - |
| `code_generation/good/epoch 13` | `lambda_peak` | 22.7705 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [22.0874, 23.4536] | - |
| `code_generation/good/epoch 13` | `lambda_avg` | 17.5061 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [16.9809, 18.0312] | - |
| `code_generation/good/epoch 14` | `lambda_peak` | 14.1955 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [13.7696, 14.6214] | - |
| `code_generation/good/epoch 14` | `lambda_avg` | 11.44 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [11.0968, 11.7832] | - |
| `code_generation/good/epoch 15` | `lambda_peak` | 10.7855 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [10.4619, 11.1091] | - |
| `code_generation/good/epoch 15` | `lambda_avg` | 9.40733 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [9.12511, 9.68955] | - |
| `code_generation/good/epoch 16` | `lambda_peak` | 9.4655 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [9.18153, 9.74946] | - |
| `code_generation/good/epoch 16` | `lambda_avg` | 7.75076 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [7.51824, 7.98328] | - |
| `code_generation/good/epoch 17` | `lambda_peak` | 8.7155 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [8.45403, 8.97696] | - |
| `code_generation/good/epoch 17` | `lambda_avg` | 7.07461 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [6.86237, 7.28685] | - |
| `code_generation/good/epoch 18` | `lambda_peak` | 9.1105 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [8.83718, 9.38382] | - |
| `code_generation/good/epoch 18` | `lambda_avg` | 7.46188 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [7.23802, 7.68574] | - |
| `code_generation/good/epoch 19` | `lambda_peak` | 7.5205 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [7.29488, 7.74611] | - |
| `code_generation/good/epoch 19` | `lambda_avg` | 5.66895 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [5.49889, 5.83902] | - |
| `code_generation/good/epoch 20` | `lambda_peak` | 5.7255 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [5.55373, 5.89726] | - |
| `code_generation/good/epoch 20` | `lambda_avg` | 4.43813 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [4.30499, 4.57128] | - |
| `code_generation/good/epoch 21` | `lambda_peak` | 5.6155 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [5.44703, 5.78396] | - |
| `code_generation/good/epoch 21` | `lambda_avg` | 3.88031 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [3.7639, 3.99672] | - |
| `code_generation/good/epoch 22` | `lambda_peak` | 4.5905 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [4.45279, 4.72822] | - |
| `code_generation/good/epoch 22` | `lambda_avg` | 3.59415 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [3.48633, 3.70198] | - |
| `code_generation/good/epoch 23` | `lambda_peak` | 3.7305 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [3.61858, 3.84242] | - |
| `code_generation/good/epoch 23` | `lambda_avg` | 2.90541 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [2.81825, 2.99257] | - |
| `video_qa/good/epoch 0` | `lambda_peak` | 44.1828 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [42.8573, 45.5083] | - |
| `video_qa/good/epoch 0` | `lambda_avg` | 38.5755 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [37.4183, 39.7328] | - |
| `video_qa/good/epoch 1` | `lambda_peak` | 42.2928 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [41.024, 43.5616] | - |
| `video_qa/good/epoch 1` | `lambda_avg` | 39.235 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [38.058, 40.4121] | - |
| `video_qa/good/epoch 2` | `lambda_peak` | 40.0178 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [38.8173, 41.2184] | - |
| `video_qa/good/epoch 2` | `lambda_avg` | 36.1386 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [35.0544, 37.2227] | - |
| `video_qa/good/epoch 3` | `lambda_peak` | 42.8645 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [41.5786, 44.1504] | - |
| `video_qa/good/epoch 3` | `lambda_avg` | 37.7103 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [36.579, 38.8416] | - |
| `video_qa/good/epoch 4` | `lambda_peak` | 47.2978 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [45.8789, 48.7168] | - |
| `video_qa/good/epoch 4` | `lambda_avg` | 43.1387 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [41.8445, 44.4328] | - |
| `video_qa/good/epoch 5` | `lambda_peak` | 55.5112 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [53.8458, 57.1765] | - |
| `video_qa/good/epoch 5` | `lambda_avg` | 47.3702 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [45.9491, 48.7914] | - |
| `video_qa/good/epoch 6` | `lambda_peak` | 53.8078 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [52.1936, 55.4221] | - |
| `video_qa/good/epoch 6` | `lambda_avg` | 48.4108 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [46.9585, 49.8632] | - |
| `video_qa/good/epoch 7` | `lambda_peak` | 53.0845 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [51.492, 54.677] | - |
| `video_qa/good/epoch 7` | `lambda_avg` | 45.9039 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [44.5268, 47.281] | - |
| `video_qa/good/epoch 8` | `lambda_peak` | 46.3062 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [44.917, 47.6954] | - |
| `video_qa/good/epoch 8` | `lambda_avg` | 41.7449 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [40.4926, 42.9972] | - |
| `video_qa/good/epoch 9` | `lambda_peak` | 46.4228 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [45.0301, 47.8155] | - |
| `video_qa/good/epoch 9` | `lambda_avg` | 38.9741 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [37.8049, 40.1433] | - |
| `video_qa/good/epoch 10` | `lambda_peak` | 45.8628 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [44.4869, 47.2387] | - |
| `video_qa/good/epoch 10` | `lambda_avg` | 40.8858 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [39.6593, 42.1124] | - |
| `video_qa/good/epoch 11` | `lambda_peak` | 43.7745 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [42.4613, 45.0877] | - |
| `video_qa/good/epoch 11` | `lambda_avg` | 38.667 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [37.507, 39.8271] | - |
| `video_qa/good/epoch 12` | `lambda_peak` | 38.2678 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [37.1198, 39.4159] | - |
| `video_qa/good/epoch 12` | `lambda_avg` | 33.4695 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [32.4654, 34.4736] | - |
| `video_qa/good/epoch 13` | `lambda_peak` | 34.6862 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [33.6456, 35.7268] | - |
| `video_qa/good/epoch 13` | `lambda_avg` | 25.3032 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [24.5442, 26.0623] | - |
| `video_qa/good/epoch 14` | `lambda_peak` | 27.7912 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [26.9574, 28.6249] | - |
| `video_qa/good/epoch 14` | `lambda_avg` | 24.3791 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [23.6477, 25.1105] | - |
| `video_qa/good/epoch 15` | `lambda_peak` | 32.6445 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [31.6652, 33.6238] | - |
| `video_qa/good/epoch 15` | `lambda_avg` | 27.3903 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [26.5686, 28.212] | - |
| `video_qa/good/epoch 16` | `lambda_peak` | 34.7678 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [33.7248, 35.8109] | - |
| `video_qa/good/epoch 16` | `lambda_avg` | 31.8198 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [30.8652, 32.7744] | - |
| `video_qa/good/epoch 17` | `lambda_peak` | 50.4945 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [48.9797, 52.0093] | - |
| `video_qa/good/epoch 17` | `lambda_avg` | 34.9554 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [33.9067, 36.0041] | - |
| `video_qa/good/epoch 18` | `lambda_peak` | 38.1278 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [36.984, 39.2717] | - |
| `video_qa/good/epoch 18` | `lambda_avg` | 35.3976 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [34.3357, 36.4596] | - |
| `video_qa/good/epoch 19` | `lambda_peak` | 35.4562 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [34.3925, 36.5199] | - |
| `video_qa/good/epoch 19` | `lambda_avg` | 29.5155 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [28.63, 30.4009] | - |
| `video_qa/good/epoch 20` | `lambda_peak` | 33.4728 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [32.4686, 34.477] | - |
| `video_qa/good/epoch 20` | `lambda_avg` | 29.1068 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [28.2336, 29.98] | - |
| `video_qa/good/epoch 21` | `lambda_peak` | 37.4162 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [36.2937, 38.5387] | - |
| `video_qa/good/epoch 21` | `lambda_avg` | 31.4397 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [30.4965, 32.3828] | - |
| `video_qa/good/epoch 22` | `lambda_peak` | 42.8762 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [41.5899, 44.1625] | - |
| `video_qa/good/epoch 22` | `lambda_avg` | 38.9881 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [37.8184, 40.1577] | - |
| `video_qa/good/epoch 23` | `lambda_peak` | 47.0645 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [45.6526, 48.4764] | - |
| `video_qa/good/epoch 23` | `lambda_avg` | 40.9061 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [39.679, 42.1333] | - |
| `video_qa/good/epoch 0` | `lambda_peak` | 18.9355 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [18.3674, 19.5036] | - |
| `video_qa/good/epoch 0` | `lambda_avg` | 16.5324 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [16.0364, 17.0283] | - |
| `video_qa/good/epoch 1` | `lambda_peak` | 18.1255 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [17.5817, 18.6693] | - |
| `video_qa/good/epoch 1` | `lambda_avg` | 16.815 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [16.3106, 17.3195] | - |
| `video_qa/good/epoch 2` | `lambda_peak` | 17.1505 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [16.636, 17.665] | - |
| `video_qa/good/epoch 2` | `lambda_avg` | 15.488 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [15.0233, 15.9526] | - |
| `video_qa/good/epoch 3` | `lambda_peak` | 18.3705 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [17.8194, 18.9216] | - |
| `video_qa/good/epoch 3` | `lambda_avg` | 16.1616 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [15.6767, 16.6464] | - |
| `video_qa/good/epoch 4` | `lambda_peak` | 20.2705 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [19.6624, 20.8786] | - |
| `video_qa/good/epoch 4` | `lambda_avg` | 18.488 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [17.9334, 19.0426] | - |
| `video_qa/good/epoch 5` | `lambda_peak` | 23.7905 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [23.0768, 24.5042] | - |
| `video_qa/good/epoch 5` | `lambda_avg` | 20.3015 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [19.6925, 20.9106] | - |
| `video_qa/good/epoch 6` | `lambda_peak` | 23.0605 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [22.3687, 23.7523] | - |
| `video_qa/good/epoch 6` | `lambda_avg` | 20.7475 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [20.1251, 21.3699] | - |
| `video_qa/good/epoch 7` | `lambda_peak` | 22.7505 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [22.068, 23.433] | - |
| `video_qa/good/epoch 7` | `lambda_avg` | 19.6731 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [19.0829, 20.2633] | - |
| `video_qa/good/epoch 8` | `lambda_peak` | 19.8455 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [19.2501, 20.4409] | - |
| `video_qa/good/epoch 8` | `lambda_avg` | 17.8907 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [17.354, 18.4274] | - |
| `video_qa/good/epoch 9` | `lambda_peak` | 19.8955 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [19.2986, 20.4924] | - |
| `video_qa/good/epoch 9` | `lambda_avg` | 16.7032 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [16.2021, 17.2043] | - |
| `video_qa/good/epoch 10` | `lambda_peak` | 19.6555 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [19.0658, 20.2452] | - |
| `video_qa/good/epoch 10` | `lambda_avg` | 17.5225 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [16.9968, 18.0482] | - |
| `video_qa/good/epoch 11` | `lambda_peak` | 18.7605 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [18.1977, 19.3233] | - |
| `video_qa/good/epoch 11` | `lambda_avg` | 16.5716 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [16.0744, 17.0687] | - |
| `video_qa/good/epoch 12` | `lambda_peak` | 16.4005 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [15.9085, 16.8925] | - |
| `video_qa/good/epoch 12` | `lambda_avg` | 14.3441 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [13.9138, 14.7744] | - |
| `video_qa/good/epoch 13` | `lambda_peak` | 14.8655 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [14.4195, 15.3115] | - |
| `video_qa/good/epoch 13` | `lambda_avg` | 10.8442 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [10.5189, 11.1696] | - |
| `video_qa/good/epoch 14` | `lambda_peak` | 11.9105 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [11.5532, 12.2678] | - |
| `video_qa/good/epoch 14` | `lambda_avg` | 10.4482 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [10.1347, 10.7616] | - |
| `video_qa/good/epoch 15` | `lambda_peak` | 13.9905 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [13.5708, 14.4102] | - |
| `video_qa/good/epoch 15` | `lambda_avg` | 11.7387 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [11.3866, 12.0909] | - |
| `video_qa/good/epoch 16` | `lambda_peak` | 14.9005 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [14.4535, 15.3475] | - |
| `video_qa/good/epoch 16` | `lambda_avg` | 13.637 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [13.2279, 14.0462] | - |
| `video_qa/good/epoch 17` | `lambda_peak` | 21.6405 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [20.9913, 22.2897] | - |
| `video_qa/good/epoch 17` | `lambda_avg` | 14.9809 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [14.5315, 15.4303] | - |
| `video_qa/good/epoch 18` | `lambda_peak` | 16.3405 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [15.8503, 16.8307] | - |
| `video_qa/good/epoch 18` | `lambda_avg` | 15.1704 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [14.7153, 15.6255] | - |
| `video_qa/good/epoch 19` | `lambda_peak` | 15.1955 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [14.7396, 15.6514] | - |
| `video_qa/good/epoch 19` | `lambda_avg` | 12.6495 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [12.27, 13.029] | - |
| `video_qa/good/epoch 20` | `lambda_peak` | 14.3455 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [13.9151, 14.7759] | - |
| `video_qa/good/epoch 20` | `lambda_avg` | 12.4743 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [12.1001, 12.8486] | - |
| `video_qa/good/epoch 21` | `lambda_peak` | 16.0355 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [15.5544, 16.5166] | - |
| `video_qa/good/epoch 21` | `lambda_avg` | 13.4741 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [13.0699, 13.8784] | - |
| `video_qa/good/epoch 22` | `lambda_peak` | 18.3755 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [17.8242, 18.9268] | - |
| `video_qa/good/epoch 22` | `lambda_avg` | 16.7092 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [16.2079, 17.2105] | - |
| `video_qa/good/epoch 23` | `lambda_peak` | 20.1705 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [19.5654, 20.7756] | - |
| `video_qa/good/epoch 23` | `lambda_avg` | 17.5312 | req/s | PAPER_FIGURE_READ | [BOTH] Figure 19, p.587 | [17.0053, 18.0571] | - |
| `global` | `alpha` | 1.15 | dimensionless | PAPER_TEXT | [BOTH] Section A.5, p.586 | exact | - |
