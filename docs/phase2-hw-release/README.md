# Phase 2 course release

| Document | PDF | Source |
| --- | --- | --- |
| Student instructions | [Phase 2: Port, Review Policies, Test, Inspect](phase2-instruction.pdf) | [TeX](phase2-instruction.tex) |
| Runtime handout | [How Runtime Enforcement Works](how-runtime-enforcement-works.pdf) | [TeX](how-runtime-enforcement-works.tex) |

The TeX files are the source of truth for this release. Keep each PDF in sync with its source; review screenshots live in `images/`. For framework installation and application adaptation, see [setup](../setup.md) and [porting](../porting.md).

Build from this directory with a LaTeX installation providing `latexmk`, pdfLaTeX and the packages imported by the sources:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error phase2-instruction.tex
latexmk -pdf -interaction=nonstopmode -halt-on-error how-runtime-enforcement-works.tex
latexmk -c phase2-instruction.tex how-runtime-enforcement-works.tex
```

Retain the sources, release PDFs and referenced images. Auxiliary LaTeX outputs are ignored.
