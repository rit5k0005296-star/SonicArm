# Development sources

The Skill suite was distilled from the current SonicArm source tree, implementation reports, handoff documents, retained tool outputs, and project interaction records. Reusable rules were confirmed against executable tests and official PYNQ/AMD interfaces before inclusion.

The package records the source category used for each capability:

- HWH, bitstream and manifest handling: project Overlay artifacts and HWH parser tests.
- Register drivers: explicit add-IP interface contract and generated MockMMIO driver.
- DMA and cache handling: PYNQ Buffer/DMA APIs plus fake Buffer and channel tests.
- Golden and report automation: numeric fixtures, benchmark JSON and Vivado text-report fixtures.

