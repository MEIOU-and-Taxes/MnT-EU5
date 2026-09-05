When running any script, make sure the working directory is a child of `tools` (or a sibling of `shared` folder)
eu5lint is the exception: run it from the repository root (`python3 tools/eu5lint check --root .`), as CI does.
