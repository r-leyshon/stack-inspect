.PHONY: stack-values

# Launch the reference stack with parameter values recorded.
stack-values:
	STACK_INSPECT_VALUES=1 NEXT_PUBLIC_STACK_INSPECT_VALUES=1 uv run python scripts/e2e_stack.py
